# 04 — Multi-Agent Knowledge-Building Workflow

> Brainstorm output for Project Hermes. Topic: one expert agent per supported language, arguing
> to converge on a cross-language feature model, with every claim backed by verified sources —
> building an incrementally self-backing knowledge net. Source of truth: `context/input-brief.md`
> (esp. §2.4, §2.5, §2.7).

## 1. Problem framing

The owner's idea (brief §2.7): one expert agent per language; the experts argue among themselves
until they converge on a feature model that fits all languages, adding sources to the knowledge
base to back their arguments. Three distinct problems hide inside this:

1. **Model-shaping** — deciding the *shape* of the feature model (which features exist, how they
   are atomized, which layer they belong to, edge types between them). This is a design activity;
   "consensus" here means schema agreement, not fact truth.
2. **Fact-filling** — asserting *feature instances*: "language L realizes feature F, expressed as
   syntax S, with characteristics C." These are checkable claims about the world; every one needs
   a real source (brief §2.1: every user-facing fact needs a source).
3. **Grounding** — preventing agents from laundering their training priors into "facts". An LLM
   expert on Rust *will* confidently state true-sounding things with no source, or cite a source
   that does not say what the agent claims. This is the failure mode that kills the whole
   "self-backing net" idea if unaddressed: a net of confident hallucinations is self-*referencing*,
   not self-*backing*.

Additional real-world constraints (brief §2.7):

- Solo developer; human review bandwidth is the scarcest resource.
- Claude Code Pro subscription → session/usage limits; long free-chat debates burn tokens fast.
- Slow university-hosted API → usable for high-volume, latency-tolerant, low-IQ roles only.
- No GPU for local inference.
- Output must land as challengeable, human-readable artifacts (brief §2.5 — YAML-ish files on
  GitHub is candidate (a)) and feed the vector DB / RAG store (brief §2.1–2.3).

Key reframe: **"debate" is a review protocol, not a chat room.** What actually needs to survive is
an auditable trail: claim → evidence → challenge → resolution → recorded decision, all in files.
The agents' conversation itself is disposable; the structured residue is the product.

## 2. Options with trade-offs

### 2.1 Debate / consensus protocol

**Option A — Free multi-agent chat ("let them argue").**
All language experts in one shared conversation, converging organically.
- Pros: matches the romantic version of the idea; zero protocol design.
- Cons: token-explosive (N agents × M turns, each seeing the whole transcript); LLM agents
  exhibit sycophantic convergence (first confident claim wins); no structured output; consensus is
  "whatever the transcript trails off into"; impossible to audit; worst possible fit for Pro
  session limits. **Reject.**

**Option B — Structured claim → challenge → evidence rounds (proposer/challenger/judge).**
Fixed roles, fixed round count, fixed artifact formats:
1. *Proposer* (the expert for language L, or the feature-owner agent) emits a claim file:
   claim text + source citation + **verbatim quote** from the source.
2. *Challengers* (2–3 experts for contrast languages) each emit at most one structured challenge:
   `{type: counterexample | wrong-atomization | missing-source | quote-mismatch | scope}`, with
   their own quoted evidence if they assert a counter-fact.
3. *Proposer* gets one rebuttal round (may revise the claim).
4. *Judge/moderator* (a separate agent with no stake, or the human) records the resolution:
   accepted / accepted-as-revised / rejected / escalate-to-human.
- Pros: bounded cost (≤ ~6 messages per claim); every step is a file; disagreement is typed and
  therefore aggregatable ("feature F drew 4 wrong-atomization challenges → schema smell");
  challengers with different priors are the actual anti-groupthink mechanism.
- Cons: protocol design + orchestration code up front; rigid rounds can under-explore genuinely
  hard modeling questions (mitigate: `escalate-to-human` outcome).

**Option C — Independent parallel drafts + reconciliation (no live debate at all).**
Each expert independently fills the same per-feature questionnaire for its language; a
reconciler agent diffs the answers, and only *conflicts* trigger an Option-B mini-debate.
- Pros: cheapest by far; embarrassingly parallel; most claims (~"does Python have list
  comprehensions") will simply agree and need no debate; debate budget is spent only where
  experts actually disagree, which is exactly where debate adds value.
- Cons: needs a shared questionnaire schema first (chicken-and-egg with model-shaping); silent
  agreement on a shared *wrong* prior is possible (mitigate: verifier still checks every quote,
  agreement doesn't waive sourcing).

**Recommendation preview:** C for fact-filling, B for schema disputes and conflicts. Never A.

**Who moderates?** Three sub-options:
- Dedicated moderator agent (fresh context, sees only the claim + challenges, not the experts'
  personas) — good default; keeps judging cheap and prompt-injection-resistant.
- Rotating expert-as-moderator — saves an agent role but imports bias; skip.
- Human moderates everything — doesn't scale past a handful of debates; reserve the human for
  escalations and batch sign-off (see §2.6).

**How consensus is recorded:** never as prose. A `resolution` block appended to the claim file:
outcome, vote/challenge summary, moderator id, timestamp, and the final canonical fact emitted to
the facts store. Git commit per debate batch = free audit history, matching brief §2.5(a).

### 2.2 The grounding problem (source-first enforcement)

This is the load-bearing wall. Options, weakest to strongest:

**Option A — Prompt-level exhortation** ("always cite sources"). Known to fail; agents fabricate
plausible citations. Insufficient alone.

**Option B — Source-first workflow (retrieve-then-claim).** The expert is *forbidden from
asserting* until it has fetched a source. Mechanically: the claim template has required fields
`source_id`, `locator` (page/section/anchor), and `quote` (verbatim, ≤ ~50 words), and the
orchestrator rejects any claim file missing them. The agent's workflow is: search allowed sources
→ fetch → extract quote → then write the claim *derived from the quote*. Inverts the hallucination
direction: instead of "claim, then decorate with a citation", it's "evidence, then a claim that
the evidence supports."

**Option C — Independent quote verification (trust-but-verify).** A separate cheap verifier agent
(university API tier — slow is fine, this is batch work) receives ONLY `{source_id, locator,
quote, claim}` — never the debate context — and does two checks:
1. *Quote integrity*: fetch the source, confirm the quote appears verbatim (or near-verbatim with
   an explicit fuzziness threshold; normalize whitespace/typography). A pure string check can even
   be non-LLM code for exact matches; LLM only for fuzzy cases.
2. *Support check*: does the quote actually support the claim (entailment judgment:
   supports / partially-supports / does-not-support / contradicts)?
Failures bounce the claim back with status `unverified`; unverified claims can never enter the
canonical facts store. Verifier independence matters: it must not see *why* the expert wants the
claim to be true.

**Option D — Source allowlist + snapshotting.** Only sources from a curated registry (the brief
already lists a starter set: Van Roy & Haridi 2003, Jordan et al. 2015, pldb.info, hyperpolyglot,
official language references/specs, Wikidata) may be cited in the PoC. Each source gets a stable
id in the `.bib`-like registry (brief §2.1), and fetched content is snapshotted (hash + retrieval
date) so quote verification is reproducible and link rot doesn't silently invalidate facts. Web
search for *new* sources is a separate, human-gated action: an agent may *propose* a source, the
human approves it into the registry, only then may it be cited.

**Recommendation:** B + C + D together. B makes fabrication hard, C makes it detected, D makes it
bounded. Also record `claim_origin: prior | source-derived` — agents may still *use* their priors
to decide what to look for; they just can't publish a prior as a fact. Priors are hypotheses;
sources make facts. This distinction should be explicit in every expert's system prompt.

**Residual risks to accept knowingly:** (i) quote-real-but-cherry-picked — mitigated by
challengers who cite competing quotes; (ii) source itself is wrong — mitigated by human
challengeability (brief §2.5) and per-source reliability tiers (spec > textbook > community wiki);
(iii) verifier LLM errors — mitigated by exact-match fast path and human spot-checks.

### 2.3 Dedup and contradiction handling

- **Dedup at claim time:** before a proposer files a claim, it must query the existing facts store
  (embedding similarity over canonical claim text + exact key `(language, feature)` lookup). If a
  near-duplicate exists: extend/strengthen the existing fact (add a second source) instead of
  creating a sibling. A second independent source on an existing fact is *valuable* — record it as
  additional evidence, raising a simple confidence tier (single-source / multi-source /
  human-confirmed).
- **Contradiction types need different handling:**
  - *Factual contradiction* ("Go has/doesn't have generics") → often a versioning problem; the
    schema must carry `as_of_version` on feature instances. Force claims to be version-qualified
    and many "contradictions" dissolve.
  - *Atomization disagreement* ("is this one feature or two?") → schema issue, route to an
    Option-B debate on the feature model, not the facts.
  - *Characterization disagreement* ("ownership hurts learnability — how much?") → these are the
    quality-impact judgments from the brief; store as *attributed assessments with sources*, not
    single truths. The brief itself warns feature value is application-dependent; don't force
    false consensus here — record the spread.
- **Standing contradiction register:** unresolved contradictions live as first-class records
  (`contradictions/` dir) linking both claims; the site can even surface them ("disputed") —
  aligned with the brief's challengeability goal. Never silently overwrite one sourced claim
  with another.

### 2.4 Orchestration under real constraints (which role on which tier)

Roles and their demands:

| Role | Needs | Tier |
|---|---|---|
| Feature-model schema debates (Option B) | strongest reasoning, low volume | Claude (Pro, interactive or scripted sessions) |
| Language-expert claim drafting | good reasoning + source reading, medium volume | Claude, batched (one session drafts many claims) |
| Challenger passes | medium reasoning, parallelizable | Claude batched; can degrade to university API for easy passes |
| Quote-integrity verification | trivial/mechanical | plain code for exact match; university API LLM for fuzzy + entailment (slow OK — overnight batch) |
| Embedding for dedup/RAG | bulk, no reasoning | university API or any embedding endpoint |
| Moderator/judge | fresh-context judgment, low volume | Claude |
| Human owner | escalations, source-registry approvals, batch sign-off | — |

Orchestration mechanics that fit Claude Code Pro specifically:
- Drive everything as **filesystem-first pipelines**: claims, challenges, resolutions are files in
  the repo; each pipeline stage is a script that invokes an agent (Claude Code headless/SDK, or a
  subagent within a session) on a batch of files. Restartable, inspectable, diffable — and Pro
  session limits just mean "run the next batch tomorrow", nothing breaks.
- **Batch aggressively per session**: one Claude session = one expert drafting all its claims for
  one feature sweep, not one session per claim. Keep debate transcripts out of context by passing
  only the structured files each role needs.
- **Queue discipline**: a simple `status` field per claim file (`draft → challenged → revised →
  verified → accepted | rejected | escalated`) makes the whole pipeline a folder scan; no
  workflow engine needed for a PoC.

### 2.5 Batch shape: per-feature debates vs per-language sweeps

- **Per-language sweep** (expert fills all features for its language): best context reuse per
  expert; natural for fact-filling; conflicts only surface at reconciliation.
- **Per-feature debate** (all experts on one feature): best for schema questions and for features
  with known cross-language variance (typing, memory management); expensive if used for
  everything.
- **Hybrid (recommended):** phase 1 per-language sweeps to fill the matrix cheaply → reconciler
  diffs → phase 2 per-feature debates only for the conflicted/ambiguous cells. Empirically most
  cells of a 5×10 matrix will be uncontroversial.

### 2.6 Provenance metadata and human checkpoints

Every fact record carries (this is the provenance schema; keep it boring and complete):
`fact_id, claim_text (canonical), language, feature_id, as_of_version, source_id(s), locator(s),
quote(s), quote_hash, retrieval_date, proposer_agent (name+model+prompt_version), debate_id,
challenges[], resolution {outcome, moderator, date}, verifier {model, result, date}, status,
confidence_tier, human_review {reviewer, date} | null`.

Human-in-the-loop checkpoints (solo owner — protect their time):
1. **Schema sign-off** — human approves the feature model / questionnaire before any sweep starts
   (highest leverage point).
2. **Source registry approvals** — human gate on adding new sources (cheap, occasional).
3. **Escalations only** — moderator routes irresolvable debates to the human; everything else
   auto-flows.
4. **Batch review before merge** — accepted facts land as a git branch / PR of YAML files; the
   human skims the diff and merges. This *is* candidate (a) from brief §2.5 — GitHub PR review is
   the human challengeability mechanism, for the owner now and outside experts later.
5. **Spot-check sampling** — human verifies ~5–10% of verifier-passed quotes early on to calibrate
   trust in the verifier; taper off as confidence grows.

## 3. Recommendation — concrete PoC pipeline (5 languages × 10 features)

**Scope:** languages Python, Rust, Haskell, Go, JavaScript (deliberately spread across paradigms);
features: pick 10 from the brief's layer-2/3 lists mixing easy (first-class functions, pattern
matching) and contentious (memory management, typing discipline, effects/exceptions). 50 matrix
cells; expect ~150–250 sourced claims (multiple claims per cell: presence, syntax, version,
characteristics).

**Repo layout (all human-readable YAML, per brief §2.5(a)):**

```
knowledge/
  sources/registry.yaml        # allowlisted sources, .bib-like ids (CSL-YAML works well)
  sources/snapshots/<id>/      # fetched text + hash + date
  schema/feature-model.yaml    # features, layers, edge types — human-signed-off
  claims/<lang>/<feature>/NNN.yaml   # claim lifecycle files (status field)
  facts/<lang>/<feature>.yaml  # accepted canonical facts only (feeds vector DB)
  contradictions/              # standing disputes
  debates/<debate_id>.yaml     # challenge/resolution records
```

**Stages (each a script; each runs in bounded batches):**

0. **Bootstrap (human + 1 Claude session):** finalize the 10-feature questionnaire from the
   brief's model; seed `registry.yaml` with the brief's sources + the 5 official language specs.
   Human signs off. (Checkpoint 1.)
1. **Sweep (5 Claude sessions, one per language expert):** expert answers the questionnaire for
   its language, source-first: search snapshots/allowlisted sources → quote → claim files with
   `status: draft`. Priors allowed only as search guidance, flagged `claim_origin`.
2. **Verify (overnight, university API + plain code):** quote-integrity (exact-match code path
   first, LLM fuzzy fallback) + entailment check on every draft. Fail → `unverified`, bounced.
3. **Reconcile (1 Claude session):** diff the 5 experts' answers per feature; auto-accept
   uncontested verified claims to `facts/`; emit a conflict list.
4. **Debate (Claude, only conflicted cells — expect ~5–15):** Option-B rounds: proposer +2
   challengers + fresh-context moderator, ≤6 messages, typed challenges, resolution recorded.
   Irresolvable → `escalated`. (Checkpoint 3.)
5. **Human review (owner, ~1 hour):** handle escalations; review the PR of new
   `facts/` files; spot-check 10% of quotes; merge. (Checkpoints 4–5.)
6. **Index:** embed accepted facts into the vector DB with `fact_id` back-references
   (source display data stays in the normal DB per brief §2.3).

**Budget sanity:** ~8–10 Claude sessions total for a full 5×10 cycle, spreadable across days under
Pro limits; verification is free-ish on the university API because it is batch and latency-blind.

**PoC success criteria:** (a) ≥90% of accepted facts pass an independent human quote audit;
(b) at least one debate demonstrably *changed* an outcome vs. the proposer's draft (evidence the
protocol isn't theater); (c) at least one contradiction correctly dissolved via version
qualification; (d) end-to-end trace works: pick any fact on a rendered page → its quote → its
snapshotted source.

## 4. Open questions for the owner

1. **Version policy:** are facts pinned to a language version (`as_of Python 3.12`) or "current
   stable"? This decision shapes the schema and dissolves/creates many contradictions.
2. **Characteristics (quality impacts):** may these be attributed assessments with a recorded
   spread, or does the site require a single consensus value per cell? (The brief's own citation
   of Jordan et al. suggests the former.)
3. **Source ceiling:** are community sources (hyperpolyglot, pldb, wikis) acceptable as *sole*
   backing for a fact, or only as corroboration alongside specs/textbooks? Suggest per-source
   reliability tiers in `registry.yaml`.
4. **University API reality check:** what model(s), context window, and rough throughput? The
   verifier design (LLM entailment vs. code-only) depends on it.
5. **How much may an expert claim from the language's official docs without a debate at all?**
   (E.g., syntax previews could be auto-accepted if quote-verified against the official spec,
   skipping challengers entirely — big cost saver.)
6. **Citation format decision:** CSL-YAML vs. BibLaTeX vs. Hayagriva for `registry.yaml`
   (brief §2.1 asks for "most universal/modern"). Proposal: CSL-YAML (renders everywhere,
   YAML-native, matches the repo format).
7. **Agent persona depth:** do experts get real persona prompts ("you are the Rust expert,
   biased toward its idioms") or neutral "researcher assigned to Rust"? Personas make challenges
   sharper but risk performative disagreement.

## 5. New brainstorm topics surfaced

- **Source snapshotting & licensing** — storing fetched source text (even excerpts/hashes) for
  verification: copyright limits, snapshot storage strategy, link-rot policy.
- **Fact schema / canonical claim language** — a controlled vocabulary or template grammar for
  claim texts so dedup and contradiction detection are tractable (relates to topic on KB design).
- **Confidence & reliability model** — formalizing source tiers × corroboration count × human
  confirmation into the confidence score the Builder/Selector modules consume.
- **Prompt-injection surface of fetched web sources** — experts and verifiers read arbitrary web
  content; fetched text must be treated as data, never instructions (sandboxing the fetch role).
- **Scaling the pipeline past PoC** — from 5×10 to "many, many languages": incremental sweeps,
  re-verification cadence when sources update, and whether debates amortize (schema stabilizes,
  debates become rare).
- **Community contribution intake** — how GitHub-based human challenges (brief §2.5(a)) re-enter
  this pipeline: does a human challenge spawn the same claim→challenge→resolution machinery?
- **Evaluation harness for the agents themselves** — a small gold-standard fact set to regression-
  test expert/verifier prompts when models or prompts change (prompt_version is already in
  provenance for this reason).
