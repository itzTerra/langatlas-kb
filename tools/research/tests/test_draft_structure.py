import pytest

from langatlas_research.draft.contested import contested_triggers, drop, open_carves
from langatlas_research.draft.finalize import r4_blockers
from langatlas_research.draft.gate import _ready
from langatlas_research.draft.minting import _mintable
from langatlas_research.draft.structure import (
    BLOCKED, Misfit, block_entries, is_blocked, synthesize_friction,
)


def test_block_entries_marks_only_the_misfit_keys_and_joins_reasons():
    entries = [{"key": "a"}, {"key": "b"}]
    blocked = block_entries(entries, [Misfit("b", "realizes", "r1"),
                                      Misfit("b", "layers", "r2")])
    assert blocked[0] == {"key": "a"}
    assert blocked[1] == {"key": "b", "blocked": BLOCKED, "block_reason": "r1; r2"}
    assert is_blocked(blocked[1]) and not is_blocked(blocked[0])


def test_a_misfit_the_model_already_reported_is_not_reported_twice():
    reported = [{"kind": "structure-friction", "detail": "d", "keys": ["b"],
                 "area": "ontology", "element": "realizes"}]
    assert synthesize_friction([Misfit("b", "realizes", "r")], reported) == []


def test_an_unreported_misfit_becomes_one_finding_per_key_and_element():
    found = synthesize_friction([Misfit("b", "realizes", "r1"),
                                 Misfit("b", "realizes", "r1"),
                                 Misfit("b", "layers", "r2")], [])
    assert [(f["keys"], f["element"], f["detail"]) for f in found] == [
        (["b"], "realizes", "r1"), (["b"], "layers", "r2")]
    assert all(f["kind"] == "structure-friction" and f["area"] == "ontology" for f in found)


def _entry(**over):
    return {"key": "child", "from_candidates": ["child"], "kind": "feature", "id": "child",
            "name": "Child", "summary": "s", "layer": 2, "dimension": None,
            "evidence": [{"source": "a", "locator": "§1"}],
            "contested": [], "debate_id": None, "status": "proposed",
            "verification": None, "note": "", **over}


BLOCKED_ENTRY = {"blocked": "structure", "block_reason": "realizes a feature"}


class _Store:
    nodes = frozenset()


def test_a_blocked_carve_is_never_contested_so_never_debated():
    plan = {"dimensions": [], "qualities": [], "edges": [], "quality_edges": [],
            "nodes": [_entry(**BLOCKED_ENTRY, contested=["ontologist-flagged"])]}
    assert contested_triggers(plan, store=_Store()) == {}
    assert open_carves(plan) == []


def test_a_blocked_carve_is_not_ready_for_the_gate_and_never_mints():
    assert _ready(_entry()) is True
    assert _ready(_entry(**BLOCKED_ENTRY)) is False
    assert _mintable("nodes", _entry(**BLOCKED_ENTRY, status="verified")) is False
    layerless = {k: v for k, v in _entry(**BLOCKED_ENTRY, status="verified").items()
                 if k != "layer"}
    assert _mintable("nodes", layerless) is False


def test_a_blocked_carve_blocks_the_mint_mode_finalize(research_repo, signed_cycle):
    from langatlas_research.draft.plan import build_plan_record

    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="r", generated_at="t")
    plan["nodes"] = [_entry(**BLOCKED_ENTRY)]
    assert any("blocked" in b and "structure review" in b
               for b in r4_blockers(signed_cycle, plan, repo_root=research_repo))


def test_drop_marks_a_carve_dropped_with_the_reason():
    plan = {"dimensions": [], "qualities": [], "edges": [], "quality_edges": [],
            "nodes": [_entry(**BLOCKED_ENTRY)]}
    dropped = drop(plan, "child", "the revised structure still has no slot for it")
    assert dropped["nodes"][0]["status"] == "dropped"
    assert dropped["nodes"][0]["drop_reason"].startswith("the revised structure")


def test_drop_refuses_a_minted_carve_and_a_blank_reason():
    plan = {"dimensions": [], "qualities": [], "edges": [], "quality_edges": [],
            "nodes": [_entry(status="minted")]}
    with pytest.raises(ValueError, match="minted"):
        drop(plan, "child", "why")
    plan["nodes"][0]["status"] = "proposed"
    with pytest.raises(ValueError, match="reason"):
        drop(plan, "child", "  ")
