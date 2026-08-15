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
        snapshots.fetch_url(args.source_id, args.url, locator_kinds=kinds)
    elif args.file:
        snapshots.put(args.source_id, Path(args.file), media_type=args.media_type,
                      locator_kinds=kinds)
    with connect(config.dsn) as conn:
        try:
            result = ingest_source(args.source_id, conn=conn, config=config,
                                   snapshots=snapshots, locator_kinds=kinds)
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
            hits = SourceSearch(conn, ctx, config=config, rerank=rerank).search(
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
            result = run_eval(conn, ctx, config=config, rerank=rerank)
    print(result.to_markdown())
    return 0


def build_parser() -> argparse.ArgumentParser:
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
    search.set_defaults(func=_cmd_search)

    evaluate = sub.add_parser("eval", help="score the retrieval golden set")
    evaluate.add_argument("--no-rerank", action="store_true",
                          help="score the no-rerank arm of §8.6's comparison")
    evaluate.set_defaults(func=_cmd_eval)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
