"""Chunk ids in, citations out — the one place an R4 role's evidence becomes a `sources:` entry.

A role names only a chunk id. `source` and `locator` are copied from `source_chunks` (§4.3:
machine-produced, never re-derived), so a model can neither invent a locator nor typo one. A
quote is optional and gets two checks it cannot argue with: D14's 50-word cap, and being
actually present in the chunk it claims. A quote that fails either is dropped and the citation
survives without it — the claim is still sourced, it just no longer carries a verbatim excerpt.

A lead that resolves to nothing at all is a failure, not a warning: an entry with zero evidence
is unmintable (D4), and saying so here is cheaper than discovering it at the gate."""
import re

from pydantic import BaseModel

from langatlas_ingest.verify.quotes import quote_within_cap
from langatlas_research.drafts import Evidence
from langatlas_research.errors import EvidenceUnresolvable
from langatlas_research.survey.chunks import ChunkLookup

_WS = re.compile(r"\s+")


class EvidenceItem(BaseModel):
    """One evidence lead in a Claude role's structured output."""

    chunk_id: str
    quote: str | None = None


def _flat(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def bind_evidence(items, *, lookup: ChunkLookup,
                  what: str) -> tuple[list[dict], list[str]]:
    """@param items: `EvidenceItem`s (or anything with `.chunk_id` / `.quote`).
    @param what: the entry key, for error and warning text.
    @returns: `(entries, warnings)` — entries in first-seen order, deduped by chunk id.
    @raises EvidenceUnresolvable: not one lead resolved, so the entry has no evidence at all."""
    entries: list[dict] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item.chunk_id in seen:
            continue
        seen.add(item.chunk_id)
        ref = lookup(item.chunk_id)
        if ref is None:
            warnings.append(f"{what}: evidence chunk {item.chunk_id} does not resolve;"
                            f" dropped")
            continue
        entry = {"source": ref.source_id, "locator": ref.locator, "chunk_id": ref.chunk_id}
        if item.quote:
            quote = _WS.sub(" ", item.quote).strip()
            if not quote_within_cap(quote):
                warnings.append(f"{what}: quote on {ref.chunk_id} exceeds D14's 50 words;"
                                f" kept the citation, dropped the quote")
            elif _flat(quote) not in _flat(ref.text):
                warnings.append(f"{what}: quote on {ref.chunk_id} is not verbatim in that"
                                f" chunk; kept the citation, dropped the quote")
            else:
                entry["quote"] = quote
        entries.append(entry)
    if not entries:
        raise EvidenceUnresolvable(
            f"{what}: not one evidence chunk resolved, so this entry has no source at all"
            f" (D4/§6.1)")
    return entries, warnings


def as_drafts(entries) -> tuple[Evidence, ...]:
    """Plan evidence -> 3A's `Evidence` tuples. `chunk_id` is plan bookkeeping and is
    deliberately dropped: a record's `sources:` list is `(source, locator, quote?)` only."""
    return tuple(Evidence(source=entry["source"], locator=entry["locator"],
                          quote=entry.get("quote")) for entry in entries)
