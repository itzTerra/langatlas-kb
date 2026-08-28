from dataclasses import dataclass, field
from langatlas_validate.claims import fact_id as _fact_id

# Section 6.4's 13 strata, in the spec's order. Frozen: the taxonomy is shared between
# the golden set, the scorer's per-stratum report, and 2D's calibration write-up, so a
# rename here is a data migration, not a refactor.
STRATA = (
    "correct",
    "overstated-claim",             # first-class K1 defense; the only `partial` stratum
    "fabricated-locator",
    "wrong-since-off-by-one",
    "wrong-since-off-by-major",
    "contradicted",
    "right-claim-wrong-source",
    "category-error",
    "fabricated-combination",
    "quote-mismatch",
    "quote-found-elsewhere",
    "ocr-noisy",
    "paraphrase-heavy-correct",
)

# Section 6.2's six per-(claim, citation) verdicts, in the spec's order.
VERDICTS = ("source-unavailable", "locator-not-found", "supported", "partial",
            "unsupported", "contradicted")

# Stage-2 annotations, deliberately NOT verdicts (Section 6.2).
ANNOTATIONS = ("quote-mismatch", "quote-found-elsewhere")

# The admissibility rule is ">=1 citation `supported` from a tier-A/B source". `partial`
# bounces for claim narrowing and never admits, so it is not an accept — the whole
# false-accept measurement hangs off this set being exactly {"supported"}.
ADMITTING_VERDICTS = frozenset({"supported"})

# Which verdicts a stratum may legitimately expect. Single-element sets where Section 6.2
# fixes the answer; two-element sets where the per-assertion fold ratified 2026-08-28
# genuinely admits both outcomes:
#   - a wrong `since` is `contradicted` when the cited text states a conflicting version
#     and `partial` when the text is simply silent on versions (the as-of-supported path
#     of Section 6.2, which enters the store and queues for back-dating). The size of the
#     error does not enter into it, so both `since` strata share one verdict set.
#   - a fabricated quote never admits: `unsupported`, or `contradicted` when the source
#     also opposes the claim's substance. It is never `partial` — the citation as
#     submitted is untrustworthy, whatever the claim's substance turns out to be.
STRATUM_VERDICTS = {
    "correct":                  frozenset({"supported"}),
    "overstated-claim":         frozenset({"partial"}),
    "fabricated-locator":       frozenset({"locator-not-found"}),
    "wrong-since-off-by-one":   frozenset({"partial", "contradicted"}),
    "wrong-since-off-by-major": frozenset({"partial", "contradicted"}),
    "contradicted":             frozenset({"contradicted"}),
    "right-claim-wrong-source": frozenset({"unsupported", "contradicted"}),
    "category-error":           frozenset({"unsupported"}),
    "fabricated-combination":   frozenset({"unsupported", "contradicted"}),
    "quote-mismatch":           frozenset({"unsupported", "contradicted"}),
    "quote-found-elsewhere":    frozenset({"supported", "partial"}),
    "ocr-noisy":                frozenset({"supported"}),
    "paraphrase-heavy-correct": frozenset({"supported"}),
}

# Two strata are *defined* by the annotation the quote fast path must raise; an item that
# does not expect it is testing something other than what its stratum claims.
REQUIRED_ANNOTATION = {"quote-mismatch": "quote-mismatch",
                       "quote-found-elsewhere": "quote-found-elsewhere"}

# D14's verbatim cap. Golden items embed source text, so they are bound by it too.
MAX_QUOTE_WORDS = 50

# Section 6.3's two `since` outcomes, which the entailment stage must distinguish.
SINCE_STATUSES = ("since-supported", "as-of-supported")

CONTROVERSY_LEVELS = (0, 1, 2, 3)

# Section 6.4: the assessor sees structured inputs only.
ALLOWED_CONTROVERSY_INPUTS = ("debates", "contradiction_records", "verdicts",
                              "source_strength", "assessment_spread")
# Explicitly excluded by Section 6.4 (and by the 2026-07-20 withdrawal of
# `closure_attempt.outcome`). A bootstrap case that smuggles one of these in would
# calibrate the assessor against an input it will never legitimately receive.
FORBIDDEN_CONTROVERSY_INPUTS = ("github_activity", "challenge_activity",
                                "human_challenges", "closure_attempt", "issue_comments")


@dataclass(frozen=True)
class Claim:
    """The claim half of a (claim, citation) pair, as the verifier will see it.

    `text` is the canonical claim string built by `langatlas_validate.claims.build_claim`
    — the same string the canonical store would hold — so a golden item and a real fact
    are the same shape of input.
    """

    kind: str
    text: str
    rendered: str | None = None          # optional human-readable prose, for review only
    status: str | None = None            # present | partial | absent, for instance-exists
    since: str | None = None
    expected_since_status: str | None = None   # since-supported | as-of-supported
    absence_scope: str | None = None
    feature_aliases: tuple[str, ...] = ()

    @property
    def fact_id(self) -> str:
        """The fact id the claim text hashes to. Derived, never stored: an item whose
        stored id disagreed with its claim text would be a silently wrong test."""
        return _fact_id(self.text)


@dataclass(frozen=True)
class Citation:
    source: str
    locator: str
    quote: str | None = None


@dataclass(frozen=True)
class VerifierItem:
    """One committed calibration item: a (claim, citation) pair plus the verdict a
    correctly-calibrated D24 verifier must return for it."""

    id: str
    stratum: str
    expected_verdict: str
    claim: Claim
    citation: Citation
    evidence_chunk_ids: tuple[str, ...] = ()
    expected_annotations: tuple[str, ...] = ()
    # Stage 0 rejects a malformed locator before resolution ever runs. Most
    # fabricated-locator items are shape-valid but resolve to nothing; this flag marks the
    # minority that deliberately fail the grammar, so the validator does not reject them.
    shape_invalid: bool = False
    # Section 6.4's passive contamination gauge: items deliberately targeting obscure loci.
    # Scored on their own line — a wide gap against the mainstream items is the signal.
    contamination_gauge: bool = False
    authored_by: str = "developer"       # developer | llm-curated
    curated: bool = True
    notes: str = ""
    held_out: bool = False

    def verifier_input(self) -> dict:
        """Build the whitelist input of Section 6.2 — and nothing else.

        Context blindness is structural, so this is an allow-list construction rather
        than a redaction: notes, stratum, expected verdict, `claim_origin`, proposer
        identity and the item's own provenance are simply never assembled. D49's
        inverted-framing stage verifies the agent's own absence argument, so an `absent`
        claim widens the whitelist by exactly `absence_scope` and `feature_aliases`.

        @returns the dict a D24 verifier receives for this item
        """
        payload = {"fact_id": self.claim.fact_id, "claim": self.claim.text,
                   "since": self.claim.since, "source_id": self.citation.source,
                   "locator": self.citation.locator, "quote": self.citation.quote}
        if self.claim.status == "absent":
            payload["absence_scope"] = self.claim.absence_scope
            payload["feature_aliases"] = list(self.claim.feature_aliases)
        return payload


@dataclass(frozen=True)
class ControversyCase:
    """One bootstrap case for the D21/D25 assessor: structured inputs in, ordinal level
    out. The assessor itself is Stage 3; these cases exist so it has a calibration set
    the day it is written."""

    id: str
    expected_level: int
    inputs: dict = field(default_factory=dict)
    expected_signals: tuple[str, ...] = ()
    authored_by: str = "developer"
    curated: bool = True
    notes: str = ""
