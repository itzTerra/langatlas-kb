"""Pure metric-arithmetic tests for `langatlas_ingest.eval._score` — deliberately not
`db`-marked, and deliberately not going through `run_eval`/`SourceSearch` at all, because
the two bugs these pin (recall_at_5 computing hit-rate instead of a real fraction, and
nDCG@10's IDCG being normalized by what was retrieved instead of what the golden entry
declares) are invisible to single-expected-chunk cases, where both the buggy and correct
formulas happen to agree. A multi-chunk `expected_chunks` entry with a partial hit at
non-trivial ranks is the only kind of case that can tell them apart, so that is what these
construct — using the same hand-computed scenario the code review verified by hand.
"""
import pytest
from dataclasses import dataclass
from langatlas_ingest.errors import GoldenEntryInvalid
from langatlas_ingest.eval import _score, _validate


@dataclass
class _StubChunk:
    chunk_id: str
    source_id: str = "stub-source"


@dataclass
class _StubHit:
    chunk: _StubChunk


def _hit(chunk_id: str) -> _StubHit:
    return _StubHit(chunk=_StubChunk(chunk_id=chunk_id))


def test_recall_at_5_is_a_real_fraction_not_a_hit_rate():
    """3 relevant chunks declared; only 2 (A, B) land in the top 5, C is never retrieved.
    A hit-rate formula ("any relevant chunk in the top 5?") scores this 1.0, identical to
    a query that surfaced all 3 — that collapse is exactly the bug. True recall is 2/3."""
    entry = {"id": "q1", "expected_chunks": ["A", "B", "C"]}
    hits = [_hit("X"), _hit("A"), _hit("Y"), _hit("B"), _hit("Z"),
           _hit("n1"), _hit("n2"), _hit("n3"), _hit("n4"), _hit("n5")]

    recall5, reciprocal_rank, ndcg, first = _score(entry, hits)

    assert recall5 == pytest.approx(2 / 3)
    assert recall5 != 1.0                     # the hit-rate bug's answer
    assert reciprocal_rank == pytest.approx(0.5)   # first hit (A) at rank 1, 0-indexed
    assert first == 1


def test_ndcg_at_10_is_penalized_for_a_relevant_chunk_never_retrieved():
    """Same ranking as above. IDCG must be built from the declared relevant count (3,
    capped at 10) so missing C entirely costs something. The old code built IDCG from
    `sum(flags)` (2, the count *found*), which hand-computes to 0.651 — a materially
    inflated score that can never be penalized for a chunk that was never retrieved at
    all. The correct value, hand-verified independently, is ~0.498."""
    entry = {"id": "q1", "expected_chunks": ["A", "B", "C"]}
    hits = [_hit("X"), _hit("A"), _hit("Y"), _hit("B"), _hit("Z"),
           _hit("n1"), _hit("n2"), _hit("n3"), _hit("n4"), _hit("n5")]

    _, _, ndcg, _ = _score(entry, hits)

    assert ndcg == pytest.approx(0.4981, abs=1e-4)
    assert ndcg != pytest.approx(0.6512, abs=1e-4)   # the found-only-IDCG bug's answer


def test_a_query_that_finds_one_of_five_relevant_chunks_is_not_a_perfect_score():
    """The clearest illustration of the IDCG bug: finding exactly 1 of 5 declared
    relevant chunks, at rank 0, scored a perfect 1.000 under the old formula (IDCG built
    from the 1 chunk found) even though 4 relevant chunks were missed entirely."""
    entry = {"id": "q", "expected_chunks": ["A", "B", "C", "D", "E"]}
    hits = [_hit("A")] + [_hit(f"n{i}") for i in range(9)]

    recall5, _, ndcg, _ = _score(entry, hits)

    assert recall5 == pytest.approx(1 / 5)
    assert ndcg < 1.0


def test_a_perfect_multi_chunk_run_still_scores_one():
    """All 3 declared-relevant chunks land in the top 3 — recall and nDCG both hit their
    ceiling, same as the single-chunk boundary cases in test_eval.py."""
    entry = {"id": "q", "expected_chunks": ["A", "B", "C"]}
    hits = [_hit("A"), _hit("B"), _hit("C")] + [_hit(f"n{i}") for i in range(7)]

    recall5, reciprocal_rank, ndcg, first = _score(entry, hits)

    assert recall5 == 1.0 and reciprocal_rank == 1.0 and ndcg == pytest.approx(1.0)
    assert first == 0


def test_expected_sources_keeps_hit_rate_semantics_by_design():
    """Source-level entries have no declared relevant *count* (you don't generally know
    how many chunks of a source are "relevant"), so — unlike `expected_chunks` — this
    intentionally stays a hit-rate: any top-5 hit from a listed source scores 1.0."""
    entry = {"id": "q", "expected_sources": ["stub-source"]}
    hits = [_hit("A"), _hit("B")]

    recall5, _, _, _ = _score(entry, hits)

    assert recall5 == 1.0


def test_an_entry_missing_both_expectation_keys_raises_a_named_error():
    """A hand-authored golden entry with a typo'd key (`expected_chunk` instead of
    `expected_chunks`) must not silently score 0.0 — it must fail loudly, naming the
    entry, so a Stage 2 QA skim notices the typo instead of trusting a plausible-looking
    bad number."""
    entry = {"id": "typo-entry", "expected_chunk": ["A"]}

    with pytest.raises(GoldenEntryInvalid) as exc_info:
        _validate(entry)
    assert "typo-entry" in str(exc_info.value)


def test_an_entry_with_both_expectation_keys_is_rejected():
    """Regression: `_score` picks the chunk branch (denominator = len(expected_chunks))
    the moment `expected_chunks` is truthy, but `_relevant` — used to build the ranking
    flags `_score` reads — also matches on `expected_sources`. Before this validation
    existed, an entry declaring both let source-only hits inflate the chunk-based
    numerator past the chunk-based denominator: 1 declared chunk plus 5 top hits that all
    match a declared source scored recall5 = 5.0 and nDCG > 1.0, both nonsensical for a
    [0, 1] metric. `queries.example.yaml` used to model exactly this (now fixed to show
    the two kinds as separate entries), so a Stage 2 author copying the template would
    have walked straight into it. Rejecting the shape outright — rather than inventing a
    union semantics nobody asked for — closes it for good."""
    entry = {"id": "dual-key", "expected_chunks": ["A"], "expected_sources": ["stub-source"]}

    with pytest.raises(GoldenEntryInvalid) as exc_info:
        _validate(entry)
    assert "dual-key" in str(exc_info.value)

    # Demonstrate what the pre-fix arithmetic actually did, so the regression this
    # closes is on the record even though `_validate` now stops it before `_score` runs.
    hits = [_hit(f"n{i}") for i in range(5)]     # none match expected_chunks == ["A"]
    recall5, _, ndcg, _ = _score(entry, hits)    # all 5 match expected_sources
    assert recall5 == 5.0 and ndcg > 1.0         # the bug this test's rejection prevents


def test_an_entry_with_either_expectation_key_validates_cleanly():
    _validate({"id": "ok1", "expected_chunks": ["A"]})
    _validate({"id": "ok2", "expected_sources": ["s"]})
