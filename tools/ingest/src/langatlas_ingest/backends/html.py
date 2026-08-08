import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from langatlas_ingest.extract import Block, ExtractedDocument

_HEADINGS = {f"h{level}": level for level in range(1, 7)}

# Level given to a <head> trafilatura emits with no `rend`, or a `rend` we don't
# recognize — in practice its <summary>-derived headings (`convert_details` sets no
# `rend`). Deepest, not shallowest: this is a synthesized heading of unknown rank, and the
# outline it feeds is diffed against the chunker's section paths, so an over-promoted entry
# is far more damaging than an under-promoted one. At level 6 a disclosure widget nests
# under whatever real section precedes it; at level 1 it would open a phantom top-level
# section and reparent everything after it. (trafilatura's own HTML rendering defaults
# unknown `rend` to h3, but that is a middle guess for display, not a claim about
# hierarchy.)
_SYNTHESIZED_HEADING_LEVEL = 6

# Yoast FAQ blocks mark questions with this class on a <strong>; trafilatura promotes them
# to <head rend="h3">, so the level here mirrors the `rend` it assigns.
_FAQ_QUESTION_CLASS = "schema-faq-question"
_FAQ_QUESTION_LEVEL = 3


def _promotable_level(tag: str, attrs: dict[str, str | None]) -> int | None:
    """The level to record for a raw element trafilatura may emit as a `<head>`, or None.

    Mirrors every tag→head conversion in the installed trafilatura's `htmlprocessing`
    (verified by reading it: `convert_headings` for h1–h6, `convert_details` for a
    `<summary>`, and the Yoast FAQ path for `<strong class="schema-faq-question">` — those
    are the only three sites that assign `tag = "head"`). Anything trafilatura can promote
    must be recorded here or `_anchors_by_key`'s superset precondition is false."""
    if tag in _HEADINGS:
        return _HEADINGS[tag]
    if tag == "summary":
        return _SYNTHESIZED_HEADING_LEVEL
    if tag == "strong" and _FAQ_QUESTION_CLASS in (attrs.get("class") or ""):
        return _FAQ_QUESTION_LEVEL
    return None


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().lower()


def _element_text(element: ET.Element) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", "".join(element.itertext()))).strip()


class _AnchorParser(HTMLParser):
    """trafilatura discards element ids entirely, so anchors — §4.3's web locators — have
    to come from a separate parse of the raw HTML. `self.headings` is a plain list in
    document order, not a dict: two sections can share a heading's exact text, so lookups
    must stay positional (see `_anchors_by_key`) rather than a persistent text-keyed cache.

    A heading's *identity as a heading* never comes from this parser or from text
    matching — that comes from trafilatura's own structural output (see `extract_html`).
    This parser exists only to recover the `id` attribute for a heading trafilatura has
    already told us is real.

    **This parse records every element trafilatura can emit as a `<head>`, with no
    filtering whatsoever.** That is deliberate and load-bearing, not an oversight.
    `_anchors_by_key`'s soundness rests on this list being a *superset* of trafilatura's
    headings, so that equal counts can only mean the same headings. Two ways that
    precondition has already been broken, both of which produced wrong anchors:

    - *Filtering by container.* An earlier version skipped headings inside
      `<nav>`/`<header>`/`<footer>`/`<aside>`. trafilatura keeps a `<header>` nested inside
      `<article>`, so the two views could omit *different* headings, counts could coincide
      on non-corresponding ones, and parity certified a wrong anchor. Filtering boilerplate
      is also unnecessary — a boilerplate heading trafilatura drops simply makes the counts
      unequal, which already degrades that text to no anchor.
    - *Assuming headings are only `hN` tags.* trafilatura synthesizes `<head>` elements
      from non-heading markup too (`<summary>`, Yoast `<strong class="schema-faq-question">`
      — see `_promotable_level`). Those were invisible to this parse, so a synthesized
      heading could be handed the id of an unrelated element trafilatura had dropped.

    So: do not add filtering back, and if trafilatura gains a new tag→head conversion,
    `_promotable_level` must gain it too."""

    def __init__(self):
        super().__init__()
        self.headings: list[tuple[str, int, str | None]] = []
        self._tag: str | None = None
        self._level = 0
        self._buffer: list[str] = []
        self._id: str | None = None

    def handle_starttag(self, tag, attrs):
        if self._tag is not None:
            return      # outermost wins: inline markup inside a heading is part of it
        level = _promotable_level(tag, dict(attrs))
        if level is not None:
            self._tag = tag
            self._level = level
            self._buffer = []
            self._id = dict(attrs).get("id")

    def handle_data(self, data):
        if self._tag is not None:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        if tag == self._tag:
            text = _key("".join(self._buffer))
            if text:
                self.headings.append((text, self._level, self._id))
            self._tag = None
            self._level = 0


def _anchors_by_key(
    raw_headings: list[tuple[str, int, str | None]],
    elements: list[ET.Element],
) -> dict[str, list[str | None]]:
    """Align trafilatura's headings with the raw-HTML ones, by count parity per text.

    The two parses are independent and cannot be made to agree in general: trafilatura
    drops boilerplate on content heuristics (`<div class="related-links">`, `.promo`,
    `.sidebar`) that no tag list can reproduce from the markup, so the raw parse routinely
    sees headings trafilatura never emits. Earlier rounds tried to bridge that with ever
    smarter text matching — a text-keyed dict, then a FIFO queue, then scan-forward — and
    each new rule invented a new way to hand out a *wrong* anchor. An anchor is a public
    citation locator, so the governing invariant here is: **emit a missing anchor, never a
    wrong one.**

    The rule that enforces it: consider each normalized heading text on its own. If
    trafilatura emitted exactly as many headings with that text as the raw parse found,
    the correspondence is forced — both lists are in document order, and the only
    order-preserving pairing of n items with n items is the identity — so the i-th
    trafilatura heading takes the i-th raw anchor. If the counts differ, at least one raw
    heading was dropped (or reworded past recognition) and there is no structural basis
    for choosing which survivor is which; every heading with that text gets `anchor=None`.
    Counting is per-text, so an ambiguous or mangled heading degrades only itself and
    cannot desync the rest of the document the way a shared queue could.

    **Precondition, and the only thing keeping this sound:** `raw_headings` must be a
    superset of trafilatura's headings. That means the raw parse must record every element
    trafilatura *can* emit as a `<head>` — not merely every `hN` tag, since it also
    synthesizes headings from `<summary>` and from Yoast's
    `<strong class="schema-faq-question">` (see `_promotable_level`) — and must filter
    none of them. Equal counts then genuinely mean "the same headings", because the only
    way to lose one is trafilatura dropping it. If the raw side can omit headings too, the
    two views can omit *different* ones, counts can coincide on headings that do not
    correspond, and this function will confidently return a wrong anchor. Both halves of
    that precondition have been violated before; see `_AnchorParser`'s docstring."""
    raw_counts = Counter(key for key, _level, _anchor in raw_headings)
    extracted_counts = Counter(_key(_element_text(element)) for element in elements
                               if element.tag == "head")
    aligned: dict[str, list[str | None]] = {}
    for key, _level, anchor in raw_headings:
        if raw_counts[key] == extracted_counts[key]:
            aligned.setdefault(key, []).append(anchor)
    return aligned


def extract_html(path: Path, *, source_id: str) -> ExtractedDocument:
    """Structure comes from trafilatura's own `<head rend="hN">` elements, not from
    guessing at markdown markup or matching body text against heading text: a block's
    identity as a heading is a structural fact from trafilatura, so a body paragraph is
    never structurally eligible to be mistaken for one, in either direction. `rend` gives
    the heading level directly. Raw-HTML text is only ever used afterwards, heading
    against heading, to recover an `id` for §4.3's web locators — trafilatura drops those.
    Where that recovery is ambiguous the anchor is simply omitted; see `_anchors_by_key`.

    Verified directly against the installed trafilatura (2.2.0) that this structural
    output only appears once a document is substantial enough, and typically wrapped in a
    landmark element (`<article>`/`<main>`), to trip its content-detection heuristics —
    the same prose flattens to bare `<p>` elements, with no `<head>` at all, inside a bare
    `<body>` with no such wrapper, or when the document is too small. That is treated
    below as a deliberate, fully-degraded document rather than patched around: every
    block becomes plain body text, the outline stays empty, and no heading is ever
    invented from it."""
    import trafilatura

    raw = path.read_text(encoding="utf-8", errors="replace")
    parser = _AnchorParser()
    parser.feed(raw)

    xml_text = trafilatura.extract(raw, output_format="xml", include_formatting=True,
                                   include_comments=False, include_tables=True,
                                   favor_recall=True, with_metadata=True)
    elements: list[ET.Element] = []
    if xml_text:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            root = None
        main = root.find("main") if root is not None else None
        if main is not None:
            elements = list(main)

    blocks: list[Block] = []
    outline: list[str] = []
    anchors = _anchors_by_key(parser.headings, elements)

    if not any(element.tag == "head" for element in elements):
        # Degenerate collapse (see docstring): no structural headings at all, so nothing
        # here can be trusted as a heading. Keep whatever prose trafilatura did extract,
        # but only ever as body text.
        for element in elements:
            text = _element_text(element)
            if text:
                blocks.append(Block(text=text))
    else:
        for element in elements:
            text = _element_text(element)
            if not text:
                continue
            if element.tag != "head":
                blocks.append(Block(text=text))
                continue
            level = _HEADINGS.get(element.get("rend", ""), _SYNTHESIZED_HEADING_LEVEL)
            candidates = anchors.get(_key(text))
            anchor = candidates.pop(0) if candidates else None
            outline.append(text)
            blocks.append(Block(text=text, heading_level=level, anchor=anchor))

    return ExtractedDocument(source_id=source_id, media_type="text/html", backend="trafilatura",
                             backend_version=trafilatura.__version__, page_count=0,
                             blocks=blocks, outline=outline)
