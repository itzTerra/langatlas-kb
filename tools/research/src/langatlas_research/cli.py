"""`langatlas-research` — the research phase's bookkeeping CLI.

Subcommand dispatch, markdown/plain text to stdout, no daemon, never canonical data
beyond the `research/` files it is the writer of (matching the established
`tools/<domain>/` shape)."""
import argparse
import datetime as _dt
import subprocess
import sys
from pathlib import Path

from langatlas_research.cycle import CYCLE_STATUSES, advance, load_cycle, new_cycle, save_cycle, sign_off
from langatlas_research.errors import ResearchError
from langatlas_research.paths import ensure_layout
from langatlas_research.rotation import plan_languages
from langatlas_research.schema import validate_research_tree
from langatlas_research.themes import load_themes


def _git_user(repo_root: Path) -> str:
    result = subprocess.run(["git", "config", "user.name"], cwd=repo_root,
                            capture_output=True, text=True, check=False)
    return result.stdout.strip() or "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-research")
    parser.add_argument("--repo-root", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the research/ layout")
    sub.add_parser("validate", help="validate every research artifact")

    p_themes = sub.add_parser("themes").add_subparsers(dest="themes_command", required=True)
    p_themes.add_parser("list")

    p_cycle = sub.add_parser("cycle").add_subparsers(dest="cycle_command", required=True)
    p_new = p_cycle.add_parser("new")
    p_new.add_argument("number", type=int)
    p_new.add_argument("theme")
    p_new.add_argument("--size", type=int, default=5, help="R5 language sample width (4-5)")
    p_sign = p_cycle.add_parser("sign-off")
    p_sign.add_argument("number", type=int)
    p_sign.add_argument("--by", default=None)
    p_sign.add_argument("--date", default=None)
    p_status = p_cycle.add_parser("status")
    p_status.add_argument("number", type=int, nargs="?")
    p_advance = p_cycle.add_parser("advance")
    p_advance.add_argument("number", type=int)
    p_advance.add_argument("--to", required=True, choices=CYCLE_STATUSES)

    args = parser.parse_args(argv)
    root = args.repo_root
    try:
        return _dispatch(args, root)
    except ResearchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _dispatch(args, root: Path | None) -> int:
    if args.command == "init":
        for path in ensure_layout(root):
            print(f"created {path}")
        return 0

    if args.command == "validate":
        errors = validate_research_tree(root)
        for error in errors:
            print(error, file=sys.stderr)
        print(f"{len(errors)} error(s)")
        return 1 if errors else 0

    if args.command == "themes":
        for theme in load_themes(root).values():
            print(f"{theme.slug:34} {theme.label}")
        return 0

    if args.cycle_command == "new":
        cycle = new_cycle(args.number, args.theme, repo_root=root,
                          languages=plan_languages(args.number, size=args.size))
        print(f"drafted cycle {cycle.slug}; R5 sample: {', '.join(cycle.languages)}")
        print("NOT signed off — nothing may run until"
              f" `langatlas-research cycle sign-off {cycle.number}`")
        return 0

    if args.cycle_command == "sign-off":
        cycle = load_cycle(args.number, repo_root=root)
        signed = sign_off(cycle, by=args.by or _git_user(root or Path(".")),
                          date=args.date or _dt.date.today().isoformat(), repo_root=root)
        print(f"cycle {signed.slug} signed off by {signed.signed_off['by']}"
              f" on {signed.signed_off['date']} (theme digest"
              f" {signed.signed_off['theme_digest']})")
        return 0

    if args.cycle_command == "status":
        numbers = [args.number] if args.number else [
            int(p.name[:2]) for p in sorted((root or Path(".")).glob("research/cycles/*.yaml"))]
        for number in numbers:
            cycle = load_cycle(number, repo_root=root)
            signed = "signed" if cycle.signed_off else "UNSIGNED"
            print(f"{cycle.slug:28} {cycle.status:12} {signed:9}"
                  f" {len(cycle.nodes_minted):3} nodes  [{', '.join(cycle.languages)}]")
        return 0

    if args.cycle_command == "advance":
        cycle = advance(load_cycle(args.number, repo_root=root), args.to)
        save_cycle(cycle, repo_root=root)
        print(f"cycle {cycle.slug} -> {cycle.status}")
        return 0

    raise AssertionError("unreachable: argparse requires a subcommand")
