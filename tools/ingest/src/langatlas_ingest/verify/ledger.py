import json
import sqlite3
from pathlib import Path

from langatlas_ingest.paths import VERDICT_LEDGER_PATH
from langatlas_ingest.verify.verdicts import Assertion, PairVerdict

LEDGER_SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS verdicts (
    fact_id             TEXT NOT NULL,
    source_id           TEXT NOT NULL,
    locator             TEXT NOT NULL,
    run_id              TEXT NOT NULL,
    verdict             TEXT NOT NULL,
    per_assertion       TEXT NOT NULL DEFAULT '[]',
    annotations         TEXT NOT NULL DEFAULT '[]',
    since_status        TEXT,
    model               TEXT,
    prompt_version      TEXT,
    anchor              TEXT,
    date                TEXT,
    evidence_chunk_ids  TEXT NOT NULL DEFAULT '[]',
    hint                TEXT NOT NULL DEFAULT '',
    detail              TEXT NOT NULL DEFAULT '',
    recorded_at         TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (fact_id, source_id, locator, run_id)
);
CREATE INDEX IF NOT EXISTS verdicts_by_run ON verdicts (run_id);
"""


class VerdictLedger:
    """Section 6.2's private verdict ledger.

    Build-side and **never written into authored YAML** (D23): a verdict is a measurement
    about the corpus, not a fact about a language, and putting it in git would make the
    canonical store depend on which model happened to run last night.

    Every row carries `{verdict, per_assertion, model, prompt_version, run_id, anchor,
    date, evidence_chunk_ids}` so a verdict is re-derivable and each fact's "AI chat" link
    lands on the exact entailment exchange. Re-runs append rather than overwrite: the
    history is the audit trail for a prompt or model change.
    """

    def __init__(self, db_path: Path | None = None):
        """
        @param db_path - SQLite file to open; defaults to `paths.VERDICT_LEDGER_PATH`
            (always under `PRIVATE_DIR` per D23).
        @pre the parent directory is creatable (or already exists).
        """
        self.path = Path(db_path or VERDICT_LEDGER_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_DDL)
        self.conn.commit()

    def record(self, verdict: PairVerdict) -> None:
        """Store one pair verdict.

        @param verdict - the `PairVerdict` to persist.
        @returns None
        @pre Idempotent per (fact_id, source_id, locator, run_id): recording the same
            key again replaces that row in place rather than duplicating it, while a new
            `run_id` for the same (fact, source, locator) is kept as a separate row so the
            verdict history stays a re-runnable audit trail.
        """
        self.conn.execute(
            "INSERT OR REPLACE INTO verdicts (fact_id, source_id, locator, run_id,"
            " verdict, per_assertion, annotations, since_status, model, prompt_version,"
            " anchor, date, evidence_chunk_ids, hint, detail)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (verdict.fact_id, verdict.source_id, verdict.locator, verdict.run_id or "",
             verdict.verdict,
             json.dumps([a.as_dict() for a in verdict.per_assertion]),
             json.dumps(list(verdict.annotations)), verdict.since_status, verdict.model,
             verdict.prompt_version, verdict.anchor, verdict.date,
             json.dumps(list(verdict.evidence_chunk_ids)), verdict.hint, verdict.detail))
        self.conn.commit()

    def all_for(self, fact_id: str) -> list[PairVerdict]:
        """Every verdict ever recorded for `fact_id`, oldest first.

        @param fact_id - the fact to look up.
        @returns the full verdict history, including superseded runs.
        """
        rows = self.conn.execute(
            "SELECT * FROM verdicts WHERE fact_id = ? ORDER BY recorded_at, rowid",
            (fact_id,)).fetchall()
        return [_from_row(row) for row in rows]

    def latest_for(self, fact_id: str) -> list[PairVerdict]:
        """The newest verdict per (source, locator) — what the fold table reads.

        @param fact_id - the fact to look up.
        @returns one `PairVerdict` per distinct citation of the fact, from its most
            recent run.
        @pre "most recent" is ranked by `recorded_at` first and `rowid` only as a
            tiebreak — the same ordering `all_for` uses — so a backfill that inserts an
            older run's results after a newer run was already recorded does not get
            mistaken for the latest verdict just because it has the highest `rowid`.
        """
        rows = self.conn.execute(
            "SELECT * FROM verdicts v1 WHERE fact_id = ? AND NOT EXISTS ("
            "  SELECT 1 FROM verdicts v2"
            "  WHERE v2.fact_id = v1.fact_id AND v2.source_id = v1.source_id"
            "    AND v2.locator = v1.locator"
            "    AND (v2.recorded_at, v2.rowid) > (v1.recorded_at, v1.rowid))"
            " ORDER BY source_id, locator",
            (fact_id,)).fetchall()
        return [_from_row(row) for row in rows]

    def verdicts_in_run(self, run_id: str) -> list[PairVerdict]:
        """Every verdict produced by one verification run, in recording order.

        @param run_id - the run to look up.
        @returns all rows recorded under that run_id.
        """
        rows = self.conn.execute(
            "SELECT * FROM verdicts WHERE run_id = ? ORDER BY rowid", (run_id,)).fetchall()
        return [_from_row(row) for row in rows]

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.conn.close()

    def __enter__(self) -> "VerdictLedger":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _from_row(row: sqlite3.Row) -> PairVerdict:
    """Reconstruct a `PairVerdict` from one `verdicts` table row.

    @param row - a `sqlite3.Row` selected with `SELECT *` from `verdicts`.
    @returns the equivalent `PairVerdict`.
    """
    return PairVerdict(
        fact_id=row["fact_id"], source_id=row["source_id"], locator=row["locator"],
        verdict=row["verdict"],
        per_assertion=tuple(Assertion(**a) for a in json.loads(row["per_assertion"])),
        annotations=tuple(json.loads(row["annotations"])),
        since_status=row["since_status"], model=row["model"],
        prompt_version=row["prompt_version"], run_id=row["run_id"] or None,
        anchor=row["anchor"], date=row["date"],
        evidence_chunk_ids=tuple(json.loads(row["evidence_chunk_ids"])),
        hint=row["hint"], detail=row["detail"])
