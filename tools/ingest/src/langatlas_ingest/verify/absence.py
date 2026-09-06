from dataclasses import dataclass
from langatlas_ingest.verify.entailment import EntailmentOut, fold_assertions
from langatlas_ingest.verify.evidence import Evidence
from langatlas_ingest.verify.inputs import CitationInput, ClaimInput
from langatlas_pipeline.prompts import load_prompt
from langatlas_pipeline.providers.completion import Sampling

PROMPT_ID = "verify-absence"

# Per alias. Enough to show the model what the source actually says about the feature;
# more would just be the same finding restated at the cost of context.
NEGATIVE_GREP_LIMIT = 5


@dataclass(frozen=True)
class AbsenceResult:
    verdict: str
    out: EntailmentOut
    grep_chunk_ids: tuple[str, ...]
    model: str


def negative_grep(conn, source_id: str, aliases) -> list[str]:
    """D49 step 2: a corpus-wide negative full-text search across every chunk of the
    cited source, using the feature's `aliases: []`.

    Reuses `source_chunks.tsv` — the same generated `tsvector` column and GIN index
    `search.py`'s hybrid FTS branch queries — rather than a sequential `LIKE`/regex scan
    over `text`. `plainto_tsquery` also gives the word-boundary behavior D49 needs for
    free: English stemming folds "generics" to the lexeme `generic`, but "degenericized"
    stems to `degeneric`, so a substring like "generic" inside an unrelated compound word
    does not falsely match. A false hit here would turn a true absence into a
    `contradicted` that blocks a correct fact.

    @pre `aliases` are prose words/phrases (e.g. "generics", "parametric polymorphism"),
        matching every `feature_aliases` example in this codebase and the plan. A purely
        symbolic/operator alias (e.g. `??`, `<=>`, `|>`) tokenizes to nothing under
        `to_tsvector`, which strips punctuation-only tokens — such an alias's literal
        occurrence in a source would silently produce zero hits here, with no
        vector/rerank backstop the way `search.py`'s hybrid branch has one. Widening this
        to cover symbolic aliases is out of scope for D49; this is a known, bounded gap.

    @returns matching chunk ids, deduplicated and ordered (first-seen across aliases,
        then by chunk ordinal within an alias)
    """
    hits: list[str] = []
    with conn.cursor() as cur:
        for alias in aliases:
            cur.execute(
                "SELECT chunk_id FROM source_chunks"
                " WHERE source_id = %s AND tsv @@ plainto_tsquery('english', %s)"
                " ORDER BY ordinal LIMIT %s",
                (source_id, alias, NEGATIVE_GREP_LIMIT))
            hits.extend(row[0] for row in cur.fetchall())
    seen: set[str] = set()
    ordered: list[str] = []
    for chunk_id in hits:
        if chunk_id not in seen:
            seen.add(chunk_id)
            ordered.append(chunk_id)
    return ordered


def run_absence(ctx, conn, *, claim: ClaimInput, citation: CitationInput,
                evidence: Evidence, alias: str, store=None,
                grep_chunk_ids=None) -> AbsenceResult:
    """D49's completeness check: the same ladder and verdict vocabulary as
    `run_entailment` (Task 7), inverted framing.

    Stage 3 here verifies the claimant's own `absence_scope` argument rather than
    searching for a supporting quote. A source that actually documents the feature yields
    `contradicted` and blocks admission — the inverse of K1 (false-absence laundering).

    @param grep_chunk_ids - pre-computed grep hits; None runs `negative_grep` itself
    @param store - a `SourceChunksStore`; injected in tests
    @param alias - a model alias from `config/provider_capabilities.yaml`, never a
        hardcoded Claude/Anthropic model id (D6: Claude is never in the verification loop)

    @returns the verdict, the raw decomposition, the grep hits, and the resolved model
    """
    if store is None:
        from langatlas_ingest.store import SourceChunksStore
        store = SourceChunksStore(conn)
    if grep_chunk_ids is None:
        grep_chunk_ids = tuple(negative_grep(conn, citation.source_id,
                                             claim.feature_aliases))
    grep_chunk_ids = tuple(grep_chunk_ids)

    passages = [evidence.text]
    for chunk_id in grep_chunk_ids:
        found = store.get(chunk_id)
        if found is not None:
            passages.append(f"[{found.locator}] {found.text}")
    delimited = ctx.tool_result(tool=PROMPT_ID, text="\n\n".join(p for p in passages if p),
                                source_id=citation.source_id)

    grep_result = (f"{len(grep_chunk_ids)} passage(s) mention the feature's names"
                   if grep_chunk_ids else "no passage in this source mentions the "
                                          "feature's names")
    prompt = load_prompt(PROMPT_ID)
    messages = prompt.render(claim=claim.claim,
                             absence_scope=claim.absence_scope or "(none argued)",
                             aliases=", ".join(claim.feature_aliases) or "(none)",
                             locator=citation.locator, evidence=delimited,
                             grep_result=grep_result)
    completion = ctx.complete(alias, messages, prompt=prompt, schema=EntailmentOut,
                              sampling=Sampling(temperature=0.0))
    out = completion.parsed
    return AbsenceResult(verdict=fold_assertions(out.assertions), out=out,
                         grep_chunk_ids=grep_chunk_ids,
                         model=completion.resolved_model)
