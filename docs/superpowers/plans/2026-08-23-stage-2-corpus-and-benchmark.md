# LangAtlas Stage 2 — R1/R2: Corpus & Benchmark (sequencing map)

> **For agentic workers:** this document sequences Stage 2's sub-plans and their interface
> contracts only. It is **not** a bite-sized task plan. Per the writing-plans Scope Check, each
> sub-plan below gets its own full implementation plan
> (`docs/superpowers/plans/YYYY-MM-DD-stage-2<letter>-<name>.md`, written with
> superpowers:writing-plans) at the point that sub-plan actually starts — not now, and not all at
> once, since later sub-plans depend on artifacts earlier ones haven't produced yet (real chunk
> ids, a pinned embedding model, a committed golden set).

**Goal:** Turn Stage 1's empty infrastructure into a working, benchmarked, QA'd corpus with a
calibrated D24 verifier — the fixed calibration inputs every Stage 3 theme cycle reads.

**Architecture:** Five sub-plans. 2A ingests and QAs the corpus (R1). 2B authors the golden sets
and their scoring harnesses. 2C runs the D22 embedding benchmark (R2) and pins the source-corpus
model. 2D builds and calibrates the D24 verifier. 2E builds D53's finding aids and the
corpus-maintenance standing jobs. 2A gates everything; 2E is independent of 2B–2D once 2A lands.

**Tech Stack:** the Stage 1 packages, used as-is — `langatlas_ingest` (ingestion CLI, `run_qa`,
`SourceSearch`, `run_eval`, `SourcingQueue`, `PostgresSourceChunksIndex`), `langatlas_validate`
(`validate_record`, `normalize_record`, `validate_locator`, `validate_store`),
`langatlas_pipeline` (`RunContext`, completion/Claude/embedding/rerank channels, prompt registry,
transcript writer), `langatlas_commit` (land loop), `langatlas_orchestrator` (`register_job_kind`,
`CheckpointStore`). New code lands as new modules inside these packages, plus one new package for
2E.

**Spec:** [context/spec.md](../../../context/spec.md) — Stage 2's checklist is §14 "Stage 2";
subsystem detail in §4.1–4.5, §6.2–6.5, §7.1, §7.4, §8.2, §8.6.

**Predecessor:** [2026-07-25-langatlas-cross-stage-plan.md](2026-07-25-langatlas-cross-stage-plan.md)
— Stage 2's "Consumes from Stage 1" / "Produces (interface contract for Stage 3)" lists are the
contract this document decomposes.

## Global Constraints

Stage 1's constraints carry over verbatim and are not restated per sub-plan:

- No deadline; do not take shortcuts that damage the long-term product (D6/D11).
- Git is the database — Postgres, extracted text, embeddings, and the verdict ledger are derived,
  private, or both, never authoritative (D1). Extracted text and embeddings stay out of git (D15).
- No PR gate for agent-committed facts — admissibility comes from the automated verification gate
  (D4/D24), never human review bandwidth.
- English-only; code MIT, corpus CC BY-SA 4.0 (D7, D14).
- **Claude never does volume work; the university API never has the final judgment call (D6).**
  Stage 2 applies this sharply: the verifier's entailment stage is university-API only (Claude is
  never in the verification loop except as a manual developer spot-check instrument), while golden-set
  curation and calibration judgment are the developer's and Claude's.
- Every agent chat is logged (D18) — every benchmark run, verification batch, and golden-set
  generation pass writes a transcript.
- Verbatim quote cap ~50 words, ~300-word per-page aggregate warning (D14) — golden-set items that
  embed source text are bound by this too.
- Model ids are configuration, never hardcoded (`config/ingest.yaml`, `config/providers.yaml`).

---

## Stage 2 entry state (what Stage 1 actually shipped)

Recorded here so no sub-plan re-derives it:

- **Ingestion**: `langatlas-sources` CLI with `db | ingest | reingest | qa | queue | embed | search
  | eval`. `run_qa(doc, chunks)` → `QaReport` (mojibake / min-chars / OCR-rate / length-outlier /
  outline-coverage; encoding + extraction-collapse hard-gate promotion). `source_chunks`,
  `source_ingestions`, `sourcing_queue` tables live in `db/0001`–`db/0005`.
- **Retrieval**: `SourceSearch.search()` (hybrid FTS+vector, RRF, `qwen3-reranker-4b` default-on,
  `rerank_candidates: 20`), `get_section()`, and the two pipeline-only tools
  `search_sources` / `get_source_section` (`sdk_source_tools(ctx, conn)`, `TOOL_NAMES`,
  `render_for_prompt`).
- **Retrieval scoring**: `run_eval(conn, ctx, *, golden_dir=None, config=None, rerank=None)` →
  `EvalResult(queries, recall_at_5, mrr, ndcg_at_10, latency_p50_ms, per_query, golden_dir_missing)`.
  `tests/golden/retrieval/` is **empty by design** apart from `queries.example.yaml` (skipped by
  name) and a README.
- **Validation**: `validate_record`, `normalize_record`, `validate_locator` /
  `validate_locator_shape`, `validate_claim_template`, `canonical_endpoints`, `canonical_when_all`,
  `validate_store`, `iter_store_records`. CLI `langatlas-validate precommit | precommit-auto | ci |
  regression`. `PostgresSourceChunksIndex.resolve(source_id, locator)` provides phase-2 locator
  resolution and is wired into `ci`.
- **Providers/observability**: `RunContext` with completion / Claude / embedding / rerank channels,
  content-addressed cache, cost log, budget signals; D31 delimiting + `injection.py` lexical scan;
  prompt registry under `prompts/`; `config/provider_capabilities.yaml` with a completed probe;
  transcript writer publishing to `langatlas-transcripts`.
- **Commit/CI**: `langatlas_commit` land loop with GitHub App identity, trailers
  (`LangAtlas-Record-Key`, `chat_run_id`), is-main-green gate, failure bot; CI validated-artifact
  pipeline with `data-vN` tagging.
- **Orchestrator**: `driver.py`, `register_job_kind`, `CheckpointStore`, `config/jobs/*.yaml`,
  `crontab.example`. `r0-exit-test` and `monthly-capability-probe` are real; six job kinds are
  registered as loud `NotImplementedError` stubs in `jobs/deferred.py`. **Four of those six are
  Stage 2's to replace**: `monthly-link-checker`, `quarterly-edition-check`,
  `monthly-finding-aid-mirror-refresh` (all 2E), and `nightly-verification` (2D — Stage 2 makes it
  real; Stage 5 gives it volume).
- **Schemas**: `ontology/` at `VERSION 0.1.0`, eight JSON Schemas in `ontology/schema/` including
  `source.schema.json` with `custom.{tier, grounding, canonical_source, acquisition_note,
  locator_kinds, edition, edition_check_url, archive_url, accessed, added_by, superseded_by}`;
  six claim templates in `ontology/claim-templates/`; `contradictions.yaml` exists as
  `contradictions: []` with **no schema** (2D writes it).

**Not built by Stage 1, named here so no sub-plan assumes them** (carried over from 1C):

- No transcript/video extractor — `t=HH:MM:SS` locators validate but never resolve.
- No repo-file ingestion backend — `<sha7>:<path>#LN-LM` locators likewise resolve to nothing.
  Both park a citing claim in `pending-source`, which is the correct visible outcome. 2A decides
  per acquired source whether any seed source needs one; if so, that backend is a 2A deliverable.
- No `knowledge_embeddings` table and no fact-embedding index (D62/§8.3) — Stage 5.
- No debate machinery, reconciler, or controversy assessor — Stage 3.

---

## Sub-plan sequence

### 2A — Corpus assembly, ingestion & QA (R1)

**Gate:** none (first sub-plan; gates 2B–2E).

The largest developer-time item in the project (§7.4: ~1–2 focused weeks of ingestion, 0.5–2 h QA
per book). Most of the *work* is manual; the *plan* is the tooling and bookkeeping that makes the
manual work checkpointed and resumable rather than a shapeless slog.

**Consumes:** the Stage 1 ingestion CLI, snapshot store, QA harness, `sourcing_queue`, validators,
transcript logging — **used as-is; no infra changes expected**. If 2A finds it must change the
ingestion CLI's behavior (as opposed to its configuration), that is a finding to surface, not a
silent fix.

**Produces:**
- **Acquisition tracking** for the six ratified D27 texts (Scott *Programming Language
  Pragmatics*; Turbak & Gifford *Design Concepts in Programming Languages*; Harper *PFPL* (free);
  Krishnamurthi *PLAI* (free); Sebesta *Concepts of Programming Languages*; Kaijanaho 2015 (free
  thesis)) plus the two Elsevier papers identified at ingestion, via `SourcingQueue.file(kind=
  "pending-source", reason="access-pending" | "paywalled" | "acquisition-failed")`. Paid titles go
  through university library access; the developer drops PDFs into the snapshot store. **Agents
  cannot acquire books** — every acquisition is a developer checkpoint item.
- **Ingested seed corpus**: the D15 developer collection (Van Roy & Haridi CTM; Pierce TAPL +
  ATTAPL; Cardelli & Wegner 1985; the two Elsevier papers; *Software Foundations* vol. 2) + Jordan
  et al. (2015) + the D27 acquisitions + **D28 phase-1 language specs/docs only** (Python, C, Java,
  Rust, Haskell, Prolog — official specs/reference chapters; editions pinned per §7.5: C23/N3220,
  JLS SE 25, Haskell 2010 + latest GHC guide, Deransart et al. 1996 for Prolog). ~30 sources,
  ~12–20k chunks, ~200 MB.
- **Per-source QA reports** stored in `source_ingestions.qa_report`, each skimmed by the developer.
  Hard failures (encoding, extraction collapse) block promotion and must be resolved — a different
  backend, a different acquisition, or a documented parked entry — before that source counts as
  ingested.
- **Retroactive D37 backfill**: `custom.canonical_source` set on every source record, and
  `custom.acquisition_note` present on every non-canonical one (CI-enforced presence). This is the
  one-time R1 pass §4.4 owes.
- **Phase-1 `grounding` classification (D51)**: the one-time retroactive pass over phase-1's six
  languages, applying §4.2's per-language rules — Python → `reference-implementation-docs` (PEPs
  `design-doc`); Rust split per claim between the Reference
  (`reference-implementation-docs`) and the FLS (`formal-spec`), preferring the FLS wherever it
  covers a claim; Prolog → `formal-spec` via Deransart et al.; the rest defaulting to
  `third-party-reference` unless a rule says otherwise. Phases 2–4 classify at their own ingestion
  time and are **out of scope here**.
- **Batch embed** of every promoted source on the incumbent `qwen3-embedding-4b`, so 2B and 2C have
  a queryable index. 2C may re-embed under other candidate models; the incumbent run is the
  baseline arm.

**Produces for 2B–2E:**
- A populated `source_chunks` table with **real chunk ids** (`<source_id>#cNNNNN`) and real
  machine-produced locators — 2B's golden-set entries reference these directly, and a golden set
  authored against invented ids is worthless.
- Committed `sources/*.yaml` records with complete `custom` blocks — 2D's tier-A/B admissibility
  rule and confidence lookup read `custom.tier`; 2E's mirror/link/edition jobs read
  `custom.{URL, edition, edition_check_url, locator_kinds}`.
- The QA reports themselves, which are the developer's reading surface during the skims that
  double as golden-set co-authoring time (§7.4).

**Developer checkpoints (block progress; not agent-decidable):** each acquisition; each per-source
QA skim sign-off; the decision to park a genuinely inaccessible source indefinitely.

**Spec pointer:** §4.1, §4.2, §4.4, §7.4 (R1), §7.5, §8.2.

---

### 2B — Golden sets & scoring harnesses

**Gate:** 2A's corpus ingested and embedded (golden items must reference real chunks).

**Consumes:** 2A's `source_chunks` + committed source records; `run_eval` and its
`tests/golden/retrieval/` contract; `RunContext`'s completion channel (LLM-generated candidate
volume, deliberately decorrelated from the verifier model per §6.4); the transcript writer.

**Produces:**
- **Retrieval golden set** — 40–60 queries in three difficulty bands (`exact-term`,
  `paraphrase-concept`, `cross-source-survey`), co-authored during 2A's QA skims, committed as
  `tests/golden/retrieval/queries-<theme>.yaml` in the format `queries.example.yaml` already
  documents (each entry: `id`, `band`, `query`, and **exactly one** of `expected_chunks` /
  `expected_sources`). Derived-first from the verifier golden set's own correct-stratum
  `(claim, locator)` pairs; hand-authoring reserved for the paraphrase-hard and cross-source bands.
- **Verifier golden set** — ~200–300 stratified items under `tests/golden/verifier/`, over §6.4's
  **13 strata**: correct; overstated claim (first-class, separately reported — the K1 defense and
  the only stratum exercising `partial`'s intended meaning); fabricated locator; wrong `since`
  off-by-one; wrong `since` off-by-major; contradicted; right-claim-wrong-source; category error;
  fabricated feature-instance combination; quote-mismatch; quote-found-elsewhere; OCR-noisy;
  paraphrase-heavy correct. Mix ~40% correct / 60% wrong, with overstated-claim and wrong-`since`
  over-weighted. **Must include `status: absent` items** so 2D's D49 completeness-check ladder is
  covered by the same calibration.
- ~~**Held-out audit slice** — ~10–15 items authored entirely by the developer, no LLM in the
  loop, committed separately and never used for tuning.~~ **Abandoned by developer ruling
  (2026-09-09)** — no held-out slice is authored; `SET_INVARIANTS` in `goldens/loader.py`
  requires exactly 0.
- **Bootstrap controversy cases** — ~15–20 synthetic structured-input cases under
  `tests/golden/controversy/`, seeding the ~50-case target that Stage 3's opportunistic lane grows.
- **A scored, threshold-gated runner** for the verifier and controversy sets — the counterpart to
  `run_eval` for retrieval — reporting **false-accept and false-reject rates separately**, plus
  per-stratum breakdowns (overstated-claim reported on its own line). Layout and posture per §6.4:
  `tests/golden/{verifier,controversy,retrieval,debates}/`, scored and threshold-gated, **distinct
  from** the diff-reviewed `tests/fixtures/providers/regression/` family, and **never a CI blocker
  on its own**. Staleness enforcement on golden items is soft/log-only.
- **Contamination defenses, structurally** (not as a later audit): perturb toward counterfactual,
  specifically-invented wrongness (invented version numbers, swapped similar-language attribution,
  altered loci) rather than famous-facts-stated-wrong; target obscure loci; keep a cross-family
  sample that doubles as a passive contamination gauge.

**Produces for 2C:** the retrieval golden set — 2C's entire benchmark is scored against it, and
`run_eval` is the scoring function.

**Produces for 2D:** the verifier golden set and the scored runner — 2D's calibration gate is
defined entirely in terms of these. (No held-out slice — abandoned 2026-09-09.)

**Not built here:** `tests/golden/debates/` stays empty — debate machinery is Stage 3. The public
golden-set benchmark is a stretch goal and explicitly out of scope (§6.4).

**Developer checkpoints:** curation of every LLM-generated candidate (the developer curates, the
LLM only supplies volume).

**Spec pointer:** §6.4, §8.6 (golden-set clause), §7.4 (R1's "QA skims double as golden-set
co-authoring time").

---

### 2C — D22 embedding benchmark (R2)

**Gate:** 2A ingested (pilot corpus available) + 2B's retrieval golden set committed.

**Consumes:** 2B's 40–60 queries; `run_eval(conn, ctx, golden_dir=..., config=..., rerank=...)` —
already parameterized for the rerank-vs-no-rerank arm; `RunContext`'s embedding + rerank channels;
`config/ingest.yaml`'s `models` / `retrieval` blocks (model ids are configuration, so candidates
swap without code changes).

**Produces:**
- A **benchmark harness** wrapping `run_eval` with the metrics §8.6 asks for that `EvalResult` does
  not yet carry — **Recall@50 pre-rerank, indexing throughput, storage** — alongside the existing
  Recall@5, nDCG@10 post-rerank, MRR, and latency.
- A **completed benchmark run on a pilot corpus (3–4 sources)** across: the university-hosted
  candidates (`qwen3-embedding-4b` incumbent, `nomic-embed-text-v1.5`/`v2-moe`, `mxbai-embed-large`,
  `multilingual-e5-large-instruct`) **plus one local-CPU fastembed representative** as the
  "does free-and-local suffice" floor. Short-context models tested **honestly** —
  breadcrumb-prefixed chunks truncated exactly as in production, never given a longer window than
  they would get.
- Variant axes: vector-only vs hybrid+RRF vs hybrid+reranker; 400 vs 800 chunk size as a secondary
  axis.
- A **per-table verdict record** applying §8.6's decision rules mechanically: incumbent
  `qwen3-embedding-4b` stays unless beaten by ≥5 pts Recall@5, or matched within 2 pts by a local
  model; reranker stays default-on unless it adds <2 pts nDCG@10; hybrid-vs-vector follows the same
  2-point rule.
- The **source-corpus table's model/dimension/index-type pinned** into `config/ingest.yaml`, and a
  full re-embed of the corpus if the verdict moves off the incumbent.

**Produces for 2D and Stage 3:** the pinned source-corpus retrieval stack. Stage 3's
`search_sources` retrieves against exactly this; 2D's stage-1 retrieval-rescue ladder uses it too.

**Explicitly not produced here:** the **fact-index** verdict. §8.6 schedules a fact-index *proxy*
run late in the research phase (Stage 3) and the **real re-run at sweep start (Stage 5, D62)**; the
debate-history use case is deferred to v2. Per-table verdicts are independent — the two indexes may
choose different models.

**Developer checkpoints:** adopting the verdict (the decision rules are mechanical, but the
adoption is the developer's), and the re-embed go-ahead if the model changes.

**Spec pointer:** §8.6, §8.1, §7.1 (model roster), §8.3 (what is deferred).

---

### 2D — D24 verifier & calibration

**Gate:** 2A ingested, 2B's verifier golden set committed, 2C's model pinned.

The largest *engineering* item in Stage 2, and the one Stage 1 left entirely unbuilt — there is no
verifier code in the repo today.

**Consumes:** `source_chunks` (index-only evidence — the verifier **never live-fetches at verdict
time**); `PostgresSourceChunksIndex.resolve(source_id, locator)` and `validate_locator` for
stage-0/1; `SourceSearch` for the stage-1 scoped-retrieval bounce hint; `RunContext`'s completion
channel with `deepseek` / `deepseek-thinking` / `mini` (gpt-oss-120b); D31 delimiting +
`injection.py` for evidence text; the transcript writer; `SourcingQueue.file(kind="pending-source")`
for un-ingested citations; 2B's scored runner.

**Produces:**
- **The four-stage pipeline** of §6.2, as increasingly expensive filters, not one LLM call:
  0. schema + referential checks in plain code (`source_id` resolves? locator shape valid?);
  1. evidence resolution — ingested? → `pending-source` | locate chunks at locator, via the
     ladder *exact locator match → containment (range overlap) → scoped hybrid retrieval as a
     **bounce hint only*** (a strong hit far from the claimed locator yields `locator-not-found` +
     hint; rescue **never** silently passes a wrong locator), with small-to-big parent-section
     expansion when the chunk is <~300 tokens or mid-argument;
  2. quote fast path (only when a quote is present) — NFKC-normalized token-level fuzzy match,
     ≥0.90 pass, ≤0.80 `quote-mismatch`, LLM adjudicates between (OCR vs fabrication); a miss at
     the locator searches the whole source (`quote-found-elsewhere` annotation, locator
     auto-correctable); plus the mechanical `since` token-presence precheck and quote-cap
     compliance;
  3. entailment (university-API, **context-blind**) — claim decomposition into atomic assertions
     (presence, syntax form, `since`, qualifiers), each marked supported/not-supported/contradicted
     with a grounding span, overall verdict by fixed rule, structured JSON, temperature 0.
     **A matched quote never waives entailment** — quote-real-but-overstated is the core K1
     laundering pattern.
- **Verdict vocabulary** per (claim, citation) pair — `source-unavailable | locator-not-found |
  supported | partial | unsupported | contradicted` (six; `quote-mismatch` /
  `quote-found-elsewhere` are stage-2 **annotations**, not verdicts).
- **The admissibility rule**: a derived fact enters the canonical store iff **≥1 citation is
  `supported` from a tier-A/B source** (C/D corroborate only). `partial`-only facts bounce once for
  claim narrowing (2-bounce budget, already modeled by `sourcing_queue.bounce_count`);
  `unsupported`/`contradicted` never enter and bounce with rationale.
- **`since` semantics**: entailment distinguishes *since-supported* from *as-of-supported*; the
  latter is a legitimate `partial` — presence enters, `since` gets `as-of` status and lands in the
  back-dating queue.
- **The authoritative verdict fold table** (§6.2) folding per-pair verdicts over each load-bearing
  field into `verification: unverified | verified | partially-verified | failed`, plus the derived
  confidence lookup of §6.3 (`high | medium | low`, with mechanical independence checking from CSL
  records — no shared author, no shared publisher/venue; borderline defaults to *not* independent).
- **The D49 completeness-check method** for `status: absent` claims, extending the same ladder and
  vocabulary: (1) tier-A/B + locator resolution; (2) a corpus-wide **negative full-text grep** across
  every chunk of the cited source using the feature's `aliases: []`; (3) an **inverted-framing**
  entailment stage verifying the agent's own `absence_scope` argument rather than searching for a
  supporting quote. A source that actually documents the feature yields `contradicted`, blocking
  admission. Absence confidence caps at `medium` on a single source.
- **Structural context blindness**: whitelist-built input — `{fact_id, canonical claim text, since,
  source_id, locator, quote}` **only**; never notes, `claim_origin`, proposer identity/persona,
  debate/chat context, or other citations' verdicts (pairs judged independently). The verifier has
  **no tools** (pure text-in/JSON-out; retrieval is done by the runner beforehand); evidence is
  delimited as data; the lexical scan flags instruction-like patterns into the transcript.
- **The private verdict ledger** — build-side, **never written into authored YAML** (D23) — with
  per-verdict blocks carrying `{verdict, per_assertion, model, prompt_version, run_id, anchor, date,
  evidence_chunk_ids}` so verdicts are re-derivable and each fact's "AI chat" link lands on the
  exact entailment exchange. One transcript per batch (`<date>-verify-<slug>-<seq>`) with per-claim
  `#msg-N` anchors.
- **`contradictions.yaml`'s schema and the `type: verification` minting path** (D45) — content-keyed
  `ctr-<12-hex SHA-256>` over sorted participant ids, mutable `status`, closed records never
  deleted. Minted **only** when a `contradicted` verdict lands on a *secondary* citation of an
  otherwise-admissible fact (a contradicted primary/only citation blocks admission and mints
  nothing); **`partial` verdicts never mint records**. Closure v0: automated since/status
  comparison at mint time → `dissolved`; auto-closure on participant correction via tombstone
  cross-reference. The `dispute` axis is a derived read of currently-open records.
- **Model tiering**: primary `deepseek` (reasoning off); escalation to `deepseek-thinking` on
  `partial` / `contradicted` / inconsistent per-assertion output (~5–15% of pairs); `mini`
  (gpt-oss-120b) as a **cross-family second opinion on ~10% of `supported` verdicts** — a drift
  gauge whose rising disagreement is the earliest rubber-stamping signal. If measured false-accept
  misses target, the `mini` sample hardens into a mandatory second vote for `supported`.
  **Claude is never in the verification loop** (D6) except as a manual developer spot-check.
- **Calibration to FA ≤2% / FR ≤10%** against 2B's golden set (the cost asymmetry is deliberate: a
  false accept poisons a public RAG-recycled corpus; a false reject costs one retry). Rerun on any
  verifier prompt or model change. **Per-batch known-bad canaries halt the batch on a pass.**
  The measured error rates are **published** — on the site and in the bundle manifest — as an
  honesty feature, so they must be emitted in a machine-readable form the D35 bundle can carry.
- **`nightly-verification` promoted from stub to real** in `jobs/deferred.py` →
  `jobs/verification.py`, registered via `register_job_kind`, checkpointed through `CheckpointStore`,
  driven by `config/jobs/nightly-verification.yaml`. Stage 5 gives it volume; Stage 2 makes it run.

**Throughput expectation (sanity, not a target):** ~4–6k tokens and ~1.15 university-API calls per
pair; ~1,000–4,000 pairs per 8-hour overnight window at concurrency 4. Verification is not the
bottleneck; cash cost is zero.

**Produces for Stage 3:** the exact calibration every R4 drafting run and every later fact commit
passes through. Stage 3 does not re-calibrate.

**Not built here:** the **cross-fact scan (D59)** — it needs `knowledge_embeddings` (§8.3) for
candidate generation, which is Stage 5. The **controversy assessor** (D21/D25) is Stage 3: its
inputs are debate records and reconciler conflicts that do not exist yet; Stage 2 only ships its
bootstrap golden cases (2B). Human-challenge resolution and the D63 hard-override are Stage 6.

**Developer checkpoints:** accepting the calibration result (and, if the targets are missed,
deciding between prompt work, the mandatory-`mini`-second-vote hardening, and golden-set
revision). (No held-out audit step — the slice was abandoned 2026-09-09.)

**Spec pointer:** §6.2, §6.3, §6.4, §6.5, §6.6 (D49), §7.1, §4.3.

---

### 2E — Finding aids & corpus standing jobs

**Gate:** 2A ingested. Independent of 2B–2D; may run in parallel with them. **Must land before
Stage 3's first R3 batch survey**, which consumes `report.py checklist`.

**Scope note:** the cross-stage plan's Stage 2 "Produces" list does not name D53's finding-aid
tooling. It belongs here regardless: `jobs/deferred.py` already assigns
`monthly-finding-aid-mirror-refresh` to Stage 2, and Stage 3's R3 thematic surveys consume the
`checklist` mode. Flagged as a deliberate scope addition rather than folded in silently.

**Consumes:** 2A's committed source records (`custom.URL`, `custom.edition`,
`custom.edition_check_url`, `custom.locator_kinds`); `SourcingQueue.file()` — the `link-checker` and
`edition-check` kinds already exist in the table's `CHECK` constraint and in `SourcingQueue`, only
the jobs are missing; `RunContext` (caching/rate-limiting/logging ride it as a **fifth channel**);
`register_job_kind` + `CheckpointStore`; the D31 instruction-pattern scan.

**Produces:**
- **One `langatlas_finding_aids` package** with two consumption modes: `tools/finding-aids/report.py`
  (`checklist` for R3 batch surveys, `lookup` ad hoc) and a live **`search_finding_aids`** tool via
  the provider layer for D5 sweep point lookups — available to every agent session type and
  **never on the public MCP**.
- **Per-source adapters**: live throttled/cached clients for Wikidata (scoped SPARQL template) and
  Wikipedia (REST API); **monthly-refreshed local mirrors** for PLDB (git-clone-style mirror of its
  published repo) and Hyperpolyglot (scoped scrape respecting robots.txt / TDM opt-outs). **All
  reads are served from mirrors** for reproducibility.
- **Non-citability enforced three ways** (D29/D3 — bulk import of PLDB/Wikidata as fact content is
  *rejected*): a typed `FindingAidResult` envelope **the fact schema has no slot for**; a
  tool-description caveat restating D29/D3 once per session; the D31 instruction-pattern scan from
  day one. `provenance.candidate_source` is populated as advisory bookkeeping;
  `mint_identification_source` is the separate explicit path minting a real tier-D attribution
  citation (ungated, per D29).
- **`monthly-link-checker`** over URL-locator sources only — resolution, anchor presence, and
  content-hash drift as **three independent signals**; a single retry before flagging
  `link_status: dead`. Content drift feeds the `snapshot-drift` trigger. **A dead live link never
  retroactively unverifies a fact verified against its archived snapshot.**
- **`quarterly-edition-check`** — plain page fetch, **no re-ingestion**; opens a triage-queue entry
  on mismatch and never auto-reingests. §4.2 owes a **flat shorter interval for every
  non-`formal-spec` grounding** (no per-implementation-speed variance). Adopting a new edition is a
  separate developer-initiated act: ingest as a new versioned `source_id`, tombstone the old via
  `custom.superseded_by` in `sources/_tombstones.yaml`, fire an `edition-superseded` staleness
  trigger.
- **`monthly-finding-aid-mirror-refresh`** — refreshes the PLDB and Hyperpolyglot mirrors.
- All three replace their `jobs/deferred.py` stubs with registered job kinds + real
  `config/jobs/*.yaml` entries.

**Produces for Stage 3:** `report.py checklist`, the R3 batch-survey coverage input.

**Spec pointer:** §4.4, §4.5, §7.11, D29/D53.

---

## Stage 2 exit condition (entry into Stage 3)

Not a single mechanical test the way R0's was — Stage 2's exit is the conjunction of its four
interface deliverables being real and pinned:

1. Seed corpus + phase-1 language specs ingested, QA-skimmed, with `canonical_source` /
   `acquisition_note` backfilled and phase-1 `grounding` classified (2A).
2. Retrieval golden set (40–60), verifier golden set (~200–300 + 15–20 bootstrap controversy;
   no held-out slice — abandoned 2026-09-09) committed and scored by a working runner (2B).
3. D22 source-corpus verdict recorded and the model/dimension/index type pinned in
   `config/ingest.yaml` (2C).
4. D24 verifier calibrated at **FA ≤2% / FR ≤10%** against the golden set with canaries wired and
   `nightly-verification` running as a real job kind (2D).

Plus, before Stage 3's first R3 survey: 2E's `report.py checklist`.

Stage 3 treats all of these as **fixed calibration inputs** — it reads them, it does not re-derive
them.

---

## Deliberately out of scope

- Fact-index embedding benchmark (§8.3/D62) — proxy run late in Stage 3, real re-run at Stage 5.
- `knowledge_embeddings` table, cross-fact scan (D59), D54 auto-skip calibration — Stage 5.
- Debate machinery, reconciler, controversy assessor, `tests/golden/debates/` — Stage 3.
- D28 phase 2–5 language specs and their `grounding` classification — they classify at their own
  ingestion time (§4.2).
- The D57 onboarding checklist template — spec explicitly defers its build to nearer D28 phase 2/3.
- Public golden-set benchmark — stretch goal only (§6.4).
- Anything site-facing: popover disclosure copy, status glyphs, published error-rate rendering.
  Stage 2 must *emit* the machine-readable error rates; rendering them is Stage 6.

---

## Execution handoff

This document is a sequencing map, not an executable plan. When Stage 2 starts, write the detailed
implementation plan for **2A** first (superpowers:writing-plans — bite-sized tasks, exact file
paths, test-first steps), using 2A's "Produces for 2B–2E" list as its required deliverables. Write
2B–2E's plans only once each one's concrete inputs actually exist: 2B needs 2A's real chunk ids,
2C needs 2B's committed queries, 2D needs 2B's golden set and 2C's pinned model. 2E may be planned
any time after 2A lands.
