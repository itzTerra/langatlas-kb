from dataclasses import dataclass
from pathlib import Path
from langatlas_ingest.verify.confidence import derive_confidence
from langatlas_ingest.verify.contradictions import mint_verification_record
from langatlas_ingest.verify.verdicts import (ADMISSIBLE_TIERS, ADMITTING_VERDICTS,
                                              fold_verification)

# Which verdicts are worth a retry with a narrowed claim, and what to tell the proposer.
_BOUNCE_REASONS = {
    "partial": "every citation tops out at `partial`; narrow the claim to what the cited"
               " text actually supports and resubmit",
    "unsupported": "no citation supports the claim; find a source that states it, or"
                   " withdraw it",
    "contradicted": "the cited text contradicts the claim; the claim is wrong as written",
    "locator-not-found": "no citation resolves to a passage; correct the locators",
    "source-unavailable": "no cited source is ingested",
}
# Worst-first, so the bounce message names the most informative failure rather than
# whichever pair happened to be last.
_BOUNCE_PRIORITY = ("contradicted", "unsupported", "partial", "locator-not-found",
                    "source-unavailable")


@dataclass(frozen=True)
class FactOutcome:
    """What the gate decided about one fact, and what it did about it."""

    fact_id: str
    admissible: bool
    verification: str
    confidence: str | None
    bounced: bool = False
    bounce_reason: str = ""
    contradiction_ids: tuple[str, ...] = ()
    exhausted: bool = False


def _bounce(queue, fact_id: str, pairs, budget: int) -> tuple[bool, str, bool]:
    present = {p.verdict for p in pairs}
    verdict = next((v for v in _BOUNCE_PRIORITY if v in present), None)
    if verdict is None:
        return False, "", False
    reason = _BOUNCE_REASONS[verdict]
    if queue is None:
        return False, reason, False

    source_id = next(p.source_id for p in pairs if p.verdict == verdict)
    # `sourcing_queue.bounce_count` already models the budget (Section 4.4); reusing it
    # keeps one counter rather than inventing a second one that could disagree.
    existing = next((entry for entry in queue.open_entries(kind="pending-source")
                     if entry.get("source_id") == source_id), None)
    if existing is None:
        queue.file(kind="pending-source", source_id=source_id,
                   reason="partially-ingested", detail=f"{fact_id}: {reason}")
        return True, reason, False
    if existing.get("bounce_count", 0) >= budget:
        # Budget exhausted: the entry stays visibly open rather than being bounced
        # forever. A human decides what happens next.
        return False, reason, True
    queue.bounce(existing["id"])
    return True, reason, False


def decide_fact(fact_id: str, pairs, source_facts: dict, *, has_since: bool = False,
                absent: bool = False, queue=None, bounce_budget: int = 2,
                contradictions_path: Path | None = None,
                chat_run_id: str | None = None) -> FactOutcome:
    """Apply Section 6.2's admissibility rule and Section 6.5's minting rule to one fact.

    Admissible iff **>=1 citation is `supported` from a tier-A/B source**. C/D corroborate
    only. `partial`-only facts bounce once for claim narrowing (2-bounce budget);
    `unsupported`/`contradicted` never enter and bounce with a rationale.

    @param pairs - every `PairVerdict` for this fact (the latest per citation)
    @param queue - a `SourcingQueue`; None skips queue side effects (tests, dry runs)
    @param contradictions_path - None uses the repo's `contradictions.yaml`

    @returns the decision, including any contradiction ids this call is responsible for
    """
    pairs = list(pairs)
    verification = fold_verification(
        pairs, tier_of=lambda s: source_facts[s].tier if s in source_facts else "",
        has_since=has_since)
    admissible = any(p.verdict in ADMITTING_VERDICTS
                     and source_facts.get(p.source_id)
                     and source_facts[p.source_id].tier in ADMISSIBLE_TIERS
                     for p in pairs)
    confidence = derive_confidence(verification, pairs, source_facts, absent=absent)

    contradiction_ids = tuple(mint_verification_record(
        pairs, fact_id=fact_id, has_admissible_alternative=admissible,
        path=contradictions_path, chat_run_id=chat_run_id))

    bounced = exhausted = False
    reason = ""
    if pairs and not admissible:
        bounced, reason, exhausted = _bounce(queue, fact_id, pairs, bounce_budget)

    return FactOutcome(fact_id=fact_id, admissible=admissible, verification=verification,
                       confidence=confidence, bounced=bounced, bounce_reason=reason,
                       contradiction_ids=contradiction_ids, exhausted=exhausted)
