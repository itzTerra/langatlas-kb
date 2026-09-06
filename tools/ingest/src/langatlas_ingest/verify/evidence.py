from dataclasses import dataclass
from langatlas_ingest.config import IngestConfig

# Section 6.2's small-to-big trigger: below this the chunk is too thin to judge on its
# own, so the parent section is offered instead.
SMALL_CHUNK_TOKENS = 300
# How wide the scoped rescue searches. Three is enough to say "the claim is clearly
# somewhere else in this book"; more would just be a longer hint.
BOUNCE_HINT_K = 3


@dataclass(frozen=True)
class Evidence:
    """What stage 1 hands to stages 2 and 3.

    `hint` is deliberately separate from `text`: a scoped-retrieval rescue is a BOUNCE
    HINT, never evidence. Fusing them would let a strong hit far from the claimed locator
    silently pass a wrong citation, which is the exact failure Section 6.2 forbids."""

    chunk_ids: tuple[str, ...] = ()
    text: str = ""
    resolution: str = "none"          # exact | containment | none
    expanded: bool = False
    hint: str = ""

    @property
    def resolved(self) -> bool:
        return bool(self.chunk_ids)


def _bounce_hint(search, *, source_id: str, claim_text: str, config: IngestConfig) -> str:
    """Section 6.2's rescue: a scoped hybrid search over the cited source alone, offered
    only as a pointer for the sourcing queue — never as evidence text (see `Evidence`).

    @returns the hint string, or "" when nothing in the scoped pool clears the floor
    """
    hits = search.search(claim_text, k=BOUNCE_HINT_K, source_ids=[source_id])
    strong = [hit for hit in hits if hit.score >= config.relevance_floor]
    if not strong:
        return ""
    best = strong[0]
    return (f"the claim's text retrieves strongly at {best.chunk.locator!r}"
            f" ({best.chunk.chunk_id}); the cited locator resolves to nothing")


def resolve_evidence(conn, ctx, *, source_id: str, locator: str, claim_text: str,
                     config: IngestConfig | None = None, index=None, store=None,
                     search=None) -> Evidence:
    """Section 6.2's stage-1 resolution ladder.

    exact locator match -> containment (range overlap) -> scoped hybrid retrieval as a
    **bounce hint only**. Then small-to-big: when the resolved text is thinner than
    `SMALL_CHUNK_TOKENS`, offer the parent section instead, bounded by
    `retrieval.max_section_tokens` so an expansion cannot silently fill a context.

    `exact` vs `containment` is decided on the chunk's own display locator, because
    `PostgresSourceChunksIndex` resolves both in one overlap query — the distinction is
    recorded for the ledger, not used to gate anything.

    @param conn - a psycopg connection; unused when `index`/`store`/`search` are injected
    @param claim_text - the canonical claim string, used only for the rescue query
    @pre index/store/search, if given, satisfy `PostgresSourceChunksIndex`/
        `SourceChunksStore`/`SourceSearch`'s `resolve`/`get`/`search`+`get_section` shapes

    @returns an `Evidence`; `resolved` is False when the locator resolves to nothing
    """
    config = config or IngestConfig.load()
    if index is None:
        from langatlas_ingest.index import PostgresSourceChunksIndex
        index = PostgresSourceChunksIndex(conn)
    if store is None:
        from langatlas_ingest.store import SourceChunksStore
        store = SourceChunksStore(conn)
    if search is None:
        from langatlas_ingest.search import SourceSearch
        search = SourceSearch(conn, ctx, config=config)

    chunk_ids = index.resolve(source_id, locator)
    chunks = [c for c in (store.get(cid) for cid in chunk_ids) if c is not None]
    if not chunks:
        return Evidence(hint=_bounce_hint(search, source_id=source_id,
                                          claim_text=claim_text, config=config))

    resolution = "exact" if any(c.locator == locator for c in chunks) else "containment"
    expanded = False
    if sum(c.token_count for c in chunks) < SMALL_CHUNK_TOKENS and chunks[0].parent_section_id:
        section = search.get_section(chunks[0].chunk_id)
        if section and sum(c.token_count for c in section) <= config.max_section_tokens:
            chunks, expanded = section, True

    return Evidence(chunk_ids=tuple(c.chunk_id for c in chunks),
                    text="\n\n".join(c.text for c in chunks),
                    resolution=resolution, expanded=expanded)
