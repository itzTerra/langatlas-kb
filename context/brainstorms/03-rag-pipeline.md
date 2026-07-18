# 03 — RAG Pipeline & Provider Connectivity

> Brainstorm output for Project Hermes. Source of truth: `context/input-brief.md`.
> Constraints held throughout: solo dev, PoC/MVP, no GPU, Claude Code Pro subscription,
> slow university-hosted model API, every fact must trace to a source.

## Problem framing

Hermes' "knowledge base for agents" is not a generic document pile — it is a **highly
structured, typed graph of small facts**: features, feature instances, syntax previews,
quality impacts, edges (requires/enables/conflicts/…), each with a citation. That shapes
everything:

1. **Retrieval is mostly lookup, not fuzzy discovery.** An agent arguing about "does
   Rust's ownership conflict with green threads?" needs *the* relevant nodes and edges,
   plus their source excerpts — not 5 vaguely similar paragraphs. Structured/metadata
   queries will answer a large share of questions; vectors fill the gap for concept-level
   phrasing ("non-blocking single-assignment variables" → dataflow concurrency).
2. **The corpus is small.** Even ambitiously: ~200 features × ~50 languages × a few facts
   each ≈ low tens of thousands of chunks. Every vector DB on earth handles this; "scale"
   is a non-criterion. Optimize for zero ops, easy re-index, and easy sync with the
   canonical fact files (see brainstorm 0x on fact storage / GitHub YAML).
3. **The same retrieval layer must serve four consumers:** (a) Claude Code via MCP,
   (b) developer-managed arguing agents (possibly on the slow university API or local
   CPU models), (c) other providers / local models, (d) the website (which needs
   *structured* browse + search far more than semantic search).
4. **Re-indexing must be cheap and boring**, because facts churn constantly while agents
   argue and humans challenge them. Whatever embedding strategy is chosen must make
   "wipe and rebuild the whole index" a one-command, minutes-not-hours, cents-not-dollars
   operation. That is the single most important embedding decision.

Key reframe worth stating explicitly: **for Hermes, RAG is the secondary index; the
structured store is primary.** The vector layer is a synonym/paraphrase bridge into a
graph, not the system of record.

## Options with trade-offs

### A. Vector store

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **sqlite-vec** | Single `.db` file next to the repo; zero daemon/ports/Docker; trivially versionable and rebuildable; SQLite already ideal for the structured fact tables + FTS5 gives BM25 for free in the *same* engine | Brute-force KNN (fine at this corpus size); young project; single-writer | **Strong fit for MVP** |
| **pgvector** | Boring, battle-tested; one DB for app + vectors + relational fact model; real concurrent writes; SQL joins between facts and embeddings; website likely needs Postgres anyway | Requires a running Postgres (Docker/managed) — small but nonzero ops for a solo dev; local dev slightly heavier | **Best fit once the website exists** |
| **LanceDB** | Embedded, no server; good Python/JS APIs; columnar, handles > RAM | Extra dependency solving a scale problem Hermes doesn't have; weaker relational side — facts would live elsewhere anyway | Skip |
| **Chroma** | Easy start, popular in tutorials | Client/server drift, migration churn history, another process to run; no relational home for the fact model | Skip |
| **Qdrant** | Excellent filtering, fast | A dedicated service (Docker container, config, backups) for tens of thousands of vectors — pure overhead here | Skip |

The honest comparison is only sqlite-vec vs pgvector, and it is really a question about
the *app database*, not the vector database: whichever DB holds the structured facts
should also hold the vectors, so metadata filters and joins are native. Recent
independent write-ups reach the same conclusion for small local-first projects
([pgvector vs sqlite-vec](https://llbbl.blog/2026/04/26/pgvector-vs-sqlitevec-you-probably.html),
[Firecrawl vector DB guide](https://www.firecrawl.dev/blog/best-vector-databases),
[Encore comparison](https://encore.dev/articles/best-vector-databases)).

Mitigation for the "which one" anxiety: hide the store behind a ~5-function retrieval
interface (`search_semantic`, `search_keyword`, `get_fact`, `get_neighbors`,
`list_by_filter`). Migrating sqlite-vec → pgvector later is then a day of work, and the
embeddings themselves are portable (they're just float arrays keyed by fact ID).

### B. Embeddings without a GPU

| Option | Cost | Re-index story | Notes |
|---|---|---|---|
| **Local CPU: sentence-transformers small models** (`all-MiniLM-L6-v2` 384d, `bge-small-en-v1.5`, or `snowflake-arctic-embed-s`) | $0 | Full re-index of ~30k short chunks: minutes on a laptop CPU (these models run ~100–500 chunks/s on CPU, faster via ONNX/int8 through `fastembed` or `onnxruntime`) | Fully offline, deterministic, no key management; quality is genuinely sufficient for short technical chunks |
| **API embeddings** (OpenAI `text-embedding-3-small` ~$0.02/1M tok; Voyage/Cohere similar) | Cents per full re-index at this corpus size | Fast but network-bound; needs a paid key (Claude Code Pro does **not** include an embeddings API; Anthropic has no embeddings endpoint — they point to partners) | Slightly better quality; adds a billing account + online dependency for something the CPU can do |
| **University API** | "Free" | Unknown whether it exposes embeddings at all; stated to be slow — a re-index that takes hours will rot | Use only as a fallback experiment |
| **Hybrid: local for bulk, API for queries** | — | — | Invalid: query and document embeddings must come from the same model. Don't mix. |

Critical properties regardless of choice:
- Store `embedding_model` + `content_hash` per row; re-embed only changed rows
  incrementally, with full rebuild as the recovery path.
- Chunks here are *short* (a fact + its context ≈ 50–200 tokens), which is exactly where
  small models are least disadvantaged versus large ones.
- No GPU + tiny corpus + frequent churn ⇒ local CPU embeddings dominate: free re-index
  removes all hesitation about restructuring the corpus, which the argue-loop will do a lot.

### C. What to embed (given highly structured knowledge)

Candidate chunk types — these are not exclusive; embed several types into one index with
a `chunk_type` metadata field:

1. **Fact cards (primary).** One chunk per fact/claim, rendered from the structured
   record into a template: *"Feature: pattern matching. Language: Haskell. Claim: …
   Qualities affected: …"*. Self-contained, one citation each, maps 1:1 to the
   challengeable unit. This is what agents should retrieve to *cite*.
2. **Feature/concept descriptions.** One chunk per feature node (definition, aliases,
   related concepts). This is the synonym bridge: user/agent phrasing → canonical node ID.
   Arguably the highest-value embedding target, because after resolving to a node,
   graph/metadata traversal answers the rest better than similarity can.
3. **Source excerpts.** The quoted passage backing a fact (e.g., Van Roy & Haridi
   paragraphs). Lets agents verify claims against the actual text and lets retrieval
   surface support that the fact-card summary lost. Embed per-quote, not per-PDF-page.
4. **Edge sentences.** Render each graph edge as a sentence ("Ownership *requires* move
   semantics because …"). Cheap, and makes relationship questions retrievable
   semantically. Optional for MVP — `get_neighbors` on the graph covers most of it.
5. **Syntax snippets.** Probably *not* worth embedding with a text model (code + prose
   mismatch); retrieve them via metadata (feature ID + language ID) after resolving the
   node. Keep them out of the vector index at first.

**Metadata filtering is the co-star, not a nicety.** Every chunk carries
`{chunk_type, feature_id, language_id?, quality?, source_id, status(proposed/accepted/challenged)}`.
Typical agent query = filter (`language=rust`, `chunk_type=fact`) + semantic ranking
inside the filtered set. At this corpus size, filter-then-brute-force-scan is fast and
exact — a real advantage of keeping vectors in SQL.

### D. Hybrid search (BM25 + vector)

Yes — and in this domain it is close to mandatory rather than "smarter default":
- PL terminology is exact-match heavy: `call-by-need`, `HKT`, `GADT`, `ARC`, `functor`,
  language names, operator syntax. Dense models mangle rare acronyms and code tokens;
  BM25 nails them. Conversely BM25 misses paraphrase ("automatic memory reclamation" →
  GC); vectors fix that. Classic complementary failure modes.
- Cost is near zero in the recommended stack: SQLite **FTS5** (or Postgres `tsvector`)
  over the same chunk table, then **Reciprocal Rank Fusion** (RRF, ~15 lines of code) to
  merge the two ranked lists. No extra service (no Elasticsearch, no Tantivy needed).
- A cross-encoder reranker (e.g. `bge-reranker-base` on CPU) is a possible later add for
  top-20 → top-5, but with short chunks and RRF it is likely unnecessary for MVP; note it
  as an eval-driven upgrade, not a default.

### E. Provider connectivity

**MCP server as the front door** (stdio for local Claude Code; Streamable HTTP if it ever
needs to be remote — HTTP is current best practice for remote servers, stdio remains the
simplest for a local single-user tool; see [Claude Code MCP docs](https://code.claude.com/docs/en/mcp)).
Design principles that current practice converged on:

- **Few, high-level tools with tight token budgets.** Every tool + its description eats
  the agent's context; a small curated set beats mirroring the whole API
  ([2026 MCP guide](https://generect.com/blog/claude-mcp/),
  [private KB via MCP write-up](https://pub.towardsai.net/building-a-private-knowledge-base-with-mcp-how-i-made-claude-search-my-own-articles-06c591bb300a)).
  Proposed tool surface (~6 tools):
  - `search_knowledge(query, filters?, top_k?)` — hybrid search, returns fact cards
    *with inline citation keys*
  - `get_fact(fact_id)` / `get_feature(feature_id)` — full record + sources + edges
  - `get_neighbors(node_id, edge_type?)` — graph traversal
  - `get_source(source_id)` — full bibliographic record + excerpt
  - `propose_fact(payload)` — the write path for the arguing agents (gated by
    `status=proposed`; humans/GitHub review promotes to `accepted`)
- **Relevance floor + sensible k.** Empirically a similarity threshold and k≈5 (not 3)
  noticeably improve answer quality for KB-style MCP tools (same write-up above).
- **Citations in-band.** Every returned chunk ends with `[src:jordan2015]`-style keys so
  agent output stays traceable without a second lookup.

**Architecture: thin MCP over a shared core.** Implement retrieval once as a plain
Python library + tiny FastAPI (or equivalent) service; then:
- **Claude Code** → MCP server (stdio) that imports the library directly. Registered in
  `.mcp.json` at the repo root so it's a project-scoped server.
- **Other/local providers** (OpenAI-compatible clients, university API, llama.cpp/Ollama
  CPU models): most now also speak MCP; for any that don't, the same FastAPI endpoints
  serve as classic function-calling tools. One core, two thin adapters — never two
  retrieval implementations.
- **Website**: does *not* go through MCP. It queries the structured store directly
  (browse by language/feature, show sources) and can reuse the hybrid-search endpoint for
  its search box. SEO pages are rendered from the canonical fact tables, not from RAG.

### F. Retrieval evaluation at small scale

Skip RAGAS/LLM-judge frameworks for MVP; they're heavyweight and the slow university API
makes judge-loops painful. Instead:

1. **Golden-set retrieval eval (the workhorse).** Hand-write 30–60 queries with expected
   fact/feature IDs (10 min of work per batch, grown over time — add a query every time
   retrieval disappoints). Metrics: Recall@5, MRR. A pytest file + a small script;
   runs in seconds because everything is local. Run it in CI and on every change to
   chunking, embedding model, or fusion weights.
2. **A/B by config, not by vibes.** Because re-embedding is free (local CPU), comparing
   MiniLM vs bge-small vs vector-only vs hybrid is just re-running the eval script.
3. **Faithfulness spot-checks.** Occasionally have Claude Code (already paid for via Pro)
   grade 10 sampled answer+citation pairs: "is the claim supported by the cited
   excerpt?" — manual-ish, cheap, catches citation drift.
4. **Log real agent queries.** The arguing agents generate a natural query distribution;
   harvest failed/empty retrievals into the golden set weekly.

## Recommendation (concrete stack)

**MVP (start here):**
- **Store:** SQLite — one file, three roles: structured fact/graph tables, **FTS5** for
  BM25, **sqlite-vec** for vectors. Zero services. The DB is a build artifact,
  regenerable from the canonical fact files (GitHub YAML) by an `index.py` script.
- **Embeddings:** local CPU via `fastembed`/ONNX, model **`bge-small-en-v1.5`** (384d)
  — fallback `all-MiniLM-L6-v2` if speed matters more. Incremental re-embed keyed on
  `content_hash`; full rebuild is minutes and $0.
- **Chunks:** fact cards + feature descriptions + source excerpts, each with
  `{chunk_type, feature_id, language_id, source_id, status}` metadata. Syntax snippets
  retrieved structurally, not vectorially.
- **Search:** filter-first, then hybrid **BM25 + vector fused with RRF**, k=5, with a
  relevance floor. No reranker until the eval says otherwise.
- **Connectivity:** one Python retrieval library; **MCP server (stdio, ~6 tools)** in
  `.mcp.json` for Claude Code and MCP-speaking local models; thin FastAPI wrapper for
  non-MCP providers and the website's search box; website otherwise reads the structured
  tables directly.
- **Eval:** committed golden-set (queries → expected IDs), Recall@5 + MRR in pytest;
  grow it from logged agent misses.

**Graduation path (only when the multi-user website ships):** move the same schema to
**Postgres + pgvector** (vectors and FTS both port cleanly); the retrieval-library
interface makes this a contained migration. Nothing else changes — same embeddings, same
MCP tools, same eval set.

## Open questions for the owner

1. Does the university API expose an *embeddings* endpoint at all, and is offline/CPU
   embedding acceptable as the default? (Recommendation assumes yes to the latter.)
2. Should the arguing agents be allowed to **write** through MCP (`propose_fact`), or is
   the write path exclusively via PRs to the canonical YAML files on GitHub? This
   decides whether the MCP server is read-only (simpler, safer for MVP).
3. Is English-only retrieval acceptable for MVP? (Small English models chosen; a
   multilingual requirement changes the embedding pick to `bge-m3`-class models.)
4. What is the canonical ID scheme for features/languages/sources? Stable slugs
   (`feature:pattern-matching`, `lang:haskell`, `src:jordan2015`) must be fixed before
   indexing, since every chunk, edge, and citation hangs off them (ties into the .bib
   format decision from constraint #1).
5. How much of the source PDFs may be stored/quoted? Embedding excerpts of copyrighted
   books (Van Roy & Haridi) is fine privately; the *website* showing long excerpts may
   not be. Affects what goes into the `source_excerpt` chunks.
6. Do the arguing agents need retrieval over *each other's arguments* (debate history as
   a searchable corpus), or only over accepted facts? That's a second index/status filter
   worth deciding early.

## New brainstorm topics surfaced

- **Fact schema & ID design**: the exact YAML/record schema for facts, edges, sources
  (.bib mapping — CSL-JSON vs BibLaTeX), and stable slug/ID policy. Everything in this
  doc depends on it.
- **YAML↔DB build pipeline**: the `index.py` compile step (validate → build SQLite →
  embed changed rows), CI integration, and how challenged/edited facts round-trip from
  GitHub back into the index.
- **Agent debate orchestration**: how per-language expert agents consume the k=5 results,
  budget tokens on the slow university API, and how `propose_fact` outputs are queued for
  review — including guardrails against agents citing each other circularly.
- **Website search UX**: how far the site's search should lean on the hybrid endpoint vs
  pure structured facets; SEO implications of rendering fact cards as pages.
- **Knowledge graph queries beyond RAG**: whether emergent-interaction validation
  (requires/conflicts propagation in the builder) needs a real constraint solver or
  graph library rather than retrieval at all.
