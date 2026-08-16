# tools/ingest/src/langatlas_ingest/pipeline.py
from dataclasses import dataclass
from typing import Sequence
from langatlas_ingest.chunker import chunk_document, chunking_fingerprint
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.errors import (
    ExtractionFailed, IngestError, QaHardGate, SnapshotMissing,
)
from langatlas_ingest.extract import backend_identity, extract_document
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
    # True when this call proved the stored ingestion was already current and did no
    # work. Reported rather than hidden: a `reingest` sweep that skips everything and one
    # that silently failed to run must not look the same to the developer.
    skipped: bool = False


def _is_current(existing: dict | None, *, content_hash: str,
                backend: tuple[str, str] | None, kinds: list[str],
                chunking: dict) -> bool:
    """Whether the stored ingestion already reflects exactly this run's inputs.

    `replace_source` is a delete-then-reinsert, and the embedding tables reference
    `source_chunks(chunk_id) ON DELETE CASCADE` — so re-ingesting a source that did not
    actually change throws away every embedding it has and costs a full re-embed on the
    paid, rate-limited provider (1263 calls for the real Van Roy & Haridi corpus) to
    arrive back at byte-identical rows. Every input that can change the stored chunks is
    compared here: the snapshot's own content hash, the backend and its version, the
    locator-kind preference order, and the chunking fingerprint (which carries the
    source's `min_chars` QA floor too — see `chunking_fingerprint`).

    That last one is what stops the skip from being a trap. The chunk boundaries are a
    product of the config knobs (`chunking.target_tokens`/`max_tokens`/`overlap_tokens`)
    and of the chunker/QA code itself, neither of which the other four inputs can see:
    without them, tuning chunk size in `config/ingest.yaml` and re-running a source
    silently kept the old chunks — no error, no warning, and no recovery short of
    deleting the `source_ingestions` row by hand. Detection has to be automatic, because
    the failure mode is silence. The source's `min_chars` floor rides in the same
    fingerprint for the same reason: it moves the promotion verdict for content that did
    not change, so re-ingesting under a new floor must not be skipped as unchanged.

    Anything unknown or unequal — including a prior run that was not promoted, and a row
    written before the fingerprint existed, whose empty `chunking` can never equal a real
    one — falls through to the full pipeline."""
    return bool(existing and backend and existing["promoted"]
                and existing["content_hash"] == content_hash
                and existing["backend"] == backend[0]
                and existing["backend_version"] == backend[1]
                and list(existing["locator_kinds"] or []) == kinds
                and (existing["chunking"] or {}) == chunking)


def ingest_source(source_id: str, *, conn, config: IngestConfig | None = None,
                  snapshots: SnapshotStore | None = None,
                  locator_kinds: Sequence[str] | None = None,
                  min_chars: int | None = None) -> IngestResult:
    """Snapshot -> extract -> chunk -> QA -> (promote | hard-gate). The QA verdict is
    always recorded, even when it blocks promotion: a refused source must stay visible,
    never silently missing (D37)."""
    config = config or IngestConfig.load()
    snapshots = snapshots or SnapshotStore()
    store, queue = SourceChunksStore(conn), SourcingQueue(conn)
    # Only used if the snapshot itself is missing; the real preference order comes from
    # the snapshot manifest below, which is the thing that survives to the next run.
    kinds = list(locator_kinds or DEFAULT_LOCATOR_KINDS)

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

    # D1: the locator preference order is a *stored* property of the source, not a flag
    # the developer has to remember. An explicit argument is an override and updates what
    # is stored (so the next run reproduces this one); otherwise the snapshot's own value
    # wins, and only a source that has never had one falls back to the default order.
    if locator_kinds is not None:
        kinds = list(locator_kinds)
        if kinds != list(snapshot.locator_kinds or []):
            snapshot = snapshots.set_locator_kinds(source_id, kinds)
    else:
        kinds = list(snapshot.locator_kinds or DEFAULT_LOCATOR_KINDS)

    # Same rule again for the QA floor: an explicit argument overrides and persists, so
    # the run that admitted a legitimately tiny source is the run a re-ingest reproduces;
    # otherwise the snapshot's stored value wins; a source that never had one keeps
    # `None` and gets `run_qa`'s own default floor.
    if min_chars is not None:
        if min_chars != snapshot.min_chars:
            snapshot = snapshots.set_min_chars(source_id, min_chars)
    else:
        min_chars = snapshot.min_chars

    backend = backend_identity(snapshot.media_type, config)
    existing = store.ingestion(source_id)
    chunking = chunking_fingerprint(config, min_chars=min_chars)
    # The chunk count is checked against the table, not just the bookkeeping row: the
    # skip is only sound while the chunks it points at are actually there. A source whose
    # rows were dropped (a targeted `delete_source`, a partially restored database) would
    # otherwise be skipped forever on the strength of a stale `promoted = true`, and stay
    # silently missing from the corpus — the exact failure D37 refuses to allow.
    if (_is_current(existing, content_hash=snapshot.content_hash, backend=backend,
                    kinds=kinds, chunking=chunking)
            and store.count_by_source(source_id) == existing["chunk_count"]):
        # Nothing that determines the stored chunks has changed, so re-extracting would
        # reproduce them byte for byte — and re-writing them would cascade away every
        # embedding for the source (see `_is_current`). Report the existing state.
        return IngestResult(source_id=source_id, promoted=True,
                            chunk_count=existing["chunk_count"],
                            qa_status=existing["qa_status"],
                            qa_report_path=str(snapshots.dir_for(source_id) / "qa"
                                               / "report.md"),
                            skipped=True)
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
    report = run_qa(doc, chunks, min_chars=min_chars)
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
                               promoted=promoted, locator_kinds=kinds,
                               chunking=chunking)
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


def reingest_all(*, conn, config: IngestConfig | None = None,
                 snapshots: SnapshotStore | None = None
                 ) -> dict[str, IngestResult | IngestError]:
    """D1's "drop the database and re-run ingestion from the snapshot store", as one
    runnable operation rather than a loop the developer reconstructs from memory. Each
    source is re-ingested with its own stored `locator_kinds`, so the regenerated
    locators are the ones that are already public.

    A source that fails does not abort the sweep: its failure is already recorded in the
    sourcing queue and in `source_ingestions`, and stopping would leave the rest of a
    known-good corpus unregenerated. The failure is returned in place of a result so the
    caller can report it."""
    config = config or IngestConfig.load()
    snapshots = snapshots or SnapshotStore()
    results: dict[str, IngestResult | IngestError] = {}
    for source_id in snapshots.sources():
        try:
            results[source_id] = ingest_source(source_id, conn=conn, config=config,
                                               snapshots=snapshots)
        except IngestError as failure:
            results[source_id] = failure
    return results
