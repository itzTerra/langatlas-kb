import pytest
from langatlas_ingest.benchmark.relevance import (
    Span, load_expected_spans, make_span_relevance, overlaps, span_of,
)
from langatlas_ingest.store import SourceChunk


def _chunk(chunk_id="s#c1", source_id="s", section_path=("3", "3.1"),
           page_start=None, page_end=None):
    return SourceChunk(chunk_id=chunk_id, source_id=source_id, ordinal=1,
                       parent_section_id=None, section_path=list(section_path),
                       breadcrumb=" > ".join(section_path), locator="x",
                       locator_kind="numbered-section", page_start=page_start,
                       page_end=page_end, section_number=None, anchor=None,
                       line_start=None, line_end=None, text="body", token_count=3)


def test_span_of_reads_both_coordinate_systems():
    span = span_of(_chunk(page_start=10, page_end=12))
    assert span == Span("s", ("3", "3.1"), 10, 12)


def test_a_different_source_never_overlaps():
    assert overlaps(Span("a", ("1",), 1, 2), Span("b", ("1",), 1, 2)) is False


def test_page_ranges_overlap_inclusively():
    expected = Span("s", ("3",), 10, 12)
    assert overlaps(expected, Span("s", ("9",), 12, 15)) is True    # touching at 12
    assert overlaps(expected, Span("s", ("9",), 13, 15)) is False
    assert overlaps(expected, Span("s", ("3",), 1, 2)) is False     # pages win when both


def test_section_path_decides_when_either_side_has_no_pages():
    expected = Span("s", ("3", "3.1"), None, None)
    assert overlaps(expected, Span("s", ("3", "3.1"), 1, 2)) is True
    assert overlaps(expected, Span("s", ("3", "3.2"), 1, 2)) is False


def test_an_ancestor_section_counts_as_covering_a_descendant():
    # A larger chunk size merges subsections upward; the merged chunk still contains the
    # passage the golden entry pointed at.
    expected = Span("s", ("3", "3.1", "3.1.2"), None, None)
    assert overlaps(expected, Span("s", ("3", "3.1"), None, None)) is True
    assert overlaps(expected, Span("s", ("4",), None, None)) is False


def test_span_relevance_falls_back_to_source_matching_for_survey_entries():
    relevant = make_span_relevance({})
    entry = {"id": "q", "expected_sources": ["s"]}
    assert relevant(entry, _chunk(source_id="s")) is True
    assert relevant(entry, _chunk(source_id="other")) is False


def test_span_relevance_uses_the_loaded_spans_for_chunk_entries():
    relevant = make_span_relevance({"q": {"s#c1": Span("s", ("3", "3.1"), None, None)}})
    entry = {"id": "q", "expected_chunks": ["s#c1"]}
    assert relevant(entry, _chunk(section_path=("3", "3.1"))) is True
    assert relevant(entry, _chunk(section_path=("7",))) is False


def test_span_relevance_scopes_to_the_ids_named_in_expected_chunks():
    # Finding I5: `eval._score` asks about one expected id at a time by substituting a
    # single-element `expected_chunks` — that must check only that id's span, not every
    # span ever resolved for the entry's id, or distinct-coverage recall could not tell
    # two different expected chunks apart.
    relevant = make_span_relevance({"q": {"s#c1": Span("s", ("3",), None, None),
                                          "s#c2": Span("s", ("9",), None, None)}})
    full_entry = {"id": "q", "expected_chunks": ["s#c1", "s#c2"]}
    only_c1 = {"id": "q", "expected_chunks": ["s#c1"]}
    candidate = _chunk(section_path=("9",))    # overlaps s#c2's span only

    assert relevant(full_entry, candidate) is True     # some declared id covers it
    assert relevant(only_c1, candidate) is False       # but not the one named here


def test_an_entry_with_no_resolvable_span_matches_nothing():
    # Better a hard zero for one query than a silent fallback to source-level matching,
    # which would inflate an exact-term query into a hit-rate.
    relevant = make_span_relevance({})
    assert relevant({"id": "q", "expected_chunks": ["s#c1"]}, _chunk()) is False


@pytest.mark.db
def test_load_expected_spans_resolves_against_the_production_corpus(searchable):
    # `searchable` (from tests/test_search.py's pattern) seeds sources "s" and "t" with
    # book-page chunks; import the fixture into this module's conftest rather than
    # re-seeding, so the span rule is exercised against real stored rows.
    spans = load_expected_spans(searchable, [{"id": "q",
                                              "expected_chunks": ["s#c00000"]}])
    assert spans["q"]["s#c00000"].source_id == "s"
    assert spans["q"]["s#c00000"].page_start == 1


@pytest.mark.db
def test_an_unresolvable_chunk_id_is_simply_absent(searchable):
    assert load_expected_spans(searchable,
                               [{"id": "q", "expected_chunks": ["nope#c1"]}]) == {}
