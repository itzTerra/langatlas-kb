"""`langatlas-research consolidate …` — R6 (Stage 3F). The offline steps never open a provider
or a database; `edges` and `migrate` open their own `RunContext` (D18). Later tasks add their
subcommands to `add_parser` and `_HANDLERS`."""
import datetime as _dt
from pathlib import Path

from langatlas_research.errors import ResearchError
from langatlas_research.paths import REPO_ROOT


def add_parser(sub) -> None:
    group = sub.add_parser(
        "consolidate", help="R6: cross-theme edges, dedup, slugs, migrations, settling"
    ).add_subparsers(dest="consolidate_command", required=True)
    group.add_parser("open", help="open the cycle's R6 consolidation record").add_argument(
        "number", type=int)
    group.add_parser("status", help="summarize a cycle's R6").add_argument("number", type=int)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _open(args, repo: Path) -> int:
    from langatlas_research.consolidate.lifecycle import open_r6

    cycle, _record = open_r6(args.number, repo_root=repo, opened_at=_now())
    print(f"R6 open for {cycle.slug}: research/consolidations/{cycle.slug}.yaml")
    print(f"next: langatlas-research consolidate edges {cycle.number}")
    return 0


def _status(args, repo: Path) -> int:
    from langatlas_research.consolidate.record import load_record
    from langatlas_research.cycle import load_cycle
    from langatlas_research.draft.plan import entries, load_plan

    cycle = load_cycle(args.number, repo_root=repo)
    record = load_record(cycle.slug, repo_root=repo)
    cross = record["cross_theme"]
    print(f"{cycle.slug}: {cycle.status}")
    print("cross-theme pass: " + (cross["run"] or (f"skipped — {cross['skipped']}"
                                                   if cross["skipped"] else "not run")))
    r6 = [entry for _name, entry in entries(load_plan(cycle.slug, repo_root=repo))
          if entry.get("pass") == "r6"]
    for status in sorted({entry["status"] for entry in r6}):
        print(f"  r6 edges {status}: {sum(1 for entry in r6 if entry['status'] == status)}")
    print(f"dedup rulings: {len(record['dedup'])}")
    print(f"migrations: {', '.join(record['migrations']) or 'none'}")
    return 0


_HANDLERS = {"open": _open, "status": _status}


def dispatch(args, root: Path | None) -> int:
    """An unknown cycle is a typed CLI error, not a FileNotFoundError traceback."""
    try:
        return _HANDLERS[args.consolidate_command](args, root or REPO_ROOT)
    except FileNotFoundError as exc:
        raise ResearchError(str(exc)) from exc
