"""Claude's review of a level the thinker was unsure about, or set to 3.

Two jobs, and the second is the one that compounds: §6.4's controversy golden set has a
bootstrap lane of ~15-20 synthetic cases and an **opportunistic lane** that "the Claude-escalation
reviews produce". Every escalation here is therefore written out as an uncurated candidate the
developer can hand-label, which is how the set walks toward its ~50-case target without anybody
sitting down to invent cases.

Candidates land in `tests/golden/controversy/candidates/`, not in the golden directory itself:
`load_controversy_cases` globs `*.yaml` non-recursively and raises on `curated: false`, so a
subdirectory is invisible to it — the same arrangement `tests/golden/verifier/held-out/` uses."""
import io
from dataclasses import replace
from pathlib import Path

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from langatlas_research.controversy.assessor import Assessment
from langatlas_research.controversy.inputs import ControversyInputs, derivable_signals
from langatlas_research.survey.claude import role_budget, run_structured

ESCALATION_PROMPT_ID = "controversy-escalation"

_yaml = YAML(typ="safe")


class EscalationOut(BaseModel):
    level: int = Field(ge=0, le=3)
    signals: list[str] = Field(default_factory=list)


def escalate(ctx, proposed: Assessment, inputs: ControversyInputs, *, role_config,
             prompt=None) -> Assessment:
    """Run the Claude review and return the final assessment.

    @param ctx: a `RunContext` opened for the escalation (D18 — its own context, so the review
        is greppable separately from the volume pass).
    @returns a new `Assessment` carrying Claude's level, filtered signals, and
        `escalated_to="claude"`. `alternative` is cleared: the ambiguity has been adjudicated,
        and carrying it forward would re-escalate the same fact every night.
    @raises SurveyOutputInvalid: no usable structured output, unchanged from `run_structured`."""
    from langatlas_pipeline.prompts import load_prompt

    prompt = prompt or load_prompt(ESCALATION_PROMPT_ID)
    import json

    parsed, _result = run_structured(
        ctx, prompt,
        {"inputs_json": json.dumps(inputs.as_dict(), indent=2, sort_keys=True),
         "signal_vocabulary": "\n".join(f"  - {s}" for s in sorted(derivable_signals(inputs)))
                              or "  (none)",
         "proposed_level": str(proposed.level),
         "alternative_level": "none" if proposed.alternative is None else str(proposed.alternative),
         "proposed_signals": ", ".join(proposed.signals) or "none"},
        output_model=EscalationOut, role_config=role_config)

    allowed = derivable_signals(inputs)
    signals = tuple(s for s in dict.fromkeys(parsed.signals) if s in allowed)
    return replace(proposed, level=parsed.level, signals=signals, alternative=None,
                   escalated_to="claude")


def candidates_path(*, repo_root: Path, today: str) -> Path:
    """One file per month, so the developer reviews a manageable batch rather than a file that
    grows forever."""
    return (Path(repo_root) / "tests" / "golden" / "controversy" / "candidates"
            / f"{today[:7]}.yaml")


def capture_candidate(proposed: Assessment, final: Assessment, inputs: ControversyInputs, *,
                      repo_root: Path, today: str) -> Path:
    """Append this review to the month's candidate file.

    `expected_level` is seeded with Claude's answer and `curated: false` — a seed, not a label.
    §6.4's golden-set methodology is explicit that cases are developer-curated; promoting one is
    the developer editing `expected_level` (or agreeing with it) and moving the case up into
    `tests/golden/controversy/`."""
    path = candidates_path(repo_root=repo_root, today=today)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = (_yaml.load(path.read_text()) or {}) if path.exists() else {}
    cases = existing.get("cases") or []
    cases.append({
        "id": f"c-escalated-{final.fact_id}-{today}",
        "expected_level": int(final.level),
        "first_pass_level": int(proposed.level),
        "first_pass_alternative": proposed.alternative,
        "inputs": inputs.as_dict(),
        "expected_signals": list(final.signals),
        "authored_by": "llm-curated",
        "curated": False,
        "notes": f"escalation review on {today}; first pass {proposed.model} said"
                 f" {proposed.level}, Claude said {final.level}",
    })
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    buf = io.StringIO()
    yaml.dump({"version": 1, "cases": cases}, buf)
    path.write_text(buf.getvalue())
    return path
