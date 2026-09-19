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
