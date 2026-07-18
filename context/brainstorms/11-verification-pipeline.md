# 11 — Claim↔Source Verification Pipeline (round 3)

> Brainstorm output for LangAtlas. Topic: the concrete design of the D4 source-integrity +
> entailment gate — the load-bearing gate, since there is no human merge/PR gate (D1) and no
> other mechanism stands between an agent's draft claim and the canonical store. Binding
> context: `context/decisions.md` (esp. D1–D6, D15, D18, D20, D21); builds on brainstorms 02
> (sources/citations), 04 (multi-agent workflow), 08 (risk K1), 21 (full-source RAG).
> All proposals here are *proposed* until the developer ratifies.

## 1. Problem framing

D1 removed the human merge gate; D4 made an automated verifier the sole admissibility
authority; D15 gave that verifier its evidence substrate (the `source_chunks` table). What has
never been designed is the gate itself: what exactly goes in, what comes out, which checks are
mechanical code and which are LLM judgment, which university-API model judges entailment, how
wrong the gate is allowed to be, and how its work is logged and audited. Sub-problems:

1. **Unit of verification.** Per D20, the authoring unit is a feature-instance record with
   per-field `sources:` lists, and challengeable facts are derived per (record, field). The
   verifiable unit is therefore the **(claim, citation) pair**: one derived per-field claim ×
   one `{source_id, locator, quote?}` entry. A field with three sources yields three
   independent verification pairs; a fact's admissibility is then a function over its pairs'
   verdicts.
2. **Evidence acquisition.** The verifier must work from source text it can actually retrieve:
   ingested PDFs and HTML in `source_chunks` (D15), including paywalled papers that arrive via
   the developer's university access, with the fetcher honoring robots.txt/TDM opt-outs (D14).
   Claims citing not-yet-ingested sources need a defined holding state, not a silent pass or
   fail.
3. **Judgment.** Verbatim quotes are optional (D3), so the general case is *entailment from
   locator + retrieved text*, not string matching. String matching remains the cheap fast path
   when a quote exists. The `since` value is part of the claim and must be checked against the
   source (D2) — the single most common way a "true" claim is subtly wrong.
4. **Calibration.** The gate's error rates are the project's epistemic floor. False accepts
   are citation laundering (risk K1, the top risk); false rejects burn agent budget and stall
   the pipeline. Both must be *measured*, not assumed — which requires a golden set containing
   deliberately wrong claims.
5. **Independence.** The verifier must be context-blind: it may never see the proposer's
   reasoning, persona, debate context, or desired outcome (D4). This must be enforced
   structurally (what the runner is *able* to send), not by prompt discipline.
6. **Audit trail.** One transcript per verification batch with per-claim anchors (D18); each
   fact's provenance links into the batch transcript at its anchor.

Key reframe: **the gate is a pipeline of increasingly expensive filters, not one LLM call.**
Most citation failures (dangling source ID, locator that resolves to nothing, quote that isn't
there) are detectable by plain code for free; the LLM only adjudicates the residue — "the text
is here; does it say that?"

## 2. Options with trade-offs

### 2.1 End-to-end gate mechanics (proposed shape, then the contested points)

The uncontested skeleton, per (claim, citation) pair:

```
claim file (status: draft)
  │ 0. schema + referential checks (CI-grade, plain code)
  │      source_id resolves in registry? locator grammar valid? since well-formed?
  │ 1. evidence resolution (plain code + retrieval)
  │      source ingested into source_chunks?  ── no ──► status: pending-source (queue)
  │      fetch chunk(s) at locator  ── locator resolves to nothing ──► verdict: locator-not-found
  │ 2. quote fast path (plain code, only if quote present)
  │      normalized fuzzy match of quote against located chunk text
  │      miss at locator → search quote across whole source (catches locator typos;
  │      a hit elsewhere = verdict quote-found-elsewhere, locator auto-correctable)
  │ 3. entailment (university-API LLM, context-blind)
  │      input: canonical claim text (incl. since), located chunk(s) ± parent section,
  │             quote if any — nothing else
  │      output: verdict + minimal grounding span(s) + short machine-readable rationale
  │ 4. verdict recording (plain code)
  │      verification block written into the record's citation entry; batch transcript
  │      anchor recorded; fact status updated per the admissibility rule
```

Stages 0–2 are deterministic and free; stage 3 is the only model spend. Everything below
argues the contested choices inside this skeleton.

### 2.2 Evidence acquisition: live fetch vs index-only

| Option | How | Pros | Cons |
|---|---|---|---|
| **Verifier fetches sources live at verdict time** | wget/render the cited URL or PDF per claim | No ingestion dependency; always current | Non-reproducible verdicts (page changed between proposer and verifier); slow; re-downloads per batch; robots/TDM compliance re-checked constantly; PDF extraction quality varies per run |
| **Index-only: verifier reads `source_chunks` exclusively** | Verification requires prior ingestion (D15 pipeline); un-ingested source ⇒ claim parks in `pending-source` | Reproducible (content-hashed snapshots); proposer and verifier read the *same* text; one compliance point (the ingestion fetcher, D14); paywalled papers handled once at ingestion via university access (D15) | Ingestion becomes a hard dependency; a claim citing a fresh source waits for the ingestion queue |

**Index-only wins decisively.** It is already implied by D15 ("the D4 verifier reads the same
table") and it converts K1's hardest sub-case — "the source changed / never said that" — into
a hash-pinned non-event. The `pending-source` state is a feature, not a cost: it forces the
source-minting flow (registry entry → fetch respecting robots.txt/TDM → extract → chunk →
embed) to complete before any fact citing that source can exist, which is exactly the D4
source-first ordering. Paywalled papers: the agent files a `source-acquisition` request; the
developer drops the PDF (obtained via university access, D14/D15 confirm this is licit for the
private pipeline) into the snapshot store; ingestion proceeds; parked claims auto-resume on
the next batch. A `pending-source` age alarm (e.g. >14 days) keeps the queue from silting up.

One escape hatch worth keeping: a **registry-existence-only check** for citations whose claim
*is* the source's existence (e.g. "language L has an ISO standard" citing the standard) —
mechanical, no text needed.

### 2.3 Locator resolution inside `source_chunks`

The chunk table carries normalized locators and `section_path` (D15 schema). Resolution
ladder, cheapest first:

1. **Exact locator match** — claim's locator equals a chunk's `locator` (the common case when
   the proposer copied it from `search_sources` output, as the D15 workflow mandates).
2. **Containment match** — claim locator is a page/§ range overlapping a chunk's range
   (`pp. 492–495` vs chunk `pp. 493–494`).
3. **Scoped hybrid retrieval** — filter `source_id`, run FTS+vector with the claim text as
   query, rerank; accept top chunks only if they sit *near* the claimed locator (same chapter/
   §-prefix). A strong semantic hit far from the claimed locator is evidence of locator
   fabrication → `locator-not-found`, with the found chunk noted so the proposer can correct
   rather than guess.
4. **Small-to-big expansion** — always offer the entailment model the `parent_section_id`
   text when the located chunk alone is <~300 tokens or ends mid-argument; entailment over an
   orphaned half-paragraph is a known false-reject generator.

Trade-off in step 3: allowing retrieval to "rescue" bad locators improves throughput but
weakens the discipline that locators be machine-produced. Resolution: rescue is allowed to
*inform a bounce* (verdict `locator-not-found` + hint), never to silently pass a claim whose
cited locator was wrong. The claim must be re-filed with the correct locator — cheap for the
agent, and it keeps the corpus's locators honest.

### 2.4 Mechanical vs LLM code paths

**Mechanical (plain code, no model):**
- Registry/schema/locator-grammar validation (stage 0).
- Quote integrity: normalize (Unicode NFKC, collapse whitespace, strip soft hyphens/
  ligatures, normalize quotes/dashes) then token-level fuzzy match (partial ratio ≥ 0.90
  proposed; below 0.80 = `quote-mismatch`, between = LLM adjudicates OCR-vs-fabrication).
- `since` surface check: does any token in the located text lexically match the claimed
  version (`3.10`, `C++20`, `since Java 8`, `1.0`)? A pure *presence* precheck — absence
  doesn't fail the claim (prose like "introduced in the October 2021 release" is common), but
  presence lets the entailment prompt pin attention on the span.
- Quote-cap compliance (~50 words, D14) — CI-grade.

**LLM (entailment):** everything that requires reading: does the located text support the
claim; does it support the *whole* claim including the `since` value and any qualifier; or
does it actually assert something incompatible. A matched quote does **not** waive
entailment — quote-real-but-claim-overstated is precisely the K1 laundering pattern (04 §2.2)
— it only narrows the evidence window and raises prior confidence.

The entailment call is engineered as **claim decomposition + verdict**, not free chat: the
prompt asks the model to (a) list the claim's atomic assertions (presence, syntax form,
`since`, qualifier), (b) mark each as supported / not-supported / contradicted by the provided
text with a grounding span, (c) emit the overall verdict by a stated rule (all supported →
`supported`; some → `partial`; none → `unsupported`; any contradicted → `contradicted`).
Structured JSON out; temperature 0; the per-assertion table is what makes `partial` verdicts
actionable and feeds `since`-specific handling below.

**`since` semantics (D2):** the entailment output distinguishes *since-supported* ("feature
introduced in 3.10" — source supports the exact origin) from *as-of-supported* ("the 3.12
reference documents the feature" — source only bounds it from above). As-of-supported is a
legitimate `partial`: the presence assertion enters, the `since` value gets status
`as-of, not verified-since`, and the record lands in the back-dating work queue that D2
already anticipates. This single distinction dissolves what would otherwise be the largest
class of false rejects.

### 2.5 Verdict vocabulary and the admissibility rule

Per (claim, citation) pair — two mechanical pre-verdicts and four judgment verdicts:

| Verdict | Produced by | Meaning |
|---|---|---|
| `source-unavailable` | stage 1 | not ingested / acquisition pending (transient) |
| `locator-not-found` | stages 1–3 | cited locator resolves to nothing relevant (bounce) |
| `supported` | stage 3 | located text entails the full claim |
| `partial` | stage 3 | some atomic assertions supported (incl. as-of-only `since`) |
| `unsupported` | stage 3 | text is on-topic but does not entail the claim |
| `contradicted` | stage 3 | text asserts something incompatible |

(`quote-mismatch` / `quote-found-elsewhere` are stage-2 annotations attached to whichever
verdict results, not verdicts themselves.)

**Admissibility rule (proposed):** a derived fact enters the canonical store iff **at least
one of its citations is `supported`**, with community-tier (C/D) sources unable to be that
sole supporter (D3: corroboration only). `partial`-only facts do not enter as claimed — the
proposer gets one bounce to *narrow the claim to what the source supports* (usually shedding
or downgrading the `since`); the narrowed claim then verifies cleanly. `unsupported` and
`contradicted` never enter and bounce with the rationale. A `contradicted` verdict on one
citation of an otherwise-supported fact does **not** block admission — it auto-creates a
contradiction record (D5) and is a first-class **input to the D21 controversy score**, as are
surviving `partial` verdicts on secondary citations. This is exactly the interface D21
specifies ("partial verification verdicts" as an assessor input) and gives topic 12's status
lifecycle its verification-side statuses: `pending-source`, `bounced`, `verified`,
`verified-with-partials`, plus the D2 `since: as-of` marker.

Alternative considered — a numeric confidence score per verdict — rejected for the same
reason 02 rejected numeric source confidence: false precision, and thresholds would just
reintroduce a categorical boundary with extra steps. Ordinal categories + the per-assertion
table carry all the information the controversy assessor needs.

### 2.6 Verifier model choice (university API, D6 aliases)

Requirements: instruction-following JSON reliability, strong reading comprehension over
technical prose, cheap enough for every-claim use, latency-irrelevant (overnight batch), and
— important for K1 — *decorrelation from the proposer*: entailment errors should not be the
same errors the drafting model makes.

| Alias | Fit |
|---|---|
| `mini` (gpt-oss-120b) | Cheapest/fastest; different family from both Claude (proposers) and the Chinese-lab models — good decorrelation; comprehension ceiling on dense spec prose is the question mark |
| `glm` (glm-5.2) | Strong general model; fine candidate; likely the volume workhorse elsewhere in the pipeline, which *reduces* decorrelation if it also drafts bulk claims |
| `deepseek` (v4-pro, reasoning off) | Strong comprehension per call, deterministic-ish, good structured output; solid primary |
| `deepseek-thinking` | Best judgment on genuinely borderline entailment; slowest; overkill as the default |
| `coder` (qwen3.5-122b) | Code-tuned; entailment over prose is not its lane — skip |

**Proposed: a two-tier verifier with an escalation rule, settled by the golden set.**
Primary = **`deepseek` (reasoning off)** on every pair; escalate to **`deepseek-thinking`**
when the primary returns `partial`/`contradicted` or its per-assertion table is internally
inconsistent (expected ~5–15% of pairs). Additionally, **`mini` runs as a second opinion on a
10% random sample** of primary `supported` verdicts purely as a drift/error estimator — a
cross-family disagreement rate that trends up is the earliest available signal that the
primary is rubber-stamping. The golden-set benchmark (§2.8) makes the final call between
`deepseek` and `glm` as primary; the recommendation leans `deepseek` only because `glm` is
the more likely bulk-drafting model and the gate should not share a brain with the thing it
gates. Claude is deliberately **not** in the verification loop (D6: Claude never does volume)
except as an occasional manual spot-check instrument for the developer.

### 2.7 Context blindness — enforced structurally

The verifier is a **separate batch process** whose input is constructed by the runner from a
field whitelist: `{fact_id, canonical claim text, since, source_id, locator, quote}` — never
the record's free-text notes, never `claim_origin`, never proposer identity/model/persona,
never debate or chat context, never *other citations' verdicts* (each pair judged alone,
preventing anchor-on-the-first-verdict effects). The entailment prompt contains the claim,
the evidence text, and the rubric; nothing else. This is not prompt discipline — the
verifier process has no code path that reads those fields, which is auditable in review and
stable under prompt drift.

Prompt-injection hardening (04's surfaced risk, now concrete): chunk text is data. It is
delimited and the rubric states that instructions inside evidence are content to be judged,
not followed; the verifier has **no tools** (pure text-in/JSON-out — retrieval is done by the
runner beforehand, so there is nothing for injected text to call); and a cheap lexical scan
flags evidence chunks containing instruction-like patterns for the transcript record.

### 2.8 Calibration: golden set, error tolerances, drift watch

**Golden set** (committed to the repo, ~200–300 items, grown over time), stratified over the
failure taxonomy — roughly: 40% correct claims (should pass), and deliberate wrongs: quote
real but claim overstated (the laundering pattern — the single most important stratum),
fabricated/misplaced locators, wrong `since` (off-by-one-version), claims contradicted by the
cited text, right-claim-wrong-source, paraphrase-heavy correct claims (false-reject probes),
and OCR-noisy quotes. Wrong items are authored by inverting/perturbing verified real claims —
cheap to produce and realistic. Run in pytest like the D7 retrieval eval; re-run on any
verifier prompt or model change (`prompt_version` is already provenance, D5).

**Tolerances (proposed, to be ratified):** the cost asymmetry is extreme — a false accept
poisons a public, RAG-recycled corpus (K1's feedback loop); a false reject costs one agent
retry. So tune thresholds reject-ward: target **false-accept ≤ 2%** on the wrong strata
(measured, with the overstated-claim stratum reported separately — it will be the worst) and
accept **false-reject ≤ 10%** on the correct strata. If a model can't reach ≤2% FA alone, the
sample-based `mini` cross-check hardens into a mandatory second vote for `supported` (accept
only on agreement) — roughly squaring the correlated-error rate at 2× cost, still trivial
overnight.

**Ongoing drift watch:** (a) the 10% cross-family sample disagreement rate, batch over batch;
(b) **canaries** — each production batch silently includes a few known-wrong golden items;
any canary passing halts the batch and files an issue (same reflex as D13's failure bot);
(c) the developer's occasional manual audit of N random `supported` verdicts, logged.

### 2.9 Cost per fact and overnight throughput

Per (claim, citation) pair, typical: 1 embedding call + 1 rerank (only when locator rescue is
needed) + **one entailment call ≈ 2.5–4k input tokens** (claim ~100, rubric ~600, chunk +
parent expansion 1.5–3k) **+ ~200–400 output**; escalations double one call for ~10% of
pairs; the `mini` sample adds ~10%. Call it **~4–6k tokens/pair end-to-end**, ~1.15 LLM
calls/pair amortized.

Throughput on a "fairly slow" university API, assuming 20–60 s/call and modest safe
concurrency of 4 (the D6 wrapper's throttle owns this): **~1,000–4,000 pairs per 8-hour
overnight window**. Even the pessimistic end comfortably outruns any realistic drafting rate
(a per-language sweep produces hundreds of claims, not tens of thousands, per day). Cash
cost: zero (university API); the real budget line is the wrapper's cost-log entry feeding the
cost-per-accepted-fact metric (D6). Re-verification waves (source re-ingestion, D16 migration
fast-paths) batch the same way and are bounded by the same arithmetic.

### 2.10 Logging (D18 mechanics applied)

One verification batch = one run: `run_id = <date>-verify-<slug>-<seq>`, one
`transcript.jsonl` capturing every entailment/escalation call via the shared wrapper, one
`manifest.yaml` mapping `fact_id → {citation_index, msg_anchor}` per D18's ratified
one-transcript-per-batch, per-claim `#msg-N` anchors. The verdict block written into the
record's citation entry carries `{verdict, per_assertion, model, prompt_version, run_id,
anchor, date, evidence_chunk_ids}` — so a fact's citation popover "AI chat" link lands on the
exact entailment exchange, and `evidence_chunk_ids` + content hashes make the verdict
re-derivable. Large evidence chunks in the *published* transcript are truncated to
excerpt+hash per D18's copyright rule; the full text stays in the private snapshot store.

## 3. Recommendation

*Proposed* — the gate as one nightly batch process in `langatlas-kb`:

1. **Index-only evidence**: the verifier reads exclusively from `source_chunks` (D15);
   un-ingested citations park claims in `pending-source` with an acquisition queue
   (developer-assisted for paywalled items per D15; fetcher compliance per D14 lives solely
   in the ingestion pipeline). Reproducibility via content-hashed snapshots.
2. **Filter ladder**: schema/registry checks → locator resolution ladder (exact →
   containment → scoped-retrieval *bounce hints only*, never silent rescue) → quote fuzzy
   fast path (≥0.90 pass, ≤0.80 mismatch, LLM between) → decomposition-based entailment with
   per-assertion grounding → verdict. Matched quotes never waive entailment.
3. **Verdicts**: `source-unavailable | locator-not-found | supported | partial | unsupported
   | contradicted` per (claim, citation) pair. Admissible = ≥1 `supported` citation of tier
   A/B (C/D corroborate only, D3). `partial`-only bounces once for claim narrowing.
   `contradicted` on a secondary citation admits the fact but mints a contradiction record
   and feeds the D21 controversy assessor; surviving partials likewise. `since` gets the
   *since-supported vs as-of-supported* split; as-of lands in the D2 back-dating queue.
4. **Models**: primary `deepseek` (reasoning off), escalation `deepseek-thinking` on
   partial/contradicted/inconsistent (~10%), `mini` cross-family second opinion on a 10%
   sample of accepts as the drift gauge; final primary choice (`deepseek` vs `glm`) settled
   by the golden set, with a bias against sharing a model family with bulk drafting. No
   Claude in the loop.
5. **Calibration**: committed golden set (~200–300 stratified items, overstated-claim
   stratum first-class), targets FA ≤2% / FR ≤10%, pytest-run on every prompt/model change;
   per-batch canaries that halt on a pass; escalate `mini` to a mandatory second vote if FA
   misses target.
6. **Context blindness by construction**: whitelist-built prompts (claim + evidence + rubric
   only), pairs judged independently, tool-less verifier, evidence-as-data injection rule.
7. **Logging**: one transcript per batch with per-claim anchors (D18); verdict blocks carry
   run/anchor/model/prompt_version/evidence-chunk hashes for full re-derivability.
8. **Budget**: ~4–6k tokens and ~1.15 university-API calls per pair; ~1,000–4,000 pairs per
   overnight window at conservative concurrency — verification will not be the pipeline's
   bottleneck; cash cost zero.

Why this wins: every K1 sub-mechanism gets a named, tested counter — fabricated sources die
at the registry, fabricated locators at resolution (with rescue demoted to a hint),
fabricated quotes at fuzzy match, real-quote-overstated-claim at decomposition entailment,
verifier gullibility at the golden set + canaries + cross-family sampling, and verifier
contamination at structural context blindness. And it is solo-sized: plain code around one
batched LLM call, no new services, riding infrastructure D15 builds anyway.

## 4. Open questions for the developer

1. **Admissibility strictness**: ratify "≥1 `supported` tier-A/B citation admits; `partial`-
   only bounces once for narrowing"? The alternative (admit partials immediately with a flag)
   grows the corpus faster but publishes claims their own sources don't fully back.
2. **Error-rate targets**: are FA ≤2% / FR ≤10% the right asymmetry, and — since some false
   accepts will exist at any threshold — is the golden-set-measured rate acceptable to state
   publicly (e.g. on the site's methodology page) as an honesty feature?
3. **Second-vote default**: start with the mandatory two-model agreement rule for `supported`
   (safer, ~2× cost, still free), or start single-model + 10% sampling and harden only if the
   golden set demands it (recommended)?
4. **`pending-source` SLA**: is a 14-day age alarm on the acquisition queue (routing a
   prefilled request to the developer for paywalled items) the right pressure valve?
5. **Bounce budget**: how many times may a proposer re-file a bounced claim before it is
   dropped rather than retried (proposal: 2 — one locator fix, one narrowing)? Prevents
   agents grinding the gate through variation.
6. **Verdict visibility on the site**: do `verified-with-partials` facts get any visible
   marker distinct from the D21 controversy badge, or is verification detail
   popover/provenance-only (recommended: provenance-only; controversy is the user-facing
   signal)?

## 5. New brainstorm topics surfaced

- **Golden-set authoring methodology** — how deliberately-wrong claims are generated
  (perturbation taxonomy, who writes them, contamination hygiene so drafting agents never see
  them), and whether the set doubles as a public benchmark artifact.
- **Source-acquisition queue design** — the concrete request/fulfil loop for paywalled and
  not-yet-ingested sources (prefilled requests to the developer, ingestion triggers, parked-
  claim resume), sitting between this gate and the D15 ingestion CLI.
- **Re-verification cadence policy** — which events (source re-ingestion, extractor upgrades,
  verifier prompt/model bumps, D16 migrations) trigger which scope of re-verification, and
  how verdict provenance marks "verified under old verifier" (feeds topic 12's staleness
  story).
- **Contradiction-record lifecycle** — what happens after a `contradicted` verdict mints a
  record: routing into D5 debates, surfacing to the D21 assessor, and eventual resolution
  states (extends 04's contradiction register into the no-PR-gate world).

## Sources

- Honovich, O., et al. (2022). TRUE: Re-evaluating Factual Consistency Evaluation. *NAACL
  2022*. https://aclanthology.org/2022.naacl-main.287/ — meta-evaluation showing NLI-style
  entailment checkers must be judged on deliberately corrupted examples, the pattern behind
  the golden-set design.
- Laban, P., et al. (2022). SummaC: Re-Visiting NLI-based Models for Inconsistency Detection.
  *TACL 10*. https://doi.org/10.1162/tacl_a_00453 — granularity matters: sentence/chunk-level
  entailment beats whole-document, supporting the chunk-scoped verifier.
- Min, S., et al. (2023). FActScore: Fine-grained Atomic Evaluation of Factual Precision.
  *EMNLP 2023*. https://aclanthology.org/2023.emnlp-main.741/ — decomposing claims into
  atomic assertions before verification, the pattern behind the per-assertion entailment
  prompt.
- Tang, L., et al. (2024). MiniCheck: Efficient Fact-Checking of LLMs on Grounding Documents.
  *EMNLP 2024*. https://aclanthology.org/2024.emnlp-main.499/ — small dedicated checkers can
  match frontier models on grounded fact-checking, supporting the cheap-model-as-gate
  economics.
