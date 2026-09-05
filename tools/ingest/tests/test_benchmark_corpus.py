import uuid
import pytest
from langatlas_ingest.benchmark.corpus import (
    BENCH_DB_NAME, PRODUCTION_DB_NAME, bench_dsn, build_bench_corpus, check_parity,
    chunk_ids, create_bench_db,
)
from langatlas_ingest.errors import BenchCorpusMismatch


def test_bench_dsn_swaps_only_the_database_name():
    dsn = "postgresql://u:p@localhost:55432/langatlas"
    assert bench_dsn(dsn) == f"postgresql://u:p@localhost:55432/{BENCH_DB_NAME}"
    assert bench_dsn(dsn, name="other").endswith("/other")


def test_bench_dsn_refuses_to_return_the_production_name():
    # The one mistake this module exists to prevent.
    with pytest.raises(ValueError):
        bench_dsn("postgresql://u:p@h/langatlas", name="langatlas")


def test_bench_dsn_refuses_the_production_name_even_from_a_non_production_base_dsn():
    # Finding 1: the guard must reject the literal production name regardless of what
    # database `base_dsn` itself points at — a maintenance DSN aimed at `postgres`, or a
    # DSN already rebased through `bench_dsn` once, must not silently bypass it.
    with pytest.raises(ValueError):
        bench_dsn("postgresql://u:p@h/postgres", name=PRODUCTION_DB_NAME)
    with pytest.raises(ValueError):
        bench_dsn("postgresql://u:p@h/langatlas_bench", name=PRODUCTION_DB_NAME)
    with pytest.raises(ValueError):
        bench_dsn("postgresql://u:p@h/some_other_db", name=PRODUCTION_DB_NAME)


def _chunk(chunk_id: str, ordinal: int):
    from langatlas_ingest.store import SourceChunk

    return SourceChunk(chunk_id=chunk_id, source_id="s1", ordinal=ordinal,
                       parent_section_id=None, section_path=["Ch"], breadcrumb="Ch",
                       locator=f"p. {ordinal}", locator_kind="book-page",
                       page_start=ordinal, page_end=ordinal, section_number=None,
                       anchor=None, line_start=None, line_end=None,
                       text=f"body {ordinal}", token_count=3, content_hash=f"h{ordinal}")


@pytest.fixture
def two_stores(db_conn, dsn):
    """Two independent databases, standing in for bench and production."""
    import psycopg
    from langatlas_ingest.db import migrate

    migrate(db_conn)
    second_dsn = dsn.rsplit("/", 1)[0] + "/langatlas_test_two"
    with psycopg.connect(dsn.rsplit("/", 1)[0] + "/postgres", autocommit=True) as admin:
        with admin.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS langatlas_test_two WITH (FORCE)")
            cur.execute("CREATE DATABASE langatlas_test_two")
    with psycopg.connect(second_dsn, autocommit=True) as other:
        migrate(other)
        yield db_conn, other


@pytest.mark.db
def test_chunk_ids_are_ordered_by_ordinal(two_stores):
    from langatlas_ingest.store import SourceChunksStore

    bench, _ = two_stores
    SourceChunksStore(bench).replace_source(
        "s1", [_chunk("s1#c00002", 2), _chunk("s1#c00001", 1)])
    assert chunk_ids(bench, "s1") == ["s1#c00001", "s1#c00002"]


@pytest.mark.db
def test_check_parity_is_silent_on_identical_corpora(two_stores):
    from langatlas_ingest.store import SourceChunksStore

    bench, production = two_stores
    for conn in (bench, production):
        SourceChunksStore(conn).replace_source("s1", [_chunk("s1#c00001", 1)])
    assert check_parity(bench, production, ["s1"]) == []


@pytest.mark.db
def test_check_parity_reports_a_differing_count(two_stores):
    from langatlas_ingest.store import SourceChunksStore

    bench, production = two_stores
    SourceChunksStore(bench).replace_source("s1", [_chunk("s1#c00001", 1)])
    SourceChunksStore(production).replace_source(
        "s1", [_chunk("s1#c00001", 1), _chunk("s1#c00002", 2)])
    differences = check_parity(bench, production, ["s1"])
    assert differences == ["s1: 1 chunks in bench, 2 in production"]


@pytest.mark.db
def test_check_parity_names_the_first_divergent_ordinal(two_stores):
    from langatlas_ingest.store import SourceChunksStore

    bench, production = two_stores
    SourceChunksStore(bench).replace_source(
        "s1", [_chunk("s1#c00001", 1), _chunk("s1#c00009", 2)])
    SourceChunksStore(production).replace_source(
        "s1", [_chunk("s1#c00001", 1), _chunk("s1#c00002", 2)])
    [difference] = check_parity(bench, production, ["s1"])
    assert "ordinal 1" in difference and "s1#c00009" in difference


@pytest.mark.db
def test_check_parity_catches_same_count_same_ids_different_content(two_stores):
    """Finding 3: two corpora with identical ids at identical ordinals but different text
    (e.g. a redistributed snapshot re-ingested under stale content) must not read as `[]`
    — the previous bare-chunk-id comparison would have missed this entirely."""
    from langatlas_ingest.store import SourceChunksStore

    bench, production = two_stores
    bench_chunk = _chunk("s1#c00001", 1)
    bench_chunk.content_hash = "hash-bench"
    prod_chunk = _chunk("s1#c00001", 1)
    prod_chunk.content_hash = "hash-production"
    SourceChunksStore(bench).replace_source("s1", [bench_chunk])
    SourceChunksStore(production).replace_source("s1", [prod_chunk])

    [difference] = check_parity(bench, production, ["s1"])
    assert "s1#c00001" in difference
    assert "hash-bench" in difference and "hash-production" in difference
    assert "content differs" in difference


def test_mismatch_error_lists_the_sources():
    error = BenchCorpusMismatch(["s1: 10 chunks in bench, 12 in production"])
    assert "s1" in str(error)


@pytest.fixture
def bench_target(dsn):
    """A distinctly-named throwaway database for exercising `create_bench_db` and
    `build_bench_corpus` against a REAL Postgres instance — never `langatlas_bench` (what
    the real chunk-size arms use) and never the production `langatlas` database."""
    import psycopg

    name = f"langatlas_bench_test_{uuid.uuid4().hex[:8]}"
    yield dsn, name
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.mark.db
def test_create_bench_db_creates_a_fresh_migrated_database(bench_target):
    import psycopg

    base_dsn, name = bench_target
    target = create_bench_db(base_dsn, name=name)

    assert target.endswith(f"/{name}")
    with psycopg.connect(target, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('source_chunks')")
            assert cur.fetchone()[0] == "source_chunks"


@pytest.mark.db
def test_create_bench_db_without_drop_is_idempotent(bench_target):
    base_dsn, name = bench_target
    create_bench_db(base_dsn, name=name)
    # A second call with the database already present must not raise on "already exists".
    target = create_bench_db(base_dsn, name=name)
    assert target.endswith(f"/{name}")


@pytest.mark.db
def test_create_bench_db_with_drop_discards_previous_rows(bench_target):
    import psycopg
    from langatlas_ingest.store import SourceChunksStore

    base_dsn, name = bench_target
    target = create_bench_db(base_dsn, name=name)
    with psycopg.connect(target, autocommit=True) as conn:
        SourceChunksStore(conn).replace_source("s1", [_chunk("s1#c00001", 1)])

    target = create_bench_db(base_dsn, name=name, drop=True)

    with psycopg.connect(target, autocommit=True) as conn:
        assert SourceChunksStore(conn).count_by_source("s1") == 0


_BENCH_SOURCE_BODY = ("A match expression compares a scrutinee against a sequence of "
                     "patterns and evaluates the arm of the first pattern that matches "
                     "it. ") * 6
_BENCH_SOURCE_HTML = (f"<html><body><h1 id='expressions'>Expressions</h1>"
                     f"<p>{_BENCH_SOURCE_BODY}</p>"
                     f"<h2 id='match-expressions'>Match expressions</h2>"
                     f"<p>{_BENCH_SOURCE_BODY}</p></body></html>")


@pytest.mark.db
def test_build_bench_corpus_reingests_a_real_source_and_returns_chunk_counts(
        bench_target, snapshot_root, tmp_path):
    import psycopg
    from langatlas_ingest.config import IngestConfig
    from langatlas_ingest.snapshot import SnapshotStore
    from langatlas_ingest.store import SourceChunksStore

    base_dsn, name = bench_target
    target = create_bench_db(base_dsn, name=name)

    path = tmp_path / "ref.html"
    path.write_text(_BENCH_SOURCE_HTML)
    snapshots = SnapshotStore(snapshot_root)
    snapshots.put("bench-src", path, media_type="text/html",
                  source_url="https://example.org/ref", locator_kinds=["web-fragment"])
    config = IngestConfig.load(overrides={"chunk_target_tokens": 40, "chunk_max_tokens": 60,
                                          "chunk_overlap_tokens": 8})

    with psycopg.connect(target, autocommit=True) as conn:
        counts = build_bench_corpus(conn, sources=["bench-src"], config=config,
                                    snapshots=snapshots)

        assert counts["bench-src"] > 0
        assert counts == {"bench-src": SourceChunksStore(conn).count_by_source("bench-src")}
