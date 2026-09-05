import pytest
from langatlas_ingest.benchmark.corpus import (
    BENCH_DB_NAME, bench_dsn, check_parity, chunk_ids,
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


def test_mismatch_error_lists_the_sources():
    error = BenchCorpusMismatch(["s1: 10 chunks in bench, 12 in production"])
    assert "s1" in str(error)
