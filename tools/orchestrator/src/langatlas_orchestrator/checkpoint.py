import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orchestrator_checkpoint (
    spec_kind         TEXT NOT NULL,
    item_key          TEXT NOT NULL,
    run_id            TEXT NOT NULL,
    status            TEXT NOT NULL,
    record_key        TEXT,
    detail            TEXT NOT NULL DEFAULT '',
    last_pause_reason TEXT,
    attempted_at      TEXT NOT NULL,
    PRIMARY KEY (spec_kind, item_key)
)
"""


@dataclass(frozen=True)
class CheckpointRow:
    run_id: str
    spec_kind: str
    item_key: str
    status: str
    record_key: str | None
    detail: str
    last_pause_reason: str | None
    attempted_at: str


_COLUMNS = ("run_id", "spec_kind", "item_key", "status", "record_key", "detail",
           "last_pause_reason", "attempted_at")


class CheckpointStore:
    """D43 §2.2: driver-level bookkeeping only, in the same private, non-git tier as
    D26's cache/cost log. Never the source of truth for whether an item actually
    landed — `driver.py` re-verifies any non-`done` row against the `LangAtlas-Record-Key`
    git trailer (D36 §2.6) before treating it as resolved."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def upsert(self, *, run_id: str, spec_kind: str, item_key: str, status: str,
               record_key: str | None = None, detail: str = "",
               last_pause_reason: str | None = None) -> None:
        self._conn.execute(
            "INSERT INTO orchestrator_checkpoint"
            " (spec_kind, item_key, run_id, status, record_key, detail,"
            "  last_pause_reason, attempted_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(spec_kind, item_key) DO UPDATE SET"
            "   run_id=excluded.run_id, status=excluded.status,"
            "   record_key=excluded.record_key, detail=excluded.detail,"
            "   last_pause_reason=excluded.last_pause_reason,"
            "   attempted_at=excluded.attempted_at",
            (spec_kind, item_key, run_id, status, record_key, detail, last_pause_reason,
             datetime.now(timezone.utc).isoformat()))
        self._conn.commit()

    def get(self, *, spec_kind: str, item_key: str) -> CheckpointRow | None:
        row = self._conn.execute(
            "SELECT run_id, spec_kind, item_key, status, record_key, detail,"
            " last_pause_reason, attempted_at FROM orchestrator_checkpoint"
            " WHERE spec_kind = ? AND item_key = ?", (spec_kind, item_key)).fetchone()
        return CheckpointRow(*row) if row else None

    def rows_for_spec(self, spec_kind: str) -> list[CheckpointRow]:
        rows = self._conn.execute(
            "SELECT run_id, spec_kind, item_key, status, record_key, detail,"
            " last_pause_reason, attempted_at FROM orchestrator_checkpoint"
            " WHERE spec_kind = ? ORDER BY item_key", (spec_kind,)).fetchall()
        return [CheckpointRow(*row) for row in rows]

    def close(self) -> None:
        self._conn.close()
