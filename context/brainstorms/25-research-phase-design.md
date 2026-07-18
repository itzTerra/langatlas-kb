# 25 — Frontloaded Ontology Research Phase Design

> Round-3 brainstorm for LangAtlas. Topic: the heavy frontloaded research phase (D11) in which
> broad-knowledge agents + internet sources design the generic language-feature landscape (the
> ontology), backed by sources — completely separate from the per-language sweep pipeline (D5),
> which is retained only for onboarding new languages later. Binding context:
> `context/decisions.md` (esp. D4, D5, D6, D11, D15, D16, D22); builds on brainstorms 04
> (multi-agent workflow), 21 (full-source RAG), 22 (ontology versioning). The initial language
> set is an **input parameter** delivered by topic 34 (tentatively TIOBE top 10, corrected for
> paradigm coverage); this document does not choose it.

## Problem framing

The research phase must turn "the brief's layer lists plus a shelf of PL-design books" into
**ontology v1.0**: a sourced, debated, layered node set (concepts, features, dimensions,
edge vocabulary) stable enough that the per-language sweep pipeline can fill feature instances
against it without constant re-carving. Five properties define success:

1. **Source-backed, not prior-backed.** Every node the phase mints must be traceable to
   literature — the same D4 rule that governs facts. Agents' broad knowledge steers *where to
   look*; only retrieved text justifies a node's existence and its carve (`claim_origin`
   discipline). Otherwise the ontology itself becomes the biggest citation-laundering artifact
   in the project (risk K1 at the schema level, feeding risk K2).
2. **Generic before specific.** The phase designs the landscape of *features* (realisations of
   concepts across the family of languages), not feature instances. Languages appear only as
   reality checks: a carve that cannot classify real languages is wrong, but per-language
   coverage is explicitly the later sweep pipeline's job.
3. **Minted under D16 rules from the first node**: immutable `id` vs renameable `slug`,
   `ontology/VERSION` at `0.x`, content-keyed IDs hashing node `id`s. Restructures during the
   phase must stay cheap (that is what 0.x is for) while still leaving an audit trail.
4. **Budget-shaped per D6.** Claude does the judgment (atomization, dimension design, debate,
   final prose); the university API does the volume (corpus tagging, extraction sweeps,
   entailment verification, embeddings). No deadline, no shortcuts that damage the long-term
   product — but also no romantic token bonfires (brainstorm 04's "never Option A" still binds).
5. **A defined exit.** v1.0.0 is declared by the developer at a coverage threshold of their
   choosing (D16); the phase's job is to *produce the evidence* on which that declaration is
   made, not to auto-trigger it.

Two structural facts shape everything below. First, **full-source RAG (D15) is the phase's
foundation**: the workload is "survey ten books at concept level," which is exactly what the
`source_chunks` index exists for; the ingestion pipeline is therefore on the critical path
before any real research starts. Second, the project already *has* a seed ontology — the
brief's layer-2/3 lists (Van Roy & Haridi-derived) and the Jordan et al. (2015) feature model.
The phase is not a blank-page exercise; it is the systematic sourcing, expansion, atomization,
and stress-testing of an existing sketch.

### What "the landscape" concretely consists of at exit

- **Concept nodes** (thin, pedagogical; includes the Concept-first staging of the excluded
  four — scope, exceptions, security, naming — per D16/O6).
- **Feature nodes** with `layer` (1/2/3), layer-3 `dimension` membership, descriptions, and
  per-node sourced *existence/definition facts* ("this feature is a recognized, distinct thing
  in the literature, defined thus").
- **The dimension list** with exclusivity modes, and the `cross_cutting` affordance in place.
- **Feature↔feature edges** (requires / enables / influences ± / conflicts-with /
  alternative-to) and feature→quality edges, each a sourced fact.
- **Rules** for known multi-feature interactions (sparse at v1.0 is fine).
- **The questionnaire compiled from the ontology** — the handoff artifact the D5 sweep
  pipeline consumes (see "Handoff" below).

## Options with trade-offs

### O1 — Phase shape: waterfall vs iterative loop vs one big design session

**1a: Strict waterfall** (ingest → survey → draft → validate → exit). Clean checkpoints, but
pretends atomization questions won't send agents back to the corpus, and that reality checks
won't reopen dimension design. They will, constantly.

**1b: One long "architect" effort** — a few giant Claude sessions drafting the whole ontology
from priors, sources decorated afterwards. Cheapest in orchestration, fastest to a plausible
draft — and exactly the prior-laundering failure mode D4 exists to prevent. The draft would
*look* excellent and be unauditable. Reject.

**1c: Staged subphases with an explicit R3→R5 iteration loop (recommended).** Fixed
infrastructure and benchmark subphases up front (they genuinely are prerequisites), then a
survey → draft → reality-check cycle that repeats per thematic area and again globally, with
each cycle's output committed and validated. Matches the filesystem-first, resumable-batch
discipline already ratified (D11 hygiene), and Pro session limits just mean "next cycle
tomorrow."

**Proposed subphase structure (1c):**

| # | Subphase | Nature | Primary tier |
|---|---|---|---|
| R0 | Infrastructure preflight | build | — (engineering) |
| R1 | Corpus assembly & ingestion | build + QA | code + university API |
| R2 | Embedding-model benchmark (D22) | eval | code + university API |
| R3 | Thematic survey (divergent) | research | university API volume, Claude synthesis |
| R4 | Ontology drafting (convergent) | design | Claude |
| R5 | Language reality checks | validation | mixed |
| R3′–R5′ | Iterate per theme / globally | loop | as above |
| R6 | Consolidation & exit report | audit | code + university API, Claude prose |

- **R0** — everything the phase depends on and cannot be retrofitted: the D15 ingestion CLI +
  `source_chunks` index; `ontology/` scaffolding with `VERSION 0.1.0`, id/slug machinery, and
  schemas (needs topic 09's v0 schemas — see dependency note in "Recommendation"); the D18
  logging wrapper (mandatory for pipeline runs); the D13 pre-commit validators; the provider
  wrapper with cost logging (D6). R0 is engineering, not research; its exit test is "an agent
  can run `search_sources`, mint a node file that validates, and the run is logged."
- **R1** — ingest the initial corpus (D15 list + topic-34 language specs + acquired canonical
  texts, see O5), with per-source extraction QA. The developer's QA skim doubles as golden-set
  authoring time (O4).
- **R2** — the D22 benchmark (O4 below). Placed after a *pilot* ingestion (3–4 sources), not
  the full corpus, so a model switch doesn't force large re-embeds — though re-embedding is
  overnight-cheap anyway, the golden set needs real chunks to point at.
- **R3** — divergent harvesting per **theme** (typing; memory management; concurrency &
  parallelism; higher-order programming & abstraction; data/ADTs & pattern matching; modules &
  encapsulation; metaprogramming & reflection; evaluation & parameter passing; effects &
  exceptions; dispatch & inheritance; syntax-layer constructs; qualities vocabulary — final
  theme list is an early R3 deliverable itself, seeded from the brief's layers). For each
  theme: bulk passes on the university API tag corpus chunks with candidate terms; a Claude
  surveyor session then synthesizes a **candidate inventory** — proposed concept/feature
  candidates, each with 1–3 evidence chunks (source + locator) and known aliases across books
  ("single-assignment store" ≡ "dataflow variable").
- **R4** — convergent design per theme: a Claude ontologist session atomizes candidates into
  feature nodes, assigns layers/dimensions, drafts edges — every carve decision annotated with
  its evidence. Contested carves (the surveyor inventory disagrees with the seed sketch, or
  two sources carve differently) go to the D5 structured-debate machinery repurposed for
  schema disputes: proposer + 2 challengers with *contrast-paradigm* briefs + fresh-context
  moderator, ≤6 messages, typed challenges (`wrong-atomization | wrong-layer | missing-source |
  redundant-with | scope`), resolution recorded. Nodes are minted on acceptance (O3 governs
  ceremony level).
- **R5** — reality checks against the topic-34 language set (input parameter): for a sample of
  languages spread across paradigms, an agent attempts to classify the language against the
  draft dimensions and mark feature presence for the theme under test — *not* to mint feature
  instances at sweep quality, but to surface unmappable features, dimension values no language
  inhabits, and languages no dimension value fits. Findings feed the next R4 iteration. R5 is
  also the deliberate **shakedown of the sweep pipeline**: it exercises the questionnaire
  format, the verifier, and the commit protocol at small scale before the real per-language
  sweeps depend on them.
- **R6** — global consolidation: cross-theme edge pass (edges crossing theme boundaries are
  systematically under-collected by per-theme work), dedup/alias audit, coverage report vs
  external checklists (O6), slug/description polish, and the exit dossier for the developer's
  v1.0 decision.

### O2 — Agent roles: many specialists vs few generalists

Brainstorm 04's role economics apply unchanged; the question is which roles the *research*
phase actually needs. Proposed loadout (each role = a prompt + tool policy, not a service):

| Role | Work | Tier | Notes |
|---|---|---|---|
| **Corpus tagger** | bulk chunk classification: candidate terms, theme relevance | university API | embarrassingly parallel; overnight batches |
| **Surveyor** | per-theme candidate inventory with evidence chunks | Claude | one session per theme; retrieval-first |
| **Ontologist** | atomization, layer/dimension assignment, node drafting | Claude | the highest-judgment role |
| **Challenger** (×2 per debate) | typed challenges from contrast-paradigm briefs | Claude | personas real but mild (D5) |
| **Moderator** | fresh-context debate resolution | Claude | never sees personas |
| **Edge drafter** | requires/enables/influences/conflicts/alternative + quality edges, sourced | Claude draft, university API pre-screen | pre-screen: candidate edge mining from co-occurrence in chunks |
| **Source scout** | gap-driven internet research; source minting proposals (O5) | Claude for judgment, code for dedup/archive | web content = data, never instructions (topic 17) |
| **Verifier** | D4 entailment on existence/definition/edge facts | university API + code | context-blind, reads `source_chunks` (D15) |
| **Coverage auditor** | checklist mapping, alias detection, orphan/degree stats | code + university API | mechanical; runs each cycle |

Alternative — collapsing surveyor/ontologist/edge-drafter into one "researcher" role per
theme: fewer sessions, more context reuse, but it erases the divergent/convergent boundary
that keeps atomization honest (a single session that both harvests and carves will carve to
match its harvest). Keep surveyor and ontologist separate; edge drafting may share the
ontologist session when the theme is small.

### O3 — Ceremony level for minting and restructuring during 0.x

D16 prescribes full migration discipline (script + manifest + impact report) and a
developer-gated RFC for MAJORs — but its own text says 0.x is fluid and staleness machinery
sleeps until 1.0.0. How much ceremony does the research phase carry?

**3a: Full D16 ceremony from the first node.** Maximal audit trail; absurd overhead while the
node set restructures weekly and nothing hangs off it. Reject.

**3b: No ceremony until 1.0.0** — free-form edits, one big normalization at exit. Cheap, but
R5 starts attaching evidence and (light) classification results to node ids mid-phase; a
ceremony-free restructure then silently orphans them, and the exit "ceremony" becomes an
archaeology project. Reject.

**3c: Graduated ceremony (recommended).**
- From the first node: immutable `id` minted once, content keys hash `id`s, every commit
  passes schema + referential-integrity validation, every run is logged (D18). These are
  free-ish and cannot be retrofitted.
- While a theme is in active R3/R4 iteration: restructures are ordinary commits; CI auto-bumps
  0.x MINOR for additions; a split/merge needs only a one-line `redirects.yaml`/tombstone
  entry so ids never dangle — no migration script, no RFC, no developer gate.
- Once a theme passes its R5 check, it is marked **settled**; restructuring a settled theme
  requires the lightweight middle form — a migration manifest (machine-readable disposition of
  affected nodes/evidence) but still no RFC gate, since 0.x MAJOR semantics are suspended.
- The full D16 process (RFC + gated MAJORs + staleness) switches on at 1.0.0 exactly as
  ratified.

### O4 — The embedding-model benchmark subphase (D22)

**What is benchmarked.** Candidates × use cases × pipeline variants:

- *Models*: `qwen3-embedding-4b` (incumbent default per D15), `multilingual-e5-large-instruct`,
  `mxbai-embed-large`, `nomic-embed-text-v1.5`/`v2-moe` (all university-hosted), plus one
  local-CPU fastembed representative (e.g. bge-small-class) as the "does free-and-local
  suffice" floor. English-only models are eligible (D7).
- *Use cases*: (i) **source-corpus retrieval** — the phase's daily workload and the verifier's
  substrate; benchmark now. (ii) **fact index** — no real facts exist yet; benchmark with a
  proxy set over draft node descriptions late in the phase, and re-run properly when the sweep
  pipeline starts. (iii) **debate-history** (D18 v2) — defer entirely; it is a v2 index.
- *Variants*: vector-only vs hybrid FTS+RRF vs hybrid+`qwen3-reranker-4b`; chunk-size
  sensitivity (400 vs 800 target) as a secondary axis. Short-context models (512) get their
  honest treatment: breadcrumb-prefixed chunks truncated as they would be in production.

**Golden-set eval.** Extend the D7 committed golden set with 40–60 source-retrieval queries →
expected chunk/section IDs, in three deliberate difficulty bands: exact-term ("call-by-need"),
paraphrase/concept ("waiting on unbound variables" → VR&H dataflow sections — the band that
justifies RAG over grep at all), and cross-source survey ("which sources define parametric
polymorphism" → expected multi-source hit set). Authored during R1 QA skims (the developer +
a Claude session reading alongside), grown later from logged agent misses per D7. Metrics:
Recall@5 and nDCG@10 post-rerank, Recall@50 pre-rerank (candidate generation quality), MRR;
plus operational columns — query latency on the university API, indexing throughput, vector
storage. All in pytest, committed, rerunnable (this is generic MTEB-style methodology
(Muennighoff et al. 2023) narrowed to a domain-specific golden set — domain sets beat public
leaderboard rank for a corpus this specialized).

**Decision criteria** (*proposed*): per-table decisions (the two-table design allows differing
models). The incumbent `qwen3-embedding-4b` stays unless a challenger beats it by ≥5 points
Recall@5 or matches it within 2 points while being local-CPU-capable (removes the
university-API availability dependency for re-indexing). Reranker stays default-on unless it
adds <2 points nDCG@10 (then it becomes flag-only). Hybrid-vs-vector-only follows the same
2-point rule. Record the verdict in the eval report; D22's "default stands until the benchmark
says otherwise" is thereby discharged.

### O5 — Source acquisition: curated-corpus-first vs web-wide research

**5a: Web-first breadth** — agents roam the open web harvesting feature discussions. Maximum
coverage of modern/niche features, but tier-C/D-heavy, injection-exposed, and it inverts the
quality gradient: the canonical texts already cover ~90% of the landscape at tier A/B. Reject
as the *primary* mode.

**5b: Curated-corpus-first with gap-driven internet research (recommended).**
- **Seed corpus** = the ratified D15 list (VR&H CTM; Pierce TAPL + ATTAPL; Cardelli & Wegner
  1985; the two Elsevier papers; Software Foundations vol. 2) + Jordan et al. (2015) + the
  official specs/reference chapters of the topic-34 language set.
- **Proposed acquisitions** (all standard PL-design syntheses; each covers carve territory the
  seed corpus treats only formally): Scott, *Programming Language Pragmatics* (the single best
  feature-taxonomy companion); Turbak & Gifford, *Design Concepts in Programming Languages*;
  Harper, *Practical Foundations for Programming Languages* (free author PDF); Krishnamurthi,
  *Programming Languages: Application and Interpretation* (free); Sebesta, *Concepts of
  Programming Languages* (workhorse undergraduate taxonomy; useful precisely because its
  carves are conventional); Kaijanaho (2015) for the quality-impact/evidence side (free
  thesis; systematically maps empirical evidence about language-design choices — directly
  feeds feature→quality edges with tier-A backing). Paid titles route through university
  library access per D15's paywalled-paper flow (agents request; the developer fetches).
- **Gap-driven internet research**: when the coverage auditor or a surveyor flags a feature
  with no adequate source (typical for post-2010 features: async/await fine points, effect
  handlers, ownership/borrowing, gradual typing), the source scout searches for tier-A/B
  material (papers via DOI, official design docs/RFCs of languages — Rust RFCs, PEPs, JEPs
  are tier-B official docs and superb locator-friendly sources). Minting follows D3/D4
  automation: dedup → tier assignment → Wayback archive → registry commit (logged, ungated).
  D14 constraints bind: community aggregators (PLDB, Hyperpolyglot, Wikipedia) are finding
  aids and corroboration only, never sole backing and never copied; robots/TDM opt-outs
  respected; quote caps enforced.
- **Acquisition loop cadence**: batch source-minting per theme (a theme's survey opens with a
  "do we have the literature for this?" check) rather than ad-hoc per node — keeps ingestion
  QA batched and the corpus deliberate.

### O6 — Exit evidence: what the v1.0 dossier contains

The developer declares v1.0 (D16); options differ on what evidence the phase owes them.
A bare "the agents think it's done" is worthless; a rigid auto-trigger contradicts D16.
**Recommended: a standing coverage dossier, recomputed each R6 cycle**, containing:

1. **External-checklist coverage**: every item in the brief's layer-2/3 lists, Jordan et al.'s
   feature model, and VR&H's concept index is either mapped to a node or explicitly
   dispositioned (merged-into / deferred / excluded-with-rationale). PLDB's feature list is
   used as a *finding aid* (D14) for a "did we miss anything the community tracks?" diff —
   corroboration of completeness, never imported content.
2. **Sourcing integrity**: 100% of nodes carry ≥1 verified tier-A/B existence/definition fact;
   % of edges verified; verifier pass-rate trend.
3. **Reality-check results**: % of features encountered in R5 language checks that were
   unmappable (*proposed* readiness bar: <5% over the final cycle), and zero known languages
   violating hard dimension-exclusivity constraints.
4. **Churn trend**: settled-theme restructures per cycle, trending toward zero across the last
   two cycles (K2's empirical measure).
5. **Graph health**: orphan nodes, edge-degree distribution, cross-theme edge coverage.
6. **Pipeline readiness**: golden-set eval green under the chosen embedding config; R5
   shakedown issues closed; questionnaire compiler producing valid sweeps.

The developer reads the dossier and declares — possibly choosing a threshold stricter or
looser than the proposed bars; the dossier format is designed so the declaration is a
documented judgment, not a vibe.

## Recommendation

*Proposed* — the developer ratifies:

1. **Adopt the R0–R6 staged structure with the R3→R5 per-theme iteration loop (O1c).**
   Waterfall only for the genuine prerequisites (R0 infrastructure, R1 pilot ingestion, R2
   benchmark); everything after runs as committed, resumable, per-theme cycles under the
   graduated 0.x ceremony (O3c: ids + validation always; manifests only for settled themes;
   full D16 process from 1.0.0).
2. **Sequence the dependency correctly**: topic 09 (v0 schemas + stable-ID scheme) and topic
   28's locator grammar are R0 inputs — schedule 09 before or alongside R0; the research phase
   cannot mint a node without a schema to validate against. Topic 34's language list is needed
   by R1 (spec ingestion) and R5 (reality checks) — it runs in parallel now and is treated
   here as an input parameter.
3. **Roles per O2**: tagger/verifier/auditor volume on the university API; surveyor,
   ontologist, challengers, moderator, edge-drafter judgment on Claude; the D5 debate
   machinery reused for contested carves with schema-dispute challenge types. Cost log tracks
   **cost-per-accepted-node** (the phase's analogue of cost-per-accepted-fact).
4. **Full-source RAG grounds everything (D15)**: retrieval-first prompts (search → expand
   parent section → read → then write), machine-produced locators copied into every evidence
   entry, the grep complement for exact terms, and the verifier reading the same
   `source_chunks` table. No node without evidence chunks; priors are search guidance only.
5. **Run the D22 benchmark as R2 on a pilot corpus** with the golden set, metrics, and
   decision criteria of O4; per-table verdicts; fact-index benchmark deferred to a proxy run
   late in the phase + a real re-run at sweep start.
6. **Source strategy per O5b**: seed corpus + proposed acquisitions (Scott, Turbak & Gifford,
   Harper, Krishnamurthi, Sebesta, Kaijanaho) + gap-driven scouting into papers and official
   language design docs (RFCs/PEPs/JEPs), all under D3/D14 minting rules.
7. **Exit via the O6 coverage dossier**, recomputed each consolidation cycle; the developer
   declares v1.0.0 against it (D16), which flips on full ontology governance and hands the
   sweep pipeline its inputs.
8. **Handoff to the per-language sweep pipeline (D5)**: the phase's terminal artifacts are
   (a) ontology v1.0.0 (nodes, dimensions, edges, rules, slugs/redirects); (b) the
   **questionnaire compiler** — a build step deriving the per-feature sweep questionnaire
   from the ontology, so the questionnaire can never drift from the node set; (c) the
   ingested + QA'd source corpus including the initial languages' specs; (d) the benchmarked
   retrieval stack; (e) a shaken-down verifier and commit protocol. Sweeps stamp
   `ontology_version`; onboarding language N+1 later touches only the sweep pipeline, never
   the research machinery — unless sweeps surface carve failures, which re-enter as ordinary
   post-1.0 D16 RFCs.

**Budget sanity** (*proposed*, order-of-magnitude): R3+R4 ≈ 2–3 Claude sessions per theme ×
~12 themes ≈ 30–40 sessions, plus ~10–15 for debates, R5, and R6 cycles — comfortably
spreadable over weeks under Pro limits with no calendar pressure (D6/D11). University-API
work (tagging, verification, embeddings, audits) is overnight-batch and effectively free.
The single largest engineering cost remains R0/R1 (the D15 estimate: ~1–2 focused weeks for
ingestion + 0.5–2 h QA per book) — already accepted as a precondition of D11.

## Open questions for the developer

1. **Graduated 0.x ceremony (O3c)** — confirm that during 0.x, un-settled-theme restructures
   need no migration scripts/RFCs (only id immutability + redirect/tombstone lines), settled
   themes need manifests, and the full D16 gate starts at 1.0.0.
2. **Acquisitions**: which of the proposed texts (Scott, Turbak & Gifford, Sebesta — the paid
   ones; Harper, Krishnamurthi, Kaijanaho are free) should actually be obtained via
   university library / purchase for ingestion?
3. **Golden-set co-authoring**: are you willing to spend part of the R1 QA skims co-authoring
   ~40–60 retrieval queries with expected answers? (The benchmark's value hinges on
   human-vetted expectations; agent-only golden sets grade their own homework.)
4. **Reality-check breadth (R5)**: classify *all* languages of the topic-34 set per theme, or
   a rotating sample of 4–5 chosen for paradigm spread per cycle? (Recommendation: sample;
   full coverage is the sweep pipeline's job.)
5. **Proposed exit bars** — sanity-check the dossier thresholds: <5% unmappable features in
   the final R5 cycle, zero exclusivity violations, 100% tier-A/B-backed nodes, churn ≈ 0
   across the last two cycles. Do you want any bar pre-declared as binding now, or all held
   loosely until the dossier exists?
6. **Fact-index benchmark timing**: accept deferring the fact-index embedding decision to a
   proxy run late in the phase + a real re-run at sweep start (source-corpus decision lands
   in R2 regardless)?
7. **Theme list sign-off**: the R3 theme decomposition (the ~12 survey themes) is itself a
   carve — do you want to ratify it explicitly when R3 opens, or leave it fully to the phase?

## New brainstorm topics surfaced

- **Questionnaire compiler design** — the build step deriving the D5 sweep questionnaire from
  ontology nodes (question templates per layer/dimension, evidence expectations per question,
  versioning against `ontology_version`); the concrete handoff contract between this phase
  and the sweep pipeline (extends topics 20 and 09).
- **Existence/definition fact type** — schema and verification semantics for the research
  phase's node-backing facts ("the literature recognizes and defines feature X"): how
  entailment differs from instance-fact entailment, and how these facts render (or stay
  internal) on the site (feeds topics 09, 11, 12).
- **Coverage-audit tooling** — the checklist-mapping harness (brief lists, Jordan et al.,
  VR&H index, PLDB-as-finding-aid diff), alias detection across sources, and the dossier
  generator (feeds the D16 v1.0 declaration; relates to topic 29's blast-radius tooling).
- **Theme decomposition & cross-theme edge pass method** — how to slice the survey so
  cross-cutting edges (e.g. typing × dispatch) aren't systematically dropped by per-theme
  work; possibly a dedicated edge-mining pass design (extends 16's instrumentation questions).
- **Design-doc source class** — Rust RFCs / PEPs / JEPs as a first-class source type:
  locator conventions (RFC number + section), tier placement, version-pinning, and their
  special value for `since` verification (feeds topics 28 and 11).

## Sources

- Muennighoff, N., Tazi, N., Magne, L., & Reimers, N. (2023). MTEB: Massive Text Embedding
  Benchmark. *EACL 2023*. https://arxiv.org/abs/2210.07316
- Kaijanaho, A.-J. (2015). *Evidence-Based Programming Language Design: A Philosophical and
  Methodological Exploration.* PhD thesis, University of Jyväskylä.
  https://jyx.jyu.fi/handle/123456789/47698
- Harper, R. (2016). *Practical Foundations for Programming Languages* (2nd ed.). Cambridge
  University Press. Free author edition: https://www.cs.cmu.edu/~rwh/pfpl/
- Krishnamurthi, S. *Programming Languages: Application and Interpretation.* Free online:
  https://www.plai.org/
- Scott, M. L. (2015). *Programming Language Pragmatics* (4th ed.). Morgan Kaufmann.
- Turbak, F., & Gifford, D. (2008). *Design Concepts in Programming Languages.* MIT Press.
- Sebesta, R. W. (2019). *Concepts of Programming Languages* (12th ed.). Pearson.
- (Previously cited in project docs: Jordan et al. 2015; Van Roy & Haridi 2003 — see
  CLAUDE.md Sources.)
