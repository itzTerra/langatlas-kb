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
from langatlas_research.paths import REPO_ROOT, ensure_layout
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
    p_drop_gap = p_survey.add_parser(
        "drop-gap", help="developer escape hatch: mark an unevidenced gap dropped by hand")
    p_drop_gap.add_argument("number", type=int)
    p_drop_gap.add_argument("key", help="the unevidenced candidate's key")
    p_drop_gap.add_argument("--reason", required=True,
                            help="why this gap is being dropped without a source")

    p_draft = sub.add_parser("draft").add_subparsers(dest="draft_command", required=True)
    for name, help_text in (
            ("atomize", "run the ontologist over the cycle's candidate inventory"),
            ("contested", "list contested entries and their triggers"),
            ("status", "summarize the carve plan"),
            ("verify", "run the D24 gate over every ready entry"),
            ("mint", "land every admitted entry, one commit per record"),
            ("edges", "run the edge drafter over the committed nodes"),
            ("finalize", "land the carve plan and mark the cycle r4-done")):
        p_draft.add_parser(name, help=help_text).add_argument("number", type=int)
    p_debate = p_draft.add_parser("debate", help="debate contested entries (§7.2)")
    p_debate.add_argument("number", type=int)
    p_debate.add_argument("--key", action="append", default=[],
                          help="entry key; repeatable. Omit with --all for every open carve")
    p_debate.add_argument("--all", action="store_true")
    p_waive = p_draft.add_parser(
        "waive", help="developer escape hatch: accept a contested entry without a debate")
    p_waive.add_argument("number", type=int)
    p_waive.add_argument("key")
    p_waive.add_argument("--reason", required=True)

    p_instrument = sub.add_parser("instrument").add_subparsers(
        dest="instrument_command", required=True)
    for name, help_text in (("replay", "D30(a): the verifier-replay counterfactual"),
                            ("cost", "D30(b): Claude messages per accepted node by debate")):
        p_instrument.add_parser(name, help=help_text).add_argument(
            "number", type=int, nargs="?", help="cycle number; omit for every cycle")

    p_contro = sub.add_parser("controversy").add_subparsers(dest="controversy_command",
                                                            required=True)
    p_assess = p_contro.add_parser("assess", help="assess controversy levels (D21/D25)")
    p_assess.add_argument("records", nargs="*",
                          help="record paths; default: every record in the store")
    p_assess.add_argument("--limit", type=int, default=None,
                          help="stop after this many facts (default: config's max_facts_per_run)")
    p_assess.add_argument("--no-escalate", action="store_true",
                          help="skip the Claude review; level-3 and ambiguous facts are"
                               " assessed by the thinker alone and reported, not landed")
    p_contro.add_parser("status", help="levels recorded by the last assessment runs")

    from langatlas_research.reality.cli import add_parser as add_reality_parser

    add_reality_parser(sub)

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

    if args.command == "draft":
        return _dispatch_draft(args, root)

    if args.command == "instrument":
        return _dispatch_instrument(args, root)      # Task 13 writes this

    if args.command == "controversy":
        return _dispatch_controversy(args, root)

    if args.command == "reality":
        from langatlas_research.reality.cli import dispatch as dispatch_reality

        return dispatch_reality(args, root)

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


def _drop_gap(args, cycle, repo: Path) -> int:
    """Developer-only escape hatch for a gap the scout could never close — see `survey.rst` /
    README's "R3: the survey" section. Never called by an agent."""
    from langatlas_research.survey.inventory import drop_gap, load_survey, save_survey

    survey = load_survey(cycle.slug, repo_root=repo)
    gap = next((g for g in survey["unevidenced"] if g["key"] == args.key), None)
    if gap is None:
        print(f"error: no unevidenced candidate {args.key!r} in {cycle.slug}'s survey",
              file=sys.stderr)
        return 1
    if gap["disposition"] != "open":
        print(f"error: {args.key} is already {gap['disposition']}", file=sys.stderr)
        return 1
    save_survey(drop_gap(survey, args.key, args.reason), repo_root=repo)
    print(f"dropped {args.key} ({cycle.slug}): {args.reason}")
    return 0


def _dispatch_survey(args, root: Path | None) -> int:
    """The provider- and database-touching R3 steps. Each opens its own RunContext (D18)."""
    from langatlas_ingest.config import IngestConfig
    from langatlas_ingest.db import connect
    from langatlas_pipeline.providers.core import RunContext

    from langatlas_research.config import ResearchConfig
    from langatlas_research.paths import research_config_path
    from langatlas_research.survey.chunks import db_chunk_lookup, db_search_fn

    repo = root or REPO_ROOT
    config = ResearchConfig.load(research_config_path(repo))
    cycle = load_cycle(args.number, repo_root=repo)

    if args.survey_command == "drop-gap":
        return _drop_gap(args, cycle, repo)

    with connect(IngestConfig.load().dsn) as conn:
        lookup = db_chunk_lookup(conn)

        if args.survey_command == "pool":
            from langatlas_research.survey.pool import build_pool, save_pool

            with RunContext.start(kind="r3-pool", slug=cycle.slug) as ctx:
                pool = build_pool(ctx, cycle, repo_root=repo, search_fn=db_search_fn(ctx, conn),
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

            pool = require_current_pool(cycle, repo_root=repo)
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
                    ctx, cycle, repo_root=repo,
                    inputs=SurveyInputs(pool=pool, tags=tags, checklist=checklist),
                    lookup=lookup, config=config, mcp_servers=servers, allowed_tools=tools)
            path = save_survey(data, repo_root=repo)
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

            survey = load_survey(cycle.slug, repo_root=repo)
            with RunContext.start(kind="r3-scout", slug=cycle.slug,
                                  budget=role_budget(config.scout),
                                  agents=[{"role": "source-scout"}]) as ctx:
                updated = run_scout(ctx, cycle, survey, repo_root=repo, config=config,
                                    queue=SourcingQueue(conn),
                                    mcp_servers={SERVER_NAME: sdk_source_tools(ctx, conn)},
                                    allowed_tools=TOOL_NAMES)
            save_survey(updated, repo_root=repo)
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


def _dispatch_draft(args, root: Path | None) -> int:
    """R4's steps. The four offline ones (`contested`, `status`, `waive`, `finalize`) never
    open a connection or a provider; the rest open their own `RunContext` (D18)."""
    from langatlas_research.draft.contested import contested_triggers, open_carves, waive
    from langatlas_research.draft.plan import entries, load_plan, save_plan

    repo = root or REPO_ROOT
    cycle = load_cycle(args.number, repo_root=repo)

    if args.draft_command == "contested":
        plan = load_plan(cycle.slug, repo_root=repo)
        open_keys = set(open_carves(plan))
        for key, triggers in contested_triggers(plan, repo_root=repo).items():
            state = "OPEN" if key in open_keys else "closed"
            print(f"{key:44} {state:7} {', '.join(triggers)}")
        return 0

    if args.draft_command == "status":
        plan = load_plan(cycle.slug, repo_root=repo)
        for name, entry in entries(plan):
            verdict = (entry.get("verification") or {}).get("verdict", "-")
            print(f"{name:14} {entry['key']:44} {entry['status']:9} {verdict:12}"
                  f" {entry.get('debate_id') or ''}")
        return 0

    if args.draft_command == "waive":
        plan = load_plan(cycle.slug, repo_root=repo)
        try:
            save_plan(waive(plan, args.key, args.reason), repo_root=repo)
        except (KeyError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"waived {args.key} ({cycle.slug}): {args.reason}")
        return 0

    if args.draft_command == "finalize":
        from langatlas_research.draft.finalize import finalize_r4

        updated, results = finalize_r4(cycle.number, repo_root=repo)
        for result in results:
            print(repr(result))
        print(f"cycle {updated.slug} -> {updated.status}")
        return 0 if updated.status == "r4-done" else 1

    return _dispatch_draft_online(args, cycle, repo)


def _dispatch_draft_online(args, cycle, repo: Path) -> int:
    from langatlas_ingest.config import IngestConfig
    from langatlas_ingest.db import connect
    from langatlas_ingest.store import SourcingQueue
    from langatlas_pipeline.providers.core import RunContext

    from langatlas_research.config import ResearchConfig
    from langatlas_research.draft.plan import load_plan, save_plan
    from langatlas_research.paths import research_config_path
    from langatlas_research.survey.chunks import db_chunk_lookup
    from langatlas_research.survey.claude import role_budget

    config = ResearchConfig.load(research_config_path(repo))
    with connect(IngestConfig.load().dsn) as conn:
        lookup = db_chunk_lookup(conn)

        if args.draft_command == "atomize":
            from langatlas_research.draft.contested import mark_contested
            from langatlas_research.draft.ontologist import ontologist_tools, run_ontologist
            from langatlas_research.survey.inventory import load_survey

            survey = load_survey(cycle.slug, repo_root=repo)
            with RunContext.start(kind="r4-atomize", slug=cycle.slug,
                                  budget=role_budget(config.draft.ontologist),
                                  agents=[{"role": "ontologist"}]) as ctx:
                servers, tools = ontologist_tools(ctx, conn)
                plan, warnings = run_ontologist(ctx, cycle, repo_root=repo, survey=survey,
                                                lookup=lookup, config=config,
                                                mcp_servers=servers, allowed_tools=tools)
            path = save_plan(mark_contested(plan, repo_root=repo), repo_root=repo)
            print(f"wrote {path}: {len(plan['nodes'])} nodes,"
                  f" {len(plan['dimensions'])} dimension(s),"
                  f" {len(plan['findings'])} finding(s)")
            for warning in warnings:
                print(f"warning: {warning}")
            print("next: langatlas-research draft contested"
                  f" {cycle.number}")
            return 0

        if args.draft_command == "edges":
            from langatlas_research.draft.edges import run_edge_drafter
            from langatlas_research.draft.ontologist import ontologist_tools

            plan = load_plan(cycle.slug, repo_root=repo)
            with RunContext.start(kind="r4-edges", slug=cycle.slug,
                                  budget=role_budget(config.draft.edge_drafter),
                                  agents=[{"role": "edge-drafter"}]) as ctx:
                servers, tools = ontologist_tools(ctx, conn)
                updated, warnings = run_edge_drafter(ctx, cycle, plan, repo_root=repo,
                                                     lookup=lookup, config=config,
                                                     mcp_servers=servers,
                                                     allowed_tools=tools)
            save_plan(updated, repo_root=repo)
            print(f"{len(updated['edges'])} edge(s),"
                  f" {len(updated['quality_edges'])} quality edge(s),"
                  f" {len(updated['qualities'])} proposed quality/qualities")
            for warning in warnings:
                print(f"warning: {warning}")
            return 0

        if args.draft_command == "debate":
            from langatlas_research.draft.contradictions import mint_debate_contradiction
            from langatlas_research.draft.contested import open_carves
            from langatlas_research.draft.debate import run_debate
            from langatlas_research.draft.ontologist import ontologist_tools

            plan = load_plan(cycle.slug, repo_root=repo)
            keys = args.key or (open_carves(plan) if args.all else [])
            if not keys:
                print("error: name at least one --key, or pass --all", file=sys.stderr)
                return 1
            cap = config.draft.debate.max_debates_per_cycle
            if len(keys) > cap:
                print(f"error: {len(keys)} debates exceeds the configured cap of {cap};"
                      f" debate the most contested carves and waive the rest",
                      file=sys.stderr)
                return 1
            for key in keys:
                debate_id = None
                with RunContext.start(kind="r4-debate", slug=f"{cycle.slug}-{key}",
                                      budget=role_budget(config.draft.debate.proposer),
                                      agents=[{"role": "proposer"},
                                              {"role": "challenger-a"},
                                              {"role": "challenger-b"}]) as ctx:
                    servers, tools = ontologist_tools(ctx, conn)
                    with RunContext.start(kind="r4-moderator",
                                          slug=f"{cycle.slug}-{key}",
                                          budget=role_budget(
                                              config.draft.debate.moderator),
                                          agents=[{"role": "moderator"}]) as moderator_ctx:
                        plan, debate = run_debate(ctx, cycle, plan, key, repo_root=repo,
                                                  config=config, lookup=lookup,
                                                  moderator_ctx=moderator_ctx,
                                                  mcp_servers=servers, allowed_tools=tools)
                        debate_id = debate["id"]
                        # Both contexts carry the debate id so the transcripts join up.
                        ctx.manifest.debate_id = debate_id
                        moderator_ctx.manifest.debate_id = debate_id
                contradiction = mint_debate_contradiction(debate, repo_root=repo)
                save_plan(plan, repo_root=repo)
                resolution = debate["resolution"]
                print(f"{debate_id}  {key}: {resolution['disposition']} ->"
                      f" {resolution['outcome']}"
                      f"{' (standing dissent)' if resolution['standing_dissent'] else ''}"
                      f"{' contradiction ' + contradiction if contradiction else ''}")
            return 0

        if args.draft_command == "verify":
            from langatlas_research.draft.gate import verify_plan

            from langatlas_ingest.verify.ledger import VerdictLedger
            from langatlas_ingest.verify.pipeline import VerifyDeps

            plan = load_plan(cycle.slug, repo_root=repo)
            # D68: record R4's verdicts in the private ledger, as R5 and the nightly batch do,
            # so 3F's sourcing-integrity item never waits on a nightly re-verification.
            with VerdictLedger() as ledger, RunContext.start(kind="r4-verify",
                                                              slug=cycle.slug) as ctx:
                deps = VerifyDeps.build(conn, ctx, config=IngestConfig.load(), ledger=ledger)
                updated, results = verify_plan(ctx, conn, plan, cycle=cycle, repo_root=repo,
                                               config=config, lookup=lookup, deps=deps,
                                               queue=SourcingQueue(conn))
            save_plan(updated, repo_root=repo)
            for result in results:
                mark = "admitted" if result.admissible else "REFUSED "
                print(f"{mark} {result.key:44} {result.verdict:12}"
                      f" {result.pairs} pair(s) {result.detail}")
            return 0

        from langatlas_research.draft.minting import mint_plan, plan_prompt_versions

        plan = load_plan(cycle.slug, repo_root=repo)
        # Which prompt version produced each list, resolved from the registry rather than
        # left blank: a record whose `proposer.prompt_version` is empty cannot be traced
        # back to the prompt that wrote it, which is the whole point of versioning them.
        versions = plan_prompt_versions()
        with RunContext.start(kind="r4-mint", slug=cycle.slug) as ctx:
            updated, results = mint_plan(plan, repo_root=repo, cycle=cycle,
                                         chat_run_id=ctx.run_id, prompt_version="",
                                         prompt_versions=versions)
        save_plan(updated, repo_root=repo)
        for minted, outcome in results:
            print(f"{minted.path}: {outcome!r}")
        return 0


def _dispatch_instrument(args, root: Path | None) -> int:
    """D30's two scripts. The cost join is pure log reading; the replay counterfactual runs
    the verifier again, so it opens a connection and a `RunContext` like any other verified
    step (D18)."""
    repo = root or REPO_ROOT

    if args.instrument_command == "cost":
        from langatlas_research.instrument.costjoin import cost_join, render_cost

        print(render_cost(cost_join(repo, cycle=args.number)), end="")
        return 0

    from langatlas_ingest.config import IngestConfig
    from langatlas_ingest.db import connect
    from langatlas_pipeline.providers.core import RunContext

    from langatlas_research.config import ResearchConfig
    from langatlas_research.instrument.replay import render_replay, replay_counterfactual
    from langatlas_research.paths import research_config_path

    config = ResearchConfig.load(research_config_path(repo))
    with connect(IngestConfig.load().dsn) as conn:
        with RunContext.start(kind="r4-replay", slug=f"cycle-{args.number or 'all'}") as ctx:
            rows = replay_counterfactual(ctx, conn, repo, cycle=args.number, config=config)
    print(render_replay(rows), end="")
    return 0


def _dispatch_controversy(args, root: Path | None) -> int:
    """D21/D25's assessor. Sources, contradictions and debates are read once for the whole
    run; the verdict ledger and the assessment ledger are opened once each."""
    from langatlas_ingest.verify.ledger import VerdictLedger
    from langatlas_pipeline.providers.core import RunContext

    from langatlas_research.config import ResearchConfig
    from langatlas_research.controversy.assemble import load_deps
    from langatlas_research.controversy.assessor import assess_inputs
    from langatlas_research.controversy.escalate import capture_candidate, escalate
    from langatlas_research.controversy.ledger import AssessmentLedger
    from langatlas_research.controversy.run import Deps, assess_record, default_land, store_record_paths
    from langatlas_research.paths import research_config_path

    repo = root or REPO_ROOT
    config = ResearchConfig.load(research_config_path(repo)).controversy

    if args.controversy_command == "status":
        with AssessmentLedger() as ledger:
            levels = ledger.levels()
        counts = {level: sum(1 for v in levels.values() if v == level) for level in (0, 1, 2, 3)}
        print(f"{len(levels)} assessed fact(s): "
              + ", ".join(f"level {k}: {v}" for k, v in counts.items()))
        return 0

    today = _dt.date.today().isoformat()
    paths = list(args.records) or store_record_paths(repo)
    budget = args.limit if args.limit is not None else config.max_facts_per_run
    totals = {"assessed": 0, "skipped": 0, "escalated": 0, "changed": 0}

    with VerdictLedger() as verdicts, AssessmentLedger() as ledger, \
            RunContext.start(kind="controversy", slug=today) as ctx:
        shared = load_deps(repo, verdicts)

        def _escalate(assessment, inputs):
            # Its own RunContext (D18): the review is a different conversation with a
            # different model, and a shared transcript would make the volume pass unreadable.
            with RunContext.start(kind="controversy-escalation",
                                  slug=assessment.fact_id) as review_ctx:
                final = escalate(review_ctx, assessment, inputs,
                                 role_config=config.escalation)
            capture_candidate(assessment, final, inputs, repo_root=repo, today=today)
            return final

        deps = Deps(assess=assess_inputs,
                    escalate=None if args.no_escalate else _escalate,
                    ledger=ledger, land=default_land(repo, ctx.run_id), alias=config.alias,
                    today=today, source_facts=shared.source_facts,
                    contradictions=shared.contradictions, debates=shared.debates,
                    verdict_ledger=verdicts,
                    spread_min_assessments=config.spread_min_assessments)
        for record_path in paths:
            if totals["assessed"] >= budget:
                print(f"budget reached ({budget} facts); re-run to continue")
                break
            outcome = assess_record(ctx, record_path, repo_root=repo, deps=deps)
            totals["assessed"] += outcome.assessed
            totals["skipped"] += outcome.skipped
            totals["escalated"] += outcome.escalated
            totals["changed"] += int(outcome.changed)
            if outcome.assessed or outcome.changed:
                print(f"{record_path}: assessed {outcome.assessed}, skipped {outcome.skipped},"
                      f" escalated {outcome.escalated},"
                      f" {'landed' if outcome.changed else 'unchanged'}")
    print(f"total: {totals['assessed']} assessed, {totals['skipped']} unchanged,"
          f" {totals['escalated']} escalated, {totals['changed']} record(s) landed")
    return 0
