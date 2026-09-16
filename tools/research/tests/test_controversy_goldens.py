"""§6.4's calibration path: the committed cases in, an ordinal score out."""
import pytest

from langatlas_ingest.goldens.items import ControversyCase
from langatlas_ingest.goldens.loader import load_controversy_cases, validate_controversy_cases
from langatlas_ingest.goldens.runner import run_controversy_goldens
from langatlas_ingest.paths import GOLDEN_CONTROVERSY_DIR
from langatlas_research.controversy.assessor import Assessment, GoldenAssessor

CASE = ControversyCase(
    id="c-test-0001", expected_level=3,
    inputs={"debates": [{"id": "d-01-typing-003", "outcome": "escalated",
                         "standing_dissent": True, "rounds": 4}],
            "verdicts": [{"fact": "f-a", "citation": 1, "verdict": "contradicted",
                          "field": "base", "tier": "A"}],
            "source_strength": {"tier_a": 2, "tier_b": 0, "independent_corroborations": 1}},
    expected_signals=("verdict:contradicted:base", "debate:d-01-typing-003:escalated"))


def test_the_entry_point_returns_a_bare_ordinal_level():
    """`Assessor` is `(case) -> int`. The runner scores integers; anything else is a crash at
    the far end of a paid run."""
    assessor = GoldenAssessor(assess=lambda ctx, fact_id, inputs, *, alias, prompt=None:
                              Assessment(fact_id=fact_id, level=3, signals=()),
                              escalate=None, ctx=object(), alias="thinker")
    assert assessor(CASE) == 3


def test_a_case_id_stands_in_for_the_fact_id():
    seen = []

    def _assess(ctx, fact_id, inputs, *, alias, prompt=None):
        seen.append(fact_id)
        return Assessment(fact_id=fact_id, level=0, signals=())

    GoldenAssessor(assess=_assess, escalate=None, ctx=object(), alias="thinker")(CASE)
    assert seen == ["c-test-0001"]


def test_escalation_runs_for_the_golden_set_too():
    """Level 3 always escalates in production (§6.4), so a scored run that skipped escalation
    would measure something the pipeline never does — and level-3 recall is the headline
    metric."""
    escalated = []

    def _assess(ctx, fact_id, inputs, *, alias, prompt=None):
        return Assessment(fact_id=fact_id, level=3, signals=())

    def _escalate(assessment, inputs):
        escalated.append(assessment.fact_id)
        return Assessment(fact_id=assessment.fact_id, level=2, signals=(),
                          escalated_to="claude")

    assert GoldenAssessor(assess=_assess, escalate=_escalate, ctx=object(),
                          alias="thinker")(CASE) == 2
    assert escalated == ["c-test-0001"]


def test_a_refused_input_surfaces_as_a_scoring_failure_not_a_silent_zero():
    bad = ControversyCase(id="c-test-0002", expected_level=0,
                          inputs={"github_activity": {"issues": 3}})
    assessor = GoldenAssessor(assess=lambda *a, **k: Assessment(fact_id="x", level=0),
                              escalate=None, ctx=object(), alias="thinker")
    with pytest.raises(Exception):
        assessor(bad)


def test_the_committed_bootstrap_cases_still_validate():
    cases = load_controversy_cases(GOLDEN_CONTROVERSY_DIR)
    assert validate_controversy_cases(cases) == []
    assert len(cases) >= 15


def test_the_runner_scores_a_perfect_assessor_at_one():
    cases = load_controversy_cases(GOLDEN_CONTROVERSY_DIR)
    expected = {case.id: case.expected_level for case in cases}
    score = run_controversy_goldens(cases, lambda case: expected[case.id])
    assert score.exact_accuracy == 1.0
    assert score.level3_recall == 1.0


def test_the_configured_entry_point_resolves_to_a_case_callable():
    """The bug this guards: `golden-score` calls `load_entry_point(...)` and hands the result
    straight to the runner as the assessor."""
    from langatlas_ingest.config import IngestConfig
    from langatlas_ingest.goldens.runner import load_entry_point

    dotted = IngestConfig.load().controversy_assessor_entry_point
    assert dotted
    assessor = load_entry_point(dotted)
    assert callable(assessor) and not isinstance(assessor, type)
