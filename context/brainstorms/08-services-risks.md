# 08 — Service Architecture Map & Risk Register

> Brainstorm output for Project Hermes. Topic: enumerate every service/component the system
> needs, split MVP vs later, favor the most boring solo-dev implementation, and produce a frank
> ranked risk register. Source of truth: `context/input-brief.md`.

## Problem framing

Hermes is three things wearing one trenchcoat:

1. A **curated fact corpus** mapping programming languages onto a structured concept/feature
   graph, where every fact carries a citation to a real source (brief §2.1, §2.3).
2. An **agentic pipeline** (developer-managed) that grows and audits that corpus using RAG over
   the same corpus plus external sources (brief §2.4), connectable to Claude Code and other
   providers via MCP (brief §2.2).
3. A **public, SEO-focused, human-readable website** rendering the corpus, with visible
   per-fact sourcing and an easy challenge path for human experts (brief §2.5, §2.6).

The architectural trap is treating these as one online application. They are better treated as
a **build pipeline**: agents write facts → facts live in versioned storage → a static site is
compiled from them. Almost nothing needs to be a running server for the MVP. The constraints
that drive everything: solo dev, no GPU, slow university API + Claude Pro subscription, no
architecture decided yet, proof-of-concept scope.

**Core framing decision (needed before code):** is the *source of truth* (a) files in a Git
repo, or (b) a Postgres database? The brief's own challenge-channel option (a) — "YAML-like
files on GitHub" — strongly suggests **Git-as-database** for the MVP: facts as structured text
files, PRs/issues as the challenge channel, the website and the vector index both *derived
artifacts* compiled from the repo. This one decision collapses roughly half of the component
map below into "a script in CI". The rest of this document assumes it, and calls out where it
breaks.

## Component map (MVP vs later)

Legend: **MVP** = needed for the proof-of-concept. **Later** = defer until a signal demands it.
Each entry: what it is, simplest boring implementation, where the boring version breaks.

### 1. Fact/source store — **MVP**

- **What:** canonical storage for facts (language ↔ feature ↔ evidence) and structured source
  records (the ".bib-like" identification, brief §2.1/§2.3). This is the heart; everything else
  derives from it.
- **Boring implementation:** one Git repo. Facts as YAML (or JSON5/TOML) files with a JSON
  Schema validated in CI; sources as **CSL-JSON** records in a `sources/` directory (CSL-JSON is
  the modern, tooling-rich answer to "some kind of .bib" — convertible to/from BibTeX with
  pandoc/citeproc; recommend it as the canonical format, keep a generated `.bib` export for
  academics). Fact IDs are stable slugs; every fact field that is a claim carries
  `source: <source-id>` + locator (page/section/URL anchor).
- **Where it breaks:** (i) when facts need heavy cross-record queries at *runtime* (the MVP
  doesn't — the site is static and queries happen at build time, where you can load everything
  into memory or a throwaway SQLite/DuckDB); (ii) when the corpus exceeds what a repo handles
  comfortably (~tens of thousands of small files is fine; archived source *content* is not —
  see §5); (iii) when non-Git-literate experts must edit (see §8). Migrate to Postgres only
  when one of these actually bites; write the schema as if it will (flat, normalized records,
  no clever nesting) so the migration is an import script.

### 2. Concept/feature graph model — **MVP**

- **What:** the typed graph from the brief (requires / enables / conflicts / alternative-to /
  implemented-by / expressed-as / improves-quality / hurts-quality). Not a separate service —
  a schema concern of §1 — but listed because it is the highest-design-risk artifact.
- **Boring implementation:** edges as fields in the YAML fact files; a CI script loads all files
  into `networkx` (or plain dicts) to validate referential integrity, cycle constraints, and
  required/conflict consistency. **No graph database.** Neo4j for a corpus this size is pure
  operational weight; every graph query the MVP needs runs at build time over in-memory data.
- **Where it breaks:** interactive graph exploration on the website with server-side traversal.
  Even then: precompute the JSON the visualization needs at build time first.

### 3. Vector index + embedding service — **MVP (thin)**

- **What:** RAG retrieval over the corpus for the agents and for MCP clients (brief §2.1/§2.2).
- **Boring implementation:** **sqlite-vec (or Chroma in embedded mode) rebuilt from the repo by
  a script**; embeddings via a cheap hosted API (Voyage or OpenAI `text-embedding-3-small`;
  embedding cost for a corpus of this size is single-digit dollars, so "no GPU" is a non-issue).
  The index is a *derived, disposable artifact* — never the source of truth — so re-embedding
  after schema changes is `make index`, not a migration. A dedicated embedding *service* is not
  a thing the MVP has; it's ~30 lines calling an API with a local content-hash cache so
  unchanged facts are never re-embedded.
- **Honest caveat:** for a corpus of hundreds-to-thousands of *structured* facts, plain
  keyword/BM25 + the graph structure may retrieve better than embeddings. Build retrieval as
  hybrid (BM25 via SQLite FTS5 + vectors) from day one; it's cheap and hedges the quality risk.
- **Where it breaks:** multi-writer concurrent access (SQLite) or corpus far beyond memory.
  pgvector-in-Postgres is the natural successor, and only alongside the §1 migration.

### 4. Agent orchestration pipeline — **MVP (the actual product of the PoC)**

- **What:** developer-managed agents (per-language experts, debaters, auditors) that propose
  facts, argue, and attach sources (brief §2.4, §2.7).
- **Boring implementation:** **Python scripts run manually / via cron on the dev machine**, one
  agent-run = one function, using the Claude Agent SDK or plain API calls; slow university API
  as the bulk workhorse for cheap steps, Claude for judgment-heavy steps. Agent output is
  **never written directly to the corpus**: agents emit candidate facts into a `proposals/`
  staging area (or open draft PRs), and a human (the owner) merges. This staging boundary is
  simultaneously the moderation tool, the quality gate, and the audit log — do not skip it.
  Debate = a script that runs N agent turns over a shared markdown transcript and ends with a
  structured "consensus + dissent + citations" block. No LangChain/LangGraph/queue
  infrastructure; a `for` loop with checkpointing to JSON files survives crashes fine.
- **Where it breaks:** long-running always-on pipelines, parallel fleets, or multi-user
  triggering. None are MVP. If runs get long, `cron` + a lockfile + resumable checkpoints goes
  a surprisingly long way.

### 5. Source fetcher/archiver — **MVP (minimal), full archiving Later**

- **What:** resolving a citation to actual content the agents can quote and the site can link;
  protection against link rot.
- **Boring implementation (MVP):** a fetch script with per-domain politeness (respect
  robots.txt, throttle, identify with a real User-Agent), storing *extracted text excerpts +
  content hash + fetch date* per source, and firing a **Save Page Now** request to the Internet
  Archive for every URL-based source (outsource rot protection to the people whose job it is).
  Store the archive.org snapshot URL in the CSL-JSON record.
- **Later:** full local WARC archiving, paywalled-source handling, PDF corpus management. Do
  **not** commit full page snapshots or PDFs into the Git repo (this is where "one repo" breaks
  first — binary blobs balloon it); if local archiving becomes necessary, that's an object
  store (a directory on a VPS or B2/S3 bucket), keyed by content hash, referenced from source
  records.
- **Legal note:** store *short excerpts* used as evidence, not full copyrighted texts, in the
  public repo. See risk L1.

### 6. MCP server — **MVP (small)**

- **What:** the bridge that lets Claude Code (and other MCP clients / local models via MCP
  bridges) query the knowledge base (brief §2.2).
- **Boring implementation:** one stdio MCP server (official Python SDK, FastMCP) exposing
  ~4 tools: `search_facts` (hybrid retrieval over §3), `get_fact` (with sources),
  `get_language` / `get_feature` (structured views), `list_sources`. Runs locally against the
  same SQLite artifacts the agents use. No network service, no auth, no hosting.
- **Where it breaks:** the moment *other people* want remote access — then it needs an HTTP
  transport, hosting, and auth (see §11). Explicitly Later.

### 7. Website build + hosting — **MVP**

- **What:** the SEO-focused, clean, non-wiki public site (brief §2.5).
- **Boring implementation:** **static site generator** (Astro is the current sweet spot for
  content sites: content collections map 1:1 onto YAML fact files, zero-JS by default = fast =
  SEO) compiled from the repo by GitHub Actions, hosted on Cloudflare Pages or GitHub Pages
  behind a custom domain. Every fact page renders its citations and a "Challenge this fact"
  link (→ prefilled GitHub issue, §8) and a "source file" link (the brief explicitly asks for
  per-fact source-code links). Sitemap, structured data (schema.org), canonical URLs — all
  build-time concerns, all free.
- **Where it breaks:** any interactive/user-generated feature — the Builder module, upvotes,
  comments, accounts. Those are explicitly *later modules* in the brief; when they arrive they
  need a real backend (one VPS + Postgres + a small API). The static site does not need to be
  thrown away then — it becomes the content half in front of a small dynamic API.

### 8. Challenge/feedback channel — **MVP**

- **What:** the path for human experts to dispute facts (brief §2.5, options (a) GitHub vs (b)
  custom forum).
- **Recommendation:** **option (a), unambiguously.** A custom forum for an MVP with zero
  community is negative-value work. Implementation: each fact page has "Challenge" →
  GitHub issue with a template prefilled with the fact ID and current sources; GitHub
  Discussions per language/feature area; CONTRIBUTING.md. The Notion page itself already wanted
  "link to GitHub discussion under each feature" — the options converge.
- **Where it breaks:** if the target expert audience turns out not to live on GitHub (academic
  PL researchers mostly do), or when volume needs triage tooling. Both are good problems, both
  are Later.

### 9. Moderation tooling — **MVP = the PR review flow; anything more Later**

- **What:** keeping bad facts out.
- **Boring implementation:** the §4 staging boundary + CI checks on every proposal (schema
  valid, source resolves, source actually contains something resembling the claim — an agent
  can do a cheap verification pass) + owner review before merge. Moderation of *user* content
  doesn't exist until user content exists (Builder, comments — Later).

### 10. Backups — **MVP (nearly free)**

- **Boring implementation:** Git *is* the backup of the source of truth (GitHub + one `git
  push` mirror to a second remote, e.g. Codeberg, via a cron/Action — protects against account
  lockout). Derived artifacts (vector index, site) need no backup: rebuildable. Agent run
  transcripts/checkpoints: a tarball synced to any cloud drive weekly. The day Postgres enters,
  the day `pg_dump` cron + offsite copy enters with it — write that into the migration plan.

### 11. Auth — **not needed for MVP. At all.**

- The site is read-only static; challenges ride on GitHub's auth; the pipeline and MCP server
  are local to the owner. First real auth need: hosted MCP endpoint or Builder module. Then:
  boring options are GitHub OAuth (audience already has it) or an API token list; do not build
  an account system.

### 12. Rate limiting toward model APIs — **MVP (small but real)**

- **What:** protecting the slow university API from the pipeline, the pipeline from Claude
  usage caps, and the wallet from runaway loops.
- **Boring implementation:** a single client wrapper used by all agent code: token-bucket
  throttle per provider, exponential backoff on 429/5xx, response cache keyed by
  (model, prompt-hash) so re-runs are free, per-run token/cost budget that hard-stops the run,
  and a one-line-per-call cost log (CSV is fine). Fifty lines of Python; pays for itself the
  first time a debate loop goes circular.

### 13. Analytics / SEO monitoring — **MVP (trivial), depth Later**

- **Boring implementation:** Google Search Console + Bing Webmaster (free, and the actual
  ground truth for SEO) + a privacy-friendly stats layer — Cloudflare Web Analytics if hosting
  there (free, no cookie banner), else GoatCounter/Plausible. Nothing self-hosted. Later:
  position tracking, Core Web Vitals dashboards — only if SEO becomes the growth strategy in
  earnest.

### Components that are *absent on purpose*

Message queues, Kubernetes/containers-as-architecture, microservices, graph DBs, managed vector
DBs (Pinecone/Weaviate), search clusters, a CMS, and a custom forum. Each is replaceable at
this scale by a script, a file, or GitHub. The whole MVP is: **one Git repo, one static site,
one directory of Python scripts, two SQLite files, cron.** Postgres itself is *Later* — the
brief's instinct ("one Postgres") is right for phase 2, but the MVP genuinely doesn't need a
database server.

## Risk register (ranked)

Scale: impact and likelihood 1–5; score = I × L. **Decision-before-code** flag marks risks that
must be settled before writing code.

| # | Risk | I | L | Score | Pre-code decision? |
|---|------|---|---|-------|--------------------|
| K1 | **Citation laundering** — agents attach real sources that don't actually support the claim; the site then *looks* rigorously sourced, which makes the failure worse than plain hallucination. The "self-backing net of information" (brief §2.4) is explicitly a feedback loop: one bad fact retrieved via RAG becomes evidence for the next. | 5 | 4 | **20** | **Yes** — verification gate design (claim↔source entailment check + human merge) and a rule that agent-generated text is never itself citable must be in the schema and pipeline from commit one. |
| K2 | **Fact-schema instability** — the concept/feature ontology (what counts as a concept vs feature vs characteristic, the edge types) *will* change as agents argue; every change invalidates existing facts, embeddings, and site URLs. | 4 | 5 | **20** | **Yes** — version the schema, keep fact IDs decoupled from taxonomy position, treat migrations-as-scripts from day one. Also freeze a v0 ontology on ~5 languages before mass generation. |
| P1 | **Differentiation vs PLDB / hyperpolyglot / Rosetta Code / programming-languages.info** — "another language comparison site" already exists several times over; PLDB alone has thousands of languages. | 5 | 4 | **20** | **Yes** — the wedge must be explicit before building: Hermes' plausible edges are (i) *per-fact academic sourcing* (nobody does this), (ii) the *typed concept graph with interaction edges* (requires/conflicts), (iii) the Builder as the long-term destination. Write the one-paragraph positioning statement first; it dictates what the MVP must prove. |
| S1 | **Solo-maintainer scope collapse** — the brief spans knowledge base + builder + selector + agent fleet + community. Solo + PoC means the realistic MVP is ~one module; trying to scaffold all of it kills the project. | 5 | 4 | **20** | **Yes** — declare the MVP cut line (recommended: knowledge base for 5–10 languages × the semantic-features layer only, + MCP + static site; Builder/Selector explicitly out). |
| P2 | **SEO cold start** — a new domain takes 6–12 months to rank for anything contested; "SEO-focused" cannot be the MVP's success metric. | 3 | 5 | **15** | No — but set expectations: MVP success = corpus quality + MCP usability + a handful of expert challenges, not traffic. Ship programmatic long-tail pages ("pattern matching in <lang>") early since the clock only starts at first index. |
| K3 | **Source rot** — URLs die; a sourcing-centric site with dead links loses its entire premise. | 4 | 4 | **16** | No — mitigated cheaply by §5 (archive.org snapshot at ingest + periodic link-check CI). Decide only that snapshotting happens at ingest, not later. |
| S2 | **API cost/limit creep** — multi-agent debate is token-hungry; Claude Pro caps + a slow university API can silently stall the pipeline or push toward paid API spend. | 3 | 4 | **12** | No — §12 wrapper + budget-per-run + caching; design debates to be *resumable* so slow APIs are an inconvenience, not a blocker. Track cost-per-accepted-fact as a first-class metric. |
| P3 | **Community cold start on challenges** — the epistemic model leans on human experts correcting agents, but a zero-traffic site gets zero challenges; unchallenged ≠ correct. | 4 | 3 | **12** | No — plan for it: seed review by directly asking specific people (language core-team members, PL researchers) to audit their language's page; treat "no challenges yet" as unverified, not verified, in the fact confidence field. |
| L1 | **Copyright on the corpus's evidence** — quoting sources: short attributed excerpts are defensible; wholesale storage/republication of book chapters (e.g. Van Roy & Haridi) or paywalled papers is not. Scraping: low risk if polite (public docs pages, robots.txt respected), but archiving full copies publicly raises it. | 4 | 3 | **12** | **Yes (licensing half)** — pick licenses now, they're near-impossible to retrofit once contributions arrive: **facts/data → CC BY-SA 4.0** (or CC BY 4.0 if maximal reuse is preferred; ODbL is the DB-specific alternative but adds friction), **code → MIT/Apache-2.0**, plus a DCO/CLA-lite line in CONTRIBUTING so external challenge-contributions are cleanly licensed. Quoting policy: excerpts ≤ a few sentences, always attributed, full texts never committed publicly. |
| K4 | **Ontology validity** — the deeper risk under K2: the feature model itself may not survive contact with real languages (the Notion page already excludes scope/exceptions/security/naming as "hard to atomize"); experts may reject the categorization wholesale, which taints every fact hung on it. | 4 | 3 | **12** | Partially — anchor the ontology on citable literature (Jordan et al., Van Roy & Haridi) rather than agent consensus, and record *dissent* as data (an "contested" edge/flag), so disagreement enriches instead of invalidates. |
| S3 | **Data migrations as schema evolves** — YAML→YAML v2→Postgres; each hop risks silent data loss across hundreds of files. | 3 | 4 | **12** | No — but adopt the discipline now: schema version stamped in every file, migration = reviewed script committed to the repo, CI validates the whole corpus on every change. Git makes every migration diffable and revertible — a real advantage of the file-based MVP. |
| K5 | **Plain hallucinated facts** (no source, or fabricated source) | 4 | 2 | **8** | No — cheapest risk to kill: CI rejects any fact without a resolvable source ID; fabricated-source risk folds into K1's entailment gate. |
| S4 | **Bus factor / motivation** — solo project with a long payoff curve; abandonment is the modal failure mode for this class of project. | 4 | 2* | 8 | No — mitigations are structural: everything-in-one-repo means the project is forkable/inheritable by design; small shippable increments (one language fully sourced is already a useful artifact). *Likelihood of pauses is high; the mitigation makes pauses non-fatal, hence scored on "unrecoverable loss". |
| L2 | **Upstream data licensing** — importing from PLDB (public domain — fine), Wikidata (CC0 — fine), hyperpolyglot (CC BY-SA — attribution + share-alike obligations), TIOBE (proprietary — link, don't ingest). | 3 | 2 | **6** | No — but keep provenance per fact (already required by the sourcing rule), which automatically satisfies attribution obligations. |
| P4 | **MCP ecosystem shift** — MCP is young; transports/spec evolve. | 2 | 3 | **6** | No — the server is a thin adapter over stable internals; churn is contained. |

**Must-decide-before-code summary (in order):** (1) MVP cut line (S1); (2) Git-as-source-of-
truth vs DB (§ framing / K2, S3); (3) v0 ontology + fact schema + stable ID scheme (K2, K4);
(4) verification-gate rules — what evidence a fact needs to merge (K1, K5); (5) positioning
paragraph vs PLDB et al. (P1); (6) licenses for data and code (L1).

## Open questions for the owner

1. **MVP cut line:** is "knowledge base only, 5–10 languages, semantic-features layer, static
   site + MCP server" an acceptable PoC scope, with Builder and Selector explicitly deferred?
2. **Git-as-database:** do you accept facts-as-YAML-in-repo as the *canonical* store for the
   MVP (Postgres deferred to phase 2), given your own option (a) leaned that way? This is the
   single most architecture-defining choice.
3. **Merge authority:** are you personally the merge gate for every agent-proposed fact in the
   MVP, and roughly how many facts/week can you realistically review? (This number, not API
   speed, is the pipeline's real throughput limit.)
4. **License comfort:** CC BY-SA 4.0 for the fact corpus and MIT/Apache-2.0 for code — any
   objection (e.g., do you want commercial reuse of the data to require share-alike, or prefer
   maximally permissive CC BY)?
5. **Positioning:** which differentiator do you want the MVP to *prove* — per-fact academic
   sourcing, the typed concept graph, or agent-debate-as-curation? (Pick one; the others ride
   along.)
6. **University API terms:** any usage/ToS constraints on the university-hosted models (data
   sent to it, output ownership, volume) that would restrict pipeline design?
7. **Budget ceiling:** is there any monthly cash budget beyond the Claude Pro subscription
   (embeddings ~$5 one-off, domain ~$10/yr, everything else in the MVP is free tier) — and a
   ceiling for API spend if debates prove worth paying for?
8. **First expert contacts:** do you have 2–3 concrete humans (colleagues, PL community
   members) willing to audit one language's facts each? The challenge channel is dead weight
   without a seeded first challenge.

## New brainstorm topics surfaced

- **Fact confidence & dissent model** — how a fact's status (proposed / agent-consensus /
  human-verified / contested / retracted) is represented, displayed on the site, and used by
  retrieval. Falls out of K1/K4/P3 and touches schema, UI, and pipeline.
- **Claim↔source entailment verification design** — the concrete mechanics of the K1 gate:
  which model checks entailment, on which excerpt, at what cost per fact, with what
  false-accept tolerance.
- **Corpus bootstrap & import strategy** — a dedicated pass on seeding from PLDB/Wikidata
  (license-clean bulk skeleton) vs pure agent generation, and how imported vs agent-derived vs
  human facts are distinguished.
- **URL & information-architecture design for SEO** — page-per-fact vs page-per-feature vs
  page-per-language-feature-pair; decides both SEO surface area and stable-ID scheme, so it
  interacts with K2 and should be settled with the schema.
- **Phase-2 dynamic backend sketch** — a one-pager for the day the Builder arrives (one VPS,
  Postgres + pgvector, the static site kept as the content front): not to build now, but to
  ensure MVP choices don't paint it out.
- **Agent debate protocol design** — turn structure, consensus criteria, dissent recording,
  and evaluation of whether debate actually beats a single careful agent + verifier (worth
  testing early; debate is the most token-expensive assumption in the brief).
