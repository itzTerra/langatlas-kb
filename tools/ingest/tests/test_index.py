# tools/ingest/tests/test_index.py
import pytest
from langatlas_ingest.chunker import Chunk
from langatlas_ingest.db import migrate
from langatlas_ingest.index import PostgresSourceChunksIndex
from langatlas_ingest.locators import LocatorRange, parse_locator, ranges_overlap
from langatlas_ingest.store import SourceChunksStore
from langatlas_validate.locators import validate_locator

pytestmark = pytest.mark.db


def chunk(ordinal, **overrides):
    data = dict(chunk_id=f"s#c{ordinal:05d}", source_id="s", ordinal=ordinal,
                parent_section_id="s#s0001", section_path=["Types"], breadcrumb="Types",
                locator="p. 10", locator_kind="book-page", text="body", token_count=1,
                content_hash="h", page_start=10, page_end=12)
    data.update(overrides)
    return Chunk(**data)


@pytest.fixture
def index(db_conn):
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("s", [
        chunk(0),                                                     # pages 10-12
        chunk(1, page_start=20, page_end=20, locator="p. 20"),
        chunk(2, section_number="13.2.1", locator="§13.2.1", locator_kind="numbered-section",
              section_path=["13 Types", "13.2 Subtyping"], page_start=None, page_end=None),
        chunk(3, anchor="match-guards", locator="#match-guards", locator_kind="web-fragment",
              section_path=["Match expressions"], page_start=None, page_end=None),
    ])
    return PostgresSourceChunksIndex(db_conn)


def test_page_citations_resolve_by_overlap_not_equality(index):
    assert index.resolve("s", "p. 11") == ["s#c00000"]        # inside 10-12, not equal
    assert index.resolve("s", "pp. 12–20") == ["s#c00000", "s#c00001"]
    assert index.resolve("s", "p. 15") == []


def test_section_citations_resolve_by_containment(index):
    assert index.resolve("s", "§13") == ["s#c00002"]
    assert index.resolve("s", "§13.2.1") == ["s#c00002"]
    assert index.resolve("s", "§14") == []


def test_named_sections_resolve_against_the_section_path(index):
    assert index.resolve("s", "§ Match expressions") == ["s#c00003"]
    assert index.resolve("s", "§ 13.2 Subtyping") == ["s#c00002"]


def test_web_fragments_resolve_by_anchor(index):
    assert index.resolve("s", "#match-guards") == ["s#c00003"]
    assert index.resolve("s", "#nonexistent") == []


def test_resolution_is_scoped_to_the_cited_source(index):
    assert index.resolve("other-source", "p. 11") == []


def test_an_ungrammatical_locator_resolves_to_nothing(index):
    """A malformed locator is 1A's `validate_locator_shape` failure to report, not an
    exception here — the resolver's job is only to say 'no chunk backs this'."""
    assert index.resolve("s", "page eleven") == []


def test_1as_validate_locator_accepts_this_index(index):
    result = validate_locator("p. 11", "s", index)
    assert result.shape_ok and result.resolved
    assert result.chunk_ids == ["s#c00000"]

    missing = validate_locator("p. 15", "s", index)
    assert missing.shape_ok and not missing.resolved


# --- boundary and cross-implementation pinning (beyond the brief) -------------------

def test_touching_page_ranges_overlap_and_adjacent_ones_do_not(index):
    """Task 5 pinned `ranges_overlap` on touching ranges; the SQL join must agree.
    10-12 touches 12-14 at a single page, and stops short of 13-14."""
    assert index.resolve("s", "pp. 12–14") == ["s#c00000"]
    assert index.resolve("s", "pp. 13–14") == []
    assert index.resolve("s", "pp. 1–100") == ["s#c00000", "s#c00001"]


def test_section_containment_does_not_leak_across_sibling_numbers(index):
    """`§13.2` covers `§13.2.1` but must never match `§13.20` — component comparison,
    not string prefix (the boundary `locators._section_covers` was written for)."""
    assert index.resolve("s", "§13.2") == ["s#c00002"]
    assert index.resolve("s", "§1") == []
    assert index.resolve("s", "§13.20") == []


def test_a_video_locator_resolves_to_nothing_rather_than_raising(index):
    """1C has no transcript extractor, so a video citation parks in the sourcing queue."""
    assert index.resolve("s", "t=00:01:30") == []


@pytest.fixture
def doc_index(db_conn):
    """The three kinds whose SQL clause is *weaker* than `ranges_overlap`. Kept in their
    own source so the page/section fixtures above stay unperturbed."""
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("doc", [
        chunk(0, chunk_id="doc#c00000", source_id="doc", locator="PEP 8 §Indentation",
              locator_kind="design-doc", section_path=["Indentation"],
              page_start=None, page_end=None),
        chunk(1, chunk_id="doc#c00001", source_id="doc",
              locator="a1b2c3d:src/x.py#L10-L20", locator_kind="repo-file",
              anchor="src/x.py", line_start=10, line_end=20,
              section_path=[], page_start=None, page_end=None),
        chunk(2, chunk_id="doc#c00002", source_id="doc", locator="guide/intro#setup",
              locator_kind="multipage-docs", anchor="setup",
              section_path=[], page_start=None, page_end=None),
    ])
    return PostgresSourceChunksIndex(db_conn)


def _chunk_range(row):
    """The chunk's comparable range, built from its *columns* — the authoritative span.
    Returns None for a chunk whose kind carries nothing comparable."""
    if row.page_start is not None:
        return LocatorRange("book-page", pages=(row.page_start, row.page_end))
    if row.section_number is not None:
        return LocatorRange("numbered-section", section_number=row.section_number)
    if row.locator_kind == "design-doc":
        kind, number = row.locator.split(" ")[0], row.locator.split(" ")[1]
        heading = row.section_path[0].lower() if row.section_path else None
        return LocatorRange("design-doc", doc_kind=kind.lower(), doc_number=int(number),
                            heading=heading)
    if row.locator_kind == "repo-file":
        return LocatorRange("repo-file", commit=row.locator.split(":")[0],
                            path=row.anchor, lines=(row.line_start, row.line_end))
    if row.locator_kind == "multipage-docs":
        return LocatorRange("multipage-docs", path=row.locator.split("#")[0],
                            anchor=row.anchor)
    if row.anchor is not None:
        return LocatorRange("web-fragment", anchor=row.anchor)
    return None


def test_design_doc_citations_resolve_by_heading(doc_index):
    assert doc_index.resolve("doc", "PEP 8 §Indentation") == ["doc#c00000"]
    assert doc_index.resolve("doc", "PEP 8 §Whitespace") == []


def test_repo_file_and_multipage_citations_resolve_on_their_own_terms(doc_index):
    assert doc_index.resolve("doc", "a1b2c3d:src/x.py#L11") == ["doc#c00001"]
    assert doc_index.resolve("doc", "a1b2c3d:src/x.py#L30") == []
    assert doc_index.resolve("doc", "guide/intro#setup") == ["doc#c00002"]
    assert doc_index.resolve("doc", "guide/intro#teardown") == []


def test_design_doc_identity_diverges_from_ranges_overlap(doc_index):
    """KNOWN GAP (docstring #3): a whole-document citation is `TRUE`, so the document's
    own identity is never checked. `PEP 484` cited against a source that is PEP 8
    resolves to every chunk of it. Pinned so the gap is visible, not discovered later
    by a wrong fact in the public record."""
    everything = ["doc#c00000", "doc#c00001", "doc#c00002"]
    assert doc_index.resolve("doc", "RFC 1") == everything
    assert doc_index.resolve("doc", "PEP 484") == everything

    fact = parse_locator("PEP 484")
    chunk_range = _chunk_range(SourceChunksStore(doc_index.conn).get("doc#c00000"))
    assert ranges_overlap(fact, chunk_range) is False, "the divergence being pinned"


def test_heading_qualified_design_doc_citations_are_identity_blind_too(doc_index):
    """KNOWN GAP (docstring #3), the half that looks safe and is not: a *section*-qualified
    design-doc citation still never checks the document. `RFC 2119 §Indentation` compiles
    to the same `section_path` clause as `PEP 8 §Indentation` and resolves against the
    PEP 8 chunk — precision in the citation's shape, none in the join."""
    assert doc_index.resolve("doc", "RFC 2119 §Indentation") == ["doc#c00000"]
    assert doc_index.resolve("doc", "PEP 8 §Indentation") == ["doc#c00000"]

    fact = parse_locator("RFC 2119 §Indentation")
    assert (fact.doc_kind, fact.doc_number) == ("rfc", 2119)
    chunk_range = _chunk_range(SourceChunksStore(doc_index.conn).get("doc#c00000"))
    assert (chunk_range.doc_kind, chunk_range.doc_number) == ("pep", 8)
    assert ranges_overlap(fact, chunk_range) is False, "the divergence being pinned"


def test_repo_file_commit_is_ignored_and_diverges_from_ranges_overlap(doc_index):
    """KNOWN GAP (docstring #4): there is no `commit` column in source_chunks, so a
    citation at a different commit still resolves. Line numbers move between commits,
    so this can attach a fact to the wrong lines."""
    assert doc_index.resolve("doc", "ffffff0:src/x.py#L11") == ["doc#c00001"]

    fact = parse_locator("ffffff0:src/x.py#L11")
    chunk_range = _chunk_range(SourceChunksStore(doc_index.conn).get("doc#c00001"))
    assert chunk_range.commit == "a1b2c3d"
    assert ranges_overlap(fact, chunk_range) is False, "the divergence being pinned"


def test_multipage_path_is_ignored_and_diverges_from_ranges_overlap(doc_index):
    """KNOWN GAP (docstring #4): the clause is `anchor = %s` alone, so two different
    pages sharing a fragment id resolve to each other."""
    assert doc_index.resolve("doc", "other/page#setup") == ["doc#c00002"]

    fact = parse_locator("other/page#setup")
    chunk_range = _chunk_range(SourceChunksStore(doc_index.conn).get("doc#c00002"))
    assert chunk_range.path == "guide/intro"
    assert ranges_overlap(fact, chunk_range) is False, "the divergence being pinned"


@pytest.mark.parametrize("locator", ["PEP 8 §Indentation", "PEP 8 §Whitespace",
                                     "a1b2c3d:src/x.py#L11", "a1b2c3d:src/x.py#L30",
                                     "guide/intro#setup", "guide/intro#teardown"])
def test_sql_agrees_with_ranges_overlap_where_no_gap_applies(doc_index, locator):
    """The same oracle as below, restricted to citations that do NOT exercise one of the
    two known gaps — for these, SQL and `ranges_overlap` must still agree exactly."""
    fact = parse_locator(locator)
    expected = [row.chunk_id for row in SourceChunksStore(doc_index.conn).by_source("doc")
                if (chunk_range := _chunk_range(row)) and ranges_overlap(fact, chunk_range)]
    assert doc_index.resolve("doc", locator) == expected


@pytest.mark.parametrize("locator", ["p. 11", "pp. 12–20", "p. 15", "pp. 12–14",
                                     "pp. 13–14", "§13", "§13.2", "§13.20", "§14",
                                     "#match-guards", "#nonexistent"])
def test_sql_resolution_agrees_with_ranges_overlap(index, locator):
    """The SQL in `index.py` and `locators.ranges_overlap` are two expressions of the
    same §4.3 rule; this pins them together so neither can drift. The chunk's range is
    built from its *columns* (the authoritative span), not from its display locator —
    a chunk shown as `p. 10` may cover pages 10-12."""
    fact = parse_locator(locator)
    expected = []
    for chunk_row in SourceChunksStore(index.conn).by_source("s"):
        if chunk_row.page_start is not None:
            chunk_range = LocatorRange("book-page",
                                       pages=(chunk_row.page_start, chunk_row.page_end))
        elif chunk_row.section_number is not None:
            chunk_range = LocatorRange("numbered-section",
                                       section_number=chunk_row.section_number)
        elif chunk_row.anchor is not None:
            chunk_range = LocatorRange("web-fragment", anchor=chunk_row.anchor)
        else:
            continue
        if ranges_overlap(fact, chunk_range):
            expected.append(chunk_row.chunk_id)
    assert index.resolve("s", locator) == expected
