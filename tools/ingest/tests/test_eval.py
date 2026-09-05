import pytest
from langatlas_ingest.chunker import Chunk
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import migrate
from langatlas_ingest.embed import embed_source
from langatlas_ingest.errors import GoldenEntryInvalid
from langatlas_ingest.eval import run_eval
from langatlas_ingest.store import SourceChunksStore

pytestmark = pytest.mark.db

CONFIG = IngestConfig.load(overrides={"retrieval_k": 5, "retrieval_candidates": 10})

TEXTS = ["Lazy evaluation defers a computation until its value is demanded.",
         "Call-by-need memoizes the delayed computation on first demand.",
         "Pattern matching destructures a value against a sequence of patterns."]


@pytest.fixture
def corpus(db_conn, fake_ctx):
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("ctm", [
        Chunk(chunk_id=f"ctm#c{i:05d}", source_id="ctm", ordinal=i,
              parent_section_id="ctm#s0001", section_path=["Ch"], breadcrumb="Ch",
              locator=f"p. {i + 1}", locator_kind="book-page", text=text, token_count=12,
              content_hash=f"h{i}", page_start=i + 1, page_end=i + 1)
        for i, text in enumerate(TEXTS)])
    embed_source(fake_ctx, db_conn, config=CONFIG)
    return db_conn


def write_golden(tmp_path, entries):
    path = tmp_path / "queries-test.yaml"
    lines = ["queries:"]
    for entry in entries:
        lines += [f"  - id: {entry['id']}", "    band: exact-term",
                  f"    query: {entry['query']}",
                  f"    expected_chunks: {entry['expected_chunks']}"]
    path.write_text("\n".join(lines) + "\n")
    return tmp_path


def test_a_perfect_run_scores_one(corpus, fake_ctx, tmp_path):
    golden = write_golden(tmp_path, [
        {"id": "q1", "query": "pattern matching destructures",
         "expected_chunks": ["ctm#c00002"]}])
    result = run_eval(corpus, fake_ctx, golden_dir=golden, config=CONFIG)
    assert result.queries == 1
    assert result.recall_at_5 == 1.0 and result.mrr == 1.0


def test_a_miss_scores_zero(corpus, fake_ctx, tmp_path):
    golden = write_golden(tmp_path, [
        {"id": "q1", "query": "pattern matching destructures",
         "expected_chunks": ["ctm#c99999"]}])
    result = run_eval(corpus, fake_ctx, golden_dir=golden, config=CONFIG)
    assert result.recall_at_5 == 0.0 and result.mrr == 0.0


def test_the_example_file_is_ignored(corpus, fake_ctx, tmp_path):
    (tmp_path / "queries.example.yaml").write_text(
        "queries:\n  - id: x\n    band: exact-term\n    query: y\n"
        "    expected_chunks: ['nope']\n")
    result = run_eval(corpus, fake_ctx, golden_dir=tmp_path, config=CONFIG)
    assert result.queries == 0


def test_an_empty_golden_set_is_not_an_error(corpus, fake_ctx, tmp_path):
    """Stage 1C ships the harness empty; Stage 2 fills it. Zero queries must report
    zero queries, not crash and not silently claim a perfect score."""
    result = run_eval(corpus, fake_ctx, golden_dir=tmp_path, config=CONFIG)
    assert result.queries == 0
    assert result.recall_at_5 is None and result.mrr is None
    assert result.golden_dir_missing is False    # tmp_path exists; just has no queries


def test_source_level_expectations_are_supported(corpus, fake_ctx, tmp_path):
    path = tmp_path / "queries-src.yaml"
    path.write_text("queries:\n  - id: q\n    band: exact-term\n"
                    "    query: lazy evaluation\n    expected_sources: ['ctm']\n")
    result = run_eval(corpus, fake_ctx, golden_dir=tmp_path, config=CONFIG)
    assert result.recall_at_5 == 1.0


def test_a_malformed_golden_entry_raises_a_named_error(corpus, fake_ctx, tmp_path):
    """A hand-authored entry with a typo'd key (`expected_chunk`, not `expected_chunks`)
    must fail loudly and name the entry, not silently contribute a 0.0 that looks like a
    plausible bad score (Section 8.6's real 40-60-query set is hand-authored)."""
    path = tmp_path / "queries-bad.yaml"
    path.write_text("queries:\n  - id: bad-entry\n    band: exact-term\n"
                    "    query: pattern matching\n    expected_chunk: ['ctm#c00002']\n")
    with pytest.raises(GoldenEntryInvalid) as exc_info:
        run_eval(corpus, fake_ctx, golden_dir=tmp_path, config=CONFIG)
    assert "bad-entry" in str(exc_info.value)


def test_a_golden_entry_with_both_expectation_keys_is_rejected(corpus, fake_ctx, tmp_path):
    """Regression test: an entry that sets both `expected_chunks` and `expected_sources`
    used to let source-only hits inflate the chunk-based recall@5/nDCG denominator above
    1.0 (5 hits all matching `expected_sources` but none matching `expected_chunks` used
    to score recall5=5.0). Rather than give dual-key entries a bespoke union semantics,
    `run_eval` rejects them outright — this pins that rejection, not a bounded score."""
    path = tmp_path / "queries-dual.yaml"
    path.write_text("queries:\n  - id: dual-key\n    band: exact-term\n"
                    "    query: lazy evaluation\n    expected_chunks: ['ctm#c00000']\n"
                    "    expected_sources: ['ctm']\n")
    with pytest.raises(GoldenEntryInvalid) as exc_info:
        run_eval(corpus, fake_ctx, golden_dir=tmp_path, config=CONFIG)
    assert "dual-key" in str(exc_info.value)


def test_a_missing_golden_directory_is_distinguishable_from_an_empty_one(
        corpus, fake_ctx, tmp_path):
    """A typo'd or moved --golden-dir must not read the same as the harness's genuinely
    empty pre-Stage-2 state (test_an_empty_golden_set_is_not_an_error, above)."""
    result = run_eval(corpus, fake_ctx, golden_dir=tmp_path / "does-not-exist",
                      config=CONFIG)
    assert result.queries == 0
    assert result.golden_dir_missing is True
    assert "WARNING" in result.to_markdown()


def test_rerank_can_be_switched_off_for_the_no_rerank_arm(corpus, fake_ctx, tmp_path):
    """§8.6 asks for a rerank-vs-no-rerank comparison, which the harness could not run at
    all while it always built its search with the configured default. It is also the cost
    question: with reranking on, every query spends a completion round-trip per 8
    candidates, so a 60-query set is hundreds of sequential calls."""
    golden = write_golden(tmp_path, [
        {"id": "q1", "query": "pattern matching destructures",
         "expected_chunks": ["ctm#c00002"]}])

    run_eval(corpus, fake_ctx, golden_dir=golden, config=CONFIG, rerank=False)
    assert fake_ctx.rerank_calls == []

    run_eval(corpus, fake_ctx, golden_dir=golden, config=CONFIG, rerank=True)
    assert len(fake_ctx.rerank_calls) == 1


def test_depth_50_reports_recall_at_50_against_the_real_corpus(db_conn, fake_ctx, tmp_path):
    """§8.6's pre-rerank pool measurement, exercised against real search SQL rather than
    a stub. `_score` only reports recall@50 when the run actually retrieved 50 hits, so
    this needs a corpus with at least that many chunks — the shared 3-chunk `corpus`
    fixture cannot exercise it."""
    migrate(db_conn)
    texts = [f"Filler sentence number {i} about lazy evaluation and pattern matching."
             for i in range(59)]
    texts.append("Pattern matching destructures a value against a sequence of patterns.")
    SourceChunksStore(db_conn).replace_source("ctm", [
        Chunk(chunk_id=f"ctm#c{i:05d}", source_id="ctm", ordinal=i,
              parent_section_id="ctm#s0001", section_path=["Ch"], breadcrumb="Ch",
              locator=f"p. {i + 1}", locator_kind="book-page", text=text, token_count=12,
              content_hash=f"h{i}", page_start=i + 1, page_end=i + 1)
        for i, text in enumerate(texts)])
    embed_source(fake_ctx, db_conn, config=CONFIG)
    golden = write_golden(tmp_path, [
        {"id": "q1", "query": "pattern matching destructures",
         "expected_chunks": [f"ctm#c{len(texts) - 1:05d}"]}])

    shallow = run_eval(db_conn, fake_ctx, golden_dir=golden, config=CONFIG, depth=10)
    assert shallow.recall_at_50 is None

    deep = run_eval(db_conn, fake_ctx, golden_dir=golden, config=CONFIG, depth=50)
    assert deep.recall_at_50 == 1.0


def test_corpus_sources_scopes_out_queries_against_the_real_corpus(corpus, fake_ctx,
                                                                    tmp_path):
    """The pilot corpus only ingests a subset of sources; a golden query expecting a
    source outside `corpus_sources` must be skipped rather than scored as a miss —
    verified here against real search execution, not a stub, since the skip decision
    has to happen before a query the corpus cannot possibly answer is ever searched."""
    golden = write_golden(tmp_path, [
        {"id": "answerable", "query": "pattern matching destructures",
         "expected_chunks": ["ctm#c00002"]},
        {"id": "unanswerable", "query": "something else entirely",
         "expected_chunks": ["other-source#c00000"]}])

    result = run_eval(corpus, fake_ctx, golden_dir=golden, config=CONFIG,
                      corpus_sources=["ctm"])

    assert result.queries == 1
    assert result.skipped_queries == 1
    assert result.recall_at_5 == 1.0
    assert [entry["skipped"] for entry in result.per_query] == [False, True]


def test_rerank_defaults_to_the_configured_flag(corpus, fake_ctx, tmp_path):
    """Absent an explicit argument the decision stays with `models.rerank_default_on` —
    the same opt-out shape the CLI uses, never a silent override of the config."""
    golden = write_golden(tmp_path, [
        {"id": "q1", "query": "lazy evaluation", "expected_chunks": ["ctm#c00000"]}])
    off = IngestConfig.load(overrides={"retrieval_k": 5, "retrieval_candidates": 10,
                                       "rerank_default_on": False})

    run_eval(corpus, fake_ctx, golden_dir=golden, config=off)
    assert fake_ctx.rerank_calls == []

    run_eval(corpus, fake_ctx, golden_dir=golden, config=CONFIG)
    assert len(fake_ctx.rerank_calls) == 1
