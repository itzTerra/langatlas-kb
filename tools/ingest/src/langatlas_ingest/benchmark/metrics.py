import time
from dataclasses import dataclass, replace
from typing import Sequence
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import embedding_table_name
from langatlas_ingest.embed import embed_source


@dataclass(frozen=True)
class IndexStats:
    """§8.6's indexing-throughput and storage metrics, plus the two numbers that say
    whether they can be believed: how many chunks the model had to be fed truncated, and
    how many vectors came from the cache instead of the provider."""

    model: str
    chunks: int
    tokens: int
    embed_seconds: float
    chunks_per_second: float | None
    tokens_per_second: float | None
    # Only meaningful when `throughput_honest` is True — i.e. when every chunk in
    # `chunks` was actually embedded fresh this round (`written == chunks`). An arm that
    # embedded nothing (a prior arm already populated its embedding table) still reports
    # `truncated_chunks=0`/`truncated_share=0%` for lack of anything else to report, but
    # that 0% does NOT mean "this model doesn't truncate its content" — it means nothing
    # was measured. Read it beside `throughput_honest`, never alone.
    truncated_chunks: int
    cached_vectors: int
    throughput_honest: bool
    table_bytes: int
    bytes_per_chunk: float | None
    dimensions: int

    def as_dict(self) -> dict:
        return {"model": self.model, "chunks": self.chunks, "tokens": self.tokens,
                "embed_seconds": round(self.embed_seconds, 3),
                "chunks_per_second": self.chunks_per_second,
                "tokens_per_second": self.tokens_per_second,
                "truncated_chunks": self.truncated_chunks,
                "truncated_share": (self.truncated_chunks / self.chunks
                                    if self.chunks else None),
                "cached_vectors": self.cached_vectors,
                "throughput_honest": self.throughput_honest,
                "table_bytes": self.table_bytes,
                "bytes_per_chunk": self.bytes_per_chunk,
                "dimensions": self.dimensions}


def derive_rates(stats: IndexStats) -> IndexStats:
    """Rates are `None`, never 0.0, when there is no denominator — an unmeasured
    throughput and a measured zero would otherwise be the same cell in the results table.

    `throughput_honest` goes false the moment *any* vector came from the cache: a partly
    warm run's wall time is a blend of provider latency and SQLite reads, and there is no
    principled way to unblend it. The number is still recorded; the flag says not to rank
    on it.
    """
    honest = stats.throughput_honest and stats.cached_vectors == 0
    return replace(
        stats,
        chunks_per_second=(stats.chunks / stats.embed_seconds
                           if stats.chunks and stats.embed_seconds > 0 else None),
        tokens_per_second=(stats.tokens / stats.embed_seconds
                           if stats.tokens and stats.embed_seconds > 0 else None),
        bytes_per_chunk=(stats.table_bytes / stats.chunks if stats.chunks else None),
        throughput_honest=honest)


def table_bytes(conn, table: str) -> int:
    """Heap + indexes + TOAST. §8.6 asks for 'storage', and a vector table's HNSW index
    is routinely larger than its heap — reporting the heap alone would understate a
    2560-dim model against a 384-dim one by exactly the amount that matters."""
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(pg_total_relation_size(to_regclass(%s)), 0)",
                    (table,))
        return int(cur.fetchone()[0])


def corpus_size(conn, sources: Sequence[str]) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), COALESCE(sum(token_count), 0) FROM source_chunks"
                    " WHERE source_id = ANY(%s)", (list(sources),))
        row = cur.fetchone()
    return int(row[0]), int(row[1])


def embed_and_measure(ctx, conn, *, model: str, sources: Sequence[str],
                      config: IngestConfig, batch_size: int = 32,
                      truncate: bool = False) -> IndexStats:
    """Embed the pilot on one candidate and time it.

    `embed_source` is reused rather than reimplemented: it is the code production runs,
    and a benchmark that measured a bespoke embed loop would be measuring the wrong thing.
    The model is threaded in through a config override for the same reason — a model id is
    configuration everywhere else too.
    """
    arm_config = replace(config, embedding_model=model)
    chunks, tokens = corpus_size(conn, sources)
    truncated_before = ctx.embedding_truncations
    cached_before = ctx.embedding_cache_hits

    began = time.monotonic()
    written = 0
    for source_id in sources:
        written += embed_source(ctx, conn, source_id=source_id, config=arm_config,
                                batch_size=batch_size, truncate=truncate)
    elapsed = time.monotonic() - began

    table = embedding_table_name(model)
    return derive_rates(IndexStats(
        model=model, chunks=chunks, tokens=tokens, embed_seconds=elapsed,
        chunks_per_second=None, tokens_per_second=None,
        truncated_chunks=ctx.embedding_truncations - truncated_before,
        cached_vectors=ctx.embedding_cache_hits - cached_before,
        # `written == chunks`: every chunk this arm claims to measure was actually sent
        # to the provider this round. A prior arm sharing this model's embedding table
        # (or the table pre-populated from production) leaves nothing pending —
        # `embed_source` then does zero work and `cached_vectors` stays 0 (no embed call
        # happened at all to register a hit), which the old `cached_vectors == 0` check
        # alone could not tell apart from a genuinely honest fresh-embed run.
        throughput_honest=written == chunks, table_bytes=table_bytes(conn, table),
        bytes_per_chunk=None,
        dimensions=ctx.config.embedding(model).dimensions))
