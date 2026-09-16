"""§6.4's assessor: one university-API `thinker` call over a fixed rubric.

Three things the model is not allowed to decide:

1. **Whether its justification is real.** Signals are intersected with `derivable_signals`, so a
   reference the inputs cannot produce never reaches the record. §6.4 has no prose rationale to
   fall back on, which makes a fabricated signal a fabricated justification.
2. **Whether it gets reviewed.** It types the adjacent level it nearly chose; `needs_escalation`
   reads that plus the level. A model that could type "escalate" could also decline to.
3. **What model answered.** `resolved_model` comes off the completion, and `RunContext` pins the
   alias for the run (D26) — a level whose provenance said `thinker` while something else
   answered would be unauditable."""
import json
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from langatlas_ingest.goldens.items import CONTROVERSY_LEVELS
from langatlas_pipeline.prompts import PromptRef, load_prompt

from langatlas_research.controversy.inputs import ControversyInputs, derivable_signals
from langatlas_research.errors import AssessorOutputInvalid

ASSESSOR_PROMPT_ID = "controversy-assessor"


class AssessmentOut(BaseModel):
    level: int = Field(ge=0, le=3)
    alternative: int | None = None
    signals: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class Assessment:
    """One fact's level, with everything needed to stamp it into a record and audit it."""

    fact_id: str
    level: int
    signals: tuple[str, ...] = ()
    alternative: int | None = None
    model: str = ""
    prompt: str = ""
    run_id: str = ""
    escalated_to: str | None = None


def _vocabulary(inputs: ControversyInputs) -> str:
    signals = sorted(derivable_signals(inputs))
    return "\n".join(f"  - {signal}" for signal in signals) or "  (none)"


def assess_inputs(ctx, fact_id: str, inputs: ControversyInputs, *, alias: str,
                  prompt: PromptRef | None = None) -> Assessment:
    """Assess one fact.

    @param ctx: a `RunContext` (or a test double exposing `complete`).
    @param alias: the completion alias, from `config/research.yaml` — `thinker` in production.
    @raises AssessorOutputInvalid: a level outside 0-3.
    @raises BudgetExceeded / StructuredOutputError: unchanged from `ctx.complete`; the
        orchestrator turns the first into a clean pause."""
    prompt = prompt or load_prompt(ASSESSOR_PROMPT_ID)
    messages = prompt.render(
        inputs_json=json.dumps(inputs.as_dict(), indent=2, sort_keys=True),
        signal_vocabulary=_vocabulary(inputs))
    completion = ctx.complete(alias, messages, prompt=prompt, schema=AssessmentOut)
    out = completion.parsed
    if out.level not in CONTROVERSY_LEVELS:
        raise AssessorOutputInvalid(
            f"{fact_id}: level {out.level!r} is not one of {list(CONTROVERSY_LEVELS)}")

    allowed = derivable_signals(inputs)
    signals = tuple(s for s in dict.fromkeys(out.signals) if s in allowed)
    alternative = out.alternative
    if alternative is not None and (alternative not in CONTROVERSY_LEVELS
                                    or abs(alternative - out.level) != 1):
        # "Adjacent-level ambiguity" is what §6.4 routes to Claude. A two-level gap is not
        # ambiguity, it is a model contradicting itself, and treating it as a review request
        # would spend Claude credits on noise.
        alternative = None
    return Assessment(fact_id=fact_id, level=out.level, signals=signals,
                      alternative=alternative, model=completion.resolved_model,
                      prompt=prompt.ref(), run_id=getattr(ctx, "run_id", ""))


def needs_escalation(assessment: Assessment) -> bool:
    """§6.4: Claude reviews adjacent-level ambiguity and **every** level-3 assignment.

    Level 3 is unconditional because it is the level the site renders as an AI-judged dispute
    and the one a false positive is most expensive on."""
    return assessment.level == 3 or assessment.alternative is not None


class GoldenAssessor:
    """§6.4's calibration adapter: `ControversyCase -> int`, the `Assessor` protocol 2B froze.

    Deliberately thin. A golden case supplies its structured inputs directly, so this skips
    assembly entirely and exercises what a model can actually get wrong: the rubric, the signal
    filter and the escalation policy.

    It opens a `RunContext` lazily on first use and closes it in `close()`, which step 6 teaches
    `golden-score` to call — a calibration number whose transcript was never finalized is a
    number nobody can trace back to a model and a prompt version."""

    def __init__(self, *, assess=assess_inputs, escalate=None, ctx=None, alias: str = "thinker",
                 prompt: PromptRef | None = None):
        self._assess, self._escalate = assess, escalate
        self._ctx, self._alias, self._prompt = ctx, alias, prompt
        self._owns_ctx = False

    def _context(self):
        if self._ctx is None:
            from langatlas_pipeline.providers.core import RunContext

            self._ctx = RunContext.start(kind="controversy-goldens", slug="scored")
            self._owns_ctx = True
        return self._ctx

    def __call__(self, case) -> int:
        """@raises ControversyInputRefused: a case carrying a forbidden or unknown input —
            surfaced, never scored as a level, because a case the assessor may not legally see
            is a broken case, not a hard one."""
        inputs = ControversyInputs.from_mapping(case.inputs or {})
        assessment = self._assess(self._context(), case.id, inputs, alias=self._alias,
                                  prompt=self._prompt)
        if self._escalate is not None and needs_escalation(assessment):
            assessment = self._escalate(assessment, inputs)
        return int(assessment.level)

    def close(self) -> None:
        if self._owns_ctx and self._ctx is not None:
            self._ctx.close()
            self._ctx, self._owns_ctx = None, False


def _claude_escalator():
    from langatlas_pipeline.providers.core import RunContext
    from langatlas_research.config import ResearchConfig
    from langatlas_research.controversy.escalate import escalate as _escalate
    from langatlas_research.paths import research_config_path

    config = ResearchConfig.load(research_config_path()).controversy

    def _run(assessment, inputs):
        with RunContext.start(kind="controversy-escalation", slug=assessment.fact_id) as ctx:
            return _escalate(ctx, assessment, inputs, role_config=config.escalation)

    return _run


def _default_alias() -> str:
    from langatlas_research.config import ResearchConfig
    from langatlas_research.paths import research_config_path

    return ResearchConfig.load(research_config_path()).controversy.alias


class _LazyGoldenAssessor(GoldenAssessor):
    """The module-level entry point `config/ingest.yaml` names.

    Config is read on first call rather than at import, so merely importing this module — which
    `load_entry_point` does — never touches the filesystem or a provider."""

    def __init__(self, *, escalate_factory=None):
        super().__init__(escalate=None, alias="")
        self._escalate_factory = escalate_factory
        self._configured = False

    def __call__(self, case) -> int:
        if not self._configured:
            self._alias = _default_alias()
            if self._escalate_factory is not None:
                self._escalate = self._escalate_factory()
            self._configured = True
        return super().__call__(case)


#: What production does, escalation included — the entry point `config/ingest.yaml` names.
golden_assessor = _LazyGoldenAssessor(escalate_factory=_claude_escalator)
#: The university-API pass alone. Useful for measuring how much of level-3 recall the
#: escalation step is carrying.
golden_assessor_thinker_only = _LazyGoldenAssessor()
