# LangAtlas Stage 3 — R3→R5 theme cycles (sequencing map)

> **For agentic workers:** this document sequences Stage 3's sub-plans and their interface
> contracts only. It is **not** a bite-sized task plan. Per the writing-plans Scope Check, each
> sub-plan below gets its own full implementation plan
> (`docs/superpowers/plans/YYYY-MM-DD-stage-3<letter>-<name>.md`, written with
> superpowers:writing-plans) at the point that sub-plan actually starts — not now, and not all at
> once, since later sub-plans depend on artifacts earlier ones haven't produced yet (a real
> candidate inventory, real minted nodes, real debate records).

**Goal:** Turn Stage 2's calibrated, benchmarked, QA'd corpus into a **sourced ontology** — the
first real `concepts/`, `features/`, `edges/`, `rules/` records and the layer-3 dimension
vocabulary — by building the R3→R5 cycle machinery once and then running it ~12 times, one theme
per cycle, each cycle gated on the developer's sign-off.

**Architecture:** Six sub-plans. 3A builds the research spine (cycle bookkeeping, developer
sign-off gate, the node-minting path, 0.x version ceremony). 3B builds R3's divergent survey (bulk
corpus tagger + Claude surveyor + source scout). 3C builds R4's convergent drafting and the D5
debate machinery with schema-dispute challenge types, plus D30 instrumentation. 3D builds the D21
controversy assessor. 3E builds the D46 questionnaire compiler and R5's reality-check runner.
3F builds R6 consolidation: `tools/coverage/report.py`, the settled-theme migration ceremony, and
the per-cycle runbook. 3A gates everything; 3B→3C→3E are strictly sequential within a cycle; 3D
and 3F can be built in either order once 3C lands.

**Then the stage runs**: cycle 1 is the shakedown that 3A–3F are built against; cycles 2–12 are
*executions of the runbook*, not new plans. Stage 3 ends when the developer stops calling cycles,
which is Stage 4's entry.

**Tech Stack:** the Stage 1 + Stage 2 packages, used as-is — `langatlas_validate`
(`validate_record`, `normalize_record`, `validate_store`, `iter_store_records`, `build_claim`,
`fact_id`, `canonical_endpoints`, `canonical_when_all`), `langatlas_pipeline` (`RunContext` with
completion / Claude / embedding / rerank channels, prompt registry, transcript writer, D31
delimiting), `langatlas_ingest` (`search_sources`, `get_source_section`, `sdk_source_tools`,
`SourcingQueue`, the D24 verifier `verify_pair` + `nightly-verification`),
`langatlas_finding_aids` (`build_checklist`, `search_finding_aids`), `langatlas_commit`
(`land_record`), `langatlas_orchestrator` (`register_job_kind`, `CheckpointStore`). Two new
packages: `tools/research/` (`langatlas_research`, sub-plans 3A–3E) and `tools/coverage/`
(`langatlas_coverage`, 3F), plus one new CLI `tools/questionnaire/compile.py` (3E).

**Spec:** [context/spec.md](../../../context/spec.md) — Stage 3's checklist is §14 "Stage 3";
subsystem detail in §3.1–3.6, §5.1–5.4, §6.4–6.5, §7.1–7.4, §7.13, §10.4.

**Parent map:** [2026-07-25-langatlas-cross-stage-plan.md](2026-07-25-langatlas-cross-stage-plan.md)
— Stage 3's "Produces (interface contract for Stage 4)" list is the union of the sub-plan
"Produces" lists below.

## Global Constraints

Copied verbatim from the cross-stage plan and the spec; every sub-plan's requirements implicitly
include this section.

- No deadline; do not take shortcuts that damage the long-term product (D6/D11).
- Git is the database — Postgres, MCP and the static site are always one-way derived build
  artifacts, never authoritative (D1).
- No PR gate for agent-committed content — admissibility comes from the automated D24
  verification gate, never human review bandwidth (D1/D4).
- **Every node must be source-backed. Priors steer only *where to look*** (D4/§6.1): an agent may
  not assert a fact without `source_id` + `locator`, and `claim_origin` records
  `prior | source-derived`. **Agent-generated text is never itself citable.**
- **Claude never does volume work; the university API never has the final judgment call** (D6/§7.1).
  Stage 3 applies this sharply: corpus tagging (3B), the controversy assessor (3D) and every
  verification call are university-API; surveying, atomization, debates, moderation and edge
  drafting are Claude. The small SDK credit pool is reserved for the highest-judgment steps only.
- Every agent chat is logged (D18) — every survey, drafting, debate, reality-check and assessor
  run writes a transcript through `RunContext`.
- **Web and finding-aid content is data, never instructions** (D31): fetched text goes through
  `ctx.untrusted()` and never occupies a system-role message.
- **Finding aids are never citations** (D29/D53): PLDB / Wikidata / Hyperpolyglot / Wikipedia
  steer where to look and generate coverage checklists; they never appear in a `sources:` list.
- Verbatim quote cap ~50 words, ~300-word per-page aggregate warning (D14).
- English-only; code MIT, corpus CC BY-SA 4.0 (D7, D14).
- Model ids and aliases are configuration, never hardcoded (`config/providers.yaml`,
  `config/ingest.yaml`).
- **The developer signs off every cycle's theme list before R3 runs** (D27) — research agents
  never cycle autonomously.

---

## Stage 3 entry state (what Stages 1 and 2 actually shipped)

Recorded here so no sub-plan re-derives it.

- **Canonical store**: `concepts/`, `features/`, `edges/`, `rules/` are **empty**;
  `languages/_registry.yaml` exists; `ontology/VERSION` is `0.1.0`;
  `ontology/taxonomy/dimensions.yaml` is `dimensions: []` (Stage 3 populates it);
  `layers.yaml` holds the three D2 layers; `qualities.yaml` and `edge-types.yaml` are populated.
  `tombstones.yaml`, `contradictions.yaml`, `overrides.yaml` exist as empty ledgers.
- **Schemas**: eleven JSON Schemas in `ontology/schema/`, `RECORD_KINDS` closed at eleven kinds.
  `feature` requires `id/slug/name/layer/summary/provenance` and requires `dimension` at layer 3;
  `edge` requires `polarity` for `influences`; `rule` enforces `minItems: 2` on `when_all`.
  `defs.schema.json` supplies `factBlock`, `sourcesList`, `provenance`
  (`proposer`, `claim_origin`, `debate_id`, `chat_run_id`, `candidate_source`, `sampling`).
- **Validation**: `validate_store(repo_root)` checks schema validity, normalization drift,
  claim-template self-check, `alternative-to` endpoint ordering, `when_all` ordering, and source
  `acquisition_note` presence. It does **not** yet check referential integrity or filename/id
  agreement — 3A adds both, because Stage 3 is the first stage that mints nodes at all.
- **Corpus**: ~30 QA'd sources ingested, `source_chunks` populated with real chunk ids, pinned
  source-corpus embedding model from the D22 benchmark, `search_sources` / `get_source_section`
  live on both session shapes.
- **Verifier**: calibrated D24 verifier at FA ≤2% / FR ≤10%, canaries wired,
  `benchmarks/d24-verifier/calibration.json` committed, `nightly-verification` a real job kind.
  **Stage 3 treats the calibration as a fixed input — it reads the gate, it never re-derives it.**
- **Golden sets**: `tests/golden/{verifier,controversy,retrieval}/` populated;
  `tests/golden/debates/` exists with a README and **no items** — 3C fills it.
  `goldens.controversy_assessor_entry_point` is null — 3D fills it.
- **Finding aids**: `build_checklist(ctx, theme_slug)` produces an R3 coverage checklist pinned to
  a mirror version; `config/finding-aids.yaml` carries one seed theme (`type-systems`) —
  **Stage 3 owns the real theme list.**
- **Jobs**: eight real job kinds; `jobs/deferred.py` holds only the Stage 5
  (`backstop-sweep-18mo`) and Stage 6 (`monthly-demand-export`) stubs. 3D adds one more kind.

**Not built by Stages 1–2, named here so no sub-plan assumes it:**

- No `knowledge_embeddings` table and no fact-embedding index (§8.3/D62) — Stage 5. The **D59
  cross-fact scan therefore cannot run in Stage 3**; `contradiction.schema.json` admits
  `type: cross-fact` but nothing mints one until Stage 5.
- No reconciler, no per-language sweep runner, no parallel independent sweeps — Stage 5. 3E's
  reality checks are deliberately a *small-scale shakedown* of the questionnaire/verifier/commit
  path, not the sweep pipeline.
- No D38 blast-radius script, no RFC intake, no `/changelog/ontology/` pages — Stage 4 (the
  governance flip) and Stage 6 (the site). 3F builds only the **settled-theme** slice: manifest
  schema, `migrate.py` interpreter, tombstone chain walking.
- No human-challenge path, no `overrides.yaml` writer — Stage 6.
- No transcript/video extractor and no repo-file ingestion backend, so `t=HH:MM:SS` and
  `<sha7>:<path>#LN-LM` locators validate but never resolve; a citing claim parks in the sourcing
  queue. If a theme's scouting (3B) turns up a source that needs one, that is a finding to
  surface, not a silent fix.

---

## Sub-plan sequence

### 3A — Research spine: cycles, sign-off, and the node-minting path

**Gate:** none (first sub-plan; gates 3B–3F).

The deterministic, provider-free core. Everything else in Stage 3 is an agent role that ends by
calling into 3A's minting path, so 3A is written and tested first with hand-written inputs —
no model in the loop.

**Consumes:** `langatlas_validate` (schemas, `validate_record`, `normalize_record`,
`validate_store`, id composition), `langatlas_commit.land_record`, `langatlas_pipeline.RunContext`
(for `chat_run_id` provenance only).

**Produces:**
- **`tools/research/`** — a new `langatlas_research` package and `langatlas-research` CLI, sibling
  to the existing tool packages, wired into CI.
- **The `research/` directory contract**: `research/themes.yaml`, `research/cycles/<NN>-<theme>.yaml`,
  `research/surveys/`, `research/debates/`, `research/reality-checks/`, each with a README saying
  what writes it and what reads it. Research artifacts are **committed bookkeeping, not canonical
  store** — they are validated by `langatlas_research`'s own schemas under `research/schema/`,
  and `iter_store_records` deliberately does not walk them.
- **The ~12-theme list** seeded from §7.4 (typing; memory management; concurrency; higher-order
  programming; ADTs & pattern matching; modules; metaprogramming; evaluation & parameter passing;
  effects & exceptions; dispatch & inheritance; syntax-layer constructs; qualities vocabulary) —
  seeded, **not frozen**: §7.4 makes the final theme list itself an early R3 deliverable.
- **The developer sign-off gate** (D27, the one hard checkpoint inside Stage 3): a cycle file
  carries `signed_off: {by, date, theme_digest}` where the digest binds the sign-off to the exact
  theme entry signed. `require_sign_off(cycle)` raises unless the digest still matches — so
  editing a theme after sign-off re-opens the gate instead of silently passing it.
- **The minting path** (`langatlas_research.mint`): `ConceptDraft`, `FeatureDraft`, `EdgeDraft`,
  `RuleDraft` → normalized, schema-valid YAML at the §3.3 path, landed one record per commit
  through `land_record` with `chat_run_id` provenance. Mint-time refusal on an unsourced node
  (D4) and on a degenerate 1-antecedent rule (D64).
- **Dimension minting** — the layer-3 dimension vocabulary in
  `ontology/taxonomy/dimensions.yaml`, with `exclusivity` (default `exclusive`, D39) and
  `applies_to` (default `[general-purpose]`, D50) written pre-emptively.
- **Referential integrity in `validate_store`** — every edge endpoint, `realizes` target and
  `when_all`/`then` antecedent names a committed node; every record's filename agrees with its
  id (§3.3's `edges/<from-id>/<type>--<to-id>.yaml` included). Stage 3 is the first stage where
  these can fail, so it is the stage that adds them.
- **The 0.x minting ceremony** (§7.4/§5.1): `langatlas-validate version-bump` classifying a
  store diff as additive / restructuring / cosmetic, auto-bumping `ontology/VERSION` MINOR
  (PATCH for cosmetic-only) and appending to `ontology/CHANGELOG.md` from CI on `main`. During
  `0.x` a restructure is an ordinary MINOR — the RFC-gated MAJOR machinery switches on at
  `1.0.0` (Stage 4), and 3F adds the settled-theme manifest requirement on top.

**Produces for 3B–3F:** the cycle record shape, `require_sign_off`, and the `mint_*` signatures
every agent role ends at. **Write its detailed plan first.**

**Developer checkpoints:** approving the seed theme list; every per-cycle sign-off thereafter.

**Spec pointer:** §3.1–3.3, §3.5, §5.1, §7.4 (ceremony), §7.9.

---

### 3B — R3 thematic survey (divergent)

**Gate:** 3A landed, and cycle 1's theme signed off.

**Consumes:** 3A's cycle records + `require_sign_off`; `search_sources` / `get_source_section` on
both session shapes; `build_checklist(ctx, theme_slug)` from 2E; `SourcingQueue.file`;
`RunContext`'s completion channel (bulk) and Claude channel (judgment); the prompt registry.

**Produces:**
- **The corpus tagger** — a university-API bulk pass over the theme's candidate `source_chunks`,
  tagging each chunk with candidate terms. Embarrassingly parallel, checkpointed through
  `CheckpointStore` so an interrupted pass resumes, budget-bounded through `RunContext`. This is
  the volume lane: Claude never runs it.
- **The surveyor** (Claude) — synthesizes the tagged chunks plus the finding-aid checklist into a
  **candidate inventory**, `research/surveys/<cycle>-<theme>.yaml`: one entry per candidate with
  a name, a one-line gloss, **1–3 evidence chunk ids**, and cross-book aliases. Candidates are
  not nodes and are never committed to the canonical store.
- **The source scout** (Claude) — gap-driven internet scouting for candidates the corpus cannot
  evidence (typical for post-2010 features): papers and official design docs (Rust RFCs, PEPs,
  JEPs), batched per theme, filed into `sourcing_queue` as `pending-source`. Fetched pages go
  through `ctx.untrusted()`; **nothing the scout fetches is citable until it is ingested as a
  real source record.**
- **Theme-list amendment** — the survey may propose theme-list edits (§7.4 makes the final list an
  R3 deliverable); amendments land in `research/themes.yaml` and **re-open the sign-off gate** for
  any cycle whose digest they invalidate.

**Produces for 3C:** the candidate inventory file 3C's ontologist atomizes, with evidence already
bound to real chunk ids.

**Spec pointer:** §7.4 (R3), §4.5, §7.8, §8.2.

---

### 3C — R4 ontology drafting & the D5 debate machinery (convergent)

**Gate:** 3B produced a real candidate inventory for the cycle's theme.

**Consumes:** 3B's inventory; 3A's `mint_*` path; the D24 verifier (`verify_pair`) as the
admissibility gate on every node's existence/definition facts; `RunContext`'s Claude channel with
`agents=` and `debate_id=`; the prompt registry.

**Produces:**
- **The ontologist** (Claude) — atomizes candidates into Concept/Feature nodes, assigns
  `layer` and (at layer 3) `dimension`, sets `cross_cutting` and `aliases`, and annotates every
  carve with its evidence. Mints through 3A, one record per commit.
- **The edge drafter** (Claude, a separate role by design — §7.4 keeps surveyor/ontologist/edge
  drafter distinct so no agent carves to match its own harvest) — drafts the five feature↔feature
  edge types plus signed `affects-quality` edges.
- **The D5 debate machinery repurposed for schema disputes** — proposer + 2 challengers +
  **fresh-context** moderator, ≤6 messages, mild real personas, with R4's typed challenge
  vocabulary `wrong-atomization | wrong-layer | missing-source | redundant-with | scope`.
  Contested carves only; a debate is never free chat. Resolutions are structured blocks, and the
  `debate_id` lands in each affected record's `provenance`.
- **Debate records** under `research/debates/<debate-id>.yaml`, plus the first items in
  `tests/golden/debates/` (2B created the directory empty by design).
- **The debate-outcome contradiction mint path** (D45) — one of the four legal minting paths into
  `contradictions.yaml`; `partial` verdicts never mint.
- **D30 instrumentation** — the two zero-new-infrastructure scripts: the **verifier-replay
  counterfactual** (re-score a debate's pre-challenge draft through the verifier to see whether
  the challenger round changed anything detectable) and the **cost join**
  (Claude-messages-per-accepted-node segmented by `debate_id`). Both read existing logs.
- **R4 outcome tracking** — each debated carve's outcome recorded so Stage 4+ can ask whether a
  carve that survived R4 sign-off later got reverted (the D30 MAJOR-churn question).

**Produces for 3D/3E/3F:** real nodes and edges in the canonical store; debate records and
verification verdicts as the structured inputs 3D's assessor reads; the ontology subtree 3E's
questionnaire compiler compiles.

**Spec pointer:** §7.2 (debate shape), §7.4 (R4), §7.13, §6.5, §3.6.

---

### 3D — The controversy assessor (D21/D25)

**Gate:** 3C producing debate records and verification verdicts (the assessor's inputs).

**Consumes:** debate records, reconciler conflicts + contradiction register, verification
verdicts, mechanically-computed source-strength context, assessment spread — **structured inputs
only**; 2B's bootstrap controversy cases and `run_controversy_goldens`;
`register_job_kind`.

**Produces:**
- **The assessor** — university-API `thinker` (`deepseek-v4-pro-thinking`) over a fixed rubric,
  emitting one of four ordinal levels (`0 settled | 1 noted-variance | 2 contested |
  3 disputed`). Output is a **machine-written block in the canonical record whose `signals` list
  of machine references *is* the justification** — no free-prose rationale; an absent block means
  level 0.
- **Claude escalation** for adjacent-level ambiguity and **all level-3 assignments**, with each
  escalation review hand-labelled into `tests/golden/controversy/` (the opportunistic lane that
  grows 2B's ~15–20 bootstrap cases toward the ~50-case target).
- **Exclusions enforced in code, not prose**: nothing human-challenge-derived reaches the
  assessor — no GitHub activity, and not a contradiction record's
  `closure_attempt.outcome: confirmed-open` (withdrawn 2026-07-20); open contradiction records
  feed it only through their machine-produced content. **The assessor never mints contradiction
  records.**
- **Event-driven nightly batching** — unchanged inputs ⇒ unchanged level (so a re-run is free);
  registered as a job kind and wired into `crontab.example`.
- `goldens.controversy_assessor_entry_point` pointed at the real assessor, and a scored run
  against the controversy golden set.

**Spec pointer:** §6.4, §6.3, §6.5, §7.11.

---

### 3E — R5 reality checks & the D46 questionnaire compiler

**Gate:** 3C settled a theme's draft nodes and dimensions.

**Consumes:** the committed ontology subtree; 3A's cycle record (which carries the cycle's
rotating language sample); the D24 verifier; `land_record`; the phase-1 language specs ingested in
2A.

**Produces:**
- **`tools/questionnaire/compile.py`** (D46) — the deterministic compiler, six mechanical steps,
  zero judgment calls. Emits sweep items **only for the four fact-bearing FeatureInstance fields**
  (`exists` / `since` / `characteristics` / `syntax`); everything ontology-authored compiles
  instead into a `constraints:` list. Per-dimension grouped items carrying `exclusivity` context
  once, standalone flat items for layer-1/2 features, every item's `anchor_prefix` matching the
  `fi.<lang>.<feature>` scheme, the mechanical `applies_to` mask (D50) as the only filtering,
  each spec stamped with its `ontology_version` and committed as a diffable artifact. A
  schema-shape regression fixture guards vocabulary drift, starting `mode: soft` per D48.
- **The reality-check runner** — a **rotating 4–5-language sample per cycle** (paradigm spread,
  drawn by 3A's planner from the D28 15-language set) classified against the draft dimensions,
  every answer run through the D24 verifier and recorded — *amended 2026-09-18 (D68): R5 mints
  no FeatureInstance records and registers no languages* (minting would break D28's phase order,
  D49's `not-yet-onboarded` state and D5/D34 sweep independence); the commit protocol is still
  exercised by landing the compiled spec and the reality-check file.
  **This is deliberately not the sweep pipeline** (no independent parallel sweeps, no reconciler —
  Stage 5): it is the shakedown of the questionnaire format, the verifier and the commit protocol.
- **`research/reality-checks/<cycle>-<theme>.yaml`** (D52's named authored artifact, the one
  dossier item that is not pure computation) — structured findings: unmappable features,
  uninhabited dimension values, unfittable languages, exclusivity violations.
- **A shakedown issue log** — every friction the run exposes in the compiler, verifier or commit
  protocol, so Stage 4's "pipeline readiness" dossier item has something real to read.

**Spec pointer:** §7.3, §7.4 (R5), §7.5, §10.4, §6.6.

---

### 3F — R6 consolidation, coverage dossier & the cycle runbook

**Gate:** one cycle has passed R5 (so there is something to consolidate and something to settle).

**Consumes:** the whole canonical store; `research/reality-checks/*.yaml`; the cost log; the
verification ledger.

**Produces:**
- **`tools/coverage/report.py`** on a shared `langatlas_coverage.metrics` library ("instance
  count per node, keyed by immutable id", computed once), with **`dossier`** (the five-item R6
  exit dossier: sourcing integrity; reality-check results; churn trend; graph health; pipeline
  readiness — external-checklist coverage is **dropped**, D27/D52 amendment 2026-07-19) and
  **`gaps`** (`<dimension, value>` corroborating-instance counts against `--min-instances`
  default 2, report-only, explicitly near-meaningless before Stage 5 phase 1). `demand` is
  Stage 6. Output is **ephemeral** — stdout plus an optional gitignored snapshot, never a
  committed audit trail.
- **The cross-theme edge pass** — per-theme work systematically under-collects boundary-crossing
  edges, so R6 runs an explicit pass for them, plus the **dedup/alias audit** and **slug polish**
  (slug changes are PATCH events resolved through `ontology/redirects.yaml`).
- **The settled-theme ceremony** — marking a theme settled in its cycle record, and from then on
  requiring a **lightweight migration manifest** for restructures: the D38 disposition DSL
  (`op: split | merge | move | remove` carrying a `fact_remap` of matcher→action entries over the
  closed vocabulary `remap | requeue | tombstone | untouched`), the thin shared `migrate.py`
  interpreter, CI replay for determinism, casebook defaults seeding the drafted remap, and the
  depth-capped tombstone chain walker. **Not** the RFC intake, **not** the blast-radius script,
  **not** the diff-visualization pages — those land with the governance flip (Stage 4) and the
  site (Stage 6).
- **The per-cycle runbook** — `docs/runbooks/theme-cycle.md`: the ordered, copy-pasteable sequence
  (sign off → R3 → R4 → R5 → R6 → settle) that cycles 2–12 execute without a new plan.

**Spec pointer:** §10.4, §5.2, §5.4, §7.4 (R6), §3.5.

---

## Running the cycles (after 3A–3F land)

Cycle 1 is the shakedown the sub-plans are built against. Cycles 2–12 are executions of 3F's
runbook. Each cycle:

1. Developer signs off the cycle's theme (hard checkpoint — nothing proceeds without it).
2. R3 survey (3B) → candidate inventory.
3. R4 drafting + debates (3C) → nodes, edges, dimensions, debate records.
4. R5 reality checks (3E) → instances, `research/reality-checks/<cycle>-<theme>.yaml`, shakedown
   findings.
5. R6 consolidation (3F) → cross-theme edges, dedup/alias audit, `dossier` recompute, theme
   marked settled.

A sub-plan is only re-opened if a cycle exposes a real defect in its machinery — the expected
steady state after cycle 2 is that cycles change data, not code.

**Stage 3 exit (= Stage 4 entry):** the developer stops calling cycles, having read a
`coverage report.py dossier` whose five items they find good enough. No bar is binding (D27) —
the `1.0.0` declaration is Stage 4's, and entirely discretionary.

---

## Execution handoff

Write the detailed implementation plan for **3A** first
([2026-09-13-stage-3a-research-spine-and-minting.md](2026-09-13-stage-3a-research-spine-and-minting.md)),
using 3A's "Produces for 3B–3F" list as its required deliverables. Write 3B–3F only once each
one's concrete inputs exist — 3C's plan cannot be written against an imagined candidate-inventory
shape, and 3E's cannot be written against an imagined ontology subtree.
