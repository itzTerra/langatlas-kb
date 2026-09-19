from dataclasses import replace

import pytest

from langatlas_research.consolidate.lifecycle import open_r6
from langatlas_research.consolidate.record import (
    add_migration, add_ruling, build_record, consolidation_path, iter_records, load_record,
    save_record,
)
from langatlas_research.cycle import (
    load_cycle, save_cycle, settle_cycle, settled_record_ids, settled_themes_by_record,
)
from langatlas_research.errors import (
    ConsolidationInvalid, ConsolidationMissing, InvalidTransition, R6NotReady,
)


@pytest.fixture
def r5_cycle(research_repo, signed_cycle):
    cycle = replace(signed_cycle, status="r5-done",
                    nodes_minted=("static-typing", "edge.requires.static-typing.type-inference"))
    save_cycle(cycle, repo_root=research_repo)
    return cycle


def _ruling(key, reason="x"):
    return {"key": key, "nodes": ["a", "b"], "signals": ["same-name"],
            "disposition": "distinct", "reason": reason}


def test_a_record_round_trips_and_its_schema_is_enforced(research_repo, r5_cycle):
    record = build_record(cycle=r5_cycle, opened_at="2026-10-01T10:00:00Z")
    save_record(record, repo_root=research_repo)

    assert load_record(r5_cycle.slug, repo_root=research_repo) == record
    assert iter_records(research_repo) == [record]
    with pytest.raises(ConsolidationInvalid):
        save_record({**record, "dedup": [{"key": "nope"}]}, repo_root=research_repo)
    with pytest.raises(ConsolidationInvalid):
        save_record({**record, "dedup": [{**_ruling("d-000000000001"),
                                          "disposition": "merge"}]}, repo_root=research_repo)


def test_a_missing_record_names_the_command_that_creates_it(research_repo):
    with pytest.raises(ConsolidationMissing, match="consolidate open 1"):
        load_record("01-typing", repo_root=research_repo)


def test_a_malformed_record_file_is_a_typed_error(research_repo, r5_cycle):
    path = consolidation_path(r5_cycle.slug, research_repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    for text in ("key: [unclosed", "- just\n- a list\n"):
        path.write_text(text)
        with pytest.raises(ConsolidationInvalid):
            load_record(r5_cycle.slug, repo_root=research_repo)


def test_migrations_and_rulings_are_deduplicated_and_sorted(r5_cycle):
    record = build_record(cycle=r5_cycle, opened_at="t")
    record = add_migration(add_migration(add_migration(record, "0002-b"), "0001-a"), "0002-b")
    record = add_ruling(add_ruling(add_ruling(record, _ruling("d-000000000002")),
                                   _ruling("d-000000000001")),
                        _ruling("d-000000000002", reason="y"))

    assert record["migrations"] == ["0001-a", "0002-b"]
    assert [(e["key"], e["reason"]) for e in record["dedup"]] == [
        ("d-000000000001", "x"), ("d-000000000002", "y")]


def test_settling_needs_r5_and_records_who_and_when(signed_cycle, r5_cycle):
    with pytest.raises(InvalidTransition):
        settle_cycle(signed_cycle, by="Dev", date="2026-10-02")

    settled = settle_cycle(r5_cycle, by="Dev", date="2026-10-02")

    assert (settled.status, settled.settled) == ("settled", {"by": "Dev", "date": "2026-10-02"})


def test_settled_record_ids_come_only_from_settled_cycles(research_repo, r5_cycle):
    assert settled_record_ids(research_repo) == {}

    save_cycle(settle_cycle(r5_cycle, by="Dev", date="2026-10-02"), repo_root=research_repo)

    assert settled_record_ids(research_repo) == {
        "static-typing": "typing", "edge.requires.static-typing.type-inference": "typing"}
    assert load_cycle(1, repo_root=research_repo).settled == {"by": "Dev", "date": "2026-10-02"}
    assert settled_themes_by_record(
        [{"status": "r5-done", "theme": "x", "nodes_minted": ["a"]}]) == {}


def test_r6_opens_only_on_an_r5_done_cycle_and_is_idempotent(research_repo, signed_cycle):
    with pytest.raises(R6NotReady, match="r5-done"):
        open_r6(1, repo_root=research_repo, opened_at="t1")

    save_cycle(replace(signed_cycle, status="r5-done"), repo_root=research_repo)
    _cycle, record = open_r6(1, repo_root=research_repo, opened_at="t1")
    _cycle, again = open_r6(1, repo_root=research_repo, opened_at="t2")

    assert again == record and record["opened_at"] == "t1"
    assert consolidation_path("01-typing", research_repo).exists()


def test_the_cli_reports_an_unknown_cycle_without_a_traceback(research_repo, capsys):
    from langatlas_research.cli import main

    assert main(["--repo-root", str(research_repo), "consolidate", "open", "9"]) == 1
    assert "error:" in capsys.readouterr().err
