# tools/ingest/src/langatlas_ingest/cli.py
import argparse
from langatlas_ingest import __version__
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import connect, migrate


def _cmd_db(args) -> int:
    with connect(IngestConfig.load().dsn) as conn:
        applied = migrate(conn)
    print("\n".join(applied) if applied else "schema already up to date")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="langatlas-sources")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    db = sub.add_parser("db", help="apply pending db/*.sql migrations")
    db.set_defaults(func=_cmd_db)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
