import hashlib
from langatlas_ingest.verify.entailment import EntailmentOut, is_inconsistent

# Section 7.1's roster, as defaults. `config.verification_aliases` is the runtime
# authority; these exist so a caller with no config still gets the ratified ladder.
PRIMARY_ALIAS = "deepseek"
ESCALATION_ALIAS = "deepseek-thinking"
SECOND_OPINION_ALIAS = "mini"

DEFAULT_SECOND_OPINION_RATE = 0.10

# Section 6.2: escalate on `partial`/`contradicted` — the two verdicts with consequences
# (a bounce, a contradiction record) that a reasoning pass can talk out of a mistake.
ESCALATING_VERDICTS = frozenset({"partial", "contradicted"})

_UINT32 = 2 ** 32


def needs_escalation(verdict: str, out: EntailmentOut, *, has_since: bool) -> bool:
    """Whether this pair should be re-run on the reasoning model (~5-15% of pairs)."""
    return verdict in ESCALATING_VERDICTS or is_inconsistent(out, has_since=has_since)


def sampled_for_second_opinion(fact_id: str, source_id: str, locator: str, *,
                               rate: float = DEFAULT_SECOND_OPINION_RATE) -> bool:
    """Deterministic sampling for Section 6.2's cross-family second opinion.

    Hash-based rather than random so a re-run of the same batch samples the same pairs:
    a drift gauge whose membership changes every night measures the sampler, not drift.

    @param rate - 0.0 disables the gauge; 1.0 is the mandatory-second-vote hardening

    @returns True when this pair is in the sample
    """
    if rate <= 0.0:
        return False
    if rate >= 1.0:
        return True
    digest = hashlib.sha256(f"{fact_id}|{source_id}|{locator}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / _UINT32 < rate
