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
    if args.url:
        snapshots.fetch_url(args.source_id, args.url)
    elif args.file:
        snapshots.put(args.source_id, Path(args.file), media_type=args.media_type)
    with connect(config.dsn) as conn:
        try:
            result = ingest_source(args.source_id, conn=conn, config=config,
                                   snapshots=snapshots,
                                   locator_kinds=args.locator_kinds or None)
        except QaHardGate as gate:
            report = snapshots.dir_for(args.source_id) / "qa" / "report.md"
            print(f"QA hard gate: {gate}\nreport: {report}")
            return 2
    print(f"{result.source_id}: {result.chunk_count} chunks, QA {result.qa_status}\n"
          f"report: {result.qa_report_path}")
    return 0


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
                        help="preference order; defaults to DEFAULT_LOCATOR_KINDS")
    ingest.set_defaults(func=_cmd_ingest)

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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
