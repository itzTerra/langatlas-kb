from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

# Layer 2 of D53's three (the tool description carries this verbatim, once per session).
# Stated as policy, not as a warning, because an agent under time pressure discounts
# warnings and follows rules.
NON_CITABLE_CAVEAT = (
    "Finding-aid results are LEADS, never citations. They may tell you what to look for "
    "and where to look for it. They may never appear in a fact's `sources:` list or in "
    "claim text: every committed fact still needs an independently verified tier-A/B "
    "source through the normal verification gate (D4/D24, D29/D3).")

# D29's ratified `provenance.candidate_source` enum has five relevant members and no
# `wikipedia`. Widening a ratified enum for one adapter would be the tail wagging the dog.
_CANDIDATE_SOURCE = {"pldb": "pldb", "wikidata": "wikidata",
                     "hyperpolyglot": "hyperpolyglot", "wikipedia": "internal-survey"}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class FindingAidResult:
    """One lead from one finding aid.

    Note what this type does *not* have: `source_id`, `locator`, `quote`, `tier`. Those
    four are what a `sources:` entry is made of (§3.4), and their absence is the structural
    layer of D53's non-citability — there is no assignment, no `**result`, and no dict
    round-trip that turns a lead into a citation. `fields` is a free-form per-adapter
    payload precisely so it can never grow into a citation shape by accident."""

    source: str                     # pldb | wikidata | hyperpolyglot | wikipedia
    item_id: str                    # the aid's own identifier (Q-id, slug, page path)
    label: str
    fields: dict
    url: str                        # where a human can look, not where a claim is cited
    retrieved_at: str
    mirror_version: str | None = None   # the mirror commit/manifest a read came from
    non_citable: bool = field(default=True)

    def as_dict(self) -> dict:
        return asdict(self)


def candidate_source_for(result: FindingAidResult) -> str:
    """The advisory `provenance.candidate_source` value for a fact drafted after this
    lead (D29/D53 §O5). Advisory bookkeeping only — nothing verifies that the lead caused
    the draft; D18's transcript is where the real trace lives."""
    return _CANDIDATE_SOURCE[result.source]
