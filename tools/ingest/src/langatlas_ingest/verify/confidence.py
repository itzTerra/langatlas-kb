from langatlas_ingest.verify.sources import are_independent
from langatlas_ingest.verify.verdicts import ADMISSIBLE_TIERS, ADMITTING_VERDICTS

# Ordinal, never numeric (Section 6.3), but comparable so D49's absence cap can be applied
# as a ceiling rather than as a second branch of the lookup.
_RANK = {"low": 0, "medium": 1, "high": 2}
_BY_RANK = {rank: level for level, rank in _RANK.items()}


def derive_confidence(verification: str, pairs, source_facts: dict, *,
                      absent: bool = False) -> str | None:
    """Section 6.3's confidence lookup — derived, never hand-edited, never numeric.

    | Level | Rule (first match) |
    |---|---|
    | high | verified; >=1 tier-A/B fully supports; >=1 additional *independent* corroborator (any tier) |
    | medium | verified; exactly one tier-A/B source, uncorroborated — or tier-C sole backing with >=1 independent corroboration |
    | low | verified; tier-C sole backing uncorroborated — or partially-verified at any tier |
    | (none) | unverified/failed facts, and tier-D-only backing, which never establishes verification |

    @param verification - the fold table's output
    @param pairs - every `PairVerdict` for this fact
    @param source_facts - source_id -> SourceFacts
    @param absent - the claim is `status: absent`; D49 caps single-source absence at medium

    @returns "high" | "medium" | "low", or None when no confidence value applies
    """
    if verification in ("unverified", "failed"):
        return None
    if verification == "partially-verified":
        return "low"

    supporting = {pair.source_id for pair in pairs if pair.verdict in ADMITTING_VERDICTS}
    known = {source_id for source_id in supporting if source_id in source_facts}
    admissible = {s for s in known if source_facts[s].tier in ADMISSIBLE_TIERS}
    tier_c = {s for s in known if source_facts[s].tier == "C"}

    if admissible:
        backing = admissible
    elif tier_c:
        # Tier-C sole backing: still verified (it reached the fold table), but the
        # corroboration rule shifts down one level.
        backing = tier_c
    else:
        # Community/tier-D sources can lift a level but never establish verification.
        return None

    corroborated = any(are_independent(source_facts[primary], source_facts[other])
                       for primary in backing for other in known if other != primary)
    if admissible:
        level = "high" if corroborated else "medium"
    else:
        level = "medium" if corroborated else "low"

    if absent and len(known) == 1:
        # D49: a single source cannot establish more than `medium` for an absence claim —
        # one book being silent is weaker evidence than one book being explicit.
        level = _BY_RANK[min(_RANK[level], _RANK["medium"])]
    return level
