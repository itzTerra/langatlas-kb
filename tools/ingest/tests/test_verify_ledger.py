import pytest
from langatlas_ingest.verify.ledger import VerdictLedger
from langatlas_ingest.verify.verdicts import Assertion, PairVerdict


def verdict(**kw):
    base = dict(fact_id="f-000000000001", source_id="scott-plp", locator="p. 12",
                verdict="supported", model="deepseek-v4", prompt_version="v-abc12345",
                run_id="2026-09-06-verify-batch-01", anchor="2026-09-06-verify-batch-01#msg-3",
                date="2026-09-06", evidence_chunk_ids=("scott-plp#c00412",))
    base.update(kw)
    return PairVerdict(**base)


@pytest.fixture
def ledger(tmp_path):
    with VerdictLedger(tmp_path / "verdicts.sqlite") as store:
        yield store


def test_a_recorded_verdict_round_trips(ledger):
    original = verdict(per_assertion=(Assertion("presence", "p", "supported", "span"),),
                       annotations=("quote-found-elsewhere",), since_status="since-supported")
    ledger.record(original)
    got = ledger.all_for("f-000000000001")
    assert len(got) == 1
    assert got[0] == original


def test_a_rerun_of_the_same_pair_supersedes_rather_than_duplicates(ledger):
    ledger.record(verdict(run_id="run-1", verdict="partial"))
    ledger.record(verdict(run_id="run-2", verdict="supported"))
    latest = ledger.latest_for("f-000000000001")
    assert len(latest) == 1
    assert latest[0].verdict == "supported"
    # Both rows are retained: a verdict history is the audit trail for a calibration
    # change, and dropping the older row would make a regression invisible.
    assert len(ledger.all_for("f-000000000001")) == 2


def test_distinct_citations_of_one_fact_are_separate_rows(ledger):
    ledger.record(verdict(source_id="a", locator="p. 1"))
    ledger.record(verdict(source_id="b", locator="p. 2"))
    assert len(ledger.latest_for("f-000000000001")) == 2


def test_recording_the_identical_row_twice_is_idempotent(ledger):
    ledger.record(verdict())
    ledger.record(verdict())
    assert len(ledger.all_for("f-000000000001")) == 1


def test_latest_for_prefers_recorded_at_over_insertion_order(ledger):
    # `recorded_at` is stamped by SQLite's own clock at insert time, so a test can't
    # control it through the public `record()` API. To pin a genuine backfill scenario
    # (an older run's results inserted *after* a newer run was already recorded), rewrite
    # the later-inserted row's `recorded_at` directly to a timestamp before the
    # earlier-inserted row's — mirroring what a real backfill's stamped time would be.
    ledger.record(verdict(run_id="run-1", verdict="partial"))
    ledger.record(verdict(run_id="run-2", verdict="supported"))
    ledger.conn.execute(
        "UPDATE verdicts SET recorded_at = '2000-01-01T00:00:00' WHERE run_id = 'run-2'")
    ledger.conn.commit()
    latest = ledger.latest_for("f-000000000001")
    assert len(latest) == 1
    # run-2 has the higher rowid but the earlier recorded_at, so run-1 (recorded later)
    # is genuinely the latest verdict and must win.
    assert latest[0].verdict == "partial"


def test_verdicts_can_be_listed_by_run(ledger):
    ledger.record(verdict(run_id="run-1"))
    ledger.record(verdict(source_id="b", run_id="run-1"))
    ledger.record(verdict(source_id="c", run_id="run-2"))
    assert len(ledger.verdicts_in_run("run-1")) == 2


def test_an_unknown_fact_has_no_verdicts(ledger):
    assert ledger.latest_for("f-nope") == []


def test_the_ledger_lives_in_the_private_tier_by_default():
    from langatlas_ingest.paths import VERDICT_LEDGER_PATH
    from langatlas_pipeline.paths import PRIVATE_DIR
    # D23: verdicts are build-side and are never written into authored YAML.
    assert VERDICT_LEDGER_PATH.parent == PRIVATE_DIR
