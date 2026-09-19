"""`langatlas-research consolidate …` — R6 (Stage 3F). The offline steps never open a provider
or a database; `edges` and `migrate` open their own `RunContext` (D18). Later tasks add their
subcommands to `add_parser` and `_HANDLERS`."""
import datetime as _dt
import sys
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
    p_draft = group.add_parser("draft-migration",
                               help="draft a manifest from the casebook defaults (D38)")
    p_draft.add_argument("number", type=int, help="the cycle doing the consolidating")
    p_draft.add_argument("--op", required=True, choices=["merge", "split", "remove", "move"])
    p_draft.add_argument("--from", dest="frm", action="append", default=[],
                         help="merge: repeatable; split: the node being split")
    p_draft.add_argument("--to", action="append", default=[],
                         help="merge: the survivor; split: repeatable children")
    p_draft.add_argument("--node", help="remove / move: the node")
    p_draft.add_argument("--layer", type=int, choices=[1, 2, 3], help="move: the new layer")
    p_draft.add_argument("--dimension", help="move to layer 3: the dimension")
    p_draft.add_argument("--old-node", choices=["demote-to-concept", "tombstone"],
                         help="split: what becomes of the split node (default demote)")
    p_draft.add_argument("--rationale", required=True)
    p_draft.add_argument("--slug", help="migration id slug (default: op and node ids)")
    group.add_parser("edges", help="the cross-theme edge pass (Claude)").add_argument(
        "number", type=int)
    p_guard = group.add_parser("guard", help="CI: settled themes restructure only by manifest")
    p_guard.add_argument("--since", default=None)
    p_migrate = group.add_parser("migrate",
                                 help="plan, gate and land a drafted manifest as one commit")
    p_migrate.add_argument("number", type=int)
    p_migrate.add_argument("migration_id")
    group.add_parser("dedup", help="list the cycle's open dedup/alias candidates").add_argument(
        "number", type=int)
    p_rule = group.add_parser("rule", help="developer ruling on one dedup candidate")
    p_rule.add_argument("number", type=int)
    p_rule.add_argument("key")
    how = p_rule.add_mutually_exclusive_group(required=True)
    how.add_argument("--distinct", action="store_true")
    how.add_argument("--merge-into", metavar="NODE")
    how.add_argument("--drop-alias", metavar="ALIAS")
    p_rule.add_argument("--node", help="with --drop-alias: the feature losing the alias")
    p_rule.add_argument("--reason", required=True)
    group.add_parser("slugs", help="list slug-polish candidates").add_argument(
        "number", type=int)
    p_settle = group.add_parser("settle", help="close R6 and mark the theme settled (§7.4)")
    p_settle.add_argument("number", type=int)
    p_settle.add_argument("--by", default=None, help="the developer settling the theme (required)")
    p_settle.add_argument("--date", default=None)
    p_rename = group.add_parser("rename-slug", help="rename a slug; the old one redirects")
    p_rename.add_argument("number", type=int)
    p_rename.add_argument("node")
    p_rename.add_argument("new_slug")


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


def _disposition(args) -> dict:
    if args.op == "merge":
        if len(args.to) != 1 or not args.frm:
            raise SystemExit("merge takes one or more --from and exactly one --to")
        return {"op": "merge", "from": args.frm, "to": args.to[0]}
    if args.op == "split":
        if len(args.frm) != 1 or len(args.to) < 2:
            raise SystemExit("split takes exactly one --from and two or more --to")
        disposition = {"op": "split", "from": args.frm[0], "to": args.to}
        if args.old_node:
            disposition["old_node"] = args.old_node
        return disposition
    if not args.node:
        raise SystemExit(f"{args.op} takes --node")
    if args.op == "remove":
        return {"op": "remove", "node": args.node}
    if args.layer is None:
        raise SystemExit("move takes --layer")
    return {"op": "move", "node": args.node, "to_layer": args.layer,
            "to_dimension": args.dimension}


def _draft_migration(args, repo: Path) -> int:
    from langatlas_research.consolidate.migration import (
        default_slug, draft_manifest, write_draft,
    )
    from langatlas_research.cycle import load_cycle

    cycle = load_cycle(args.number, repo_root=repo)
    disposition = _disposition(args)
    manifest = draft_manifest(repo, disposition, cycle=cycle,
                              date=_dt.date.today().isoformat(), rationale=args.rationale,
                              slug=args.slug or default_slug(disposition))
    path = write_draft(repo, manifest)
    print(f"drafted {path.relative_to(repo)} — {len(manifest['dispositions'][0]['fact_remap'])}"
          f" fact_remap entries from the casebook; settled themes touched:"
          f" {', '.join(manifest['settled_themes']) or 'none'}")
    print("review and edit it, dry-run with `langatlas-validate migrations plan <path>`, then:")
    print(f"next: langatlas-research consolidate migrate {cycle.number} {manifest['migration_id']}")
    return 0


def _migrate(args, repo: Path) -> int:
    from langatlas_ingest.config import IngestConfig
    from langatlas_ingest.db import connect
    from langatlas_ingest.store import SourcingQueue
    from langatlas_ingest.verify.ledger import VerdictLedger
    from langatlas_ingest.verify.pipeline import VerifyDeps
    from langatlas_pipeline.providers.core import RunContext

    from langatlas_research.config import ResearchConfig
    from langatlas_research.consolidate.migration import run_migration
    from langatlas_research.cycle import load_cycle
    from langatlas_research.paths import research_config_path

    cycle = load_cycle(args.number, repo_root=repo)
    config = ResearchConfig.load(research_config_path(repo))
    ingest_config = IngestConfig.load()
    with connect(ingest_config.dsn) as conn, VerdictLedger() as ledger, \
            RunContext.start(kind="r6-migrate",
                             slug=f"{cycle.slug}-{args.migration_id[:4]}") as ctx:
        deps = VerifyDeps.build(conn, ctx, config=ingest_config, ledger=ledger)
        plan, results, outcome = run_migration(ctx, conn, cycle, args.migration_id,
                                               repo_root=repo, config=config, deps=deps,
                                               queue=SourcingQueue(conn))
    for result in results:
        print(f"admitted {result.key:44} {result.verdict}")
    print(f"{len(plan.changes)} file(s), {len(plan.tombstones)} tombstone(s): {outcome!r}")
    return 0 if type(outcome).__name__ == "Landed" else 1


def _edges(args, repo: Path) -> int:
    from langatlas_research.consolidate.cross_theme import run_cross_theme, skip_reason
    from langatlas_research.consolidate.record import load_record, save_record
    from langatlas_research.cycle import load_cycle, require_sign_off
    from langatlas_research.draft.plan import load_plan, save_plan

    cycle = load_cycle(args.number, repo_root=repo)
    require_sign_off(cycle, repo_root=repo)
    record = load_record(cycle.slug, repo_root=repo)
    plan = load_plan(cycle.slug, repo_root=repo)
    reason = skip_reason(repo, cycle)
    if reason:
        save_record({**record, "cross_theme": {"run": None, "skipped": reason, "edges": []}},
                    repo_root=repo)
        print(f"cross-theme pass skipped: {reason}")
        return 0

    from langatlas_ingest.config import IngestConfig
    from langatlas_ingest.db import connect
    from langatlas_pipeline.providers.core import RunContext

    from langatlas_research.config import ResearchConfig
    from langatlas_research.draft.ontologist import ontologist_tools
    from langatlas_research.paths import research_config_path
    from langatlas_research.survey.chunks import db_chunk_lookup
    from langatlas_research.survey.claude import role_budget

    config = ResearchConfig.load(research_config_path(repo))
    with connect(IngestConfig.load().dsn) as conn:
        with RunContext.start(kind="r6-cross-theme", slug=cycle.slug,
                              budget=role_budget(config.consolidation.cross_theme_drafter),
                              agents=[{"role": "cross-theme-edge-drafter"}]) as ctx:
            servers, tools = ontologist_tools(ctx, conn)
            updated, record, warnings = run_cross_theme(
                ctx, cycle, plan, record, repo_root=repo, lookup=db_chunk_lookup(conn),
                config=config, mcp_servers=servers, allowed_tools=tools)
    save_plan(updated, repo_root=repo)
    save_record(record, repo_root=repo)
    print(f"{len(record['cross_theme']['edges'])} cross-theme edge(s) proposed")
    for warning in warnings:
        print(f"warning: {warning}")
    print(f"next: langatlas-research draft debate {cycle.number} --all, then draft verify /"
          f" draft mint")
    return 0


def _guard(args, repo: Path) -> int:
    from langatlas_research.consolidate.guard import check_settled

    errors = check_settled(repo, args.since)
    for error in errors:
        print(f"SETTLED {error}")
    if not errors:
        print("settled themes: no unmanifested restructure")
    return 1 if errors else 0



def _dedup(args, repo: Path) -> int:
    from langatlas_research.consolidate.dedup import open_candidates
    from langatlas_research.consolidate.record import load_record
    from langatlas_research.cycle import load_cycle

    from langatlas_research.cycle import require_sign_off

    cycle = load_cycle(args.number, repo_root=repo)
    require_sign_off(cycle, repo_root=repo)
    found = open_candidates(repo, cycle=cycle, record=load_record(cycle.slug, repo_root=repo))
    for candidate in found:
        print(f"{candidate['key']}  {' / '.join(candidate['nodes']):56}"
              f" {', '.join(candidate['signals'])}")
    print(f"{len(found)} open candidate(s)")
    return 0


def _rule(args, repo: Path) -> int:
    from langatlas_commit.land import Landed, land_record

    from langatlas_research.consolidate.dedup import candidates, drop_alias, make_ruling
    from langatlas_research.consolidate.migration import draft_manifest, write_draft
    from langatlas_research.consolidate.record import add_ruling, load_record, save_record
    from langatlas_research.cycle import load_cycle, require_sign_off
    from langatlas_research.land import store_validator

    cycle = load_cycle(args.number, repo_root=repo)
    require_sign_off(cycle, repo_root=repo)
    record = load_record(cycle.slug, repo_root=repo)
    candidate = next((c for c in candidates(repo, cycle=cycle) if c["key"] == args.key), None)
    if candidate is None:
        print(f"error: {args.key} is not a current candidate of {cycle.slug}", file=sys.stderr)
        return 1
    if args.distinct:
        ruling = make_ruling(candidate, disposition="distinct", reason=args.reason)
    elif args.merge_into:
        if args.merge_into not in candidate["nodes"]:
            print(f"error: {args.merge_into} is not one of {candidate['nodes']}", file=sys.stderr)
            return 1
        other = next(node for node in candidate["nodes"] if node != args.merge_into)
        manifest = draft_manifest(repo, {"op": "merge", "from": [other], "to": args.merge_into},
                                  cycle=cycle, date=_dt.date.today().isoformat(),
                                  rationale=args.reason, slug=f"merge-{other}")
        path = write_draft(repo, manifest)
        ruling = make_ruling(candidate, disposition="merge", reason=args.reason,
                             migration=manifest["migration_id"], node=args.merge_into)
        print(f"drafted {path.relative_to(repo)}; land it with `langatlas-research consolidate"
              f" migrate {cycle.number} {manifest['migration_id']}`")
    else:
        if not args.node:
            print("error: --drop-alias needs --node (the feature losing the alias)",
                  file=sys.stderr)
            return 1
        if args.node not in candidate["nodes"]:
            print(f"error: {args.node} is not one of {candidate['nodes']}", file=sys.stderr)
            return 1
        rel, text = drop_alias(repo, args.node, args.drop_alias)
        outcome = land_record(repo, rel, text, chat_run_id=f"r6-developer-{cycle.slug}",
                              validator=store_validator)
        if not isinstance(outcome, Landed):
            print(f"error: {rel} did not land: {outcome!r}", file=sys.stderr)
            return 1
        ruling = make_ruling(candidate, disposition="drop-alias", reason=args.reason,
                             node=args.node, alias=args.drop_alias)
    save_record(add_ruling(record, ruling), repo_root=repo)
    print(f"ruled {args.key}: {ruling['disposition']}")
    return 0


def _slugs(args, repo: Path) -> int:
    from langatlas_research.consolidate.slugs import slug_candidates
    from langatlas_research.cycle import load_cycle, require_sign_off

    require_sign_off(load_cycle(args.number, repo_root=repo), repo_root=repo)
    found = slug_candidates(repo)
    for candidate in found:
        print(f"{candidate['node']:40} {candidate['slug']:40} -> {candidate['suggested']:40}"
              f" {', '.join(candidate['signals'])}")
    print(f"{len(found)} candidate(s)")
    return 0


def _rename_slug(args, repo: Path) -> int:
    from langatlas_commit.land import Landed, land_changeset

    from langatlas_research.consolidate.slugs import rename_slug
    from langatlas_research.cycle import load_cycle, require_sign_off
    from langatlas_research.land import store_validator

    cycle = load_cycle(args.number, repo_root=repo)
    require_sign_off(cycle, repo_root=repo)
    changes = rename_slug(repo, args.node, args.new_slug)
    outcome = land_changeset(repo, changes, message=f"rename slug of {args.node} to"
                             f" {args.new_slug}", chat_run_id=f"r6-developer-{cycle.slug}",
                             validator=store_validator)
    print(f"{args.node}: slug {args.new_slug}: {outcome!r}")
    return 0 if isinstance(outcome, Landed) else 1


def _settle(args, repo: Path) -> int:
    from langatlas_research.consolidate.lifecycle import settle

    cycle, results = settle(args.number, repo_root=repo, by=args.by or "",
                            date=args.date or _dt.date.today().isoformat())
    for result in results:
        print(repr(result))
    print(f"cycle {cycle.slug} -> {cycle.status}")
    if cycle.status == "settled":
        print("next: uv run --package langatlas-coverage langatlas-coverage dossier")
    return 0 if cycle.status == "settled" else 1


_HANDLERS = {"open": _open, "edges": _edges, "status": _status, "settle": _settle,
             "draft-migration": _draft_migration, "migrate": _migrate, "guard": _guard, "dedup": _dedup, "rule": _rule,
             "slugs": _slugs, "rename-slug": _rename_slug}


def dispatch(args, root: Path | None) -> int:
    """An unknown cycle is a typed CLI error, not a FileNotFoundError traceback."""
    try:
        return _HANDLERS[args.consolidate_command](args, root or REPO_ROOT)
    except FileNotFoundError as exc:
        raise ResearchError(str(exc)) from exc
