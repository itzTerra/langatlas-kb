"""D24's nightly verification batch (context/spec.md Section 6.2), driven through the
generic orchestrator loop.

One work item per fact, because the fact is what an admissibility decision is *about* —
its citations are verified as independent pairs inside the item, and a mid-fact crash
resumes by re-verifying that one fact rather than a whole night's batch.

Stage 2 makes this run; Stage 5 gives it volume (D25's ~200-facts/night budget is already
in `config/jobs/nightly-verification.yaml`)."""
from pathlib import Path

from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import connect
from langatlas_ingest.store import SourcingQueue
from langatlas_ingest.verify.admissibility import decide_fact
from langatlas_ingest.verify.batch import verify_batch
from langatlas_ingest.verify.job_support import work_for_fact
from langatlas_ingest.verify.ledger import VerdictLedger
from langatlas_ingest.verify.pipeline import VerifyDeps
from langatlas_ingest.verify.sources import load_source_facts
from langatlas_validate.compile import derive_facts
from langatlas_validate.store import iter_store_records

from langatlas_orchestrator.registry import ItemOutcome, register_job_kind


def _derived_facts(repo_root: Path) -> list[dict]:
    return derive_facts(list(iter_store_records(repo_root)))


def _enumerate(extra: dict, repo_root: Path) -> list[str]:
    """Every fact that has at least one citation to verify.

    A fact with no `sources:` has nothing for the gate to read; enumerating it would burn
    a checkpoint row every night and never reach a verdict."""
    wanted = set(extra.get("fact_ids") or ())
    return [fact["fact_id"] for fact in _derived_facts(repo_root)
            if fact.get("sources") and (not wanted or fact["fact_id"] in wanted)]


def _verify_fact(ctx, item_key: str, repo_root: Path, config: IngestConfig):
    """Look up one fact by id and verify its citations, deciding its admissibility.

    @returns (BatchResult | None, FactOutcome | None) — both None when the store changed
        between enumeration and this item and `item_key` no longer names a fact; result
        is non-None with outcome None only when a canary halted the batch
    """
    fact = next((f for f in _derived_facts(repo_root) if f["fact_id"] == item_key), None)
    if fact is None:
        return None, None

    with connect(config.dsn) as conn, VerdictLedger() as ledger:
        deps = VerifyDeps.build(conn, ctx, config=config, ledger=ledger)
        queue = SourcingQueue(conn)
        result = verify_batch(ctx, conn, work_for_fact(fact), config=config, deps=deps,
                              queue=queue)
        if result.halted:
            return result, None
        outcome = decide_fact(fact["fact_id"], result.verdicts, load_source_facts(),
                              has_since=bool(fact.get("since")),
                              absent=fact.get("status") == "absent", queue=queue,
                              bounce_budget=config.bounce_budget,
                              chat_run_id=getattr(ctx, "run_id", None))
    return result, outcome


def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
    config = IngestConfig.load()
    result, outcome = _verify_fact(ctx, item_key, repo_root, config)
    if result is None:
        # The store changed between enumeration and this item. Not an error worth a
        # human: the next run enumerates the store as it now is.
        return ItemOutcome(status="done", detail=f"{item_key} no longer in the store")

    if result.halted:
        return ItemOutcome(status="halted", detail=result.halt_reason)
    if outcome.admissible:
        detail = f"{outcome.verification}, confidence {outcome.confidence}"
        if outcome.contradiction_ids:
            detail += f", minted {', '.join(outcome.contradiction_ids)}"
        return ItemOutcome(status="done", record_key=item_key, detail=detail)
    if outcome.exhausted:
        # Two bounces spent and still not admissible: a human decides what happens to
        # this claim, so the job stops rather than looping on it nightly.
        return ItemOutcome(status="halted",
                           detail=f"bounce budget exhausted: {outcome.bounce_reason}")
    return ItemOutcome(status="blocked",
                       detail=f"{outcome.verification}: {outcome.bounce_reason}")


register_job_kind("nightly-verification", _enumerate, _run_item)
