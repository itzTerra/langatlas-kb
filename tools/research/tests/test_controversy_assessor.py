"""What must hold whatever the model says: the level is in range, the signals are real, and
escalation is computed rather than volunteered."""
import pytest

from langatlas_research.controversy.assessor import (
    Assessment, AssessmentOut, assess_inputs, needs_escalation,
)
from langatlas_research.controversy.inputs import ControversyInputs
from langatlas_research.errors import AssessorOutputInvalid

INPUTS = ControversyInputs.from_mapping({
    "debates": [{"id": "d-01-typing-003", "outcome": "escalated", "standing_dissent": True,
                 "rounds": 4}],
    "verdicts": [{"fact": "f-a", "citation": 1, "verdict": "contradicted", "field": "base",
                  "tier": "A"}],
    "source_strength": {"tier_a": 2, "tier_b": 0, "independent_corroborations": 1},
})


class _Completion:
    def __init__(self, parsed, model="deepseek-v4-pro-thinking"):
        self.parsed, self.resolved_model = parsed, model


def _reply(fake_ctx, **out):
    fake_ctx.completions.append(lambda alias, messages, schema: _Completion(AssessmentOut(**out)))


def test_a_clean_assessment_comes_back_with_its_signals(fake_ctx):
    _reply(fake_ctx, level=3, alternative=None,
           signals=["debate:d-01-typing-003:standing-dissent", "verdict:contradicted:base"])
    assessment = assess_inputs(fake_ctx, "f-a", INPUTS, alias="thinker")
    assert assessment.level == 3
    assert assessment.signals == ("debate:d-01-typing-003:standing-dissent",
                                  "verdict:contradicted:base")
    assert assessment.model == "deepseek-v4-pro-thinking"
    assert assessment.prompt.startswith("controversy-assessor@v-")


def test_the_thinker_alias_is_the_one_asked_for(fake_ctx):
    _reply(fake_ctx, level=0, alternative=None, signals=[])
    assess_inputs(fake_ctx, "f-a", INPUTS, alias="thinker")
    assert fake_ctx.complete_calls[0]["alias"] == "thinker"


def test_an_invented_signal_is_dropped(fake_ctx):
    """§6.4 makes the signals list the justification, so a signal the inputs cannot produce is
    a fabricated justification — not a weak one."""
    _reply(fake_ctx, level=2, alternative=1,
           signals=["verdict:contradicted:base", "debate:d-99-made-up-001:escalated"])
    assessment = assess_inputs(fake_ctx, "f-a", INPUTS, alias="thinker")
    assert assessment.signals == ("verdict:contradicted:base",)


def test_a_non_adjacent_alternative_is_dropped(fake_ctx):
    _reply(fake_ctx, level=3, alternative=0, signals=[])
    assert assess_inputs(fake_ctx, "f-a", INPUTS, alias="thinker").alternative is None


def test_an_out_of_range_level_is_refused(fake_ctx):
    fake_ctx.completions.append(
        lambda alias, messages, schema: _Completion(
            type("O", (), {"level": 4, "alternative": None, "signals": []})()))
    with pytest.raises(AssessorOutputInvalid, match="4"):
        assess_inputs(fake_ctx, "f-a", INPUTS, alias="thinker")


def test_level_3_always_escalates():
    assert needs_escalation(Assessment(fact_id="f-a", level=3, signals=(), alternative=None))


def test_an_adjacent_alternative_escalates():
    assert needs_escalation(Assessment(fact_id="f-a", level=1, signals=(), alternative=2))


def test_a_confident_low_level_does_not_escalate():
    assert not needs_escalation(Assessment(fact_id="f-a", level=1, signals=(), alternative=None))


def test_the_prompt_lists_only_derivable_signals(fake_ctx):
    """The vocabulary handed to the model is the same set the filter enforces — a model asked
    to choose from a list it is then punished for using would just look unreliable."""
    _reply(fake_ctx, level=0, alternative=None, signals=[])
    assess_inputs(fake_ctx, "f-a", INPUTS, alias="thinker")
    rendered = "\n".join(m["content"] for m in fake_ctx.complete_calls[0]["messages"])
    assert "debate:d-01-typing-003:standing-dissent" in rendered
    assert "d-99" not in rendered
