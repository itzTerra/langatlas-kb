# tools/ingest/src/langatlas_ingest/benchmark/relevance.py
from dataclasses import dataclass
from typing import Callable
from langatlas_ingest.store import SourceChunk, SourceChunksStore


@dataclass(frozen=True)
class Span:
    """Where a chunk sits in its document, in the two coordinate systems the corpus
    actually carries and that survive a re-chunking: the page range (PDF-derived sources)
    and the outline path (HTML/section-derived sources). Chunk ids do not survive; these
    do, which is the whole reason this type exists."""

    source_id: str
    section_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None

    @property
    def paged(self) -> bool:
        return self.page_start is not None and self.page_end is not None


def span_of(chunk: SourceChunk) -> Span:
    return Span(source_id=chunk.source_id,
                section_path=tuple(chunk.section_path or ()),
                page_start=chunk.page_start, page_end=chunk.page_end)


def overlaps(expected: Span, candidate: Span) -> bool:
    """Does `candidate` cover the region `expected` occupies?

    Pages first when both sides have them — a page range is the finer and less ambiguous
    signal, and a differently-sized chunk of the same pages is exactly what the chunk-size
    axis is varying. Otherwise the outline path, where an *ancestor* counts: a larger
    chunk size merges subsections upward, and the merged chunk genuinely contains the
    passage the golden entry pointed at. A descendant does not count in the other
    direction by accident — `section_path` prefix containment is asymmetric on purpose.

    When only one side carries page numbers (an HTML source has none at all), pages are
    not comparable and the rule falls through to the section path rather than treating the
    missing side as either an automatic match or an automatic miss — a page-only golden
    entry against a page-less candidate, or vice versa, has no page signal to disagree on,
    so the outline path is the only honest arbiter left.
    """
    if expected.source_id != candidate.source_id:
        return False
    if expected.paged and candidate.paged:
        return (candidate.page_start <= expected.page_end
                and expected.page_start <= candidate.page_end)
    if not expected.section_path or not candidate.section_path:
        return False
    return (expected.section_path[:len(candidate.section_path)]
            == candidate.section_path)


def load_expected_spans(prod_conn, entries: list[dict]) -> dict[str, dict[str, Span]]:
    """Resolve every `expected_chunks` id against the *production* corpus — the one
    chunking in which those ids exist. Entries whose ids resolve to nothing are simply
    absent from the result, and `make_span_relevance` then matches nothing for them:
    a query whose target cannot be located is unscorable, and pretending otherwise would
    move the arm's recall for a reason that has nothing to do with chunk size.

    Keyed by chunk id (not just by entry id) so `make_span_relevance` can resolve one
    specific expected chunk's span on request — `eval._score`'s distinct-coverage recall
    needs to ask "does anything cover *this* expected chunk" one id at a time, which a
    plain per-entry tuple of spans cannot answer once an entry declares more than one.
    """
    store = SourceChunksStore(prod_conn)
    spans: dict[str, dict[str, Span]] = {}
    for entry in entries:
        resolved = {chunk_id: span_of(chunk)
                    for chunk_id, chunk in (
                        (chunk_id, store.get(chunk_id))
                        for chunk_id in entry.get("expected_chunks") or [])
                    if chunk is not None}
        if resolved:
            spans[entry["id"]] = resolved
    return spans


def make_span_relevance(spans: dict[str, dict[str, Span]]) \
        -> Callable[[dict, SourceChunk], bool]:
    """A `run_eval(relevance=...)` predicate for a re-chunked corpus.

    `expected_sources` entries keep source-level matching unchanged — a source id is
    chunking-independent already, so there is nothing to translate.

    Only the ids named in `entry["expected_chunks"]` are checked (not every id ever
    resolved for that entry's id) — a full-entry call and a single-id call (substituting
    a one-element `expected_chunks`, as `eval._score` does for distinct-coverage recall)
    must agree on what "relevant to *this* id" means.
    """
    def relevant(entry: dict, chunk: SourceChunk) -> bool:
        if entry.get("expected_sources"):
            return chunk.source_id in entry["expected_sources"]
        candidate = span_of(chunk)
        by_id = spans.get(entry.get("id"), {})
        return any(overlaps(by_id[chunk_id], candidate)
                   for chunk_id in entry.get("expected_chunks") or ()
                   if chunk_id in by_id)

    return relevant
