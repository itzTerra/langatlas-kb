import pytest

from langatlas_validate.cli import main
from langatlas_validate.tombstones import (
    TOMBSTONES_REL, ChainCycle, ChainTooDeep, check_append_only, derived_from, parse_tombstones,
    render_tombstones, resolve_fact, validate_tombstones,
)


def _entry(fact_id, successors=(), *, action="remap", reason="merge", migration_id="0001-x"):
    return {"fact_id": fact_id, "anchor": f"{fact_id}-anchor#summary", "action": action,
            "reason": reason, "superseded_by": list(successors),
            "migration_id": migration_id, "date": "2026-10-01"}


def test_render_and_parse_round_trip_in_schema_key_order():
    entries = [_entry("f-aaaaaaaaaaaa", ["f-bbbbbbbbbbbb"])]
    text = render_tombstones(entries)

    assert parse_tombstones(text) == entries
    assert text.index("fact_id") < text.index("superseded_by") < text.index("date")
    assert render_tombstones([]) == "tombstones: []\n"


def test_a_live_fact_resolves_to_itself():
    resolution = resolve_fact("f-aaaaaaaaaaaa", entries=[], live={"f-aaaaaaaaaaaa"})

    assert resolution.status == "live"
    assert resolution.successors == ("f-aaaaaaaaaaaa",)


def test_a_chain_resolves_to_its_live_terminals():
    entries = [_entry("f-000000000001", ["f-000000000002"]),
               _entry("f-000000000002", ["f-000000000003", "f-000000000004"])]

    resolution = resolve_fact("f-000000000001", entries=entries,
                              live={"f-000000000003", "f-000000000004"})

    assert resolution.status == "superseded"
    assert resolution.successors == ("f-000000000003", "f-000000000004")
    assert [entry["fact_id"] for entry in resolution.chain] == ["f-000000000001",
                                                                 "f-000000000002"]


def test_an_empty_successor_list_is_a_retirement_not_an_error():
    resolution = resolve_fact("f-000000000001",
                              entries=[_entry("f-000000000001", action="tombstone")], live=set())

    assert resolution.status == "retired"
    assert resolution.successors == ()


def test_an_unknown_id_is_unknown():
    assert resolve_fact("f-000000000009", entries=[], live=set()).status == "unknown"


def test_a_chain_longer_than_the_cap_fails_loudly():
    ids = [f"f-{index:012d}" for index in range(7)]
    entries = [_entry(ids[index], [ids[index + 1]]) for index in range(6)]

    resolve_fact(ids[1], entries=entries, live={ids[6]})         # five hops: fine
    with pytest.raises(ChainTooDeep):
        resolve_fact(ids[0], entries=entries, live={ids[6]})     # six hops: a data bug


def test_a_diamond_is_walked_once_per_node():
    entries = [_entry("f-000000000001", ["f-000000000002", "f-000000000003"]),
               _entry("f-000000000002", ["f-000000000004"]),
               _entry("f-000000000003", ["f-000000000004"])]

    resolution = resolve_fact("f-000000000001", entries=entries, live={"f-000000000004"})

    assert resolution.successors == ("f-000000000004",)


def test_derived_from_is_the_inverse_of_superseded_by():
    entries = [_entry("f-000000000001", ["f-000000000003"]),
               _entry("f-000000000002", ["f-000000000003"])]

    assert derived_from("f-000000000003", entries) == ("f-000000000001", "f-000000000002")
    assert derived_from("f-000000000001", entries) == ()


def test_validation_catches_schema_duplicates_and_dangling_successors():
    entries = [_entry("f-000000000001", ["f-000000000002"]),
               _entry("f-000000000001", ["f-000000000002"]),
               {**_entry("f-000000000003"), "action": "vanish"}]

    errors = validate_tombstones(entries, live=set())

    assert any("duplicate" in error for error in errors)
    assert any("f-000000000002" in error and "neither" in error for error in errors)
    assert any("vanish" in error for error in errors)


def test_the_ledger_is_append_only_except_for_a_resurrecting_revert():
    before = [_entry("f-000000000001", ["f-000000000002"])]

    assert check_append_only(before, [*before, _entry("f-000000000005")], live_after=set()) == []
    edited = [{**before[0], "superseded_by": []}]
    assert any("edited" in e for e in check_append_only(before, edited, live_after=set()))
    assert any("removed" in e for e in check_append_only(before, [], live_after=set()))
    # `git revert` of the migration brings the old fact back and drops its line: legal.
    assert check_append_only(before, [], live_after={"f-000000000001"}) == []


def test_ledger_check_fails_on_a_removed_line_and_skips_without_a_base(store_git, capsys):
    store, repo = store_git
    store.feature("alpha")
    line = render_tombstones([_entry("f-000000000001", action="tombstone")])
    base = repo.commit({TOMBSTONES_REL: line})
    repo.commit({TOMBSTONES_REL: "tombstones: []\n"})

    assert main(["ledger-check", "--since", base, "--repo-root", str(store.root)]) == 1
    assert "removed" in capsys.readouterr().out
    assert main(["ledger-check", "--since", "0" * 40, "--repo-root", str(store.root)]) == 0


def test_a_truncated_ledger_is_an_error_string_not_a_traceback(store_git, capsys):
    from langatlas_validate.store import validate_store

    store, repo = store_git
    store.feature("alpha")
    base = repo.commit({TOMBSTONES_REL: "tombstones: []\n"})
    repo.commit({TOMBSTONES_REL: "tombstones:\n  - fact_id: [f-00000\n"})

    assert any(e.startswith("tombstones.yaml:") and "unparseable" in e
               for e in validate_store(store.root))
    assert main(["ledger-check", "--since", base, "--repo-root", str(store.root)]) == 1
    assert "tombstones.yaml" in capsys.readouterr().out


def test_resolve_prints_the_chain(mini_store, capsys):
    from langatlas_validate.compile import derive_facts
    from langatlas_validate.store import iter_store_records

    mini_store.feature("alpha")
    live = derive_facts(list(iter_store_records(mini_store.root)))[0]["fact_id"]
    mini_store.write(TOMBSTONES_REL, render_tombstones([_entry("f-000000000001", [live])]))

    assert main(["resolve", "f-000000000001", "--repo-root", str(mini_store.root)]) == 0
    assert f"-> {live}" in capsys.readouterr().out


def test_malformed_entries_yield_errors_not_tracebacks():
    no_id = {k: v for k, v in _entry("f-000000000001").items() if k != "fact_id"}
    no_succ = {k: v for k, v in _entry("f-000000000002").items() if k != "superseded_by"}

    errors = validate_tombstones([no_id, no_succ, "junk"], live=set())

    assert any("fact_id" in e for e in errors)
    assert any("superseded_by" in e for e in errors)
    assert any("not a mapping" in e for e in errors)
    assert check_append_only([no_id, "junk"], [no_succ, 5], live_after=set()) == []


def test_a_cycle_is_a_loud_error_but_a_diamond_and_a_retirement_are_not():
    cycle = [_entry("f-000000000001", ["f-000000000002"]),
             _entry("f-000000000002", ["f-000000000001"])]

    with pytest.raises(ChainCycle):
        resolve_fact("f-000000000001", entries=cycle, live=set())
    assert any("loops" in e for e in validate_tombstones(cycle, live=set()))
    assert resolve_fact("f-000000000001", entries=[_entry("f-000000000001")],
                        live=set()).status == "retired"


def test_resolve_exits_non_zero_on_a_cycle(mini_store, capsys):
    mini_store.write(TOMBSTONES_REL, render_tombstones([
        _entry("f-000000000001", ["f-000000000002"]),
        _entry("f-000000000002", ["f-000000000001"])]))

    assert main(["resolve", "f-000000000001", "--repo-root", str(mini_store.root)]) == 1
    assert "loops" in capsys.readouterr().out
