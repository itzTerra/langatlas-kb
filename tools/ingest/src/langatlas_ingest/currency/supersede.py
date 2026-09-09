"""§4.4's edition-adoption act, as one explicit command.

Deliberately *not* reachable from the edition-check job: §4.4 says the job "opens a
triage-queue entry on mismatch, never auto-reingests", and this is the other side of that
sentence. Ingesting the replacement is the developer's existing `langatlas-sources ingest`
run; this module does the two bookkeeping halves that are easy to forget and impossible to
reconstruct later — the pointer on the old record and the ledger entry — plus the
`edition-superseded` trigger §4.4 names.

The trigger is filed into `sourcing_queue` (kind `edition-check`) because D25's own
re-verification queue does not exist until Stage 5. That is a carrier, not a redefinition:
the entry says a human should re-check what cited the old edition."""
import io
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_ingest.store import SourcingQueue
from langatlas_validate.normalize import normalize_record

_yaml = YAML()
_yaml.default_flow_style = False
_safe = YAML(typ="safe")

TOMBSTONE_REASON = "edition-superseded"


def _dump(data) -> str:
    buf = io.StringIO()
    _yaml.dump(data, buf)
    return buf.getvalue()


def supersede_source(repo_root: Path, *, old_id: str, new_id: str, note: str = "",
                     queue: SourcingQueue | None = None) -> list[Path]:
    """@returns the paths this rewrote, for the caller to stage and commit

    @raises ValueError when either id names no committed record, or they are the same
    """
    sources = repo_root / "sources"
    old_path, new_path = sources / f"{old_id}.yaml", sources / f"{new_id}.yaml"
    if old_id == new_id:
        raise ValueError(f"{old_id} cannot supersede itself")
    for source_id, path in ((old_id, old_path), (new_id, new_path)):
        if not path.exists():
            raise ValueError(f"no committed source record for {source_id} ({path})")

    old = _safe.load(old_path.read_text())
    old.setdefault("custom", {})["superseded_by"] = new_id
    old_path.write_text(normalize_record(_dump(old), "source"))

    ledger_path = sources / "_tombstones.yaml"
    ledger = _safe.load(ledger_path.read_text()) if ledger_path.exists() else None
    ledger = ledger or {"tombstones": []}
    entry = {"id": old_id, "superseded_by": new_id, "reason": TOMBSTONE_REASON,
             "note": note}
    # Re-running the command after a partial commit must not double the ledger: the
    # tombstone is a statement about a record, and a record is superseded once.
    existing = [t for t in ledger["tombstones"] if t.get("id") == old_id]
    if existing:
        existing[0].update(entry)
    else:
        ledger["tombstones"].append(entry)
    ledger_path.write_text(_dump(ledger))

    if queue is not None:
        queue.file(kind="edition-check", source_id=old_id, reason=TOMBSTONE_REASON,
                   detail=f"superseded by {new_id}; re-verify claims citing {old_id}"
                          + (f" ({note})" if note else ""))
    return [old_path, ledger_path]
