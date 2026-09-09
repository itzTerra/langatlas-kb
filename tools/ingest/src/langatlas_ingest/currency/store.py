"""Persistence for §4.4's two standing checks, plus the `sourcing_queue` filing that is
their only externally visible consequence.

`SourcingQueue.file()` is idempotent per (kind, source_id, reason) for these non-
pending-source kinds — it updates an open entry in place rather than stacking duplicates
when the same reason is refiled. Both checks lean on that: a link that has been dead for
four months is one open entry with a refreshed detail line, not four. Distinct reasons on
the same source (an `anchor-missing` alongside a `content-drift`) stay as separate,
independently resolvable entries."""
from datetime import datetime

from langatlas_ingest.currency.links import LinkCheckResult
from langatlas_ingest.store import SourcingQueue


def previous_link_hash(conn, source_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT content_hash FROM source_link_checks WHERE source_id = %s",
                    (source_id,))
        row = cur.fetchone()
    return row[0] if row else None


def record_link_check(conn, result: LinkCheckResult) -> None:
    """Upsert this source's current link state.

    `content_hash` is written with COALESCE so a failed fetch (hash None) keeps the last
    known good hash: the baseline a future check compares against is the last body we
    actually saw, not "nothing". Without it, one outage would make the next successful
    fetch look like a first-ever check and silently swallow a real drift."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO source_link_checks (source_id, url, checked_at, resolves,"
            " http_status, anchor, anchor_present, content_hash, drifted)"
            " VALUES (%s, %s, now(), %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (source_id) DO UPDATE SET"
            "   url=excluded.url, checked_at=excluded.checked_at,"
            "   resolves=excluded.resolves, http_status=excluded.http_status,"
            "   anchor=excluded.anchor, anchor_present=excluded.anchor_present,"
            "   content_hash=COALESCE(excluded.content_hash,"
            "                         source_link_checks.content_hash),"
            "   drifted=excluded.drifted",
            (result.source_id, result.url, result.resolves, result.http_status,
             result.anchor, result.anchor_present, result.content_hash, result.drifted))


_DETAIL = {
    "link-dead": "live URL did not resolve on two attempts: {url} (status {status})",
    "anchor-missing": "anchor #{anchor} is no longer present at {url}",
    "content-drift": "page content changed since the last check: {url}",
}


def file_link_findings(queue: SourcingQueue, result: LinkCheckResult) -> list[str]:
    """One queue entry per finding. Returns the reasons filed, for the job's `detail`."""
    for reason in result.findings:
        queue.file(kind="link-checker", source_id=result.source_id, reason=reason,
                   detail=_DETAIL[reason].format(url=result.url, anchor=result.anchor,
                                                 status=result.http_status))
    return list(result.findings)


def last_edition_check(conn, source_id: str) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute("SELECT checked_at FROM source_edition_checks WHERE source_id = %s",
                    (source_id,))
        row = cur.fetchone()
    return row[0] if row else None


def record_edition_check(conn, result) -> None:
    """`result` is Task 5's `EditionCheckResult`; imported lazily-by-duck-typing rather
    than by name so this module does not import `editions.py` just for a type."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO source_edition_checks (source_id, checked_at, edition, matched,"
            " detail) VALUES (%s, now(), %s, %s, %s)"
            " ON CONFLICT (source_id) DO UPDATE SET checked_at=excluded.checked_at,"
            "   edition=excluded.edition, matched=excluded.matched,"
            "   detail=excluded.detail",
            (result.source_id, result.edition, result.matched, result.detail))
