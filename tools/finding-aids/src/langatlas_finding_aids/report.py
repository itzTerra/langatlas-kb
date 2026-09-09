"""D53's CLI: `checklist` for R3 batch surveys, `lookup` for ad hoc queries,
`mirror-refresh` for a manual refresh between monthly job runs.

Every subcommand opens its own `RunContext`, because every one of them may reach an
external service and D18 logs from day one — there is no unlogged path in this package."""
import argparse
import sys

from langatlas_pipeline.providers.core import RunContext

from langatlas_finding_aids.checklist import build_checklist, write_checklist
from langatlas_finding_aids.config import FindingAidsConfig
from langatlas_finding_aids.query import render_for_prompt, search_finding_aids


def _run_context(slug: str):
    """Indirection so the CLI tests can substitute a fake without minting a transcript."""
    return RunContext.start(kind="finding-aids", slug=slug)


def _cmd_checklist(args) -> int:
    config = FindingAidsConfig.load()
    ctx = _run_context(f"checklist-{args.theme}")
    try:
        checklist = build_checklist(ctx, args.theme, config=config)
        md, js = write_checklist(checklist, out_dir=args.out)
    finally:
        ctx.close()
    gaps = sum(1 for row in checklist.rows if not row.covered_by)
    print(f"{md}\n{js}\n{len(checklist.rows)} rows, {gaps} gaps")
    return 0


def _cmd_lookup(args) -> int:
    ctx = _run_context("lookup")
    try:
        results = search_finding_aids(ctx, args.query, sources=args.sources or None,
                                      limit=args.limit)
        print(render_for_prompt(ctx, results) or "no leads")
    finally:
        ctx.close()
    return 0


def _cmd_mirror_refresh(args) -> int:
    from langatlas_finding_aids.mirror import refresh

    from langatlas_finding_aids.config import MIRRORED_SOURCES

    ctx = _run_context("mirror-refresh")
    try:
        for source in (args.source and [args.source]) or list(MIRRORED_SOURCES):
            state = refresh(source, ctx)
            print(f"{state.source}: {state.version} ({state.item_count} items)")
    finally:
        ctx.close()
    return 0


def _cmd_mint_identification(args) -> int:
    from langatlas_finding_aids.identification import mint_identification_source

    ctx = _run_context("mint-identification")
    try:
        results = search_finding_aids(ctx, args.query, sources=[args.source], limit=1)
    finally:
        ctx.close()
    if not results:
        print(f"no {args.source} result for {args.query!r}")
        return 1
    path = mint_identification_source(results[0], args.field)
    print(f"{path}\nreview and commit it; the value itself belongs on the language"
          " registry record, not in a gated fact")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="langatlas-finding-aids",
        description="PLDB/Wikidata/Hyperpolyglot/Wikipedia leads. Never citations (D29).")
    sub = parser.add_subparsers(dest="command", required=True)

    checklist = sub.add_parser("checklist",
                               help="build an R3 batch-survey coverage checklist")
    checklist.add_argument("--theme", required=True)
    checklist.add_argument("--out", default=None,
                           help="output directory (default: the private tier)")
    checklist.set_defaults(func=_cmd_checklist)

    lookup = sub.add_parser("lookup", help="ad hoc finding-aid query")
    lookup.add_argument("query")
    lookup.add_argument("--sources", nargs="*", default=None)
    lookup.add_argument("--limit", type=int, default=10)
    lookup.set_defaults(func=_cmd_lookup)

    refresh = sub.add_parser("mirror-refresh", help="refresh the PLDB/Hyperpolyglot mirrors")
    refresh.add_argument("--source", default=None)
    refresh.set_defaults(func=_cmd_mirror_refresh)

    mint = sub.add_parser("mint-identification",
                          help="mint a tier-D attribution citation for one identification"
                               " metadata point (D29's carve-out)")
    mint.add_argument("query")
    mint.add_argument("--source", required=True)
    mint.add_argument("--field", required=True,
                      help="file-extension | first-appeared")
    mint.set_defaults(func=_cmd_mint_identification)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
