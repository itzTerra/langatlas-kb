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


def _normalize_numerics(obj: Any) -> Any:
    """Recursively normalize all int values to float to ensure consistent hashing.
    Prevents cache misses from semantically identical calls differing only in int vs
    float representation (e.g., temperature=0 vs temperature=0.0)."""
    if isinstance(obj, dict):
        return {k: _normalize_numerics(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_normalize_numerics(item) for item in obj]
    elif isinstance(obj, int) and not isinstance(obj, bool):
        return float(obj)
    else:
        return obj


def cache_key(*, endpoint: str, resolved_model: str, messages: list[dict],
              sampling: dict[str, Any], schema_name: str | None,
              prompt_ref: str | None) -> str:
    """D26: keyed on the *resolved* model id, so a response is only ever re-served for
    the model that produced it. What this actually guarantees, precisely:

    - Entries are written under the model id the gateway reported on the response, and
      `CompletionClient` reads under the alias's run pin once one exists. So *within a
      run*, an alias floating to a different model is a miss, and the following
      `pin_alias` raises `AliasDrift`.
    - The first call of a run has no pin yet, so it reads under the configured
      `resolved_model` from `config/provider_capabilities.yaml`. If that value is stale
      (the probe runs monthly), that read simply misses — it cannot serve a response
      from a different model, but it also cannot *detect* the drift.
    - Nothing here consults the gateway's `/v1/model/info` route, so drift between probe
      cycles is invisible until a real call reports a different model id. Detecting it
      earlier would require querying that route; no code currently does.

    sort_keys makes dict ordering irrelevant; facts derived from a cached response are
    exactly as good, so entries are kept forever (no eviction)."""
    payload_dict = {
        "endpoint": endpoint, "resolved_model": resolved_model,
        "messages": messages, "sampling": sampling, "schema": schema_name,
        "prompt": prompt_ref
    }
    # Normalize numerics to ensure int/float variance doesn't cause false cache misses
    payload_dict = _normalize_numerics(payload_dict)
    payload = json.dumps(payload_dict, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CallCache:
    """Content-addressed response cache in the private tier (same backup as the D15
    snapshot store). On by default for pipeline runs; `--no-cache` for prompt tuning."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        # Enable WAL mode for better concurrency
        self._conn.execute("PRAGMA journal_mode=WAL")
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
