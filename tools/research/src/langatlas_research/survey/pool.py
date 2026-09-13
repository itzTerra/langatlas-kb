"""R3's candidate-chunk pool: which chunks a theme's tagging pass reads.

Frozen to a private file (§2.2 private tier) because the orchestrator's enumerator gets no
`RunContext` and so cannot search — and because a pool that re-derived itself on every resume
would silently change what an interrupted pass was tagging. The file holds ids and content
hashes only, never chunk text."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from langatlas_research.config import PoolConfig
from langatlas_research.cycle import Cycle, require_sign_off
from langatlas_research.errors import PoolMissing, PoolStale
from langatlas_research.paths import private_research_dir
from langatlas_research.survey.chunks import ChunkLookup, ChunkRef, SearchFn
from langatlas_research.themes import Theme, load_themes

DIGEST_HEX_LEN = 16


@dataclass(frozen=True)
class Pool:
    cycle_slug: str
    theme_digest: str
    queries: tuple[str, ...]
    entries: tuple[ChunkRef, ...]

    @property
    def digest(self) -> str:
        body = json.dumps(sorted([e.chunk_id, e.content_hash] for e in self.entries))
        return hashlib.sha256(body.encode()).hexdigest()[:DIGEST_HEX_LEN]


def pool_queries(theme: Theme) -> tuple[str, ...]:
    """Label, summary, then each seed term — whitespace-collapsed, case-insensitively
    deduped, in that order."""
    seen: dict[str, str] = {}
    for raw in (theme.label, theme.summary, *theme.seed_terms):
        query = " ".join(raw.split())
        if query and query.lower() not in seen:
            seen[query.lower()] = query
    return tuple(seen.values())


def build_pool(ctx, cycle: Cycle, *, repo_root: Path | None, search_fn: SearchFn,
               lookup: ChunkLookup, config: PoolConfig) -> Pool:
    """@raises SignOffMissing / SignOffStale: D27 before any search runs."""
    require_sign_off(cycle, repo_root=repo_root)
    queries = pool_queries(load_themes(repo_root)[cycle.theme])

    # (hit rank, query index) — every query's rank-0 hit outranks any query's rank-1 hit,
    # so a cap never lets one prolific seed term crowd the others out.
    ranks: dict[str, tuple[int, int]] = {}
    for q_index, query in enumerate(queries):
        for h_index, hit in enumerate(search_fn(query, config.k_per_query)):
            ranks.setdefault(hit["chunk_id"], (h_index, q_index))

    entries: list[ChunkRef] = []
    for chunk_id in sorted(ranks, key=lambda cid: (ranks[cid], cid)):
        if len(entries) >= config.max_chunks:
            break
        ref = lookup(chunk_id)
        if ref is None:
            continue
        entries.append(ChunkRef(chunk_id=ref.chunk_id, source_id=ref.source_id,
                                locator=ref.locator, breadcrumb=ref.breadcrumb,
                                content_hash=ref.content_hash))
    pool = Pool(cycle_slug=cycle.slug, theme_digest=cycle.signed_off["theme_digest"],
                queries=queries, entries=tuple(sorted(entries, key=lambda e: e.chunk_id)))
    ctx.writer.append(role="system", flags=["r3:pool"],
                      content=f"pool {pool.cycle_slug}: {len(pool.entries)} chunks from"
                              f" {len(queries)} queries (digest {pool.digest})")
    return pool


def pool_path(cycle_slug: str) -> Path:
    return private_research_dir() / "pools" / f"{cycle_slug}.json"


def save_pool(pool: Pool) -> Path:
    path = pool_path(pool.cycle_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "cycle_slug": pool.cycle_slug, "theme_digest": pool.theme_digest,
        "queries": list(pool.queries),
        "entries": [{"chunk_id": e.chunk_id, "source_id": e.source_id,
                     "locator": e.locator, "breadcrumb": e.breadcrumb,
                     "content_hash": e.content_hash} for e in pool.entries],
    }, indent=2, sort_keys=True))
    return path


def load_pool(cycle_slug: str) -> Pool:
    """@raises PoolMissing: `survey pool` has not run for this cycle."""
    path = pool_path(cycle_slug)
    if not path.exists():
        raise PoolMissing(f"no frozen pool for {cycle_slug}: run"
                          f" `langatlas-research survey pool <cycle>` first")
    data = json.loads(path.read_text())
    return Pool(cycle_slug=data["cycle_slug"], theme_digest=data["theme_digest"],
                queries=tuple(data["queries"]),
                entries=tuple(ChunkRef(**entry) for entry in data["entries"]))


def require_current_pool(cycle: Cycle, *, repo_root: Path | None = None) -> Pool:
    """The gate plus the pool, together: a pool built for a theme text the developer has
    since changed is refused, even if the cycle was re-signed afterwards.

    @raises SignOffMissing / SignOffStale / PoolMissing / PoolStale"""
    require_sign_off(cycle, repo_root=repo_root)
    pool = load_pool(cycle.slug)
    if pool.theme_digest != cycle.signed_off["theme_digest"]:
        raise PoolStale(f"pool {cycle.slug} was built for theme digest {pool.theme_digest},"
                        f" the cycle is signed off at {cycle.signed_off['theme_digest']}:"
                        f" rebuild it with `langatlas-research survey pool {cycle.number}`")
    return pool


def batches(pool: Pool, size: int) -> list[tuple[ChunkRef, ...]]:
    return [pool.entries[i:i + size] for i in range(0, len(pool.entries), size)]


def batch_key(cycle_slug: str, index: int) -> str:
    return f"{cycle_slug}:batch-{index:04d}"


def parse_batch_key(key: str) -> tuple[str, int]:
    slug, _, batch = key.rpartition(":batch-")
    return slug, int(batch)
