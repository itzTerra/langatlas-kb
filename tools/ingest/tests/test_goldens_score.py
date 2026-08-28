import json
import pytest
from langatlas_ingest.goldens.items import Citation, Claim, ControversyCase, VerifierItem
from langatlas_ingest.goldens.score import (
    Thresholds, VerdictOutcome, score_controversy, score_verifier,
)

THRESHOLDS = Thresholds(false_accept_max=0.02, false_reject_max=0.10)


def item(item_id, stratum, verdict, **kw):
    return VerifierItem(id=item_id, stratum=stratum, expected_verdict=verdict,
                        claim=Claim(kind="instance-exists",
                                    text=f"instance-exists(i-{item_id}, status=present)",
                                    **kw.pop("claim_kwargs", {})),
                        citation=Citation(source="ctm", locator="p. 1"), **kw)


def test_a_perfect_run_scores_zero_error_rates():
    items = [item("a", "correct", "supported"),
             item("b", "category-error", "unsupported")]
    outcomes = {"a": VerdictOutcome("supported"), "b": VerdictOutcome("unsupported")}
    score = score_verifier(items, outcomes, thresholds=THRESHOLDS)
    assert score.false_accept_rate == 0.0 and score.false_reject_rate == 0.0
    assert score.exact_verdict_accuracy == 1.0 and score.thresholds_met is True


def test_a_wrong_claim_marked_supported_is_a_false_accept_not_a_false_reject():
    items = [item("a", "category-error", "unsupported")]
    score = score_verifier(items, {"a": VerdictOutcome("supported")},
                           thresholds=THRESHOLDS)
    assert score.false_accept_rate == 1.0
    assert score.false_reject_rate is None      # no should-admit items at all
    assert score.false_accepts == ["a"]
    assert score.thresholds_met is False


def test_partial_on_an_overstated_item_is_correct_and_supported_is_a_false_accept():
    # `partial` never admits, so the overstated stratum is exactly where K1 laundering
    # would show up as a false accept.
    items = [item("a", "overstated-claim", "partial"),
             item("b", "overstated-claim", "partial")]
    score = score_verifier(items, {"a": VerdictOutcome("partial"),
                                   "b": VerdictOutcome("supported")},
                           thresholds=THRESHOLDS)
    assert score.false_accept_rate == 0.5
    assert score.per_stratum["overstated-claim"].false_accepts == 1


def test_a_correct_item_rejected_is_a_false_reject():
    items = [item("a", "correct", "supported")]
    score = score_verifier(items, {"a": VerdictOutcome("unsupported")},
                           thresholds=THRESHOLDS)
    assert score.false_reject_rate == 1.0 and score.false_accept_rate is None
    assert score.false_rejects == ["a"]


def test_a_partial_where_supported_was_expected_is_a_false_reject_not_a_pass():
    items = [item("a", "correct", "supported")]
    score = score_verifier(items, {"a": VerdictOutcome("partial")}, thresholds=THRESHOLDS)
    assert score.false_reject_rate == 1.0


def test_annotations_are_scored_separately_from_verdicts():
    items = [item("a", "quote-found-elsewhere", "supported",
                  expected_annotations=("quote-found-elsewhere",))]
    score = score_verifier(items, {"a": VerdictOutcome("supported")},
                           thresholds=THRESHOLDS)
    assert score.exact_verdict_accuracy == 1.0
    assert score.annotation_accuracy == 0.0     # verdict right, annotation missed


def test_a_missing_outcome_is_an_error_not_a_silent_zero():
    with pytest.raises(ValueError, match="no outcome"):
        score_verifier([item("a", "correct", "supported")], {}, thresholds=THRESHOLDS)


def test_the_contamination_gauge_reports_the_obscure_versus_mainstream_gap():
    items = [item("a", "correct", "supported", contamination_gauge=True),
             item("b", "correct", "supported")]
    score = score_verifier(items, {"a": VerdictOutcome("unsupported"),
                                   "b": VerdictOutcome("supported")},
                           thresholds=THRESHOLDS)
    assert score.gauge.gauge_exact_rate == 0.0
    assert score.gauge.mainstream_exact_rate == 1.0
    assert score.gauge.gap == 1.0


def test_absent_items_get_their_own_false_accept_line():
    items = [item("a", "contradicted", "contradicted",
                  claim_kwargs={"status": "absent", "absence_scope": "C23",
                                "feature_aliases": ("pattern matching",)})]
    score = score_verifier(items, {"a": VerdictOutcome("supported")},
                           thresholds=THRESHOLDS)
    assert score.absent_items == 1 and score.absent_false_accept_rate == 1.0


def test_the_json_shape_is_machine_readable_for_the_d35_bundle():
    items = [item("a", "correct", "supported")]
    payload = json.loads(score_verifier(items, {"a": VerdictOutcome("supported")},
                                        thresholds=THRESHOLDS).to_json())
    assert payload["false_accept_rate"] is None or isinstance(
        payload["false_accept_rate"], float)
    for key in ("items", "false_reject_rate", "exact_verdict_accuracy", "thresholds",
                "thresholds_met", "per_stratum", "contamination_gauge"):
        assert key in payload


def test_controversy_scoring_reports_exact_and_adjacent_accuracy():
    cases = [ControversyCase(id="c1", expected_level=3, inputs={"verdicts": []}),
             ControversyCase(id="c2", expected_level=0, inputs={"verdicts": []})]
    score = score_controversy(cases, {"c1": 2, "c2": 0})
    assert score.exact_accuracy == 0.5 and score.within_one_accuracy == 1.0
    assert score.confusion[(3, 2)] == 1
    assert score.level3_recall == 0.0
