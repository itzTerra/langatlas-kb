"""§6.4's structured-input allow-list and the closed signal grammar, with no model in sight."""
import pytest

from langatlas_research.controversy.inputs import (
    ControversyInputs, derivable_signals, inputs_digest,
)
from langatlas_research.errors import ControversyInputRefused

DEBATE = {"id": "d-01-typing-003", "outcome": "escalated", "standing_dissent": True, "rounds": 4}
CTR = {"id": "ctr-0123456789ab", "type": "verification", "status": "open", "participants": 2}
VERDICT = {"fact": "f-000000000115", "citation": 1, "verdict": "contradicted",
           "field": "base", "tier": "A"}


def test_from_mapping_accepts_exactly_the_five_permitted_keys():
    inputs = ControversyInputs.from_mapping(
        {"debates": [DEBATE], "contradiction_records": [CTR], "verdicts": [VERDICT],
         "source_strength": {"tier_a": 2, "tier_b": 0, "independent_corroborations": 1},
         "assessment_spread": {}})
    assert inputs.debates == (DEBATE,)
    assert inputs.as_dict()["source_strength"]["tier_a"] == 2


def test_from_mapping_refuses_a_human_challenge_derived_input():
    with pytest.raises(ControversyInputRefused, match="closure_attempt"):
        ControversyInputs.from_mapping({"verdicts": [], "closure_attempt": {"outcome": "confirmed-open"}})


def test_from_mapping_refuses_an_unknown_input():
    with pytest.raises(ControversyInputRefused, match="source_text"):
        ControversyInputs.from_mapping({"source_text": "..."})


def test_derivable_signals_is_exactly_what_the_inputs_can_justify():
    inputs = ControversyInputs.from_mapping(
        {"debates": [DEBATE], "contradiction_records": [CTR], "verdicts": [VERDICT],
         "assessment_spread": {"quality_edge_strength": ["strong", "weak"]}})
    assert derivable_signals(inputs) == {
        "debate:d-01-typing-003:standing-dissent",
        "contradiction:ctr-0123456789ab:open",
        "verdict:contradicted:base",
        "assessment-spread:quality_edge_strength",
    }


def test_a_debate_without_standing_dissent_signals_its_outcome():
    inputs = ControversyInputs.from_mapping(
        {"debates": [{"id": "d-01-typing-004", "outcome": "converged-after-revision",
                      "standing_dissent": False, "rounds": 2}]})
    assert derivable_signals(inputs) == {"debate:d-01-typing-004:converged-after-revision"}


def test_supported_verdicts_are_not_signals():
    """A signal is a *disagreement* reference. A clean support justifies nothing — it is the
    absence of signals that makes a fact level 0."""
    inputs = ControversyInputs.from_mapping(
        {"verdicts": [{"fact": "f-1", "citation": 1, "verdict": "supported",
                       "field": "base", "tier": "A"}]})
    assert derivable_signals(inputs) == set()


def test_digest_is_stable_across_key_order_and_changes_with_content():
    a = ControversyInputs.from_mapping({"verdicts": [VERDICT], "debates": [DEBATE]})
    b = ControversyInputs.from_mapping({"debates": [DEBATE], "verdicts": [VERDICT]})
    c = ControversyInputs.from_mapping({"debates": [DEBATE]})
    assert inputs_digest(a) == inputs_digest(b)
    assert inputs_digest(a) != inputs_digest(c)
    assert len(inputs_digest(a)) == 16
