"""R6's entry and exit. `open_r6` creates the consolidation record for an r5-done cycle;
`settle` (Task 13) closes R6 and marks the theme settled."""
import subprocess
from dataclasses import replace
from pathlib import Path

from langatlas_commit.land import Landed, land_record
from ruamel.yaml.error import YAMLError
from langatlas_validate.migrate import MANIFEST_NAME, MIGRATIONS_REL, manifest_rel

from langatlas_research.consolidate.dedup import open_candidates
from langatlas_research.consolidate.record import (
    build_record, consolidation_path, consolidation_rel, load_record, render_record, save_record,
)
from langatlas_research.cycle import Cycle, load_cycle, require_sign_off, save_cycle, settle_cycle
from langatlas_research.draft.finalize import r4_blockers
from langatlas_research.draft.plan import load_plan, render_plan
from langatlas_research.errors import R6Incomplete, R6NotReady
from langatlas_research.land import store_validator
from langatlas_research.schema import validate_research_record


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


def _committed(repo_root: Path, rel: str) -> bool:
    """Tracked and identical to HEAD. False outside a git work tree."""
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", rel], cwd=repo_root,
                             capture_output=True, check=False)
    if tracked.returncode != 0:
        return False
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=repo_root,
                           capture_output=True, check=False)
    return clean.returncode == 0


def _unlanded_manifests(repo_root: Path) -> list[str]:
    directory = Path(repo_root) / MIGRATIONS_REL
    if not directory.exists():
        return []
    rels = [str(path.relative_to(repo_root))
            for path in sorted(directory.glob(f"*/{MANIFEST_NAME}"))]
    return [rel for rel in rels if not _committed(repo_root, rel)]


def r6_blockers(cycle: Cycle, plan: dict, record: dict, *, repo_root: Path) -> list[str]:
    """Every reason R6 cannot close, at once — each is a developer decision. A malformed
    plan or record is reported as its schema errors alone: nothing else about it can be
    trusted."""
    blockers = []
    if cycle.status != "r5-done":
        blockers.append(f"the cycle is at {cycle.status!r}; R6 settles an r5-done cycle")
    malformed = [f"carve plan: {error}" for error in
                 validate_research_record(plan, "draft", repo_root=repo_root)]
    malformed += [f"consolidation record: {error}" for error in
                  validate_research_record(record, "consolidation", repo_root=repo_root)]
    if malformed:
        return blockers + malformed
    cross = record["cross_theme"]
    if cross["run"] is None and cross["skipped"] is None:
        blockers.append("the cross-theme edge pass has not run — `consolidate edges`")
    blockers += r4_blockers(cycle, plan, repo_root=repo_root)
    for candidate in open_candidates(repo_root, cycle=cycle, record=record):
        blockers.append(f"{candidate['key']} ({' / '.join(candidate['nodes'])}): unruled dedup"
                        f" candidate — `consolidate rule`")
    for migration_id in record["migrations"]:
        if not _committed(repo_root, manifest_rel(migration_id)):
            blockers.append(f"{migration_id}: recorded as landed, but git does not hold it")
    for rel in _unlanded_manifests(repo_root):
        blockers.append(f"{rel}: a drafted migration that never landed — `consolidate migrate`"
                        f" it or delete it")
    return blockers


def _interrupted(landed: list[str], failed: str, why: str) -> R6Incomplete:
    done = ", ".join(landed) or "nothing"
    return R6Incomplete(
        f"settle stopped at {failed} ({why}). Landed before it: {done}. Not landed: {failed}"
        f" and everything after it; the cycle is not settled. Re-running `consolidate settle`"
        f" is safe — files already in history are not committed twice.")


def settle(cycle_number: int, *, repo_root: Path, by: str, date: str, status_checker=None,
           lander=land_record) -> tuple[Cycle, list]:
    """R6's exit and §7.4's settling, in one developer command.

    Landing order: carve plan, consolidation record (which carries any migration the run
    recorded but left uncommitted), then the settled cycle last, so a settled cycle on `main`
    always implies the other two landed. Idempotent: a settled cycle returns `(cycle, [])`,
    and a re-run after a partial landing skips what is already in history.

    @raises SignOffMissing / SignOffStale / R6Incomplete (open work, an empty `by`, or an
        interrupted landing — the message names what landed) / DraftMissing /
        ConsolidationMissing / ConsolidationInvalid"""
    cycle = load_cycle(cycle_number, repo_root=repo_root)
    require_sign_off(cycle, repo_root=repo_root)
    if not by or not by.strip():
        raise R6Incomplete("settling is the developer's act: pass --by with the developer's name")
    if cycle.status == "settled":
        return cycle, []
    try:
        plan = load_plan(cycle.slug, repo_root=repo_root)
    except YAMLError as exc:
        raise R6Incomplete(f"the carve plan of {cycle.slug} is not valid YAML: {exc}") from exc
    if not isinstance(plan, dict):
        raise R6Incomplete(f"the carve plan of {cycle.slug} must hold a YAML mapping")
    record = load_record(cycle.slug, repo_root=repo_root)
    blockers = r6_blockers(cycle, plan, record, repo_root=repo_root)
    if blockers:
        raise R6Incomplete(f"{cycle.slug} cannot settle: " + "; ".join(blockers))

    run_id = record["cross_theme"]["run"] or f"r6-{cycle.slug}"
    cycle_rel = f"research/cycles/{cycle.slug}.yaml"
    settled = replace(settle_cycle(cycle, by=by.strip(), date=date),
                      artifacts={**(cycle.artifacts or {}),
                                 "consolidation": consolidation_rel(cycle.slug)})
    results: list = []
    landed: list[str] = []

    def land(rel: str, text: str) -> None:
        try:
            result = lander(repo_root, rel, text, chat_run_id=run_id,
                            validator=store_validator, status_checker=status_checker)
        except Exception as exc:
            raise _interrupted(landed, rel, f"{type(exc).__name__}: {exc}") from exc
        results.append(result)
        if not isinstance(result, Landed):
            raise _interrupted(landed, rel, repr(result))
        landed.append(rel)

    land(f"research/drafts/{cycle.slug}.yaml", render_plan(plan))
    land(consolidation_rel(cycle.slug), render_record(record))
    save_cycle(settled, repo_root=repo_root)
    try:
        land(cycle_rel, (Path(repo_root) / cycle_rel).read_text())
    except BaseException:
        save_cycle(cycle, repo_root=repo_root)   # never leave a settled cycle nothing landed
        raise
    return settled, results
