import argparse
import json
import sys
from pathlib import Path
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import connect
from langatlas_ingest.paths import GOLDEN_CANARIES_PATH
from langatlas_ingest.verify.batch import load_canary_ids, verify_batch
from langatlas_ingest.verify.inputs import CitationInput, ClaimInput
from langatlas_ingest.verify.ledger import VerdictLedger
from langatlas_ingest.verify.pipeline import VerifyDeps, verify_pair
from langatlas_pipeline.providers.core import RunContext


def _cmd_pair(args) -> int:
    config = IngestConfig.load()
    claim = ClaimInput(fact_id=args.fact_id, claim=args.claim, since=args.since,
                       status=args.status, absence_scope=args.absence_scope,
                       feature_aliases=tuple(args.alias or ()))
    citation = CitationInput(args.source_id, args.locator, args.quote)
    with connect(config.dsn) as conn, \
            RunContext.start(kind="verification", slug="pair") as ctx, \
            VerdictLedger() as ledger:
        deps = VerifyDeps.build(conn, ctx, config=config, ledger=ledger)
        verdict = verify_pair(ctx, conn, claim=claim, citation=citation, config=config,
                              deps=deps)
    print(json.dumps(verdict.as_dict(), indent=2, sort_keys=True))
    return 0


def _cmd_ledger(args) -> int:
    with VerdictLedger() as ledger:
        verdicts = ledger.latest_for(args.fact_id) if args.latest \
            else ledger.all_for(args.fact_id)
    print(json.dumps([v.as_dict() for v in verdicts], indent=2, sort_keys=True))
    return 0


def _cmd_canaries(args) -> int:
    """`--check` is the CI-safe half: it needs no database and no provider, and only
    asserts that every canary id still names a committed golden item."""
    from langatlas_ingest.goldens.loader import load_verifier_items

    canary_ids = load_canary_ids(Path(args.path) if args.path else GOLDEN_CANARIES_PATH)
    known = {item.id for item in load_verifier_items()}
    missing = [item_id for item_id in canary_ids if item_id not in known]
    for item_id in missing:
        print(f"CANARY {item_id}: not in the committed golden set")
    print(f"{len(canary_ids)} canaries, {len(missing)} missing")
    return 1 if missing else 0


def _cmd_batch(args) -> int:
    from langatlas_ingest.store import SourcingQueue
    from langatlas_validate.compile import derive_facts
    from langatlas_validate.paths import REPO_ROOT
    from langatlas_validate.store import iter_store_records
    from langatlas_ingest.verify.job_support import work_for_fact

    config = IngestConfig.load()
    facts = derive_facts(list(iter_store_records(REPO_ROOT)))
    if args.fact_id:
        facts = [f for f in facts if f["fact_id"] in set(args.fact_id)]
    work = [pair for fact in facts for pair in work_for_fact(fact)]
    with connect(config.dsn) as conn, \
            RunContext.start(kind="verification", slug=args.slug) as ctx, \
            VerdictLedger() as ledger:
        deps = VerifyDeps.build(conn, ctx, config=config, ledger=ledger)
        result = verify_batch(ctx, conn, work, config=config, deps=deps,
                              queue=SourcingQueue(conn))
    print(result.to_markdown())
    return 1 if result.halted else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="langatlas-verify",
                                     description="D24's verification gate")
    sub = parser.add_subparsers(dest="command", required=True)

    pair = sub.add_parser("pair", help="verify one (claim, citation) pair")
    pair.add_argument("--fact-id", required=True)
    pair.add_argument("--claim", required=True)
    pair.add_argument("--source-id", required=True)
    pair.add_argument("--locator", required=True)
    pair.add_argument("--quote")
    pair.add_argument("--since")
    pair.add_argument("--status")
    pair.add_argument("--absence-scope")
    pair.add_argument("--alias", action="append", help="feature alias (repeatable, D49)")
    pair.set_defaults(func=_cmd_pair)

    batch = sub.add_parser("batch", help="verify the store's facts in one batch")
    batch.add_argument("--fact-id", action="append")
    batch.add_argument("--slug", default="manual")
    batch.set_defaults(func=_cmd_batch)

    canaries = sub.add_parser("canaries", help="inspect the known-bad canary list")
    canaries.add_argument("--check", action="store_true",
                          help="only verify the ids exist (no DB, no provider)")
    canaries.add_argument("--path")
    canaries.set_defaults(func=_cmd_canaries)

    ledger = sub.add_parser("ledger", help="read the private verdict ledger")
    ledger.add_argument("fact_id")
    ledger.add_argument("--latest", action="store_true")
    ledger.set_defaults(func=_cmd_ledger)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
