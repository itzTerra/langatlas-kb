# tools/ingest/tests/test_store.py
import pytest
from langatlas_ingest.chunker import Chunk, chunking_fingerprint
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import ensure_embedding_table, migrate
from langatlas_ingest.errors import UnknownQueueEntry
from langatlas_ingest.qa import QaCheck, QaReport
from langatlas_ingest.store import SourceChunksStore, SourcingQueue

pytestmark = pytest.mark.db


def make_chunk(ordinal: int, **overrides) -> Chunk:
    data = dict(chunk_id=f"s#c{ordinal:05d}", source_id="s", ordinal=ordinal,
                parent_section_id="s#s0001", section_path=["Ch 1"], breadcrumb="Ch 1",
                locator=f"p. {ordinal + 1}", locator_kind="book-page",
                text=f"chunk {ordinal} about lazy evaluation", token_count=7,
                content_hash=f"hash{ordinal}", page_start=ordinal + 1, page_end=ordinal + 1)
    data.update(overrides)
    return Chunk(**data)


@pytest.fixture
def store(db_conn):
    migrate(db_conn)
    return SourceChunksStore(db_conn)


def test_replace_source_is_idempotent(store):
    assert store.replace_source("s", [make_chunk(0), make_chunk(1)]) == 2
    assert store.replace_source("s", [make_chunk(0)]) == 1
    assert [c.chunk_id for c in store.by_source("s")] == ["s#c00000"]


def test_round_trip_preserves_every_locator_field(store):
    store.replace_source("s", [make_chunk(0, section_number="1.2", anchor="intro")])
    chunk = store.get("s#c00000")
    assert chunk.locator == "p. 1" and chunk.locator_kind == "book-page"
    assert chunk.section_path == ["Ch 1"] and chunk.section_number == "1.2"
    assert chunk.anchor == "intro" and chunk.parent_section_id == "s#s0001"


def test_get_returns_none_for_an_unknown_chunk(store):
    assert store.get("nope#c00000") is None


def test_children_of_returns_the_section_in_order(store):
    store.replace_source("s", [make_chunk(0), make_chunk(1),
                               make_chunk(2, parent_section_id="s#s0002")])
    assert [c.ordinal for c in store.children_of("s#s0001")] == [0, 1]


def test_record_ingestion_stores_the_qa_verdict(store, db_conn):
    report = QaReport(source_id="s", chunk_count=2, char_count=100,
                      checks=[QaCheck("encoding", "hard", True, "clean")])
    store.record_ingestion("s", content_hash="abc", backend="pymupdf", backend_version="1",
                           chunk_count=2, qa=report, promoted=True)
    with db_conn.cursor() as cur:
        cur.execute("SELECT qa_status, promoted, qa_report FROM source_ingestions"
                    " WHERE source_id = 's'")
        status, promoted, payload = cur.fetchone()
    assert (status, promoted) == ("pass", True)
    assert payload["checks"][0]["check_id"] == "encoding"


def test_record_ingestion_overwrites_the_previous_run(store, db_conn):
    report = QaReport(source_id="s")
    store.record_ingestion("s", content_hash="a", backend="b", backend_version="1",
                           chunk_count=1, qa=report, promoted=False)
    store.record_ingestion("s", content_hash="b", backend="b", backend_version="1",
                           chunk_count=9, qa=report, promoted=True)
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*), max(chunk_count) FROM source_ingestions")
        assert cur.fetchone() == (1, 9)


def test_record_ingestion_round_trips_the_chunking_fingerprint(store):
    """`ingest_source` compares this value to decide whether to skip a re-ingest, so it
    has to come back out of jsonb equal to what went in — a stringified int or a dropped
    key would read as a config change and force a needless re-embed."""
    fingerprint = chunking_fingerprint(IngestConfig.load(
        overrides={"chunk_target_tokens": 40, "chunk_max_tokens": 60,
                   "chunk_overlap_tokens": 8}))
    store.record_ingestion("s", content_hash="a", backend="b", backend_version="1",
                           chunk_count=1, qa=QaReport(source_id="s"), promoted=True,
                           chunking=fingerprint)
    assert store.ingestion("s")["chunking"] == fingerprint


def test_an_ingestion_recorded_without_a_fingerprint_reads_as_unknown(store):
    """Never as "matches by default": a caller that cannot state what it chunked with
    must leave a value that no real fingerprint equals, so the source re-ingests once."""
    store.record_ingestion("s", content_hash="a", backend="b", backend_version="1",
                           chunk_count=1, qa=QaReport(source_id="s"), promoted=True)
    assert store.ingestion("s")["chunking"] == {}


def test_unembedded_returns_only_chunks_with_no_row_in_the_embedding_table(store, db_conn):
    store.replace_source("s", [make_chunk(0), make_chunk(1), make_chunk(2)])
    table = ensure_embedding_table(db_conn, "test-model", 3)
    with db_conn.cursor() as cur:
        cur.execute(f"INSERT INTO {table} (chunk_id, embedding) VALUES (%s, %s)",
                    ("s#c00001", "[0.1,0.2,0.3]"))
    assert [c.ordinal for c in store.unembedded(table)] == [0, 2]


def test_unembedded_honours_a_limit_including_zero(store, db_conn):
    store.replace_source("s", [make_chunk(0), make_chunk(1), make_chunk(2)])
    table = ensure_embedding_table(db_conn, "test-model", 3)
    assert len(store.unembedded(table)) == 3
    assert len(store.unembedded(table, limit=2)) == 2
    # `limit=0` means none, not "no limit" -- a caller draining a budget to zero must not
    # be handed the whole table.
    assert store.unembedded(table, limit=0) == []


def test_bouncing_an_unknown_entry_raises_a_typed_error(db_conn):
    migrate(db_conn)
    with pytest.raises(UnknownQueueEntry) as excinfo:
        SourcingQueue(db_conn).bounce(4242)
    assert excinfo.value.entry_id == 4242


def test_queue_files_bounces_and_resolves(db_conn):
    migrate(db_conn)
    queue = SourcingQueue(db_conn)
    entry_id = queue.file(kind="pending-source", source_id="s", reason="paywalled",
                          detail="university access requested")
    assert [e["source_id"] for e in queue.open_entries()] == ["s"]
    assert queue.bounce(entry_id) == 1
    assert queue.open_entries()[0]["bounce_count"] == 1
    assert queue.open_entries()[0]["age_days"] == 0
    assert queue.resolve(source_id="s") == 1
    assert queue.open_entries() == []


def test_queue_refiles_rather_than_duplicating(db_conn):
    migrate(db_conn)
    queue = SourcingQueue(db_conn)
    first = queue.file(kind="pending-source", source_id="s", reason="not-ingested")
    second = queue.file(kind="pending-source", source_id="s", reason="paywalled")
    assert first == second
    assert [e["reason"] for e in queue.open_entries()] == ["paywalled"]
