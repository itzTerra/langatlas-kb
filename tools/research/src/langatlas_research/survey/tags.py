"""R3 tag rows: private, regenerable volume state (§2.2). Never in git and never in the
serving Postgres — a re-tag is free through the D26 call cache, so nothing here is a record
of anything the store depends on."""
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from langatlas_research.paths import private_research_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunk_tags (
    cycle_slug      TEXT NOT NULL,
    chunk_id        TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    status          TEXT NOT NULL,
    relevance       INTEGER NOT NULL,
    defined_terms   TEXT NOT NULL,
    mentioned_terms TEXT NOT NULL,
    dropped_terms   INTEGER NOT NULL,
    prompt_ref      TEXT NOT NULL,
    resolved_model  TEXT NOT NULL,
    tagged_at       TEXT NOT NULL,
    PRIMARY KEY (cycle_slug, chunk_id)
)
"""
_COLUMNS = ("chunk_id", "content_hash", "status", "relevance", "defined_terms",
            "mentioned_terms", "dropped_terms", "prompt_ref", "resolved_model")


@dataclass(frozen=True)
class ChunkTags:
    chunk_id: str
    content_hash: str
    status: str
    relevance: int
    defined_terms: tuple[str, ...]
    mentioned_terms: tuple[str, ...]
    dropped_terms: int
    prompt_ref: str
    resolved_model: str


def _row(values) -> ChunkTags:
    data = dict(zip(_COLUMNS, values))
    data["defined_terms"] = tuple(json.loads(data["defined_terms"]))
    data["mentioned_terms"] = tuple(json.loads(data["mentioned_terms"]))
    return ChunkTags(**data)


class TagStore:
    def __init__(self, db_path: Path | None = None):
        path = Path(db_path or private_research_dir() / "tags.sqlite")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def put(self, cycle_slug: str, tags: ChunkTags) -> None:
        """Upsert: a re-tag of the same chunk in the same cycle replaces its row."""
        self._conn.execute(
            f"INSERT OR REPLACE INTO chunk_tags (cycle_slug, {', '.join(_COLUMNS)}, tagged_at)"
            f" VALUES ({', '.join(['?'] * (len(_COLUMNS) + 2))})",
            (cycle_slug, tags.chunk_id, tags.content_hash, tags.status, tags.relevance,
             json.dumps(list(tags.defined_terms)), json.dumps(list(tags.mentioned_terms)),
             tags.dropped_terms, tags.prompt_ref, tags.resolved_model,
             datetime.now(timezone.utc).isoformat()))
        self._conn.commit()

    def get(self, cycle_slug: str, chunk_id: str) -> ChunkTags | None:
        row = self._conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM chunk_tags"
            " WHERE cycle_slug = ? AND chunk_id = ?", (cycle_slug, chunk_id)).fetchone()
        return _row(row) if row else None

    def for_cycle(self, cycle_slug: str) -> list[ChunkTags]:
        rows = self._conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM chunk_tags WHERE cycle_slug = ?"
            " ORDER BY chunk_id", (cycle_slug,)).fetchall()
        return [_row(row) for row in rows]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "TagStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
