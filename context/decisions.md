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
influences ±, conflicts-with, alternative-to; 2 feature→quality types *[superseded by D23,
2026-07-18: consolidated into one signed `affects-quality` edge]*), **Rule** (multi-feature
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
- *[developer 2026-07-20]* The budget additionally includes a **small programmatic SDK credit
  pool** alongside Claude Pro (surfaced during D26's ratification). It is never for volume:
  bulk work stays in the university-API lane, and the credit pool is reserved for the pipeline
  steps requiring the highest-quality judgment. Supersedes D26's "pipeline/bulk agentic work
  defaults to Haiku-tier models" clause.

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
non-MCP providers and the site's search box *[amended by D33, 2026-07-19: site search ships as
Pagefind; the public FastAPI search endpoint is deferred until lexical search proves
insufficient]*. The website reads structured data directly — SEO
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
- *[developer 2026-07-18]* No human experts are lined up yet; the absence of human challenge
  confers nothing — **"verified" comes only from the machine gate (D4/D24)**, never from a fact
  having gone unchallenged (fact-status model: brainstorm 12). *[Reworded 2026-07-20: the
  original "unchallenged facts count as unverified" phrasing contradicted D25's
  machine-verified-only model.]*
- *[developer 2026-07-20]* **An accepted human challenge is a hard override** of anything
  machine-decided about the fact: the re-argued correction still enters through the normal
  verification gate on its way in, but no subsequent machine verdict can reinstate a value a
  human challenge overturned.

## D10. Website (06 — ratified)

- **Astro, fully static**, static-first hosting; zero-JS knowledge-base pages *[amended via
  D32/D33, 2026-07-19: the inline Pagefind search box and giscus embeds on feature/language
  pages add scoped JS islands — "zero-JS" means core knowledge-base content renders fully
  without JS]*; builder/selector later as islands. Full rebuilds accepted initially.
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

*[developer 2026-07-20]* Embeddings-privacy clause reaffirmed against D62: embeddings stay
private as long as the web app itself has no use for them (it currently doesn't — site search is
Pagefind, D33); see the dated note on D62 for the delivery mechanics.

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

*[developer 2026-07-20]* Budget clause amended (see D6's dated bullet): the SDK credit pool is
small and reserved for the highest-judgment pipeline steps only — never bulk work, which stays
in the university-API lane per D6. The "pipeline/bulk agentic work defaults to Haiku-tier
models" clause above is superseded.

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
JEPs). Exit: a coverage dossier (100% tier-A/B-backed nodes, <5%
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

*[developer, 2026-07-19]* **External-checklist coverage is dropped from the exit dossier
entirely** (D52 amended to match): the brief and the R0/R1 seed sources (Jordan et al. 2015, Van
Roy & Haridi 2003) are seed context for the research phase, not something the developer wants
tracked as a coverage metric — the dossier now has five items, not six.

### D28. Initial language selection (34)

**15-language curated set** *(ratified as 14; Elixir added by the amendment below)* — the July
2026 TIOBE top 10 minus SQL and Visual Basic, plus Haskell, OCaml, Prolog, Erlang, Elixir, Go,
Swift — onboarded in four phases (this amends the "tentatively TIOBE top 10" clause of D15):

- **Phase 1 — ontology stress set (6)**: Python, C, Java, Rust, Haskell, Prolog — every layer-3
  dimension in the brief gets ≥2 distinct values instantiated inside this phase alone; cheap
  free references let the D15 ingestion pipeline mature before harder specs arrive (Prolog is
  the one acquisition gap — see open questions).
- **Phase 2 — mainstream weight (4)**: C++, C#, JavaScript, R — remaining TIOBE-top-10 members,
  highest sweep/ingestion cost, run against a phase-1-hardened ontology.
- **Phase 3 — landscape completers (5)**: OCaml, Erlang, Elixir, Go, Swift — functors/effect
  handlers, actors (both BEAM representatives, per the amendment below), CSP + structural
  interfaces, ARC + protocol-oriented design; all five have free permissively-licensed
  references.
- **Phase 4 — optional cheap completeness**: Visual Basic (near-zero novel facts, restores
  literal "TIOBE top 10 covered" for positioning).
- **Deferred, revisit post-1.0**: SQL (needs an ontology position on DSLs first), TypeScript (no
  normative spec), Scheme/Racket, APL-family, Julia. *(Elixir removed from this list
  2026-07-20 — editorial fix: the ratification amendment below had already moved it into
  phase 3 as the second BEAM representative.)*

All 15(+VB) have bundled Shiki grammars (Elixir's included; no D10 risk). Positioning line for topic 31: "the
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

*[developer, 2026-07-19]* **SQL gets its own new phase 5** in this phased plan (D50), rather than
folding into whichever phase is current once D50's `language_kind`/`applies_to` schema and its
vendor-dialect sourcing substitute are both settled. Phase 5 stays otherwise undesigned until
those two prerequisites land.

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

*[developer 2026-07-20]* **Identification metadata is ungated registry data, not gated facts**:
fields like file extensions and first-appeared year live on the Language registry record, never
pass through D4/D24's admissibility gate, and need no tier-A/B backing — the tier-D citation is
recorded for attribution only. (Resolves the otherwise-impossible interaction with D24's
≥1-supported-tier-A/B admissibility rule; D53's "through the normal D4 gate" wording is
superseded accordingly.)

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

## Batch 18, 19, 20 decisions (2026-07-19 — from brainstorms 18, 19, 20 — **ratified by the developer**, amendments noted inline)

### D32. Contribution funnel & ergonomics (18)

Four typed GitHub Issue Forms (`challenge-fact.yml`, `propose-coverage.yml`,
`request-language.yml`, `general-question.yml` redirecting to Discussions) replace D9's single
generic template, auto-labeled and deep-linkable from site surfaces with pre-filled query params
— this *is* the "propose a fact" web form; no dedicated form backend, serverless relay, or
third-party form service gets built (would conflict with D10's static site / D12's no-custom-auth
stance for no real benefit over the already-accepted GitHub-account requirement). giscus
Discussions scoped to feature and language pages only (`pathname` mapping, lazy thread creation,
small fixed category set), with an explicit Issues-vs-Discussions division of labor documented in
`CONTRIBUTING.md`. A new `/coverage/` page joins the site IA: a build-time feature × language
matrix with three distinct empty-cell states (not-yet-swept / not-yet-onboarded / deferred per
D28), each empty cell deep-linking to a pre-filled `propose-coverage` issue; ships as pre-baked
static views (zero-JS, matching D10) with detailed interactive matrix UX left to topic 19. For the
"would-be co-author" gap D1 left open (D1 no-PR-gate was scoped to the project's own agent fleet,
not external humans), a **graduated external-authorship posture**: source/candidate-proposal PRs
only for now (mechanically checkable, no entailment judgment involved), escalating to
developer-skimmed full fact-PRs once the channel has a track record, with unqualified
auto-merge-on-green reserved indefinitely — mirroring how D16 and D30 already handle comparable
trust-boundary questions. No growth chrome (no contributor leaderboards/badges/counters); the
invitation lives in genuinely useful content (the coverage matrix's honest gaps), not social
signaling.

*[developer]* Ratified with: the **graduated external-PR posture confirmed as proposed** (source/
candidate-proposal PRs now, escalating to developer-skimmed full fact-PRs once the channel has a
track record, unqualified auto-merge reserved for much later) — no further commitment now.
**giscus scope confirmed as proposed**: feature and language pages only for now, **no comparison
pages** (they stay gated on D10's data-richness threshold before getting Discussions at all).
**The four-template issue-form set confirmed as proposed** (`challenge-fact` / `propose-coverage`
/ `request-language` / `general-question`) — no folding/splitting. **`/coverage/` IA placement
confirmed**: a standalone top-level page, with **no conflict** with topic 19's matrix-component
assumptions. **Not-yet-onboarded (D28 later-phase) languages get no per-language stub page** —
all recruitment for those languages lives on `/coverage/` only. **No hand-curated "good first
gap" list** — the coverage page waits for topic 44's coverage analytics data rather than the
developer hand-picking an initial seed list.

### D33. Website deep-dives (19)

Five fairly independent sub-topics, each screened against D10's zero-JS/static posture and the
"boring, solo-maintainable technology" constraint. **Search**: ship Pagefind (static, client-side
lexical index over rendered pages) as the default; defer publicly exposing the D8 FastAPI hybrid-
search endpoint until logged-query evidence shows lexical search is insufficient. **Coverage-
matrix component** (the interaction design left open by D32's IA placement): several pre-baked
static views (overview, per-language, per-dimension, "biggest gaps") rather than a live
interactive table for now; revisit an Astro island (preferred over CSS-only tricks) only if that
proves insufficient once real coverage data exists. **Syntax-preview validation**: add a
`syntax_check: parser | none` language-registry field, wiring real parse-only checks (not full
compilation) into the existing D13 offline validator suite for languages with a cheap CLI syntax-
check mode; explicitly reject LLM-based plausibility checks for code correctness as inconsistent
with D4's verified-ground-truth premise. Missing-Shiki-grammar risk for post-1.0 onboarded
languages becomes a per-onboarding-cycle checklist item (fallback to plain-text highlighting), not
a new site feature. **OG images**: build-time Satori + resvg generation, two-to-three page-kind
templates (feature/language/comparison) pulled from the structured data layer — no runtime image
service. **Analytics**: self-hosted Umami (MIT-licensed, cookieless, no PII) added to the existing
docker-compose stack post-launch, consumed manually and privately by the developer, never
surfaced on the public site. **Trust-signal UX** (rendering D25's axes without dashboard creep):
extend the existing D10 citation popover with a plain-text line covering all D25 axes
(verification/freshness/dispute/confidence/controversy); reserve exactly one shared base-page
glyph for the disputed/contradicted/superseded/partially-verified minority of facts, with every
other status combination staying visually silent on the page itself.

*[developer]* Ratified with: **search ships as an inline instant-search box on every page**
(not a dedicated `/search/` results page), which must support **ctrl+click to open a result in a
new tab**; the FastAPI hybrid-search fast-follow deferral is confirmed. **No concrete trigger** is
set now for revisiting an Astro island on the coverage matrix — "the developer notices the static
views aren't working" stays an acceptable informal trigger. **"No automated syntax check" for
languages without a fast CLI syntax-check mode (Prolog and similar) is acceptable indefinitely**,
not conditioned on topic 42 settling `language_kind` first. **OG images omit the citation-count/
controversy glyph entirely** (rather than a coarse verified/disputed-only icon), to avoid any
staleness risk between the static image and the live page. **Self-hosted Umami confirmed** over
Plausible/GoatCounter self-hosted, per the brainstorm's MIT-license/Docker-friendliness argument —
no standing preference overrides it. **The single-shared-glyph design confirmed** — one marker
doing double duty for disputed/contradicted/superseded/partially-verified, with no visual
distinction between those states outside the popover.

### D34. Scale-up & phase-2 backend sketch (20)

**Sweep pipeline at many-language scale**: keep D5's independent per-language sweep unchanged
while the language count stays near D28's curated 15 — no batching/lineage-reuse across similar
languages (rejected: would introduce anchoring bias and undermine the reconciler's independence
property, the load-bearing check that catches genuine divergence). A future **tiered "stub
sweep"** (a small fixed field subset for long-tail languages, upgradeable later without a schema
migration) is the proposed release valve *if* the project's ambition ever shifts from curated
depth toward PLDB-adjacent breadth (thousands of languages) — not designed in detail, flagged as
its own future brainstorm. Prioritization past the curated 15 should draw on coverage-gap
analytics (topic 44) and audience demand rather than D28's ontology-stress ordering, which stops
applying once the ontology is stable. **The static site (D10) needs no architectural change for
language-count scale** — full-rebuild time is the only metric to watch; the real site-scale
trigger (coverage-matrix pre-baked views proving insufficient, per brainstorm 19) is orthogonal to
language count. **The Builder does not automatically need a dynamic backend**: splitting it into
combination-validation + sharing (both stay backend-free — client-side rules engine, URL/
localStorage-encoded permalinks, matching D10's static-first plan) versus the public library of
built languages (the one piece that genuinely needs a live writable store, since "public" +
"persistent" + "browsable" cannot be static) shows the honest trigger is "the library ships," not
"the Builder ships." Ship the backend-free half first; when/if the library is greenlit, extend the
existing Postgres+FastAPI stack with a clearly separate, non-derived community schema and GitHub
OAuth — reject a third-party backend-as-a-service absent a concrete reason to distrust
self-hosting. Ontology-versioning mechanics (id/slug split, blast-radius semver, migrations) are
explicitly out of scope here — D16/topic 22 remains the authority regardless of language count.

*[developer]* Ratified with: **yes, eventually** — there is a real ambition to go past the curated
15-language set toward broader PLDB-adjacent coverage, so the tiered "stub sweep" proposal stands
as the future release valve rather than being dropped. **PLDB's language list (names only, not
content) confirmed as a legitimate future target-selection input** for choosing which languages to
consider onboarding next, distinct from D29's already-settled rejection of PLDB as fact content.
**The trigger for greenlighting the public-library half of the Builder is purely developer
discretion** — no fixed criterion (verified-fact count, traffic threshold, etc.) is set now.
**No visible site-side badge is needed for a future stub-sweep tier** distinguishing full-depth
from stub-depth languages — the existing `/coverage/` "help wanted" framing (D32) already covers
this adequately.

## Batch 26, 27, 28 decisions (2026-07-19 — from brainstorms 26, 27, 28 — **ratified by the developer**, amendments noted inline)

### D35. Dataset bundle contract design (26)

The published dataset bundle (D13) is two GitHub Release assets per `data-vN` tag: a
zstd-compressed single **SQLite file** (`langatlas-data-vN.sqlite.zst`) plus a small **JSON
manifest** (`langatlas-data-vN.manifest.json`) — no wrapping archive, since GitHub Releases
already support multiple named assets per tag. This is an interchange-format choice only; it does
**not** reopen D7's "no SQLite serving phase" decision — the live services still run on Postgres,
and the bundle is a file that gets downloaded once and loaded *into* Postgres (or read directly
only in the narrow MCP "lite mode" below). Three independent version axes go in the manifest:
`data_tag` (the D13 release tag, drives rollback), `ontology_version` (D16/D22's content semver,
carried for provenance/D25-freshness-backstop display only — no compatibility logic needed since
derived stores are always fully rebuilt), and a new **`bundle_schema_version`** (a semver over the
bundle's own table/column/manifest structure — MAJOR = breaking structural change, MINOR =
additive, PATCH = non-structural). Consumers pin a compiled-in `bundle_schema_version`
compatibility range and **hard-refuse to load on a MAJOR mismatch** (loud failure, matching D13's
failure-closed publish posture). The manifest also carries `git_commit`, `built_at`,
`embedding_model_id` (nullable), integrity hashes (`sqlite_sha256`, `sqlite_zst_sha256`,
`sqlite_bytes`), per-table row counts, and the D24 published verifier error-rate estimates.

The D20 fact-granularity interaction is resolved by shipping a **single flat, precomputed `facts`
table** — one row per derived fact, already carrying `fact_id`, `anchor`, `canonical_claim`,
`rendered_text`, `sources_json`, `provenance_json`, and all D25 status axes — alongside
record-shaped tables (`instances`, `edges`, `rules`, `sources`, `features`, `concepts`,
`languages`) for page-shaped reads, plus `tombstones`/`redirects` tables. Facts are computed once
in the build pipeline and shipped as data, never re-derived independently by each consumer.

MCP's primary path is unchanged from D8 (queries Postgres, which the loader populates and stamps
with the manifest's version fields in a `_meta` table). A documented, explicitly-labeled **lite
mode** is proposed on top: the MCP server can be pointed directly at a decompressed bundle
`.sqlite` file with no Postgres, giving full point-lookup tools and SQLite-FTS5-only lexical
search; every lite-mode response carries `"retrieval_mode": "lexical-fallback"` so reduced quality
is never silently served as the full deployment.

**The MCP caution contract** (the checklist's named sub-problem): every fact object in every MCP
tool response carries a mandatory, always-present `caution` block
(status/confidence/verification/dispute/note — note null only when fully settled); non-null notes
are additionally prepended as plain-text caveats into the tool's returned text content, not left
structured-only; and the MCP tool descriptions themselves state the caution contract so it loads
into a consuming agent's context once per session. No fact is ever suppressed for low confidence
or high controversy (mirrors D9/D25's non-suppression policy); `search_knowledge` keeps relevance
as its primary sort key, with confidence/controversy staying per-result annotations rather than a
re-ranking signal.

Snapshots are always full, never incremental/diffable, matching D13's existing rollback model;
expected size is low tens of MB compressed — trivial for GitHub Release assets at this project's
scale. Full analysis: [brainstorms/26-dataset-bundle-contract.md](brainstorms/26-dataset-bundle-contract.md).

*[developer]* Ratified with: **`bundle_schema_version` starts at `1.0.0`** once this design is
implemented, treating the pre-implementation period as `0.x` — consistent with D16/D22's own
graduated-ceremony pattern, over a lighter-touch scheme that skips the axis. **MCP lite mode is
not worth building in v0** — it stays a documented future accessibility feature while the primary
Postgres-backed MCP path (D8) ships first. **The caution contract's `(status, dispute)` →
note-sentence template table lives in the MCP server's own code**, not the bundle, so wording can
improve without a data republish. **The Postgres loader's embedding-cache-reuse check allows a
looser per-fact content-hash match** (not just exact `(embedding_model_id, corpus_hash)`), so
unchanged facts skip re-embedding even across an otherwise-changed publish.

### D36. Agent-runner commit protocol & failure bot (27)

An agent run lands each commit via a **persistent local clone**: `git fetch` + `git
rebase origin/main` + fast-forward-only `git push`, retried on non-fast-forward rejection, giving
up after 5 retries or 3 minutes (whichever first) and reporting `contention_exhausted` rather than
looping forever or dropping the record — D23's per-file sharding keeps the common case a cheap
content-free rebase. The **GitHub App identity** (already named over PATs in D13) is scoped to
`Contents: write`, `Issues: write`, `Checks: read`, `Statuses: read` — deliberately no `Pull
requests` scope, since the runner's own lane never opens PRs; a second, separately-scoped App is
proposed if the D32 external-PR skim ever needs PR permissions. Token refresh is owned by
`RunContext` (D26) and never logged (D18). DCO handling for automated commits: a documented
CONTRIBUTING.md carve-out treats the GitHub App's installation itself as the one-time sign-off,
with per-commit `Signed-off-by:` trailers reserved for human-submitted PRs only.

**Commit granularity is one commit per touched record file** — not per agent turn, not per derived
fact, since facts have no independent existence to commit (D20/D23). Every commit carries a
`LangAtlas-Record-Key` trailer (content hash + path, the idempotency key) and a
`LangAtlas-Chat-Run-Id` trailer linking to D18's separate, coarser transcript-batch granularity.
**Is-main-green gating** decouples preparation (drafting, D24 verification, local validation) from
landing: only the final push checks `main`'s CI status; on red or unknown status, the record is
held in a local ready-to-land queue and reported `blocked_red_main` rather than pushed or
discarded — the runner never tries to fix a red `main` itself.

**Auto-revert requires all four conditions**: the failing commit is `main`'s current tip; its
author is the bot identity; the failure is a deterministic validator failure reproduced once (not
a flake); and `git revert` applies cleanly. Any unmet condition halts the runner and files an
issue instead of acting. A **run-level circuit breaker halts after 2 reverts in one run** even if
each individually passed. Content disputes, D25 controversy flags, and anything the D24 verifier
already gated stay explicitly out of auto-revert's scope — those are supposed to land and render
visibly flagged, not get reverted.

The **halt/resume interface** handed to the future run-orchestrator (topic 35, not designed here)
is a typed `LandResult` union (`landed | blocked_red_main | contention_exhausted | reverted |
unsafe_halt`). Idempotent resume is guaranteed by checking the `LangAtlas-Record-Key` trailer
against `main`'s reachable history before any push — ground truth that survives even a lost
orchestrator checkpoint. **Multi-runner concurrency** needs no queue for now (optimistic retry via
§2.1's mechanics, cheap because of D23 sharding); a single Contents-API-mediated `RUNNER_LOCK`
lease is named as the escalation path if concurrent runners become real, not designed further.

**External-PR abuse handling stays a fold-in note, not a full section** — different trust domain
from D32's already-narrow near-term scope, zero current volume. The one load-bearing near-term
mitigation is GitHub's native "require approval for first-time-contributor workflow runs" setting
(no custom code). The "provenance/scope skim" D32 left unspecified is three mechanical checks:
permitted file types only, single-topic PR, resolvable bibliographic identifiers — an extension of
the validator-CLI scope (topic 40), not a new protocol. Full analysis:
[brainstorms/27-agent-runner-commit-protocol.md](brainstorms/27-agent-runner-commit-protocol.md).

*[developer]* Ratified with: **DCO carve-out confirmed** (see above). **The 5-retries/3-minutes
fetch-rebase-retry threshold and the 2-revert-per-run circuit breaker are confirmed as proposed**
— no different numbers wanted. **Time spent `blocked_red_main` gets an exemption from a run's
overall budget/wall-clock hard-stop (D26)**, since the delay isn't the runner's own doing (an early
instinct only — topic 35 still owns the final interface question). **A second, separately-scoped
GitHub App is confirmed** for the external-PR skim once it needs `Pull requests` access, mirroring
D32's trust-domain separation, rather than widening the existing runner App's permissions. **One
rerun is confirmed sufficient** to distinguish flake from real failure before auto-revert — no
stricter two-rerun bar.

### D37. Locator normalization & ingestion QA (28)

Confirms brainstorm 09's locator grammar **verbatim, no changes**. URL-kind locators
always pin to the archived snapshot, never the live page (live-page freshness is the link-checker's
job, kept cleanly separate from locator validity). Multi-entry `sources:` lists keep OR-semantics
as the default; a conjunctive `all_required` mode stays unbuilt in reserve. One shared
`validate-locator` routine (regex shape + `source_chunks` resolution check) is reused by the
pre-commit gate, CI, and the D24 verifier's stage-2 step, so a malformed locator is caught at
commit time rather than wasting a verifier batch.

**Extraction-quality harness**: garbled-text detectors (encoding/mojibake, OCR heuristics,
extraction-collapse, length-distribution outliers) plus an outline-coverage diff (chunker's
`section_path` set vs. the source's own table of contents) run in the ingestion CLI.
Encoding/extraction-collapse failures **hard-gate** a source from `source_chunks` promotion;
outline-coverage gaps and softer heuristic hits produce a structured per-source QA report consumed
during the developer's existing manual skim step — no new workflow, a pre-triaged one.

**Corpus freshness / edition pinning**: spec source records carry `custom.edition` +
optional `custom.edition_check_url`; a quarterly lightweight edition-check job (plain page fetch,
no re-ingestion) opens a triage queue entry on mismatch, never auto-reingests. Adopting a new
edition ingests it as a new versioned `source_id`, tombstones the old one via
`custom.superseded_by`, and fires a new `edition-superseded` freshness-staleness trigger riding
D25's existing event-driven re-verification queue.

**Scheduled link-checker**: a monthly job over URL-locator sources only (book/repo locators are
immune by construction), checking resolution, anchor presence, and content-hash drift as three
independent signals. Content drift feeds D25's already-designed `snapshot-drift` trigger directly;
dead links and anchor drift get their own sibling reason codes. A dead live link never
retroactively unverifies a fact already verified against its archived snapshot — it only queues
the citation for possible future repair.

**Source-acquisition queue**: a single private `sourcing_queue` log, entries typed by reason
(`not-ingested | partially-ingested | paywalled | access-pending | acquisition-failed`), tracking
`bounce_count` against D24's existing 2-bounce budget and `age_days` against its existing 14-day
alarm. Automatic re-filing into the verifier's stage-1 queue the moment a cited source becomes
ingested. Genuinely inaccessible sources stay visibly parked indefinitely, never silently dropped.

**Corpus/mirror-integrity distinction**: a new `custom.canonical_source` flag (orthogonal to D3's
evidentiary `tier`) with preference for official publishing-body URLs at ingestion time, a
mandatory `custom.acquisition_note` for every non-canonical source (CI-enforced presence, not
truth), and explicit reliance on the existing D24/D25 multi-source verification and corroboration
machinery as the structural backstop rather than a bespoke detector. The residual risk of a
single-sourced claim with no second source to catch a stealth error is named, not solved. Full
analysis: [brainstorms/28-locator-normalization-ingestion-qa.md](brainstorms/28-locator-normalization-ingestion-qa.md).

*[developer]* Ratified with: **quarterly edition-check cadence confirmed as proposed** — no
per-language cadence tracking. **The R1 initial-corpus ingestion gets a one-time retroactive pass**
backfilling `canonical_source`/`acquisition_note` before the flag becomes load-bearing for later
sources (not binding only going forward). **No additional confidence ceiling for single-sourced
claims** — D25's existing tier×corroboration-count confidence model already covers the
mirror-integrity residual risk; not worth a bespoke mechanism. **A single retry is sufficient**
before flagging `link_status: dead` — no "confirm dead across N consecutive monthly runs"
dampener, given a wrongly-flagged dead link only costs a staleness badge. **A silent no-op is
acceptable** for the outline-coverage check on sources with no machine-readable outline — no
explicit "outline-coverage: not applicable" marker needed in the QA report.

### D38. Ontology change tooling (29)

Mechanical blast-radius script (`--kind ontology-node|source`) computes direct/indirect fact
references, affected URLs, D26-cost-log-derived re-verification cost, and downstream artifact
touch counts, then drafts a starting `fact_remap` list using each D16 casebook row's default
disposition (split→requeue, merge→remap/fast-path, move→requeue only for
classification-asserting facts, removal→tombstone) — fully editable afterward, never a blank
form. A fifth GitHub Issue Form (matching D32's pattern) captures the RFC with a `change_type`
dropdown routing to the right casebook row and a required dissenting-evidence field; the
committed `impact.md` splits into an auto-generated section (CI diff-checked against a fresh
blast-radius run) and an authored rationale section. The migration-manifest gap D16 left open is
closed by a typed `op` disposition DSL (`split | merge | move | remove`, one-to-one with D16's
casebook rows) carrying a `fact_remap` list of matcher→action entries from a closed four-action
vocabulary (`remap | requeue | tombstone | untouched`); `migrate.py` becomes a thin shared
interpreter over the manifest rather than bespoke per-migration Python. Migration-triggered
tombstones extend D23's existing `tombstones.yaml` (one added `migration_id` field) instead of a
parallel ledger; one shared chain-walking resolution routine (depth-capped) serves both the
Astro build (static never-404 tombstone pages, hub pages for splits per D16's URL policy) and
the MCP server (`get_fact`/`get_feature`/`get_neighbors` on a dead id return a structured
`{status: superseded, successor(s), chain}` object with resolved successor content inline,
wrapped in D35's mandatory caution-block contract). Ontology diff visualization is a build-time
static diff table/tree (nodes added/removed/renamed/split/merged/moved, fact-disposition
counts) — an interactive graph-diff library is explicitly rejected as disproportionate at
low-hundreds-of-nodes/~monthly-MAJOR scale — generated once and reused for both RFC review and a
public `/changelog/ontology/<migration-id>/` page.

Topic 28's `edition-superseded` source-registry tombstone folds in as **structurally the same
shape, one level up**: `sources/_tombstones.yaml` reuses the identical `op`/`fact_remap`/action
schema, adding one new op (`supersede`, source-scoped) and one new action (`flag-stale` — the
only action that never touches fact content/id/verification status, matching D37's
"never retroactively unverifies" rule), written automatically by D37's quarterly edition-check
job with no RFC and no human gate. The governance split lives in *where the ledger is and who
writes to it* (RFC-gated `ontology/migrations/` vs. job-triggered ungated
`sources/_tombstones.yaml`), never in a second parallel schema. Full analysis:
[brainstorms/29-ontology-change-tooling.md](brainstorms/29-ontology-change-tooling.md).

*[developer]* Ratified with: **blast-radius script scope stays as proposed** — scoped to
facts/edges/rules per D16's original blast-radius definition; `source_chunks`, debate records,
and chat logs are not counted (revisit only if that broadening is separately greenlit, per the
topic-32 fold-in note already on the checklist). **`action: untouched` is an allowed implicit
default** — CI does not hard-require every blast-radius-discovered fact anchor to appear
explicitly in the submitted manifest's `fact_remap`. **Ontology changelog page: one static page
per migration** under `/changelog/ontology/<id>/`, in its own top-level site-IA slot (not folded
under an existing docs/about section). **`get_feature` on a split's old node id returns the hub
content directly**, in the normal feature-object shape — not wrapped in the `{status:
superseded, ...}` envelope `get_fact` uses for dead fact ids, since a hub page has real content
rather than being a dead reference. **`get_source` auto-walks to the latest edition
transparently** on a multi-hop supersession chain, matching the existing chain-walk resolution
routine, rather than stopping at the first hop. **No mechanical CI/bot enforcement of the RFC
objection window** — worth naming as considered, not worth building; stays trusted to the
developer's own process discipline, consistent with D16 O5b's developer-run-checklist framing.

### D39. Cross-cutting concern modeling (30)

Adds one new field, `exclusivity: exclusive | multi`, to each dimension record in
`ontology/taxonomy/dimensions.yaml`, defaulting to `exclusive` so every currently tree-shaped
layer-3 dimension (memory management strategy, evaluation strategy, type-system strictness, …)
needs zero edits. D2's dimension-exclusivity validation level reads this field: `exclusive`
enforces today's at-most-one-feature rule unchanged; `multi` skips the check entirely, letting
any subset of the dimension's features co-occur. Deliberately no partial/counted mode
("at most 2 of 4") — anything more nuanced than one-of/any-of is pushed to Rule entities (D2
level 4) instead of growing the dimension-exclusivity check into a constraint mini-language.
D16's `cross_cutting: true` feature-level flag is unchanged and stays pure metadata (site
badging, RFC triage), lint-checked for agreement with its home dimension's `exclusivity` rather
than doing validation work itself. The other three D2 combination-validation levels (hard
pairwise requires/conflicts, soft influences, Rules) need **no change** — they were already
feature-pairwise/feature-set machinery, never dimension-shaped, so cross-cutting features
interact with them exactly like any other feature today.

Resolves D16 O6's flagged Exceptions collision: the brief's literal `Exceptions:
checked/unchecked/effect-system` layer-3 dimension is a mis-specified `exclusive` dimension
(languages accumulate exception mechanisms, they don't pick one) that should be renamed "Error
handling mechanism" and marked `exclusivity: multi`; the deliberately-excluded "Exceptions"
Concept (D16) remains the pedagogical parent the atomized mechanism-features
(`checked-exceptions`, `result-type-error-handling`, `panic-unwind`, …) eventually link under via
`realizes`, per D16's existing Concept-first-staging-then-atomize path. No ontology content has
been minted yet (the research phase hasn't started), so this is a pre-emptive schema fix to land
before the first layer-3 dimension is authored, not a corrective migration — landing this field
is what would let a later `exclusive → multi` correction be an ordinary MINOR-cost dimension
flip under D16 rather than a forced MAJOR. Full analysis:
[brainstorms/30-cross-cutting-concern-modeling.md](brainstorms/30-cross-cutting-concern-modeling.md).

*[developer]* Ratified with: **the explicit `dimensions.yaml`-level `exclusivity: exclusive |
multi` field confirmed as proposed** — not inferred from feature-level `cross_cutting`, so the
rule stays legible straight from `dimensions.yaml` without cross-referencing every feature file
(the lint-checked agreement between the two fields stands as designed). **"Error handling
mechanism" confirmed as the renamed dimension label.** **`multi`-exclusivity dimensions get
visually distinguished from `exclusive` ones on the feature-matrix/coverage pages** (topics
19/44) — not deferred as a later site-IA-only decision; folded into topic 19's checklist entry
since it already owns trust-signal/matrix-component UX. **The no-partial-exclusivity stance
("anything more nuanced than one-of/any-of is a Rule entity's job") is confirmed as the
permanent stance** — no cross-cutting concern currently needs a genuinely counted constraint at
the dimension level. **The stated scope boundary is confirmed correct**: this topic does not
design topic 52's Builder-side consumption of `exclusivity`, nor topic 29's migration tooling for
the eventual Exceptions restructure — both stay pointers, no sketch needed here.

### D40. Brand identity & launch positioning (31)

**Positioning statement**, three nested lengths for three surfaces, all saying the same two
things in D19's order (typed graph first, per-fact sourcing second): a 3-sentence hero paragraph
("LangAtlas maps programming-language features as a typed graph... Every fact in that graph is a
single sourced claim, checked against its cited source by an independent verification pass...
Where PLDB trades depth for breadth and Hyperpolyglot trades sourcing for speed, LangAtlas is
narrower on purpose") for the homepage/about page; a compressed 1-sentence derivative for
character-constrained surfaces (meta description, OG images); D17's existing tagline as the
shortest form underneath both. Names PLDB and Hyperpolyglot honestly by their real strengths
(breadth/structured metadata; fast lookup) rather than strawmanning either.

**HN/lobste.rs launch framing**: title foregrounds the typed graph + sourcing claim
(independently checkable by any reader who clicks through), not the AI-agent-pipeline angle. The
"agents wrote this" disclosure moves to the first or second sentence of the body, framed as *why*
the sourcing claim is credible ("there's no human review gate, the citation check *is* the
gate") rather than a confession — omitting or burying the disclosure is rejected as inconsistent
with D1's own no-PR-gate architecture and more likely to backfire if discovered than disclosed.
lobste.rs gets the same disclosure-up-front structure but shifts relative emphasis toward the
ontology/typed-graph/versioning design given that community's PL-theory density.

**Wordmark/logo**: ship wordmark-only (no icon) for the actual launch — a standard open-source
geometric/humanist sans, monogram favicon — deferring a parametrically-generated isogloss-line
SVG mark (two-to-three open Bézier contour-line paths, matching real dialectology-map
conventions, built as a small reproducible script under version control) to a fast-follow once
there's slack to iterate on it properly. A commissioned custom logo is rejected outright against
the solo-maintainable, no-cash-budget constraints.

**Accent color**: warm amber/ochre as the single accent hue (a concrete starting range,
`#B5540A`–`#C9691A` light-mode / `#E8A33D`–`#F0AE4A` dark-mode, exact hex values left to an
implementation-time contrast audit) — the real ink color used for contour lines/isoglosses on
topographic and dialectology maps, distinctive against the generic dev-tool-blue default, and
avoiding the LangChain blue/violet brand-association risk D17 already flagged.

**OG-image templates** (visual design for the mechanism D33 already fixed): three templates —
feature/language (shared skeleton, swapped headline/subhead content), comparison (two-column
skeleton with an accent-color center divider deliberately echoing the isogloss-crossing
metaphor), and homepage (tagline + wordmark, centered) — on a shared warm-paper visual language
(thin accent-color rule, small corner mark once built, bottom-corner wordmark + compressed
tagline). No live-changing numbers or status glyphs on any template, generalizing D33's
citation-count-glyph omission to every numeric field to avoid staleness between a static image
and a live page. Full analysis:
[brainstorms/31-brand-identity-launch-positioning.md](brainstorms/31-brand-identity-launch-positioning.md).

*[developer]* Ratified with: **the positioning paragraph needs one cut before it's usable
verbatim**: drop the explicit named comparison against PLDB and Hyperpolyglot ("Where PLDB
trades depth for breadth and Hyperpolyglot trades sourcing for speed...") from the hero
paragraph — the rest of Option A's wording (graph-first, sourcing-second, "narrower on purpose")
stands. **HN/lobste.rs title-vs-body disclosure split (Option B) confirmed** as the right,
appropriately conservative framing — graph/sourcing in the title, AI-pipeline disclosure in the
opening body sentence. **Wordmark-only launch (no icon at all) confirmed acceptable**, deferring
the isogloss-line mark to a fast-follow. **Warm amber/ochre accent-color direction confirmed.**
**OG-image numeric fields: omit entirely, as recommended** — no build-time-stamped count field.
**Domain/org registration timing: no trigger tied to this topic's completion.** Registering
`langatlas.dev` and confirming the `langatlas` GitHub org remains unplanned and will happen only
on the developer's own independent decision, not gated on positioning/launch-post/wordmark
readiness — the `open-questions.md` deferred item's "trigger" language is superseded by this:
there is no trigger criterion, only developer discretion.

## Batch 32, 33, 35 decisions (2026-07-19 — from brainstorms 32, 33, 35 — **ratified by the developer**, amendments noted inline)

### D41. Pipeline observability & prompt registry (32)

No new service or live dashboard: a CLI tool `tools/observability/report.py` (subcommands
`cost`, `verifier`, `debates`, `sourcing-queue`, `capabilities`, `verifier-drift`) reads directly
from the D18 transcripts repo, the D26 cost log, and the private build-side verification ledger
(D23); output is ephemeral markdown, never committed as canonical data (D35's bundle manifest
already covers the one legitimately public number — verifier error rates). **Prompt registry**:
`prompts/<prompt_id>/v-<8hex-content-hash>.md` files in the kb repo, content-addressed versions
(mirroring D16/D23's immutable-id pattern) with a human-readable alias in a per-prompt
CHANGELOG; new versions trigger a soft (log-only) regression-fixture re-run check under topic
40's validator. **Capability table**: `config/provider_capabilities.yaml`, updated by a
manual/periodic `probe_capabilities.py` that diffs and flags drift rather than auto-committing.
**Claude usage-limit telemetry**: a typed reactive `ClaudeLimitSignal` (no proactive quota API
exists on Pro) raised by the Claude channel of `RunContext`, logged per D18, distinguishable from
self-imposed D26 budget stops — handed to topic 35 as an interface, not solved here.
**`provenance.candidate_source` (D29)**: no broader "why did the pipeline look here" model
needed — D18 transcript logging already gives the full trace via `chat_run_id`; D29's field
stays the sufficient per-fact summary. **Verifier-replay counterfactual reuse**: one shared
library function `replay_verdict` used both by topic 16 (single-draft debate instrumentation)
and this topic (bulk verifier-drift reporting). **Unified sourcing work queue**: one
`sourcing_queue` table with a `kind` discriminator spanning pending-source/link-checker/
edition-check entries, written by the three existing jobs, read by one report subcommand.
**Topic 29 interface**: only a join-key compatibility note (`chat_run_id`/`source_id`/`run_id`),
no design now. Full analysis:
[brainstorms/32-pipeline-observability-prompt-registry.md](brainstorms/32-pipeline-observability-prompt-registry.md).

*[developer]* Ratified with: **`report.py` output stays purely ephemeral** (stdout, optionally a
gitignored local snapshot) — no periodic reports committed anywhere, beyond what D35's bundle
manifest already publishes. **Content-hash-addressed prompt versions (§2.2 Option B) confirmed**
over plain sequential integers. **The stale/missing regression-check gate stays a uniform soft
gate everywhere** — no special hard-block carve-out for unattended overnight batches specifically,
matching D30's existing stance. **Capability-probe cadence: monthly**, run by
`probe_capabilities.py` on that schedule (via topic 35's scheduler) rather than only on-demand
before batches. **The reactive-only `ClaudeLimitSignal` is sufficient** — no proactive heuristic
attempted, given there is no quota API to calibrate one against.

### D42. Licensing follow-ups (33)

Four operational artifacts D14 deferred to their own brainstorm, none reopening D14's legal
analysis: **attribution rendering** — a site-wide BY-SA footer notice + `/license/` explainer page
+ per-page JSON-LD `license` field (distinct from D3/D10's existing per-fact citation popovers,
which handle § 31 quotation-attribution of *cited sources*, not LangAtlas's own BY-SA notice as
licensor); MCP tool descriptions state the BY-SA reuse obligation once per session (mirroring
D35's `caution`-block pattern), plus a structural `attribution` field on every fact object
alongside D35's `caution` block. **Takedown/complaint runbook** — a published email address as the
primary intake channel (plus an optional `legal-complaint.yml` GitHub Issue Form alongside D32's
four), triaged solo by the developer into legal-vs-not-legal, default safe action is unpublishing
the contested quote/excerpt (never the underlying fact, restating D14/15 §R8), "takedown" means an
ordinary forward-fixing commit except for genuine severity, which reuses D18's existing
`REDACTIONS.md` force-push escape hatch (already scoped to cover copyright incidents) rather than
a new mechanism; D14's existing lawyer-trigger list is the unchanged escalation line. **Dataset
export attribution** — one additive `license` field threaded through D35's `manifest.json`, a
companion `NOTICE.txt` Release asset, and the same field in the D35 loader's `_meta` table — no
bundle redesign. **Transcript-corpus licensing** — `langatlas-transcripts` (D18) gets its own
license, proposed **CC0 1.0**, distinct from the corpus's CC BY-SA 4.0: transcripts are audit
trail rather than product (D24's own framing), carry a thin-to-nonexistent original copyright
claim (US no-human-authorship doctrine), and CC0 directly serves the eval/training-set reuse case
the checklist names, which a share-alike obligation would otherwise complicate. Third-party
copyrighted excerpts embedded in transcripts remain governed by their original rightsholder
regardless of LangAtlas's own license choice either way. Full analysis:
[brainstorms/33-licensing-follow-ups.md](brainstorms/33-licensing-follow-ups.md).

*[developer]* Ratified with: **CC0 1.0 for `langatlas-transcripts` confirmed**, distinct from the
corpus's CC BY-SA 4.0, as proposed. **A published project-alias email as the primary
takedown-complaint channel, with `legal-complaint.yml` as the GitHub-native alternative,
confirmed** — no single-GitHub-only channel. **`REDACTIONS.md`'s existing category taxonomy gets
broadened to explicitly cover takedown-driven history rewrites, confirmed** — no sibling
`TAKEDOWNS.md` log. **Attribution name: "LangAtlas contributors"** confirmed for the footer/
JSON-LD/MCP/`NOTICE.txt` strings. **No stated acknowledgment-SLA number** — the takedown runbook
stays purely best-effort, with nothing to point to if missed (over the proposed 5-business-day
figure).

### D43. Run orchestrator & checkpointing (35)

A thin driver library, `tools/orchestrator/driver.py`, no daemon: one generic loop (enumerate
work items → call into the D26 provider layer / D36 commit protocol → interpret the typed result
→ checkpoint → continue/pause/halt), parameterized per job by a small batch-spec YAML in
`config/jobs/` (`kind`, `work_item_source`, `budget`, `checkpoint_path`). One driver invocation =
one `RunContext`-scoped run; adding a job kind is one enumerator function + one YAML file, not a
new subsystem. **Checkpoint unit** is whatever grain each job's own work-item source already
enumerates (sweep cell, R3/R4 theme, fact, source) — no forced global granularity. **Checkpoint
storage**: a local, private, non-git SQLite file in the same private tier as D26's cache/cost log
(`orchestrator_checkpoint`, one row per (run, item)); this is driver-level bookkeeping only — the
`LangAtlas-Record-Key` git trailer (D36) stays ground truth for "did it actually land," looked up
before re-attempting anything not cleanly marked `done`, so checkpoint state and repo state can
never disagree even if the checkpoint file is lost. **Budget hard-stops**: `RunContext` raises a
typed `BudgetExceeded` signal before crossing a declared cap; the driver checkpoints the in-flight
item as `blocked` (still valid, re-attemptable) and exits with a distinct code; resume is plain
re-invocation of the same command, no separate resume mode. **Claude usage-limit handling**: on
D41's `ClaudeLimitSignal`, apply a conservative fixed cool-down (proposed 4 hours, no calibration
data exists yet) before any resume attempt; a too-early re-invocation no-ops. "Alerting" is the run
halting plus two cheap surfaces — standard cron mail and a small `orchestrator/status.json` (one
more `report.py` subcommand) — no bespoke notification service, matching the project's no-new-infra
posture. **Scheduling**: plain cron on the developer's machine, one line per job (nightly
verification/controversy batch, monthly link-checker, quarterly edition-check, an 18-month
backstop sweep whose own logic no-ops until due), each invoking the same driver against a
different batch spec; a committed `config/jobs/crontab.example` documents intended cadence, the
developer's real crontab stays local machine state. Full analysis:
[brainstorms/35-run-orchestrator-checkpointing.md](brainstorms/35-run-orchestrator-checkpointing.md).

*[developer]* Ratified with: **the per-language sweep pipeline (D5) stays always
developer-initiated by hand**, never run unattended via cron — unlike the background jobs (nightly
verification, monthly link-checker, quarterly edition-check, the 18-month backstop), which do run
via cron per §2.5. **The proposed 4-hour Claude-limit cool-down is confirmed as a reasonable
starting default** — no sharper instinct from prior usage-limit experience to replace it with.
**Cron mail (`MAILTO`) is not needed** — the `orchestrator/status.json` + manual `report.py`
check-in is the only alerting actually intended; cron-mail setup is not worth documenting.
**A committed `config/jobs/crontab.example` is worth maintaining.** **The 18-month backstop
sweep's "checked monthly, no-ops until due" pattern is confirmed** as matching the developer's
expectation, over a coarser manually-remembered trigger.

*[developer 2026-07-20]* **Full periodic-job inventory** (the list above predates several later
ratifications; `config/jobs/crontab.example` must enumerate all of these): nightly
verification/controversy batch; monthly link-checker (D37), capability probe (D41), finding-aid
mirror refresh (D53), and Umami `demand` export (D52); quarterly edition-check (D37); the
18-month backstop sweep. Event-driven work (the D59 contradiction scan, D25's re-verification
triggers) rides commit/pipeline events, not cron.

## Batch 36 decision (2026-07-19 — from brainstorm 36 — **ratified by the developer**, amendments noted inline)

### D44. Golden-set authoring methodology (36)

One shared perturbation taxonomy — 13 named strata (correct, overstated claim, fabricated
locator, wrong `since` off-by-one and wrong `since` off-by-major — two distinct strata —
contradicted, right-claim-wrong-source, category
error, fabricated feature-instance combination, quote-mismatch, quote-found-elsewhere, OCR-noisy,
paraphrase-heavy correct) — reused across the D24 verifier golden set's authoring, with the
**overstated-claim stratum treated as first-class and reported separately**, since it is the only
stratum that exercises the `partial` verdict's intended meaning and the K1 laundering defense.
Construction: LLM-generated candidates (volume, decorrelated from the verifier model) curated by
the developer during R1 QA skims (quality); target composition ~40% correct / 60% wrong-stratum,
overstated-claim and wrong-`since` over-weighted. **Contamination defense** is primarily
structural: perturb toward counterfactual, specifically-invented wrongness (invented version
numbers, swapped similar-language attribution, altered page/section loci) rather than "famous
facts stated wrong," supplemented by obscure-locus targeting, the existing D24 cross-family
sample repurposed as a passive contamination gauge, and a small (~10–15 item) fully-developer-
authored held-out slice for occasional manual audits; no dedicated red-teaming role (matches
D31's disproportionality precedent). **Hand-labeled controversy cases**: keep D25's ~50-case
target, reached via a bootstrap lane (~15–20 synthetic structured-input cases authored at project
start) plus an opportunistic lane (D25's own Claude-escalation-review process already produces
real hand-labeled cases as a byproduct); genuine field-dispute cases minted opportunistically as
the corpus acquires opposing tier-A/B literature, not on a schedule; cases carry
`ontology_version`/`prompt_version` tags, staleness-checked (not migration-gated) by topic 40's
validator. **Retrieval golden queries**: derived-first from the verifier golden set's own
correct-stratum `(claim, locator)` pairs (shared bootstrap corpus, not duplicated authoring),
supplemented by dedicated hand-authoring (developer, R1 QA skims per D27) for the paraphrase and
cross-source difficulty bands the derivation can't produce. **Topic-16 join**: a sibling
`tests/golden/` directory (`verifier/`, `controversy/`, `retrieval/`, `debates/`), scored/
threshold-gated (vs topic-16's diff-reviewed `tests/fixtures/providers/regression/`); the
verifier golden set reuses D41's `replay_verdict` as a third consumer; the deferred debate-outcome
golden set (D30's Option B) becomes this topic's responsibility once phase-1 debate volume exists.
**Public benchmark**: stretch goal, not a near-term commitment — ship D24's already-ratified
"publish measured error rates" now; if pursued later, use a public-sample + private-held-out-slice
split (contamination mitigation) with CC0 1.0 licensing matching the `langatlas-transcripts`
precedent (D42). Full analysis:
[brainstorms/36-golden-set-authoring-methodology.md](brainstorms/36-golden-set-authoring-methodology.md).

*[developer]* Ratified with: **O1's LLM-generated-candidates + developer-curated-selection split
confirmed as proposed** — no fully-manual authoring pass for the overstated-claim stratum
specifically. **Counterfactual construction confirmed as the primary contamination defense**,
with the ~10–15 item held-out audit slice size accepted as proposed (not sized larger). **D25's
~50-case controversy golden-set target and the bootstrap + opportunistic sourcing hybrid
confirmed** — no firmer near-term floor forcing all ~50 cases authored before R3/R4 debates
start. **Retrieval golden-query derivation confirmed as proposed**: derive the majority of
exact-term/paraphrase bands from the verifier golden set's own citations, hand-authoring
reserved for paraphrase-hard and cross-source queries only. **`tests/golden/` fixture directory
placement confirmed** as proposed, sibling to topic-16's `tests/fixtures/providers/regression/`.
**Public-benchmark posture confirmed as stretch-goal/not-now** — no need to scope the
public-sample/private-holdout split or a `public-eligible` tagging convention in advance.
**Golden-set staleness enforcement is a soft/log-only flag**, mirroring D41's soft-gate stance on
topic-16's regression-fixture staleness checks — not a CI hard-fail.

## Batch 37 decision (2026-07-19 — from brainstorm 37 — **ratified by the developer**, amendments noted inline)

### D45. Contradiction-register lifecycle (37)

Splits D5's "contradictions are first-class records" policy and D24's `contradicted` verdict into
**two record types sharing one schema**: `type: verification` (a fact vs. one of its own
citations — low-severity, mechanical, minted by the D24 verifier only when the fact stays
admissible via a different citation; a contradicted primary/only citation blocks admission
outright and never mints a record) and `type: cross-fact` (two independently verified facts
disagreeing — the rare, high-severity case D5 originally meant, and what D25's controversy level 3
and the site's disputed glyph actually refer to). Minting is restricted to three mechanical
sources — the D24 verifier, the D5 reconciler/debate outcome, and human-challenge resolution
sessions — plus a proposed (not yet designed) periodic cross-fact scan job to catch conflicts
between facts admitted in different pipeline runs; the controversy assessor never mints records
itself, preserving its D25 structured-input-only lane. **Identity is content-keyed**
(`ctr-<12-hex SHA-256>` over sorted participant fact ids, or fact+citation for verification-type),
mirroring D23's fact-id scheme so concurrent no-PR-gate processes dedup automatically. **Storage**:
one root-level `contradictions.yaml`, sibling to `tombstones.yaml`, mutable `status` field (git
history is the audit trail). **Closure**: an automated since/version-qualification check at mint
time closes the D5-named common case immediately (`status: dissolved`) with no visible dispute
state; auto-closure on participant correction via a tombstone cross-reference; human-challenge
adjudication (qualify, correct, or explicitly confirm-as-genuinely-open); indefinite `open` status
is the correct default for genuine field disagreement, re-checked only on new-source-ingestion
events — never forced closed. Closed records are never deleted; the live `dispute` axis (D25) is
always a derived read of currently-open records only. **`partial` verdicts do not mint
contradiction records** — corrects the checklist topic's own phrasing, since `partial` and
`contradicted` are mutually exclusive under D24's own decomposition fold rule; partials get their
own filterable build-side log per D24's existing ratification. **Site**: verification-type records
add one short clause to the existing D25-axis popover line; cross-fact records get a compact
"Sources disagree" block inside the same popover, both riding brainstorm 19's shared base-page
glyph with no new page chrome; a dedicated `/disputed/` index of open cross-fact records is
proposed as a content/positioning opportunity, left open. **MCP**: `get_fact` on a `dispute:
contradicted` fact inlines the conflicting participant fact(s) in full (mirroring the D35/29
tombstone-inlining precedent), each with its own `caution` block; a proposed
`list_contradictions`/`get_contradiction` read-only tool pair would extend D8's set. Full analysis:
[brainstorms/37-contradiction-register-lifecycle.md](brainstorms/37-contradiction-register-lifecycle.md).

*[developer]* Ratified with: **the core `verification`/`cross-fact` type split (O1b) confirmed**
as matching the developer's own intuition for what "a contradiction" means on this project.
**`partial`-verdict exclusion from the register confirmed** — `partial` and `contradicted` stay
mutually exclusive per D24's fold rule, with partials living in their own filterable log. **The
proposed periodic cross-fact contradiction-scan job (O3.3) is an acceptable future pipeline
component** — already tracked as backlog topic 56, not designed further here. **A dedicated
`/disputed/` page is declined** — stays popover-only indefinitely, per D10's minimal-surface-area
ethos, over building it as a content/positioning feature. **Since/version qualification check
scope (O4 path 1) stays at v0's `since`/`status` comparison only** — not extended to other
structured scoping fields (dialect/edition, platform) for now. **Human-challenge-confirmed-open
contradictions (O4 path 3b) carry more weight in the controversy assessor's rubric** than a
machine-discovered, never-human-reviewed contradiction — the assessor's rubric should read
`closure_attempt.outcome: confirmed-open` as stronger evidence toward level-3 `disputed` than an
unreviewed open record. *[Withdrawn 2026-07-20 — see the dated note below.]* **MCP tool
extension confirmed as part of this topic's implementation**:
`list_contradictions`/`get_contradiction` (O7) ship now rather than deferring to a future
D8-extension pass — consistent with backlog topic 57's standing tracking note, which stays open
only for consolidating the *rest* of the extended tool list (D15's `search_sources`/
`get_source_section`), not this pair.

*[developer 2026-07-20]* The confirmed-open-weighting clause above is **withdrawn**: no
human-challenge-derived result — including a contradiction record's
`closure_attempt.outcome: confirmed-open` — may serve as a controversy-assessor input. D21/D25's
challenge-free rubric holds without exception; open contradiction records feed the assessor only
through their machine-produced content.

## Batch 38 decision (2026-07-19 — from brainstorm 38 — **ratified by the developer**, amendments noted inline)

### D46. Questionnaire compiler (38)

A real, deterministic code tool, `tools/questionnaire/compile.py` (matching the "small Python
CLI, no daemon" shape of D38's blast-radius script and D41's `report.py`), turns the ontology
tree into the D5 sweep questionnaire — never a hand-maintained document (which would drift the
moment either source of truth changed without a human remembering to touch the other) and never a
live per-sweep re-derivation (which makes drift undetectable after the fact). **Fact-bearing vs.
structural line**: the compiler emits sweep items only for D23's four FeatureInstance fields
(`exists`/`since`/`characteristics`/`syntax`); everything ontology-authored (feature/edge/rule
existence, edge polarity, `affects-quality` assessments, dimension `exclusivity`, `layer`,
`cross_cutting`) is never re-asked per language — hard `requires`/`conflicts-with` edges and
`rules/*.yaml` instead compile to a separate `constraints:` list the reconciler validates sweep
answers against, never rendered as questions themselves. **Schema**: per-dimension grouped items
(carrying the group's `exclusivity` context once, per topic 30's field) plus standalone flat items
for layer-1/2 features outside any dimension; every item's `anchor_prefix` matches D23's
`fi.<lang>.<feature>` anchor scheme so compiled items and derived facts share vocabulary by
construction. **Algorithm**: six mechanical steps over `features/`, `taxonomy/dimensions.yaml`,
`edges/**`, `rules/*.yaml` — no judgment calls inside the compiler, which is what makes "compiled"
a meaningful guarantee. **Drift prevention** is structural, not procedural: the questionnaire is
never independently-editable state, so there is nothing to fall out of sync by omission —
extending D23's "facts are build artifacts" and D26's "computed once, shipped as data" precedents
one layer up the pipeline; a schema-shape regression fixture (shared pattern with D26/D30) guards
the rarer schema-vocabulary-drift mode. **Handoff contract**: every compiled spec is stamped with
the `ontology_version` it was compiled from (no independent questionnaire semver in v0); every
sweep-run manifest records which spec version it answered, mirroring D26/D35's version-provenance
pattern. In-flight-answer disposition after a later ontology migration reuses D38's existing
migration-manifest disposition DSL applied to FeatureInstance records — this topic's only new
deliverable is a **delta-questionnaire diff** (`compile.py`, diff two spec versions by
`anchor_prefix`) feeding D38's `fact_remap` requeue list. **Operational placement**: on-demand,
invoked at R6/first-sweep-launch and at the start of each subsequent D28 onboarding phase (plus ad
hoc whenever a migration touches previously-compiled nodes), as one more `config/jobs/` entry for
D43's driver — never continuous/cron-triggered, matching D43's "sweep launches stay
developer-initiated by hand" ratification. Full analysis:
[brainstorms/38-questionnaire-compiler.md](brainstorms/38-questionnaire-compiler.md).

*[developer]* Ratified with: **language-agnostic spec confirmed, no per-language
candidate-feature filtering** — filtering up front would make the compiler render a judgment
call about a language before any evidence exists, contradicting D23's "absence is a sourced
fact, not a skip" principle. **Constraint violations route into the existing D5 conflicted-cell
debate machinery unchanged** — no separate resolution path or auto-flagging of the
ontology-level edge/rule itself. *Amended 2026-07-20 (D61): superseded* — a `constraint-disputed`
debate outcome now does auto-flag the edge/rule itself via an RFC-issue work-queue item; see D61.
**Delta-questionnaire requeue scoped to exactly the changed
anchors** (minimal re-ask), not the whole dimension group. **`questionnaire_schema_version` stays
deferred** until the compiler has shipped at least one real version — not stubbed in now the way
D35 stubbed in `bundle_schema_version`. **Compiled questionnaire spec output is a committed
artifact** (visible in git history, diffable across ontology versions) — the opposite of D41's
`report.py` ephemeral-output precedent — with no directory-location preference specified beyond
`tools/questionnaire/`'s existing output path.

## Batch 39, 40, 41 decisions (2026-07-19 — from brainstorms 39, 40, 41 — **ratified by the developer**, amendments noted inline)

### D47. Fact statement templating (39)

Concretizes D23's "canonical claim phrasing as fixed per-kind templates over node ids," which
was never given a concrete home. **Template catalog**: a new sibling registry
`ontology/claim-templates/<kind>.yaml`, one file per brainstorm-09 §O6 claim kind, each carrying
a frozen `claim_pattern` (the S-expression grammar, documentation/CI cross-check only) plus an
editable `render:` block (the English wording), versioned with the same content-hash pattern
D16/D23/D41 already use — deliberately a separate artifact family from D41's `prompts/` LLM-
instruction registry, since claim rendering is pure deterministic string interpolation with no
model call in it at all. **Change management** splits on the file's two blocks:
`claim_pattern` edits are ontology-schema surgery routed through D16/D38's existing migration
machinery (no new format invented); `render:` (wording-only) edits are **always re-rendered**
(free, automatic, every build — `rendered_text` is already a precomputed D35 bundle column),
**blast-radius-surfaced before re-embedding** (extending D38's blast-radius script to `--kind
claim-template`, the exact broadening D41 §2.8 already anticipated, so the developer sees an
affected-fact count before a batch re-embed runs — no hard gate, cost stays governed by
D26/D35's existing cache/budget machinery), and **never trigger re-verification** (the D24
verifier certifies the underlying claim, which a wording-only edit never touches, per O6's
"claims never derive from renderings" rule) — scoped to the five templated claim kinds only;
free-text kinds (`characteristic`, `syntax-valid`, a `quality-assessment`'s `statement:`) already
have D23's copyedit-tolerant-hashing answer and don't need this machinery. **Sampling-parameter
provenance** resolves as a category error in the checklist's framing, not an unanswered
question: the template-rendering layer makes no model call, so there is no sampling to attribute.
The real gap (from brainstorm 13) is a small optional `sampling: {temperature, top_p, seed}`
sub-block added to brainstorm 09 §O4's existing per-record `provenance:` schema, populated only
for LLM-drafted claims that deviated from pipeline defaults (mirroring D26's omit-when-default
convention). Full analysis:
[brainstorms/39-fact-statement-templating.md](brainstorms/39-fact-statement-templating.md).

*[developer]* Ratified with: **D38's blast-radius script itself gets extended** to accept `--kind
claim-template` rather than building a bespoke smaller script. A `render:` wording edit's
blast-radius count **folds into the existing scheduled re-embed cadence** (still TBD per D27's
deferred fact-index embedding-model decision) rather than getting its own on-demand "re-embed now"
trigger. The `sampling:` sub-block **populates only when it deviates from pipeline defaults**, as
originally drafted. **`quality-assessment` gets a split identity**: a templated existence-claim
plus a free-text statement-claim, per O6's own claim-pattern example showing both are true at
once — it does not fit cleanly into either the templated-kinds or free-text-kinds bucket alone.

### D48. Validator/normalizer CLI (40)

Closes out five prior brainstorms' fold-in notes (09, 27, 28, 29, 38) in one pass. **Structure**:
a library-first Python package `tools/validate/` (module `langatlas_validate`) with a thin
`cli.py` dispatching to plain, independently-importable functions — resolving the tension between
"one shared tool" and "callable inline from the D24 verifier's batch loop, not via subprocess."
Three call-site contracts: `langatlas-validate precommit <files...>` (fast, scoped to touched
files + direct referential neighbors, phase-1-only locator check by default, refuses to commit on
nonzero exit per D36); `langatlas-validate ci` (full corpus scan, phase-2 locator resolution,
fact-id collision check, migration-manifest validation, full regression run); and `from
langatlas_validate.locators import validate_locator` imported directly inside the verifier's
stage-2 step, called with the verifier's own already-open `source_chunks` index handle.
**`validate_locator`** (D37/topic 28's named routine) is two-phase: `validate_locator_shape`
(pure regex-shape check against brainstorm-09's grammar table, zero I/O, always run) and
`validate_locator` (shape + `source_chunks` resolution, requires a caller-supplied
`SourceChunksIndex` handle, always run in CI/verifier, only in pre-commit if a local index is
configured) — one implementation, three call sites, dependency-injected rather than owning a DB
connection. **Migration-manifest validation** (D38/topic 29) checks matcher resolvability (every
`fact_remap[].match` pattern matches ≥1 real anchor — catching typo-class dead matchers), target
resolvability, per-op required fields, a closed action vocabulary scoped by ledger kind, and the
`impact.md` auto-generated-section diff-check — **explicitly does not** require every blast-radius-
discovered anchor to appear in `fact_remap`, since `action: untouched` stays a valid implicit
default per D38's ratification. **Regression-fixture convention** unifies D26 (hard), D30 (soft),
D41 (soft), and D46 (undecided) into one fixture format (`fixture_id`, `kind`, `mode: hard|soft`)
under `tests/fixtures/providers/`, one runner (`langatlas-validate regression run`) with a
pluggable checker registry (`provider-record-replay`, `schema-shape`, `questionnaire-shape`,
`prompt-version-rerun`) — mode is fixture metadata, not tool-hardcoded per-kind behavior — kept
explicitly distinct from D44's `tests/golden/` scored/threshold-gated evaluation harness (a
structurally different diff-vs-recording vs. score-vs-threshold mechanism). **YAML normalization**
implements brainstorm 09's spec as two functions in `normalize.py`: `normalize_record` (whole-file
formatting, idempotent, run by the pre-commit hook to write and by CI/pre-commit check-mode to
verify) and `normalize_value` (copyedit-tolerant claim-content normalization feeding D23's fact-id
hashing) — both single-sourced so every consumer (pre-commit writer, CI checker, fact-id-minting
code) imports rather than reimplements. Full analysis:
[brainstorms/40-validator-normalizer-cli.md](brainstorms/40-validator-normalizer-cli.md).

*[developer]* Ratified with: **pre-commit always runs phase-1-only locator checks by default** —
no auto-upgrade to phase-2 `source_chunks` resolution even when a local Postgres happens to be
reachable, keeping pre-commit's fast/zero-DB-dependency contract unconditional. **D46's
schema-shape fixture starts `mode: soft`** for a shakeout period, since `compile.py` hasn't shipped
a real version yet; hardening it is a later step. **Console-script packaging: an installable
`pyproject.toml` `[project.scripts]` entry point**, matching the project's uv-in-Docker packaging
approach (uv resolves and installs the console script cleanly from `pyproject.toml`, no bespoke
`python -m` call-site wiring needed at the pre-commit hook, CI workflow, or verifier import path).
**Package location/naming confirmed as proposed**: `tools/validate/` (module
`langatlas_validate`), matching the existing `tools/questionnaire/`/`tools/orchestrator/`/
`tools/observability/` convention — no more prominent top-level name needed despite its
central imported-by-the-verifier role. **A `fact_remap` matcher resolving to zero anchors is a
hard CI failure**, blocking the migration PR outright rather than surfacing only as an
impact-report warning — even though ontology MAJORs already go through D16 O5b's human-gated
process review, a dead matcher is a mechanically-detectable defect that shouldn't rely on the
human reviewer catching it by eye.

### D49. Absence & unknown semantics (41)

Closes D23's "absence is a sourced fact, not a skip" principle and D46's ratification note into
concrete cross-surface mechanics. **State space**: `not-yet-onboarded`, `not-yet-swept`, and
`deferred` are all "no record exists" states — not facts, nothing to verify/dispute/embed;
`present`, `partial`, and `absent` are all "a record exists" states, the same `instance-exists`
claim kind differing only in the `status` value, equally first-class and equally verified.
**Schema**: no new entity — one new required field `absence_scope` (free text) on `status: absent`
records, the sweep agent's argument for why the cited source(s) can be trusted as comprehensive
over the feature's category, feeding the verifier check below. **Coverage page (D32)**: `absent`
is explicitly **not** a fourth empty-cell state — D32's three empty-cell states
(`not-yet-swept | not-yet-onboarded | deferred`) stand unchanged; an `absent` cell renders as a
normal filled cell ("Not present" + sourced summary) using the same fact-popover machinery as
`present`/`partial`, and gets a real, normally-served feature-instance page, never suppressed.
**Verification**: a new method, `completeness-check`, extends D24's existing six-verdict ladder
(reusing the vocabulary, not inventing new verdicts) via three stages — tier-A/B + locator
resolution; a corpus-wide negative full-text grep across every chunk of the cited source using a
new optional feature-level `aliases: []` field; an inverted-framing LLM entailment stage verifying
the agent's own `absence_scope` argument rather than searching for a supporting quote. A source
that actually documents the feature yields `contradicted`, blocking admission outright — guarding
the inverse of K1 citation-laundering (a false absence claim). Confidence (D25) for `absent` facts
caps at `medium` on a single tier-A/B source, requiring a second independent source to reach
`high`. **Contradiction handling**: no new machinery — D45's cross-fact type and D25's existing
since/version-qualification dissolution already cover apparent present/absent disagreements; this
topic only makes the underlying `absent` claim trustworthy enough for that machinery to matter.
**MCP**: two typed response shapes, not three — an ordinary fact object (covering
`present`/`partial`/`absent` uniformly, full `caution` block) and a new `no-record` envelope
(`{status: "no-record", reason: not-yet-swept | not-yet-onboarded | deferred, language, feature,
coverage_url}`, no `caution` block since it isn't a fact) for the three no-file states, reusing
D32's `reason` vocabulary rather than minting a parallel one; `search_knowledge`/`get_neighbors`
never synthesize an absence conclusion from a missing hit, and the MCP caution text gets one added
sentence stating this explicitly. **Builder**: pointer only (deferred module) — must consume the
fact-object/`no-record` split as first-class three-valued logic, never defaulting unknown to
false; D2's four combination-validation levels are unaffected since they're feature-graph-level,
never per-instance. Full analysis:
[brainstorms/41-absence-and-unknown-semantics.md](brainstorms/41-absence-and-unknown-semantics.md).

*[developer]* Ratified with: **`absence_scope` is a hard requirement** on every `absent` record,
not optional-but-verifier-penalized. **Feature-level `aliases: []` ships now** as a general schema
field, useful beyond absence-checking (e.g. search/synonym matching), rather than staying scoped
to only appear once a language's sweep has produced an `absent` record. **The `medium`-confidence
cap for single-sourced absence claims is confirmed** as the right conservatism, as drafted.
**Coverage-page `absent` cells get the same filled-cell treatment as `present`/`partial`**,
distinguished only by a status chip — no visual muting relative to `present`, confirming the
brainstorm's draft. **The `no-record` envelope's `coverage_url` field is not added now** —
premature given no "agent notices a gap and flags it" MCP workflow exists yet.

### D50. Domain-specific languages in the ontology (42)

DSLs stay in scope in principle — no global exclusion — but each
candidate (SQL now, others later) is still evaluated case-by-case per D28's existing
per-language selection discipline; this topic only removes the *ontological* blocker, not SQL's
separate ISO/IEC 9075 sourcing blocker. **Schema**: `language_kind: general-purpose |
domain-specific` (+ free-text `domain` tag) on the Language record, default `general-purpose`
(zero edits to existing languages); `applies_to: [language_kind, ...]` on `dimensions.yaml`,
parallel to brainstorm 30's `exclusivity` field but with the *opposite* default polarity —
defaults to `[general-purpose]` so every dimension authored against the general-purpose-only
research phase needs no edits and is only widened when confirmed genuinely universal; the same
field name works as a rarer per-feature override. **Compiler**: the D46 questionnaire compiler
reads `applies_to` mechanically (like `exclusivity`) and never emits a sweep item for a
(language, feature) pair the language's `language_kind` doesn't reach — a one-time,
taxonomy-driven scoping decision distinguishable from D46's banned per-language evidentiary
guess by a concrete test: would a `challenge-fact.yml` on the cell make sense? (No, for this
case.) **State space**: extends D49's `no-record` reason enum with a fourth value,
`not-applicable`, mechanically derived at build time — distinct from `absent` (sourced,
challengeable claim), `not-yet-swept` (real unanswered work), and `deferred` (human-maintained
per-language roadmap decision). Coverage matrix and MCP `no-record` envelope both extend to
carry the new reason; exact visual treatment deferred to topic 19/33. **Combination validation**:
no change at the requires/conflicts/influences/Rules levels (feature-graph-level, not
per-instance, same reasoning as brainstorm 30). **SQL concretely**: recommends the same
vendor-dialect substitution pattern already used for Prolog (Deransart et al. 1996) — PostgreSQL
or SQLite documentation as tier-A/B backing in place of the paywalled ISO/IEC 9075 standard.
Full analysis:
[brainstorms/42-dsl-in-ontology.md](brainstorms/42-dsl-in-ontology.md).

*[developer]* Ratified in full, with: **the asymmetric defaults confirmed as specified** —
`language_kind` defaults to `general-purpose`, `applies_to` defaults to `[general-purpose]`,
opposite polarity from brainstorm 30's `exclusivity` default, kept despite the mental-model
inconsistency because it's the correct default here. **`not-applicable` confirmed as the name**
for the fourth `no-record` reason, as drafted. **`domain` stays free text but as an "open"
vocabulary in practice**: a sweep/onboarding agent minting a new DSL's `domain` tag should try
hard to map onto an existing value first, and only add a new one when no existing tag genuinely
fits — an informal authoring discipline, not a schema-enforced closed enum. **O1c's
case-by-case DSL-candidate scoping line confirmed acceptable** — no more mechanical rule needed
for borderline candidates (regex, HCL, jq) at this time. **SQL's vendor-dialect sourcing
substitute is greenlit** — PostgreSQL or SQLite documentation stands in as tier-A/B backing for
SQL in place of pursuing the paywalled ISO/IEC 9075 text. **SQL onboarding gets its own new
phase-5-style slot in D28's phased plan** (see the dated note added to D28), rather than folding
into whichever phase happens to be current once its schema and sourcing questions are settled.

### D51. Spec-vs-implementation provenance (43)

Extends D3's source-tier system without touching D4/D24's
admissibility rule. **New Source-record field, `custom.grounding`**: one of `formal-spec |
reference-implementation-docs | design-doc | third-party-reference`,
orthogonal to D3's tier — tier answers document quality/authority; `grounding` answers what kind
of authority the document holds over the language's true definition (a reference-implementation's
docs can be tier-B *and* the most reliable available grounding for a language with no fuller
formal spec, which a tier-only model can't express). Default `third-party-reference`, with a
one-time retroactive pass classifying D28 phase-1's primary sources at ingestion, mirroring D37's
own retroactive-pass precedent for `canonical_source`. **Derived, not authored, per-fact `basis`
rollup**: computed at build time as the union of a fact's citations' `grounding` values, joining
D25's existing display-derived-axes family (verification/freshness/dispute) as a descriptive
label — never a fifth axis with display precedence, never gating admissibility. **Design docs**
(PEPs/JEPs/RFCs/TC39 proposals): no new tier letter — `grounding: design-doc` classifies them,
tier follows D3's letter unmodified (B once accepted/final, C while in-flight); new locator
grammar row `<doc-kind> <number> ["§" <section>]` (e.g. `PEP 634 §Overview`), `doc-kind` an open
documented string. **D4/D24 unchanged**: the six-verdict entailment ladder already checks "does
the source support this claim" identically regardless of `grounding`; the one edge case (a design
doc's stated intent cited for current behavior) is already caught by existing overstated-claim
handling, flagged only as a D44 golden-set coverage note. **Two additive downstream hooks**: a
shorter default edition-check interval for non-`formal-spec` groundings
(D37's existing job, config-tuned), and one added plain-text disclosure line in the
citation popover when `basis` isn't `formal-spec`. **Per-language**: Python and R get
`reference-implementation-docs` (PEPs get `design-doc`); Rust splits by claim between the
Reference (`reference-implementation-docs`) and the FLS (`formal-spec`), preferring the FLS
wherever it covers a claim (sweep-agent instruction, not schema enforcement); TypeScript's
eventual sourcing is pre-resolved as permanently `reference-implementation-docs`; SQL's D50
vendor-dialect substitute also gets `reference-implementation-docs` (see amendment below). Full
analysis:
[brainstorms/43-spec-vs-implementation-provenance.md](brainstorms/43-spec-vs-implementation-provenance.md).

*[developer]* Ratified with: **`vendor-dialect-docs` folded into `reference-implementation-docs`**
— the vocabulary is four values, not five (`formal-spec | reference-implementation-docs |
design-doc | third-party-reference`), accepting that "spec exists but is paywalled" (SQL) and "no
fuller spec exists at all" (Python/R/TypeScript) collapse into one disclosure/grounding value,
since only SQL currently needs the distinction and Prolog's already-resolved precedent
(`formal-spec`, via Deransart et al.) doesn't. **Retroactive `grounding`-classification pass
scoped to D28 phase-1's six languages only** at first ingestion, not the full 14-language set up
front — phases 2–4 classify at their own ingestion time. **`doc-kind` stays an open,
undocumented-enum string indefinitely** — no lightweight registered list needed unless a real
governance problem shows up later. **Edition-check interval: a flat shorter interval for every
non-`formal-spec` grounding**, no further per-implementation-speed variance (CPython's annual
cadence vs. a rolling-release tool are treated the same for now). **Popover disclosure wording
accepted as the v0 template** as drafted ("Sourced from [Python]'s reference implementation's
documented behavior, not a formal language specification") — no separate review batch needed
before it ships. **Rust's per-claim FLS-preference rule stays a sweep-agent instruction only** —
no mechanical recheck trigger for now, despite the FLS's active post-2026 growth.

### D52. Coverage analytics (44)

Splits the checklist's single topic into **three reports at three
different points in the project's lifecycle** (the three inputs are never simultaneously
populated), sharing one tool and one computational core rather than three inconsistent scripts or
folding into D41's pipeline-telemetry tool (different data domain: corpus/audience data, not
pipeline-run data). **One new sibling CLI, `tools/coverage/report.py`**, matching D41/D46/D48's
established `tools/<domain>/` shape (subcommand dispatch, markdown to stdout, optional gitignored
snapshot, no daemon, never canonical data), built on one shared `langatlas_coverage.metrics`
library computing "instance count per node, keyed by immutable id" once. **`dossier`** implements
brainstorm 25's O6 exit dossier (five items per the D27 amendment dropping external-checklist
coverage): four items are pure computation over existing data; one (R5 structured findings) needs
a small named authored artifact —
`research/reality-checks/<cycle>-<theme>.yaml` (per R5 cycle, a light format addition to
brainstorm 25's R5 design). **`gaps`** computes `<dimension, value>` corroborating-instance counts
against a configurable `--min-instances` default of `2` (no per-dimension override for now),
purely advisory — nothing automatic triggers, and the report explicitly caveats that the metric is
close to meaningless before D28 phase 1 completes. **`demand`** reads a monthly Umami custom-event
export of Pagefind search queries (`pagefind-search` event, a small addition to the already-
ratified inline search-box JS), matched against D49's `aliases: []` field to separate "known
synonym miss" from "genuinely absent content." **No structural interaction with topic 29**: every
metric recomputes from current data on each run (no cache to invalidate); the only obligation is
keying by immutable node `id`, already project-wide convention. Coverage-page visual treatment of
thin/gap values is explicitly out of scope, folded into topic 19/33's existing trust-signal/matrix
ownership. Full analysis:
[brainstorms/44-coverage-analytics.md](brainstorms/44-coverage-analytics.md).

*[developer]* Ratified with: **tool boundary confirmed** — a new sibling `tools/coverage/report.py`
over folding into D41's `tools/observability/report.py`, given the different data domain. **R5
structured-findings format confirmed** — R5 sessions emit a small
`research/reality-checks/<cycle>-<theme>.yaml` file, not just a prose summary. **`--min-instances`
default of `2` confirmed**, no per-dimension override, and crossing it triggers nothing automatic
(report-only). **Report persistence: ephemeral** — `dossier`/`gaps`/`demand` output stays stdout +
optional gitignored snapshot, mirroring D41's precedent, not committed as a dated audit trail.
**Pagefind→Umami `pagefind-search` custom-event wiring is acceptable** under D33's existing search
ratification and should be added — no separate sign-off needed beyond this note. **`demand`
cadence: monthly export**, matching D37/D41's other periodic jobs, not purely on-demand.

*[developer, 2026-07-19]* **External-checklist coverage is dropped from `dossier` entirely** — the
brief and the R0/R1 seed sources (Jordan et al. 2015, Van Roy & Haridi 2003) are seed context for
the research phase, not something the developer wants coverage-reported. The owed
`ontology/exit-checklists/<source>.yaml` authored-artifact deliverable is cancelled along with it;
`dossier` ships with five items, matching the amended D27 exit-dossier definition.

## Batch 45, 46, 47, 48, 49 decisions (2026-07-19 — from brainstorms 45, 46, 47, 48, 49 — **ratified by the developer**, amendments noted inline)

### D53. Finding-aid tooling for the research phase (45)

Turns D29's "finding aids only" policy into a concrete pipeline component. **One library, two
consumption modes**: a `langatlas_finding_aids` package with per-source query functions
(`query_pldb`, `query_wikidata`, `query_hyperpolyglot`, `query_wikipedia`), wrapped by
`tools/finding-aids/report.py` (`checklist` subcommand for D27 R3 batch survey generation,
`lookup` for ad hoc queries) and by a thin D26 tool wrapper exposing the same functions as a live
`search_finding_aids` callable for the D5 sweep's point-lookup need. **Per-source adapters match
each backend's real shape**: live throttled/cached clients for Wikidata (scoped SPARQL template)
and Wikipedia (REST API); monthly-refreshed local mirrors for PLDB (dataset export pull) and
Hyperpolyglot (scoped scrape respecting robots.txt/TDM opt-outs per D14), with all reads served
from mirrors for reproducibility. **Caching/rate-limiting/logging ride the existing D26
`RunContext`** as a fifth channel type, no bespoke mechanism. **Non-citability enforced
structurally, three layers**: a typed `FindingAidResult` envelope the fact schema has no slot for,
a tool-description caveat restating D29/D3 once per session, and D31's data-not-instructions scan
applied from day one (this tool is the concrete retrofit point D31's own ratification flagged as
deferred-but-owed). **`provenance.candidate_source` populated as advisory bookkeeping** at
drafting time when a finding-aid query precedes a fact proposal; D29's identification-metadata
carve-out is a separate explicit path (`mint_identification_source`) producing a real tier-D
`sources/` citation through the normal D4 gate. **Location: `tools/finding-aids/`**, matching the
established `tools/<domain>/` family, never registered on the public MCP (D8). Full analysis:
[brainstorms/45-finding-aid-tooling.md](brainstorms/45-finding-aid-tooling.md).

*[developer]* Ratified with: **the D31 lexical instruction-pattern scan is built into
`search_finding_aids` from day one** — no accepted initial gap, overriding D31's own
"acceptable gap, retrofit before relied on heavily" posture now that this is the concrete
retrofit point. **Monthly mirror refresh cadence confirmed** as proposed (matching D37/D41's
other periodic jobs), not a coarser per-R3-theme-cycle refresh. **PLDB mirror mechanics: a
git-clone-style mirror** of PLDB's published repo, not a scraped/API-shaped pull. **Tool
wrapper placement: inside `tools/finding-aids/` itself**, not the provider-abstraction
package's tool registry. **Live-tool availability: available to every agent session type**, not
scoped only to R3 survey and D5 sweep sessions.

*[developer 2026-07-20]* The body's "through the normal D4 gate" clause for
`mint_identification_source` is superseded: identification metadata is ungated registry data per
D29's dated note — the tier-D citation is still minted, but only for attribution; no
admissibility gate applies.

### D54. Challenger-round auto-skip rules (46)

Designs the *mechanism* for brainstorm 04 §4's syntax-quote-auto-accept idea without picking a
numeric threshold — the sweep pipeline hasn't run yet, so no real "debate changed nothing" rate
exists to look at (per the existing open question this topic resolves). **Eligibility starts
narrow**: layer-1 syntax claims only, backing source `custom.grounding: formal-spec` (D43) only,
D24 fuzzy-match ≥0.90, no `since` back-dating in play — expansion to other claim types/groundings
happens later, per-type, on that type's own measured data, never inherited. **Mechanism is a
short-circuit inside an already-triggered D5 debate**, not reconciler-level conflict suppression:
the reconciler's conflict detection stays untouched; only the challenger/moderator sub-step is
skippable, and only after the pre-challenge draft clears the D24 verifier at the required tier —
this is also the only version the existing D30/D41 verifier-replay counterfactual can evaluate.
**Extends `replay_verdict` (D41) with stratified logging**: claim type × `grounding` ×
fuzzy-match bucket, a widened query including undebated same-type facts as the true production
denominator, and a taxonomy-tagged breakdown of what changed (reusing D44's 13-stratum
vocabulary) on debates that did matter. **Rollout: shadow mode first** (log "would have
auto-skipped" without changing behavior), **then live with a permanent kill switch and audit
sample** that never tapers to zero, mirroring D4's spot-check and D24's cross-family drift
sampling. **Governance**: a small versioned `config/auto_skip.yaml`, changed only by explicit
developer decision recorded in decisions.md, mirroring D16's MAJOR-gate pattern at config scale.
Full analysis:
[brainstorms/46-challenger-auto-skip.md](brainstorms/46-challenger-auto-skip.md).

*[developer]* Ratified with: **the narrow initial eligibility slice (layer-1 syntax,
`formal-spec` grounding, fuzzy-match ≥0.90, no `since` back-dating) confirmed as-is** — matches
the developer's intuition for the safest first cut; no further narrowing (e.g. zero prior
contradiction history) added. **Mechanism confirmed as the short-circuit inside an
already-triggered debate** (the recommended option), with reconciler-level suppression left for
later consideration only once the short-circuit version has a track record. **Initial
audit-sample fraction: a number now is fine**, anchored to D4's 5–10% spot-check / D24's ~10%
cross-family sample rather than waiting for shadow-mode volume to size it. **Governance weight:
the lighter process confirmed** — a plain versioned `config/auto_skip.yaml` change recorded in
decisions.md, not D16's full RFC-gated MAJOR process. **Rough volume goalpost: left fully
open**, as currently stated — no minimum shadow-mode sample size named yet.

### D55. Discussion→Issue promotion tooling (47)

Answers the checklist's own "whether it's ever needed" framing: **stay fully manual (D32 §2.3's
baseline) until Discussions exist and accumulate real volume** — D32 hasn't itself shipped yet, so
there is no volume to instrument against and building promotion tooling now would be automation
in search of a problem. **Trigger to revisit**: not a numeric threshold but a qualitative signal —
the developer noticing either promotions happening late or promotion triage itself consuming
noticeable recurring time. **When triggered, build a private developer-facing digest first**
(`tools/community/report.py` or similar, styled like D41/D44's CLIs) — a scheduled job using a
two-stage signal funnel (cheap structural pre-filter: reply count/participant count/staleness-as-
stop-signal, feeding an LLM claim+source-presence classification only on the pre-filtered subset)
that surfaces candidate threads to the developer; promotion itself stays a manual click. **Only
escalate to a public-facing bot** if the digest's own triage load (not just the noticing problem)
becomes the bottleneck — and even then, the bot proposes promotion (comments, human confirms)
rather than silently auto-filing, since GitHub's native "convert to issue" is lossy against D32's
four typed Issue Forms and template-misselection/mis-transcription risk is real. If ever built,
the bot needs its own third, narrowly-scoped GitHub App (`Discussions: write` + `Issues: write`
only, distinctly named from D36's `langatlas-bot[bot]`), matching D36's "new trust surface gets
its own App" pattern. Full analysis:
[brainstorms/47-discussion-issue-promotion.md](brainstorms/47-discussion-issue-promotion.md).

*[developer]* Ratified with: **sequencing confirmed** — manual now → private digest once real
Discussion volume exists → public bot only if the digest's own triage load becomes the
bottleneck; the developer does not want to commit now to building the full public-facing bot.
**Trigger condition confirmed as purely qualitative** (developer-judged "promotions happening
late" or "triage consuming noticeable time") — no concrete proxy metric named ahead of any
Discussion data existing. **Propose-only mechanic confirmed**: if/when the public bot is built,
it must propose (comment, human confirms) rather than silently auto-file, even once the
classification step has a shadow-mode track record. **Bot identity confirmed**: a third,
distinctly-named GitHub App (`Discussions: write` + `Issues: write` only), separate from both the
D36 runner App and the future external-PR-skim App — it does not ride on the external-PR App.
**Digest placement: a standalone script**, not a subcommand on an existing CLI (D41's
observability tool or D44's coverage tool).

### D56. CONTRIBUTING.md content (48)

A doc-writing item, not a design decision — D32 already settled every substantive question
(channels, lane division, PR posture, DCO). This decision records that a full `CONTRIBUTING.md`
draft has been produced and reviewed for structure (see the brainstorm file for the complete
drafted markdown), covering: a two-sentence project one-liner; the three lanes (challenge a fact
via `challenge-fact.yml`, start/join a Discussion, propose new coverage/sources via
`propose-coverage.yml`/`request-language.yml` or a source/proposal PR); D32's graduated
external-authorship posture stated plainly (source/proposal PRs open now, full fact-authoring PRs
not yet, no fixed date); a DCO section correctly distinguishing D36's bot-installation carve-out
from human per-commit `Signed-off-by:`; a licensing section tied to D42 (CC BY-SA 4.0 corpus /
MIT code, "LangAtlas contributors" attribution, takedown contact + `legal-complaint.yml`); and a
"no growth chrome" closing note pointing to `/coverage/` as the honest entry point. **The file is
not landed at the repo root yet** — the developer decides when (tied to public-launch timing,
per brainstorm 31) and confirms placeholder GitHub-org/domain links once D17's org-name action
resolves. Full analysis, with the complete drafted document:
[brainstorms/48-contributing-md-content.md](brainstorms/48-contributing-md-content.md).

*[developer]* Ratified with: **hold, not land now** — the drafted content stays unlanded until
the public-launch checklist (tied to brainstorm 31's positioning work), rather than landing as
the actual `CONTRIBUTING.md` immediately on the private repo. **Real URLs: wait on D17's
still-unconfirmed GitHub org name** before finalizing the link block — no placeholder-with-TODO
version lands in the interim. **Ontology-RFC mention: out of scope** for this contributor-facing
doc — no pointer to the D16 ontology-MAJOR RFC process is added. **Tone check: the drafted
plain/declarative voice is fine as written** — it lands D32 §2.6's "no growth chrome" principle
correctly; no spots (including the opening paragraph) need to run warmer.

### D57. Per-onboarding-cycle tooling checklist (49)

Consolidates four scattered onboarding-relevant decisions (D28/D34's audit, D33's Shiki/
`syntax_check` aside, D50's `language_kind` classification, D51's `grounding` classification, plus
D37's source-ingestion fields) into one reusable artifact. **Hybrid (O3)**: a markdown checklist
template, `ontology/onboarding-checklists/language-template.md`, covering nine items (selection
sanity, license/access class, D51 grounding resolution, D50 `language_kind`/`domain`, Shiki-
grammar presence, D33 `syntax_check` mode, D37 source-record fields, ingestion-cost note, D28
phase sign-off) as a `- [ ]` checkbox list per CLAUDE.md's checkbox-plan convention, copied to
`ontology/onboarding-checklists/<lang-id>.md` per language and filled in at onboarding start.
Items that are already schema fields on canonical records (`syntax_check`, `language_kind`/
`domain`, `custom.grounding`, D37's source fields) are not duplicated into a separate structured
file — the checklist just points at the field to set; the schema and validator remain the
enforcement surface. **One small fold-in to D48's `tools/validate/` `precommit`/`ci` contracts**:
a required-field-*presence* check (not correctness) confirming every language that has reached
`not-yet-swept`-or-later status has `language_kind` and `syntax_check` set to *something*, closing
the one silent-skip failure mode (an unset field is indistinguishable from a deliberate default)
a pure-documentation template can't catch on its own. **Directory choice**: `ontology/
onboarding-checklists/`, not `ontology/exit-checklists/` — that name was proposed then explicitly
cancelled by the developer per D52's dated amendment, so it's a naming precedent to avoid
repeating; not under `tools/<domain>/` either, since this artifact has no importable library or
CLI, only a markdown template. Full analysis, including a worked example for Rust (D28 phase 1):
[brainstorms/49-onboarding-checklist.md](brainstorms/49-onboarding-checklist.md).

*[developer]* Ratified with: **directory choice amended — nest under `context/` instead**, not
`ontology/onboarding-checklists/` as proposed and not attached inside each language's own
registry record directory. **D48 fold-in dropped**: the narrow required-field-presence check
(`language_kind` and `syntax_check` only) is **not worth adding now** — both stay fully manual,
unenforced checklist items, since the failure mode it guards against hasn't actually happened yet
(no onboarding has run yet — D28 phase 1 is still ahead; parenthetical corrected 2026-07-20). **Selection-sanity item (checklist
item 1) stays purely narrative** — D34's per-candidate audit-table columns are not pulled in as a
reusable sub-table format. **Timing: deferred** until closer to D28 phase 2/3, rather than built
now, despite the shape being fresh from this consolidation pass.

## Batch 53, 56, 57, 59 decisions (2026-07-20 — from brainstorms 53, 56, 57, 59 — **ratified by the developer**, amendments noted inline)

Consolidated from the fourth round-4-backlog brainstorm batch and ratified in conversation on
2026-07-20.

### D58. Postgres loader implementation & blue-green load mechanics (53)

A single Python loader script (`tools/loader/load_bundle.py`, matching D48's `tools/<domain>/`
CLI convention) reads the D35 zstd-SQLite bundle via stdlib `sqlite3` and writes into Postgres
via `psycopg` v3, upgrading JSON-in-TEXT bundle columns to native `jsonb`. **Blue-green
mechanics**: each load builds into a fresh schema named after the bundle's `data_tag` (e.g.
`data_v418`) — all bulk copy and index builds (pgvector ANN, tsvector FTS) happen there with zero
live-query impact — then an atomic single-transaction swap of `CREATE OR REPLACE VIEW
current.<table> AS SELECT * FROM data_v418.<table>` flips everything at once; MCP/FastAPI query
`current.*` exclusively via Postgres role grants. A MAJOR `bundle_schema_version` bump needs
`DROP VIEW`+recreate instead of `CREATE OR REPLACE`. **Embedding-cache keying**: recommended
`(embedding_model_id, fact_id)` — not a coarser `corpus_hash` — since D23's fact ids are already
content-derived (copyedit-tolerant), so fact-id stability *is* content stability; route through
the existing D26 `RunContext` cache plus a new `knowledge_embeddings` lookup table. Index rebuild
happens entirely inside the isolated shadow schema before the swap. **Rollback**: a failed
build-phase load just leaves an orphaned unused shadow schema (drop and retry); rollback after a
successful swap is the same view-swap run in reverse, retaining exactly two live schemas
(current + previous); deeper rollback re-runs the loader against an older `data-vN` release asset.
Full analysis: [brainstorms/53-postgres-loader-blue-green.md](brainstorms/53-postgres-loader-blue-green.md).

*[developer]* Ratified with: **role/grant setup: a separate docker-compose init script**, not the
loader itself — the loader's own code stays focused on data movement, not role management.
**Pre-swap validation: simple checks only** (row-count-against-manifest + a handful of
hand-picked smoke queries), not the full golden-set Recall@5/MRR eval — that stays a separate
pipeline check, not duplicated inside the loader. **Invocation: both** — the `langatlas-site`
repo's `repository_dispatch` build triggers the site-owned Postgres load, and a separate
scheduled job also runs against the `langatlas-kb` repo's own compose stack (plus manual local
loads for MCP testing). **Retention depth: confirmed as proposed** — exactly two live schemas
(current + previous), no deeper grace window.

*[developer 2026-07-20]* **Where Postgres lives, clarified**: Postgres serves the RAG/MCP local
agentic workload on developers' machines (the kb repo's compose stack) — its only role at
launch. A site-side Postgres becomes relevant only later, when/if the deferred public FastAPI
search (D33) or additional live modules (e.g. the Builder's public library, D34) ship; the
"site-owned Postgres load" invocation path above provisions for that stage, not a launch
requirement.

### D59. Cross-fact contradiction scan job design (56)

Adds no new infrastructure category, reusing what the project already committed to building.
**Candidate generation** is two-stage: free same-anchor-family filtering via D23's record-id
scheme, then an embedding-similarity top-k pool (k=10–20, cosine floor ≈0.75) drawn from a new
fact-embedding index — a table separate from D15's `source_chunks`, not piggybacked on it.
**Cadence**: event-driven off new-fact commits (mirroring D25's re-verification philosophy)
rather than a fixed calendar interval, plus a rare backstop re-scan tied to embedding-model swaps.
**Cost**: stays on the university API at D24's own `deepseek`/`deepseek-thinking` tiering;
estimated volume stays a strict subset of D24's own verification load, so no new cost-tiering or
drift-sampling decision is needed. **Comparison call**: a distinct four-verdict vocabulary
(`no-conflict | qualified-non-conflict | conflict | inconclusive`) — a claim-vs-claim relation,
deliberately not reusing D24's six-verdict claim-vs-source vocabulary — folding D45's since/
version qualification check into the same call for this minting path only. **Findings** write
directly into D45's existing `contradictions.yaml` (zero schema changes, `type: cross-fact`,
mechanism `contradiction-scan`) and surface via a new `report.py cross-fact-scan` subcommand
riding D41's CLI pattern, orchestrated as one more job kind in D43's `driver.py`. Full analysis:
[brainstorms/56-cross-fact-contradiction-scan.md](brainstorms/56-cross-fact-contradiction-scan.md).

*[developer]* Ratified with: **fact-embedding index confirmed as a separate table from
`source_chunks`**, deferring model choice to D22's fact-index benchmark rather than making its
own choice now. **Similarity floor/top-k defaults (≈0.75 cosine, k=10–20) confirmed** as
reasonable starting points to tune empirically once real fact volume exists. **Cadence
confirmed**: event-driven-per-commit as the primary trigger, plus the proposed annual/
embedding-model-swap backstop re-scan as an acceptable low-frequency complement. **D24-style
cross-family drift sampling skipped at v0**, as recommended. **Four-verdict vocabulary
(`no-conflict | qualified-non-conflict | conflict | inconclusive`) confirmed as-is** — no further
split of `qualified-non-conflict`. **Folding the qualification check into this job's LLM call
accepted**, including the resulting asymmetry with the reconciler/human-challenge paths that keep
it a separate mechanical step (D45).

### D60. MCP tool-set extension tracking (57)

A consolidation, not a new mechanism: the brainstorm file is now the standing reference for the
public read-only MCP tool set and everything deliberately kept off it. **Public set (7 tools)**:
D8's original five (`search_knowledge`, `get_fact`, `get_feature`, `get_neighbors`, `get_source`)
plus D45's `list_contradictions`/`get_contradiction` (confirmed shipping, correcting brainstorm
37's own stale "not fully specified" language). **Pipeline-only (never public)**: D15's
`search_sources`/`get_source_section`, D53's `search_finding_aids`, and D18's still-unbuilt
`search_debate_history` (v2, proposed only). The recorded boundary test: a tool is public only if
every possible return is either an admitted/verified fact or citable KB structure; pipeline-only
if any output is raw pre-verification evidence, structurally non-citable finding-aid content, or
non-citable agent chat text (the common K1 citation-laundering rationale). Process
recommendation: future brainstorms that propose a new MCP tool append a row to this file instead
of re-deriving the boundary from scratch; any decisions.md ratification touching a listed tool
updates this file's status column in the same pass. Full analysis:
[brainstorms/57-mcp-toolset-tracking.md](brainstorms/57-mcp-toolset-tracking.md).

*[developer]* Ratified with: **`search_debate_history` does not get its own dedicated brainstorm
now** — it stays parked until the transcripts repo (D18) has enough real volume to make the
design concrete, reusing D15/D45/D53's non-citability pattern (typed envelope, tool-description
caveat, D31 scan) whenever it is eventually built. **Maintenance ownership: manual
per-brainstorm-append upkeep of this tracking file is sufficient** — no mechanical regeneration
from decisions.md planned.

### D61. Constraint-violation resolution path (59)

Proposes a hybrid (Option C), amending D46's existing quick-ratification text ("route into D5's
debate machinery unchanged, no separate path"). Keep D5's debate machinery for the fact-level
question it's actually built for — is the sweep evidence for each contradicting answer solid,
and does a `since`/version qualification dissolve the apparent contradiction (this part of D46
stays unchanged). Add one new resolution outcome, `constraint-disputed`, for when evidence is
solid on both sides and nothing dissolves it: that outcome lands as a pre-filled
`constraint-dispute`-typed RFC issue draft in a work queue (mirroring D1's "controversial facts
are auto-flagged... surfaced... in a work queue" pattern and backlog topic 47's
discussion-issue-promotion shape) for manual promotion, rather than auto-opening the issue —
since "is the ontology rule itself wrong" is
squarely inside D16's one human-gated carve-out, not a fact question D1's no-PR-gate default
should settle. The sweep's FeatureInstance records land and render visibly flagged the whole
time, never blocked — applying D36's existing "disputes are excluded from auto-revert, land and
render visibly flagged" policy and D25's dispute axis, not a new policy. Full analysis:
[brainstorms/59-constraint-violation-resolution.md](brainstorms/59-constraint-violation-resolution.md).

*[developer]* Ratified with: **the refinement supersedes D46's existing "no separate path"
text** (dated amendment added at D46 above), rather than reconfirming the original
unchanged-debate-machinery option. **RFC trigger: a work-queue item for manual promotion**, not
an automatic issue-open — matching backlog topic 47's discussion-issue-promotion shape, decided
the same way for consistency. **Label confirmed**: `constraint-disputed` stays as named, no
rename to something like `rule-suspect` — distinct enough from D25's `disputed` controversy
level in context. **One-side-well-sourced case confirmed as assumed**: resolves as an ordinary
D5 fact outcome (reject/qualify the weak claim), no RFC and no constraint-dispute machinery
invoked; the lightweight pattern-spotting note (tracking repeat partial challenges against the
same rule) is filed as a nice-to-have, not designed here. **Debate prompt framing: not needed**
— the reconciler's constraint-violation debate variant does not need explicit "adjudicate
evidence, not ontology correctness" prompt-level framing beyond the existing typed-challenge
vocabulary.

### D62. Fact-embedding index build-out (61)

Concretizes D7's originally-named fact-embedding index, assembling fragments left open by D56/
D58/D60. One table, `knowledge_embeddings`, `chunk_type IN ('fact', 'feature-description')`
discriminator (not split tables) — a single table already sufficient for D7's original filter-first
design, since the earlier split into a separate `source_chunks` (D15) was motivated by source text's
different lifecycle, not by anything specific to facts vs. feature descriptions. Primary key
`(embedding_model_id, chunk_type, subject_id)`, `vector(N)` at whatever dimension D22's benchmark
selects, `rendered_text` (D47's precomputed claim/description string) as the exact embedded text,
plus D7's original filter metadata (`feature_id`, `language_id`, `status`) extended with
`controversy_level`. **Loader relationship**: embeddings are computed once during the bundle-build
pipeline (via `RunContext`/D26) and shipped as a precomputed bundle column (D35); D58's loader
copies them into the shadow schema using its own already-specified cache-reuse-keyed,
build-before-`COPY` mechanics — no new loader code path. **Refresh cadence**: no fixed calendar
job; incremental re-embed rides whatever cadence bundle builds already run at (unchanged
`rendered_text` reuses its vector via cache-reuse keying), with a full re-embed falling out for
free on an embedding-model swap since the cache key includes `embedding_model_id` — the same event
D59 already names as its own contradiction-scan backstop trigger. **Shared consumers**: the
contradiction scan (D59) and `search_knowledge` (D8) both read this one table, differently (raw
cosine top-k vs. filtered hybrid BM25+vector RRF gated to a publicly-safe status); site search
stays Pagefind (D33) — a different architectural layer, not a consumer of this index at v0; D33's
deferred public FastAPI hybrid search, if ever built, becomes a third consumer of the same table.
**Cache table question resolved**: `knowledge_embeddings` *is* the table D58 left open as a
parenthetical ("or reuse of D26's existing cache store directly") — it serves both D58's
cache-reuse bookkeeping and the live query index every downstream reader needs; `RunContext`'s
existing content-addressed cache stays the separate, complementary embedding-API-call dedup layer
underneath it. Full analysis:
[brainstorms/61-fact-embedding-index-build-out.md](brainstorms/61-fact-embedding-index-build-out.md).

*[developer]* Ratified with: **table renamed to `knowledge_embeddings`** — the name better
covers its scope (fact claims *and* feature/concept-description rows) now, before any code
references the original `fact_embeddings` wording inherited from D58; applied throughout this
decision and the source brainstorm. **Feature/concept-description embedding source text
confirmed already resolved by the proposed schema**: brainstorm 09's O7 Feature/Concept record
shape already carries a fact-bearing `summary.text` field for exactly this purpose (see
`features/pattern-matching.yaml`'s `summary:` block) — no follow-up decision needed;
`chunk_type='feature-description'` rows embed that field's rendered text. **Bundle-column
computation confirmed** — embeddings are computed once during the bundle-build pipeline and
shipped as a precomputed `data-vN` column, not computed by the Postgres loader at load time.
**`search_knowledge`'s publicly-safe-status filter confirmed**: D25 verification values
`verified` and `partially-verified` (the latter rendering with its existing public badge, per
D25) gate a fact into results; `unverified` and `failed` do not. **Embedding dimension and
HNSW-vs-IVFFlat index choice confirmed deferred to D22's benchmark output**, no default pinned
now.

*[developer 2026-07-20]* **Embedding columns stay out of the public bundle**, resolving the
conflict with D13's embeddings-stay-private ratification: the web app has no use for the vectors
(site search is Pagefind, D33), so the precomputed `knowledge_embeddings` data is built alongside
the bundle but delivered through the private tier (the D15 snapshot store, same home as D26's
cache) rather than as a public `data-vN` asset; D58's loader reads it from there. Everything else
in this decision stands unchanged.

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
