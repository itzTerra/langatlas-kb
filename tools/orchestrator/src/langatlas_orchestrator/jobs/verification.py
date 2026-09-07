"""D24's nightly verification batch (context/spec.md Section 6.2), driven through the
generic orchestrator loop.

One work item per fact, because the fact is what an admissibility decision is *about* —
its citations are verified as independent pairs inside the item, and a mid-fact crash
resumes by re-verifying that one fact rather than a whole night's batch.

Stage 2 makes this run; Stage 5 gives it volume (D25's ~200-facts/night budget is already
in `config/jobs/nightly-verification.yaml`)."""
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from langatlas_commit.land import BlockedRedMain, ContentionExhausted, Landed, land_record
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import connect
from langatlas_ingest.store import SourcingQueue
from langatlas_ingest.verify.admissibility import decide_fact
from langatlas_ingest.verify.batch import (
    BatchResult, load_canary_ids, run_canaries, verify_batch,
)
from langatlas_ingest.verify.job_support import work_for_fact
from langatlas_ingest.verify.ledger import VerdictLedger
from langatlas_ingest.verify.pipeline import VerifyDeps
from langatlas_validate.compile import derive_facts
from langatlas_validate.store import iter_store_records, validate_contradictions

from langatlas_orchestrator.registry import ItemOutcome, register_job_kind

CONTRADICTIONS_RECORD = "contradictions.yaml"


def _derived_facts(repo_root: Path) -> list[dict]:
    return derive_facts(list(iter_store_records(repo_root)))


@dataclass
class _RunState:
    """What one driver invocation computes once and every item reuses.

    The registry's contract is two functions (enumerate, run one item) with no run-scoped
    object between them, so the run's shared work lives here instead: deriving the whole
    store per item — to find a single fact by id — costs a full store walk 200 times a
    night, and re-running the canary preflight per item costs a full provider pass over
    every canary 200 times a night. Both are per-*run* work by design (Section 6.2's
    canaries are a batch preflight); this is where "the run" is representable at all."""

    repo_root: Path
    facts: dict[str, dict]
    canaries_run_for: set[str] = field(default_factory=set)
    canary_halt: BatchResult | None = None

    @classmethod
    def build(cls, repo_root: Path) -> "_RunState":
        return cls(repo_root=repo_root,
                   facts={fact["fact_id"]: fact for fact in _derived_facts(repo_root)})


# Replaced by every `_enumerate` call, i.e. once per driver invocation.
_state: _RunState | None = None


def _state_for(repo_root: Path) -> _RunState:
    """The current run's state, rebuilt if this process has none for `repo_root` — a
    resumed run always enumerates first, so the rebuild is a safety net (and the path a
    test that calls `_run_item` directly takes), not the normal case."""
    global _state
    if _state is None or _state.repo_root != repo_root:
        _state = _RunState.build(repo_root)
    return _state


def _enumerate(extra: dict, repo_root: Path) -> list[str]:
    """Every fact that has at least one citation to verify.

    A fact with no `sources:` has nothing for the gate to read; enumerating it would burn
    a checkpoint row every night and never reach a verdict."""
    global _state
    _state = _RunState.build(repo_root)
    wanted = set(extra.get("fact_ids") or ())
    return [fact_id for fact_id, fact in _state.facts.items()
            if fact.get("sources") and (not wanted or fact_id in wanted)]


def _canary_preflight(ctx, conn, *, config, deps, state) -> BatchResult | None:
    """Section 6.2's known-bad questions, asked **once per run** before the first fact.

    Task 15 designed these as a per-batch preflight. Task 17 made each fact its own batch,
    which would run every canary through the whole pipeline — real provider calls — once
    per fact. The guard below restores the per-run cost the design intended.

    @returns None to proceed, or the halted `BatchResult` every item of this run inherits
    """
    run_id = getattr(ctx, "run_id", None) or ""
    if run_id in state.canaries_run_for:
        return state.canary_halt
    canary_ids = load_canary_ids()
    passed = run_canaries(ctx, conn, config=config, deps=deps, canary_ids=canary_ids)
    state.canaries_run_for.add(run_id)
    if passed:
        state.canary_halt = BatchResult(
            halted=True, canaries_run=len(canary_ids),
            halt_reason=f"canaries passed: {', '.join(passed)}")
        ctx.writer.append(role="assistant", content=state.canary_halt.to_markdown(),
                          flags=["verification:halted"])
    return state.canary_halt


def _verify_fact(ctx, item_key: str, repo_root: Path, config: IngestConfig,
                 state: _RunState):
    """Look up one fact by id and verify its citations, deciding its admissibility.

    @returns (BatchResult | None, FactOutcome | None) — both None when the store changed
        between enumeration and this item and `item_key` no longer names a fact; result
        is non-None with outcome None only when a canary halted the run
    """
    fact = state.facts.get(item_key)
    if fact is None:
        return None, None

    with connect(config.dsn) as conn, VerdictLedger() as ledger:
        deps = VerifyDeps.build(conn, ctx, config=config, ledger=ledger)
        queue = SourcingQueue(conn)
        halt = _canary_preflight(ctx, conn, config=config, deps=deps, state=state)
        if halt is not None:
            return halt, None
        result = verify_batch(ctx, conn, work_for_fact(fact), config=config, deps=deps,
                              queue=queue, canary_ids=[])
        # `deps.source_facts` is what `VerifyDeps.build` just loaded — calling
        # `load_source_facts()` again here would re-parse every `sources/*.yaml` a second
        # time for this one fact.
        outcome = decide_fact(fact["fact_id"], result.verdicts, deps.source_facts,
                              has_since=bool(fact.get("since")),
                              absent=fact.get("status") == "absent", queue=queue,
                              bounce_budget=config.bounce_budget,
                              contradictions_path=repo_root / CONTRADICTIONS_RECORD,
                              chat_run_id=getattr(ctx, "run_id", None))
    return result, outcome


def _land_contradictions(ctx, repo_root: Path) -> tuple[ItemOutcome | None, str]:
    """Commit the contradiction register `decide_fact` just rewrote.

    D1: a canonical file the pipeline mutates and never commits is not in the database —
    it is an unattended run's dirty working tree. `land_record` is idempotent on
    (path, content), so a run whose later facts mint nothing new re-lands nothing.

    @returns (an outcome that must be returned instead of this item's own, or None; a
        detail fragment describing the landing)
    """
    path = repo_root / CONTRADICTIONS_RECORD
    if not path.exists():
        return None, ""
    try:
        result = land_record(repo_root, CONTRADICTIONS_RECORD, path.read_text(),
                             chat_run_id=getattr(ctx, "run_id", None) or "",
                             validator=lambda worktree: validate_contradictions(worktree))
    except subprocess.CalledProcessError as exc:
        # `land_record` shells out with check=True; the reachable case is a commit of a
        # file git sees as unchanged (the register already carries these records, but
        # history lost the trailer that would have proved it). A human should look at the
        # register rather than have the run keep re-trying it every night.
        return ItemOutcome(status="halted",
                           detail=f"{CONTRADICTIONS_RECORD} could not be committed:"
                                  f" {exc}"), ""
    if isinstance(result, Landed):
        return None, f"register landed as {result.commit_sha}"
    # Mirrors exit_test.py's mapping: the re-attemptable `LandResult` variants become the
    # driver's re-attemptable statuses, everything else needs a human.
    if isinstance(result, BlockedRedMain):
        return ItemOutcome(status="blocked", detail=f"main is red: {result!r}"), ""
    if isinstance(result, ContentionExhausted):
        return ItemOutcome(status="contention",
                           detail=f"contention exhausted: {result!r}"), ""
    return ItemOutcome(status="halted",
                       detail=f"{CONTRADICTIONS_RECORD} did not land: {result!r}"), ""


def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
    config = IngestConfig.load()
    state = _state_for(repo_root)
    try:
        result, outcome = _verify_fact(ctx, item_key, repo_root, config, state)
    except psycopg.OperationalError as exc:
        # An unreachable database is an infrastructure condition, not a verdict about
        # this fact: `blocked` pauses the run for a later retry, which is exactly what
        # the driver's `blocked` means everywhere else (see exit_test.py).
        return ItemOutcome(status="blocked", detail=f"database unavailable: {exc}")

    if result is None:
        # The store changed between enumeration and this item. Not an error worth a
        # human: the next run enumerates the store as it now is.
        return ItemOutcome(status="done", detail=f"{item_key} no longer in the store")

    if result.halted:
        # The only genuine halt here: a canary answered `supported`, so nothing this
        # verifier says tonight is trustworthy.
        return ItemOutcome(status="halted", detail=result.halt_reason)

    detail = f"{outcome.verification}, confidence {outcome.confidence}"
    if outcome.contradiction_ids:
        landed, note = _land_contradictions(ctx, repo_root)
        if landed is not None:
            return landed
        detail += f", minted {', '.join(outcome.contradiction_ids)}"
        if note:
            detail += f" ({note})"

    if outcome.admissible:
        return ItemOutcome(status="done", record_key=item_key, detail=detail)
    # A fact that fails admissibility has still *completed* its verification: the claim
    # was checked and the consequence recorded (a bounce filed to the sourcing queue, or
    # a spent budget a human now owns). That is `done` with the outcome in `detail` —
    # never `blocked`/`halted`, either of which would stop the entire night's run on the
    # first fact whose citation did not check out, which is the normal case this gate
    # exists to produce.
    if outcome.exhausted:
        detail += f"; bounce budget exhausted, awaiting a human: {outcome.bounce_reason}"
    elif outcome.bounced:
        detail += f"; bounced for resubmission: {outcome.bounce_reason}"
    elif outcome.bounce_reason:
        detail += f"; {outcome.bounce_reason}"
    return ItemOutcome(status="done", detail=detail)


register_job_kind("nightly-verification", _enumerate, _run_item)
