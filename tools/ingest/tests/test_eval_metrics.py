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

    recalls, reciprocal_rank, ndcg, first = _score(entry, hits)

    assert recalls[5] == pytest.approx(2 / 3)
    assert recalls[5] != 1.0                     # the hit-rate bug's answer
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

    recalls, _, ndcg, _ = _score(entry, hits)

    assert recalls[5] == pytest.approx(1 / 5)
    assert ndcg < 1.0


def test_a_perfect_multi_chunk_run_still_scores_one():
    """All 3 declared-relevant chunks land in the top 3 — recall and nDCG both hit their
    ceiling, same as the single-chunk boundary cases in test_eval.py."""
    entry = {"id": "q", "expected_chunks": ["A", "B", "C"]}
    hits = [_hit("A"), _hit("B"), _hit("C")] + [_hit(f"n{i}") for i in range(7)]

    recalls, reciprocal_rank, ndcg, first = _score(entry, hits)

    assert recalls[5] == 1.0 and reciprocal_rank == 1.0 and ndcg == pytest.approx(1.0)
    assert first == 0


def test_expected_sources_keeps_hit_rate_semantics_by_design():
    """Source-level entries have no declared relevant *count* (you don't generally know
    how many chunks of a source are "relevant"), so — unlike `expected_chunks` — this
    intentionally stays a hit-rate: any top-5 hit from a listed source scores 1.0."""
    entry = {"id": "q", "expected_sources": ["stub-source"]}
    hits = [_hit("A"), _hit("B")]

    recalls, _, _, _ = _score(entry, hits)

    assert recalls[5] == 1.0


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
    union semantics nobody asked for — closes it for good.

    `_score`'s recall clamp (`min(1.0, found / len(relevant_ids))`, added alongside the
    depth axis so a re-chunked corpus with several retrieved chunks mapping to one
    expected chunk cannot itself exceed 1.0) happens to also cap this dual-key entry's
    recall at 1.0 — but nDCG's IDCG is still built from the 1-chunk denominator while 5
    flags fire, so nDCG > 1.0 survives as the demonstrated defect `_validate` exists to
    stop from ever being scored."""
    entry = {"id": "dual-key", "expected_chunks": ["A"], "expected_sources": ["stub-source"]}

    with pytest.raises(GoldenEntryInvalid) as exc_info:
        _validate(entry)
    assert "dual-key" in str(exc_info.value)

    # Demonstrate what the pre-fix arithmetic actually did, so the regression this
    # closes is on the record even though `_validate` now stops it before `_score` runs.
    hits = [_hit(f"n{i}") for i in range(5)]     # none match expected_chunks == ["A"]
    recalls, _, ndcg, _ = _score(entry, hits)    # all 5 match expected_sources
    assert recalls[5] == 1.0 and ndcg > 1.0      # nDCG is the bug the rejection prevents


def test_an_entry_with_either_expectation_key_validates_cleanly():
    _validate({"id": "ok1", "expected_chunks": ["A"]})
    _validate({"id": "ok2", "expected_sources": ["s"]})


from langatlas_ingest.eval import EvalResult, expected_sources_of, run_eval


def test_expected_sources_reads_both_expectation_kinds():
    assert expected_sources_of({"expected_chunks": ["scott-plp#c00417"]}) == {"scott-plp"}
    assert expected_sources_of({"expected_sources": ["a", "b"]}) == {"a", "b"}


class _StubSearch:
    """Returns a fixed ranked list, so the metric arithmetic is tested without a
    database or a provider — the same posture the existing metric tests take."""

    def __init__(self, hits):
        self.hits = hits
        self.queries = []

    def search(self, query, *, k=None, source_ids=None):
        self.queries.append((query, k))
        return self.hits[:k]


def _search_hit(chunk_id, source_id):
    """Named distinctly from the module's `_hit(chunk_id)` helper above (single-source,
    `_score`-only stubs) — this one carries a `source_id` too, since it goes through
    `run_eval`/`SourceSearch`'s hit shape, not `_score` directly."""
    from types import SimpleNamespace

    return SimpleNamespace(chunk=SimpleNamespace(chunk_id=chunk_id, source_id=source_id))


def test_recall_at_50_is_reported_only_at_depth_50(tmp_path, fake_ctx):
    (tmp_path / "queries-t.yaml").write_text(
        "queries:\n  - id: q1\n    band: exact-term\n    query: x\n"
        "    expected_chunks: ['s#c2']\n")
    hits = [_search_hit(f"s#c{i}", "s") for i in range(60)]

    shallow = run_eval(None, fake_ctx, golden_dir=tmp_path, depth=10,
                       search=_StubSearch(hits))
    assert shallow.recall_at_50 is None
    assert shallow.recall_at_5 == 1.0        # s#c2 is rank 3

    deep = run_eval(None, fake_ctx, golden_dir=tmp_path, depth=50,
                    search=_StubSearch(hits))
    assert deep.recall_at_50 == 1.0


def test_a_chunk_outside_the_top_5_but_inside_the_top_50_separates_the_two(tmp_path,
                                                                           fake_ctx):
    (tmp_path / "queries-t.yaml").write_text(
        "queries:\n  - id: q1\n    band: exact-term\n    query: x\n"
        "    expected_chunks: ['s#c40']\n")
    hits = [_search_hit(f"s#c{i}", "s") for i in range(60)]
    result = run_eval(None, fake_ctx, golden_dir=tmp_path, depth=50,
                      search=_StubSearch(hits))
    assert result.recall_at_5 == 0.0
    assert result.recall_at_50 == 1.0


def test_queries_outside_the_corpus_are_skipped_not_missed(tmp_path, fake_ctx):
    (tmp_path / "queries-t.yaml").write_text(
        "queries:\n"
        "  - id: in\n    band: exact-term\n    query: x\n"
        "    expected_chunks: ['s#c1']\n"
        "  - id: out\n    band: exact-term\n    query: y\n"
        "    expected_chunks: ['other#c1']\n")
    result = run_eval(None, fake_ctx, golden_dir=tmp_path, depth=10,
                      corpus_sources=["s"], search=_StubSearch([_search_hit("s#c1", "s")]))
    assert result.queries == 1               # only the scorable one counts
    assert result.skipped_queries == 1
    assert result.recall_at_5 == 1.0         # not dragged to 0.5 by an unanswerable query
    assert [entry["skipped"] for entry in result.per_query] == [False, True]


def test_a_survey_query_needs_every_listed_source_present(tmp_path, fake_ctx):
    (tmp_path / "queries-t.yaml").write_text(
        "queries:\n  - id: q\n    band: cross-source-survey\n    query: x\n"
        "    expected_sources: ['s', 'other']\n")
    result = run_eval(None, fake_ctx, golden_dir=tmp_path, depth=10,
                      corpus_sources=["s"], search=_StubSearch([_search_hit("s#c1", "s")]))
    # Scoring it against a corpus holding half its sources would report a hit rate for a
    # survey that cannot be surveyed.
    assert (result.queries, result.skipped_queries) == (0, 1)


def test_an_injected_relevance_predicate_overrides_chunk_id_matching(tmp_path, fake_ctx):
    (tmp_path / "queries-t.yaml").write_text(
        "queries:\n  - id: q\n    band: exact-term\n    query: x\n"
        "    expected_chunks: ['s#c1']\n")
    # Chunk ids do not match at all; the predicate says the first hit is relevant anyway,
    # which is exactly what a re-chunked corpus needs.
    result = run_eval(None, fake_ctx, golden_dir=tmp_path, depth=10,
                      search=_StubSearch([_search_hit("s#c999", "s")]),
                      relevance=lambda entry, chunk: chunk.chunk_id == "s#c999")
    assert result.recall_at_5 == 1.0


def test_as_dict_round_trips_every_reported_metric():
    payload = EvalResult(queries=3, recall_at_5=0.5, mrr=0.4, ndcg_at_10=0.6,
                         recall_at_50=0.9, latency_p50_ms=12.0,
                         skipped_queries=2).as_dict()
    assert payload["recall_at_50"] == 0.9
    assert payload["skipped_queries"] == 2
    assert payload["queries"] == 3
    _validate({"id": "ok2", "expected_sources": ["s"]})
