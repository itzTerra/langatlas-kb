from typing import Sequence
import psycopg
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import migrate
from langatlas_ingest.pipeline import ingest_source
from langatlas_ingest.snapshot import SnapshotStore

# §8.6's arms re-chunk the corpus at 400 and 800 tokens. Doing that in the production
# database would rewrite every chunk id the 2B golden sets cite — the single most
# destructive thing this stage could do — so the benchmark gets its own database and the
# production one is never opened for writing here.
BENCH_DB_NAME = "langatlas_bench"


def bench_dsn(base_dsn: str, *, name: str = BENCH_DB_NAME) -> str:
    head, _, current = base_dsn.rpartition("/")
    if name == current:
        raise ValueError(f"refusing to use the production database {current!r} as the"
                         " benchmark database")
    return f"{head}/{name}"


def create_bench_db(base_dsn: str, *, name: str = BENCH_DB_NAME,
                    drop: bool = False) -> str:
    """Create (optionally recreate) the benchmark database and apply `db/*.sql`. Returns
    its DSN. `drop=True` is the chunk-size axis's reset: a re-chunk must not leave the
    previous size's rows behind, and per-source replacement would not catch a source
    that vanished from the pilot."""
    target = bench_dsn(base_dsn, name=name)
    with psycopg.connect(base_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            if drop:
                cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{name}"')
    with psycopg.connect(target, autocommit=True) as conn:
        migrate(conn)
    return target


def build_bench_corpus(conn, *, sources: Sequence[str], config: IngestConfig,
                       snapshots: SnapshotStore | None = None) -> dict[str, int]:
    """Re-ingest each pilot source from its stored snapshot at `config`'s chunk size.

    Nothing is fetched: `SnapshotStore` already holds every original 2A acquired, and
    re-fetching would make the benchmark depend on a publisher's uptime and could return
    a different document than the one the golden set was authored against.
    """
    snapshots = snapshots or SnapshotStore()
    counts: dict[str, int] = {}
    for source_id in sources:
        result = ingest_source(source_id, conn=conn, config=config, snapshots=snapshots)
        counts[source_id] = result.chunk_count
    return counts


def chunk_ids(conn, source_id: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT chunk_id FROM source_chunks WHERE source_id = %s"
                    " ORDER BY ordinal", (source_id,))
        return [row[0] for row in cur.fetchall()]


def check_parity(bench_conn, prod_conn, sources: Sequence[str]) -> list[str]:
    """Assert the 600-token rebuild reproduces production's chunk ids exactly.

    This is the load-bearing check of the whole benchmark: the golden set's
    `expected_chunks` are production chunk ids, so if the bench corpus's ids differ, every
    primary arm is scoring against ids that do not exist and would report a uniform zero
    that looks like a model failure. Chunking is deterministic given the same snapshot and
    the same config, so any difference is a real finding — a changed snapshot, a changed
    extractor, a changed config — and never something to work around.
    """
    differences: list[str] = []
    for source_id in sources:
        bench, production = chunk_ids(bench_conn, source_id), chunk_ids(prod_conn,
                                                                        source_id)
        if bench == production:
            continue
        if len(bench) != len(production):
            differences.append(f"{source_id}: {len(bench)} chunks in bench,"
                               f" {len(production)} in production")
        else:
            first = next(index for index, (a, b)
                         in enumerate(zip(bench, production)) if a != b)
            differences.append(f"{source_id}: same count, first divergence at ordinal"
                               f" {first}: {bench[first]!r} != {production[first]!r}")
    return differences
