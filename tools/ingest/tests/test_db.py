# tools/ingest/tests/test_db.py
import pytest
from langatlas_ingest.db import ensure_embedding_table, migrate

pytestmark = pytest.mark.db


def test_migrate_is_idempotent(db_conn):
    first = migrate(db_conn)
    assert "0001_source_chunks.sql" in first
    assert migrate(db_conn) == []          # already applied -> nothing re-runs


def test_source_chunks_generates_its_tsvector(db_conn):
    migrate(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO source_chunks (chunk_id, source_id, ordinal, breadcrumb, locator,"
            " locator_kind, text, token_count, content_hash)"
            " VALUES ('s#c00001', 's', 1, 'Ch 1', 'p. 4', 'book-page',"
            " 'lazy evaluation defers computation', 6, 'abc')")
        cur.execute("SELECT tsv @@ plainto_tsquery('english', 'lazy evaluation')"
                    " FROM source_chunks WHERE chunk_id = 's#c00001'")
        assert cur.fetchone()[0] is True


def test_ensure_embedding_table_is_per_model(db_conn):
    migrate(db_conn)
    table = ensure_embedding_table(db_conn, "qwen3-embedding-4b", 2560)
    assert table == "source_chunk_emb_qwen3_embedding_4b"
    assert ensure_embedding_table(db_conn, "qwen3-embedding-4b", 2560) == table
    other = ensure_embedding_table(db_conn, "nomic-embed-text-v1.5", 768)
    assert other != table                   # D22 candidates coexist, different dimensions


def test_ensure_embedding_table_rejects_a_dimension_change(db_conn):
    migrate(db_conn)
    ensure_embedding_table(db_conn, "qwen3-embedding-4b", 2560)
    with pytest.raises(ValueError, match="dimension"):
        ensure_embedding_table(db_conn, "qwen3-embedding-4b", 768)


def test_sourcing_queue_rejects_an_unknown_reason(db_conn):
    migrate(db_conn)
    with pytest.raises(Exception):
        with db_conn.cursor() as cur:
            cur.execute("INSERT INTO sourcing_queue (kind, source_id, reason)"
                        " VALUES ('pending-source', 's', 'invented-reason')")
