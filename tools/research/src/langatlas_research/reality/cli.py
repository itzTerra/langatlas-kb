"""`langatlas-research reality …` — R5's steps, in the order a cycle runs them:

    compile -> classify -> verify -> finalize

`status` and `shakedown` are offline and can run at any point. Every provider step opens its own
`RunContext` (D18). There is no `mint`: R5 mints nothing (D68)."""
import subprocess
import sys
from pathlib import Path

from langatlas_research.reality.record import SHAKEDOWN_COMPONENTS

_GATED = ("compile", "classify", "verify", "finalize", "shakedown")


def add_parser(sub) -> None:
    reality = sub.add_parser("reality", help="R5 reality checks (Stage 3E)").add_subparsers(
        dest="reality_command", required=True)
    p_compile = reality.add_parser(
        "compile", help="compile and land the questionnaire; open the cycle's reality check")
    p_compile.add_argument("number", type=int)
    p_compile.add_argument("--restart", action="store_true",
                           help="discard an in-progress reality check and start again")
    p_classify = reality.add_parser(
        "classify", help="run the reality checker, one session per sampled language")
    p_classify.add_argument("number", type=int)
    p_classify.add_argument("--language", action="append", default=[],
                            help="repeatable; default: every sampled language not yet classified")
    p_classify.add_argument("--redo", action="store_true",
                            help="re-run languages that were already classified")
    for name, help_text in (
            ("verify", "run the D24 gate over every proposed cell"),
            ("status", "print the cells, the findings and the open shakedown entries"),
            ("finalize", "land the reality check and mark the cycle r5-done")):
        reality.add_parser(name, help=help_text).add_argument("number", type=int)
    p_shake = reality.add_parser("shakedown", help="list, add or close shakedown log entries")
    p_shake.add_argument("number", type=int)
    action = p_shake.add_mutually_exclusive_group()
    action.add_argument("--add", metavar="COMPONENT", choices=SHAKEDOWN_COMPONENTS)
    action.add_argument("--close", metavar="KEY")
    p_shake.add_argument("--detail", default=None)
    p_shake.add_argument("--resolution", default=None)


def dispatch(args, root: Path | None) -> int:
    from langatlas_research.cycle import load_cycle, require_sign_off
    from langatlas_research.paths import REPO_ROOT

    repo = Path(root) if root else REPO_ROOT
    cycle = load_cycle(args.number, repo_root=repo)
    command = args.reality_command
    if command in _GATED:
        require_sign_off(cycle, repo_root=repo)
    if command == "status":
        return _status(cycle, repo)
    if command == "shakedown":
        return _shakedown(args, cycle, repo)
    if command == "finalize":
        return _finalize(cycle, repo)
    if command == "compile":
        return _compile(args, cycle, repo)
    return _online(args, cycle, repo)


def _status(cycle, repo: Path) -> int:
    from langatlas_questionnaire.spec import load_spec
    from langatlas_research.reality.findings import refresh
    from langatlas_research.reality.record import load_record, open_shakedown

    record = load_record(cycle.slug, repo_root=repo)
    record = refresh(record, load_spec(repo / record["questionnaire"]))
    for cell in record["cells"]:
        verdict = ((cell.get("verification") or {}).get("exists") or {}).get("verdict", "-")
        print(f"{cell['key']:44} {cell['status']:10} {cell['answer'] or '-':8} {verdict}")
    findings = record["findings"]
    print(f"unmappable: {len(findings['unmappable'])}  uninhabited values:"
          f" {len(findings['uninhabited_values'])}  unfittable: {len(findings['unfittable'])}"
          f"  exclusivity violations: {len(findings['exclusivity_violations'])}")
    for value in findings["uninhabited_values"]:
        print(f"  uninhabited {value['dimension']}={value['value']}")
    for key in findings["unfittable"]:
        print(f"  unfittable {key}")
    for violation in findings["exclusivity_violations"]:
        print(f"  exclusivity {violation['language']} {violation['dimension']}:"
              f" {', '.join(violation['members'])}")
    print(" ".join(f"{key}={value}" for key, value in record["summary"].items()))
    print(f"open shakedown entries: {len(open_shakedown(record))}")
    return 0


def _tracked(repo: Path, rel: str) -> bool:
    result = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=repo,
                            capture_output=True, check=False)
    return result.returncode == 0


def _shakedown(args, cycle, repo: Path) -> int:
    from langatlas_research.reality.record import (
        add_shakedown, close_shakedown, load_record, reality_rel, save_record,
    )

    record = load_record(cycle.slug, repo_root=repo)
    if not args.add and not args.close:
        for entry in record["shakedown"]:
            print(f"{entry['key']:22} {entry['status']:6} {entry['component']:13}"
                  f" {entry['detail']}")
        return 0
    if args.add:
        if not args.detail:
            print("error: --add needs --detail", file=sys.stderr)
            return 1
        record = add_shakedown(record, component=args.add, detail=args.detail)
    else:
        if not args.resolution:
            print("error: --close needs --resolution", file=sys.stderr)
            return 1
        try:
            record = close_shakedown(record, args.close, resolution=args.resolution)
        except (KeyError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    save_record(record, repo_root=repo)
    rel = reality_rel(cycle.slug)
    if not _tracked(repo, rel):
        print("saved; the reality check lands with `reality finalize`")
        return 0
    # A finalized reality check is tracked, and an unlanded edit to a tracked file blocks every
    # other record's rebase — so an edit after finalize lands at once.
    from langatlas_commit.land import Landed, land_record
    from langatlas_pipeline.providers.core import RunContext
    from langatlas_research.land import store_validator

    with RunContext.start(kind="r5-shakedown", slug=cycle.slug) as ctx:
        outcome = land_record(repo, rel, (repo / rel).read_text(), chat_run_id=ctx.run_id,
                              validator=store_validator)
    print(repr(outcome))
    return 0 if isinstance(outcome, Landed) else 1


def _finalize(cycle, repo: Path) -> int:
    from langatlas_research.reality.lifecycle import finalize_r5

    updated, results = finalize_r5(cycle.number, repo_root=repo)
    for result in results:
        print(repr(result))
    print(f"cycle {updated.slug} -> {updated.status}")
    return 0 if updated.status == "r5-done" else 1


def _compile(args, cycle, repo: Path) -> int:
    from langatlas_pipeline.providers.core import RunContext
    from langatlas_research.reality.lifecycle import open_r5

    with RunContext.start(kind="r5-compile", slug=cycle.slug) as ctx:
        record, outcome = open_r5(cycle.number, repo_root=repo, chat_run_id=ctx.run_id,
                                  restart=args.restart)
    print(repr(outcome))
    if record is None:
        return 1
    print(f"{record['questionnaire']}: {len(record['scope']['features'])} feature(s),"
          f" {len(record['scope']['dimensions'])} dimension(s) in scope")
    print(f"next: langatlas-research reality classify {cycle.number}")
    return 0


def _online(args, cycle, repo: Path) -> int:
    """`classify` and `verify`: the two steps that need the corpus database."""
    from langatlas_ingest.config import IngestConfig
    from langatlas_ingest.db import connect
    from langatlas_pipeline.providers.core import RunContext
    from langatlas_research.config import ResearchConfig
    from langatlas_research.paths import research_config_path
    from langatlas_research.reality.record import load_record, save_record

    config = ResearchConfig.load(research_config_path(repo))
    record = load_record(cycle.slug, repo_root=repo)
    with connect(IngestConfig.load().dsn) as conn:
        if args.reality_command == "classify":
            from langatlas_questionnaire.spec import load_spec
            from langatlas_research.draft.ontologist import ontologist_tools
            from langatlas_research.reality.classifier import run_classifier
            from langatlas_research.survey.chunks import db_chunk_lookup
            from langatlas_research.survey.claude import role_budget
            from langatlas_research.taxonomy import REGISTRY_PATH
            from ruamel.yaml import YAML

            spec = load_spec(repo / record["questionnaire"])
            registry = (YAML(typ="safe").load((repo / REGISTRY_PATH).read_text()) or {}).get(
                "languages") or {}
            done = set(record["runs"]["classify"])
            languages = args.language or [language for language in cycle.languages
                                          if args.redo or language not in done]
            if not languages:
                print("every sampled language is classified; pass --redo to re-run one")
                return 0
            lookup = db_chunk_lookup(conn)
            for language in languages:
                # D50's default: a language not (yet) in the registry is general-purpose.
                kind = (registry.get(language) or {}).get("language_kind", "general-purpose")
                with RunContext.start(kind="r5-classify", slug=f"{cycle.slug}-{language}",
                                      budget=role_budget(config.reality.classifier),
                                      agents=[{"role": "reality-checker",
                                               "language": language}]) as ctx:
                    servers, tools = ontologist_tools(ctx, conn)
                    record, warnings = run_classifier(
                        ctx, cycle, record, spec, language=language, language_kind=kind,
                        repo_root=repo, lookup=lookup, config=config, mcp_servers=servers,
                        allowed_tools=tools)
                # Saved per language, so a failure in a later session keeps this one's work.
                save_record(record, repo_root=repo)
                cells = [c for c in record["cells"] if c["language"] == language]
                print(f"{language}: {len(cells)} cell(s),"
                      f" {sum(c['status'] == 'unmappable' for c in cells)} unmappable,"
                      f" {sum(c['status'] == 'unsourced' for c in cells)} unsourced,"
                      f" {len(warnings)} warning(s)")
            print(f"next: langatlas-research reality verify {cycle.number}")
            return 0

        from langatlas_ingest.store import SourcingQueue
        from langatlas_ingest.verify.ledger import VerdictLedger
        from langatlas_ingest.verify.pipeline import VerifyDeps
        from langatlas_research.reality.gate import verify_cells

        # D68: verdicts go to the private ledger, never into authored YAML (D23).
        with VerdictLedger() as ledger, RunContext.start(kind="r5-verify",
                                                          slug=cycle.slug) as ctx:
            deps = VerifyDeps.build(conn, ctx, config=IngestConfig.load(), ledger=ledger)
            record, results = verify_cells(ctx, conn, record, cycle=cycle, repo_root=repo,
                                           config=config, deps=deps, queue=SourcingQueue(conn))
    save_record(record, repo_root=repo)
    for result in results:
        mark = "admitted" if result.per_fact and result.per_fact[0]["admissible"] else "REFUSED "
        print(f"{mark} {result.key:44} {result.pairs} pair(s) {result.detail}")
    print(f"next: langatlas-research reality finalize {cycle.number}")
    return 0
