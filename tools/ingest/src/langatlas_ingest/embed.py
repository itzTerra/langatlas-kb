from typing import Sequence
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import ensure_embedding_table
from langatlas_ingest.store import SourceChunksStore


def vector_literal(values: Sequence[float]) -> str:
    """pgvector accepts its own text form, so no extra adapter package is needed."""
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def embed_source(ctx, conn, *, source_id: str | None = None,
                 config: IngestConfig | None = None, batch_size: int = 32) -> int:
    """D15's overnight batch embed. Every call goes through `ctx` (D26), so it is logged,
    budgeted, and content-addressed-cached like any other provider call; re-running after
    an interruption re-embeds only what is missing, which is what makes a multi-hour job
    survivable on a slow university API."""
    config = config or IngestConfig.load()
    model = config.embedding_model
    dimensions = ctx.config.embedding(model).dimensions
    table = ensure_embedding_table(conn, model, dimensions)

    store = SourceChunksStore(conn)
    pending = [chunk for chunk in store.unembedded(table)
               if source_id is None or chunk.source_id == source_id]
    written = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        vectors = ctx.embed([chunk.text for chunk in batch], model=model)
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {table} (chunk_id, embedding) VALUES (%s, %s::vector)"
                " ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding,"
                " embedded_at = now()",
                # strict=True: a provider returning fewer vectors than requested must
                # raise here, not silently drop a chunk and let `written` over-report
                # what was actually inserted.
                [(chunk.chunk_id, vector_literal(vector))
                 for chunk, vector in zip(batch, vectors, strict=True)])
        written += len(batch)
    return written
