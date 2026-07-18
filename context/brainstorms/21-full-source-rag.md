# 21 — Full-Source RAG (round 2)

> Round-2 brainstorm for Project Hermes. Owner prompt: "my main RAG motivation was to have all
> of the full sources RAGed so that agents creating the facts don't have to load 10 books in
> their context. Brainstorm why that wasn't included in the proposed RAG in the first place and
> if it would be beneficial." Binding context: `context/decisions.md` (esp. D4, D6, D7, D11).
> Builds on brainstorms 03 (RAG pipeline) and 04 (multi-agent workflow).

## 1. Problem framing

### 1.1 Two different RAGs were being talked about

Round-1 brainstorm 03 designed retrieval for the **consumption side** of the knowledge base:
agents and the website looking up *already-minted* facts, features, and edges. Its chunk types
(fact cards, feature descriptions, short source excerpts) all presuppose that the knowledge
exists and just needs to be found again. The owner's original motivation was the
**production side**: agents doing research across large source texts — Van Roy & Haridi
(~900 pp, ~450k tokens), Jordan et al., language specifications, official docs sites — in
order to *create* facts without stuffing whole books into context. These are different corpora,
different query patterns, and different consumers, and round 1 only built the first one.

### 1.2 Why it was missed — the honest account

1. **Framing lock-in.** Brainstorm 03 opened with the reframe "Hermes' knowledge base is not a
   generic document pile — it is a highly structured, typed graph of small facts," and then
   optimized everything for that. The reframe was correct *for the fact index* but it silently
   scoped "RAG" to mean "retrieval over Hermes' own records," excluding the document pile that
   the facts are made *from*. The brief's constraint #1 ("knowledge base for agents = vector
   database for RAG") was read as "index the facts for agents" when the owner meant, at least
   equally, "index the sources for the agents that make facts."
2. **The corpus-size argument backfired.** 03's "the corpus is small (~tens of thousands of
   chunks)" observation was about fact cards. Full sources are 10–50× that, and having framed
   smallness as a design pillar, the larger corpus fell outside the mental model.
3. **Round-1 embedding assumptions.** Round 1 assumed no usable embeddings endpoint on the
   university API (now void per D6) and picked tiny local CPU models with 512-token windows.
   Under that assumption, embedding dozens of full books looked like the expensive, awkward
   case, so the design gravitated to short curated excerpts.
4. **The rejected 3×5 MVP slice.** Under the round-1 proof-slice scoping, the source-reading
   burden per sweep was small enough that "agent opens the snapshot and greps/reads" seemed
   adequate. D11's frontloaded research phase — agents designing the whole feature landscape
   from broad literature — changes the workload from "look up one cell" to "survey ten books,"
   which is exactly the workload full-source RAG exists for.
5. **Source excerpts were designed backwards.** 03's chunk type 3 embeds the quote *backing an
   existing fact* — a post-hoc artifact. That covers re-finding evidence, not *discovering*
   evidence in text nobody has quoted yet. The discovery direction was the owner's actual use
   case.

None of these were wrong analyses of the fact index; they were a scope error about what "the
RAG" was for. D7 already flags the gap ("Whether full source texts also get an index:
brainstorm 21") and D11 already anticipates the answer ("Full-source RAG is likely its
foundation").

### 1.3 Who consumes a source-corpus index

- **Research-phase agents (D11)** — concept-level queries across many books at once ("which
  sources discuss single-assignment dataflow variables?") while designing the ontology.
- **Per-language sweep agents (D5)** — evidence retrieval before drafting claims, source-first
  per D4.
- **The verification gate (D4)** — the context-blind verifier needs the source text at a
  locator to run entailment. A source-corpus index with locator-carrying chunks serves this
  directly: verification becomes "fetch chunk(s) at/near the claimed locator, check support."
  One index, both halves of the claim lifecycle. This dual use is the strongest single argument
  for building it.
- **Not the website.** Site search stays on structured facts (D8/D10); the source corpus is a
  private working asset.

## 2. Options with trade-offs

### 2.1 How agents access large sources (the real comparison)

| Option | How it works | Pros | Cons | Verdict |
|---|---|---|---|---|
| **Long-context stuffing** | Load book(s) into the chat model's window | Zero infrastructure; model sees full continuity | A single VR&H is ~450k tokens; ten books ≈ 3–5M tokens — no available window holds that. Even one book saturates most windows, costs the whole budget per question, and suffers lost-in-the-middle degradation. University chat models' windows are unspecified but certainly not multi-million | Rejected as the general mechanism; fine for *one short spec section* once located |
| **Agentic grep/read over snapshots** | Agent runs text search over extracted source files, opens matching regions | No new services; exact-term queries (`call-by-need`, `GADT`) work great; agent controls depth | Fails on paraphrase (the book says "single-assignment store," the agent searches "dataflow variables"); many tool round-trips burn context and Pro budget; no ranking across dozens of sources; agent must know *which* file to search | Keep as a **complement** (exact-match tool over the same extracted text), not the primary path |
| **Full-source RAG (second index)** | Chunk + embed all extracted sources; hybrid search + rerank; chunks carry locators | Concept-level recall across the whole corpus in one call; returns citation-ready locators; also powers the D4 verifier; embedding is effectively free on the university API (D6) | Ingestion pipeline to build and QA (PDF extraction, anchoring); index freshness when sources are added; retrieval can return misleadingly decontextualized chunks | **Adopt** |

These aren't exclusive: the recommended shape is retrieval to *locate*, then agentic reading of
the located neighborhood to *understand*, then long-context only for the final passage in the
drafting prompt. That is also exactly the source-first workflow D4 mandates.

### 2.2 One index or two?

| Option | Pros | Cons |
|---|---|---|
| **Single index, `chunk_type=source_text` rows added** | One search path | Different lifecycles (fact index churns constantly and is wipe-rebuildable in minutes; source corpus is append-mostly and expensive to rebuild), different metadata shapes, different embedding-model trade-offs, and fact-search results would need constant filtering to exclude raw text |
| **Second index (separate `source_chunks` table), same Postgres+pgvector** | Independent lifecycle and re-embed cadence; separate tool surface (`search_sources` vs `search_knowledge`); can use a different embedding model/dimension per table; keeps D7's fact-index design untouched | Two ingest paths to maintain (they share the embedding client and DB anyway) |

**Second table in the same database** wins clearly. No new service (D7, D12 absent-on-purpose
list intact).

### 2.3 Ingestion & extraction

- **PDFs (books, papers):** extract to structured Markdown with per-page anchoring. Modern
  extractors (Docling, marker, PyMuPDF4LLM) preserve headings and page numbers; VR&H is a
  digital-native PDF (good text layer). Math-heavy pages will be imperfect — acceptable, since
  claims about PL features live in prose. Keep `{page_start, page_end}` per chunk so every
  retrieved chunk yields a page-level locator automatically.
- **HTML (specs, docs sites):** fetch → readability/trafilatura extraction → per-heading
  sections; locator = the page URL + heading anchor (specs like ECMA-262 or the Python
  reference have numbered sections — ideal locators for free).
- **Extracted text lives outside git.** D1 forbids committing page snapshots; extracted text +
  content hashes live on disk (the existing D4 snapshot store), the DB stays a derived
  artifact rebuilt from those snapshots. The source *registry* (CSL-YAML) stays canonical in
  git; the texts do not.
- **Per-source QA pass:** a one-time skim per ingested source (spot-check N random chunks
  against the original) — extraction garbage in the index silently poisons both research and
  verification.

### 2.4 Chunking strategy

Different source shapes want different splits, all structure-aware (never fixed-size sliding
windows over headings):

- **Books:** split on the section hierarchy, target ~400–800 tokens per chunk, ~15% overlap,
  each chunk prefixed with its breadcrumb ("Van Roy & Haridi 2003 › Ch. 7 Object-Oriented
  Programming › 7.3 Classes as complete data abstractions") — the breadcrumb both aids
  embedding and *is* the human-readable locator.
- **Specs:** one chunk per numbered clause (splitting oversized clauses); the clause number is
  the locator.
- **Docs pages:** one chunk per page section under an `h2`/`h3`; URL+anchor is the locator.

**On long-context embedding:** `qwen3-embedding-4b`'s 40,960-token window technically permits
whole-chapter chunks. Resist it. Huge chunks average many topics into one vector (poor
precision), return walls of text that defeat the purpose of saving agent context, and blur
locators to "somewhere in chapter 7." The long context's real value is different: (a) no
truncation anxiety for occasional oversized clauses, (b) breadcrumb + context prefixes cost
nothing, (c) it enables a **small-to-big pattern** — embed modest chunks, but store
`parent_section_id` so an agent can pull the surrounding section on demand after retrieval
ranks the small chunk. That gets big-context reading *after* precise ranking, which is the
right order.

### 2.5 Embedding model choice

| Candidate | For | Against |
|---|---|---|
| **qwen3-embedding-4b** (univ. API; 40,960 ctx, 2560-dim) | Best quality on offer; long context removes truncation edge cases; instruction-aware; pairs with `qwen3-reranker-4b`; supports MRL-style dimension truncation if 2560-dim storage ever matters | API-bound (re-index depends on university availability); 2560-dim = ~10 KB/vector float32 |
| **nomic / mxbai / e5 small models** (512 ctx) | Cheap, local-capable | 512-token window forces smaller chunks or truncation; English-only fine (D7) but quality lower on technical prose |
| Local CPU fastembed (round-1 pick) | $0, offline | Same 512-token ceiling; quality gap on book-length technical text |

**Recommendation: `qwen3-embedding-4b` for the source corpus**, validated by extending the D7
golden-set eval with source-retrieval queries. The source corpus is append-mostly, so the
round-1 "re-index must be minutes and free" pillar doesn't bind here — a slow overnight batch
embed per newly ingested book is fine (D6: latency-blind batch work belongs on the university
API). The *fact* index can keep whatever model the eval picks independently — the two-table
design allows differing models. Add **`qwen3-reranker-4b` as a default-on stage for source
search** (top-50 candidates → top-5..8): unlike the fact index's short uniform cards, book
chunks are heterogeneous, and reranking is where a 40k-context reranker earns its keep.

### 2.6 Schema sketch

```
source_chunks(
  chunk_id            text pk,      -- content-keyed, deterministic (D11 hygiene)
  source_id           text fk,      -- registry slug, e.g. vanroy-haridi-2003
  section_path        text,         -- "7 › 7.3 Classes as complete data abstractions"
  locator             text,         -- normalized: "pp. 492–495" | "§13.2.1" | url#anchor
  page_start/page_end int null,
  parent_section_id   text null,    -- small-to-big expansion
  content             text,         -- with breadcrumb prefix
  content_hash        text,
  tier                char,         -- inherited from source registry (A–D)
  embedding_model     text,
  embedding           vector(2560),
  tsv                 tsvector      -- hybrid search per D7
)
```

Search = filter-first (`source_id`, `tier`) → hybrid FTS+vector RRF → rerank → return chunks
with `{source_id, locator, section_path, text}`.

### 2.7 Flow into the source-first claim workflow (D4)

1. Agent calls `search_sources(query, filters?)` → k reranked chunks, each already carrying
   `source_id + locator`.
2. Agent optionally expands to the parent section (`get_source_section`) to read in context.
3. Agent drafts the claim with `source_id`, `locator` (copied from the chunk — no manual
   locator invention), and an optional verbatim quote (D3: quotes optional).
4. The verifier — context-blind — retrieves the chunk(s) at that locator from the *same* table
   (plus semantic neighbors when no quote is given) and runs entailment. Quote present →
   string-check fast path against `content`; quote absent → LLM entailment over the located
   chunk, per D3/D4.

The index thus mechanically closes the loop the decisions already require: locators are
machine-produced at retrieval time, so "cite a locator that exists and says what you claim"
stops depending on agent diligence. This directly attacks risk K1 (citation laundering).

New read-only tools (D8 surface grows by two): `search_sources(query, filters?, top_k?)` and
`get_source_section(source_id, section|locator)`. Both agent-facing only; never the website.

### 2.8 Copyright

A **private, never-published, never-committed** full-text index of purchased/freely-distributed
sources is ordinary research infrastructure — functionally identical to keeping the PDFs on
disk plus an index, and squarely the private text/data-mining use that even conservative
readings tolerate. The constraints that matter (all already decided): extracted text and
embeddings never enter the public repos (D1), the site shows only short attributed quotes
(D3/D10), and the corpus artifact is never distributed. The corpus-licensing brainstorm (15)
governs what Hermes *publishes*; it does not constrain this internal index. Note VR&H 2003 is
publicly distributed by the author; language specs are openly published; the main care point is
any paywalled papers — index them privately like everything else, quote them briefly.

## 3. Recommendation

Build the source-corpus index as a **second table in the existing Postgres+pgvector**, before
the D11 research phase starts (it is that phase's foundation):

1. **Ingestion CLI**: registry entry → fetch/copy → extract (Docling-class for PDF,
   trafilatura for HTML) → structure-aware chunks (400–800 tokens, breadcrumb prefix,
   page/section locators, `parent_section_id`) → overnight batch embed on
   `qwen3-embedding-4b` → upsert. Content-keyed chunk IDs; incremental by `content_hash`.
2. **Retrieval**: filter-first hybrid FTS+vector with RRF, then `qwen3-reranker-4b`
   default-on, k≈5–8; small-to-big expansion tool.
3. **Tool surface**: add `search_sources` + `get_source_section` to the MCP server (read-only,
   D8); keep a plain exact-match grep tool over the extracted snapshots as the cheap
   complement.
4. **Verifier integration**: the D4 gate reads from this table (locator fetch + neighbor
   retrieval), removing its ad-hoc source-fetching path.
5. **Eval**: extend the golden set with 20–30 source-retrieval queries ("find where VR&H
   defines active objects" → expected chunk/section IDs) before trusting the research phase
   to it.

**Cost/effort at realistic size.** ~30 sources (a dozen books at ~200–450k tokens, a dozen
specs, assorted docs) ≈ 6–10M tokens ≈ 12–20k chunks at ~600 tokens — comparable to the fact
index, trivially within pgvector's comfort zone. Storage: ~20k × 10 KB ≈ 200 MB of vectors +
text — nothing. Embedding: free on the university API, run as overnight batches (hours, not
a problem — append-mostly corpus). The real cost is **ingestion engineering and QA**: the
pipeline itself (~1–2 focused weeks) plus ~0.5–2 h of extraction QA per book-class source.
That effort is a precondition of D11 either way — without this index, the research phase pays
it repeatedly in agent context instead of once in tooling.

## 4. Open questions for the owner

1. **Initial corpus list**: which sources get ingested first? Proposal: VR&H 2003, Jordan
   et al. 2015, the official specs/references for the initially interesting languages, plus
   2–3 general PL-design texts (candidates to be proposed during the research-phase design,
   brainstorm 25).
2. **Paywalled academic papers**: is the owner able/willing to obtain PDFs via university
   access for private indexing, and should tier-A paper acquisition be part of the research
   phase's source-minting flow?
3. **Reranker default-on** adds one university-API call per source query — acceptable latency
   for research sessions? (Recommendation assumes yes; it is skippable via a flag.)
4. **Docs-site crawl depth**: whole reference manuals (hundreds of pages per language) or only
   spec/reference chapters? Affects corpus size ~5× and ingestion QA effort.
5. **Snapshot storage location**: extracted text on plain disk under the existing D4 snapshot
   dir, or in a private object store / separate private git repo for machine portability?

## 5. New brainstorm topics surfaced

- **Ingestion QA harness** — automated extraction-quality checks (chunk-length distributions,
  garbled-text detectors, heading-coverage diffs against the PDF outline) so a bad extractor
  run can't silently poison research and verification.
- **Locator normalization scheme** — one canonical locator grammar (`pp. N–M` | `§x.y.z` |
  `url#anchor`) shared by chunks, facts, and the verifier; needed before mass fact minting
  (feeds brainstorms 11/12).
- **Research-phase tool loadout (extends 25)** — the exact tool surface and prompt patterns
  research agents get (`search_sources`, grep, section expansion, source minting), and budget
  discipline per D6.
- **Corpus freshness policy** — when a spec version updates: re-ingest as a new source version
  vs in-place update, and what that does to existing locators and verified facts (ties to the
  `since` back-dating pipeline, D2).
