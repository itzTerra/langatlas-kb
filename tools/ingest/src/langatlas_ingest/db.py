# tools/ingest/src/langatlas_ingest/db.py
import re
import psycopg
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.paths import DB_DIR

_SAFE = re.compile(r"[^a-z0-9]+")

_LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


def connect(dsn: str | None = None):
    """Autocommit by default: this package's writes are per-source replace operations
    that manage their own transactions where atomicity actually matters."""
    return psycopg.connect(dsn or IngestConfig.load().dsn, autocommit=True)


def migrate(conn) -> list[str]:
    """Apply every unapplied `db/NNNN_*.sql` in filename order. No framework: numbered
    files plus a ledger table is the whole mechanism, and the database is regenerable
    anyway (D1)."""
    applied: list[str] = []
    with conn.cursor() as cur:
        cur.execute(_LEDGER)
        cur.execute("SELECT filename FROM schema_migrations")
        done = {row[0] for row in cur.fetchall()}
        for path in sorted(DB_DIR.glob("[0-9]*.sql")):
            if path.name in done:
                continue
            cur.execute(path.read_text())
            cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
            applied.append(path.name)
    return applied


def embedding_table_name(model_id: str) -> str:
    return "source_chunk_emb_" + _SAFE.sub("_", model_id.lower()).strip("_")


def ensure_embedding_table(conn, model_id: str, dimensions: int) -> str:
    """One table per embedding model. D22's Stage 2 benchmark compares candidates with
    different dimensions in the same database, and HNSW needs a fixed dimension — so
    per-model tables, not one table with a nullable-dimension column.

    The stored column is always full-precision `vector(dimensions)` — a re-embed or a
    D22 benchmark comparison needs the exact values. But pgvector's HNSW caps `vector`
    at 2000 dimensions (the project's incumbent model is 2560-dim), so the index is
    built on a `halfvec(dimensions)` cast instead; `halfvec` raises that cap to 4000.
    This one code path covers every dimension, low or high, rather than branching on
    2000. Callers building a query that should hit this index (Task 10's hybrid
    retrieval) MUST cast identically:
        ORDER BY embedding::halfvec(<dimensions>) <=> %s::halfvec(<dimensions>)
    A plain `vector` distance operator against `embedding` will not match this
    expression index and silently falls back to a sequential scan."""
    table = embedding_table_name(model_id)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT atttypmod FROM pg_attribute"
            " WHERE attrelid = to_regclass(%s) AND attname = 'embedding'", (table,))
        row = cur.fetchone()
        if row is not None:
            existing = row[0]
            if existing != dimensions:
                raise ValueError(
                    f"{table} already exists at dimension {existing}, refusing to "
                    f"redefine it as {dimensions}; drop the table to re-embed")
            return table
        cur.execute(
            f"CREATE TABLE {table} ("
            "  chunk_id  text PRIMARY KEY REFERENCES source_chunks(chunk_id) ON DELETE CASCADE,"
            f" embedding vector({dimensions}) NOT NULL,"
            "  embedded_at timestamptz NOT NULL DEFAULT now())")
        cur.execute(f"CREATE INDEX {table}_hnsw ON {table}"
                    f" USING hnsw ((embedding::halfvec({dimensions})) halfvec_cosine_ops)")
    return table
