# tools/ingest/src/langatlas_ingest/store.py
import json
from dataclasses import dataclass
from typing import Sequence
from langatlas_ingest.errors import UnknownQueueEntry

_COLUMNS = ("chunk_id", "source_id", "ordinal", "parent_section_id", "section_path",
            "breadcrumb", "locator", "locator_kind", "page_start", "page_end",
            "section_number", "anchor", "line_start", "line_end", "text", "token_count",
            "content_hash")
_SELECT = ", ".join(_COLUMNS)


@dataclass
class SourceChunk:
    chunk_id: str
    source_id: str
    ordinal: int
    parent_section_id: str | None
    section_path: list[str]
    breadcrumb: str
    locator: str
    locator_kind: str
    page_start: int | None
    page_end: int | None
    section_number: str | None
    anchor: str | None
    line_start: int | None
    line_end: int | None
    text: str
    token_count: int
    content_hash: str = ""


def _row(values) -> SourceChunk:
    return SourceChunk(**dict(zip(_COLUMNS, values)))


class SourceChunksStore:
    """The one table D15 promised: written here, read by `search_sources` and — from
    Stage 2 — by the D24 verifier. Writes are whole-source replacements so a re-ingest
    can never leave orphaned chunks behind."""

    def __init__(self, conn):
        self.conn = conn

    def replace_source(self, source_id: str, chunks: Sequence) -> int:
        chunks = list(chunks)
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute("DELETE FROM source_chunks WHERE source_id = %s", (source_id,))
                cur.executemany(
                    f"INSERT INTO source_chunks ({_SELECT})"
                    f" VALUES ({', '.join(['%s'] * len(_COLUMNS))})",
                    [tuple(getattr(chunk, name) for name in _COLUMNS) for chunk in chunks])
        return len(chunks)

    def delete_source(self, source_id: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM source_chunks WHERE source_id = %s", (source_id,))
            return cur.rowcount

    def get(self, chunk_id: str) -> SourceChunk | None:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT {_SELECT} FROM source_chunks WHERE chunk_id = %s",
                        (chunk_id,))
            row = cur.fetchone()
        return _row(row) if row else None

    def by_source(self, source_id: str) -> list[SourceChunk]:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT {_SELECT} FROM source_chunks WHERE source_id = %s"
                        " ORDER BY ordinal", (source_id,))
            return [_row(row) for row in cur.fetchall()]

    def children_of(self, parent_section_id: str) -> list[SourceChunk]:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT {_SELECT} FROM source_chunks"
                        " WHERE parent_section_id = %s ORDER BY ordinal",
                        (parent_section_id,))
            return [_row(row) for row in cur.fetchall()]

    def unembedded(self, table: str, *, limit: int | None = None) -> list[SourceChunk]:
        query = (f"SELECT {', '.join('c.' + name for name in _COLUMNS)} FROM source_chunks c"
                 f" LEFT JOIN {table} e ON e.chunk_id = c.chunk_id"
                 " WHERE e.chunk_id IS NULL ORDER BY c.source_id, c.ordinal")
        if limit is not None:
            # `is not None`, not truthiness: `limit=0` is an honest "give me nothing"
            # (a caller draining a budget down to zero), not "give me the whole table".
            query += f" LIMIT {int(limit)}"
        with self.conn.cursor() as cur:
            cur.execute(query)
            return [_row(row) for row in cur.fetchall()]

    def record_ingestion(self, source_id: str, *, content_hash: str, backend: str,
                         backend_version: str, chunk_count: int, qa, promoted: bool) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO source_ingestions (source_id, content_hash, backend,"
                " backend_version, chunk_count, qa_status, qa_report, promoted)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (source_id) DO UPDATE SET content_hash = EXCLUDED.content_hash,"
                " backend = EXCLUDED.backend, backend_version = EXCLUDED.backend_version,"
                " chunk_count = EXCLUDED.chunk_count, qa_status = EXCLUDED.qa_status,"
                " qa_report = EXCLUDED.qa_report, promoted = EXCLUDED.promoted,"
                " ingested_at = now()",
                (source_id, content_hash, backend, backend_version, chunk_count,
                 qa.status, json.dumps(qa.to_dict()), promoted))


class SourcingQueue:
    """D37/D41's single private queue. Re-filing an already-open entry updates it in place
    rather than stacking duplicates — the queue is a state, not a log."""

    def __init__(self, conn):
        self.conn = conn

    def file(self, *, kind: str, source_id: str, reason: str, detail: str = "") -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT id FROM sourcing_queue WHERE kind = %s AND source_id = %s"
                        " AND resolved_at IS NULL", (kind, source_id))
            existing = cur.fetchone()
            if existing:
                cur.execute("UPDATE sourcing_queue SET reason = %s, detail = %s WHERE id = %s",
                            (reason, detail, existing[0]))
                return existing[0]
            cur.execute("INSERT INTO sourcing_queue (kind, source_id, reason, detail)"
                        " VALUES (%s, %s, %s, %s) RETURNING id",
                        (kind, source_id, reason, detail))
            return cur.fetchone()[0]

    def open_entries(self, *, kind: str | None = None) -> list[dict]:
        clause = " AND kind = %s" if kind else ""
        params = (kind,) if kind else ()
        names = ("id", "kind", "source_id", "reason", "detail", "bounce_count",
                 "opened_at", "age_days")
        with self.conn.cursor() as cur:
            cur.execute("SELECT id, kind, source_id, reason, detail, bounce_count,"
                        " opened_at, EXTRACT(day FROM now() - opened_at)::int"
                        " FROM sourcing_queue WHERE resolved_at IS NULL" + clause
                        + " ORDER BY opened_at", params)
            return [dict(zip(names, row)) for row in cur.fetchall()]

    def bounce(self, entry_id: int) -> int:
        with self.conn.cursor() as cur:
            cur.execute("UPDATE sourcing_queue SET bounce_count = bounce_count + 1"
                        " WHERE id = %s RETURNING bounce_count", (entry_id,))
            row = cur.fetchone()
        if row is None:
            # D24 spends a 2-bounce budget against this number, so a silent 0 for an id
            # that does not exist would read as "budget untouched" and loop forever.
            raise UnknownQueueEntry(entry_id)
        return row[0]

    def resolve(self, *, source_id: str, kind: str = "pending-source") -> int:
        with self.conn.cursor() as cur:
            cur.execute("UPDATE sourcing_queue SET resolved_at = now()"
                        " WHERE source_id = %s AND kind = %s AND resolved_at IS NULL",
                        (source_id, kind))
            return cur.rowcount
