import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


def cache_key(*, endpoint: str, resolved_model: str, messages: list[dict],
              sampling: dict[str, Any], schema_name: str | None,
              prompt_ref: str | None) -> str:
    """D26: keyed on the *resolved* model id, so an alias silently floating to a new
    model version is a cache miss, not a stale hit. sort_keys makes dict ordering
    irrelevant; facts derived from a cached response are exactly as good, so entries
    are kept forever (no eviction)."""
    payload = json.dumps(
        {"endpoint": endpoint, "resolved_model": resolved_model, "messages": messages,
         "sampling": sampling, "schema": schema_name, "prompt": prompt_ref},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CallCache:
    """Content-addressed response cache in the private tier (same backup as the D15
    snapshot store). On by default for pipeline runs; `--no-cache` for prompt tuning."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def get(self, key: str) -> dict | None:
        row = self._conn.execute("SELECT value FROM calls WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, value: dict) -> None:
        self._conn.execute("INSERT OR REPLACE INTO calls (key, value) VALUES (?, ?)",
                           (key, json.dumps(value, ensure_ascii=False)))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
