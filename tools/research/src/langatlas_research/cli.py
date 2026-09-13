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

    p_amend = p_themes.add_parser("amend", help="apply or reject a survey's theme amendment")
    p_amend.add_argument("number", type=int, help="cycle whose survey proposed it")
    p_amend.add_argument("index", type=int, help="position in theme_amendments")
    p_amend.add_argument("--reject", action="store_true")

    p_survey = sub.add_parser("survey").add_subparsers(dest="survey_command", required=True)
    for name, help_text in (("pool", "freeze the cycle's candidate-chunk pool"),
                            ("run", "build the checklist and run the surveyor"),
                            ("scout", "scout sources for unevidenced candidates"),
                            ("finalize", "land the survey and mark the cycle r3-done")):
        p_survey.add_parser(name, help=help_text).add_argument("number", type=int)

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
        if args.themes_command == "amend":
            return _amend(args, root)
        for theme in load_themes(root).values():
            print(f"{theme.slug:34} {theme.label}")
        return 0

    if args.command == "survey":
        return _dispatch_survey(args, root)

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
        from langatlas_research.survey.amend import stale_cycles

        stale = {cycle.slug for cycle in stale_cycles(root)}
        numbers = [args.number] if args.number else [
            int(p.name[:2]) for p in sorted((root or Path(".")).glob("research/cycles/*.yaml"))]
        for number in numbers:
            cycle = load_cycle(number, repo_root=root)
            signed = "STALE" if cycle.slug in stale else (
                "signed" if cycle.signed_off else "UNSIGNED")
            print(f"{cycle.slug:28} {cycle.status:12} {signed:9}"
                  f" {len(cycle.nodes_minted):3} nodes  [{', '.join(cycle.languages)}]")
        return 0

    if args.cycle_command == "advance":
        cycle = advance(load_cycle(args.number, repo_root=root), args.to)
        save_cycle(cycle, repo_root=root)
        print(f"cycle {cycle.slug} -> {cycle.status}")
        return 0

    raise AssertionError("unreachable: argparse requires a subcommand")


def _amend(args, root: Path | None) -> int:
    from langatlas_research.survey.amend import apply_amendment, mark_amendment
    from langatlas_research.survey.inventory import load_survey, save_survey

    cycle = load_cycle(args.number, repo_root=root)
    survey = load_survey(cycle.slug, repo_root=root)
    amendment = survey["theme_amendments"][args.index]
    if amendment["status"] != "proposed":
        print(f"error: amendment {args.index} is already {amendment['status']}",
              file=sys.stderr)
        return 1
    if args.reject:
        save_survey(mark_amendment(survey, args.index, "rejected"), repo_root=root)
        print(f"rejected amendment {args.index} ({amendment['op']} {amendment['slug']})")
        return 0
    stale = apply_amendment(amendment, repo_root=root)
    # The survey's own digest may now be stale; its schema does not care, finalize does.
    save_survey(mark_amendment(survey, args.index, "applied"), repo_root=root)
    print(f"applied amendment {args.index} ({amendment['op']} {amendment['slug']})")
    for slug in stale:
        print(f"cycle {slug}: sign-off re-opened (D27) — review research/themes.yaml and run"
              f" `langatlas-research cycle sign-off {int(slug[:2])}`")
    return 0


def _dispatch_survey(args, root: Path | None) -> int:
    """The provider- and database-touching R3 steps. Each opens its own RunContext (D18)."""
    from langatlas_ingest.config import IngestConfig
    from langatlas_ingest.db import connect
    from langatlas_pipeline.providers.core import RunContext

    from langatlas_research.config import ResearchConfig
    from langatlas_research.paths import research_config_path
    from langatlas_research.survey.chunks import db_chunk_lookup, db_search_fn

    config = ResearchConfig.load(research_config_path(root))
    repo = root or Path(".")
    cycle = load_cycle(args.number, repo_root=root)

    with connect(IngestConfig.load().dsn) as conn:
        lookup = db_chunk_lookup(conn)

        if args.survey_command == "pool":
            from langatlas_research.survey.pool import build_pool, save_pool

            with RunContext.start(kind="r3-pool", slug=cycle.slug) as ctx:
                pool = build_pool(ctx, cycle, repo_root=root, search_fn=db_search_fn(ctx, conn),
                                  lookup=lookup, config=config.pool)
            path = save_pool(pool)
            print(f"froze {len(pool.entries)} chunks for {cycle.slug} at {path}")
            print("next: uv run --package langatlas-orchestrator langatlas-orchestrator run"
                  f" config/jobs/r3-corpus-tagging.yaml --set cycle={cycle.number}")
            return 0

        if args.survey_command == "run":
            from langatlas_research.survey.checklist import build_cycle_checklist
            from langatlas_research.survey.claude import role_budget
            from langatlas_research.survey.inventory import save_survey
            from langatlas_research.survey.pool import require_current_pool
            from langatlas_research.survey.surveyor import (
                SurveyInputs, run_surveyor, surveyor_tools,
            )
            from langatlas_research.survey.tags import TagStore

            pool = require_current_pool(cycle, repo_root=root)
            with TagStore() as store:
                tags = store.for_cycle(cycle.slug)
            if not any(row.status == "tagged" for row in tags):
                print(f"error: no tagged chunks for {cycle.slug}; run the"
                      " r3-corpus-tagging job first", file=sys.stderr)
                return 1
            with RunContext.start(kind="r3-survey", slug=cycle.slug,
                                  budget=role_budget(config.surveyor),
                                  agents=[{"role": "surveyor"}]) as ctx:
                checklist = build_cycle_checklist(ctx, cycle, repo_root=repo)
                servers, tools = surveyor_tools(ctx, conn)
                data, report = run_surveyor(
                    ctx, cycle, repo_root=root,
                    inputs=SurveyInputs(pool=pool, tags=tags, checklist=checklist),
                    lookup=lookup, config=config, mcp_servers=servers, allowed_tools=tools)
            path = save_survey(data, repo_root=root)
            print(f"wrote {path}: {len(data['candidates'])} candidates,"
                  f" {len(data['unevidenced'])} unevidenced,"
                  f" {len(data['theme_amendments'])} theme amendment(s)")
            for warning in report.warnings:
                print(f"warning: {warning}")
            return 0

        if args.survey_command == "scout":
            from langatlas_ingest.store import SourcingQueue
            from langatlas_ingest.tools import SERVER_NAME, TOOL_NAMES, sdk_source_tools

            from langatlas_research.survey.claude import role_budget
            from langatlas_research.survey.inventory import load_survey, save_survey
            from langatlas_research.survey.scout import new_source_command, run_scout

            survey = load_survey(cycle.slug, repo_root=root)
            with RunContext.start(kind="r3-scout", slug=cycle.slug,
                                  budget=role_budget(config.scout),
                                  agents=[{"role": "source-scout"}]) as ctx:
                updated = run_scout(ctx, cycle, survey, repo_root=repo, config=config,
                                    queue=SourcingQueue(conn),
                                    mcp_servers={SERVER_NAME: sdk_source_tools(ctx, conn)},
                                    allowed_tools=TOOL_NAMES)
            save_survey(updated, repo_root=root)
            new_entries = updated["scouting"][len(survey["scouting"]):]
            for entry in new_entries:
                print(f"{entry['status']:9} {entry['source_id']}"
                      f"{' — ' + entry['rejection'] if entry.get('rejection') else ''}")
                if entry["status"] == "filed":
                    print(f"          {new_source_command(entry)}")
            return 0

        from langatlas_research.survey.finalize import finalize_r3

        updated, results = finalize_r3(cycle.number, repo_root=repo, lookup=lookup)
        for result in results:
            print(repr(result))
        print(f"cycle {updated.slug} -> {updated.status}")
        return 0 if updated.status == "r3-done" else 1
