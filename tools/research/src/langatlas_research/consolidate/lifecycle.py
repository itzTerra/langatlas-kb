"""R6's entry and exit. `open_r6` creates the consolidation record for an r5-done cycle;
`settle` (Task 13) closes R6 and marks the theme settled."""
from pathlib import Path

from langatlas_research.consolidate.record import (
    build_record, consolidation_path, load_record, save_record,
)
from langatlas_research.cycle import Cycle, load_cycle, require_sign_off
from langatlas_research.errors import R6NotReady


def open_r6(cycle_number: int, *, repo_root: Path, opened_at: str) -> tuple[Cycle, dict]:
    """Idempotent: an existing record is returned untouched, so a re-run never discards
    rulings.

    @raises SignOffMissing / SignOffStale / R6NotReady"""
    cycle = load_cycle(cycle_number, repo_root=repo_root)
    require_sign_off(cycle, repo_root=repo_root)
    if cycle.status != "r5-done":
        raise R6NotReady(f"cycle {cycle.slug} is at {cycle.status!r}; R6 opens once"
                         f" `reality finalize` has put it at r5-done")
    if consolidation_path(cycle.slug, repo_root).exists():
        return cycle, load_record(cycle.slug, repo_root=repo_root)
    record = build_record(cycle=cycle, opened_at=opened_at)
    save_record(record, repo_root=repo_root)
    return cycle, record
