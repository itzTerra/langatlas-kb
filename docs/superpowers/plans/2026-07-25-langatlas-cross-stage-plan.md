# LangAtlas Cross-Stage Plan

> **For agentic workers:** this document sequences stages and their interface contracts only.
> It is not itself a bite-sized task plan. Per the writing-plans Scope Check, each stage below
> gets its own full implementation plan (`docs/superpowers/plans/YYYY-MM-DD-stage-N-<name>.md`,
> written with superpowers:writing-plans) at the point the stage actually starts — not now, and
> not all at once, since later stages depend on outputs earlier stages haven't produced yet.

**Goal:** Sequence LangAtlas's build stages (per [context/spec.md §14](../../../context/spec.md))
so each stage's implementation plan can be written knowing exactly what it consumes from the
previous stage and must produce for the next, without re-deriving that from the full spec each
time.

**Architecture:** Stage 0 (developer-discretionary, no trigger) plus six dependency-ordered
build stages — R0 infra preflight → R1/R2 corpus & benchmark → R3–R5 theme cycles → v1.0.0
exit → sweep pipeline & language onboarding → site build & public launch. Stage 1 is itself
decomposed into five dependency-ordered sub-plans (1A–1E); each sub-plan gets its own detailed
implementation plan when it starts, not before. Stage 6 can overlap Stage 5 once real facts
exist; all others are strictly sequential (no interleaving, per D27/D28).

**Tech Stack:** langatlas-kb repo (YAML canonical store, Python pipeline/agents, Postgres +
pgvector/FTS via docker compose, stdio MCP server); langatlas-site repo (Astro static site);
langatlas-transcripts repo (chat logs). Full stack detail: [context/spec.md §2](../../../context/spec.md).

## Global Constraints

- No deadline; do not take shortcuts that damage the long-term product (D6/D11).
- Git is the database — Postgres, MCP, and the static site are always one-way derived build
  artifacts, never authoritative (D1).
- No PR gate for agent-committed facts — admissibility comes from the automated verification
  gate (D4/D24), never human review bandwidth (D1).
- English-only; code MIT, corpus CC BY-SA 4.0 (D7, D14).
- Claude never does volume work; the university API never has the final judgment call (D6).
- Every agent chat is logged from day one — cannot be retrofitted (D18).

---

## Stage sequence

### Stage 0 — developer-discretionary setup (no trigger)

Not gated on anything; can happen anytime before the stage that consumes each item. Tracked
here (unlike the rest of Stage 0's calendar-free posture) because the repo-management wiring is
a prerequisite the later stages silently assume.

**Produces:**
- Registered `langatlas.dev` (+ optionally defensive `lang-atlas.io`) and a confirmed
  `langatlas` GitHub org name (D17/D40). Until the org is confirmed the canonical repo lives
  under the developer's personal account (currently `itzTerra/langatlas-kb`); org confirmation
  is the trigger that unblocks real-URL work in later stages (CONTRIBUTING.md, D56, Stage 6).
- **Repo management** — the spec designs three sibling repos (§2.2 component map); today only
  `langatlas-kb` exists. Stage 0 stands up the other two as empty repos and wires them into the
  developer's Claude Code workspace so agents can commit across them:
  - Create `langatlas-site` (Astro static site; consumed in Stage 6) and
    `langatlas-transcripts` (chat-log store, CC0 license file; consumed in Stage 1's transcript
    logging) as siblings of `langatlas-kb`, cloned next to it on disk (`../langatlas-site`,
    `../langatlas-transcripts`).
  - Register both clones as additional working directories in `langatlas-kb/.claude/settings.json`
    so tool calls may read/write them without per-path permission friction:
    ```json
    { "permissions": { "additionalDirectories": ["../langatlas-site", "../langatlas-transcripts"] } }
    ```
  - Set `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` (env or `settings.json` `env` block) so
    each sibling repo's own `CLAUDE.md` loads when work touches it.

**Note:** Stage 0 only *creates* `langatlas-transcripts` and wires the workspace; Stage 1 (sub-plan
1B) is what actually *wires transcript logging into it* (gitleaks CI, `REDACTIONS.md`, normalizer).
`langatlas-site` stays empty until Stage 6.

**Spec pointer:** [context/spec.md §14 Stage 0](../../../context/spec.md), §2.2.

---

### Stage 1 — R0: infrastructure preflight

**Gate:** none (first stage; gates everything else).

Stage 1 is ten independent subsystems; per the writing-plans Scope Check it is decomposed into
**five dependency-ordered sub-plans (1A–1E)**, each producing working, testable software on its
own and getting its own detailed bite-sized plan when it starts. The whole-stage "Produces" list
below is the union of the sub-plans' outputs; the "Exit test" is the cross-subsystem gate that
only 1E can satisfy. Sub-plan boundaries:

- **1A — Canonical store foundation.** Repo layout (§3.3), `ontology/` at `VERSION 0.1.0`,
  id/slug machinery, JSON Schemas in `ontology/schema/` with all pre-emptive fields
  (`exclusivity`, `applies_to`, `aliases`, `absence_scope`, `language_kind`, `syntax_check`,
  `grounding`), the claim-template registry `ontology/claim-templates/` (D47), and the
  validator+normalizer CLI `tools/validate/` (D48: `normalize_record`, `validate_locator_shape`,
  precommit/CI contracts, regression-fixture runner). *Everything else in Stage 1 depends on
  this; write its detailed plan first.*
  - **Consumes:** nothing (first sub-plan).
  - **Produces for 1B–1E:** the schema shapes, canonical-claim/normalization rules, and CLI
    signatures (`normalize_record`, `validate_locator_shape`) the other four build against.
- **1B — Provider & observability.** Provider abstraction + `RunContext` (§7.6/D26: openai-SDK
  channel, Claude channel, cost log, cache, budget signals), prompt-injection posture (§7.8/D31:
  data-not-instructions delimiting + lexical scan), transcript logging (§7.10/D18: wrapper
  persistence, normalizer, wired to the live `langatlas-transcripts` repo from Stage 0, gitleaks
  CI, `REDACTIONS.md`), prompt registry `prompts/` + `config/provider_capabilities.yaml` + first
  capability probe (§7.7/D41).
  - **Consumes:** Stage 0's `langatlas-transcripts` repo + workspace wiring.
  - **Produces for 1C–1E:** the provider-call surface + `RunContext` every agent-invoking
    subsystem uses, and the transcript-logging path every logged run writes through.
  - **Carried over from 1A — resolved:** 1B added the first `provider-record-replay`
    (`mode: hard`) and `prompt-version-rerun` (`mode: soft`) fixtures, so `run_regression`
    now gives the two modes distinct behavior: soft failures become warnings and never
    affect the exit code (D41's log-only prompt-version check), hard failures still fail.
    Fixtures whose checker is not installed in the current environment report as skipped.
- **1C — Ingestion & retrieval.** D15 ingestion CLI + `source_chunks` schema (§8.2) +
  extraction-QA harness (§4.4) + snapshot store layout + the `search_sources` retrieval tool.
  - **Consumes:** 1A source-record schema + locator grammar; 1B provider abstraction (embeddings
    via the university API channel).
  - **Produces for 1E:** the `search_sources` tool the R0 exit test drives.
  - **Carried over from 1A:** same `mode: hard|soft` note as 1B, if 1C is the one that adds the
    first `questionnaire-shape` fixture instead.
  - **Carried over from 1C — for 1D:** `PostgresSourceChunksIndex` exists and satisfies
    1A's `SourceChunksIndex` protocol, but nothing calls it yet. 1D's `langatlas-validate
    ci` is where phase-2 locator resolution gets wired in — construct the index from
    `langatlas_ingest.db.connect()` and pass it to `validate_locator`; `precommit` stays
    phase-1-only even when Postgres is reachable (D48, no auto-upgrade).
  - **Carried over from 1C — for 1E:** the R0 exit test drives `search_sources` through
    `langatlas_ingest.tools.sdk_source_tools(ctx, conn)` on the Claude channel
    (`ClaudeRunOptions(mcp_servers={"langatlas_sources": server}, allowed_tools=TOOL_NAMES)`)
    or through `search_sources()` + `render_for_prompt()` on the completion channel. The
    orchestrator's standing jobs (link-checker, edition-check) file into the existing
    `sourcing_queue` table via `SourcingQueue.file(kind=...)` — the table and its two
    non-ingestion kinds already exist, the jobs do not.
  - **Not built in 1C (named, not deferred silently):** no transcript/video extractor, so
    `t=HH:MM:SS` locators validate but never resolve; no repo-file ingestion backend, so
    `<sha>:<path>#L…` locators likewise resolve to nothing. Both park a citing claim in the
    sourcing queue, which is the correct visible outcome for a source the corpus does not
    contain. The D22 fact-index benchmark and the retrieval golden set itself belong to
    Stages 2 and 5.
- **1D — Commit & CI.** Agent-runner commit protocol (§7.9/D36: GitHub App identity, trailers,
  land loop, is-main-green gate, failure bot) and the CI validated-artifact pipeline skeleton
  (§8.7/D13: validators, fact derivation, collision check, last-green publication, `data-vN`
  tagging).
  - **Consumes:** 1A validators/normalizer (pre-commit + CI run these); 1B transcript path
    (commits carry `chat_run_id` provenance).
  - **Produces for 1E:** the commit path every later stage's agents land facts through.
  - **Carried over from 1A:** 1A's `langatlas-validate ci` command only re-runs the
    regression-fixture suite — it does not yet walk the live canonical store to validate every
    committed record, check normalization drift against disk, cross-check the claim-template
    registry (`validate_claim_template`), or enforce the canonical `alternative-to`/`when_all`
    ordering (`canonical_endpoints`/`canonical_when_all` exist and are unit-tested but have no
    caller outside their own test). Per 1A's own final review, turning `ci` into that real
    store-validating gate is 1D's "CI validated-artifact pipeline skeleton" deliverable, not a 1A
    gap to backfill — build it against the already-shipped `validate_record`/`normalize_record`/
    `validate_claim_template`/`canonical_endpoints`/`canonical_when_all` functions.
- **1E — Orchestrator + R0 exit test.** Orchestrator (`tools/orchestrator/driver.py`,
  `config/jobs/`, `crontab.example`; §7.11/D43) and the end-to-end wiring that satisfies the hard
  exit gate below.
  - **Consumes:** all of 1A–1D.
  - **Produces:** a green R0 exit-test run — the Stage 2 entry condition.

**Produces (interface contract for Stage 2):**
- `ontology/` scaffold at `VERSION 0.1.0` with id/slug machinery and JSON Schemas
  (`ontology/schema/`) — including pre-emptive fields (`exclusivity`, `applies_to`, `aliases`,
  `absence_scope`, `language_kind`, `syntax_check`, `grounding`).
- `tools/validate/` (normalizer, precommit/CI contracts, `validate_locator_shape`).
- Provider abstraction + `RunContext` (cost log, cache, budget signals, injection-safe
  delimiting).
- Transcript logging wired to a live `langatlas-transcripts` repo.
- Prompt registry + `config/provider_capabilities.yaml` with a completed first capability probe.
- D15 ingestion CLI + `source_chunks` schema + extraction-QA harness + snapshot store layout —
  Stage 2 ingests through this, unmodified.
- `ontology/claim-templates/` registry.
- Agent-runner commit protocol (GitHub App identity, land loop, is-main-green gate, failure
  bot) — every later stage's agents commit through this path.
- CI validated-artifact pipeline skeleton (validators, fact derivation, collision check,
  last-green publication, `data-vN` tagging).
- Orchestrator (`tools/orchestrator/driver.py`, `config/jobs/`, `crontab.example`).

**Exit test (hard gate into Stage 2):** an agent can run `search_sources`, mint a node file that
validates, and the run is logged.

**Spec pointer:** [context/spec.md §14 Stage 1](../../../context/spec.md), detail in §§7, 3.3,
4.4, 5.4, 7.6–7.11.

---

### Stage 2 — R1/R2: corpus & benchmark

**Consumes from Stage 1:** the ingestion CLI, snapshot store, validators, transcript logging,
orchestrator — all used as-is, no infra changes expected.

**Produces (interface contract for Stage 3):**
- Ingested seed corpus (six ratified texts + phase-1 language specs + two Elsevier papers),
  QA-skimmed, with retroactive `canonical_source`/`acquisition_note` and phase-1 `grounding`
  classification.
- Retrieval golden set (40–60 queries) and verifier golden set (~200–300 items + ~10–15 held-out
  + ~15–20 bootstrap controversy cases) — Stage 3's debates and R4 drafting read these as fixed
  calibration inputs.
- D22 embedding benchmark result for the **source corpus** table only (fact-index benchmark is
  deferred to Stage 5) — pins the model Stage 3's `search_sources` tool retrieves against.
- A calibrated D24 verifier (FA ≤2% / FR ≤10% against the golden set, canaries wired) — Stage 3's
  R4 drafting and every later fact commit runs through this exact calibration.

**Spec pointer:** [context/spec.md §14 Stage 2](../../../context/spec.md), detail in §§4.4, 6.2,
6.4, 8.6.

---

### Stage 3 — R3→R5 theme cycles (repeats ~12×)

**Consumes from Stage 2:** calibrated verifier, golden sets, ingested corpus + pinned source
embedding model.

**Produces (interface contract for Stage 4):**
- `research/reality-checks/*.yaml` per cycle (rotating 4–5-language reality checks).
- Settled themes accumulating toward full ontology coverage, each closed out with an R6
  consolidation pass (`coverage report.py dossier`).
- R4 debate-outcome tracking data (D30) feeding later MAJOR-churn analysis.

**Per-cycle checkpoint (not a stage gate, but blocks cycle N+1):** developer signs off each
cycle's R3 theme list before R4 drafting starts — no autonomous cycling.

**Spec pointer:** [context/spec.md §14 Stage 3](../../../context/spec.md), detail in §7.4, §5.

---

### Stage 4 — v1.0.0 exit

**Consumes from Stage 3:** all settled themes, the accumulated coverage dossier inputs.

**Produces (interface contract for Stage 5):**
- Global R6 consolidation (cross-theme edge pass, dedup/alias audit, slug polish).
- Developer-declared `1.0.0` ontology version — **flips on full D16 governance**
  (RFC-gated MAJORs, staleness machinery, ~monthly MAJOR batching) for every subsequent stage.
- First compiled sweep questionnaire (D46) and frozen handoff artifacts — Stage 5's sweep agents
  consume this directly; it is not re-derived.

**Gate:** developer discretion on the five-item dossier — no bar is binding (D27).

**Spec pointer:** [context/spec.md §14 Stage 4](../../../context/spec.md), detail in §7.3, §5.1–5.3.

---

### Stage 5 — sweep pipeline & language onboarding

**Consumes from Stage 4:** frozen questionnaire, `1.0.0` ontology under full governance.

**Produces (interface contract for Stage 6):**
- Fact-index embedding benchmark re-run, pinning `knowledge_embeddings` model/dimension/index
  type (D62/D22) — the fact-serving index Stage 6's site and MCP server read from.
- Real, verified, sourced facts accumulating per phase (1: Python/C/Java/Rust/Haskell/Prolog →
  2 → 3 → optional 4 → 5/SQL), each phase strictly gated on the previous phase's completed
  sweeps — **Stage 6 can start once phase 1 produces real facts**, it does not wait for all
  phases.
- Live nightly verification/controversy batches, `since` back-dating batches, contradiction
  scanning — standing jobs Stage 6's site displays consume as ongoing state, not one-time output.
- D54 auto-skip calibration data (shadow mode through phase 1, live cutover only on measured
  rates).

**Spec pointer:** [context/spec.md §14 Stage 5](../../../context/spec.md), detail in §7.2, §7.5,
§6.8.

---

### Stage 6 — site build & public launch

**Consumes from Stage 5:** the dataset bundle (D35 contract) built from real phase-1+ facts, the
pinned fact-embedding index, standing verification/controversy jobs already running.

**Can start:** once Stage 5 phase 1 produces real facts — explicitly allowed to overlap the rest
of Stage 5.

**Produces:** `langatlas-site` (Astro build, IA pages, popovers, coverage matrix, Pagefind,
OG templates, JSON-LD, `/license/`, `/changelog/ontology/`); Postgres loader + blue-green swap +
MCP server (7 public tools); **D63 human-challenge hard-override mechanics — hard-gated to land
before the challenge channel goes live**; issue forms + giscus; CONTRIBUTING.md; finalized
positioning copy/wordmark/accent color; launch posts; post-launch analytics + `demand` export.

**Spec pointer:** [context/spec.md §14 Stage 6](../../../context/spec.md), detail in §§9, 10, 11,
6.8.

---

## Standing periodic jobs (cut across stages once their subsystems exist)

Nightly verification/controversy batch; monthly link-checker/capability-probe/finding-aid-mirror
refresh/`demand` export; quarterly edition-check; 18-month rolling backstop re-verification;
event-driven contradiction scan / re-verification triggers / questionnaire recompiles /
blast-radius runs. Full inventory: [context/spec.md §14](../../../context/spec.md), D43.

## Deferred work (not part of this sequence)

Backlog topics 50–52, 54, 55, 58, 60 and the deferred open questions listed in
[context/spec.md §14](../../../context/spec.md) wait on specific future triggers (Builder
greenlight, scaling past 15 languages, public golden-set benchmark, etc.) — not scheduled
against any stage above.

---

## Execution handoff

This document is a sequencing map, not an executable plan. When Stage 1 is ready to start, write
the detailed implementation plan for **sub-plan 1A** first (superpowers:writing-plans — bite-sized
tasks, file paths, test-first steps) using 1A's "Produces for 1B–1E" list as its required
deliverables; write 1B–1E only once each one's concrete inputs (1A's schema shapes and CLI
signatures, 1B's provider surface, etc.) actually exist. Repeat per stage. Do not write Stage 2+'s
detailed plan before Stage 1 lands — its concrete inputs (schema shapes, tool signatures) don't
exist yet.
