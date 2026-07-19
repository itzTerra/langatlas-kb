# 16 — Debate Cost/Quality Instrumentation

> Backlog brainstorm for LangAtlas. Scope (checklist item 16): measuring whether N-agent debate
> beats one careful agent + verifier; treating agent-chat logs as data; designing an agent/prompt
> regression eval harness. Derives from brainstorms 04, 07, 08. Binding context: D5 (multi-agent
> workflow, scoping superseded by D11), D6 (model tiering — Claude never does volume), D18/D24
> (chat logging → `langatlas-transcripts`), D21/D25 (controversy score), D24 (verification
> pipeline), D26 (provider-abstraction cost log + record/replay), D27 (research-phase R3/R4
> debate repurposing), D28 (phased language onboarding). Joins backlog topic 36 (golden-set
> authoring) for the shared corpus and topic 32 (pipeline observability) for the reporting
> surface this topic's measurements ultimately feed. All proposals below are *proposed* until the
> developer ratifies.

## Problem framing

The checklist phrasing — "measuring whether N-agent debate beats one careful agent + verifier" —
implicitly assumes a standing binary choice between two always-on pipeline shapes. That is not
what got ratified. Worth stating precisely, because it changes what this topic can even measure:

1. **D5 already rejected free-chat, always-on debate.** Brainstorm 04's Option C (independent
   per-language sweeps + a reconciler that diffs answers) is the ratified default; the
   proposer/challenger/moderator protocol (Option B) fires **only on conflicted cells** the
   reconciler surfaces, capped at ≤6 messages. Most facts in the sweep pipeline are never
   debated at all — they go straight from a single proposer's source-first claim through the D24
   verifier. So the sweep-pipeline comparison this topic can actually run is narrower than "N
   agents vs 1": it is *"does the challenger round, triggered only on detected disagreement, add
   value the D24 verifier alone would not have caught on the original (pre-challenge) draft?"*
2. **The sweep pipeline isn't running yet.** Per D11/D28, the per-language sweep — and therefore
   any conflicted-cell debates — starts with phase-1 onboarding (Python, C, Java, Rust, Haskell,
   Prolog), which itself waits on the frontloaded research phase reaching a `1.0.0` ontology
   (D27/D16). There is no sweep-debate data to analyze today.
3. **Debate is already running, in a different shape, right now.** D27's R4 (convergent ontology
   drafting) explicitly repurposes the D5 debate machinery with "schema-dispute challenge types"
   for contested carves during the research phase. These are model-shaping debates (does this
   split into two features? which layer/dimension?), not fact-filling debates — brainstorm 04 §1
   drew exactly this line between "model-shaping" and "fact-filling" debates, and D27 confirms
   R4 lives on the model-shaping side. So the *only* debate data available before phase-1
   onboarding is schema-dispute debate data, which is a different question from "does debate
   improve fact quality" — it's closer to "does debate improve ontology-carve decisions,"
   measured by different downstream signals (MAJOR-churn rate under D16, not verifier verdicts).
4. **D24's verifier is not a weak baseline.** It runs claim decomposition, per-assertion
   grounding, a filter ladder, and cross-family drift sampling, calibrated to false-accept ≤2% /
   false-reject ≤10% on a committed golden set. "One careful agent + verifier" in this codebase
   already means a fairly strong mechanical gate, not a synonym for "unchecked single pass." The
   fair comparison is therefore *"challenger round vs. verifier-alone,"* not *"debate vs. no
   quality control."*

Given all four points, this brainstorm reframes the checklist scope into two separable
questions, sequenced by when data becomes available:

- **Q1 (available now, research phase):** does R4's schema-dispute challenger round change
  ontology-carve outcomes enough to justify its Claude-session cost, versus a single architect
  agent proposing carves that go straight to developer sign-off (the graduated-ceremony
  free-restructure path D27 already allows during an active theme)?
- **Q2 (available from phase-1 onboarding onward):** for conflicted-cell fact debates, does the
  challenger round catch anything the D24 verifier, run alone on the pre-challenge draft, would
  have missed?

Both need the same underlying instrumentation: transcripts (D18) and cost logs (D26) treated as
queryable data rather than write-only audit trail, joined against fact/edge outcomes
(D23 fact ids, D25 controversy score, D9 challenge activity).

## Options with trade-offs

### 2.1 What counts as "debate wins"

**Option A — Verifier-replay counterfactual (proposed as the core metric for Q2).** For every
sweep-pipeline debate, the pre-challenge proposer draft is already a file (D5 provenance: claim
text + source + quote, `status: draft` before challenge). Re-run *that* draft through the D24
verifier pipeline exactly as if it had never been challenged, and compare its verdict to the
verdict eventually recorded for the accepted (possibly revised) fact.
- If the pre-challenge draft would have passed the verifier at the same tier as the debated
  outcome, the debate step added nothing measurable for that claim — the reconciler's conflict
  detection did the real work by *routing* the claim to a debate, but the debate's *content*
  (challenger counter-evidence, moderator revision) was redundant with what verification alone
  would have caught.
- If the pre-challenge draft would have passed verification but the debate demonstrably changed
  the claim (the brainstorm-04 §3 PoC success criterion — "at least one debate demonstrably
  changed an outcome vs. the proposer's draft"), that is a clean, mechanically detectable win:
  the verifier is checking claim↔source entailment, not cross-language consistency or
  atomization quality, and a challenger caught something orthogonal to what D24 checks.
- Pros: reuses machinery that already exists (D24 verifier, D26 record/replay), zero new
  agent calls, cheap to run in batch, directly answers Q2 rather than a proxy for it.
- Cons: only detects the subset of debate value that shows up as a verifier-legible
  claim/source mismatch; misses debate value that shows up later as *lower controversy* or
  *fewer human challenges* (Option B) or as better cross-language atomization (Option C).

**Option B — Downstream dispute-rate comparison.** Segment accepted facts by
`debate_id != null` vs `debate_id == null` and compare their D25 controversy-score distribution
and D9 GitHub-challenge rate over time.
- Pros: measures what actually matters to the site (contested badges, human correction load);
  uses signals that already exist per-fact with no new instrumentation.
- Cons: confounded — debated facts are, by construction, exactly the facts the reconciler
  already flagged as contested going in (D5's conflict-detection selection effect), so a debated
  fact having *higher* controversy than an undebated fact proves nothing (it was already the
  harder case); the honest comparison needs a matched baseline — undebated facts on the *same*
  feature/dimension pairing across a comparably contentious set of languages — which doesn't
  reliably exist. Usable only as a secondary signal, and only once enough facts exist that
  matching is feasible (post phase-2/3 per D28, not phase-1).

**Option C — Blind human/expert audit sampling.** Periodically sample debated and undebated
facts and have the developer (or, once recruited, a human expert per D9) rate correctness/
atomization quality blind to which path produced them.
- Pros: the only option that catches quality dimensions neither the verifier nor the controversy
  score can see (is this the *right* feature split, not just a *sourced* one).
- Cons: burns the scarcest resource in the whole project — solo-developer review time — which
  D1/D5/D27 have been deliberately designed to avoid spending on routine review. Only justified
  as an occasional calibration check (mirrors D4's existing 5–10% verifier spot-check idea), not
  a running metric.

**Recommendation preview:** A as the primary, cheap, always-on metric; B as a secondary
long-horizon signal once volume exists; C as an occasional calibration spot-check, not a metric.

### 2.2 Cost accounting

CLAUDE.md's constraints make the cost side asymmetric in a way that a token-count comparison
alone would misrepresent. Per D6/D26: Claude (Pro session/usage limits — the genuinely scarce
resource) does proposer/challenger/moderator work; the university API (slow but effectively
unmetered, per D6's "no cash budget, reasonable academic use") does verification. A debate that
costs "5x the tokens" of verifier-alone is not 5x as expensive in the resource that actually
constrains a solo developer running headless overnight batches — it's expensive in **Claude
messages/sessions per accepted fact**, which is a different axis than total tokens.

- **Proposed cost metric:** `claude_messages_per_accepted_fact`, computed separately for
  `debate_id != null` and `debate_id == null` facts, joined from the D26 cost log (already keyed
  by `run_id`/`prompt_id@version`) against D23 fact ids in the manifest's
  `resulting_fact_ids`. This is a pure join over data D18/D26 already write — no new logging.
- **Proposed unit of comparison:** not "debate vs. no quality control" (a straw comparison, per
  the problem framing) but "marginal Claude messages spent on the challenger+moderator rounds"
  vs. "marginal verifier-replay-detected wins" (Option A above) on the same debate set. If a
  research-phase or phase-1 debate batch shows, say, 4 Claude messages per debate and Option A
  detects a genuine win on 1 in 5 debates, that's a concrete, reportable number the developer can
  weigh — not a philosophical argument.
- **Latency is a separate, non-trivial cost** the checklist's framing under-weights: Claude
  session/usage limits mean a debate batch that pauses on a limit mid-run (per D26 §2.5's
  pause-and-checkpoint policy) delays the whole sweep-batch, not just the contested cells. Any
  report on debate cost should carry wall-clock-to-completion alongside message counts.

### 2.3 Regression eval harness for prompts/agents

**Option A — Minimal: extend the record/replay fixtures D26 already specifies.** D26 §"Testing
strategy" already commits to `replay.py`: recorded `(request-hash → response)` fixtures under
`tests/fixtures/providers/`, with cache misses failing CI. Add a small, hand-curated subset of
these fixtures tagged as **regression cases** — known-tricky proposer/challenger/moderator
inputs (a genuinely ambiguous atomization call, a claim that should get challenged, a claim that
shouldn't) with an expected structured-output shape or expected resolution outcome recorded
alongside the fixture. Re-run whenever a prompt (`prompt_id@version`) or resolved model id
changes; diff outputs against the recorded expectation; a human (the developer) reviews drift,
not an automated pass/fail, because "did the moderator's revision improve the claim" isn't a
string-equality check.
- Pros: zero new infrastructure — same fixture format, same replay harness, same
  `prompt_id@version` cache key D26 already uses for drift detection; scales down to "a dozen
  cases in a folder," which a solo developer can actually maintain; naturally grows from real
  debate transcripts (pull an interesting real case into the fixture set, per brainstorm 04 §5's
  "small gold-standard fact set to regression-test expert/verifier prompts").
- Cons: doesn't give a numeric pass rate, so it can't gate CI the way D7's Recall@5/MRR eval or
  D24's calibration set do — it's a diff-and-review tool, not a threshold gate.

**Option B — A scored golden set, matching D24's calibration-set pattern.** Build a
dedicated ~30–50-item golden set of (feature, language-pair, conflict-type) → expected debate
outcome (accept / accept-as-revised / reject / escalate) and expected verifier verdict on the
pre-challenge draft, scored automatically like D24's FA/FR targets, re-run on every prompt or
model change with a numeric threshold gating whether the change ships.
- Pros: matches the rigor of D24/D7's existing eval patterns exactly — same shape, same
  discipline, directly comparable dashboards.
- Cons: authoring 30–50 *debate*-outcome golden cases (not fact-verification cases — a
  different, harder authoring task: someone has to hand-adjudicate what the *correct* debate
  resolution is, including cases where reasonable experts would disagree) is real solo-developer
  effort, and there is no debate volume yet to draw cases from (per the problem framing, sweep
  debates don't exist before phase-1). Premature before real debates exist to mine cases from.
- This authoring effort should not fork from backlog topic 36 (golden-set authoring
  methodology), which already scopes "hand-labeled controversy cases" and explicitly says it
  "joins the topic-16 eval harness" — Option B, if ever built, is topic 36's job, not a parallel
  effort here.

**Option C — Full N-agent debate simulator with synthetic disagreement injection**, running
scheduled A/B batches between debate-on and debate-off pipeline configurations at scale.
- Pros: the only option that would produce a defensible statistical answer to the checklist's
  literal question.
- Cons: this is CI infrastructure for a debate volume the project doesn't have yet, built by a
  solo developer against a fixed effort budget, for a decision (keep/simplify the challenger
  round) that has a cheap fallback (Option A's verifier-replay counterfactual, run periodically
  by hand) already available. Reject for now; revisit only if phase-2+ sweep volume (D28) makes
  debate cost a real recurring line item worth automating around.

**Recommendation:** A now, feeding into topic 36's golden set as real cases accumulate; B
deferred to topic 36 once phase-1 debate volume exists; C rejected for the foreseeable future.

### 2.4 Timing — before or after the research phase concludes

The checklist itself asks this. Given the problem framing (§1), the honest answer splits by
question:

- **Q1 (schema-dispute debates, R3/R4) is running *now*.** Its instrumentation — tagging D18
  transcripts with `debate_id` and `outcome`, which the format already carries — costs
  essentially nothing extra to turn on immediately, and "logs as data" per the checklist scope
  is best satisfied by never having a gap to backfill. Recommend: wire the join query (transcript
  + manifest + D16 ontology-diff/migration-manifest outcome) as a small script now, run it
  informally at R4 checkpoints, no gating decision attached yet — just visibility.
- **Q2 (sweep-pipeline fact debates) cannot start before phase-1 onboarding produces its first
  conflicted cells** (D28). Building Option B's golden set or any statistically meaningful
  debate-vs-verifier comparison before then is pure speculation with no data to calibrate
  against — actively wasteful for a solo developer under D11's "no shortcuts that damage the
  long-term product" posture, which cuts both ways: it also means not front-loading effort on
  evals for a pipeline stage that isn't running.

## Recommendation *(proposed)*

1. **Turn on cheap, always-on instrumentation now, using data D18/D26 already capture.** Two
   small scripts, not a service: (a) a verifier-replay counterfactual runner (§2.1 Option A) that
   re-scores any debate's pre-challenge draft through the D24 verifier and records whether the
   debate changed the outcome; (b) a cost join (§2.2) computing
   `claude_messages_per_accepted_fact` segmented by `debate_id`. Both are pure reads over
   existing transcripts/cost-log/manifest data — no new logging fields, no new agent calls.
2. **Apply (a) to R3/R4 schema-dispute debates as they happen during the research phase**,
   informally, at R3/R4 checkpoints (which per D27 already require developer sign-off) — this
   answers Q1 with real data before phase-1 onboarding even starts, at near-zero marginal cost.
3. **Defer Q2 (fact-debate value) and any scored golden set (§2.3 Option B) until phase-1
   onboarding produces real conflicted-cell debates** (D28) — there is nothing to measure before
   then, and building the harness earlier would mean guessing at the shape of debate outcomes
   the project hasn't seen yet.
4. **Adopt the record/replay regression pattern (§2.3 Option A) as the standing "prompt
   changed, did behavior drift" check**, growing organically from real transcripts (both
   schema-dispute and, later, fact-debate cases) rather than authored from scratch — this is the
   minimal-viable harness CLAUDE.md's "boring, solo-maintainable technology" directive points to,
   and it rides infrastructure (D26 §2.6/testing) that is being built anyway.
5. **Do not build a debate-vs-no-debate A/B simulator (§2.3 Option C).** The cheap counterfactual
   in step 1(a), re-run periodically, is the right-sized answer to "is debate earning its keep"
   for a solo-developer project at this data volume; revisit only if phase-2+ debate volume
   (D28) makes the challenger round a visible, recurring cost line the developer wants to
   optimize.
6. **Route any eventual scored golden set through topic 36**, not as a fork of this topic's
   scope — topic 36 already claims "joins the topic-16 eval harness," and duplicating authoring
   effort across two topics would be exactly the kind of solo-scope-collapse risk (S1) the
   checklist elsewhere guards against.

## Open questions for the developer

1. **Is the verifier-replay counterfactual (§2.1 Option A) informative enough on its own**, or
   does the developer want the downstream dispute-rate comparison (§2.1 Option B) wired up now
   too, accepting its selection-effect confound, rather than waiting for post-phase-2 volume to
   make matching feasible?
2. **What threshold of "debate changed nothing detectable" would make the developer consider
   simplifying the challenger round** for some conflict types (e.g. auto-accept
   quote-verified syntax claims without challengers, per brainstorm 04 §4 open question 5,
   already flagged there but never answered)? This topic can supply the measurement; the
   threshold is a product call.
3. **Should R4 schema-dispute debate outcomes also feed the D16 MAJOR-churn tracking**, so a
   debate's "value" for ontology carves is measured against later migration cost (a carve that
   held up vs. one a MAJOR bump later reverted), not just the R4 checkpoint sign-off itself?
4. **Confirm the record/replay regression fixtures (§2.3 Option A) live under the same
   `tests/fixtures/providers/` tree D26 already specifies**, just with a `regression/` subfolder
   and a lighter-weight human-diff review step instead of CI pass/fail — or does the developer
   want them kept structurally separate from the CI-blocking fixtures to avoid accidentally
   gating commits on a diff-and-review-only check?

## New brainstorm topics surfaced

- **Counterfactual verifier-replay as reusable tooling** — the §2.1 Option A script (replay a
  pre-challenge draft through the current D24 verifier and diff against the recorded outcome) is
  generically useful beyond debate instrumentation: it's the same mechanism needed whenever the
  verifier model/prompt itself changes and old accepted facts need a "would this still pass"
  check. Worth designing once, shared between this topic and topic 32's observability surface,
  rather than building it twice.
- **Challenger-round auto-skip rules** — brainstorm 04 §4 already floated "syntax claims
  quote-verified against the official spec could auto-accept, skipping challengers entirely" as
  an open question that was never picked up; this topic's instrumentation is the natural source
  of evidence for deciding it. Small enough to fold into topic 16's eventual follow-up rather
  than standing alone, but worth a checklist pointer so it isn't lost again.
