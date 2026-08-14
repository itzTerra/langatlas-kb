import pytest
from langatlas_ingest.chunker import Chunk
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import ensure_embedding_table, migrate
from langatlas_ingest.embed import embed_source, vector_literal
from langatlas_ingest.store import SourceChunksStore

pytestmark = pytest.mark.db

CONFIG = IngestConfig.load()


def make_chunk(ordinal: int, source_id: str = "s") -> Chunk:
    return Chunk(chunk_id=f"{source_id}#c{ordinal:05d}", source_id=source_id, ordinal=ordinal,
                 parent_section_id=f"{source_id}#s0001", section_path=["Ch"], breadcrumb="Ch",
                 locator=f"p. {ordinal + 1}", locator_kind="book-page",
                 text=f"chunk {ordinal}", token_count=3, content_hash=f"h{ordinal}",
                 page_start=ordinal + 1, page_end=ordinal + 1)


def test_vector_literal_is_pgvector_shaped():
    assert vector_literal([1.0, 0.5]) == "[1.0,0.5]"


def test_embed_source_fills_the_per_model_table(db_conn, fake_ctx):
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("s", [make_chunk(i) for i in range(3)])

    assert embed_source(fake_ctx, db_conn, source_id="s", config=CONFIG) == 3

    table = ensure_embedding_table(db_conn, CONFIG.embedding_model, fake_ctx.dimensions)
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")
        assert cur.fetchone()[0] == 3


def test_embedding_is_resumable_and_never_redoes_work(db_conn, fake_ctx):
    """`SourceChunksStore.replace_source` (Task 7) is a whole-source DELETE + re-insert,
    and the embedding table's `chunk_id` is `REFERENCES source_chunks(chunk_id) ON DELETE
    CASCADE` (Task 2) — so re-ingesting a source, even to add one chunk, cascade-deletes
    every embedding row for that source, not just the changed ones (verified against the
    real store: see task-9-report.md). Resumability instead has to be demonstrated the
    way it actually happens: a run that embeds some chunks and is then interrupted before
    the rest are done. A second `embed_source` call must pick up only what
    `unembedded()` still reports as missing, and must not re-embed what already has a
    vector row."""
    migrate(db_conn)
    store = SourceChunksStore(db_conn)
    store.replace_source("s", [make_chunk(0), make_chunk(1), make_chunk(2)])
    table = ensure_embedding_table(db_conn, CONFIG.embedding_model, fake_ctx.dimensions)
    zero_vector = vector_literal([0.0] * fake_ctx.dimensions)
    with db_conn.cursor() as cur:
        # Simulate a prior run that embedded chunks 0 and 1 before being interrupted.
        cur.executemany(
            f"INSERT INTO {table} (chunk_id, embedding) VALUES (%s, %s::vector)",
            [("s#c00000", zero_vector), ("s#c00001", zero_vector)])

    assert embed_source(fake_ctx, db_conn, source_id="s", config=CONFIG) == 1
    assert [text for call in fake_ctx.embed_calls for text in call] == ["chunk 2"]


def test_reingesting_a_source_forces_a_full_reembed(db_conn, fake_ctx):
    """The flip side of the cascade behaviour documented above: since `replace_source`
    deletes and recreates every row for a source, a re-ingest (even one that only adds
    a chunk) throws away the old embeddings for the whole source, and `embed_source`
    must re-embed all of them — this is the real, demonstrated behaviour, not a gap in
    `embed_source` itself."""
    migrate(db_conn)
    store = SourceChunksStore(db_conn)
    store.replace_source("s", [make_chunk(0), make_chunk(1)])
    assert embed_source(fake_ctx, db_conn, source_id="s", config=CONFIG) == 2
    fake_ctx.embed_calls.clear()

    store.replace_source("s", [make_chunk(0), make_chunk(1), make_chunk(2)])
    assert embed_source(fake_ctx, db_conn, source_id="s", config=CONFIG) == 3


def test_embedding_covers_every_source_when_none_is_named(db_conn, fake_ctx):
    migrate(db_conn)
    store = SourceChunksStore(db_conn)
    store.replace_source("a", [make_chunk(0, "a")])
    store.replace_source("b", [make_chunk(0, "b")])
    assert embed_source(fake_ctx, db_conn, config=CONFIG) == 2


def test_deleting_a_chunk_cascades_to_its_vector(db_conn, fake_ctx):
    migrate(db_conn)
    store = SourceChunksStore(db_conn)
    store.replace_source("s", [make_chunk(0)])
    embed_source(fake_ctx, db_conn, source_id="s", config=CONFIG)
    store.delete_source("s")
    table = ensure_embedding_table(db_conn, CONFIG.embedding_model, fake_ctx.dimensions)
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")
        assert cur.fetchone()[0] == 0


def test_embedding_batches_respect_the_batch_size(db_conn, fake_ctx):
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("s", [make_chunk(i) for i in range(5)])
    embed_source(fake_ctx, db_conn, source_id="s", config=CONFIG, batch_size=2)
    assert [len(call) for call in fake_ctx.embed_calls] == [2, 2, 1]


def test_embedding_zero_pending_chunks_is_a_no_op(db_conn, fake_ctx):
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("s", [make_chunk(0)])
    assert embed_source(fake_ctx, db_conn, source_id="s", config=CONFIG) == 1
    fake_ctx.embed_calls.clear()

    assert embed_source(fake_ctx, db_conn, source_id="s", config=CONFIG) == 0
    assert fake_ctx.embed_calls == []


def test_embedding_batch_size_larger_than_pending_chunks_is_a_single_batch(db_conn, fake_ctx):
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("s", [make_chunk(i) for i in range(3)])
    embed_source(fake_ctx, db_conn, source_id="s", config=CONFIG, batch_size=32)
    assert [len(call) for call in fake_ctx.embed_calls] == [3]


def test_a_short_provider_response_raises_instead_of_silently_dropping_a_chunk(db_conn, fake_ctx):
    """A provider batch call that returns fewer vectors than requested must not be
    zipped away silently: `written` would over-report success and the missing chunk
    would be left out of `unembedded()` forever with no error to signal it."""
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("s", [make_chunk(i) for i in range(3)])

    def short_embed(texts, *, model):
        fake_ctx.embed_calls.append(list(texts))
        return [[0.0] * fake_ctx.dimensions for _ in texts[:-1]]  # one short

    fake_ctx.embed = short_embed
    with pytest.raises(ValueError):
        embed_source(fake_ctx, db_conn, source_id="s", config=CONFIG)

    table = ensure_embedding_table(db_conn, CONFIG.embedding_model, fake_ctx.dimensions)
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")
        assert cur.fetchone()[0] == 0


def test_ensure_embedding_table_rejects_a_dimension_mismatch(db_conn, fake_ctx):
    """`ensure_embedding_table` (Task 2) locks in a dimension per model on first call.
    If the embedding provider's real output dimension ever disagreed with what
    `embed_source` passes it (from `ctx.config.embedding(model).dimensions`), that must
    surface as a hard `ValueError`, not a silently truncated/padded vector."""
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("s", [make_chunk(0)])
    embed_source(fake_ctx, db_conn, source_id="s", config=CONFIG)

    other_ctx = fake_ctx.__class__(dimensions=fake_ctx.dimensions + 1)
    with pytest.raises(ValueError):
        embed_source(other_ctx, db_conn, source_id="s", config=CONFIG)
