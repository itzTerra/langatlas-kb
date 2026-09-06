import pytest
from langatlas_ingest.benchmark.metrics import IndexStats, corpus_size, table_bytes


def test_index_stats_derive_their_rates():
    stats = IndexStats(model="m", chunks=100, tokens=50_000, embed_seconds=10.0,
                       chunks_per_second=None, tokens_per_second=None,
                       truncated_chunks=7, cached_vectors=0, throughput_honest=True,
                       table_bytes=1_000_000, bytes_per_chunk=None, dimensions=384)
    payload = stats.as_dict()
    assert payload["truncated_chunks"] == 7
    assert payload["throughput_honest"] is True


def test_rates_are_none_when_nothing_was_embedded():
    from langatlas_ingest.benchmark.metrics import derive_rates

    stats = derive_rates(IndexStats(model="m", chunks=0, tokens=0, embed_seconds=0.0,
                                    chunks_per_second=None, tokens_per_second=None,
                                    truncated_chunks=0, cached_vectors=0,
                                    throughput_honest=True, table_bytes=0,
                                    bytes_per_chunk=None, dimensions=4))
    assert stats.chunks_per_second is None and stats.bytes_per_chunk is None


def test_rates_are_computed_when_work_happened():
    from langatlas_ingest.benchmark.metrics import derive_rates

    stats = derive_rates(IndexStats(model="m", chunks=100, tokens=1000,
                                    embed_seconds=4.0, chunks_per_second=None,
                                    tokens_per_second=None, truncated_chunks=0,
                                    cached_vectors=0, throughput_honest=True,
                                    table_bytes=800, bytes_per_chunk=None,
                                    dimensions=4))
    assert stats.chunks_per_second == 25.0
    assert stats.tokens_per_second == 250.0
    assert stats.bytes_per_chunk == 8.0


def test_throughput_is_marked_dishonest_when_the_cache_served_anything():
    from langatlas_ingest.benchmark.metrics import derive_rates

    stats = derive_rates(IndexStats(model="m", chunks=100, tokens=1000,
                                    embed_seconds=0.01, chunks_per_second=None,
                                    tokens_per_second=None, truncated_chunks=0,
                                    cached_vectors=40, throughput_honest=True,
                                    table_bytes=800, bytes_per_chunk=None,
                                    dimensions=4))
    assert stats.throughput_honest is False


@pytest.mark.db
def test_corpus_size_sums_chunks_and_tokens(searchable):
    chunks, tokens = corpus_size(searchable, ["s"])
    assert chunks > 0 and tokens > 0
    assert corpus_size(searchable, ["absent"]) == (0, 0)


@pytest.mark.db
def test_table_bytes_reports_zero_for_a_missing_table(db_conn):
    assert table_bytes(db_conn, "source_chunk_emb_nothing_here") == 0


@pytest.mark.db
def test_embed_and_measure_reads_the_counters_off_the_context(searchable, fake_ctx):
    # `fake_ctx` never truncates, so this pins the plumbing rather than the arithmetic:
    # the stats must read the counters off the context, not recompute them.
    from langatlas_ingest.benchmark.metrics import embed_and_measure
    from langatlas_ingest.config import IngestConfig

    fake_ctx.truncations = 3
    stats = embed_and_measure(fake_ctx, searchable, model="fake-model", sources=["s"],
                              config=IngestConfig.load(), truncate=True)
    assert stats.model == "fake-model"
    assert stats.chunks > 0
    assert stats.table_bytes > 0
    assert stats.truncated_chunks == 0     # nothing changed *during* the pass
    assert stats.dimensions == 4


@pytest.mark.db
def test_throughput_is_dishonest_when_a_prior_arm_already_embedded_everything(
        searchable, fake_ctx):
    # Finding I2/I3: the `searchable` fixture already ran `embed_source` once for
    # `config.embedding_model` (see conftest), so re-running `embed_and_measure` for
    # that SAME model against the same corpus finds nothing pending — `embed_source`
    # does zero work, `cached_vectors` stays 0 (no embed call happened at all to record
    # a cache hit), and the old logic reported `honest=True` despite having embedded
    # nothing this round.
    from langatlas_ingest.benchmark.metrics import embed_and_measure
    from langatlas_ingest.config import IngestConfig

    config = IngestConfig.load()

    # A model nothing has embedded yet: every chunk in the corpus is embedded fresh.
    fresh = embed_and_measure(fake_ctx, searchable, model="brand-new-model",
                              sources=["s"], config=config)
    assert fresh.chunks > 0
    assert fresh.throughput_honest is True

    # The corpus's default model was already fully embedded by the `searchable` fixture
    # before this test ran — this arm's `embed_source` call finds nothing pending.
    stale = embed_and_measure(fake_ctx, searchable, model=config.embedding_model,
                              sources=["s"], config=config)
    assert stale.chunks > 0
    assert stale.cached_vectors == 0           # no embed call happened at all
    assert stale.throughput_honest is False    # yet zero fresh embedding was done
