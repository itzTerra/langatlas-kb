# tools/ingest/src/langatlas_ingest/cli.py
import argparse
from pathlib import Path
from langatlas_ingest import __version__
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import connect, migrate
from langatlas_ingest.snapshot import SnapshotStore


def _cmd_db(args) -> int:
    with connect(IngestConfig.load().dsn) as conn:
        applied = migrate(conn)
    print("\n".join(applied) if applied else "schema already up to date")
    return 0


def _cmd_ingest(args) -> int:
    from langatlas_ingest.errors import QaHardGate
    from langatlas_ingest.pipeline import ingest_source

    config = IngestConfig.load()
    snapshots = SnapshotStore()
    # The flag rides along to the snapshot so a first ingest stores the source's locator
    # preference; without a flag, an existing snapshot's stored value is carried forward.
    kinds = args.locator_kinds or None
    if args.url:
        snapshots.fetch_url(args.source_id, args.url, locator_kinds=kinds,
                            min_chars=args.min_chars)
    elif args.file:
        snapshots.put(args.source_id, Path(args.file), media_type=args.media_type,
                      locator_kinds=kinds, min_chars=args.min_chars)
    with connect(config.dsn) as conn:
        try:
            result = ingest_source(args.source_id, conn=conn, config=config,
                                   snapshots=snapshots, locator_kinds=kinds,
                                   min_chars=args.min_chars)
        except QaHardGate as gate:
            report = snapshots.dir_for(args.source_id) / "qa" / "report.md"
            print(f"QA hard gate: {gate}\nreport: {report}")
            return 2
    state = " (unchanged, skipped)" if result.skipped else ""
    print(f"{result.source_id}: {result.chunk_count} chunks, QA {result.qa_status}{state}\n"
          f"report: {result.qa_report_path}")
    return 0


def _cmd_reingest(args) -> int:
    """D1's regeneration path: drop the database, `db`, then this. Every stored snapshot
    is re-ingested with its own stored `locator_kinds`, so the regenerated locators match
    the published ones."""
    from langatlas_ingest.errors import IngestError
    from langatlas_ingest.pipeline import reingest_all

    config = IngestConfig.load()
    with connect(config.dsn) as conn:
        results = reingest_all(conn=conn, config=config, snapshots=SnapshotStore())
    failed = 0
    for source_id, result in results.items():
        if isinstance(result, IngestError):
            failed += 1
            print(f"{source_id}: FAILED: {result}")
        elif result.skipped:
            print(f"{source_id}: unchanged, skipped ({result.chunk_count} chunks)")
        else:
            print(f"{source_id}: {result.chunk_count} chunks, QA {result.qa_status}")
    if not results:
        print("no stored snapshots")
    return 2 if failed else 0


def _cmd_qa(args) -> int:
    path = SnapshotStore().dir_for(args.source_id) / "qa" / "report.md"
    if not path.exists():
        print(f"no QA report for {args.source_id}; run `langatlas-sources ingest` first")
        return 1
    print(path.read_text())
    return 0


def _cmd_queue(args) -> int:
    from langatlas_ingest.store import SourcingQueue

    with connect(IngestConfig.load().dsn) as conn:
        entries = SourcingQueue(conn).open_entries(kind=args.kind)
    for entry in entries:
        # D37's 14-day alarm and 2-bounce budget, surfaced where the developer looks.
        alarm = "  [OVER 14 DAYS]" if entry["age_days"] > 14 else ""
        print(f"{entry['id']:>5}  {entry['kind']:<14} {entry['source_id']:<28}"
              f" {entry['reason']:<20} bounces={entry['bounce_count']}"
              f" age={entry['age_days']}d{alarm}")
    if not entries:
        print("queue empty")
    return 0


def _cmd_embed(args) -> int:
    from langatlas_pipeline.providers.core import RunContext
    from langatlas_ingest.embed import embed_source

    config = IngestConfig.load()
    with RunContext.start(kind="ingest", slug=args.source_id or "corpus") as ctx:
        with connect(config.dsn) as conn:
            written = embed_source(ctx, conn, source_id=args.source_id, config=config,
                                   batch_size=args.batch_size)
    print(f"embedded {written} chunks on {config.embedding_model}")
    return 0


def _cmd_search(args) -> int:
    from langatlas_pipeline.providers.core import RunContext
    from langatlas_ingest.search import SourceSearch

    config = IngestConfig.load()
    # `False if --no-rerank else None`, not `not args.no_rerank`: the flag is an opt-out,
    # so its absence must leave the decision to `models.rerank_default_on` rather than
    # silently forcing the reranker on for a config that turned it off.
    rerank = False if args.no_rerank else None
    with RunContext.start(kind="search", slug="cli") as ctx:
        with connect(config.dsn) as conn:
            hits = SourceSearch(conn, ctx, config=config, rerank=rerank,
                                mode=args.mode).search(
                args.query, k=args.k, source_ids=args.source or None)
    for hit in hits:
        print(f"[{hit.score:.4f}] {hit.chunk.source_id} {hit.chunk.locator}"
              f"  {hit.chunk.breadcrumb}")
        print(f"    {hit.chunk.text[:200].replace(chr(10), ' ')}")
    if not hits:
        print("no hits")
    return 0


def _cmd_eval(args) -> int:
    from langatlas_pipeline.providers.core import RunContext
    from langatlas_ingest.eval import run_eval

    config = IngestConfig.load()
    # Same opt-out shape as `search` — absent, the config decides (§8.6's comparison runs
    # the harness twice, once with the flag).
    rerank = False if args.no_rerank else None
    with RunContext.start(kind="eval", slug="retrieval") as ctx:
        with connect(config.dsn) as conn:
            result = run_eval(conn, ctx, config=config, rerank=rerank,
                              depth=args.depth, mode=args.mode)
    print(result.to_markdown())
    return 0


def _cmd_golden_validate(args) -> int:
    from langatlas_ingest.goldens.loader import (
        load_controversy_cases, load_verifier_items, validate_controversy_cases,
        validate_items, validate_set,
    )
    from langatlas_ingest.paths import (
        GOLDEN_CONTROVERSY_DIR, GOLDEN_VERIFIER_DIR, GOLDEN_VERIFIER_HELD_OUT_DIR,
    )
    from langatlas_validate.paths import REPO_ROOT

    verifier_dir = Path(args.verifier_dir or GOLDEN_VERIFIER_DIR)
    # The source-existence check needs the real `sources/` tree; a test pointing
    # `--verifier-dir` at a tmp dir is checking shape, not the committed corpus.
    sources_dir = REPO_ROOT / "sources" if args.verifier_dir is None else None
    items = load_verifier_items(verifier_dir)
    held_out = load_verifier_items(verifier_dir, include_held_out=True)
    held_out = [item for item in held_out if item.held_out]
    errors = validate_items(items + held_out, sources_dir=sources_dir)

    controversy_dir = Path(args.controversy_dir or GOLDEN_CONTROVERSY_DIR)
    cases = load_controversy_cases(controversy_dir) if controversy_dir.is_dir() else []
    errors += validate_controversy_cases(cases)

    if args.resolve:
        errors += _resolve_golden_locators(items + held_out)
    if args.complete:
        errors += validate_set(items, held_out)

    print(f"verifier items: {len(items)} (+{len(held_out)} held out),"
          f" controversy cases: {len(cases)}, {len(errors)} errors")
    for error in errors:
        print(f"  {error}")
    return 1 if errors else 0


def _resolve_golden_locators(items) -> list[str]:
    """Check every item's locator and evidence chunk ids against the live corpus. Needs
    Postgres, so it is opt-in (`--resolve`) and never runs in CI."""
    from langatlas_ingest.index import PostgresSourceChunksIndex
    from langatlas_ingest.store import SourceChunksStore

    errors = []
    with connect(IngestConfig.load().dsn) as conn:
        index, store = PostgresSourceChunksIndex(conn), SourceChunksStore(conn)
        for item in items:
            for chunk_id in item.evidence_chunk_ids:
                if store.get(chunk_id) is None:
                    errors.append(f"{item.id}: evidence chunk {chunk_id!r} is not in"
                                  " source_chunks")
            resolved = index.resolve(item.citation.source, item.citation.locator)
            expects_resolution = item.stratum != "fabricated-locator"
            if expects_resolution and not resolved:
                errors.append(f"{item.id}: locator {item.citation.locator!r} resolves to"
                              " no chunk — golden locators are copied from real rows")
            if not expects_resolution and resolved:
                errors.append(f"{item.id}: stratum 'fabricated-locator' but the locator"
                              " resolves; it is not fabricated")
    return errors


def _cmd_golden_score(args) -> int:
    import json
    from datetime import datetime, timezone
    from langatlas_ingest.goldens.loader import load_controversy_cases, load_verifier_items
    from langatlas_ingest.goldens.runner import (
        load_entry_point, run_controversy_goldens, run_verifier_goldens,
    )
    from langatlas_ingest.paths import GOLDEN_CONTROVERSY_DIR, GOLDEN_VERIFIER_DIR

    config = IngestConfig.load()
    dotted = args.verifier or config.verifier_entry_point
    assessor_dotted = args.controversy_assessor or config.controversy_assessor_entry_point
    if not dotted and not assessor_dotted:
        print("no verifier registered — set `goldens.verifier_entry_point` in"
              " config/ingest.yaml (2D ships it) or pass --verifier")
        return 3

    code = 0
    if dotted:
        items = load_verifier_items(Path(args.verifier_dir or GOLDEN_VERIFIER_DIR),
                                    include_held_out=args.include_held_out)
        score = run_verifier_goldens(items, load_entry_point(dotted),
                                     thresholds=config.golden_thresholds)
        print(score.to_markdown())
        if args.json:
            payload = json.loads(score.to_json())
            payload["generated"] = datetime.now(timezone.utc).isoformat()
            payload["verifier_entry_point"] = dotted
            Path(args.json).write_text(json.dumps(payload, indent=2, sort_keys=True))
        code = 0 if score.thresholds_met else 2
    if assessor_dotted:
        cases = load_controversy_cases(Path(args.controversy_dir
                                            or GOLDEN_CONTROVERSY_DIR))
        print(run_controversy_goldens(cases,
                                      load_entry_point(assessor_dotted)).to_markdown())
    return code


def _cmd_golden_candidates(args) -> int:
    from langatlas_ingest.goldens.authoring import (
        generate_candidates, write_candidate_file,
    )
    from langatlas_pipeline.providers.core import RunContext

    config = IngestConfig.load()
    with connect(config.dsn) as conn, \
            RunContext.start(kind="golden-candidates", slug=args.source_id) as ctx:
        candidates = generate_candidates(ctx, conn, source_id=args.source_id,
                                         stratum=args.stratum, count=args.count,
                                         topic=args.topic, config=config)
    path = write_candidate_file(candidates, Path(args.out))
    print(f"{len(candidates)} candidates -> {path}\n"
          "review every one, then set `curated: true` and move it into"
          " tests/golden/verifier/")
    return 0


def _cmd_golden_derive_queries(args) -> int:
    from langatlas_ingest.goldens.derive import derive_queries, write_queries
    from langatlas_ingest.goldens.loader import load_verifier_items

    queries = derive_queries(load_verifier_items(), band=args.band, limit=args.limit)
    path = write_queries(queries, Path(args.out), theme=args.theme)
    print(f"{len(queries)} queries -> {path}")
    return 0


def _cmd_golden_staleness(args) -> int:
    from langatlas_ingest.goldens.loader import load_verifier_items
    from langatlas_ingest.goldens.staleness import check_staleness

    items = load_verifier_items(include_held_out=True)
    with connect(IngestConfig.load().dsn) as conn:
        stale = check_staleness(conn, items)
    print(f"{len(stale)} of {len(items)} golden items have stale grounding")
    for entry in stale:
        print(f"  {entry.item_id}: {entry.reason}")
    # Always 0: Section 6.4 makes staleness enforcement on golden items soft/log-only.
    return 0


def _cmd_new_source(args) -> int:
    from langatlas_ingest.paths import REPO_ROOT
    from langatlas_ingest.scaffold import render_source_yaml

    author = None
    if args.author:
        author = [{"family": part.split(",")[0].strip(),
                   "given": part.split(",", 1)[1].strip() if "," in part else ""}
                  for part in args.author]
    issued = {"date-parts": [[args.issued_year]]} if args.issued_year else None
    canonical = True if args.canonical else (False if args.no_canonical else None)
    text = render_source_yaml(
        args.id, args.type, args.title, author=author, issued=issued, url=args.url,
        doi=args.doi, tier=args.tier, grounding=args.grounding, canonical_source=canonical,
        acquisition_note=args.acquisition_note, edition=args.edition,
        edition_check_url=args.edition_check_url, locator_kinds=args.locator_kinds or None)
    out_dir = Path(args.out_dir) if args.out_dir else REPO_ROOT / "sources"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{args.id}.yaml"
    if target.exists():
        print(f"{target} already exists; refusing to overwrite")
        return 1
    target.write_text(text)
    print(f"wrote {target}")
    return 0


def _cmd_file_acquisitions(args) -> int:
    from ruamel.yaml import YAML
    from langatlas_ingest.db import connect
    from langatlas_ingest.paths import REPO_ROOT
    from langatlas_ingest.store import SourcingQueue

    manifest = Path(args.file) if args.file else REPO_ROOT / "config" / "acquisitions.yaml"
    entries = YAML(typ="safe").load(manifest.read_text()) or []
    config = IngestConfig.load()
    with connect(config.dsn) as conn:
        queue = SourcingQueue(conn)
        for entry in entries:
            target = REPO_ROOT / "sources" / f"{entry['source_id']}.yaml"
            if target.exists():
                print(f"skipped {entry['source_id']}: sources/{entry['source_id']}.yaml already exists")
                continue
            entry_id = queue.file(kind="pending-source", source_id=entry["source_id"],
                                  reason=entry["reason"], detail=entry.get("detail", ""))
            print(f"filed #{entry_id}: {entry['source_id']} ({entry['reason']})")
    return 0


def _cmd_bench_pilot(args) -> int:
    from langatlas_ingest.benchmark.arms import load_matrix
    from langatlas_ingest.benchmark.pilot import select_pilot
    from langatlas_ingest.eval import load_entries

    matrix = load_matrix()
    selection = select_pilot(load_entries(matrix.golden_dir), size=args.size)
    print(selection.to_markdown())
    if tuple(matrix.pilot_sources) != selection.sources:
        print("NOTE: config/benchmark/d22-source-corpus.yaml pins a different pilot"
              f" ({', '.join(matrix.pilot_sources)}). The golden set has changed since"
              " the pilot was ratified — re-run the arms or re-ratify the pilot.")
        return 1
    return 0


def _cmd_bench_build(args) -> int:
    import psycopg
    from dataclasses import replace
    from langatlas_ingest.benchmark.arms import load_matrix
    from langatlas_ingest.benchmark.corpus import (
        build_bench_corpus, check_parity, create_bench_db,
    )
    from langatlas_ingest.errors import BenchCorpusMismatch

    config, matrix = IngestConfig.load(), load_matrix()
    target, maximum = args.chunk_target, args.chunk_max
    arm_config = replace(config, chunk_target_tokens=target, chunk_max_tokens=maximum)
    dsn = create_bench_db(config.dsn, drop=args.drop)
    with psycopg.connect(dsn, autocommit=True) as bench:
        counts = build_bench_corpus(bench, sources=matrix.pilot_sources,
                                    config=arm_config)
        for source_id, count in counts.items():
            print(f"{source_id}: {count} chunks")
        # Parity is only meaningful at production's chunking; the secondary axis is
        # *supposed* to produce different ids, which is why Task 9 exists.
        if (target, maximum) == matrix.primary_chunk_size:
            with psycopg.connect(config.dsn, autocommit=True) as prod:
                differences = check_parity(bench, prod, matrix.pilot_sources)
            if differences:
                raise BenchCorpusMismatch(differences)
            print("parity with production: OK")
    return 0


def _cmd_bench_run(args) -> int:
    import psycopg
    from langatlas_ingest.benchmark.arms import load_matrix
    from langatlas_ingest.benchmark.corpus import bench_dsn
    from langatlas_ingest.benchmark.report import matrix_markdown
    from langatlas_ingest.benchmark.runner import load_results, run_matrix

    config, matrix = IngestConfig.load(), load_matrix()
    if args.chunk_size_for:
        candidates = matrix.chunk_size_arms(args.chunk_size_for, truncate=args.truncate)
        if args.chunk_target is None or args.chunk_max is None:
            raise SystemExit(
                "--chunk-size-for needs --chunk-target and --chunk-max naming the arm"
                " whose chunk size matches the bench corpus you just built with"
                " bench-build — matrix.chunk_size_arms() returns every secondary chunk"
                " size at once, and running them all in one call would silently score"
                " an arm against a corpus chunked at a different size than its own"
                " label claims. Available: "
                + ", ".join(f"{a.chunk_target_tokens}/{a.chunk_max_tokens}"
                            for a in candidates))
        arms = [arm for arm in candidates
                if (arm.chunk_target_tokens, arm.chunk_max_tokens)
                == (args.chunk_target, args.chunk_max)]
        if not arms:
            raise SystemExit(
                f"no chunk-size arm for {args.chunk_size_for} matches"
                f" {args.chunk_target}/{args.chunk_max}. Available: "
                + ", ".join(f"{a.chunk_target_tokens}/{a.chunk_max_tokens}"
                            for a in candidates))
        span = True
    else:
        arms = [arm for arm in matrix.primary
                if not args.arm or arm.arm_id in args.arm]
        span = False
    with psycopg.connect(bench_dsn(config.dsn), autocommit=True) as bench, \
            psycopg.connect(config.dsn, autocommit=True) as prod:
        run_matrix(bench, arms, matrix=matrix, config=config, prod_conn=prod,
                   resume=not args.force, span_relevance=span)
    print(matrix_markdown(load_results(matrix.results_dir), matrix=matrix))
    return 0


def _cmd_bench_verdict(args) -> int:
    from langatlas_ingest.benchmark.arms import load_matrix
    from langatlas_ingest.benchmark.report import pin_config, write_verdict
    from langatlas_ingest.benchmark.runner import load_results
    from langatlas_ingest.benchmark.verdict import decide
    from langatlas_ingest.paths import BENCHMARK_DIR, INGEST_CONFIG_PATH

    matrix = load_matrix()
    results = load_results(matrix.results_dir)
    verdict = decide(results, matrix=matrix)
    print(verdict.to_markdown())
    json_path, md_path = write_verdict(verdict, results, matrix=matrix,
                                       root=BENCHMARK_DIR)
    print(f"wrote {json_path} and {md_path}")
    if args.write:
        changed = pin_config(verdict, config_path=INGEST_CONFIG_PATH)
        for line in changed or ["config/ingest.yaml already matches the verdict"]:
            print(line)
        if changed and verdict.model != matrix.incumbent:
            print("\nThe model moved: the production corpus must be fully re-embedded"
                  " before this configuration is used.\n"
                  "  uv --directory tools/ingest run langatlas-sources embed")
        if any(line.startswith("chunking.") for line in changed):
            print("\nThe chunking moved: this is more destructive than a model move —"
                  " every chunk id the golden set and the production index depend on"
                  " changes. Before this configuration is used:\n"
                  "  1. re-ingest the whole corpus (re-chunks every source):\n"
                  "     uv --directory tools/ingest run langatlas-sources reingest\n"
                  "  2. only then re-embed it:\n"
                  "     uv --directory tools/ingest run langatlas-sources embed\n"
                  "  3. re-derive every golden-set `expected_chunks` entry against the"
                  " new chunking — the old chunk ids no longer exist.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    from langatlas_ingest.search import SEARCH_MODES

    parser = argparse.ArgumentParser(prog="langatlas-sources")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    db = sub.add_parser("db", help="apply pending db/*.sql migrations")
    db.set_defaults(func=_cmd_db)

    ingest = sub.add_parser("ingest", help="snapshot -> extract -> chunk -> QA -> promote")
    ingest.add_argument("source_id")
    ingest.add_argument("--file", help="path to an original to store as the snapshot first")
    ingest.add_argument("--url", help="fetch and archive a URL as the snapshot first")
    ingest.add_argument("--media-type", default="application/pdf")
    ingest.add_argument("--locator-kinds", nargs="*", default=[],
                        help="preference order; stored on the snapshot and reused by"
                             " later runs. Omit to reuse the stored order (or"
                             " DEFAULT_LOCATOR_KINDS for a source that never had one)")
    ingest.add_argument("--min-chars", type=int, default=None,
                        help="extraction-collapse floor for the QA hard gate, for a"
                             " legitimately tiny source (a one-page errata note, a short"
                             " RFC). Stored on the snapshot and reused by later runs;"
                             " omit to reuse the stored value (or QA's own default)")
    ingest.set_defaults(func=_cmd_ingest)

    reingest = sub.add_parser("reingest",
                              help="re-ingest every stored snapshot (D1: regenerate the"
                                   " database), each with its own stored locator kinds")
    reingest.set_defaults(func=_cmd_reingest)

    qa = sub.add_parser("qa", help="print a stored extraction-QA report")
    qa.add_argument("source_id")
    qa.set_defaults(func=_cmd_qa)

    queue = sub.add_parser("queue", help="list open sourcing-queue entries")
    queue.add_argument("--kind", choices=["pending-source", "link-checker", "edition-check"])
    queue.set_defaults(func=_cmd_queue)

    embed = sub.add_parser("embed", help="batch-embed unembedded chunks through RunContext")
    embed.add_argument("source_id", nargs="?", default=None,
                       help="omit to embed every unembedded chunk in the corpus")
    embed.add_argument("--batch-size", type=int, default=32)
    embed.set_defaults(func=_cmd_embed)

    search = sub.add_parser("search", help="hybrid search over source_chunks (pipeline-only)")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=None)
    search.add_argument("--source", nargs="*", default=[])
    search.add_argument("--no-rerank", action="store_true")
    search.add_argument("--mode", choices=list(SEARCH_MODES), default=None,
                        help="override `retrieval.mode`; the §8.6 variant axis")
    search.set_defaults(func=_cmd_search)

    evaluate = sub.add_parser("eval", help="score the retrieval golden set")
    evaluate.add_argument("--no-rerank", action="store_true",
                          help="score the no-rerank arm of §8.6's comparison")
    evaluate.add_argument("--depth", type=int, default=10,
                          help="hits requested per query; 50 measures §8.6's pre-rerank"
                               " pool (run it with --no-rerank)")
    evaluate.add_argument("--mode", choices=list(SEARCH_MODES), default=None,
                          help="override `retrieval.mode`")
    evaluate.set_defaults(func=_cmd_eval)

    golden_validate = sub.add_parser(
        "golden-validate", help="shape-check the committed golden sets (no DB, no provider)")
    golden_validate.add_argument("--verifier-dir")
    golden_validate.add_argument("--controversy-dir")
    golden_validate.add_argument("--resolve", action="store_true",
                                 help="also resolve locators against Postgres")
    golden_validate.add_argument("--complete", action="store_true",
                                 help="also enforce the §6.4 set-level invariants")
    golden_validate.set_defaults(func=_cmd_golden_validate)

    golden_score = sub.add_parser(
        "golden-score", help="score a verifier against the golden set (never a CI gate)")
    golden_score.add_argument("--verifier", help="module:attr entry point")
    golden_score.add_argument("--controversy-assessor", help="module:attr entry point")
    golden_score.add_argument("--verifier-dir")
    golden_score.add_argument("--controversy-dir")
    golden_score.add_argument("--include-held-out", action="store_true",
                              help="run the audit slice — once, at the end, never to tune")
    golden_score.add_argument("--json", help="write the machine-readable error rates here")
    golden_score.set_defaults(func=_cmd_golden_score)

    derive = sub.add_parser("golden-derive-queries",
                            help="derive retrieval queries from correct-stratum items")
    derive.add_argument("--theme", required=True)
    derive.add_argument("--band", default="exact-term")
    derive.add_argument("--limit", type=int)
    derive.add_argument("--out", required=True)
    derive.set_defaults(func=_cmd_golden_derive_queries)

    staleness = sub.add_parser("golden-staleness",
                               help="report golden items whose grounding moved (log-only)")
    staleness.set_defaults(func=_cmd_golden_staleness)

    candidates = sub.add_parser(
        "golden-candidates", help="draft golden-item candidates (volume only; you curate)")
    candidates.add_argument("--source-id", required=True)
    candidates.add_argument("--stratum", required=True)
    candidates.add_argument("--count", type=int, default=5)
    candidates.add_argument("--topic", help="seed retrieval instead of random sampling")
    candidates.add_argument("--out", required=True)
    candidates.set_defaults(func=_cmd_golden_candidates)

    new_source = sub.add_parser("new-source",
                                help="scaffold a schema-valid sources/<id>.yaml record")
    new_source.add_argument("id")
    new_source.add_argument("type", help="CSL-JSON type, e.g. book | article-journal | report")
    new_source.add_argument("title")
    new_source.add_argument("--author", nargs="*", default=[],
                            help="'Family, Given' per author, e.g. 'Van Roy, Peter'")
    new_source.add_argument("--issued-year", type=int, default=None)
    new_source.add_argument("--url", default=None)
    new_source.add_argument("--doi", default=None)
    new_source.add_argument("--tier", required=True, choices=["A", "B", "C", "D"])
    new_source.add_argument("--grounding", required=True,
                            choices=["formal-spec", "reference-implementation-docs",
                                    "design-doc", "third-party-reference"])
    canon_group = new_source.add_mutually_exclusive_group()
    canon_group.add_argument("--canonical", action="store_true")
    canon_group.add_argument("--no-canonical", action="store_true")
    new_source.add_argument("--acquisition-note", default=None)
    new_source.add_argument("--edition", default=None)
    new_source.add_argument("--edition-check-url", default=None)
    new_source.add_argument("--locator-kinds", nargs="*", default=[])
    new_source.add_argument("--out-dir", default=None)
    new_source.set_defaults(func=_cmd_new_source)

    file_acq = sub.add_parser("file-acquisitions",
                              help="file config/acquisitions.yaml's entries into sourcing_queue")
    file_acq.add_argument("--file", default=None)
    file_acq.set_defaults(func=_cmd_file_acquisitions)

    bench_pilot = sub.add_parser("bench-pilot",
                                 help="select the D22 pilot corpus by golden coverage")
    bench_pilot.add_argument("--size", type=int, default=4)
    bench_pilot.set_defaults(func=_cmd_bench_pilot)

    bench_build = sub.add_parser("bench-build",
                                 help="build the isolated benchmark corpus at one"
                                      " chunk size")
    bench_build.add_argument("--chunk-target", type=int, default=600)
    bench_build.add_argument("--chunk-max", type=int, default=800)
    bench_build.add_argument("--drop", action="store_true",
                             help="recreate the benchmark database first (required when"
                                  " changing chunk size)")
    bench_build.set_defaults(func=_cmd_bench_build)

    bench_run = sub.add_parser("bench-run", help="run the D22 arms (resumable)")
    bench_run.add_argument("--arm", nargs="*", default=[],
                           help="run only these arm ids; omit for the whole matrix")
    bench_run.add_argument("--chunk-size-for", default=None,
                           help="run §8.6's secondary chunk-size axis for this model"
                                " instead of the primary matrix")
    bench_run.add_argument("--chunk-target", type=int, default=None,
                           help="with --chunk-size-for: run only the arm whose target"
                                " token count matches this and the currently-built bench"
                                " corpus's chunk size — required whenever"
                                " --chunk-size-for is used, since matrix.chunk_size_arms()"
                                " otherwise returns every secondary chunk size at once,"
                                " which would score arms other than the one actually"
                                " built against the current bench corpus")
    bench_run.add_argument("--chunk-max", type=int, default=None,
                           help="with --chunk-size-for: paired with --chunk-target,"
                                " must match the max token count of the arm to run")
    bench_run.add_argument("--truncate", action="store_true",
                           help="with --chunk-size-for: the chosen model is a"
                                " short-context candidate")
    bench_run.add_argument("--force", action="store_true",
                           help="re-run arms that already have a committed result")
    bench_run.set_defaults(func=_cmd_bench_run)

    bench_verdict = sub.add_parser("bench-verdict",
                                   help="apply §8.6's decision rules and record the"
                                        " verdict")
    bench_verdict.add_argument("--write", action="store_true",
                               help="also pin the verdict into config/ingest.yaml")
    bench_verdict.set_defaults(func=_cmd_bench_verdict)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
