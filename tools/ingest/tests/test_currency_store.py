import pytest

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
