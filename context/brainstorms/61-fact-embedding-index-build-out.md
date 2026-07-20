# 61 — Fact-Embedding Index Build-Out

> Backlog brainstorm for LangAtlas. Topic (checklist item 61): concretely design the schema,
> refresh cadence, and shared use of a fact-level embedding index — named in D7 ("embed: fact
> cards, feature descriptions, source excerpts... each with `{chunk_type, ...}` metadata") and
> leaned on by three later brainstorms without ever being designed itself: topic 56's contradiction
> scan (candidate pool via "embedding top-k pool over a new fact-embedding index"), D8's original
> `search_knowledge` tool, and topic 53's loader (`knowledge_embeddings` cache-keying table, keyed
> `(embedding_model_id, fact_id)`). Binding context: D7 (Postgres+pgvector from day one, the
> original `chunk_type` metadata shape); D8 (`search_knowledge` — hybrid search, relevance as
> primary sort key per D35); D15/D26 (`source_chunks` — the sibling index this one is explicitly
> *not* merged with); D22 (embedding-model benchmark subphase, fact-index model choice deferred to
> sweep-pipeline start); D23 (content-keyed `f-<12-hex>` fact ids, copyedit-tolerant hashing);
> D26 (`RunContext` cache, provider split — Claude judgment / university-API volume); D35/D58 (the
> loader's blue-green shadow-schema build, `knowledge_embeddings` cache-keying table, `(embedding_model_id,
> fact_id)` keying already recommended there); D47/brainstorm 39 (claim-template `render:` blocks,
> `rendered_text` as a precomputed bundle column, blast-radius-surfaced re-embed triggers); D59/
> brainstorm 56 (the contradiction-scan candidate pool, O1b); D60/brainstorm 57 (the public/
> pipeline-only MCP boundary test, `search_knowledge`'s existing "hybrid search over the fact
> index" status). All proposals below are *proposed*, not ratified, per the project's
> decision-hygiene convention.

## Problem framing

Three separate brainstorms have each assumed a fact-level embedding index exists, cited it as
already-planned (correctly — D7 names it), and then moved on without ever pinning down its
concrete shape:

- **Topic 56** (contradiction scan) needs it as a candidate-generation pool: embed each newly
  admitted fact's canonical claim string, retrieve the top-k most similar existing claims above a
  cosine floor, feed that pool to the claim-vs-claim comparison call. It explicitly ruled out
  piggybacking `source_chunks` (different content, different lifecycle, different consumer) and
  explicitly deferred embedding-model choice to "whatever D22's fact-index benchmark selects" —
  but never designed the table itself.
- **D8's `search_knowledge`** (the MCP tool everyone assumes just works) is specified only as
  "hybrid search, returns fact cards" over "the fact index" — the same index D7 sketches
  metadata for, but D8 never says what table backs it, what gets embedded per fact, or how it's
  kept fresh as facts are added, corrected, or superseded.
- **Topic 53** (Postgres loader) went one level deeper than either — it named a concrete
  `knowledge_embeddings` lookup table and settled the cache-reuse keying question
  (`(embedding_model_id, fact_id)`, reusing D23's content-derived fact ids directly) — but scoped
  itself to *cache-reuse mechanics during a load*, not the index's own schema, what text gets
  embedded, or its refresh/rebuild cadence outside a load.

None of these three treatments contradicts another — they're compatible fragments of the same
design, assembled from three different entry angles. What's missing is the thing this brainstorm
exists to produce: one concrete schema, one concrete "what gets embedded" answer, one concrete
refresh cadence, and an explicit statement of which of the three candidate consumers (contradiction
scan, site search, `search_knowledge`) actually share this index versus needing something else.

**Scale grounding**, carried from brainstorms 25/37/56: low hundreds of ontology nodes, tens of
thousands of derived per-field facts (D23's derived-ID scheme), bursty onboarding-phase growth
(a whole sweep phase lands over days, quiet stretches between phases). Same shape topic 56 already
sized its candidate-pool cost against — this index is the retrieval structure that both jobs sit
on top of, not a new cost center in its own right.

Four sub-problems, matching the checklist line:

1. **Schema** — what table, what's embedded per row, what metadata, what embedding model.
2. **Relationship to Postgres/D58's blue-green loader** — where index build fits the shadow-schema
   lifecycle.
3. **Refresh/build cadence** — event-driven vs. batch vs. full-rebuild-on-model-swap.
4. **Shared consumers** — does one index really serve the contradiction scan, site search, and
   `search_knowledge` all at once, or does one of those three actually want something else?

## Options with trade-offs

### O1 — Schema: one table, or split by `chunk_type`?

D7's original framing already proposed a single index with `chunk_type` as a discriminator column
(`fact | feature-description | source-excerpt`), before brainstorm 21 split `source-excerpt` out
into its own `source_chunks` table for lifecycle reasons (source text is append-mostly, rarely
re-embedded, huge relative to fact claims; fact claims are small, numerous, and re-embedded on
every content change). That split is already ratified (D15) and this brainstorm doesn't reopen it.
The live question is narrower: within the *fact-embedding* side of D7's original sketch, is it one
table with `chunk_type IN ('fact', 'feature-description')`, or two separate tables?

**O1a (recommended) — one table, `knowledge_embeddings`, `chunk_type` discriminator.** Both fact claims
and feature/concept descriptions are short, canonical, denormalized text units that get embedded
once, re-embedded on content change, and queried the same way (cosine top-k, optionally filtered
by metadata). Splitting them into two tables would duplicate the schema, the loader logic, and the
cache-keying discipline for no retrieval-time benefit — a query that wants "fact claims only" or
"feature descriptions only" is a one-column `WHERE chunk_type = 'fact'` filter, exactly D7's
original design already assumed for the whole index before the source-excerpt split motivated
carving that one lifecycle-divergent slice out. Naming it `knowledge_embeddings` (matching D58's already
-used name) rather than a more generic `knowledge_embeddings` keeps continuity with the one concrete
name that's already appeared in a ratified decision (D58), even though it will carry
feature/concept-description rows too — the name is a legacy label, not a scope constraint, the same
way `contradictions.yaml` isn't renamed every time D45/D59 add a new record type to it.

**O1b — rejected: separate `knowledge_embeddings` and `feature_embeddings` tables.** No consumer
identified anywhere in D7/56/57/58 needs feature-description embeddings and fact-claim embeddings
kept in physically separate tables — `search_knowledge`'s hybrid search wants both in one ranked
result set (a query for "pattern matching" should surface both the Rust pattern-matching feature
page and specific facts about it, ranked together), and the contradiction scan only ever needs the
`fact` rows. Splitting adds a second table, a second index, a second migration surface, for a
distinction a `WHERE` clause already handles.

**Schema (concrete, `knowledge_embeddings` table):**

```sql
CREATE TABLE knowledge_embeddings (
    chunk_type          text NOT NULL,          -- 'fact' | 'feature-description'
                                                  -- (concept-description rows reuse the same
                                                  -- discriminator value once D16's Concept
                                                  -- pages exist; no schema change needed)
    subject_id          text NOT NULL,           -- fact_id (D23 f-<12hex>) for chunk_type='fact';
                                                  -- feature/concept node id (D16) otherwise
    embedding_model_id   text NOT NULL,          -- resolved model id, D26 RunContext convention
    embedding            vector(N) NOT NULL,      -- N = D22 benchmark's chosen dimension
    rendered_text        text NOT NULL,           -- the exact string that was embedded — D47's
                                                  -- rendered_text for chunk_type='fact', the
                                                  -- feature/concept's canonical description
                                                  -- field otherwise
    -- filter metadata, mirroring D7's original {chunk_type, feature_id, language_id, source_id,
    -- status} sketch, extended with the fields D25/D59 need at query time:
    feature_id           text,                    -- null for non-feature-scoped facts
    language_id          text,                    -- null for feature/concept rows and
                                                  -- language-independent facts
    status                text NOT NULL,           -- verification status (D25) — filter-first,
                                                  -- matching D7's "filter-first, then hybrid"
                                                  -- search design
    controversy_level    smallint,                -- D25's ordinal score, present for facts only
    PRIMARY KEY (embedding_model_id, chunk_type, subject_id)
);
CREATE INDEX ON knowledge_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON knowledge_embeddings (chunk_type, feature_id);
```

The primary key deliberately includes `embedding_model_id`: D22's benchmark and any later
model-swap needs both the old and new model's vectors briefly coexisting during a rebuild (see
O3), and this is the same `(embedding_model_id, fact_id)` shape D58 already committed to for
cache-keying — this schema is that recommendation given a concrete table definition, not a new
design decision layered on top of it.

**What gets embedded per fact — resolved, not open.** D47 already answers this precisely: the
claim-template registry's `rendered_text` — the deterministic, always-current English rendering of
a fact's canonical claim — is already specified as "a precomputed D35 bundle column." Embedding
`rendered_text` rather than raw record YAML or a hand-assembled string means the embedding input is
exactly the same text the site/MCP already render for that fact, so a claim's *semantic* content and
its *embedded* content are provably the same string, and a `render:`-wording-only edit (D47) is
*by construction* the trigger for re-embedding that fact (see O3) — no separate "what to embed"
decision was needed here at all once D47 existed; this brainstorm's contribution is noticing that
D47's own text already answers it and wiring the two together explicitly.

### O2 — Relationship to Postgres and D58's blue-green loader

**O2a (recommended) — the embedding index lives inside the same shadow-schema lifecycle as
everything else the loader builds.** D58 already established this pattern for the whole bundle
load: bulk `COPY` into a fresh `data_vN` schema, indexes (pgvector ANN + tsvector FTS) built after
`COPY` completes, entirely inside the isolated shadow schema, atomic view-swap exposes it all at
once. `knowledge_embeddings` is not a special case — it is one more table populated during that same
build, using the exact cache-reuse keying D58 already specified: for each fact/feature row in the
new bundle, check whether `(embedding_model_id, subject_id)` already has a row with matching
`rendered_text` in the *previous* live schema; if so, copy the vector across without a fresh
embedding call; if not (new fact, or `rendered_text` changed), compute fresh via `RunContext`
(D26). This is a straight application of D58 §2.3's already-ratified logic, generalized from
"facts" to "facts and feature/concept descriptions" — no new mechanism.

**Where the embedding computation itself happens relative to the loader.** D58 already resolves
this too: embeddings are computed *before* the shadow schema's bulk `COPY` (so the ANN index build
has complete data in one pass). Concretely, this means the *dataset bundle itself* (D35's zstd
SQLite artifact) should carry precomputed embedding vectors as a bundle column, computed once during
the build pipeline (not per-loader-run) — the loader's job during load-into-Postgres is copying
those vectors across (with cache-reuse skipping recompute for unchanged rows), not calling an
embedding model itself. This keeps embedding-model API calls entirely inside the bundle-build
pipeline (which already goes through `RunContext`/D26 for every other LLM and embedding call in the
project) rather than teaching the loader script a second embedding-call path — the loader stays
"data movement," matching D58's own stated design philosophy for what the loader script should and
shouldn't do.

**O2b — rejected: embed on-demand at query time / lazily.** No consumer (contradiction scan, site
search, MCP) can tolerate query-time embedding latency for the *stored* side of the index — only
the *query string* itself needs a query-time embedding call (one short string per search request,
already implied by any hybrid-search design), which is unrelated to this question. Lazily embedding
stored facts would mean an index that's silently incomplete until enough queries happen to touch
every fact, which is nonsensical for a corpus meant to be exhaustively searchable.

### O3 — Refresh/rebuild cadence

Three distinct triggers, cleanly separable, mirroring how D58/D59 already separate "your data
changed" from "your model changed":

**O3a — Per-load, incremental, driven by content change (primary mechanism, recommended).**
Every dataset-bundle build (D35 — itself triggered per D58's existing invocation points: the site's
`repository_dispatch` build, the scheduled kb-repo job, manual local loads) re-renders every
templated fact's `rendered_text` (D47 — always cheap, always happens) and re-embeds only the rows
whose `rendered_text` actually changed content, via the `(embedding_model_id, subject_id,
rendered_text)` cache-reuse check from O2a. This is not a separate cadence decision from "how often
does the bundle get rebuilt" — it rides whatever cadence D35/D58 already run at. A quiet week
produces a near-empty diff (near-zero embedding calls); an onboarding-phase sweep landing hundreds
of facts produces hundreds of embedding calls, the same bursty-but-cheap shape topic 56 already
sized its own downstream cost estimate against.

**O3b — Full rebuild on embedding-model swap (rare, explicit trigger).** When D22's benchmark
selects a new model (initial selection, or a later re-benchmark), every row needs re-embedding
under the new `embedding_model_id` — this is not a partial diff, since changing the model changes
every vector regardless of whether the underlying text changed. Mechanically this is not a special
loader mode: it's an ordinary bundle build where the cache-reuse check at O2a's `(embedding_model_id,
...)` key finds *zero* matches (new model id, so every row looks "new"), so every row gets
re-embedded — the primary-key design already makes this fall out for free rather than needing a
dedicated "rebuild" code path. This is the same event D59/brainstorm 56 already names as its own
rare backstop-rescan trigger for the contradiction scan, so both consumers naturally re-derive
fresh state off the same underlying event with no extra coordination needed.

**O3c — No fixed calendar cadence.** Mirroring D25/D59's already-established "event-driven, not a
fixed interval" philosophy (re-verification, contradiction-scan cadence), a fixed nightly/weekly
re-embed sweep would either do nothing during quiet stretches or lag behind a fast-moving onboarding
burst until the next scheduled run. O3a's per-build incremental behavior already tracks content
changes at whatever granularity the bundle itself gets rebuilt, so no separate calendar-driven
re-embed job is proposed.

**Recommendation: O3a as the only routine mechanism (piggybacking the existing bundle-build
cadence, zero new scheduling), O3b as the one explicit non-routine trigger (model swap), no O3c
calendar job.** This mirrors D59's own cadence philosophy for the contradiction scan almost exactly
— consistent, not coincidental, since both are downstream of the same fact corpus's own change
rate.

### O4 — Shared use across the three named consumers

This is the sub-problem topic 56 explicitly flagged as unresolved ("no brainstorm has concretely
designed... its shared use... across this job, the site's search box, and D8's `search_knowledge`
MCP tool"). Resolving each of the three in turn:

**Contradiction scan (topic 56/D59).** Already fully specified by brainstorm 56's O1b: query
`knowledge_embeddings` filtered to `chunk_type = 'fact'`, `ORDER BY embedding <=> :new_fact_embedding
LIMIT k` (k=10–20), cosine floor ≈0.75. This schema (O1 above) is a direct, no-changes-needed fit
for that query shape — `chunk_type`/`status` are already indexed filter columns, `subject_id` is
the fact id the comparison call needs to look up the full fact record. **This consumer needs
nothing further designed here; O1's schema already serves it exactly as brainstorm 56 assumed.**

**`search_knowledge` (D8, public MCP).** D8 specifies "hybrid search, returns fact cards" and D26/
brainstorm 57 confirm it as a public tool returning admitted, verified fact content — never raw
pre-verification evidence. D7's original retrieval design ("filter-first, then hybrid BM25/FTS +
vector fused with RRF, k=5, relevance floor") already describes the query pattern this index needs
to support: `knowledge_embeddings` supplies the vector side, a `tsvector` column (added to the same
table, or a parallel `search_vector` computed column — standard Postgres FTS practice) supplies the
lexical side, RRF fuses them. **This is the same table as the contradiction scan's, queried
differently** — a `WHERE status = 'admitted'` (or whatever D25's terminology settles as the
"safe to surface publicly" status) filter plus RRF-fused ranking instead of a raw cosine top-k. No
separate index needed for this consumer; it's the same `knowledge_embeddings` table topic 56 already
assumed, confirmed here as the concrete backing store D8 never named.

One clarification worth being explicit about, since brainstorm 57's table already distinguishes
`search_knowledge` from `search_sources`: **`search_knowledge` was never meant to query
`source_chunks`** — brainstorm 21's own comparison table lists `search_sources` vs `search_knowledge`
as the two tools that motivated keeping the indexes separate in the first place. This brainstorm
doesn't change that boundary; it just gives `search_knowledge`'s side of it (the fact index) the
concrete schema it was always implicitly promised.

**Site search.** Brainstorm 19 (D33) already chose **Pagefind** as the default on-site search —
a static, client-side, build-time-indexed search library that crawls the *rendered HTML pages*
of the Astro static site, entirely independent of Postgres, pgvector, or this brainstorm's index.
Pagefind and `knowledge_embeddings` are not competing designs for the same job; they serve different
architectural layers (D33 explicitly deferred a public API-backed hybrid search as a
post-launch option). **Recommendation: `knowledge_embeddings` stays a pipeline-and-MCP-only index at
v0** — it feeds `search_knowledge` (agent-facing, Postgres-backed MCP) and the contradiction scan
(pipeline-internal), but not the public website's search box, which stays Pagefind's static index
per D33's already-ratified choice. If D33's deferred "public FastAPI hybrid search" option is ever
built, it would be a *third* consumer of this same `knowledge_embeddings` table (via the FastAPI adapter
D8 already names for non-MCP providers) rather than a reason to build a fourth index — but that
build is explicitly out of scope until D33's own deferred trigger fires.

**Consolidated answer to O4:** one table (`knowledge_embeddings`, O1), two live consumers today
(contradiction scan via raw cosine top-k; `search_knowledge` via filtered hybrid RRF), one
correctly-not-a-consumer (site search — Pagefind, a different architectural layer entirely, per
D33), one dormant future consumer if D33's deferred FastAPI hybrid search is ever built (same
table, no new index).

### O5 — Does this need its own embedding-cache table, or reuse D58's pattern?

D58 already proposed "a small `knowledge_embeddings` table (or reuse of D26's existing cache store
directly)" as the loader's cache-reuse bookkeeping, without fully committing to which. This
brainstorm's O1 schema **resolves that parenthetical**: `knowledge_embeddings` (as designed above) *is*
both the cache-reuse bookkeeping D58 needed *and* the live query index the three O4 consumers read
— they were never two separate concerns needing two separate tables. Reusing D26's `RunContext`
content-addressed cache directly (instead of a dedicated table) was D58's other option, but that
cache is keyed on full-input-replay (resolved-model-id + input + schema) and isn't queryable by
`ORDER BY embedding <=> ...` similarity search or filterable by `feature_id`/`status` — it's
correct as the *embedding-call* dedup layer (does calling the embedding API for this exact input
need to happen at all) but cannot serve as the *retrieval* index itself. **Recommendation: both,
each doing the job it's suited for** — `RunContext`'s cache dedupes the embedding API call itself
(preventing a duplicate charge if the same `rendered_text` is embedded twice for unrelated reasons);
`knowledge_embeddings` is the durable, queryable, pgvector-indexed table that stores the result and
serves every downstream reader. This is not new infrastructure beyond what D58 already proposed —
it's confirming the one table D58 left slightly open is this brainstorm's O1 schema, not a second
table.

## Recommendation

*Proposed* package:

1. **Schema (O1):** one table, `knowledge_embeddings`, `chunk_type IN ('fact', 'feature-description')`
   discriminator (not split tables), primary key `(embedding_model_id, chunk_type, subject_id)`,
   embedding column `vector(N)` at D22's chosen dimension, `rendered_text` (D47's precomputed
   claim/description string — the exact text embedded), plus D7's original filter metadata
   (`feature_id`, `language_id`, `status`) extended with `controversy_level` for D25-aware query
   filtering.
2. **Loader relationship (O2):** embeddings are computed once during the bundle-build pipeline
   (via `RunContext`, D26), shipped as a precomputed bundle column (D35), and copied into the
   shadow schema by D58's loader using the exact same cache-reuse-keyed, build-before-`COPY`,
   index-after-`COPY` mechanics D58 already specified for the rest of the bundle — no new loader
   code path, no on-demand/lazy embedding.
3. **Refresh cadence (O3):** no fixed calendar job. Primary mechanism is incremental, riding
   whatever cadence D35/D58 bundle builds already run at — unchanged `rendered_text` reuses its
   vector via cache-reuse keying, changed/new `rendered_text` re-embeds. The one explicit
   non-routine trigger is an embedding-model swap (D22's benchmark or a later re-benchmark), which
   mechanically forces a full re-embed for free because the cache-reuse key includes
   `embedding_model_id` — the same event topic 56/D59 already names as its own rare backstop-rescan
   trigger, so both consumers re-derive fresh state off one shared event.
4. **Shared consumers (O4):** the contradiction scan (topic 56) and `search_knowledge` (D8) both
   read this one table, differently (raw cosine top-k vs. filtered hybrid RRF with a
   publicly-safe-status filter). Site search stays Pagefind (D33) — a different architectural
   layer, not a consumer of this index at v0; D33's deferred public FastAPI hybrid search, if ever
   built, would become a third consumer of the same table rather than motivating a new index.
5. **Cache table question (O5):** resolved — `knowledge_embeddings` (this brainstorm's schema) *is* the
   table D58 left open as a parenthetical option, serving both the embedding-cache-reuse bookkeeping
   D58 needed and the live query index every downstream reader needs; `RunContext`'s existing cache
   stays the separate, complementary embedding-API-call dedup layer underneath it.

No new infrastructure category is added — this is a concrete schema and cadence filled in for a
table D7 already named, a model choice already deferred to D22, cache-reuse keying already decided
by D58, and consumer wiring already half-specified by D8/D56/D57. The project's "boring,
solo-maintainable technology" posture (CLAUDE.md) and D59's own "reuse, don't rebuild" precedent
both point the same direction the analysis above landed on anyway.

## Open questions for the developer

1. **`fact_embeddings` as the shared name for facts *and* feature/concept-description rows (O1)**
   — acceptable that the table's name (inherited from D58's own wording) undersells its scope once
   feature/concept-description rows are added via `chunk_type`, or would the developer prefer a
   rename (e.g. `knowledge_embeddings`) now, before any code references the D58 name, to avoid a
   legacy-name mismatch later?
2. **Feature/concept-description embedding source text (O1)** — D47 resolves what gets embedded
   for `chunk_type='fact'` rows (`rendered_text`) precisely; feature/concept rows have no equivalent
   ratified "canonical description field" decision yet. Is there already a specific YAML field
   (from brainstorm 09's schema) intended as that canonical description, or does this need a small
   follow-up decision before feature-description rows can actually be populated?
3. **Bundle-column vs. loader-side embedding computation (O2)** — confirm the recommendation that
   embedding vectors are computed once during the bundle-build pipeline and shipped as a precomputed
   `data-vN` bundle column (extending D35's manifest), rather than the Postgres loader calling the
   embedding API itself during load — does this match the developer's mental model of where D26's
   `RunContext` boundary should sit for this specific call type?
4. **`search_knowledge`'s publicly-safe-status filter (O4)** — what exact D25 status value(s) gate
   a fact into `search_knowledge`'s results (e.g. `verified` only, or a broader "not `challenged`/
   `superseded`" set)? This brainstorm assumes *some* filter exists (mirroring D8's "returns fact
   cards" framing and D35's non-suppression policy for controversial-but-verified facts) but doesn't
   pin the exact value set, since that's a D25 terminology question, not an embedding-index design
   question.
5. **Embedding dimension and HNSW vs. IVFFlat index choice (O1)** — left entirely to D22's benchmark
   output (dimension is model-dependent; index type is a scale/recall trade-off this brainstorm
   didn't evaluate, since real query volume doesn't exist yet) — confirm this stays fully deferred
   to D22 rather than wanting a starting default pinned down now.

## New brainstorm topics surfaced

- **Canonical feature/concept description field for embedding** — open question 2 above may resolve
  as a trivial pointer to an existing brainstorm-09 schema field, in which case no new brainstorm is
  needed; flagged here only in case it turns out to need a small schema decision of its own, in
  which case it's small enough to fold into whichever brainstorm next touches brainstorm 09's
  schema (matching how topics 41/43 already fold small schema additions into that same file) rather
  than deserving a dedicated session.
