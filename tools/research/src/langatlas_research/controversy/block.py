"""Reading, merging and rendering the canonical `controversy:` block.

Two asymmetries are deliberate:

- **Level 0 removes, it does not write.** §6.4 fixes an absent entry as level 0, so a fact that
  stopped being contested has to lose its entry — otherwise the site renders a dispute that
  resolved months ago.
- **Unassessed facts are untouched.** A budget stop mid-record is normal (D43), and a merge that
  dropped the entries it did not re-derive would silently downgrade every fact the run never
  reached.
"""
from pathlib import Path

from langatlas_research.mint import MintedRecord, content_digest, dump_yaml
from langatlas_validate.normalize import normalize_record


def block_entries(data: dict) -> dict:
    """@returns key -> entry for the record's existing block, empty when there is none."""
    return {entry["key"]: entry for entry in data.get("controversy") or []}


def merge_block(data: dict, assessments: dict, *, date: str) -> dict:
    """Fold this run's assessments into the record's block.

    @param assessments: field-path key (the anchor suffix, e.g. `summary`,
        `characteristics[c-exhaustive]`) -> `Assessment`.
    @param date: the assessment date stamped on every entry this run writes.
    @returns a new record dict; the input is never mutated, because the caller still needs the
        pre-merge text to decide whether anything actually changed."""
    entries = block_entries(data)
    for key, assessment in assessments.items():
        if assessment.level == 0:
            entries.pop(key, None)
            continue
        entries[key] = {
            "key": key,
            "fact_id": assessment.fact_id,
            "level": int(assessment.level),
            "signals": list(assessment.signals),
            "assessed": {"date": date, "model": assessment.model,
                         "prompt": assessment.prompt, "run_id": assessment.run_id,
                         "escalated_to": assessment.escalated_to},
        }
    merged = {k: v for k, v in data.items() if k != "controversy"}
    if entries:
        merged["controversy"] = [entries[key] for key in sorted(entries)]
    return merged


def controversy_mint(record_path: str, data: dict, *, kind: str,
                     base_text: str) -> MintedRecord:
    """The record as a shared-file `MintedRecord`, for `land_drafts`.

    `base_digest` is the digest of the text this merge was computed from, so a record another
    process rewrote between read and land is re-rendered rather than clobbered — the same
    read-modify-write protection `taxonomy.py` and the contradictions ledger use."""
    text = normalize_record(dump_yaml(data), kind)
    return MintedRecord(path=record_path, text=text, kind=kind, node_ids=(),
                        base_digest=content_digest(base_text))


def unchanged(minted: MintedRecord, base_text: str) -> bool:
    """True when the merge produced byte-identical text — the common nightly case, and the one
    that must never produce an empty commit."""
    return minted.text == base_text
