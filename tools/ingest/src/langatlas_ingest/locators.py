import re
import unicodedata
from dataclasses import dataclass
from langatlas_validate.locators import validate_locator_shape

EN_DASH = "–"

_PAGES = re.compile(r"^pp?\.\s+(\d+)(?:[–-](\d+))?$")
_NUMBERED = re.compile(r"^§(\d+(?:\.\d+)*)$")
_NAMED = re.compile(r"^(?:ch\.\s+(\d+)|§\s+(.+))$")
_DESIGN = re.compile(r"^([A-Za-z]+)\s+(\d+)(?:\s+§(.+))?$")
_REPO = re.compile(r"^([0-9a-f]{7}):([^#]+)#L(\d+)(?:-L(\d+))?$")
_MULTIPAGE = re.compile(r"^([^#]+)#([^#]+)$")
_FRAGMENT = re.compile(r"^#([^#]+)$")
_VIDEO = re.compile(r"^t=(\d{2}):(\d{2}):(\d{2})$")


def canonical_text(text: str) -> str:
    """The one canonical spelling of any heading-derived text: NFC, internal whitespace
    runs collapsed to a single space, stripped.

    This lives here, beside the comparison semantics, because it *is* part of them. Three
    copies of this rule used to exist (here, `qa._key`, `backends/html._key`) while the
    extraction backends applied only *part* of it — `pymupdf_backend` normalized and
    stripped but never collapsed, and its span joining (`" ".join(...)`) manufactures
    multi-space runs routinely: 975 of the real corpus's 1263 chunks carry a
    `section_path` entry with an internal whitespace run. The SQL side of the same join
    (`index.PostgresSourceChunksIndex._query`) compared only `lower(btrim(...))`, so a
    `named-section` citation matched neither the raw nor the collapsed spelling and the
    D24 verifier would have seen a true, well-sourced fact as unverifiable. The fix is to
    canonicalize once at extraction with this function; everything downstream then
    compares like with like."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def normalize_heading(text: str) -> str:
    """`canonical_text` plus case folding — the comparison key for heading text.
    Stored text keeps its case (it is a citation surface); only the key is lowered."""
    return canonical_text(text).lower()


@dataclass(frozen=True)
class LocatorRange:
    """A locator's *meaning*: whatever comparable parts its kind carries. 1A's
    `validate_locator_shape` owns the grammar; this owns the join semantics (§4.3:
    overlap, never string equality)."""

    kind: str
    pages: tuple[int, int] | None = None
    section_number: str | None = None
    heading: str | None = None
    doc_kind: str | None = None
    doc_number: int | None = None
    anchor: str | None = None
    path: str | None = None
    commit: str | None = None
    lines: tuple[int, int] | None = None
    seconds: tuple[int, int] | None = None


def parse_locator(locator: str, kind: str | None = None) -> LocatorRange:
    # Always derive the shape under 1A's full grammar precedence, even when a `kind`
    # is asserted: restricting the check to just the asserted kind (e.g. via
    # `allowed_kinds`) would re-run only that kind's regex in isolation and let an
    # ambiguous string — a repo-file locator also matches the multipage-docs pattern —
    # match whatever kind the caller asserts. Comparing against the *unrestricted*
    # result is what actually catches a caller asserting the wrong kind.
    actual_kind = validate_locator_shape(locator)
    if kind is None:
        kind = actual_kind
    elif kind != actual_kind:
        kind = None
    if kind is None:
        raise ValueError(f"locator {locator!r} does not match the §4.3 grammar")

    if kind == "book-page":
        match = _PAGES.match(locator)
        start = int(match.group(1))
        return LocatorRange(kind, pages=(start, int(match.group(2) or start)))
    if kind == "numbered-section":
        return LocatorRange(kind, section_number=_NUMBERED.match(locator).group(1))
    if kind == "named-section":
        match = _NAMED.match(locator)
        if match.group(1):
            return LocatorRange(kind, heading=normalize_heading(f"chapter {match.group(1)}"),
                                section_number=match.group(1))
        return LocatorRange(kind, heading=normalize_heading(match.group(2)))
    if kind == "design-doc":
        match = _DESIGN.match(locator)
        section = match.group(3)
        return LocatorRange(kind, doc_kind=match.group(1).lower(),
                            doc_number=int(match.group(2)),
                            heading=normalize_heading(section) if section else None)
    if kind == "repo-file":
        match = _REPO.match(locator)
        start = int(match.group(3))
        return LocatorRange(kind, commit=match.group(1), path=match.group(2),
                            lines=(start, int(match.group(4) or start)))
    if kind == "multipage-docs":
        match = _MULTIPAGE.match(locator)
        return LocatorRange(kind, path=match.group(1), anchor=match.group(2))
    if kind == "web-fragment":
        return LocatorRange(kind, anchor=_FRAGMENT.match(locator).group(1))
    if kind == "video":
        hours, minutes, seconds = (int(part) for part in _VIDEO.match(locator).groups())
        total = hours * 3600 + minutes * 60 + seconds
        return LocatorRange(kind, seconds=(total, total))
    raise ValueError(f"no parser for locator kind {kind!r}")


def _section_covers(outer: str | None, inner: str | None) -> bool:
    """§13 covers §13.2.1; §13.2 does not cover §13.20 — compare components, not strings."""
    if not outer or not inner:
        return False
    a, b = outer.split("."), inner.split(".")
    return a == b[:len(a)]


def _spans_overlap(a: tuple[int, int] | None, b: tuple[int, int] | None) -> bool:
    return bool(a and b and a[0] <= b[1] and b[0] <= a[1])


def _eq(a: object | None, b: object | None) -> bool:
    """Equality that requires an actual value on both sides. `None == None` is `True`
    in Python, which would let two unpopulated fields (e.g. a chunker bug that left a
    field empty) silently self-match instead of failing to overlap."""
    return a is not None and b is not None and a == b


def ranges_overlap(fact: LocatorRange, chunk: LocatorRange) -> bool:
    """True when a citation's locator is backed by a chunk's locator. Kinds must match:
    a page citation is never satisfied by a section chunk, since we cannot prove the
    section sits on that page without re-deriving it."""
    if fact.kind != chunk.kind:
        return False
    if fact.kind == "book-page":
        return _spans_overlap(fact.pages, chunk.pages)
    if fact.kind == "numbered-section":
        return (_eq(fact.section_number, chunk.section_number)
                or _section_covers(fact.section_number, chunk.section_number)
                or _section_covers(chunk.section_number, fact.section_number))
    if fact.kind == "named-section":
        return _eq(fact.heading, chunk.heading)
    if fact.kind == "design-doc":
        if not _eq(fact.doc_kind, chunk.doc_kind) or fact.doc_number != chunk.doc_number \
                or fact.doc_number is None:
            return False
        # A whole-document citation is backed by any section of that document.
        return fact.heading is None or _eq(fact.heading, chunk.heading)
    if fact.kind == "repo-file":
        return (_eq(fact.commit, chunk.commit) and _eq(fact.path, chunk.path)
                and _spans_overlap(fact.lines, chunk.lines))
    if fact.kind == "multipage-docs":
        return _eq(fact.path, chunk.path) and _eq(fact.anchor, chunk.anchor)
    if fact.kind == "web-fragment":
        return _eq(fact.anchor, chunk.anchor)
    if fact.kind == "video":
        return _spans_overlap(fact.seconds, chunk.seconds)
    return False


def format_pages(start: int, end: int) -> str:
    """Machine-produced, §4.3-shaped, en dash — never hand-authored (D37)."""
    return f"p. {start}" if start == end else f"pp. {start}{EN_DASH}{end}"


def format_section(section: str) -> str:
    return f"§{section}" if re.fullmatch(r"\d+(\.\d+)*", section) else f"§ {section}"
