import pytest

from langatlas_research.draft.contested import (
    TRIGGERS, contested_triggers, mark_contested, open_carves, waive,
)
from langatlas_research.draft.ontologist import StoreView
from langatlas_research.draft.plan import build_plan_record, find_entry

EMPTY_STORE = StoreView(concepts=frozenset(), features=frozenset(),
                        dimensions=frozenset())


def _plan(cycle, **over):
    plan = build_plan_record(cycle=cycle, ontologist_run_id="r", generated_at="t")
    return {**plan, **over}


def _node(key, **over):
    return {"key": key, "from_candidates": [key], "kind": "feature", "id": key,
            "name": key, "summary": "s", "layer": 2, "dimension": None,
            "cross_cutting": False, "aliases": [], "realizes": [],
            "evidence": [{"source": "a", "locator": "§1"},
                         {"source": "b", "locator": "§2"}],
            "contested": [], "debate_id": None, "status": "proposed",
            "verification": None, "note": "", **over}


def test_the_trigger_vocabulary_is_closed():
    assert TRIGGERS == ("merged-candidates", "split-candidate", "new-dimension",
                        "new-quality", "single-source", "id-collision",
                        "ontologist-flagged")


def test_an_uncontested_carve_has_no_triggers(signed_cycle):
    plan = _plan(signed_cycle, nodes=[_node("static-typing")])
    assert contested_triggers(plan, store=EMPTY_STORE) == {}


def test_merging_two_candidates_is_contested(signed_cycle):
    plan = _plan(signed_cycle,
                 nodes=[_node("typing", from_candidates=["static-typing", "type-checking"])])
    assert contested_triggers(plan, store=EMPTY_STORE)["typing"] == ("merged-candidates",)


def test_splitting_one_candidate_across_two_carves_contests_both(signed_cycle):
    plan = _plan(signed_cycle, nodes=[_node("a", from_candidates=["polymorphism"]),
                                      _node("b", from_candidates=["polymorphism"])])
    triggers = contested_triggers(plan, store=EMPTY_STORE)
    assert triggers["a"] == ("split-candidate",) and triggers["b"] == ("split-candidate",)


def test_a_node_leaning_on_a_dimension_this_plan_invents_is_contested(signed_cycle):
    plan = _plan(signed_cycle,
                 dimensions=[{"key": "d", "slug": "d", "label": "D", "values": ["x", "y"],
                              "exclusivity": "exclusive", "applies_to": ["general-purpose"],
                              "contested": [], "debate_id": None, "status": "proposed",
                              "verification": None, "note": ""}],
                 nodes=[_node("n", layer=3, dimension="d")])
    triggers = contested_triggers(plan, store=EMPTY_STORE)
    assert "new-dimension" in triggers["n"] and "new-dimension" in triggers["d"]


def test_a_single_source_carve_is_contested(signed_cycle):
    plan = _plan(signed_cycle, nodes=[_node("n", evidence=[{"source": "a", "locator": "§1"},
                                                           {"source": "a", "locator": "§9"}])])
    assert contested_triggers(plan, store=EMPTY_STORE)["n"] == ("single-source",)


def test_an_id_that_collides_with_a_committed_node_is_contested(signed_cycle):
    store = StoreView(concepts=frozenset({"static-typing"}), features=frozenset(),
                      dimensions=frozenset())
    plan = _plan(signed_cycle, nodes=[_node("static-typing")])
    assert "id-collision" in contested_triggers(plan, store=store)["static-typing"]


def test_the_ontologists_own_flag_survives_recomputation(signed_cycle):
    plan = _plan(signed_cycle, nodes=[_node("n", contested=["ontologist-flagged"])])
    assert contested_triggers(plan, store=EMPTY_STORE)["n"] == ("ontologist-flagged",)


def test_triggers_are_sorted_into_vocabulary_order(signed_cycle):
    plan = _plan(signed_cycle,
                 nodes=[_node("n", from_candidates=["a", "b"],
                              evidence=[{"source": "a", "locator": "§1"}],
                              contested=["ontologist-flagged"])])
    assert contested_triggers(plan, store=EMPTY_STORE)["n"] == (
        "merged-candidates", "single-source", "ontologist-flagged")


def test_mark_contested_writes_the_triggers_onto_the_entries(signed_cycle):
    plan = mark_contested(_plan(signed_cycle, nodes=[_node("n", from_candidates=["a", "b"])]),
                          store=EMPTY_STORE)
    assert find_entry(plan, "n")[1]["contested"] == ["merged-candidates"]


def test_a_minted_carve_keeps_its_triggers_and_never_reopens(signed_cycle):
    """The store now holds what this plan minted, so `id-collision` would fire on every
    minted node — and the edge drafter re-marks the whole plan after the first mint."""
    store = StoreView(concepts=frozenset(), features=frozenset({"static-typing"}),
                      dimensions=frozenset())
    plan = _plan(signed_cycle, nodes=[_node("static-typing", status="minted",
                                            contested=["merged-candidates"],
                                            debate_id="d-01-typing-001")])
    assert contested_triggers(plan, store=store) == {}

    marked = mark_contested(plan, store=store)
    entry = find_entry(marked, "static-typing")[1]
    assert entry["contested"] == ["merged-candidates"]
    assert entry["status"] == "minted"
    assert open_carves(marked) == []


def test_a_minted_carve_with_no_debate_is_not_an_open_carve(signed_cycle):
    store = StoreView(concepts=frozenset(), features=frozenset({"static-typing"}),
                      dimensions=frozenset())
    plan = _plan(signed_cycle, nodes=[_node("static-typing", status="minted")])
    assert open_carves(mark_contested(plan, store=store)) == []


def test_open_carves_lists_only_undebated_unwaived_contested_entries(signed_cycle):
    plan = _plan(signed_cycle, nodes=[
        _node("a", contested=["merged-candidates"]),
        _node("b", contested=["merged-candidates"], debate_id="d-01-typing-001"),
        _node("c", contested=["merged-candidates"], status="waived", waiver="developer call"),
        _node("d")])
    assert open_carves(plan) == ["a"]


def test_waiving_records_the_reason_and_closes_the_carve(signed_cycle):
    plan = _plan(signed_cycle, nodes=[_node("a", contested=["single-source"])])
    waived = waive(plan, "a", "Pierce is the only book that defines it; that is fine")
    assert find_entry(waived, "a")[1]["status"] == "waived"
    assert "Pierce" in find_entry(waived, "a")[1]["waiver"]
    assert open_carves(waived) == []


def test_waiving_an_uncontested_carve_is_refused(signed_cycle):
    plan = _plan(signed_cycle, nodes=[_node("a")])
    with pytest.raises(ValueError):
        waive(plan, "a", "no reason to")
