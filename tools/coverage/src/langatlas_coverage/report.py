"""`langatlas-coverage` — D52's coverage reports. Markdown to stdout; `--snapshot` also writes
it under `reports/` (gitignored). Never committed, never cached: every run recomputes."""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from langatlas_coverage.gaps import DEFAULT_MIN_INSTANCES, gaps, render_gaps
from langatlas_coverage.metrics import StoreReadError, load_store
from langatlas_validate.paths import REPO_ROOT


def snapshot(repo_root: Path, command: str, text: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = Path(repo_root) / "reports" / f"coverage-{command}-{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="langatlas-coverage")
    parser.add_argument("--repo-root", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    p_gaps = sub.add_parser("gaps", help="<dimension, value> corroborating-instance counts")
    p_gaps.add_argument("--min-instances", type=int, default=DEFAULT_MIN_INSTANCES)
    p_gaps.add_argument("--snapshot", action="store_true")
    return parser


def _render(args, root: Path) -> str:
    store = load_store(root)
    return render_gaps(gaps(store, min_instances=args.min_instances),
                       min_instances=args.min_instances, instances_total=len(store.instances))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.repo_root or REPO_ROOT
    try:
        text = _render(args, root)
    except StoreReadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(text, end="")
    if args.snapshot:
        print(f"snapshot: {snapshot(root, args.command, text)}", file=sys.stderr)
    return 0
