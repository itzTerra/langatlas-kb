"""R3's corpus tagger — the volume lane (D6): university API, runner-mediated chunk text
(§7.6), one completion per batch.

The tagger's output is never trusted for anything mechanical. Terms are grounded against
the chunk text in code (a term that is not in the passage is dropped and counted), chunk ids
are checked against the batch actually sent, and chunks that changed or vanished since the
pool was frozen are recorded without ever reaching the model."""
from dataclasses import dataclass

from pydantic import BaseModel, Field

from langatlas_pipeline.prompts import PromptRef, load_prompt
from langatlas_research.errors import TaggerOutputInvalid
from langatlas_research.survey.chunks import ChunkLookup, ChunkRef
from langatlas_research.survey.tags import ChunkTags, TagStore
from langatlas_research.themes import Theme

TAGGER_PROMPT_ID = "r3-tagger"
MAX_TERMS = 8


class ChunkTagOut(BaseModel):
    chunk_id: str
    relevance: int = Field(ge=0, le=3)
    defined_terms: list[str] = Field(default_factory=list)
    mentioned_terms: list[str] = Field(default_factory=list)


class TagBatchOut(BaseModel):
    chunks: list[ChunkTagOut]


@dataclass(frozen=True)
class TagBatchResult:
    tagged: int = 0
    skipped: int = 0
    missing: int = 0
    stale: int = 0
    dropped_terms: int = 0


def normalize_term(term: str) -> str:
    return " ".join(term.split()).lower()


def ground_terms(terms, text: str) -> tuple[tuple[str, ...], int]:
    """@returns: (normalized terms that occur in `text`, deduped, capped at MAX_TERMS;
        how many proposed terms were dropped as ungrounded)."""
    haystack = normalize_term(text)
    kept: list[str] = []
    dropped = 0
    for term in terms:
        normalized = normalize_term(term)
        if not normalized or normalized not in haystack:
            dropped += 1
        elif normalized not in kept and len(kept) < MAX_TERMS:
            kept.append(normalized)
    return tuple(kept), dropped


def _render_chunks(ctx, refs: list[ChunkRef]) -> str:
    """One D31 block per chunk. The `chunk_id:` line is ours, but it sits inside the block
    with the document text so nothing is concatenated around delimited content."""
    return "\n\n".join(
        ctx.tool_result(tool="r3-tagger", source_id=ref.source_id, kind="source-chunk",
                        text=f"chunk_id: {ref.chunk_id}\n{ref.breadcrumb}\n{ref.text}")
        for ref in refs)


def _placeholder(ref: ChunkRef, status: str, prompt: PromptRef) -> ChunkTags:
    return ChunkTags(chunk_id=ref.chunk_id, content_hash=ref.content_hash, status=status,
                     relevance=0, defined_terms=(), mentioned_terms=(), dropped_terms=0,
                     prompt_ref=prompt.ref(), resolved_model="")


def tag_batch(ctx, theme: Theme, cycle_slug: str, batch, *, lookup: ChunkLookup,
              store: TagStore, alias: str, prompt: PromptRef | None = None) -> TagBatchResult:
    """@raises TaggerOutputInvalid: the response names none of the chunks it was sent.
    @raises BudgetExceeded / StructuredOutputError: from `ctx.complete`, unchanged — the
        orchestrator turns the first into a clean pause."""
    prompt = prompt or load_prompt(TAGGER_PROMPT_ID)
    counts = {"tagged": 0, "skipped": 0, "missing": 0, "stale": 0, "dropped_terms": 0}
    fresh: list[ChunkRef] = []
    for ref in batch:
        live = lookup(ref.chunk_id)
        if live is None:
            store.put(cycle_slug, _placeholder(ref, "missing", prompt))
            counts["missing"] += 1
        elif live.content_hash != ref.content_hash:
            store.put(cycle_slug, _placeholder(ref, "stale", prompt))
            counts["stale"] += 1
        else:
            fresh.append(live)
    if not fresh:
        return TagBatchResult(**counts)

    messages = prompt.render(theme_label=theme.label, theme_summary=theme.summary,
                             seed_terms=", ".join(theme.seed_terms),
                             chunk_ids=", ".join(ref.chunk_id for ref in fresh),
                             chunks=_render_chunks(ctx, fresh))
    completion = ctx.complete(alias, messages, prompt=prompt, schema=TagBatchOut)
    wanted = {ref.chunk_id for ref in fresh}
    answers = {out.chunk_id: out for out in completion.parsed.chunks if out.chunk_id in wanted}
    if not answers:
        raise TaggerOutputInvalid(
            f"{cycle_slug}: tagger response named none of {sorted(wanted)}")

    for ref in fresh:
        out = answers.get(ref.chunk_id)
        if out is None:
            store.put(cycle_slug, _placeholder(ref, "skipped", prompt))
            counts["skipped"] += 1
            continue
        defined, dropped_d = ground_terms(out.defined_terms, ref.text)
        mentioned, dropped_m = ground_terms(out.mentioned_terms, ref.text)
        mentioned = tuple(t for t in mentioned if t not in defined)
        store.put(cycle_slug, ChunkTags(
            chunk_id=ref.chunk_id, content_hash=ref.content_hash, status="tagged",
            relevance=out.relevance, defined_terms=defined, mentioned_terms=mentioned,
            dropped_terms=dropped_d + dropped_m, prompt_ref=prompt.ref(),
            resolved_model=completion.resolved_model))
        counts["tagged"] += 1
        counts["dropped_terms"] += dropped_d + dropped_m
    return TagBatchResult(**counts)
