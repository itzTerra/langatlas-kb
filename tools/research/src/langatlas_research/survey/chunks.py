"""The two ways R3 touches `source_chunks`, behind plain callables so every survey module is
testable without Postgres. The real adapters are the only code here that imports ingest."""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ChunkRef:
    """A chunk's machine-produced identity. `locator` is copied from `source_chunks`
    verbatim and is the only locator any survey artifact may carry (§4.3)."""
    chunk_id: str
    source_id: str
    locator: str
    breadcrumb: str
    content_hash: str
    text: str = ""

    def as_evidence(self) -> dict:
        return {"chunk_id": self.chunk_id, "source_id": self.source_id,
                "locator": self.locator}


ChunkLookup = Callable[[str], "ChunkRef | None"]
SearchFn = Callable[[str, int], list[dict]]


def db_chunk_lookup(conn) -> ChunkLookup:
    from langatlas_ingest.store import SourceChunksStore

    store = SourceChunksStore(conn)

    def _lookup(chunk_id: str) -> ChunkRef | None:
        chunk = store.get(chunk_id)
        if chunk is None:
            return None
        return ChunkRef(chunk_id=chunk.chunk_id, source_id=chunk.source_id,
                        locator=chunk.locator, breadcrumb=chunk.breadcrumb,
                        content_hash=chunk.content_hash, text=chunk.text)

    return _lookup


def db_search_fn(ctx, conn, config=None) -> SearchFn:
    """Runner-mediated `search_sources` (§7.6) — every hit already passes the D31 door
    inside `search_sources` itself."""
    from langatlas_ingest.tools import search_sources

    return lambda query, k: search_sources(ctx, query, k=k, conn=conn, config=config)
