from typing import Sequence
import psycopg
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import migrate
from langatlas_ingest.pipeline import ingest_source
from langatlas_ingest.snapshot import SnapshotStore
from langatlas_ingest.store import SourceChunksStore

# §8.6's arms re-chunk the corpus at 400 and 800 tokens. Doing that in the production
# database would rewrite every chunk id the 2B golden sets cite — the single most
# destructive thing this stage could do — so the benchmark gets its own database and the
# production one is never opened for writing here.
BENCH_DB_NAME = "langatlas_bench"
# The one literal this guard exists to catch. `IngestConfig` never parses its `dsn` into a
# bare database name (it stores the whole connection string, password included), so there
# is no single-source-of-truth field to import here instead — this is the canonical place
# that records it. Checked unconditionally against `name`, independent of whatever
# database `base_dsn` itself happens to point at (a maintenance DSN, an already-rebased
# bench DSN, ...): the mistake this module exists to prevent is calling
# `bench_dsn(..., name="langatlas")` and getting a DSN back, no matter where `base_dsn`
# came from.
PRODUCTION_DB_NAME = "langatlas"


def bench_dsn(base_dsn: str, *, name: str = BENCH_DB_NAME) -> str:
    if name == PRODUCTION_DB_NAME:
        raise ValueError(f"refusing to use the production database {name!r} as the"
                         " benchmark database")
    head, _, _ = base_dsn.rpartition("/")
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


def recorded_chunk_size(conn, sources: Sequence[str]) -> tuple[int, int] | None:
    """The `(target_tokens, max_tokens)` `build_bench_corpus` actually chunked this
    bench database's sources at, read back off `source_ingestions.chunking` — the same
    per-source ledger `ingest_source` already writes via `chunking_fingerprint`. No new
    table: `build_bench_corpus` calls `ingest_source` for every pilot source, so the
    value is already sitting there once the corpus exists.

    `run_arm`'s defense-in-depth guard uses this rather than trusting the caller's
    intent: a bench database chunked at one size but scored as if it were another is
    exactly the mistake a live run once made through the CLI.

    `None` when nothing is recorded yet (the bench corpus was never built) — the guard
    that reads this treats "unknown" as "cannot verify", not as a mismatch.
    """
    for source_id in sources:
        recorded = SourceChunksStore(conn).ingestion(source_id)
        if recorded is None:
            continue
        chunking = recorded.get("chunking") or {}
        if "target_tokens" in chunking and "max_tokens" in chunking:
            return int(chunking["target_tokens"]), int(chunking["max_tokens"])
    return None


def chunk_ids(conn, source_id: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT chunk_id FROM source_chunks WHERE source_id = %s"
                    " ORDER BY ordinal", (source_id,))
        return [row[0] for row in cur.fetchall()]


def chunk_ids_and_hashes(conn, source_id: str) -> list[tuple[str, str]]:
    """Like `chunk_ids`, but pairs each id with its `content_hash` so `check_parity` can
    tell a same-ordinal content drift apart from a genuine id mismatch."""
    with conn.cursor() as cur:
        cur.execute("SELECT chunk_id, content_hash FROM source_chunks WHERE source_id = %s"
                    " ORDER BY ordinal", (source_id,))
        return [(row[0], row[1]) for row in cur.fetchall()]


def check_parity(bench_conn, prod_conn, sources: Sequence[str]) -> list[str]:
    """Assert the 600-token rebuild reproduces production's chunks exactly — both id and
    content, not id alone.

    This is the load-bearing check of the whole benchmark: the golden set's
    `expected_chunks` are production chunk ids, so if the bench corpus's ids differ, every
    primary arm is scoring against ids that do not exist and would report a uniform zero
    that looks like a model failure. Chunking is deterministic given the same snapshot and
    the same config, so any difference is a real finding — a changed snapshot, a changed
    extractor, a changed config — and never something to work around.

    Comparing bare ids is not enough: an id encodes only ordinal position, so two chunk
    sets with the same count and the same ids in the same order but different actual text
    (e.g. a redistributed snapshot re-ingested under stale content) would still report
    `[]` — a silent false "OK" on the exact guarantee this function exists to make.
    Comparing `(chunk_id, content_hash)` pairs catches that: same id, different hash is
    reported as a content mismatch, distinct from a count or id mismatch.
    """
    differences: list[str] = []
    for source_id in sources:
        bench = chunk_ids_and_hashes(bench_conn, source_id)
        production = chunk_ids_and_hashes(prod_conn, source_id)
        if bench == production:
            continue
        if len(bench) != len(production):
            differences.append(f"{source_id}: {len(bench)} chunks in bench,"
                               f" {len(production)} in production")
            continue
        first = next(index for index, (a, b) in enumerate(zip(bench, production))
                     if a != b)
        (bench_id, bench_hash), (prod_id, prod_hash) = bench[first], production[first]
        if bench_id != prod_id:
            differences.append(f"{source_id}: same count, first divergence at ordinal"
                               f" {first}: {bench_id!r} != {prod_id!r}")
        else:
            differences.append(f"{source_id}: same count and ids, content differs at"
                               f" ordinal {first} ({bench_id!r}): hash {bench_hash!r}"
                               f" != {prod_hash!r}")
    return differences
