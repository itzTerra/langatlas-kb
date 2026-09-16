"""The committed debate golden set, scored against the deterministic layer 3D reads."""
import pytest

from langatlas_research.draft.debate_record import (
    as_controversy_input, debate_signals, load_debate_goldens, resolution_outcome, rounds,
)
from langatlas_research.paths import REPO_ROOT
from langatlas_research.schema import validate_research_record

CASES = load_debate_goldens()


def test_the_set_is_not_empty_and_covers_every_outcome():
    outcomes = {case["expect"]["outcome"] for case in CASES}
    assert outcomes == {"resolved", "converged-after-revision", "escalated"}


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_every_golden_record_satisfies_the_debate_schema(case):
    assert validate_research_record(case["debate"], "debate", repo_root=REPO_ROOT) == []


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_the_outcome_is_what_the_disposition_maps_to(case):
    debate = case["debate"]
    assert resolution_outcome(debate["resolution"]["disposition"]) == case["expect"]["outcome"]
    assert debate["resolution"]["outcome"] == case["expect"]["outcome"]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_the_round_count_is_derived_from_the_messages(case):
    assert rounds(case["debate"]) == case["expect"]["rounds"]
    assert case["debate"]["resolution"]["rounds"] == case["expect"]["rounds"]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_the_controversy_projection_and_signals_match(case):
    assert as_controversy_input(case["debate"]) == case["expect"]["controversy_input"]
    assert debate_signals(case["debate"]) == case["expect"]["signals"]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_no_golden_case_smuggles_a_forbidden_controversy_input(case):
    """§6.4: the assessor sees structured inputs only. The projection is the whole
    contract, so it must never grow a field 2B's bootstrap cases do not have."""
    assert set(as_controversy_input(case["debate"])) == {"id", "outcome", "standing_dissent",
                                                          "rounds"}
