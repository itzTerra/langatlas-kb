from dataclasses import dataclass, field

# Section 6.2's six per-(claim, citation) verdicts, in the spec's order. Frozen: the
# vocabulary is shared with 2B's golden set (`goldens.items.VERDICTS`), the ledger, and
# the site's status rendering — a rename here is a data migration, not a refactor.
VERDICTS = ("source-unavailable", "locator-not-found", "supported", "partial",
            "unsupported", "contradicted")

# Stage-2 annotations, deliberately NOT verdicts.
ANNOTATIONS = ("quote-mismatch", "quote-found-elsewhere")

# Admissibility is ">=1 citation `supported` from a tier-A/B source". `partial` bounces
# for claim narrowing and never admits.
ADMITTING_VERDICTS = frozenset({"supported"})

# The tiers that can establish admissibility (Section 6.2). Public: `confidence.py` and
# `admissibility.py` both read this same set rather than keeping their own copies, so a
# tier-policy change can't drift between the fold table, the confidence lookup, and the gate.
ADMISSIBLE_TIERS = frozenset({"A", "B"})

# Section 6.2's `since` split: the source supports the exact origin, or only bounds it
# from above. The second is a legitimate `partial` and lands in the back-dating queue.
SINCE_STATUSES = ("since-supported", "as-of-supported")

# The fields the fold table runs over (Section 6.2). `since` participates only when the
# fact carries one.
LOAD_BEARING_FIELDS = ("base", "since")

# How a pair's support for one field is ranked. `None` means "this pair says nothing
# about this field" and is not the same as "this pair says the field is wrong".
_SUPPORT_RANK = {None: 0, "partial": 1, "supported": 2}


@dataclass(frozen=True)
class Assertion:
    """One atomic assertion from Section 6.2's claim decomposition."""

    kind: str                  # presence | syntax-form | since | qualifier
    text: str
    status: str                # supported | not-supported | contradicted
    grounding_span: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, "status": self.status,
                "grounding_span": self.grounding_span}


@dataclass(frozen=True)
class PairVerdict:
    """One verdict on one (claim, citation) pair, with everything the private ledger needs
    to make it re-derivable (Section 6.2's logging clause)."""

    fact_id: str
    source_id: str
    locator: str
    verdict: str
    per_assertion: tuple[Assertion, ...] = ()
    annotations: tuple[str, ...] = ()
    since_status: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    run_id: str | None = None
    anchor: str | None = None              # "<run_id>#msg-N"
    date: str | None = None
    evidence_chunk_ids: tuple[str, ...] = ()
    # A stage-1 rescue hit far from the claimed locator. A hint, never a pass.
    hint: str = ""
    detail: str = ""

    def field_support(self, field_name: str) -> str | None:
        """What this pair contributes to one load-bearing field.

        @returns "supported", "partial", or None when the pair supports the field not at
            all — which is what `source-unavailable`, `locator-not-found`, `unsupported`
            and `contradicted` all mean for the fold.
        """
        if field_name == "base":
            return self.verdict if self.verdict in ("supported", "partial") else None
        if field_name == "since":
            if self.since_status == "since-supported":
                return "supported"
            if self.since_status == "as-of-supported":
                return "partial"
            return None
        raise ValueError(f"unknown load-bearing field {field_name!r}")

    def as_dict(self) -> dict:
        return {"fact_id": self.fact_id, "source_id": self.source_id,
                "locator": self.locator, "verdict": self.verdict,
                "per_assertion": [a.as_dict() for a in self.per_assertion],
                "annotations": list(self.annotations), "since_status": self.since_status,
                "model": self.model, "prompt_version": self.prompt_version,
                "run_id": self.run_id, "anchor": self.anchor, "date": self.date,
                "evidence_chunk_ids": list(self.evidence_chunk_ids), "hint": self.hint,
                "detail": self.detail}


def fold_verification(pairs, *, tier_of, has_since: bool) -> str:
    """Section 6.2's authoritative verdict fold table.

    Folds the *best* per-pair support over each load-bearing field. The per-field reading
    is what makes the spec's two cases one rule: a `partial` citation is partial on some
    field, and the fold asks whether any citation cleared that field.

    `contradicted` deliberately does not appear here. It routes to the contradiction
    register (Section 6.5) and the separate `dispute` axis, so a fact can be `verified`
    and `contradicted` simultaneously.

    @param pairs - every `PairVerdict` for this fact
    @param tier_of - source_id -> "A" | "B" | "C" | "D"
    @param has_since - whether the fact carries a `since` (making it load-bearing)

    @returns "unverified" | "verified" | "partially-verified" | "failed"
    """
    pairs = list(pairs)
    if not pairs:
        return "unverified"
    admissible = any(pair.verdict in ADMITTING_VERDICTS
                     and tier_of(pair.source_id) in ADMISSIBLE_TIERS for pair in pairs)
    if not admissible:
        return "failed"

    fields = ("base", "since") if has_since else ("base",)
    for field_name in fields:
        best = max((pair.field_support(field_name) for pair in pairs),
                   key=lambda support: _SUPPORT_RANK[support])
        if best != "supported":
            return "partially-verified"
    return "verified"
