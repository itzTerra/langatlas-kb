from langatlas_ingest.benchmark.pilot import (
    PilotSelection, select_pilot, source_frequency,
)

ENTRIES = [
    {"id": "a", "band": "exact-term", "expected_chunks": ["s1#c1"]},
    {"id": "b", "band": "exact-term", "expected_chunks": ["s1#c2"]},
    {"id": "c", "band": "paraphrase-concept", "expected_chunks": ["s2#c1"]},
    {"id": "d", "band": "cross-source-survey", "expected_sources": ["s1", "s2"]},
    {"id": "e", "band": "cross-source-survey", "expected_sources": ["s1", "s3"]},
    {"id": "f", "band": "exact-term", "expected_chunks": ["s4#c1"]},
]


def test_source_frequency_counts_both_expectation_kinds():
    assert source_frequency(ENTRIES) == {"s1": 4, "s2": 2, "s3": 1, "s4": 1}


def test_select_pilot_maximises_fully_covered_queries():
    selection = select_pilot(ENTRIES, size=2)
    assert selection.sources == ("s1", "s2")
    # a, b, c, d — e needs s3, f needs s4.
    assert (selection.covered, selection.total) == (4, 6)


def test_a_survey_query_counts_only_when_every_source_is_present():
    # s1 alone covers a and b but not d: a survey is not half-surveyable.
    assert select_pilot(ENTRIES, size=1).covered == 2


def test_per_band_breakdown_is_reported():
    assert select_pilot(ENTRIES, size=2).per_band == {
        "exact-term": 2, "paraphrase-concept": 1, "cross-source-survey": 1}


def test_available_restricts_the_candidate_pool():
    selection = select_pilot(ENTRIES, size=2, available=["s2", "s3", "s4"])
    assert "s1" not in selection.sources


def test_a_larger_size_than_the_source_pool_is_clamped():
    selection = select_pilot(ENTRIES, size=99)
    assert set(selection.sources) == {"s1", "s2", "s3", "s4"}
    assert selection.covered == 6


def test_ties_break_deterministically_on_the_sorted_source_names():
    entries = [{"id": "x", "band": "exact-term", "expected_chunks": ["b#c1"]},
               {"id": "y", "band": "exact-term", "expected_chunks": ["a#c1"]}]
    assert select_pilot(entries, size=1).sources == ("a",)


def test_markdown_names_the_coverage():
    text = PilotSelection(("s1",), 2, 6, {"exact-term": 2}).to_markdown()
    assert "s1" in text and "2/6" in text


def test_the_committed_golden_set_selects_the_ratified_pilot():
    from langatlas_ingest.eval import load_entries
    from langatlas_ingest.paths import GOLDEN_RETRIEVAL_DIR

    selection = select_pilot(load_entries(GOLDEN_RETRIEVAL_DIR), size=4)
    assert selection.sources == ("rust-fls", "rust-reference", "scott-plp",
                                 "sebesta-copl")
    assert (selection.covered, selection.total) == (37, 52)
    assert selection.per_band == {"exact-term": 16, "paraphrase-concept": 16,
                                  "cross-source-survey": 5}
