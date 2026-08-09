import pytest
from langatlas_ingest.locators import (
    LocatorRange, format_pages, format_section, parse_locator, ranges_overlap,
)
from langatlas_validate.locators import validate_locator_shape


@pytest.mark.parametrize("locator,kind", [
    ("p. 4", "book-page"),
    ("pp. 492–495", "book-page"),
    ("§13.2.1", "numbered-section"),
    ("§ Match expressions", "named-section"),
    ("ch. 7", "named-section"),
    ("PEP 634 §Overview", "design-doc"),
    ("a1b2c3d:src/lib.rs#L10-L25", "repo-file"),
    ("reference/expressions.html#match-guards", "multipage-docs"),
    ("#match-expressions", "web-fragment"),
    ("t=00:41:20", "video"),
])
def test_every_grammar_row_parses(locator, kind):
    assert validate_locator_shape(locator) == kind       # 1A owns the shape
    assert parse_locator(locator).kind == kind           # 1C owns the meaning


def test_page_ranges_overlap_inclusively():
    fact = parse_locator("pp. 492–495")
    assert ranges_overlap(fact, parse_locator("p. 493"))
    assert ranges_overlap(fact, parse_locator("pp. 495–500"))
    assert not ranges_overlap(fact, parse_locator("p. 496"))


def test_section_numbers_overlap_by_prefix():
    """A fact citing §13 is backed by a chunk in §13.2.1; §13.2 and §13.20 are not
    the same section, so the comparison is component-wise, not string prefix."""
    assert ranges_overlap(parse_locator("§13"), parse_locator("§13.2.1"))
    assert ranges_overlap(parse_locator("§13.2.1"), parse_locator("§13"))
    assert not ranges_overlap(parse_locator("§13.2"), parse_locator("§13.20"))
    assert not ranges_overlap(parse_locator("§13"), parse_locator("§14.1"))


def test_named_sections_compare_case_and_space_insensitively():
    assert ranges_overlap(parse_locator("§ Match Expressions"),
                          parse_locator("§ match   expressions"))
    assert not ranges_overlap(parse_locator("§ Match expressions"),
                              parse_locator("§ Loop expressions"))


def test_design_doc_locators_compare_doc_then_section():
    assert ranges_overlap(parse_locator("PEP 634"), parse_locator("PEP 634 §Overview"))
    assert not ranges_overlap(parse_locator("PEP 634 §Overview"),
                              parse_locator("PEP 634 §Rationale"))
    assert not ranges_overlap(parse_locator("PEP 634"), parse_locator("PEP 635"))


def test_repo_locators_need_the_same_commit_and_overlapping_lines():
    fact = parse_locator("a1b2c3d:src/lib.rs#L10-L25")
    assert ranges_overlap(fact, parse_locator("a1b2c3d:src/lib.rs#L20-L40"))
    assert not ranges_overlap(fact, parse_locator("a1b2c3d:src/lib.rs#L26-L40"))
    assert not ranges_overlap(fact, parse_locator("9999999:src/lib.rs#L10-L25"))
    assert not ranges_overlap(fact, parse_locator("a1b2c3d:src/main.rs#L10-L25"))


def test_web_locators_compare_path_then_fragment():
    assert ranges_overlap(parse_locator("ref/expr.html#guards"),
                          parse_locator("ref/expr.html#guards"))
    assert not ranges_overlap(parse_locator("ref/expr.html#guards"),
                              parse_locator("ref/expr.html#arms"))
    assert ranges_overlap(parse_locator("#guards"), parse_locator("#guards"))


def test_video_timestamps_land_inside_a_chunk_window():
    chunk = LocatorRange(kind="video", seconds=(2400, 2600))
    assert ranges_overlap(parse_locator("t=00:41:20"), chunk)     # 2480s
    assert not ranges_overlap(parse_locator("t=00:20:00"), chunk)


def test_different_kinds_never_overlap():
    assert not ranges_overlap(parse_locator("p. 4"), parse_locator("§13"))


def test_an_ungrammatical_locator_raises():
    with pytest.raises(ValueError, match="does not match"):
        parse_locator("page four")


def test_a_locator_range_with_no_pages_never_overlaps():
    """Boundary not covered above: a book-page range missing its pages (e.g. hand-built,
    not parsed) must never be treated as overlapping anything, including itself."""
    empty = LocatorRange(kind="book-page")
    assert not ranges_overlap(empty, parse_locator("p. 4"))
    assert not ranges_overlap(parse_locator("p. 4"), empty)
    assert not ranges_overlap(empty, empty)


def test_formatters_emit_shapes_1a_accepts():
    assert format_pages(4, 4) == "p. 4"
    assert format_pages(492, 495) == "pp. 492–495"           # en dash, per §4.3
    assert validate_locator_shape(format_pages(492, 495)) == "book-page"
    assert format_section("13.2.1") == "§13.2.1"
    assert format_section("Match expressions") == "§ Match expressions"
    assert validate_locator_shape(format_section("Match expressions")) == "named-section"


@pytest.mark.parametrize("kind", [
    "named-section", "numbered-section", "design-doc", "multipage-docs", "web-fragment",
])
def test_an_all_none_range_never_overlaps_itself(kind):
    """A chunk whose locator fields failed to populate (e.g. a chunker bug) must never
    silently self-match on two empty fields — that would attach a fact to a passage on
    the strength of nothing at all."""
    empty = LocatorRange(kind=kind)
    assert not ranges_overlap(empty, empty)


def test_parse_locator_accepts_an_explicit_kind_that_actually_matches():
    result = parse_locator("§13.2.1", kind="numbered-section")
    assert result.kind == "numbered-section"
    assert result.section_number == "13.2.1"


def test_parse_locator_rejects_an_explicit_kind_that_does_not_match():
    """The `kind` parameter lets a caller skip re-deriving the shape, but the caller is
    asserting that shape — a repo-file string like "a1b2c3d:src/lib.rs#L10-L25" happens
    to also match the multipage-docs regex (`[^#]+#[^#]+`), so without re-validation this
    would silently mis-parse instead of raising."""
    with pytest.raises(ValueError, match="does not match"):
        parse_locator("a1b2c3d:src/lib.rs#L10-L25", kind="multipage-docs")
    with pytest.raises(ValueError, match="does not match"):
        parse_locator("page four", kind="book-page")
