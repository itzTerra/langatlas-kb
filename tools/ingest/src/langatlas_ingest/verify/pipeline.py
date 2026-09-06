from dataclasses import dataclass
from datetime import date as _date
from typing import Any
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.verify.absence import run_absence
from langatlas_ingest.verify.adjudication import adjudicate_quote
from langatlas_ingest.verify.entailment import (
    PROMPT_ID as ENTAILMENT_PROMPT_ID, fold_assertions, run_entailment,
)
from langatlas_ingest.verify.evidence import resolve_evidence
from langatlas_ingest.verify.inputs import CitationInput, ClaimInput, whitelist_payload
from langatlas_ingest.verify.quotes import (
    QuoteCheck, check_quote, find_quote_in_source, quote_within_cap, since_token_present,
)
from langatlas_ingest.verify.stage0 import run_stage0
from langatlas_ingest.verify.tiering import needs_escalation, sampled_for_second_opinion
from langatlas_ingest.verify.verdicts import Assertion, PairVerdict
from langatlas_pipeline.prompts import load_prompt


@dataclass
class VerifyDeps:
    """Everything `verify_pair` reaches the outside world through.

    Bundled and injectable so the composition — which is where the stage-ordering bugs
    live — is testable without Postgres, without a provider, and without the golden set."""

    source_facts: dict
    index: Any = None
    store: Any = None
    search: Any = None
    ledger: Any = None

    @classmethod
    def build(cls, conn, ctx, *, config: IngestConfig, ledger=None) -> "VerifyDeps":
        from langatlas_ingest.index import PostgresSourceChunksIndex
        from langatlas_ingest.search import SourceSearch
        from langatlas_ingest.store import SourceChunksStore
        from langatlas_ingest.verify.sources import load_source_facts

        return cls(source_facts=load_source_facts(),
                   index=PostgresSourceChunksIndex(conn), store=SourceChunksStore(conn),
                   search=SourceSearch(conn, ctx, config=config), ledger=ledger)


def _assertions(out) -> tuple[Assertion, ...]:
    return tuple(Assertion(kind=a.kind, text=a.text, status=a.status,
                           grounding_span=a.grounding_span) for a in out.assertions)


def _terminal(claim: ClaimInput, citation: CitationInput, verdict: str, *, detail: str,
              ctx, anchor, annotations=(), evidence_chunk_ids=(), hint="") -> PairVerdict:
    return PairVerdict(fact_id=claim.fact_id, source_id=citation.source_id,
                       locator=citation.locator, verdict=verdict, detail=detail,
                       annotations=tuple(annotations),
                       evidence_chunk_ids=tuple(evidence_chunk_ids), hint=hint,
                       run_id=getattr(ctx, "run_id", None), anchor=anchor,
                       date=_date.today().isoformat())


@dataclass(frozen=True)
class _Stage3Run:
    """One stage-3 call's full outcome, so every caller (primary, escalation, second
    opinion) updates `model`/`prompt_version` together with `out`/`verdict` — the
    fields that went stale independently is exactly Findings 1 and 2's bug."""

    out: object
    model: str
    verdict: str
    prompt_version: str
    grep_chunk_ids: tuple[str, ...] | None = None


def _run_stage3(ctx, conn, *, claim: ClaimInput, citation: CitationInput, evidence,
                alias: str, store, grep_chunk_ids) -> _Stage3Run:
    """Section 6.2's stage 3, dispatched on `claim.status` exactly like the primary
    pass: an `absent` claim is *always* judged by D49's inverted-framing prompt
    (`run_absence`), on every call this pair makes, primary or escalated or
    second-opinion -- never by `run_entailment`'s presence-framed prompt, which asks
    the wrong question of an absence claim.

    @returns a `_Stage3Run` carrying exactly what changed: which model answered, what
        verdict it folded to, and which prompt drove that verdict.
    """
    if claim.status == "absent":
        result = run_absence(ctx, conn, claim=claim, citation=citation, evidence=evidence,
                             alias=alias, store=store, grep_chunk_ids=grep_chunk_ids)
        return _Stage3Run(out=result.out, model=result.model, verdict=result.verdict,
                          prompt_version=load_prompt("verify-absence").version,
                          grep_chunk_ids=result.grep_chunk_ids)
    payload = whitelist_payload(claim, citation)
    out, model = run_entailment(ctx, payload=payload, evidence_text=evidence.text,
                                source_id=citation.source_id, alias=alias)
    return _Stage3Run(out=out, model=model, verdict=fold_assertions(out.assertions),
                      prompt_version=load_prompt(ENTAILMENT_PROMPT_ID).version)


def verify_pair(ctx, conn, *, claim: ClaimInput, citation: CitationInput,
                config: IngestConfig | None = None, deps: VerifyDeps | None = None,
                queue=None, anchor: str | None = None,
                grep_chunk_ids=None) -> PairVerdict:
    """Run Section 6.2's four stages over one (claim, citation) pair.

    Increasingly expensive filters, not one LLM call: stage 0 costs nothing, stage 1 costs
    one indexed query, stage 2 costs a string comparison (and, in a narrow band, one small
    completion), and only stage 3 costs a real entailment call. A pair that fails an early
    stage never reaches a later one.

    @param deps - injected collaborators; None builds them from `conn`/`ctx`
    @param queue - a `SourcingQueue`; used only to park un-ingested citations
    @param anchor - "<run_id>#msg-N" for this pair's exchange in the batch transcript
    @param grep_chunk_ids - pre-computed D49 grep hits; None lets `run_absence` do it

    @returns the pair's verdict, fully provenance-stamped for the ledger
    """
    config = config or IngestConfig.load()
    deps = deps or VerifyDeps.build(conn, ctx, config=config)
    primary, escalation, second_opinion = config.verification_aliases
    today = _date.today().isoformat()

    # ---- stage 0: schema + referential checks -----------------------------------
    stage0 = run_stage0(claim, citation, deps.source_facts)
    if not stage0.ok:
        verdict = _terminal(claim, citation, stage0.verdict, detail=stage0.detail,
                            ctx=ctx, anchor=anchor)
        return _finish(verdict, deps)

    if not quote_within_cap(citation.quote):
        # D14 binds the verifier's inputs too. Rejecting here rather than truncating: a
        # citation that broke the cap is not a citation we want to normalize into one.
        verdict = _terminal(claim, citation, "unsupported",
                            detail="citation exceeds D14's 50-word quote cap", ctx=ctx,
                            anchor=anchor)
        return _finish(verdict, deps)

    # ---- stage 1: evidence resolution -------------------------------------------
    if deps.store.ingestion(citation.source_id) is None:
        if queue is not None:
            queue.file(kind="pending-source", source_id=citation.source_id,
                       reason="not-ingested",
                       detail=f"{claim.fact_id} cites an un-ingested source")
        verdict = _terminal(claim, citation, "source-unavailable",
                            detail="source is not ingested; claim parked in the sourcing"
                                   " queue", ctx=ctx, anchor=anchor)
        return _finish(verdict, deps)

    evidence = resolve_evidence(conn, ctx, source_id=citation.source_id,
                               locator=citation.locator, claim_text=claim.claim,
                               config=config, index=deps.index, store=deps.store,
                               search=deps.search)
    if not evidence.resolved:
        # The rescue is a hint, never a pass: a strong hit far from the claimed locator
        # is still `locator-not-found`.
        verdict = _terminal(claim, citation, "locator-not-found",
                            detail="the locator resolves to no chunk", ctx=ctx,
                            anchor=anchor, hint=evidence.hint)
        return _finish(verdict, deps)

    # ---- stage 2: quote fast path -----------------------------------------------
    annotations: list[str] = []
    if citation.quote:
        quote_check = check_quote(citation.quote, evidence.text)
        if quote_check.status == "adjudicate":
            outcome = adjudicate_quote(ctx, quote=citation.quote,
                                       evidence_text=evidence.text,
                                       source_id=citation.source_id,
                                       ratio=quote_check.ratio, alias=primary)
            if outcome.outcome != "ocr-noise":
                # The adjudicator called it a fabrication, so the near-miss becomes a
                # miss and falls into the whole-source search below like any other.
                quote_check = QuoteCheck("mismatch", quote_check.ratio,
                                         annotation="quote-mismatch")
        if quote_check.status == "mismatch":
            elsewhere = find_quote_in_source(deps.store.by_source(citation.source_id),
                                             citation.quote,
                                             exclude=evidence.chunk_ids)
            if elsewhere.status == "found-elsewhere":
                # A real quote at the wrong locator is a locator error, not a
                # fabrication: annotate, keep going, let the locator be auto-corrected.
                annotations.append("quote-found-elsewhere")
            else:
                verdict = _terminal(claim, citation, "unsupported",
                                    detail=f"quote does not appear in this source"
                                           f" (best ratio {elsewhere.ratio:.2f})",
                                    ctx=ctx, anchor=anchor,
                                    annotations=("quote-mismatch",),
                                    evidence_chunk_ids=evidence.chunk_ids)
                return _finish(verdict, deps)

    since_hint = "" if since_token_present(claim.since, evidence.text) else \
        f"the version {claim.since!r} does not appear in the cited text"

    # ---- stage 3: entailment (a matched quote NEVER waives it) -------------------
    has_since = bool(claim.since)
    primary_run = _run_stage3(ctx, conn, claim=claim, citation=citation, evidence=evidence,
                              alias=primary, store=deps.store,
                              grep_chunk_ids=grep_chunk_ids)
    out, model, verdict_name, prompt_version = (
        primary_run.out, primary_run.model, primary_run.verdict, primary_run.prompt_version)
    evidence_chunk_ids = tuple(evidence.chunk_ids)
    if primary_run.grep_chunk_ids is not None:
        evidence_chunk_ids += primary_run.grep_chunk_ids
        # D49's negative grep is expensive (a corpus-wide query); reuse the primary
        # pass's hits for any escalation/second-opinion re-run of the same pair rather
        # than re-running it once per call.
        grep_chunk_ids = primary_run.grep_chunk_ids

    detail_parts = [p for p in (since_hint, evidence.hint) if p]

    if needs_escalation(verdict_name, out, has_since=has_since):
        escalated = _run_stage3(ctx, conn, claim=claim, citation=citation,
                                evidence=evidence, alias=escalation, store=deps.store,
                                grep_chunk_ids=grep_chunk_ids)
        out, model, verdict_name, prompt_version = (
            escalated.out, escalated.model, escalated.verdict, escalated.prompt_version)
        detail_parts.append(f"escalated to {escalation}")
    elif verdict_name == "supported" and sampled_for_second_opinion(
            claim.fact_id, citation.source_id, citation.locator,
            rate=config.second_opinion_rate):
        second = _run_stage3(ctx, conn, claim=claim, citation=citation, evidence=evidence,
                             alias=second_opinion, store=deps.store,
                             grep_chunk_ids=grep_chunk_ids)
        if second.verdict != verdict_name:
            detail_parts.append(
                f"second-opinion-disagreement: {second_opinion} said {second.verdict}")
            if config.mandatory_second_opinion:
                # The hardening path: the gauge becomes a vote, and the more
                # conservative of the two answers wins -- model/prompt_version travel
                # with it, so the ledger row stays re-derivable to the call that
                # actually produced the recorded verdict.
                out, model, verdict_name, prompt_version = (
                    second.out, second.model, second.verdict, second.prompt_version)

    verdict = PairVerdict(
        fact_id=claim.fact_id, source_id=citation.source_id, locator=citation.locator,
        verdict=verdict_name, per_assertion=_assertions(out),
        annotations=tuple(annotations), since_status=out.since_status, model=model,
        prompt_version=prompt_version, run_id=getattr(ctx, "run_id", None), anchor=anchor,
        date=today, evidence_chunk_ids=evidence_chunk_ids, hint=evidence.hint,
        detail="; ".join(detail_parts))
    return _finish(verdict, deps)


def _finish(verdict: PairVerdict, deps: VerifyDeps) -> PairVerdict:
    if deps.ledger is not None:
        deps.ledger.record(verdict)
    return verdict
