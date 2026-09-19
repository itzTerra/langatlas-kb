"""Blocked carves: an entry the seed structure cannot hold (D70).

A structural misfit is information about the structure, not a defect in the model's output,
so it stays in the carve plan — evidence and all — flagged `blocked: structure` and linked to a
`structure-friction` finding. A blocked entry is never debated, verified or minted; it waits for
the structure review, after which the batch is re-atomized against the revised structure.
Hygiene errors (invalid slugs, duplicate keys, re-minting a committed id) are defects and still
reject the run — that split lives in each role's shape check, not here."""
from dataclasses import dataclass

from langatlas_research.draft.findings import friction_entry

BLOCKED = "structure"


@dataclass(frozen=True)
class Misfit:
    key: str
    element: str      # a `STRUCTURE_ELEMENTS` member
    reason: str


def is_blocked(entry: dict) -> bool:
    return entry.get("blocked") == BLOCKED


def block_entries(entries: list[dict], misfits: list[Misfit]) -> list[dict]:
    """`entries` with each misfit's entry marked blocked. A key with several misfits keeps
    all its reasons, in the order they were found."""
    reasons: dict[str, list[str]] = {}
    for misfit in misfits:
        reasons.setdefault(misfit.key, []).append(misfit.reason)
    return [{**entry, "blocked": BLOCKED, "block_reason": "; ".join(reasons[entry["key"]])}
            if entry["key"] in reasons else entry
            for entry in entries]


def synthesize_friction(misfits: list[Misfit], findings: list[dict]) -> list[dict]:
    """One `structure-friction` finding per (key, element) the model did not already report.
    A key the model reported friction for is left alone: its own words are the better record."""
    covered = {key for finding in findings if finding.get("kind") == "structure-friction"
               for key in finding.get("keys") or []}
    seen: set[tuple[str, str]] = set()
    made = []
    for misfit in misfits:
        if misfit.key in covered or (misfit.key, misfit.element) in seen:
            continue
        seen.add((misfit.key, misfit.element))
        made.append(friction_entry(misfit.reason, keys=[misfit.key], element=misfit.element))
    return made
