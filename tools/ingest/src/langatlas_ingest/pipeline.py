# tools/ingest/src/langatlas_ingest/pipeline.py
from dataclasses import dataclass
from typing import Sequence
from langatlas_ingest.chunker import chunk_document
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.errors import ExtractionFailed, QaHardGate, SnapshotMissing
from langatlas_ingest.extract import extract_document
from langatlas_ingest.qa import run_qa
from langatlas_ingest.snapshot import SnapshotStore
from langatlas_ingest.store import SourceChunksStore, SourcingQueue

# Default preference order: the most edition-stable locator a source can carry first,
# since a section survives a re-typeset edition and a page number does not (Section 4.4).
DEFAULT_LOCATOR_KINDS = ("numbered-section", "web-fragment", "book-page", "named-section")


@dataclass
class IngestResult:
    source_id: str
    promoted: bool
    chunk_count: int
    qa_status: str
    qa_report_path: str


def ingest_source(source_id: str, *, conn, config: IngestConfig | None = None,
                  snapshots: SnapshotStore | None = None,
                  locator_kinds: Sequence[str] | None = None) -> IngestResult:
    """Snapshot -> extract -> chunk -> QA -> (promote | hard-gate). The QA verdict is
    always recorded, even when it blocks promotion: a refused source must stay visible,
    never silently missing (D37)."""
    config = config or IngestConfig.load()
    snapshots = snapshots or SnapshotStore()
    kinds = list(locator_kinds or DEFAULT_LOCATOR_KINDS)

    store, queue = SourceChunksStore(conn), SourcingQueue(conn)

    # D37: a refused source stays visible, never silently missing. Everything above the QA
    # gate can fail too — a snapshot that was never acquired, an extractor that finds no
    # text, a chunk with no admissible locator — and those failures happen before any
    # database write, so without this they would leave no trace at all: no ingestion row,
    # no queue entry, nothing for Stage 2's unattended runs to surface. The harder failure
    # must not be the quieter one. The exception still propagates; the queue entry is a
    # record, not a substitute for the caller learning it failed.
    try:
        snapshot = snapshots.get(source_id)
    except SnapshotMissing as missing:
        queue.file(kind="pending-source", source_id=source_id, reason="acquisition-failed",
                   detail=str(missing))
        raise
    try:
        doc = extract_document(snapshot.original_path, source_id=source_id,
                               media_type=snapshot.media_type, config=config,
                               source_url=snapshot.source_url)
        snapshots.write_extracted(source_id, doc)
        chunks = chunk_document(doc, config=config, locator_kinds=kinds)
    except ExtractionFailed as failure:
        # The original is on disk and readable; it is the text or the locators that did not
        # survive it — the same partial state a QA hard gate leaves behind.
        queue.file(kind="pending-source", source_id=source_id, reason="partially-ingested",
                   detail=str(failure))
        raise
    report = run_qa(doc, chunks)
    report_path = snapshots.write_qa(source_id, report)

    promoted = not report.hard_failures
    # One transaction for the whole verdict: `db.connect` is autocommit, so without this
    # a crash between the chunk write and the ingestion row would leave promoted chunks
    # with no record of the run that produced them (D1: Postgres must be reproducible).
    with conn.transaction():
        if promoted:
            store.replace_source(source_id, chunks)
        else:
            store.delete_source(source_id)
        store.record_ingestion(source_id, content_hash=snapshot.content_hash,
                               backend=doc.backend, backend_version=doc.backend_version,
                               chunk_count=len(chunks) if promoted else 0, qa=report,
                               promoted=promoted)
        if not promoted:
            queue.file(kind="pending-source", source_id=source_id,
                       reason="partially-ingested",
                       detail="; ".join(f"{c.check_id}: {c.detail}"
                                        for c in report.hard_failures))
        else:
            # Section 4.4: claims parked on this source auto-resume the moment it lands.
            queue.resolve(source_id=source_id)

    if not promoted:
        raise QaHardGate(source_id, report.hard_failures)
    return IngestResult(source_id=source_id, promoted=True, chunk_count=len(chunks),
                        qa_status=report.status, qa_report_path=str(report_path))
