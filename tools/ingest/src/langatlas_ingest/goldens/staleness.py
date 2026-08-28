from dataclasses import dataclass
from langatlas_ingest.index import PostgresSourceChunksIndex
from langatlas_ingest.store import SourceChunksStore


@dataclass(frozen=True)
class StaleItem:
    item_id: str
    reason: str


def check_staleness(conn, items) -> list[StaleItem]:
    """Report golden items whose grounding no longer exists in the live corpus.

    Soft by contract (Section 6.4): this returns findings and never raises, and its CLI
    always exits 0. A re-ingest that renumbers chunks would otherwise turn the whole
    calibration set red overnight for a reason that has nothing to do with calibration.

    @returns one `StaleItem` per item with a broken grounding, in item order
    """
    index, store = PostgresSourceChunksIndex(conn), SourceChunksStore(conn)
    stale = []
    for item in items:
        # A fabricated locator is *supposed* to point nowhere; reporting it would train
        # the developer to ignore this report.
        if item.stratum == "fabricated-locator":
            continue
        missing = [chunk_id for chunk_id in item.evidence_chunk_ids
                   if store.get(chunk_id) is None]
        if missing:
            stale.append(StaleItem(item.id, f"evidence chunks gone: {missing}"))
            continue
        if not index.resolve(item.citation.source, item.citation.locator):
            stale.append(StaleItem(item.id, f"locator {item.citation.locator!r} no"
                                            " longer resolves"))
    return stale
