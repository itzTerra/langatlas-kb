import pytest

from langatlas_ingest.currency.links import LinkCheckResult
from langatlas_ingest.currency.store import (
    file_link_findings, previous_link_hash, record_link_check,
)
from langatlas_ingest.db import migrate
from langatlas_ingest.store import SourcingQueue

pytestmark = pytest.mark.db


def test_migration_widens_the_queue_reason_vocabulary(db_conn):
    """D37 put `link-checker`/`edition-check` in the *kind* CHECK and left `reason`
    listing only the five pending-source reasons, so a link-checker finding had no
    legal reason string at all."""
    migrate(db_conn)
    queue = SourcingQueue(db_conn)
    for reason in ("link-dead", "anchor-missing", "content-drift"):
        queue.file(kind="link-checker", source_id=f"s-{reason}", reason=reason)
    for reason in ("edition-mismatch", "edition-superseded"):
        queue.file(kind="edition-check", source_id=f"s-{reason}", reason=reason)
    assert len(queue.open_entries(kind="link-checker")) == 3
    assert len(queue.open_entries(kind="edition-check")) == 2


def test_pending_source_reasons_still_apply(db_conn):
    migrate(db_conn)
    queue = SourcingQueue(db_conn)
    queue.file(kind="pending-source", source_id="s1", reason="paywalled")
    assert queue.open_entries(kind="pending-source")[0]["reason"] == "paywalled"


def test_an_invented_reason_is_still_rejected(db_conn):
    """Widening the constraint must not turn it into a free-text column: the queue's
    reason is read by report code and by the D24 bounce budget."""
    import psycopg

    migrate(db_conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        SourcingQueue(db_conn).file(kind="link-checker", source_id="s2",
                                    reason="vibes")


def test_currency_tables_exist(db_conn):
    migrate(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('source_link_checks'),"
                    " to_regclass('source_edition_checks')")
        assert cur.fetchone() == ("source_link_checks", "source_edition_checks")


def _result(**overrides) -> LinkCheckResult:
    base = dict(source_id="s1", url="https://example.test/ref", resolves=True,
                http_status=200, anchor=None, anchor_present=None,
                content_hash="hash-1", drifted=False, findings=())
    return LinkCheckResult(**{**base, **overrides})


def test_recording_a_check_makes_its_hash_the_next_run_s_baseline(db_conn):
    migrate(db_conn)
    assert previous_link_hash(db_conn, "s1") is None
    record_link_check(db_conn, _result())
    assert previous_link_hash(db_conn, "s1") == "hash-1"


def test_a_second_check_replaces_the_first(db_conn):
    """One row per source: this table is a state, not a history (see db/0006)."""
    migrate(db_conn)
    record_link_check(db_conn, _result())
    record_link_check(db_conn, _result(content_hash="hash-2", drifted=True))
    assert previous_link_hash(db_conn, "s1") == "hash-2"
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM source_link_checks")
        assert cur.fetchone()[0] == 1


def test_a_failed_fetch_never_clears_the_stored_baseline(db_conn):
    """A dead link must not erase the hash a later resurrection would be compared
    against — that would silently convert one outage into 'no drift, ever again'."""
    migrate(db_conn)
    record_link_check(db_conn, _result())
    record_link_check(db_conn, _result(resolves=False, http_status=503,
                                       content_hash=None, findings=("link-dead",)))
    assert previous_link_hash(db_conn, "s1") == "hash-1"


def test_every_finding_files_its_own_queue_entry(db_conn):
    migrate(db_conn)
    queue = SourcingQueue(db_conn)
    filed = file_link_findings(queue, _result(anchor="gone", anchor_present=False,
                                              drifted=True,
                                              findings=("anchor-missing",
                                                        "content-drift")))
    assert filed == ["anchor-missing", "content-drift"]
    reasons = {entry["reason"] for entry in queue.open_entries(kind="link-checker")}
    assert reasons == {"anchor-missing", "content-drift"}


def test_a_clean_check_files_nothing(db_conn):
    migrate(db_conn)
    queue = SourcingQueue(db_conn)
    assert file_link_findings(queue, _result()) == []
    assert queue.open_entries(kind="link-checker") == []
