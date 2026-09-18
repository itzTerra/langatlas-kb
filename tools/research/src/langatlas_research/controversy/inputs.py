"""§6.4's structured inputs and the closed signal grammar.

Two rules are load-bearing here and nowhere else:

1. **Allow-list construction, not redaction.** `from_mapping` refuses anything outside the
   five permitted keys, so an assessor input can never acquire a human-challenge-derived
   field by someone adding one upstream. This mirrors D24's `whitelist_payload`.
2. **A signal is a machine reference the inputs can actually justify.** §6.4 makes the
   `signals` list *the* justification — there is no free-prose rationale to fall back on — so a
   signal the inputs cannot produce is not a weak justification, it is a fabricated one, and
   `assessor.py` drops it.
"""
import hashlib
import json
from dataclasses import dataclass, field

from langatlas_ingest.goldens.items import (
    ALLOWED_CONTROVERSY_INPUTS as ALLOWED,
    FORBIDDEN_CONTROVERSY_INPUTS as FORBIDDEN,
)

from langatlas_research.errors import ControversyInputRefused

# Verdicts that say something disagrees. `supported` and `source-unavailable` justify no
# signal: the first is agreement, the second is a missing measurement.
_DISSENTING_VERDICTS = frozenset({"partial", "unsupported", "contradicted",
                                  "locator-not-found"})


@dataclass(frozen=True)
class ControversyInputs:
    """Exactly what §6.4 lets the assessor see, in 2B's committed vocabulary."""

    debates: tuple[dict, ...] = ()
    contradiction_records: tuple[dict, ...] = ()
    verdicts: tuple[dict, ...] = ()
    source_strength: dict = field(default_factory=dict)
    assessment_spread: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        """The model-facing mapping, in the frozen key order.

        @returns a plain dict with all five keys present — an absent key and an empty one
            must look the same to the rubric, or "no debates" reads as "debates unknown"."""
        return {"debates": [dict(d) for d in self.debates],
                "contradiction_records": [dict(c) for c in self.contradiction_records],
                "verdicts": [dict(v) for v in self.verdicts],
                "source_strength": dict(self.source_strength),
                "assessment_spread": {k: list(v) for k, v in self.assessment_spread.items()}}

    @classmethod
    def from_mapping(cls, raw: dict) -> "ControversyInputs":
        """@raises ControversyInputRefused: any key outside `ALLOWED`, named explicitly so the
            failure message says which rule was broken."""
        for key in raw:
            if key in FORBIDDEN:
                raise ControversyInputRefused(
                    f"{key!r} is human-challenge-derived and is excluded from the assessor"
                    f" by §6.4")
            if key not in ALLOWED:
                raise ControversyInputRefused(
                    f"{key!r} is not one of §6.4's structured inputs {list(ALLOWED)}")
        return cls(debates=tuple(raw.get("debates") or ()),
                   contradiction_records=tuple(raw.get("contradiction_records") or ()),
                   verdicts=tuple(raw.get("verdicts") or ()),
                   source_strength=dict(raw.get("source_strength") or {}),
                   assessment_spread={k: list(v) for k, v
                                      in (raw.get("assessment_spread") or {}).items()})


def derivable_signals(inputs: ControversyInputs) -> set[str]:
    """Every machine reference these inputs justify — the universe the assessor may cite.

    Debate signals reuse 3C's rule verbatim (standing dissent outranks the outcome), because
    the debate record module and this one are scored by the same committed golden set."""
    signals: set[str] = set()
    for debate in inputs.debates:
        if debate.get("standing_dissent"):
            signals.add(f"debate:{debate['id']}:standing-dissent")
        else:
            signals.add(f"debate:{debate['id']}:{debate['outcome']}")
    for record in inputs.contradiction_records:
        signals.add(f"contradiction:{record['id']}:{record['status']}")
    for verdict in inputs.verdicts:
        if verdict.get("verdict") in _DISSENTING_VERDICTS:
            signals.add(f"verdict:{verdict['verdict']}:{verdict.get('field', 'base')}")
    for key in inputs.assessment_spread:
        signals.add(f"assessment-spread:{key}")
    return signals


def inputs_digest(inputs: ControversyInputs) -> str:
    """A content key over the assessed inputs — the whole mechanism behind §6.4's
    "unchanged inputs => unchanged level, so a re-run is free".

    Canonical JSON with sorted keys: two assemblies that differ only in dict ordering are the
    same inputs and must not trigger a re-assessment.

    @returns 16 hex chars, matching the store's other content keys."""
    payload = json.dumps(inputs.as_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
