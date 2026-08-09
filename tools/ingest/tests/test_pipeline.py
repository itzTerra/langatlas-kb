# tools/ingest/tests/test_pipeline.py
import pytest
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import migrate
from langatlas_ingest.errors import ExtractionFailed, QaHardGate, SnapshotMissing
from langatlas_ingest.pipeline import ingest_source
from langatlas_ingest.snapshot import SnapshotStore
from langatlas_ingest.store import SourceChunksStore, SourcingQueue

pytestmark = pytest.mark.db

CONFIG = IngestConfig.load(overrides={"chunk_target_tokens": 40, "chunk_max_tokens": 60,
                                      "chunk_overlap_tokens": 8})

BODY = ("A match expression compares a scrutinee against a sequence of patterns and "
        "evaluates the arm of the first pattern that matches it. ") * 6
GOOD_HTML = (f"<html><body><h1 id='expressions'>Expressions</h1><p>{BODY}</p>"
             f"<h2 id='match-expressions'>Match expressions</h2><p>{BODY}</p></body></html>")

# Short enough to trip QA's extraction-collapse gate (under its 500 non-whitespace-char
# floor) but still substantial enough that trafilatura emits a real <head>. A document
# below that structural threshold degrades to headingless body text (see
# backends/html.py), and the chunker would then raise ExtractionFailed for want of an
# admissible web-fragment locator — never reaching the QA gate this test is about.
TINY_HTML = ("<html><body><article><h1 id='a'>Alpha section</h1><p>"
             + "Patterns bind names. " * 20
             + "</p></article></body></html>")


@pytest.fixture
def prepared(db_conn, snapshot_root, tmp_path):
    migrate(db_conn)
    path = tmp_path / "ref.html"
    path.write_text(GOOD_HTML)
    snapshots = SnapshotStore(snapshot_root)
    snapshots.put("rust-ref", path, media_type="text/html",
                  source_url="https://example.org/ref")
    return snapshots


def test_ingest_promotes_chunks_and_writes_the_qa_report(db_conn, prepared, snapshot_root):
    result = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                           locator_kinds=["web-fragment"])

    assert result.promoted is True
    assert result.chunk_count > 0
    assert result.chunk_count == len(SourceChunksStore(db_conn).by_source("rust-ref"))
    assert (snapshot_root / "rust-ref" / "qa" / "report.md").exists()
    assert (snapshot_root / "rust-ref" / "extracted" / "document.json").exists()
    assert SourcingQueue(db_conn).open_entries() == []


def test_a_hard_gate_failure_promotes_nothing_and_queues_the_source(db_conn, snapshot_root,
                                                                    tmp_path):
    migrate(db_conn)
    path = tmp_path / "bad.html"
    path.write_text(TINY_HTML)
    snapshots = SnapshotStore(snapshot_root)
    snapshots.put("bad", path, media_type="text/html")

    with pytest.raises(QaHardGate) as excinfo:
        ingest_source("bad", conn=db_conn, config=CONFIG, snapshots=snapshots,
                      locator_kinds=["web-fragment"])

    assert "extraction-collapse" in [c.check_id for c in excinfo.value.checks]
    assert SourceChunksStore(db_conn).by_source("bad") == []
    entries = SourcingQueue(db_conn).open_entries()
    assert [(e["source_id"], e["reason"]) for e in entries] == [("bad", "partially-ingested")]
    with db_conn.cursor() as cur:
        cur.execute("SELECT promoted, qa_status FROM source_ingestions WHERE source_id='bad'")
        assert cur.fetchone() == (False, "fail")


def test_reingesting_replaces_rather_than_appends(db_conn, prepared):
    first = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                          locator_kinds=["web-fragment"])
    second = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                           locator_kinds=["web-fragment"])
    assert first.chunk_count == second.chunk_count
    assert len(SourceChunksStore(db_conn).by_source("rust-ref")) == second.chunk_count


def test_reingesting_reproduces_the_identical_rows(db_conn, prepared):
    """D1: Postgres is a regenerable derived artifact — re-running ingestion from the same
    snapshot must reproduce the same rows, not merely the same count."""
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["web-fragment"])
    before = SourceChunksStore(db_conn).by_source("rust-ref")
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["web-fragment"])
    assert SourceChunksStore(db_conn).by_source("rust-ref") == before
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM source_chunks")
        assert cur.fetchone()[0] == len(before)


def test_a_gate_failure_demotes_a_previously_promoted_source(db_conn, prepared,
                                                             snapshot_root, tmp_path):
    """The gate is not just a doorman on first entry: a re-ingest that now fails QA must
    take the stale chunks back out rather than leave a refused source readable."""
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["web-fragment"])
    assert SourceChunksStore(db_conn).by_source("rust-ref") != []

    degraded = tmp_path / "degraded.html"
    degraded.write_text(TINY_HTML)
    prepared.put("rust-ref", degraded, media_type="text/html")
    with pytest.raises(QaHardGate):
        ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                      locator_kinds=["web-fragment"])

    assert SourceChunksStore(db_conn).by_source("rust-ref") == []
    with db_conn.cursor() as cur:
        cur.execute("SELECT promoted, chunk_count FROM source_ingestions"
                    " WHERE source_id = 'rust-ref'")
        assert cur.fetchone() == (False, 0)


def test_a_missing_snapshot_is_queued_and_still_raises(db_conn, snapshot_root):
    """D37: a refused source stays visible. A source that was never acquired must not fail
    more quietly than one that fails QA."""
    migrate(db_conn)
    snapshots = SnapshotStore(snapshot_root)
    with pytest.raises(SnapshotMissing):
        ingest_source("ghost", conn=db_conn, config=CONFIG, snapshots=snapshots,
                      locator_kinds=["web-fragment"])
    entries = SourcingQueue(db_conn).open_entries()
    assert [(e["source_id"], e["reason"]) for e in entries] == [("ghost", "acquisition-failed")]
    assert entries[0]["detail"] != ""


def test_an_extraction_failure_is_queued_and_still_raises(db_conn, snapshot_root, tmp_path):
    """A document below trafilatura's structure threshold degrades to headingless body
    text, so no web-fragment locator is admissible and the chunker refuses it — before any
    database write. It must still leave a trace."""
    migrate(db_conn)
    path = tmp_path / "degenerate.html"
    path.write_text("<html><body><h1 id='a'>A</h1><p>b c d</p></body></html>")
    snapshots = SnapshotStore(snapshot_root)
    snapshots.put("degenerate", path, media_type="text/html")

    with pytest.raises(ExtractionFailed):
        ingest_source("degenerate", conn=db_conn, config=CONFIG, snapshots=snapshots,
                      locator_kinds=["web-fragment"])

    entries = SourcingQueue(db_conn).open_entries()
    assert [(e["source_id"], e["reason"]) for e in entries] == [("degenerate",
                                                                "partially-ingested")]
    assert "no admissible locator" in entries[0]["detail"]
    assert SourceChunksStore(db_conn).by_source("degenerate") == []


def test_ingest_resolves_a_pending_source_entry(db_conn, prepared):
    """Section 4.4: claims citing an un-ingested source park in `pending-source` and
    auto-resume the moment the source ingests."""
    SourcingQueue(db_conn).file(kind="pending-source", source_id="rust-ref",
                                reason="not-ingested")
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["web-fragment"])
    assert SourcingQueue(db_conn).open_entries() == []
