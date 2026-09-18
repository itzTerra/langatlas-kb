"""The private assessment ledger: `(fact_id, inputs_digest, level, signals)`.

Why this is not in git, when the level itself is: §6.4 makes an absent block mean level 0, and
level 0 is the overwhelming majority of facts — so a git-resident digest could not cover the
case the free-re-run rule exists for. It is also, exactly like `VerdictLedger`, a measurement
made by whichever model ran last night rather than a fact about a language (D23).

It is a cache. A deleted ledger costs one full re-assessment and nothing else; it can never
disagree with the store in a way that matters, because the store's block is what the site and
the bundle read."""
import json
import sqlite3
from pathlib import Path

from langatlas_research.paths import private_controversy_dir

LEDGER_SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS assessments (
    fact_id       TEXT PRIMARY KEY,
    inputs_digest TEXT NOT NULL,
    level         INTEGER NOT NULL,
    signals       TEXT NOT NULL DEFAULT '[]',
    model         TEXT NOT NULL DEFAULT '',
    prompt        TEXT NOT NULL DEFAULT '',
    run_id        TEXT NOT NULL DEFAULT '',
    escalated_to  TEXT,
    assessed_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class AssessmentLedger:
    """@param db_path: defaults to `<private>/research/controversy/assessments.sqlite`."""

    def __init__(self, db_path: Path | None = None):
        self.path = Path(db_path or private_controversy_dir() / "assessments.sqlite")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_DDL)
        self.conn.commit()

    def previous(self, fact_id: str) -> tuple[str, int, tuple[str, ...]] | None:
        """@returns `(inputs_digest, level, signals)` from the last assessment, or None."""
        row = self.conn.execute(
            "SELECT inputs_digest, level, signals FROM assessments WHERE fact_id = ?",
            (fact_id,)).fetchone()
        if row is None:
            return None
        return row["inputs_digest"], int(row["level"]), tuple(json.loads(row["signals"]))

    def record(self, assessment, *, digest: str) -> None:
        """Latest-wins per fact: the history lives in git (the block) and in the transcript
        (D18), so a second copy here would be a third place to disagree."""
        self.conn.execute(
            "INSERT OR REPLACE INTO assessments (fact_id, inputs_digest, level, signals,"
            " model, prompt, run_id, escalated_to) VALUES (?,?,?,?,?,?,?,?)",
            (assessment.fact_id, digest, int(assessment.level),
             json.dumps(list(assessment.signals)), assessment.model, assessment.prompt,
             assessment.run_id, assessment.escalated_to))
        self.conn.commit()

    def levels(self) -> dict:
        """fact_id -> level, for `controversy status`."""
        return {row["fact_id"]: int(row["level"])
                for row in self.conn.execute("SELECT fact_id, level FROM assessments")}

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "AssessmentLedger":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
