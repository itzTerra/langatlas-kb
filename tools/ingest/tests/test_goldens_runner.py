import pytest
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.goldens.items import Citation, Claim, ControversyCase, VerifierItem
from langatlas_ingest.goldens.runner import (
    load_entry_point, run_controversy_goldens, run_verifier_goldens,
)
from langatlas_ingest.goldens.score import Thresholds, VerdictOutcome

THRESHOLDS = Thresholds(false_accept_max=0.02, false_reject_max=0.10)


def item(item_id, stratum="correct", verdict="supported"):
    return VerifierItem(id=item_id, stratum=stratum, expected_verdict=verdict,
                        claim=Claim(kind="instance-exists",
                                    text=f"instance-exists(i-{item_id}, status=present)"),
                        citation=Citation(source="ctm", locator="p. 1"))


def test_the_runner_calls_the_verifier_once_per_item_and_scores_the_result():
    seen = []

    def verify(golden_item):
        seen.append(golden_item.id)
        return VerdictOutcome("supported")

    score = run_verifier_goldens([item("a"), item("b")], verify, thresholds=THRESHOLDS)
    assert seen == ["a", "b"] and score.items == 2 and score.thresholds_met is True


def test_the_verifier_only_ever_sees_the_whitelist_input():
    # Context blindness is 2D's to implement, but the runner must not be the thing that
    # leaks: this test pins that the runner hands over the item and nothing derived from
    # the expected verdict.
    captured = {}

    def verify(golden_item):
        captured.update(golden_item.verifier_input())
        return VerdictOutcome("supported")

    run_verifier_goldens([item("a")], verify, thresholds=THRESHOLDS)
    assert set(captured) == {"fact_id", "claim", "since", "source_id", "locator", "quote"}


def test_a_verifier_raising_is_recorded_as_a_source_unavailable_not_a_crash():
    def verify(golden_item):
        raise RuntimeError("provider down")

    score = run_verifier_goldens([item("a")], verify, thresholds=THRESHOLDS)
    assert score.items == 1 and score.false_reject_rate == 1.0


def test_the_entry_point_resolver_accepts_module_colon_attr():
    resolved = load_entry_point("langatlas_ingest.goldens.score:score_verifier")
    from langatlas_ingest.goldens.score import score_verifier
    assert resolved is score_verifier


def test_an_unresolvable_entry_point_names_what_it_tried():
    with pytest.raises(ImportError, match="langatlas_ingest.nope"):
        load_entry_point("langatlas_ingest.nope:thing")


def test_the_controversy_runner_scores_assigned_levels():
    cases = [ControversyCase(id="c1", expected_level=1, inputs={"verdicts": []})]
    score = run_controversy_goldens(cases, lambda case: 1)
    assert score.exact_accuracy == 1.0


def test_the_config_exposes_the_goldens_block():
    config = IngestConfig.load()
    assert config.golden_thresholds.false_accept_max == 0.02
    assert config.golden_thresholds.false_reject_max == 0.10
    # Decorrelated from the D24 verifier's own models (deepseek / deepseek-thinking /
    # mini) — see Section 6.4.
    assert config.golden_candidate_model not in ("deepseek", "deepseek-thinking", "mini")
    assert config.verifier_entry_point is None      # 2D sets it
