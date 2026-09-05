# tools/ingest/src/langatlas_ingest/search.py
from dataclasses import dataclass
from typing import Sequence
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import embedding_table_name
from langatlas_ingest.embed import vector_literal
from langatlas_ingest.errors import IngestError
from langatlas_ingest.store import SourceChunk, SourceChunksStore, _COLUMNS

_CHUNK_COLUMNS = ", ".join(f"c.{name}" for name in _COLUMNS)

# pgvector's own default and documented ceiling for `hnsw.ef_search`.
_EF_SEARCH_DEFAULT = 40
_EF_SEARCH_MAX = 1000

# §8.6's first variant axis. `fts` is not a verdict candidate — it is the lexical-only
# denominator that makes "what does the vector branch add" answerable from both sides.
SEARCH_MODES = ("hybrid", "vector", "fts")


class MissingEmbeddingTable(IngestError):
    """Searching before `langatlas-sources embed` has ever run. Typed, because the
    alternative is an `UndefinedTable` from psycopg that reads like a schema bug."""

    def __init__(self, model: str, table: str):
        super().__init__(f"no embeddings for model {model!r} (table {table} does not "
                         f"exist); run `langatlas-sources embed` first")
        self.model = model
        self.table = table


def embedding_dimensions(conn, table: str) -> int:
    """The dimension that *built* the table, read the same way `ensure_embedding_table`
    reads it — `pg_attribute.atttypmod` is the single source of truth. Config could
    disagree with what is on disk; the halfvec cast has to match the ruled index, not
    the config file."""
    with conn.cursor() as cur:
        cur.execute("SELECT atttypmod FROM pg_attribute"
                    " WHERE attrelid = to_regclass(%s) AND attname = 'embedding'", (table,))
        row = cur.fetchone()
    return row[0] if row else 0


@dataclass
class SearchHit:
    chunk: SourceChunk
    score: float
    fts_rank: int | None = None
    vector_rank: int | None = None
    rerank_score: float | None = None


class SourceSearch:
    """Section 8.1's retrieval shape: filter first, then hybrid BM25/FTS + vector fused
    with RRF, k=5, relevance floor — with D15's reranker default-on for this table."""

    def __init__(self, conn, ctx, *, config: IngestConfig | None = None,
                 rerank: bool | None = None, mode: str | None = None):
        from langatlas_ingest.errors import UnknownSearchMode

        self.conn = conn
        self.ctx = ctx
        self.config = config or IngestConfig.load()
        self.mode = self.config.retrieval_mode if mode is None else mode
        if self.mode not in SEARCH_MODES:
            raise UnknownSearchMode(self.mode)
        self.rerank = self.config.rerank_default_on if rerank is None else rerank
        self.store = SourceChunksStore(conn)

    def build_query(self, query: str, *, vector: str, k: int,
                    source_ids: Sequence[str] | None) -> tuple[str, dict]:
        """Built as one statement so the filter, both branches, and the fusion are a
        single planner problem — and exposed so a test can EXPLAIN exactly what runs.

        Each branch is ranked *inside* its own subquery (`ORDER BY ... LIMIT`), then
        numbered by `row_number()`. The brief's shape put `row_number()` in the outer
        select of the CTE with a bare `LIMIT` under it, which asks Postgres for an
        arbitrary `candidates` rows of an unordered set and would also have kept the
        vector branch off its index — `ORDER BY <distance> LIMIT n` is the only form
        HNSW can serve.

        `mode` selects which branches are emitted. The RRF score expression keeps its
        shape in every mode — a single-branch score is `1/(rrf_k + rank)`, which is the
        same monotone function of rank the fused score uses, so `relevance_floor` and
        every recorded score stay comparable across arms.
        """
        candidates = max(int(self.config.retrieval_candidates), int(k))
        filter_sql = " AND c.source_id = ANY(%(sources)s)" if source_ids else ""
        params: dict = {"rrf_k": self.config.rrf_k,
                        "sources": list(source_ids) if source_ids else []}
        ctes, joins, score_terms, presence = [], [], [], []

        if self.mode in ("hybrid", "fts"):
            params["query"] = query
            ctes.append(f"""fts AS (
            SELECT chunk_id, row_number() OVER (ORDER BY lexical DESC, chunk_id) AS rank
            FROM (
                SELECT c.chunk_id, ts_rank_cd(c.tsv, q.query) AS lexical
                FROM source_chunks c, plainto_tsquery('english', %(query)s) AS q(query)
                WHERE c.tsv @@ q.query{filter_sql}
                ORDER BY lexical DESC, c.chunk_id
                LIMIT {int(candidates)}
            ) ranked
        )""")
            joins.append("LEFT JOIN fts ON fts.chunk_id = c.chunk_id")
            score_terms.append("COALESCE(1.0 / (%(rrf_k)s + fts.rank), 0)")
            presence.append("fts.chunk_id IS NOT NULL")

        if self.mode in ("hybrid", "vector"):
            table = embedding_table_name(self.config.embedding_model)
            dimensions = embedding_dimensions(self.conn, table)
            if dimensions <= 0:
                raise MissingEmbeddingTable(self.config.embedding_model, table)
            # Both sides cast to halfvec at the stored dimension: `ensure_embedding_table`
            # rules the HNSW index on `(embedding::halfvec(N)) halfvec_cosine_ops` because
            # pgvector caps `vector` HNSW at 2000 dimensions and the incumbent model is
            # 2560-dim. A plain `<=> %s::vector` does not match that expression index and
            # silently degrades to a sequential scan over the whole corpus.
            params["vector"] = vector
            distance = (f"e.embedding::halfvec({dimensions})"
                        f" <=> %(vector)s::halfvec({dimensions})")
            # The vector branch must not join `source_chunks` just to reach the filter
            # column: any join above the scan stops the planner from answering
            # `ORDER BY <distance> LIMIT n` from the HNSW index and leaves it sorting the
            # whole table. Unfiltered, the branch reads the embedding table alone; filtered,
            # §8.1's filter-first shape is a semi-join restricting the rows considered.
            vec_filter = ("\n                WHERE e.chunk_id IN (SELECT chunk_id FROM"
                          " source_chunks WHERE source_id = ANY(%(sources)s))"
                          if source_ids else "")
            ctes.append(f"""vec AS (
            SELECT chunk_id, row_number() OVER (ORDER BY distance, chunk_id) AS rank
            FROM (
                SELECT e.chunk_id, {distance} AS distance
                FROM {table} e{vec_filter}
                ORDER BY {distance}
                LIMIT {int(candidates)}
            ) ranked
        )""")
            joins.append("LEFT JOIN vec ON vec.chunk_id = c.chunk_id")
            score_terms.append("COALESCE(1.0 / (%(rrf_k)s + vec.rank), 0)")
            presence.append("vec.chunk_id IS NOT NULL")

        rank_columns = ", ".join(
            ("fts.rank" if "fts" in cte.split(" AS ")[0] else "vec.rank")
            for cte in ctes)
        sql = f"""
        WITH {', '.join(ctes)}
        SELECT {_CHUNK_COLUMNS}, {rank_columns},
               {' + '.join(score_terms)} AS score
        FROM source_chunks c
        {' '.join(joins)}
        WHERE {' OR '.join(presence)}
        ORDER BY score DESC, c.chunk_id
        LIMIT {int(candidates)}
        """
        return sql, params

    def tune_ef_search(self, cur, *, k: int) -> int:
        """pgvector's `hnsw.ef_search` defaults to 40 and is a hard ceiling on how many
        rows an HNSW scan can return, whatever the query's LIMIT says. With
        `retrieval.candidates: 50` the vector branch therefore yielded only 40 rows, and
        any future raise of that config value would have been silently clamped — the
        pre-rerank pool, and recall with it, quietly smaller than what is configured.

        Plain `SET`, not `SET LOCAL`: `db.connect()` opens autocommit connections, so
        there is no surrounding transaction for `LOCAL` to scope to and it would be a
        no-op. This is a session GUC on the search connection, which is what we want.
        """
        # Never *lower* recall below pgvector's own default, and stay inside the
        # documented 1..1000 range.
        wanted = max(int(self.config.retrieval_candidates), int(k), _EF_SEARCH_DEFAULT)
        ef_search = min(wanted, _EF_SEARCH_MAX)
        cur.execute(f"SET hnsw.ef_search = {int(ef_search)}")
        return ef_search

    def search(self, query: str, *, k: int | None = None,
               source_ids: Sequence[str] | None = None) -> list[SearchHit]:
        # `is None`, not truthiness: `k=0` is an honest "give me nothing" (a caller
        # draining a budget), not a request for the configured default.
        k = self.config.retrieval_k if k is None else int(k)
        if k <= 0:
            return []
        # An `fts` arm must cost zero embedding calls — otherwise the lexical-only
        # denominator is quietly paying the price of the branch it is there to isolate.
        vector = ""
        if self.mode in ("hybrid", "vector"):
            vector = vector_literal(
                self.ctx.embed([query], model=self.config.embedding_model)[0])
        sql, params = self.build_query(query, vector=vector, k=k, source_ids=source_ids)
        with self.conn.cursor() as cur:
            if self.mode in ("hybrid", "vector"):
                self.tune_ef_search(cur, k=k)
            cur.execute(sql, params)
            rows = cur.fetchall()

        width = len(_COLUMNS)
        hits = []
        for row in rows:
            chunk = SourceChunk(**dict(zip(_COLUMNS, row[:width])))
            if self.mode == "hybrid":
                fts_rank, vector_rank, score = row[width], row[width + 1], row[width + 2]
            elif self.mode == "fts":
                fts_rank, vector_rank, score = row[width], None, row[width + 1]
            else:
                fts_rank, vector_rank, score = None, row[width], row[width + 1]
            hits.append(SearchHit(chunk=chunk, fts_rank=fts_rank,
                                  vector_rank=vector_rank, score=float(score)))
        hits = [hit for hit in hits if hit.score >= self.config.relevance_floor]
        if self.rerank and hits:
            # Only the top of the fused pool is reranked. The full
            # `retrieval_candidates` pool is still fused and ranked by RRF above — that
            # is one SQL statement — but 1B's rerank client is completion-driven and
            # batches 8 documents per call, so reranking 50 candidates cost 7 sequential
            # completions on a slow API for every single search. `max(..., k)` so a
            # caller asking for more hits than the rerank pool is never starved.
            depth = max(int(self.config.rerank_candidates), k)
            hits = self._rerank(query, hits[:depth]) + hits[depth:]
        return hits[:k]

    def _rerank(self, query: str, hits: list[SearchHit]) -> list[SearchHit]:
        """D15 ratified the reranker default-on. Chunk text is untrusted external content,
        and 1B's RerankClient already puts every candidate through the D31 door — this
        method must not build its own prompt around raw chunk text."""
        scores = self.ctx.rerank(query, [hit.chunk.text for hit in hits],
                                 model=self.config.reranker_model)
        for hit, score in zip(hits, scores, strict=True):
            hit.rerank_score = float(score)
        return sorted(hits, key=lambda hit: hit.rerank_score, reverse=True)

    def get_section(self, chunk_id: str, *, expand: str = "parent") -> list[SourceChunk]:
        """D15's small-to-big expansion: retrieval finds a small chunk, the agent reads the
        whole section it came from."""
        chunk = self.store.get(chunk_id)
        if chunk is None:
            return []
        if expand == "none" or not chunk.parent_section_id:
            return [chunk]
        return self.store.children_of(chunk.parent_section_id)
