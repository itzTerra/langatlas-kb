"""The surveyor's packet, computed in code rather than by a model: which terms the tagger
found, where they are defined, and how widely. Ranking favours breadth across *sources* over
raw counts, because R3's point is cross-book aliasing — a term one textbook repeats forty times
is less informative than one three books each define once."""
from collections import Counter
from dataclasses import dataclass

from langatlas_research.survey.chunks import ChunkRef
from langatlas_research.survey.pool import Pool
from langatlas_research.survey.tagger import normalize_term
from langatlas_research.survey.tags import ChunkTags

MAX_EVIDENCE = 3


@dataclass(frozen=True)
class TermEntry:
    term: str
    evidence: tuple[ChunkRef, ...]
    defining_sources: tuple[str, ...]
    mention_count: int
    source_count: int
    seed: bool


def build_term_index(tags, pool: Pool, *, min_relevance: int, seed_terms) -> list[TermEntry]:
    refs = {entry.chunk_id: entry for entry in pool.entries}
    defining: dict[str, list[tuple[int, str]]] = {}
    mentions: Counter = Counter()
    sources: dict[str, set[str]] = {}
    for row in tags:
        if row.status != "tagged" or row.relevance < min_relevance or row.chunk_id not in refs:
            continue
        source = refs[row.chunk_id].source_id
        for term in row.defined_terms:
            defining.setdefault(term, []).append((row.relevance, row.chunk_id))
            sources.setdefault(term, set()).add(source)
        for term in row.mentioned_terms:
            mentions[term] += 1
            sources.setdefault(term, set()).add(source)

    entries = []
    for term in sorted(set(defining) | set(mentions)):
        chosen = sorted(defining.get(term, []), key=lambda rc: (-rc[0], rc[1]))[:MAX_EVIDENCE]
        evidence = tuple(refs[chunk_id] for _, chunk_id in chosen)
        defining_sources = tuple(sorted({refs[c].source_id for _, c in defining.get(term, [])}))
        entries.append(TermEntry(term=term, evidence=evidence,
                                 defining_sources=defining_sources,
                                 mention_count=mentions[term],
                                 source_count=len(sources.get(term, ())), seed=False))
    entries.sort(key=lambda e: (-len(e.defining_sources), -len(e.evidence), -e.source_count,
                                -e.mention_count, e.term))

    present = {entry.term for entry in entries}
    for seed in dict.fromkeys(normalize_term(t) for t in seed_terms):
        if seed and seed not in present:
            entries.append(TermEntry(term=seed, evidence=(), defining_sources=(),
                                     mention_count=0, source_count=0, seed=True))
    return entries


def render_term_index(ctx, entries, *, limit: int) -> str:
    """Terms are tagger output lifted from document text and breadcrumbs are document text,
    so the whole index enters the prompt as one D31 block."""
    if not entries:
        return ""
    lines = []
    for entry in entries[:limit]:
        if entry.seed and not entry.evidence and not entry.mention_count:
            lines.append(f"- {entry.term} | seed term with no corpus hits")
            continue
        evidence = "; ".join(f"{ref.chunk_id} ({ref.source_id} {ref.locator}, {ref.breadcrumb})"
                             for ref in entry.evidence) or "none (mentioned only)"
        lines.append(f"- {entry.term} | defined in {len(entry.defining_sources)} sources,"
                     f" mentioned {entry.mention_count}x across {entry.source_count} sources"
                     f" | evidence: {evidence}")
    return ctx.tool_result(tool="r3-term-index", text="\n".join(lines), source_id=None,
                           kind="tag-index")


def tagging_summary(tags, *, min_relevance: int) -> dict:
    tagged = [row for row in tags if row.status == "tagged"]
    prompts = Counter(row.prompt_ref for row in tagged)
    return {"prompt": prompts.most_common(1)[0][0] if prompts else "",
            "models": sorted({row.resolved_model for row in tagged if row.resolved_model}),
            "chunks_tagged": len(tagged),
            "chunks_relevant": sum(1 for row in tagged if row.relevance >= min_relevance)}
