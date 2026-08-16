import hashlib
import re
from dataclasses import dataclass, field
from typing import Sequence
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.errors import ExtractionFailed
from langatlas_ingest.extract import Block, ExtractedDocument
from langatlas_ingest.locators import format_pages, format_section
from langatlas_validate.locators import validate_locator_shape

_CHARS_PER_TOKEN = 4
# Bump this whenever chunking or extraction-QA logic changes in a way that could produce
# different chunks — or a different promotion verdict — for byte-identical input. It is
# the half of `chunking_fingerprint` that configuration cannot express: `ingest_source`
# skips a re-ingest whose inputs all match the recorded run, and without a version to
# compare, a rewritten splitter or a tightened QA gate would leave the whole corpus
# pinned to chunks the current code would never produce, with no error and no warning.
# Deliberately not `langatlas_ingest.__version__`: a package bump for an unrelated change
# would invalidate every source and cost a full re-embed (1263 paid provider calls for
# the real corpus) to arrive back at byte-identical rows.
CHUNKER_QA_VERSION = "1"
_NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s+\S")
# Share of chunk_max_tokens the breadcrumb prefix may consume in the embedded text.
# Heading text is capped per level (`_HEADING_MAX_CHARS`, 120) but section *depth* is
# not, so a deeply nested section's full breadcrumb can exceed the whole token budget:
# `split_budget` would then clamp to 1 and every chunk of that section would silently
# come out over chunk_max_tokens. A quarter leaves the body the clear majority of the
# budget while still carrying enough breadcrumb for retrieval context.
_BREADCRUMB_BUDGET_SHARE = 0.25
_BREADCRUMB_ELISION = "… > "


def count_tokens(text: str) -> int:
    """Same chars/4 rule 1B's `estimate_tokens` uses, without its safety margin: here the
    number picks a chunk boundary, it does not decide whether a call is refused. Exact
    tokenization is explicitly out of scope (D26)."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    ordinal: int
    parent_section_id: str
    section_path: list[str]
    breadcrumb: str
    locator: str
    locator_kind: str
    text: str                       # breadcrumb-prefixed: this is what gets embedded
    token_count: int
    content_hash: str
    page_start: int | None = None
    page_end: int | None = None
    section_number: str | None = None
    anchor: str | None = None
    line_start: int | None = None
    line_end: int | None = None


@dataclass
class _Section:
    index: int
    path: list[str] = field(default_factory=list)
    anchor: str | None = None
    number: str | None = None


def _locator_for(section: _Section, pages: tuple[int | None, int | None],
                 kinds: Sequence[str], source_id: str) -> tuple[str, str]:
    """Pick the most specific admissible locator this chunk can actually support, in the
    caller's declared preference order (the source record's `custom.locator_kinds`, §4.1)."""
    candidates: dict[str, str] = {}
    if section.number:
        candidates["numbered-section"] = format_section(section.number)
    if section.anchor:
        candidates["web-fragment"] = f"#{section.anchor}"
    if pages[0] is not None:
        candidates["book-page"] = format_pages(pages[0], pages[1])
    if section.path:
        candidates["named-section"] = format_section(section.path[-1])
    for kind in kinds:
        locator = candidates.get(kind)
        if locator and validate_locator_shape(locator, [kind]) == kind:
            return kind, locator
    raise ExtractionFailed(
        source_id,
        f"no admissible locator: section={section.path!r} pages={pages} "
        f"allowed kinds={list(kinds)}")


class _Accumulator:
    def __init__(self, config: IngestConfig, doc: ExtractedDocument, kinds: Sequence[str]):
        self.config = config
        self.doc = doc
        self.kinds = kinds
        self.chunks: list[Chunk] = []
        self.buffer: list[str] = []
        self.tokens = 0
        self.pages: list[int] = []
        # True exactly when `buffer` holds nothing but a carried-over overlap and no
        # new piece has been appended to it yet. `flush` uses this to refuse to ever
        # emit a chunk that is purely a duplicate of the tail of the chunk it was
        # carried from -- see `flush` for why that refusal has to live there, not just
        # at the one call site that first exposed it.
        self.pure_carry = False

    def _embedded_breadcrumb(self, section: _Section) -> str:
        """The breadcrumb as it appears in the *embedded* text, capped at
        `_BREADCRUMB_BUDGET_SHARE` of the token budget. The full breadcrumb is still
        stored on the Chunk (it is the citation surface); only the copy that competes
        with the body for chunk_max_tokens is capped.

        The shallowest levels go first: the deepest heading is the most specific thing a
        chunk can say about itself, and an elision marker leading the breadcrumb makes
        the truncation visible rather than passing a partial path off as the whole one."""
        breadcrumb = " > ".join(section.path)
        limit = (max(1, int(self.config.chunk_max_tokens * _BREADCRUMB_BUDGET_SHARE))
                 * _CHARS_PER_TOKEN)
        if len(breadcrumb) <= limit:
            return breadcrumb
        levels = list(section.path)
        while levels:
            candidate = _BREADCRUMB_ELISION + " > ".join(levels)
            if len(candidate) <= limit:
                return candidate
            levels.pop(0)
        # Even the deepest heading alone is wider than the whole allowance: hard-cut it,
        # the same way `_split` hard-cuts an unsplittable oversized word.
        return (_BREADCRUMB_ELISION + section.path[-1])[:limit]

    def _prefix(self, section: _Section) -> str:
        breadcrumb = self._embedded_breadcrumb(section)
        return f"{breadcrumb}\n\n" if breadcrumb else ""

    def _text_for(self, section: _Section, buffer: list[str]) -> str:
        return self._prefix(section) + "\n\n".join(buffer)

    def add(self, block: Block, section: _Section) -> None:
        # The max-token budget applies to the *final embedded text* — breadcrumb prefix,
        # "\n\n" joins between buffered pieces, all of it — not to the sum of the raw
        # piece lengths. Checking `count_tokens` on the real prospective text (rather
        # than summing each piece's token count, which silently drops the join/prefix
        # overhead and loses a token or two to floor-rounding on every piece) is what
        # actually keeps every emitted chunk inside chunk_max_tokens.
        prefix_chars = len(self._prefix(section))
        split_budget = max(1, self.config.chunk_max_tokens - prefix_chars // _CHARS_PER_TOKEN)
        for piece in self._split(block.text, split_budget):
            prospective = self.buffer + [piece]
            # `flush` refuses to emit a pure-carry buffer (see there), so calling it
            # repeatedly here is safe and terminates: at most one call emits a real
            # chunk and leaves a fresh (pure-carry) overlap, and at most one more call
            # discards that overlap outright when it still doesn't fit alongside
            # `piece` -- `_split` guarantees a lone piece into an empty buffer always
            # fits, so the loop cannot spin.
            while self.buffer and count_tokens(self._text_for(section, prospective)) \
                    > self.config.chunk_max_tokens:
                self.flush(section, carry=True)
                prospective = self.buffer + [piece]
            self.buffer.append(piece)
            self.pure_carry = False
            if block.page is not None:
                self.pages.append(block.page)
            self.tokens = count_tokens(self._text_for(section, self.buffer))
            if self.tokens >= self.config.chunk_target_tokens:
                self.flush(section, carry=True)

    def _split(self, text: str, budget: int | None = None) -> list[str]:
        """A single oversized paragraph is split on word boundaries rather than dropped —
        every character of the source has to be reachable by some locator."""
        limit = (self.config.chunk_max_tokens if budget is None else budget) * _CHARS_PER_TOKEN
        if len(text) <= limit:
            return [text]
        words = text.split()
        if not words:
            # An over-limit block with no word boundaries (e.g. one long whitespace
            # run) can't be usefully split; returning it whole, rather than the empty
            # list the loop below would silently produce, keeps it reachable by a
            # locator instead of dropping it from the corpus without a trace.
            return [text]
        pieces: list[str] = []
        current: list[str] = []
        length = 0
        for word in words:
            if length + len(word) + 1 > limit and current:
                pieces.append(" ".join(current))
                current, length = [], 0
            if len(word) > limit:
                # A single "word" (no internal whitespace) wider than the whole budget
                # can't be reduced by joining it with anything — appending it whole
                # would emit an over-limit piece. Hard-cut it into limit-sized slices
                # instead; `current` is already empty here (flushed above if not).
                for start in range(0, len(word), limit):
                    pieces.append(word[start:start + limit])
                continue
            current.append(word)
            length += len(word) + 1
        if current:
            pieces.append(" ".join(current))
        return pieces

    def flush(self, section: _Section, *, carry: bool = False) -> None:
        if not self.buffer or self.pure_carry:
            # Nothing *new* to emit — either the buffer is empty, or it holds only a
            # carried-over overlap that never got a new piece appended to it (the
            # section ended, or the next piece didn't fit, before any new content
            # arrived). Emitting that buffer would produce a chunk whose text, and
            # therefore content_hash, duplicates the tail of the chunk it was carried
            # from — corpus pollution, not a real chunk, so it is discarded here
            # rather than flushed. Either way no chunk claims these pages — but the
            # pages a bare heading pushed (chunk_document appends a heading's own page
            # before any body arrives) must not leak into whatever section flushes
            # next: without this reset, a section with no body of its own (heading
            # immediately followed by another heading) would leave its heading's page
            # sitting in self.pages, and the next section's real chunk would silently
            # inherit it into its page_start/page_end — a citation pointing at a page
            # nothing in the chunk's text actually came from.
            self.pages = []
            self.buffer = []
            self.tokens = 0
            self.pure_carry = False
            return
        body = "\n\n".join(self.buffer)
        # Two breadcrumbs on purpose: the stored one is the full path (a citation
        # surface, never truncated), the embedded one is capped so a deeply nested
        # section cannot push every chunk of itself over chunk_max_tokens — see
        # `_embedded_breadcrumb`. `_prefix` uses the same capped form, so the split
        # budget and the emitted text agree.
        breadcrumb = " > ".join(section.path)
        text = self._prefix(section) + body
        pages = (min(self.pages), max(self.pages)) if self.pages else (None, None)
        kind, locator = _locator_for(section, pages, self.kinds, self.doc.source_id)
        ordinal = len(self.chunks)
        self.chunks.append(Chunk(
            chunk_id=f"{self.doc.source_id}#c{ordinal:05d}", source_id=self.doc.source_id,
            ordinal=ordinal, parent_section_id=f"{self.doc.source_id}#s{section.index:04d}",
            section_path=list(section.path), breadcrumb=breadcrumb, locator=locator,
            locator_kind=kind, text=text, token_count=count_tokens(text),
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            page_start=pages[0], page_end=pages[1], section_number=section.number,
            anchor=section.anchor))
        overlap = self._carry(body) if carry else ""
        self.buffer = [overlap] if overlap else []
        self.pages = self.pages[-1:] if (carry and self.pages) else []
        # Consistent with every other site that sets self.tokens: it always reflects
        # count_tokens on the real prospective text (prefix included), never a bare
        # sum of piece lengths.
        self.tokens = count_tokens(self._text_for(section, self.buffer)) if self.buffer else 0
        self.pure_carry = bool(self.buffer)

    def _carry(self, body: str) -> str:
        """Small trailing overlap so a claim straddling a boundary is still retrievable
        from at least one chunk."""
        if self.config.chunk_overlap_tokens <= 0:
            return ""
        words = body.split()
        if not words:
            return ""
        take = max(1, self.config.chunk_overlap_tokens * _CHARS_PER_TOKEN // 6)
        if take >= len(words):
            # Carrying every word forward doesn't overlap the next chunk with this
            # one, it *clones* it — same text, same content_hash. A body this short
            # (typically a single unsplittable oversized word/piece) gets no overlap
            # rather than a byte-identical duplicate chunk next.
            return ""
        return " ".join(words[-take:])


def chunking_fingerprint(config: IngestConfig, *, min_chars: int | None = None) -> dict:
    """Everything about *how* this run chunks and judges a source, in one comparable value.

    Recorded beside each ingestion so `ingest_source` can tell a genuinely unchanged
    source (skippable — its chunks and their paid embeddings are already correct) from
    one whose chunk boundaries, or promotion verdict, would now come out differently.
    Only the knobs that actually reach the chunker or the QA gate are included: widening
    `retrieval_k` must not invalidate a corpus, and a fingerprint that moves for unrelated
    reasons would be a re-embed bill, not a safeguard.

    `min_chars` is the source's own extraction-collapse floor (`snapshot.min_chars`). It
    changes the QA verdict for byte-identical content, which is exactly what the currency
    key exists to catch — a source re-ingested under a different floor must not be skipped
    on the strength of the run that used the old one.

    It is omitted entirely when unset rather than recorded as `None`, so a source that
    never had an override fingerprints exactly as it did before this field existed. That
    is not cosmetic: an always-present key would make every already-recorded row unequal
    to its own re-run, re-ingest the whole corpus, cascade away every embedding
    (`source_chunks(chunk_id) ON DELETE CASCADE`) and cost a full re-embed — 1263 paid
    provider calls for the real Van Roy & Haridi corpus — to arrive back at byte-identical
    rows. "No override" and "no such setting" genuinely do mean the same thing here (both
    are `qa._MIN_CHARS`), so the equal fingerprint is honest rather than a convenience."""
    fingerprint = {"version": CHUNKER_QA_VERSION,
                   "target_tokens": config.chunk_target_tokens,
                   "max_tokens": config.chunk_max_tokens,
                   "overlap_tokens": config.chunk_overlap_tokens}
    if min_chars is not None:
        fingerprint["min_chars"] = int(min_chars)
    return fingerprint


def chunk_document(doc: ExtractedDocument, *, config: IngestConfig,
                   locator_kinds: Sequence[str]) -> list[Chunk]:
    """Structure-aware chunking (D15): sections are boundaries, headings become the
    breadcrumb, and every chunk carries a locator produced here — never hand-authored
    (§4.3/D37)."""
    accumulator = _Accumulator(config, doc, locator_kinds)
    section = _Section(index=0)
    stack: list[tuple[int, str]] = []

    for block in doc.blocks:
        if block.heading_level:
            accumulator.flush(section)
            while stack and stack[-1][0] >= block.heading_level:
                stack.pop()
            stack.append((block.heading_level, block.text))
            number = _NUMBERED_HEADING.match(block.text)
            section = _Section(index=section.index + 1,
                               path=[title for _, title in stack],
                               anchor=block.anchor,
                               number=number.group(1) if number else None)
            if block.page is not None:
                accumulator.pages.append(block.page)
            continue
        accumulator.add(block, section)
    accumulator.flush(section)
    return accumulator.chunks
