import time
from pathlib import Path

from langatlas_commit.trailers import find_record_key_in_history
from langatlas_pipeline.errors import BudgetExceeded, ClaudeLimitSignal
from langatlas_pipeline.providers.core import RunContext

from langatlas_orchestrator.checkpoint import CheckpointStore
from langatlas_orchestrator.registry import get_job_kind
from langatlas_orchestrator.spec import load_batch_spec
from langatlas_orchestrator.status import read_status, write_status

# sysexits-style: 75 (EX_TEMPFAIL) means "come back later, on purpose" — distinguishes a
# clean pause from a crash (nonzero-but-not-75) or clean completion (0), for any wrapping
# cron/shell logic to detect (D43 §2.3).
EXIT_OK = 0
EXIT_PAUSED = 75
EXIT_HALTED = 1

# D43 §2.4, ratified: a fixed 4-hour cool-down, no calibration data exists to sharpen it.
_CLAUDE_LIMIT_COOLDOWN_SECONDS = 4 * 60 * 60


def run(spec_path: Path, *, repo_root: Path, status_path: Path | None = None) -> int:
    """The one generic loop every job kind shares (D43 §2.1): enumerate → for each item,
    skip if already `done`, resolve ambiguous rows via the git trailer, otherwise call
    the job's item runner inside a `RunContext`-scoped run → checkpoint → decide
    continue/pause/halt. Resume is calling this function again with the same spec —
    there is no separate resume mode (D43 §2.3)."""
    spec = load_batch_spec(spec_path)
    enumerator, item_runner = get_job_kind(spec.kind)

    existing = read_status(status_path).get(spec.kind)
    if existing and existing.get("state") == "paused" and existing.get("reason") == "claude_limit":
        paused_until = existing.get("paused_until") or 0
        if time.time() < paused_until:
            remaining = int(paused_until - time.time())
            print(f"{spec.kind}: still cooling down from a Claude usage limit, "
                 f"{remaining}s remaining; no-op")
            return EXIT_PAUSED

    store = CheckpointStore(spec.checkpoint_path)
    items = enumerator(spec.extra, repo_root)
    ctx = RunContext.start(kind=spec.kind, slug=spec.kind, budget=spec.budget)

    try:
        for index, item_key in enumerate(items):
            row = store.get(spec_kind=spec.kind, item_key=item_key)
            if row is not None and row.status == "done":
                continue
            if row is not None and row.status in ("in_progress", "blocked", "contention") \
                    and row.record_key is not None:
                landed_sha = find_record_key_in_history(repo_root, row.record_key)
                if landed_sha is not None:
                    store.upsert(run_id=ctx.run_id, spec_kind=spec.kind, item_key=item_key,
                                status="done", record_key=row.record_key,
                                detail=f"resolved via git trailer at {landed_sha}")
                    continue

            store.upsert(run_id=ctx.run_id, spec_kind=spec.kind, item_key=item_key,
                        status="in_progress")
            try:
                outcome = item_runner(ctx, item_key, spec.extra, repo_root)
            except BudgetExceeded as exc:
                store.upsert(run_id=ctx.run_id, spec_kind=spec.kind, item_key=item_key,
                            status="blocked", last_pause_reason=f"budget:{exc}")
                write_status(spec.kind, state="paused", reason="budget",
                            paused_at=time.time(), items_remaining=len(items) - index,
                            path=status_path)
                return EXIT_PAUSED
            except ClaudeLimitSignal as exc:
                store.upsert(run_id=ctx.run_id, spec_kind=spec.kind, item_key=item_key,
                            status="blocked", last_pause_reason=f"claude_limit:{exc}")
                now = time.time()
                write_status(spec.kind, state="paused", reason="claude_limit",
                            paused_at=now, paused_until=now + _CLAUDE_LIMIT_COOLDOWN_SECONDS,
                            items_remaining=len(items) - index, path=status_path)
                return EXIT_PAUSED

            store.upsert(run_id=ctx.run_id, spec_kind=spec.kind, item_key=item_key,
                        status=outcome.status, record_key=outcome.record_key,
                        detail=outcome.detail)
            if outcome.status == "halted":
                write_status(spec.kind, state="halted", reason=outcome.detail,
                            paused_at=time.time(), items_remaining=len(items) - index,
                            path=status_path)
                return EXIT_HALTED

        write_status(spec.kind, state="done", reason=None, items_remaining=0,
                    path=status_path)
        return EXIT_OK
    finally:
        ctx.close()
        store.close()


def main(argv: list[str] | None = None) -> int:
    import argparse

    from langatlas_validate.paths import REPO_ROOT

    # Registers the built-in job kinds (capability probe, r0 exit test, the deferred
    # D43-inventory kinds) as an import side effect — see jobs/__init__.py.
    import langatlas_orchestrator.jobs  # noqa: F401

    parser = argparse.ArgumentParser(prog="langatlas-orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("spec", type=Path)
    p_run.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    p_run.add_argument("--status-path", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.command == "run":
        return run(args.spec, repo_root=args.repo_root, status_path=args.status_path)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
