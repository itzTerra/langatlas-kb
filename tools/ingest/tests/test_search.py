# tools/ingest/tests/test_search.py
import random
import pytest
from langatlas_ingest.chunker import Chunk
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import ensure_embedding_table, migrate
from langatlas_ingest.embed import embed_source, vector_literal
from langatlas_ingest.search import SourceSearch
from langatlas_ingest.store import SourceChunksStore

pytestmark = pytest.mark.db

CONFIG = IngestConfig.load(overrides={"retrieval_k": 3, "retrieval_candidates": 10})

TEXTS = [
    "Lazy evaluation defers a computation until its value is demanded.",
    "Call-by-need is the implementation strategy that memoizes a delayed computation.",
    "A type system assigns types to terms and rejects ill-typed programs.",
    "Pattern matching destructures a value against a sequence of patterns.",
]


def make_chunks(source_id="s"):
    return [Chunk(chunk_id=f"{source_id}#c{i:05d}", source_id=source_id, ordinal=i,
                  parent_section_id=f"{source_id}#s000{i // 2}", section_path=["Ch"],
                  breadcrumb="Ch", locator=f"p. {i + 1}", locator_kind="book-page",
                  text=text, token_count=len(text) // 4, content_hash=f"h{i}",
                  page_start=i + 1, page_end=i + 1)
            for i, text in enumerate(TEXTS)]


@pytest.fixture
def searchable(db_conn, fake_ctx):
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("s", make_chunks())
    SourceChunksStore(db_conn).replace_source("t", make_chunks("t"))
    embed_source(fake_ctx, db_conn, config=CONFIG)
    return db_conn


def test_search_returns_at_most_k_hits(searchable, fake_ctx):
    hits = SourceSearch(searchable, fake_ctx, config=CONFIG).search("lazy evaluation")
    assert 0 < len(hits) <= CONFIG.retrieval_k
    assert all(hit.chunk.text for hit in hits)


def test_lexical_matches_are_found_by_the_fts_branch(searchable, fake_ctx):
    hits = SourceSearch(searchable, fake_ctx, config=CONFIG,
                        rerank=False).search("pattern matching destructures")
    assert hits[0].chunk.text.startswith("Pattern matching")
    assert hits[0].fts_rank == 1


def test_source_filter_is_applied_before_ranking(searchable, fake_ctx):
    hits = SourceSearch(searchable, fake_ctx, config=CONFIG, rerank=False).search(
        "lazy evaluation", source_ids=["t"])
    assert hits and {hit.chunk.source_id for hit in hits} == {"t"}


def test_reranker_is_default_on_and_reorders(searchable, fake_ctx):
    fake_ctx.rerank_scores = [0.1, 0.9, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.05]
    hits = SourceSearch(searchable, fake_ctx, config=CONFIG).search("lazy evaluation")
    assert fake_ctx.rerank_calls, "D15 ratified the reranker default-on"
    assert hits[0].rerank_score == max(hit.rerank_score for hit in hits)


def test_rerank_can_be_switched_off(searchable, fake_ctx):
    SourceSearch(searchable, fake_ctx, config=CONFIG, rerank=False).search("types")
    assert fake_ctx.rerank_calls == []


def test_get_section_expands_small_to_big(searchable, fake_ctx):
    search = SourceSearch(searchable, fake_ctx, config=CONFIG)
    section = search.get_section("s#c00000", expand="parent")
    assert [chunk.chunk_id for chunk in section] == ["s#c00000", "s#c00001"]


def test_get_section_can_return_just_the_chunk(searchable, fake_ctx):
    search = SourceSearch(searchable, fake_ctx, config=CONFIG)
    assert [c.chunk_id for c in search.get_section("s#c00000", expand="none")] == ["s#c00000"]


def test_get_section_on_an_unknown_chunk_is_empty(searchable, fake_ctx):
    assert SourceSearch(searchable, fake_ctx, config=CONFIG).get_section("nope") == []


def test_a_query_matching_nothing_returns_nothing(searchable, fake_ctx):
    search = SourceSearch(searchable, fake_ctx, config=CONFIG, rerank=False)
    assert search.search("zzzz", source_ids=["nonexistent-source"]) == []


# --- pinned beyond the brief --------------------------------------------------------

def test_the_vector_branch_casts_both_sides_to_halfvec(searchable, fake_ctx):
    """pgvector caps HNSW at 2000 dimensions, so `ensure_embedding_table` builds the
    index on a `halfvec` cast. A query comparing plain `vector`s does not match that
    expression index and silently degrades to a sequential scan on every search."""
    search = SourceSearch(searchable, fake_ctx, config=CONFIG)
    sql, _ = search.build_query("lazy", vector="[0,0,0,0]", k=3, source_ids=None)
    assert "embedding::halfvec(4) <=>" in sql
    assert "::halfvec(4)\n" in sql or "::halfvec(4) " in sql
    assert "::vector" not in sql


def test_the_vector_branch_uses_the_hnsw_index(searchable, fake_ctx):
    """EXPLAIN is the only honest proof the cast lines up with the ruled index."""
    search = SourceSearch(searchable, fake_ctx, config=CONFIG)
    sql, params = search.build_query("lazy", vector="[0.5,0,0,0]", k=3, source_ids=None)
    with searchable.cursor() as cur:
        # Plain `SET`, not `SET LOCAL`: `db_conn` is autocommit, so there is no
        # transaction for `LOCAL` to scope to and it would silently do nothing. The
        # tiny fixture table is cheaper to seq-scan, so the planner needs the nudge to
        # show whether the index is *usable* at all — which is the question here.
        cur.execute("SET enable_seqscan = off")
        cur.execute("EXPLAIN " + sql, params)
        plan = "\n".join(row[0] for row in cur.fetchall())
        cur.execute("RESET enable_seqscan")
    assert "_hnsw" in plan, plan


@pytest.fixture
def wide_corpus(db_conn):
    """More chunks than pgvector's default `hnsw.ef_search` of 40, so the cap is
    observable. Embeddings are seeded directly with *distinct* random vectors rather
    than through `fake_ctx`, whose stub embedder collapses many texts onto the same
    (and sometimes zero) vector — degenerate input makes an ANN cap unobservable."""
    migrate(db_conn)
    chunks = [Chunk(chunk_id=f"w#c{i:05d}", source_id="w", ordinal=i,
                    parent_section_id=None, section_path=["Ch"], breadcrumb="Ch",
                    locator=f"p. {i + 1}", locator_kind="book-page",
                    text=f"chunk number {i} about lazy evaluation and types",
                    token_count=8, content_hash=f"h{i}", page_start=i + 1, page_end=i + 1)
              for i in range(120)]
    SourceChunksStore(db_conn).replace_source("w", chunks)
    table = ensure_embedding_table(db_conn, CONFIG.embedding_model, 4)
    rng = random.Random(20260814)
    with db_conn.cursor() as cur:
        cur.executemany(
            f"INSERT INTO {table} (chunk_id, embedding) VALUES (%s, %s::vector)",
            [(chunk.chunk_id, vector_literal([rng.random() for _ in range(4)]))
             for chunk in chunks])
        cur.execute(f"ANALYZE {table}")
        cur.execute("ANALYZE source_chunks")
    return db_conn


def test_ef_search_is_raised_to_the_configured_candidate_pool(wide_corpus, fake_ctx):
    """pgvector's `hnsw.ef_search` defaults to 40 and hard-caps how many rows an HNSW
    scan returns regardless of LIMIT. Without raising it, `retrieval.candidates: 50`
    silently yields a 40-row pre-rerank pool — and any future raise of the config value
    would be clamped invisibly, shrinking recall below what is configured."""
    config = IngestConfig.load(overrides={"retrieval_k": 5, "retrieval_candidates": 90})
    search = SourceSearch(wide_corpus, fake_ctx, config=config, rerank=False)
    _, params = search.build_query("lazy", vector="[0.5,0,0,0]", k=5, source_ids=None)
    sql = f"""
        SELECT count(*) FROM (
            SELECT e.chunk_id
            FROM source_chunk_emb_qwen3_embedding_4b e
            ORDER BY e.embedding::halfvec(4) <=> %(vector)s::halfvec(4)
            LIMIT 90
        ) probe
    """
    with wide_corpus.cursor() as cur:
        cur.execute("SET enable_seqscan = off")     # force the HNSW path, where the cap bites
        cur.execute(sql, params)
        capped = cur.fetchone()[0]
        assert capped == 40, f"expected pgvector's default cap, got {capped}"

        search.tune_ef_search(cur, k=5)
        cur.execute("SHOW hnsw.ef_search")
        assert int(cur.fetchone()[0]) == 90
        cur.execute(sql, params)
        assert cur.fetchone()[0] == 90, "the configured candidate pool must be reached"
        cur.execute("RESET enable_seqscan")


def test_ef_search_never_drops_below_pgvectors_default(searchable, fake_ctx):
    """A small `candidates` must not *reduce* recall below stock pgvector, and the GUC
    has a documented ceiling of 1000."""
    with searchable.cursor() as cur:
        small = IngestConfig.load(overrides={"retrieval_candidates": 5})
        assert SourceSearch(searchable, fake_ctx, config=small).tune_ef_search(cur, k=5) == 40
        huge = IngestConfig.load(overrides={"retrieval_candidates": 50_000})
        assert SourceSearch(searchable, fake_ctx, config=huge).tune_ef_search(cur, k=5) == 1000


def test_search_raises_ef_search_on_its_own_connection(wide_corpus, fake_ctx):
    """The GUC fix has to be wired into `search()`, not merely available on the class."""
    config = IngestConfig.load(overrides={"retrieval_k": 5, "retrieval_candidates": 90})
    SourceSearch(wide_corpus, fake_ctx, config=config, rerank=False).search("lazy")
    with wide_corpus.cursor() as cur:
        cur.execute("SHOW hnsw.ef_search")
        assert int(cur.fetchone()[0]) == 90


def test_the_pre_rerank_pool_is_the_configured_candidate_count(wide_corpus, fake_ctx):
    """Observed end to end: the reranker is handed the whole candidate pool, so the
    number of documents it receives *is* the pool size §8.1 configures."""
    config = IngestConfig.load(overrides={"retrieval_k": 5, "retrieval_candidates": 90})
    SourceSearch(wide_corpus, fake_ctx, config=config).search("lazy evaluation")
    assert len(fake_ctx.rerank_calls[0][1]) == 90


def test_a_hit_found_by_only_one_branch_still_scores(searchable, fake_ctx):
    """RRF fuses *ranks*, and a chunk absent from a branch simply contributes nothing
    from it — it must not drop out and must not produce a NULL score."""
    hits = SourceSearch(searchable, fake_ctx, config=CONFIG, rerank=False).search(
        "lazy evaluation", k=10)
    vector_only = [hit for hit in hits if hit.fts_rank is None]
    assert vector_only, "the vector branch returns every chunk; some match no FTS term"
    for hit in vector_only:
        assert hit.vector_rank is not None
        assert hit.score == pytest.approx(1.0 / (CONFIG.rrf_k + hit.vector_rank))


def test_rrf_ranks_each_branch_independently(searchable, fake_ctx):
    """Both ranks present => the score is the sum of the two reciprocals, never a
    raw-score blend."""
    hits = SourceSearch(searchable, fake_ctx, config=CONFIG, rerank=False).search(
        "lazy evaluation computation", k=10)
    fused = [hit for hit in hits if hit.fts_rank and hit.vector_rank]
    assert fused
    for hit in fused:
        assert hit.score == pytest.approx(1.0 / (CONFIG.rrf_k + hit.fts_rank)
                                          + 1.0 / (CONFIG.rrf_k + hit.vector_rank))
    assert sorted({hit.fts_rank for hit in hits if hit.fts_rank}) == \
        list(range(1, len({hit.fts_rank for hit in hits if hit.fts_rank}) + 1))


def test_the_relevance_floor_drops_weak_hits(searchable, fake_ctx):
    config = IngestConfig.load(overrides={"retrieval_k": 3, "retrieval_candidates": 10,
                                          "relevance_floor": 1.0})
    assert SourceSearch(searchable, fake_ctx, config=config,
                        rerank=False).search("lazy evaluation") == []


def test_k_zero_returns_nothing_without_calling_a_provider(searchable, fake_ctx):
    """`k=0` is an honest 'give me nothing', not a fallback to the configured default —
    and it must not spend an embedding call to find that out."""
    fake_ctx.embed_calls.clear()
    assert SourceSearch(searchable, fake_ctx, config=CONFIG).search("lazy", k=0) == []
    assert fake_ctx.embed_calls == []


def test_search_over_an_empty_corpus_is_empty(db_conn, fake_ctx):
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("s", make_chunks())
    embed_source(fake_ctx, db_conn, config=CONFIG)
    SourceChunksStore(db_conn).delete_source("s")
    assert SourceSearch(db_conn, fake_ctx, config=CONFIG).search("anything") == []


def test_rerank_defaults_to_the_configured_flag(searchable, fake_ctx):
    off = IngestConfig.load(overrides={"rerank_default_on": False})
    assert SourceSearch(searchable, fake_ctx, config=off).rerank is False
    on = IngestConfig.load(overrides={"rerank_default_on": True})
    assert SourceSearch(searchable, fake_ctx, config=on).rerank is True
    assert SourceSearch(searchable, fake_ctx, config=on, rerank=False).rerank is False


def test_get_section_of_a_top_level_chunk_returns_just_it(searchable, fake_ctx):
    with searchable.cursor() as cur:
        cur.execute("UPDATE source_chunks SET parent_section_id = NULL"
                    " WHERE chunk_id = 's#c00000'")
    search = SourceSearch(searchable, fake_ctx, config=CONFIG)
    assert [c.chunk_id for c in search.get_section("s#c00000")] == ["s#c00000"]


def test_get_section_returns_full_chunk_text(searchable, fake_ctx):
    search = SourceSearch(searchable, fake_ctx, config=CONFIG)
    assert [c.text for c in search.get_section("s#c00000")] == TEXTS[:2]
