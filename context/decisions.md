# Decisions

Consolidated from the round-1 brainstorms (`context/brainstorms/01`–`08`), then **ratified and
amended by the developer on 2026-07-18** (answers given in conversation; amendments marked
*[developer 2026-07-18]*). Ratified decisions are binding for implementation; edit in place with a
dated note if they change. Read the named brainstorms for the full trade-off analyses.

## D1. Git is the database (01, 05, 07, 08 — ratified with amendments)

The canonical store for all curated knowledge (features, feature instances, edges, rules, facts,
sources) is a **repo of human-readable YAML files**. Everything downstream — Postgres, vector
index, static site — is a **one-way derived build artifact** compiled by CI. There is no
sync-back problem because nothing downstream is ever authoritative.

- *[developer 2026-07-18]* **No PR gate for agent-produced facts.** Agents commit directly; a fact is
  admissible because it is backed by a verified source, not because a human reviewed it. The
  automated verification gate (D4) + CI checks are the only gates. **Controversial/conflicting
  facts are auto-flagged** (surfaced on the site and in a work queue), never routed to developer
  review — the developer is not an expert in every language and the pipeline must not depend on
  their review bandwidth. Human expert challenges (D9) remain the correction mechanism.
- *[developer 2026-07-18]* **Every agent chat is logged**, and a fact should carry an optional link
  to the chat that produced it (storage/rendering design: brainstorm 24).
- *[developer 2026-07-18]* **Public repo(s) from day one**, and **split repos**: knowledge-base
  management and the website live in separate repositories so their issue trackers stay
  separate. (CI implications: brainstorm 10.)
- Never commit embeddings, page snapshots, or binaries — build outputs only (05, 08).
- Community/runtime data (votes, usage stats, submissions) is future DB-only state, never
  round-tripped (01).

## D2. Knowledge model (01 — ratified with amendments)

Entities: **Concept** (thin, pedagogical), **Feature** (primary node; `layer` 1 syntax /
2 semantic / 3 design-choice; layer-3 features carry a `dimension`), **FeatureInstance**
(feature × language — the reified `implemented-by` edge), **SyntaxExample** (reified
`expressed-as`; functionality stays separate from syntax), **Quality** (small controlled
vocabulary), **Characteristic**, **Edge** (5 feature↔feature types: requires, enables,
influences ±, conflicts-with, alternative-to; 2 feature→quality types), **Rule** (multi-feature
emergent interactions), **Fact**, **Source**.

- *[developer 2026-07-18]* **Characteristic = a fact listed under a language feature** (an observable
  property), which **can serve as evidence feeding a quality edge**. It is not a separate
  user-facing page type — it renders as sourced facts under the feature/instance it describes.
- *[developer 2026-07-18]* **`influences` is polarity-only** (no magnitude).
- *[developer 2026-07-18]* **Nothing is developer-curated / closed.** The layer-3 dimension list, the
  feature set — everything is subject to change through the normal evidence + challenge
  process. The project actively invites collaboration between programmers.
- *[developer 2026-07-18]* **Versioning: a `since` field** on feature instances is sufficient — but
  the verification pipeline must check that the cited source actually supports the `since`
  value, and a later dedicated pipeline back-dates `since` to the earliest supportable value
  (feeds brainstorms 11 and 12).
- *[developer 2026-07-18]* Quality-impact judgments are **attributed assessments with recorded
  spread** (no forced consensus), as long as the representation is structured and presentable
  on the site.

A **fact** is one human-readable sourced sentence bound to exactly one machine-readable claim
(edge, instance/attribute assertion, or rule); two independently challengeable claims = two
facts. Facts are the embedding unit for fact-RAG, so retrieval always returns provenance.
(Exact file granularity is still open — open question C13.)

Combination validation in four levels: dimension exclusivity, hard pairwise requires/conflicts
(package-manager-style propagation), soft influences warnings, Rule entities for multi-feature
interactions. **No graph database** — plain tables / in-memory graph at build time (01, 08).

## D3. Sources & citations (02 — ratified with amendments)

- Canonical bibliographic format: **CSL-JSON field vocabulary, authored as YAML** in `sources/`;
  LangAtlas extras (tier, archive URL, accessed date, minting provenance) under the `custom` key;
  generated `.bib` export for academics. Human-readable slug IDs (`vanroy-haridi-2003`).
- Source quality tiers: **A** peer-reviewed/spec, **B** official docs/textbook, **C** talks/known
  community references, **D** blogs/popularity indexes.
- *[developer 2026-07-18]* **Verbatim quotes are optional, not mandatory.** Sources are evaluated by
  their strength; agents weigh citation credibility accordingly. When a quote is present it
  strengthens verification; when absent, verification works from locator + retrieved source
  text (gate design: brainstorm 11).
- *[developer 2026-07-18]* **Community sources (PLDB, hyperpolyglot, wikis) are corroboration only**
  — never the sole backing for a fact.
- *[developer 2026-07-18]* **Site citation style: numeric `[1]`** superscripts with popovers.
- Web sources archived via Wayback SavePageNow on mint; version-pinned permalinks preferred;
  CI link checker. Dedup on mint by DOI/ISBN/normalized URL, then fuzzy title match.

## D4. Grounding & verification (04, 08 — ratified with amendments)

- **Source-first workflow**: an agent may not assert a fact without `source_id` + `locator`;
  priors guide search but only sources make facts (`claim_origin: prior | source-derived`).
- **Independent verifier**: a context-blind checker (code paths where mechanical; academic-API
  LLM for entailment) validates that the located source text supports the claim — including
  its `since` value (developer C10). Unverified claims cannot enter the canonical store; since
  there is no human merge gate (D1), this gate is load-bearing.
- **Source registry with snapshots** (hash + retrieval date). New sources are minted by agents
  with automated dedup + tier assignment; registry changes are logged, not human-gated
  *[developer 2026-07-18: pipeline must not depend on developer review]*.
- **Agent-generated text is never itself citable** — prevents the self-backing net from becoming
  self-referencing (risk K1).

## D5. Multi-agent workflow (04 — ratified with amendments; scoping superseded by D11)

- **No free-chat debates.** Independent per-language questionnaire sweeps, source-first; a
  reconciler diffs answers; only conflicted cells trigger structured debates (proposer + 2
  challengers + fresh-context moderator, ≤6 messages, typed challenges), resolutions recorded
  as structured blocks.
- *[developer 2026-07-18]* The per-language sweep pipeline is the mechanism for **adding new
  languages later**; the initial feature landscape comes from the frontloaded research phase
  (D11).
- Contradictions are first-class records; many dissolve via `since`/version qualification.
- *[developer 2026-07-18]* **Personas: real but mild** — "the Rust expert," without strong
  engineered biases.
- Full provenance on every fact: proposer agent + model + prompt version, debate id, verifier
  result, timestamps, and *[developer 2026-07-18]* an optional link to the logged chat (D1).

## D6. Model tiering & budget (04, 07, 08 — ratified with amendments)

**Claude never does volume; the academic API never has the last word.** Claude (Pro) handles
schema design, high-judgment drafting, debates, reconciliation, moderation; the university API +
plain code handle bulk drafting, verification/entailment, and embeddings. A shared API wrapper
does throttling, backoff, (model, prompt-hash) caching, per-run cost caps, and a cost log; track
cost-per-accepted-fact.

- *[developer 2026-07-18]* **Budget = full Claude Pro limits + reasonable academic LLM API use; no
  additional cash budget.** No deadline pressure — do not take shortcuts that damage the
  long-term product.

### Environment: university API (developer-provided, 2026-07-18)

Chat model aliases:

| Alias | Resolves to | Notes |
|---|---|---|
| `glm` | glm-5.2 | latest GLM |
| `kimi` | kimi-k2.7 | latest Kimi |
| `deepseek` | deepseek-v4-pro | reasoning off by default (can be enabled) |
| `deepseek-thinking` | deepseek-v4-pro-thinking | reasoning on |
| `mini` | gpt-oss-120b | |
| `coder`, `agentic` | qwen3.5-122b | |
| `thinker` | deepseek-v4-pro-thinking | |

Embedding/reranking models:

| Model | Notes |
|---|---|
| `qwen3-embedding-4b` | 40,960-token context, 2560-dim, 100+ languages |
| `qwen3-reranker-4b` | reranker, 40,960-token context |
| `nomic-embed-text-v1.5` / `v2-moe` | 512-token context, 768-dim, English-only |
| `mxbai-embed-large` | 512-token context, 1024-dim, English-only |
| `multilingual-e5-large-instruct` | 514-token context, 1024-dim, multilingual |

So the university API **does** expose embeddings and a reranker — the "no embeddings available"
assumption from round 1 is void. Concrete embedding-model choice: decide by eval (golden set)
between university-hosted models and local CPU fastembed; English-only models are eligible
(D8: English-only ratified). The long-context `qwen3-embedding-4b` + reranker matter for
full-source RAG (brainstorm 21).

## D7. Data & retrieval stack (03 — amended: Postgres from the start)

- *[developer 2026-07-18]* **Postgres (+ pgvector + tsvector FTS) from day one — no SQLite phase.**
  The project runs under **docker compose** anyway, for contributor friendliness. The database
  remains a derived, regenerable artifact built from the canonical YAML repo; retrieval stays
  behind a small library interface.
- **Embed**: fact cards, feature descriptions, source excerpts, each with
  `{chunk_type, feature_id, language_id, source_id, status}` metadata; syntax snippets are
  retrieved structurally. (Whether *full source texts* also get an index: brainstorm 21.)
- **Search**: filter-first, then hybrid BM25/FTS + vector fused with RRF, k=5, relevance floor;
  the university reranker is an eval-driven upgrade option.
- **Eval**: committed golden set (30–60 queries → expected IDs), Recall@5 + MRR in pytest,
  grown from logged agent misses.
- *[developer 2026-07-18]* **English-only** — no translations planned; coding is done in English.

## D8. Provider connectivity (03 — ratified)

One Python retrieval core; a **stdio MCP server** registered in `.mcp.json` for Claude Code and
MCP-speaking local models (`search_knowledge`, `get_fact`, `get_feature`, `get_neighbors`,
`get_source`); returned chunks carry inline citation keys. A thin FastAPI adapter serves
non-MCP providers and the site's search box. The website reads structured data directly — SEO
pages are never rendered from RAG.

- *[developer 2026-07-18]* **MCP server is read-only.** The write path is the agent pipeline only.

## D9. Human challenge channel (05 — ratified)

- No custom forum. Every fact page has a **"Challenge this fact"** action deep-linking to a
  prefilled GitHub issue form (fact ID, file path, current value, citations, page URL) on the
  **knowledge-base repo** (repos are split per D1 — website issues stay separate).
- Resolution loop: challenge issue → agent session re-argues with the debate machinery and
  commits the correction (verification-gated) → challenger @-mentioned → CI rebuilds → git
  history is the audit trail.
- giscus-style embedded Discussions as a fast follow; anonymous intake only if experts bounce
  off the GitHub-account requirement *[developer 2026-07-18: GitHub account requirement is
  acceptable]*.
- *[developer 2026-07-18]* No human experts are lined up yet; unchallenged facts count as
  **unverified, not verified** (fact-status model: brainstorm 12).

## D10. Website (06 — ratified)

- **Astro, fully static**, static-first hosting; zero-JS knowledge-base pages;
  builder/selector later as islands. Full rebuilds accepted initially.
- IA: `/features/`, `/features/<x>/`, `/features/<x>/<lang>/`, `/features/<x>/<a>-vs-<b>/`
  (alphabetical canonical), `/languages/`, `/languages/<x>/`; comparison pages only above a
  data-richness threshold; internal links derived from graph edges; stable slugs + 301 policy.
- JSON-LD from the data layer (TechArticle, ComputerLanguage + Wikidata `sameAs`,
  SoftwareSourceCode, citation nodes from CSL records).
- Citations as quiet numeric-superscript popovers (native Popover API; no-JS references-section
  fallback); row-level popovers in tables; "Challenge this fact" inside the popover; stable
  `data-fact-id` on every fact.
- Design: typography-first (Stripe/MDN/gwern lineage), build-time Shiki highlighting, one
  accent color, dark mode, no growth chrome.

## D11. Scoping: frontloaded research phase, no artificial MVP slice *[developer 2026-07-18 — supersedes the round-1 3×5 plan]*

The round-1 "3 languages × 5 features proof slice" is **rejected**: this is a personal hobby
project with no deadline, and a tiny slice would damage the frontloaded analysis of the generic
language-feature landscape, which will change anyway as concepts and languages are added.

Instead:

1. **A heavy research phase, completely separate from the per-language agentic pipeline**, in
   which agents with broad knowledge of many programming languages + internet access design the
   generic feature landscape (the ontology), backed by sources. Design of this phase: backlog
   brainstorm 25 (high priority). Full-source RAG (brainstorm 21) is likely its foundation.
2. **The per-language sweep pipeline (D5) is retained as the mechanism for adding new languages
   later**, once the landscape exists.
3. Budget posture per D6: full Claude Pro + reasonable academic API use, no cash; no
   long-term-damaging shortcuts for MVP speed.

Still deferred entirely: Language Builder, Public Library, Selector, upvotes/rankings, TIOBE
stats, comments, forum (kept as schema affordances only). CI = data-quality checks (schema,
referential integrity, citation integrity, coverage, determinism). Iteration hygiene keeps:
deterministic content-keyed IDs, one-cell-per-invocation resumable batches, YAML normalizer,
`generated_by` metadata.

## D12. Licenses & absent-on-purpose (08 — partially ratified)

- *[developer 2026-07-18]* **Code: MIT** (over Apache-2.0). **Corpus: CC BY-SA 4.0 tentatively** —
  final call waits on the licensing brainstorm (15).
- Absent on purpose: graph DB, message queues, Kubernetes/microservices, managed vector DBs,
  CMS, custom forum, custom auth (site static; challenges ride GitHub auth; MCP local).

## Round-2 decisions (2026-07-18 — **ratified by the developer**, amendments noted inline)

Consolidated from brainstorms 10, 15, 21, 22, 23, 24 and ratified in conversation. Developer
amendments are marked *[developer]*. Two sub-points remain open (D18 d/e — see open-questions).

### D13. CI: validated-artifact pattern; two repos (10)

The repo split does **not** hurt CI, conditional on one pattern: the KB repo's CI, on every
green push to `main`, publishes a **compiled, validated dataset bundle** (+ embeddings cache)
as GitHub Release assets (`latest-green` rolling tag, immutable `data-vN` tags); the website
repo consumes only that bundle (triggered by `repository_dispatch`, daily cron fallback,
one-parameter rollback to any `data-vN`). Never submodules or HEAD checkouts. The one genuine
cost: breaking schema changes need two sequenced deploys (~30 min, a few times a year); in
exchange, agents never touch deploy credentials and the site can only build from validated
data. **Exactly two repos**: `langatlas-kb` (data + schema + pipeline + agents + MCP + compose;
receives fact challenges) and `langatlas-site` (Astro + deploy; receives website issues) — a third
tooling repo is rejected. No-PR-gate safety: the agent runner runs the same fast offline
validators pre-commit (refuses to commit on failure), publication is last-green (red `main`
publishes nothing), and a failure bot auto-reverts only mechanically-safe tip commits,
otherwise halts the runner and files an issue. Agents commit under a GitHub App identity.

*[developer]* Ratified with: **GitHub App** (not PATs) for both dispatch and the agent-runner
identity; `data-vN` tags cut **daily, only on days with changes**; the embeddings cache stays
**private for now** (not a public release asset); red-main policy confirmed; the site **does**
display its `data-vN` build stamp.

### D14. Licensing policy (15)

LangAtlas is structurally safe: it publishes uncopyrightable **facts in its own words**; Czech
§ 31 quotation right covers short attributed quotes; EU TDM exceptions (DSM Arts. 3–4) bless
the private snapshot/index pipeline. Policy package: (1) corpus **CC BY-SA 4.0 confirmed**
(a free choice — no inbound share-alike forces it; flip to CC BY only if maximal reuse
becomes the priority; sticky either way once contributions arrive), code MIT, three-layer
plain-English LICENSE note; (2) **DCO**, not CLA; (3) quote cap ~50 words + per-page aggregate
warning in CI; (4) "no source content in public repos" stated as a *legal* rule; (5) CC BY-SA
sources (Hyperpolyglot, Wikipedia) are **finding aids + corroborating citations only — never
copy their cells/prose/examples**; (6) syntax examples are original, with an
`origin: original | adapted-from:<source-id>` field; (7) TIOBE-class proprietary indexes:
single attributed data points + links only, never bulk ingestion; (8) fetcher respects
robots.txt/TDM opt-outs; (9) language names in text, no logos without a trademark check.
Lawyer only if: public snapshot hosting, a rightsholder complaint, monetization, or deliberate
bulk ingestion of a proprietary/SA database.

*[developer]* Ratified in full: **CC BY-SA 4.0 final**; quote cap (~50 words / ~300-word
per-page aggregate warning) accepted; **text-only language names, no logos**. The university
API has no ToS restrictions on third-party copyrighted content — paywalled PDFs may flow
through the private pipeline.

### D15. Full-source RAG (21)

Round 1 missed it by scope-locking "RAG" to the fact-serving side; the developer's production-side
use case (research across many books) is real and is the **foundation of the D11 research
phase**. Build a **second `source_chunks` table in the same Postgres+pgvector**: ingestion CLI
(Docling-class PDF extraction, trafilatura for HTML) → structure-aware 400–800-token chunks
with breadcrumb prefixes and page/§/anchor locators + `parent_section_id` (small-to-big
expansion) → overnight batch embed on `qwen3-embedding-4b` → hybrid FTS+vector with RRF and
**`qwen3-reranker-4b` default-on**. Extracted text and embeddings stay out of git (private
snapshot store). Two new agent-facing read-only tools: `search_sources`,
`get_source_section` — never exposed to the website. Retrieved chunks carry machine-produced
locators that flow directly into source-first claims, and the **D4 verifier reads the same
table** — one index serving both discovery and verification (directly attacks risk K1).
Cost at ~30 sources: ~12–20k chunks, ~200 MB — trivial; real cost is the ingestion pipeline
(~1–2 focused weeks) + ~0.5–2 h extraction QA per book.

*[developer]* Ratified with: **initial corpus = the developer's collection at
`/home/terra/Downloads/hermes-research/`** — Van Roy & Haridi 2003 (CTM); Pierce, *Types and
Programming Languages* (2002) and *Advanced Topics in TAPL* (2004); Cardelli & Wegner, *On
Understanding Types, Data Abstraction, and Polymorphism* (1985); two Elsevier journal papers
(identify at ingestion); *Software Foundations Vol. 2: Programming Language Foundations*
(Coq + HTML) — **plus specs/docs/books of the initially supported languages**, tentatively the
**top 10 of the TIOBE index** (selection analysis: backlog topic 34). Docs-site ingestion is
limited to **official specs/reference chapters**. Paywalled papers are available via university
access — agents request them from the developer. Reranker default-on confirmed.

- *[developer 2026-07-18]* **Snapshot-store location: a plain directory on the dev machine**
  with a periodic tarball backup; revisit (private repo or object storage) when the project
  goes multi-machine or multi-contributor.

### D16. Ontology versioning (22)

- **Split immutable node `id` from renameable `slug`** (facts and content keys reference `id`;
  every historical slug lives in a versioned redirect map) — renames become PATCH events.
  Adopt before the research phase mints any nodes.
- **One semver in `ontology/VERSION`, defined by fact blast radius**: MAJOR = some fact's
  meaning/validity affected (split/merge/semantic move/removal/breaking schema); MINOR =
  purely additive, auto-bumped by CI; PATCH = cosmetic. `0.x` during the research phase;
  `1.0.0` at its exit.
- **Migrations**: one PR = taxonomy/schema edit + idempotent `migrate.py` + the migrated
  corpus diff + machine-readable manifest + agent-drafted impact report; CI replays the script
  for determinism; rollback = `git revert`; derived stores are always rebuilt, never migrated.
- **Casebook**: split → per-fact disposition (remap + cheap re-verify vs requeue), old URL
  becomes a hub page (not a 301); merge → mechanical remap + fast-path re-verify, both URLs
  301; layer/dimension moves touch only classification facts (URLs never encode
  layer/dimension); removals tombstone. Superseded fact IDs always leave tombstones
  (`derived_from`/`superseded_by`) so challenge links and chat logs never orphan.
- **Staleness** from migration manifests (precise), with the `ontology_version` stamp as the
  coarse audit backstop; staleness is a visible fact status.
- **Governance**: ontology MAJORs are the **one human-gated exception** to D1's no-review rule
  — RFC issue + objection window + developer merging on *process* criteria (not content
  authority); MINOR/PATCH (the vast majority of community taxonomy activity) stay ungated.
  Objection-window auto-merge is written into the RFC template as the stated successor once a
  real expert community exists. MAJORs batch into occasional coordinated bumps.
- **Excluded concepts** (scope/exceptions/security/naming) enter via Concept-first staging,
  later atomizing through ordinary splits; add a `cross_cutting` schema affordance now. The
  layer-3 `Exceptions` dimension vs the excluded "Exceptions" concept is the machinery's
  likely first real test.

*[developer]* Ratified in full, with: the developer accepts the ontology-MAJOR process gate;
id/slug split confirmed; hub-page policy for splits confirmed; merges get the fast-path
re-verify; **v1.0.0 is declared by the developer at a coverage threshold of their choosing**
(not automatic research-phase exit criteria); ~monthly MAJOR batching with an
urgent-correction exception.

### D17. Naming — **LangAtlas** *[developer 2026-07-18]*

The product is named **LangAtlas** (WALS — the World Atlas of Language Structures — pedigree;
brainstorm 23 has the full analysis). The former working title "Hermes" was publicly unusable
(Meta's Hermes JS engine owns the programming SERP; luxury-brand trademark) and is retired
everywhere except historical brainstorm documents. Rename happens **now**, before repos go
public: repos are `langatlas-kb`, `langatlas-site`, `langatlas-transcripts`. Tagline pattern:
"LangAtlas — a sourced map of programming-language features. Every fact cited."

- *[developer 2026-07-18]* Registrar check done: **`langatlas.dev` is available** (primary
  domain); `langatlas.io` is taken (recently registered by a third party); `lang-atlas.io` is
  available as a defensive option. Remaining action: register `langatlas.dev` and confirm the
  `langatlas` GitHub org name.

### D18. Chat logging & publishing (24)

**Capture from day one** (cannot be retrofitted): the shared provider wrapper persists every
call; Claude Code/SDK runs export through the same normalizer; one run = `manifest.yaml` +
`transcript.jsonl`, `run_id = <date>-<kind>-<slug>-<seq>`, `debate_id` maps 1:1. Storage: a
dedicated public **`langatlas-transcripts` repo** (plain JSONL sharded `YYYY/MM/<run_id>/`, one
commit per run; ~hundreds of MB/year — fine). Redaction before first publish: wrapper logs
message content only, secret scrub + gitleaks CI, large fetched-source tool results truncated
to excerpt+hash (copyright), system prompts published, viewer renders escaped text only,
force-push escape hatch logged in `REDACTIONS.md`. Fact provenance gains optional
`chat_run_id` → "AI chat" link in the citation popover (v0: raw GitHub link; v1.5:
`/chats/<run_id>/` Astro-island viewer, noindexed). Debate-history retrieval for agents:
first-line is the structured resolution records (exact-key lookup); a `chat_chunks` pgvector
index + pipeline-only `search_debate_history` tool (NON-CITABLE banner, **never on the public
MCP**) comes later (v2). Verdict: v1 ≈ 2–4 days of work.

*[developer]* Ratified with: pipeline-run logging mandatory, interactive sessions opt-in;
large fetched-source tool results **truncated** in published transcripts; raw-GitHub "AI chat"
links acceptable before the viewer ships.

- *[developer 2026-07-18]* **Force-push redaction escape hatch accepted**: history rewrites of
  the transcripts repo are allowed **only** for secret/copyright incidents, each recorded in a
  public `REDACTIONS.md` log (date, run affected, reason category) so the audit trail openly
  acknowledges the rewrite.
- *[developer 2026-07-18]* **Verification-run transcript granularity: one transcript per
  batch**, with per-claim anchors (`#msg-N`) recorded in the run manifest; each fact's
  "AI chat" link points into the batch transcript at its anchor.

## New decisions from the round-2 ratification conversation *[developer 2026-07-18]*

### D19. Positioning

The wedge vs PLDB/hyperpolyglot is **the typed concept graph, primarily, plus per-fact
sourcing**. The one-paragraph public positioning statement gets written in backlog topic 31
(launch positioning) around these two differentiators, in that order.

### D20. Fact granularity in files — option (b)

The authoring unit is **one record per feature instance, with per-field `sources:` lists**;
challengeable per-field facts (with stable IDs) are **derived at build time** from
(record, field) paths. Resolves former open question C13; topic 09 designs the concrete
schema and the stable derived-ID scheme, honoring D16's content-keyed-ID rules.

### D21. Controversy score

Controversy is an **ordinal score assigned by a dedicated assessor agent**, based on: agent
debate non-convergence, partial agreement between experts, partial verification verdicts, and
the strength of the backing sources. **GitHub challenges are explicitly NOT mixed into this
score** — challenge activity is a separate accompanying value carried alongside it. The
website defines its own presentation thresholds on the score (how/when to badge facts as
contested). Detailed design lands in topic 12.

### D22. Embedding-model benchmarking is a research-phase subphase

A dedicated subphase of the frontloaded research phase (topic 25) benchmarks embedding models
— university-hosted vs local CPU — on quality/speed trade-offs per use case (fact index,
source corpus, debate history), using the golden-set eval. The source-corpus default remains
`qwen3-embedding-4b` (D15) until that benchmark says otherwise.

### Terminology convention

Do not use the term "owner" in project documents or code — use **"developer"** (the person
operating the pipeline/making project decisions) or **"contributor"** (anyone participating),
to support multiple people working on the project.

## Round-3 decisions (2026-07-18 — from brainstorms 09, 11, 12, 13, 25, 34 — **ratified by the developer**, amendments noted inline)

Consolidated from the round-3 brainstorm batch (P1–P6) and ratified in conversation on
2026-07-18. Developer amendments are marked *[developer]*. Read the named brainstorm files for
full trade-off analyses. One item remains open: registering `langatlas.dev` and confirming the
`langatlas` GitHub org (D17) — see `context/open-questions.md`.

### D23. Fact schema & stable IDs (09)

Two-part fact identity reconciling D16 (immutable ids) with D20 (per-field derived facts): a
human-readable **anchor** `(record-id)#(field-path)` (with immutable sub-keys for list entries,
e.g. `fi.rust.pattern-matching#characteristics[c-exhaustive]`) locates the file/field, and a
content-keyed **fact id** `f-<12-hex SHA-256 of the canonical claim string>` identifies the
claim; a corrected value mints a new id sharing the anchor, with the old id resolved via an
append-only `tombstones.yaml`. Record ids are deterministic compositions of immutable node ids
(`fi.<lang>.<feature>`, `edge.<type>.<from>.<to>`, `alternative-to` endpoints lexicographically
ordered). Layout: per-language `instances/` directories, one record per file; edges sharded by
from-feature to avoid merge conflicts under D1's concurrent no-PR-gate commits; no `facts/`
directory — facts are pure build artifacts. Concrete v0 YAML schemas given for feature, concept,
feature instance (keyed `characteristics:`, keyed `syntax:` examples carrying D14's `origin`
field), edge, quality edge (keyed `assessments:` realizing D2's attributed spread), rule, source;
a worked Rust pattern-matching example yields four independently challengeable facts. One
locator-string grammar shared verbatim with brainstorm 21's chunk table; canonical claim
phrasing as fixed per-kind templates over node ids; a full YAML normalization spec.

*[developer]* Ratified with: **12-hex fact ids** confirmed, with the proposed CI collision
check. **Copyedit-tolerant hashing** confirmed — typo/wording fixes to a claim string don't mint
a new fact id. **`status: partial` is kept** on feature instances (not folded into `present` +
characteristics only), carrying associated notes typed `limitation | extra | alternative` to
describe the missing or additional aspect. **The verifier's pass/fail verdict is not written
back into the authored YAML** — it lives in a build-side ledger; the `sources:`/proof field
(the citations backing a claim) does live in the public YAML from the start, agent-authored and
human-correctable, per D1. **Quality vocabulary**: keep the `weak|moderate|strong` strength
labels, but consolidate D2's two quality edge types (`improves-quality`/`hurts-quality`) into
**one signed `affects-quality` edge** carrying polarity + strength — this supersedes D2 on
feature→quality edges specifically (D2's "`influences` is polarity-only" wording still stands
for feature↔feature `influences`). Language registry and the `cpp`/`csharp`/`javascript` id
conventions confirmed.

### D24. Claim↔source verification pipeline (11)

Index-only evidence: the verifier reads exclusively from the D15 `source_chunks` table, never
live-fetches at verdict time; un-ingested citations park claims in `pending-source`. A filter
ladder runs free mechanical stages first (registry/schema checks → locator resolution → quote
fuzzy match ≥0.90 pass / ≤0.80 fail / LLM in between), then one entailment call with claim
decomposition into atomic assertions with per-assertion grounding spans — a matched quote never
waives entailment (the core K1 laundering pattern is "quote real but overstated"). Six verdicts
per (claim, citation): `source-unavailable | locator-not-found | supported | partial |
unsupported | contradicted`; admissible = ≥1 `supported` tier-A/B citation; `since` gets a
*since-supported vs as-of-supported* split feeding the D2 back-dating pipeline. Primary model
`deepseek` (reasoning off), escalation to `deepseek-thinking` on partial/contradicted/
inconsistent output, `mini` as a cross-family drift gauge on ~10% of pairs; Claude never in the
verification loop (D6). Calibration against a committed golden set (~200–300 stratified items
including deliberately overstated claims) targeting false-accept ≤2% / false-reject ≤10%, with
per-batch known-bad canaries halting the batch on a pass. Logging per D18: one transcript per
batch, per-claim `#msg-N` anchors.

*[developer]* Ratified with: the **admissibility rule** (≥1 `supported` tier-A/B citation)
confirmed as proposed, amended so that **`partial` verdicts are logged in an identifiable,
filterable way** for manual inspection (not just folded silently into the pass/fail count).
**Calibration targets confirmed** (false-accept ≤2% / false-reject ≤10%), and the pipeline's
**measured error rates will be published** as a site-visible honesty feature. **Single verifier
model + cross-family sampling** (recommended strategy) ratified over mandatory two-model
agreement on every pair. **`pending-source` age alarm at 14 days** and **bounce budget of 2
re-files per claim** confirmed. **`verified-with-partials` stays provenance-only** — no
additional site-visible marker beyond normal provenance.

### D25. Fact confidence, dissent & staleness (12)

Status modeled as **three orthogonal axes** rather than one lifecycle: `verification`
(unverified / verified / partially-verified / failed), `freshness` (fresh / stale, from D16
migration manifests with `ontology_version` as backstop), `dispute` (none / contradicted /
superseded); a single display status is derived by fixed precedence. "Verified" always means
machine-verified — no human-endorsement state exists (D9); GitHub challenge state is never
stored in canonical YAML, only derived at build time. Confidence is an ordinal `high/medium/low`
lookup from strongest admissible source tier × count of independent corroborating sources;
community/tier-D sources can lift a level but never establish verification. Quality edges carry
attributed `assessments:` lists rendered as a distribution, never averaged or voted. Re-
verification is event-driven (migrations, source-snapshot drift, challenge resolutions, verifier
version bumps, back-dating runs) plus an 18-month budgeted rolling backstop sweep, oldest/
weakest-backed first. `since` back-dating is monotone earlier-only, source-first through the
normal gate, tagged `since_status: as-cited | back-dated`.

**Controversy score (concretizes D21)**: five ordinal levels — 0 `settled`, 1 `noted-variance`,
2 `contested`, 3 `disputed` (pipeline couldn't settle it), 4 `unsettled-in-the-field`
(independent tier-A/B sources genuinely disagree). Assessor = university-API `thinker`
(deepseek-v4-pro-thinking) over a fixed rubric and **structured inputs only** (debate records,
contradiction register, verification verdicts, source-strength context, assessment spread —
GitHub activity excluded per D21); Claude serves as golden-set calibrator and escalation target
for adjacent-level ambiguity and all level-3/4 assignments; runs event-driven in nightly
batches; output is machine-referenced (a `signals` list), no free prose as justification.
Challenge activity ships as a separate build-time value (`open/resolved/last_activity`);
presentation thresholds stay with the site (per D21).

*[developer]* Ratified with: **four controversy levels, not five** — level 4
(`unsettled-in-the-field`) folds into level 3 (`disputed`) from the start. The
**university-API-with-Claude-calibration lane is acceptable** for the controversy assessor (not
treated as Claude-grade judgment work under D6). **Auto-escalation to Claude applies to the
merged level-3 (`disputed`) assignments** (since levels 3/4 are now one level). The **18-month
backstop re-verification window and ~200-facts/night nightly budget** confirmed. **Confidence
vocabulary (`high/medium/low`) confirmed.** **Snapshot-drift policy confirmed**: a fact whose
live source has since changed stays verified against the archived snapshot while queued for
refresh. Separately, **`partially-verified` facts render publicly, visibly marked with a
badge** — not suppressed from public pages.

### D26. Provider-abstraction layer (13)

One thin policy layer, two channel types, no frameworks. The completion channel (university API
+ future local models) uses the plain `openai` Python SDK with `base_url` swapped; LiteLLM
rejected (breadth we don't need, heavy, daemon-shaped in proxy mode); rerank is a small
hand-rolled `httpx` call. The Claude channel stays agentic via the Claude Agent SDK / Claude Code
sessions (no raw API key exists on Pro), never flattened into a `chat()` call. Both channels
share one policy core, a `RunContext` that owns: the D18 transcript writer, the D6 cost log (same
code path so they can't disagree), budget enforcement (`max_calls/tokens/wall_seconds` per run
manifest, hard-stop with resumable checkpoint), and a SQLite content-addressed cache keyed on
resolved-model-id + messages + sampling + schema + `prompt_id@version`. There is deliberately no
way to call a provider without a `ctx` — that's what makes D18 logging non-bypassable. Structured
output via a per-alias probed capability table (schema-constrained decoding where supported, else
json-mode + pydantic validate + one repair turn + one retry). Shape: pure Python library in
`langatlas-kb`, no daemon. Testing: record/replay fixtures at the wrapper interface. Prompt
registry touchpoint is one opaque `PromptRef` handle (topic 32 owns the rest). Deliberately out
of scope: streaming to UIs, tool loops on the completion channel, multi-provider routing/
fallback, fine-tuning, exact tokenization, queueing.

*[developer]* Ratified with the gateway probed and confirmed: **OpenAI-compatible API**
(matches P4's plain `openai` SDK + `base_url` swap design); auth via `x-litellm-api-key: Bearer
TOKEN`; model metadata readable at `/v1/model/info`. **Rate-limit headers and per-alias
`json_schema` support are not documented** by the gateway — treat as no formal rate limit, and
probe `json_schema` support per alias empirically against each model's official capability card
(consistent with P4's per-alias probed capability table). **No dedicated `/v1/rerank` route is
documented** — treat reranking as completion-driven like every other call, matching P4's
hand-rolled `httpx` plan. **No published fair-use numerical concurrency ceiling exists** — set
the token-bucket default conservatively at implementation time rather than waiting on a number
that isn't coming. **Alias-drift policy**: pin the resolved model at run start and abort on
drift by default; fall back to live re-resolution only if pinning would create recurring
overhead that compounds over time. **One shared budget** across headless/pipeline and
interactive Claude usage — **the project may use the developer's full SDK credit pool**, with
the amendment that **pipeline/bulk agentic work defaults to Haiku-tier models**. **Local-model
config space reserved now** (schema/config surface only) — no CPU Ollama target stood up yet.
**Cache lives inside the D15 snapshot store**, riding the same backup as the source corpus.

### D27. Frontloaded research phase design (25)

Staged subphases **R0–R6** with a repeating per-theme loop: R0 infrastructure preflight (D15
ingestion pipeline, `ontology/` scaffolding at `0.1.0` with id/slug machinery, D18 logging, D13
validators, cost-logging wrapper — flags **topics 09 and 28 as R0 prerequisites**) → R1 corpus
assembly & ingestion with QA → R2 embedding benchmark (D22) on a pilot corpus → then, repeating
per theme: R3 divergent thematic survey (candidate concept/feature inventories with evidence
chunks) → R4 convergent ontology drafting (atomization, layers, dimensions, edges; contested
carves go through the D5 debate machinery repurposed with schema-dispute challenge types) → R5
reality checks against the topic-34 language set (an input parameter, not decided here; R5
doubles as the sweep-pipeline shakedown) → R6 consolidation and exit dossier. A single "architect"
session and strict waterfall are both rejected as prior-laundering / too rigid respectively.
Minting under D16 uses a **graduated 0.x ceremony**: immutable ids, content keys, validation, and
logging from the first node; free restructures with only redirect/tombstone lines while a theme
is active; lightweight migration manifests once a theme is "settled"; the full RFC-gated D16
process switches on only at `1.0.0`. D22 benchmark concretized: 40–60 golden queries in three
difficulty bands (exact-term / paraphrase / cross-source), Recall@5 + nDCG@10 + Recall@50
pre-rerank + MRR + latency; incumbent `qwen3-embedding-4b` stays unless beaten by ≥5 pts
Recall@5 or matched within 2 pts by a local model; reranker stays default-on unless it adds
<2 pts. Source strategy: curated-corpus-first (D15 seed + specs) plus proposed new acquisitions
(Scott *Pragmatics*, Turbak & Gifford, Harper *PFPL*, Krishnamurthi *PLAI*, Sebesta, Kaijanaho
2015) with gap-driven internet scouting into papers and official design docs (Rust RFCs, PEPs,
JEPs). Exit: a coverage dossier (external-checklist coverage, 100% tier-A/B-backed nodes, <5%
unmappable, zero exclusivity violations, churn ≈ 0, pipeline readiness) against which the
developer declares v1.0.0 per D16. Handoff to the per-language sweep pipeline is a **questionnaire
compiler** deriving the D5 sweep questionnaire from the ontology's fact-bearing field map.

*[developer]* Ratified with: the **graduated 0.x minting ceremony confirmed** as proposed.
**Acquisition list ratified in full** — acquire all six proposed texts: Scott, *Programming
Language Pragmatics*; Turbak & Gifford, *Design Concepts in Programming Languages*; Harper,
*Practical Foundations for Programming Languages*; Krishnamurthi, *Programming Languages:
Application and Interpretation*; Sebesta, *Concepts of Programming Languages*; Kaijanaho
(2015). The **developer will co-author the golden set** during source-corpus QA skims. **R5
reality-check breadth: the rotating 4–5-language sample per cycle** (the cost-optimized
recommendation), not the full topic-34 set every cycle. The **proposed exit bars are advisory
only, none binding** — the v1.0.0 declaration stays entirely the developer's discretionary
judgment per D16. **Fact-index embedding-model decision deferred to sweep-pipeline start**, as
proposed — the source-corpus benchmark (D22) stands now, the fact index gets its own re-run
later. **R3's per-theme topic list requires explicit developer sign-off before each cycle** —
research agents do not proceed autonomously between checkpoints.

### D28. Initial language selection (34)

**14-language curated set** — the July 2026 TIOBE top 10 minus SQL and Visual Basic, plus
Haskell, OCaml, Prolog, Erlang, Go, Swift — onboarded in four phases (this amends the
"tentatively TIOBE top 10" clause of D15):

- **Phase 1 — ontology stress set (6)**: Python, C, Java, Rust, Haskell, Prolog — every layer-3
  dimension in the brief gets ≥2 distinct values instantiated inside this phase alone; cheap
  free references let the D15 ingestion pipeline mature before harder specs arrive (Prolog is
  the one acquisition gap — see open questions).
- **Phase 2 — mainstream weight (4)**: C++, C#, JavaScript, R — remaining TIOBE-top-10 members,
  highest sweep/ingestion cost, run against a phase-1-hardened ontology.
- **Phase 3 — landscape completers (4)**: OCaml, Erlang, Go, Swift — functors/effect handlers,
  actors, CSP + structural interfaces, ARC + protocol-oriented design; all four have free
  permissively-licensed references.
- **Phase 4 — optional cheap completeness**: Visual Basic (near-zero novel facts, restores
  literal "TIOBE top 10 covered" for positioning).
- **Deferred, revisit post-1.0**: SQL (needs an ontology position on DSLs first), TypeScript (no
  normative spec), Scheme/Racket, APL-family, Julia, Elixir.

All 14(+VB) have bundled Shiki grammars (no D10 risk). Positioning line for topic 31: "the
most-used languages of the TIOBE top 10, plus the languages that define the rest of the feature
landscape."

*[developer]* Ratified with: **SQL deferral and Visual Basic demotion to optional phase 4**
confirmed as proposed. **Prolog tier-A backing resolved** — the developer has acquired
Deransart, Ed-Dbali et al., *Prolog: The Standard Reference Manual* (1996); use it as Prolog's
tier-A/B backing text immediately, removing the phase-1 blocker (ISO/IEC 13211-1 purchase no
longer needed to start). **BEAM/actor-model representative: both Erlang and Elixir** get
language pages (bumping the phase-3 core set from 14 to 15 languages, both alongside Go and
Swift). **Oz and Coq/Rocq stay concept-source-only** — facts sourced at feature level from CTM /
*Software Foundations*, no dedicated language pages, no sweeps; Oz does not get its own language
pages despite CTM's centrality to the corpus. **Pinned spec edition per language: pick the
latest available edition** for each (e.g. C23/N3220 over C17; JLS SE 25 over SE 21 LTS; the
current ECMA-262 edition; Haskell 2010 + the latest GHC user guide), re-pinning as new editions
ship. **Later onboarding phases (2–4) are gated on completing earlier phases' sweeps** — they do
not interleave, even once the ontology reaches `1.0.0`.

## Batch 14, 16, 17 decisions (2026-07-18 — from brainstorms 14, 16, 17 — **ratified by the developer**, amendments noted inline)

### D29. Corpus bootstrap & import strategy (14)

Reject bulk import of PLDB (public domain) and Wikidata (CC0) as fact content: D3's
"community sources are corroboration only, never sole backing" rule already forbids what a bulk
import would require, and it would gut D19's positioning wedge (typed graph + per-fact sourcing
vs PLDB). Both stay **finding aids only** (alongside Hyperpolyglot/Wikipedia, D14 rule 5), used
by research-phase/sweep agents to generate coverage checklists and candidate language↔feature
pairs — never copied into `sources:` or claim text. No new fact-status tier needed. Seeding is
judged a false economy: the bottleneck is verified sourcing, not candidate generation, and the
D24 gate runs per-fact regardless of origin.

*[developer]* Ratified with: **Option C's finding-aid-only scope confirmed** as proposed — no
distinction in restrictiveness from Hyperpolyglot/Wikipedia despite PLDB/Wikidata's more
permissive licenses. **`provenance.candidate_source` specified now**, not deferred to topic 32:
an optional, non-public enum `pldb | wikidata | hyperpolyglot | internal-survey |
sweep-questionnaire | challenge`, recorded at proposal time, extending D23's provenance block,
for pipeline analytics only — never rendered on the public site. **No explicit note needed**
distinguishing this rejection (Wikidata as fact source) from D10's already-decided Wikidata
`sameAs` outbound SEO link — the two uses are different enough in context that a callout isn't
necessary. **A narrow carve-out is added**: pure identification metadata from PLDB/Wikidata
(file extensions, first-appeared year — not feature/paradigm claims) may be pulled as single
attributed data points, mirroring D14 rule 7's treatment of TIOBE.

### D30. Debate cost/quality instrumentation (16)

Split the checklist's "N-agent debate vs. single-agent+verifier" question into two
differently-timed pieces: R4 schema-dispute debates (running now, per D27) and sweep-pipeline
fact debates (D5), which can't produce volume before phase-1 onboarding (D28). Stand up two
cheap, zero-new-infrastructure scripts now, reusing data already logged under D18/D24/D26: (a) a
verifier-replay counterfactual re-scoring a debate's pre-challenge draft through the D24 verifier
to see whether the challenger round changed anything detectable; (b) a cost join computing
Claude-messages-per-accepted-fact segmented by `debate_id`. Defer any scored golden set or full
debate-vs-no-debate simulator until phase-1 onboarding produces real fact-debate volume. The
minimal regression harness is D26's already-planned record/replay fixtures plus a hand-curated
regression subset, diffed on prompt/model change — no heavier A/B simulator.

*[developer]* Ratified with: **the verifier-replay counterfactual (Option A) confirmed as
sufficient on its own for now** — the downstream dispute-rate comparison (Option B) is **not**
wired up yet, staying deferred until post-phase-2/3 volume makes matching feasible (its
selection-effect confound is not worth accepting early). **R4 schema-dispute debate outcomes
will also be tracked against later D16 MAJOR-churn** (did a carve that survived R4 sign-off
later get reverted in a MAJOR bump) — not just measured at the R4 checkpoint sign-off itself.
**Regression fixtures live under the same `tests/fixtures/providers/` tree D26 already
specifies**, in a `regression/` subfolder, with the lighter-weight human-diff review step (not
CI-blocking pass/fail like D26's core record/replay fixtures) — per the brainstorm's own
recommended shape.

Left open (needs sharper framing before the developer can answer): what threshold of "debate
changed nothing detectable" would justify simplifying the challenger round for some conflict
types — see `context/open-questions.md`.

### D31. Prompt-injection surface of fetched sources (17)

Generalize D24's existing verifier-safe pattern (fetched content delimited as evidence, never as
instructions) project-wide, enforced once inside the D26 `RunContext`/provider wrapper rather
than per-prompt discipline, plus a cheap shared lexical instruction-pattern scan on every
fetch/search tool result, logged per D18. Explicitly rejects building a dedicated low-privilege
reader/actor agent split for now (kept as an escalation path only if logged flags turn into
evidence of actual manipulation) and rejects a parallel injection-specific admissibility gate —
the existing D4/D24 entailment gate already has to catch an injected claim the same way it
catches a hallucinated one. Rationale: no private data, no exfiltration channel, low-traffic/
not a high-value target, and git history makes any landed bad fact discoverable and revertable,
so severity is bounded even though likelihood (routinely reading adversarial-by-default internet
text) is non-trivial.

*[developer]* Ratified in full, with: **the §1.2 risk framing (bounded severity, non-trivial
likelihood, light-touch controls) confirmed** as matching the developer's own risk tolerance —
no reader/actor split needed from day one. **The delimiter/scan convention gets documented by
folding into topic 13's wrapper implementation notes** — no separate spec doc. **Flagged
instruction-pattern hits always log-and-continue** — never hard-block a run. **The R3
live-web-fetch tool (topic 25) does not need the same wrapper treatment from day one** — it is
acceptable to run the first research-phase iteration without it and retrofit before it's relied
on heavily (overriding the brainstorm's own lean toward building it early in topic 13).

## Top risks to design against (08 — full ranked register in the brainstorm)

1. **K1 Citation laundering** — mitigated by D4; extra load-bearing now that there is no human
   merge gate.
2. **K2 Ontology/schema instability** — mitigated by the frontloaded research phase (D11) and
   the ontology-versioning system (brainstorm 22).
3. **P1 Differentiation vs PLDB/hyperpolyglot** — positioning statement still owed (open
   question A2).
4. **S1 Solo scope collapse** — mitigated by the deferred-modules list and incremental
   checklist-driven work.
5. **P2 SEO cold start** — success metric is corpus quality + MCP usability, not traffic.
