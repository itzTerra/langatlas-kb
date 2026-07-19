# 46 — Challenger-Round Auto-Skip Rules

> Backlog brainstorm for LangAtlas. Scope (checklist item 46): brainstorm 04 §4's floated idea
> that syntax claims quote-verified against the official spec could auto-accept, skipping the
> challenger round entirely, and the open question (`open-questions.md`, "Deferred") on what rate
> of "debate changed nothing detectable" (D30's verifier-replay counterfactual) would justify
> that. Binding context: D5 (reconciler + conflicted-cell debate protocol, ≤6 messages, proposer +
> 2 challengers + moderator), D6 (Claude never does volume — auto-skip is fundamentally a
> Claude-message cost-saving move), D16 (the ontology-MAJOR human-gate pattern, reused here as
> governance precedent), D23/D24 (claim schema, six-verdict vocabulary, quote-fuzzy-match ≥0.90
> pass threshold, ≥1 `supported` tier-A/B admissibility rule, the K1 "quote real but overstated"
> laundering pattern the entailment stage exists to catch), D25 (confidence/verification status
> axes), D26 (`RunContext` policy core), D28 (phase-1 onboarding as the earliest source of real
> sweep-debate volume), D30 (origin of the verifier-replay counterfactual and cost-join
> instrumentation, ratified with the threshold question explicitly left open), D41 (`replay_verdict`
> as the shared library function this topic's instrumentation must extend, not duplicate), D43
> (the `custom.grounding` field — `formal-spec | reference-implementation-docs |
> vendor-dialect-docs | design-doc | third-party-reference` — that gives auto-skip eligibility a
> principled axis to key on), D44 (golden-set methodology, 13-strata perturbation taxonomy,
> overstated-claim as a first-class separately-reported stratum). Per the framing already fixed in
> `open-questions.md`, **this brainstorm does not pick a numeric threshold** — the sweep pipeline
> hasn't run, D28's phase-1 onboarding hasn't produced a single real conflicted-cell debate yet,
> and picking a rate in the abstract would be exactly the kind of premature-precision the developer
> already rejected once. The job here is the *mechanism*: eligibility, what to measure, and how a
> future threshold — once ratified — gets rolled out safely. All proposals below are *proposed*
> until the developer ratifies.

## Problem framing

Brainstorm 04 §4 open question 5 asked "how much may an expert claim from the language's official
docs without a debate at all?" and named syntax-preview auto-accept as a candidate "big cost
saver." D30 picked this up, built the verifier-replay counterfactual as the measurement mechanism,
and then correctly stopped short of a threshold — the counterfactual needs real debates to run
against, and D28's phase-1 onboarding (the first source of sweep-pipeline conflicted cells) hasn't
started. `open-questions.md` restates this precisely: revisit once D30's instrumentation has
produced real numbers, don't pick a threshold now.

That leaves three things worth designing now, none of which requires a threshold to exist first:

1. **Eligibility** — auto-skip cannot mean "any claim quote-verified against the official spec."
   D24's own admissibility rule already requires ≥1 `supported` tier-A/B citation for *every*
   fact, debated or not — a claim that merely clears that bar is not evidence the challenger round
   is redundant, it's evidence the mechanical gate is working as designed. What's actually being
   asked is narrower: for *which claim types*, when a pre-challenge draft already clears
   verification cleanly, does a challenger historically add nothing the verifier wouldn't have
   caught? That's a claim-*type*-scoped empirical question, not a blanket "spec quote = safe"
   rule, and D24's own problem framing exists precisely because "quote real but overstated" (K1)
   is a documented failure mode a fuzzy-match pass does not, by itself, rule out.
2. **Measurement** — D30's verifier-replay counterfactual (reused via D41's `replay_verdict`) was
   designed to answer "did the debate change the outcome," aggregated. Deciding auto-skip
   eligibility needs the same signal *stratified* by claim type and grounding, plus a denominator
   the aggregate metric doesn't currently carry: how many facts of the candidate claim type never
   entered debate at all (because the reconciler found no conflict), since those are the facts an
   auto-skip rule would eventually also need to behave safely on.
3. **Rollout** — even with a ratified threshold, "skip the challenger round" is a change to the
   one place in the pipeline (D5's debate protocol) that D30 itself flagged as still contributing
   something the verifier doesn't check (cross-language consistency, atomization quality, source
   framing) on top of claim↔source entailment. A safe rollout needs a kill switch and a permanent
   audit lane, not a one-way flag flip, because the downside of a bad auto-skip call is a silently
   wrong fact committed under D1's no-review-gate model.

## Options with trade-offs

### O1 — Eligibility: which claim types are even candidates for instrumentation

**1a (recommended) — narrow whitelist, keyed on D43's `grounding` field.** A claim is *eligible
for auto-skip consideration* only if all of: (i) claim type is a layer-1 syntax claim (D2's
feature layers) — the class brainstorm 04 §4 actually named, and the one where "does this syntax
exist / how is it spelled" has the least room for the kind of judgment-call ambiguity that makes
semantic or quality-impact claims worth a second opinion; (ii) the backing source's
`custom.grounding` (D43) is `formal-spec` — not `reference-implementation-docs` or
`vendor-dialect-docs`, both of which D43 exists specifically because "the spec says" and "the
implementation does" can diverge, which is exactly the kind of disagreement a challenger is suited
to catch and a mechanical quote-match is not; (iii) the D24 quote-fuzzy-match score is at or above
the existing 0.90 pass threshold (no widening of that number for this purpose); (iv) no `since`
back-dating is in play (D2's `since` field ships through a separate as-cited/back-dated pipeline
this topic shouldn't touch). This is deliberately the single narrowest slice brainstorm 04 §4
actually proposed — everything else (semantic claims, quality-impact assessments, anything sourced
from an implementation rather than a formal spec) stays outside consideration until this narrow
slice has its own real data.

**1b — broad eligibility by verifier confidence alone**, any claim type/verdict above the fuzzy-
match threshold regardless of layer or grounding. Pros: bigger cost saving if it works. Cons:
conflates "the mechanical gate is confident" with "a challenger would add nothing," which is
precisely the distinction D24's entailment stage and the K1 framing exist to separate — a
confident wrong quote-match is a documented failure mode, not a hypothetical, and semantic/quality
claims are exactly where the brief (Jordan et al. 2015 spread-of-assessment framing, already
folded into D2/D25) says single-value judgment is the wrong model in the first place. Reject as
the starting scope; 1a's slice is where confidence and low-judgment-content genuinely coincide.

**1c — expand claim-type-by-claim-type only after each type accumulates its own verifier-replay
data**, i.e. 1a is the *first* whitelist entry, not the *only* one ever — a `reference-
implementation-docs` syntax claim, or a `formal-spec` semantic claim, could each earn eligibility
later on their own measured rate, never inherited from 1a's rate. This is not a separate option so
much as 1a's stated growth path — folded into the recommendation below rather than kept as a rival.

### O2 — Mechanism: what "skip" concretely means inside D5's protocol

**2a — reconciler-level suppression.** For eligible claim types, the D5 reconciler never routes a
conflicted cell to debate at all, even when independent sweep answers genuinely disagree; instead
some other rule (highest source tier wins, or straight to `escalated`) resolves the conflict.
Pros: the largest possible cost saving — removes the debate entirely, not just the challenger sub-
step. Cons: this changes what "conflict" means for eligible claim types, is the version of
auto-skip most likely to quietly launder a genuine disagreement between two sweep agents (which is
exactly the signal D5's reconciler is designed to surface, independent of what the verifier alone
would say), and cannot be evaluated by the verifier-replay counterfactual as designed — that
counterfactual assumes a debate happened and asks whether it changed anything; 2a removes the
debate, so there is nothing to replay against. Reject as the initial mechanism; the measurement
tooling this topic can actually build doesn't cover it.

**2b (recommended) — short-circuit an already-triggered debate.** The reconciler's conflict
detection is untouched — a genuine disagreement between independent sweep answers still routes to
debate exactly as D5 specifies. What changes is a new first step inside the debate: before
spawning challengers, run the proposer's pre-challenge draft through the D24 verifier (the same
call the D30 counterfactual already makes, just moved from after-the-fact analysis to in-line
gating). If the draft is eligible (O1) and the verifier returns a clean `supported` verdict at the
required tier, accept the draft and skip challengers/moderator; otherwise proceed with the full
protocol unchanged. This is a strictly narrower, safer mechanism than 2a: it never changes which
cells get flagged as conflicted, it only changes what happens once a cell is already flagged, and
— critically — it is exactly the mechanism D30's Q2 framing already measures ("does the challenger
round catch anything the verifier alone would have missed on the pre-challenge draft"), so no new
counterfactual design is needed, only a stratified read of data D41's `replay_verdict` already
produces.

**2c — apply 2b, but only after N observed cases per eligible claim type**, i.e. the mechanism
itself carries a minimum-sample-size gate rather than trusting a ratio computed on a handful of
debates. This is a rollout-safety concern more than a mechanism-shape concern — folded into O4
below rather than kept separate.

### O3 — What the verifier-replay counterfactual needs to measure and log

D30/D41's `replay_verdict` already answers, per debate, "did the pre-challenge draft's verifier
verdict match the debate's final outcome." That is necessary but not sufficient to ever ratify an
auto-skip threshold. Three additions, all extensions to the existing `replay_verdict` call site
rather than a new tool (matching D41's own stated design goal — one shared function, multiple
consumers):

1. **Stratify by O1's eligibility dimensions.** Every logged replay result should carry claim
   type (layer), the source's `custom.grounding` (D43), and fuzzy-match score bucket, not just an
   aggregate pass/fail. Without this, a future "90% of debates changed nothing" headline number is
   useless for a claim-type-scoped decision — it could be 99% on trivial `formal-spec` syntax
   claims and 40% on `vendor-dialect-docs` semantic claims averaged into one figure.
2. **Track the denominator the aggregate metric currently lacks: undebated facts of the same
   eligible claim type.** The question auto-skip eligibility actually needs answered is not just
   "of the debates on this claim type, how many did nothing," but "of *all* facts of this claim
   type (debated and not), what fraction would an auto-skip rule have handled correctly" — the
   undebated majority is the population the rule will actually run against in production, and it
   never enters a debate for `replay_verdict` to score today. This is a straightforward join
   against the existing D18/D26 logs (fact records already carry `debate_id: null` for uncontested
   facts) — no new instrumentation, just a wider query.
3. **Flag, don't just count, near-miss disagreements.** When a debate's outcome differs from the
   pre-challenge draft (a genuine "debate mattered" case), log *what kind* of difference it was —
   a revised claim string, a corrected `since` value, a scope/exclusivity catch, an outright
   rejection — reusing D44's 13-stratum perturbation taxonomy vocabulary where it fits (the
   overstated-claim stratum in particular is the exact shape of miss a spec-quote-verified draft
   could still have). This turns "debate changed nothing X% of the time" from a single scalar into
   a breakdown the developer can actually reason about before setting a threshold — a rate of
   trivial wording fixes is a different signal from a rate of caught overstated claims, even if the
   raw percentages happened to match.

None of this requires new agent calls or new logging fields beyond what D18/D26/D41 already
capture — it's a wider, stratified query over existing data, consistent with D30's own "zero-new-
infrastructure" framing.

### O4 — Safe rollout once a threshold is eventually ratified

**4a — paper/shadow mode first.** Before any claim is ever actually auto-skipped, run the
eligibility check and log "would have auto-skipped, verifier verdict X" on every eligible debate
for a defined observation window, without changing behavior — the debate still runs in full. This
is what generates the stratified data O3 needs and gives the developer a real number to look at
before ratifying anything, exactly matching the open-question's own stated sequencing ("revisit
once instrumentation has produced real numbers").

**4b — live with a kill switch and a permanent audit sample.** Once the developer ratifies a
threshold (a future decisions.md entry, not this one), auto-skip goes live for the eligible claim
type(s), gated by a single config flag that reverts to full-debate behavior for that claim type
with no code change. Alongside it, a fixed fraction of auto-skip-eligible cells (proposed as a
developer-set starting point, not fixed here — this is exactly the kind of number that shouldn't
be picked in the abstract either) continue through the *full* debate protocol anyway, purely for
audit — their outcome is compared against what auto-skip would have done and feeds back into the
same stratified O3 reporting, functioning as a standing calibration check. This mirrors two
existing precedents rather than inventing a new pattern: D4's proposed 5–10% human quote spot-
check, and D24's cross-family drift sampling on ~10% of verifier pairs — "never fully turn off the
check, just shrink its footprint once trust is earned" is already this project's house style for
exactly this class of decision.

**4c (recommended) — 4a then 4b, never 4b alone.** Skipping straight to a live kill-switched
rollout without a shadow-mode observation period would mean setting the very first threshold on
zero real data, which is the thing the open question explicitly warns against. The audit sample in
4b should also never taper to zero — a standing, if shrinking, fraction of eligible cells stays on
full debate indefinitely, both as an ongoing calibration signal and as insurance against silent
drift if the verifier model, prompt, or ontology shifts underneath an already-ratified threshold
(the same "model/prompt changed, did behavior drift" concern D41's regression-fixture design
already treats as a standing risk elsewhere in the pipeline).

### O5 — Governance: who changes the eligibility whitelist or the threshold, and how

**5a — pipeline-tunable**, an agent or a scheduled report can widen eligibility or adjust the
threshold automatically once enough data accumulates. Reject: this hands away exactly the kind of
control the developer has consistently kept human-gated elsewhere in this project (D16's ontology-
MAJOR exception, D9's human-challenge channel) whenever a decision trades off rigor for
throughput — and auto-skip is precisely that trade-off, made explicit by D6's own framing of it as
a cost-saving move.

**5b (recommended) — a small versioned config (`config/auto_skip.yaml`) naming the eligible claim
types, their `grounding` requirement, and the ratified threshold**, changed only by an explicit
developer decision recorded in `decisions.md` — mirroring D16's MAJOR-bump governance pattern at a
much smaller scale (a config-file change with a paper-trail, not an RFC issue; this isn't ontology-
scale blast radius). The observability CLI (D41's `tools/observability/report.py`) grows a
subcommand surfacing the stratified O3 data so "is there enough evidence to widen eligibility" is
a report the developer reads, not a number a script decides on its own.

## Recommendation *(proposed)*

1. **Eligibility starts narrow (O1a)**: layer-1 syntax claims, `custom.grounding: formal-spec`
   sources only, fuzzy-match ≥0.90, no `since` back-dating in play — the exact slice brainstorm
   04 §4 named, not a broader "any confident claim" rule. Expansion to other claim types or
   grounding tiers happens later, per-type, on that type's own measured data (O1c), never
   inherited.
2. **Mechanism is a short-circuit inside an already-triggered debate (O2b)**, not reconciler-level
   suppression (O2a). The reconciler's conflict detection stays untouched; only the challenger/
   moderator sub-step is skippable, and only after the pre-challenge draft clears the D24 verifier
   at the required tier. This is also the only version of auto-skip the existing verifier-replay
   counterfactual is designed to evaluate — no new measurement mechanism needed, just a stratified
   read.
3. **Extend `replay_verdict` (D41) with stratified logging (O3)**: claim type × `grounding` ×
   fuzzy-match bucket, a widened query including undebated same-type facts as the true production
   denominator, and a taxonomy-tagged breakdown of what changed on the debates that did matter,
   reusing D44's 13-stratum vocabulary rather than a bespoke one. This is the concrete deliverable
   this brainstorm can hand to implementation now, independent of any threshold decision.
4. **Roll out in shadow mode before any threshold is set (O4a), then live with a permanent kill
   switch and audit sample once ratified (O4b)** — never skip the shadow-mode observation window,
   never let the audit sample taper to zero.
5. **Govern eligibility and threshold changes through a small versioned config file, developer-
   ratified each time (O5b)**, mirroring D16's MAJOR-gate pattern at config scale — not a value a
   scheduled report or agent adjusts autonomously, since it directly trades sourcing rigor for
   Claude-message cost (D6).

This sequencing means real implementation work (the O3 logging extension) can start now, without
waiting on phase-1 sweep volume, while the actual go-live stays exactly as gated as
`open-questions.md` already said it should be.

## Open questions for the developer

1. **Does the narrow initial eligibility slice (O1a — layer-1 syntax, `formal-spec` grounding,
   fuzzy-match ≥0.90, no `since` back-dating) match the developer's intuition for "the safest
   possible first cut," or should the very first instrumented slice be even narrower (e.g. also
   require zero prior contradiction history on the same feature/language pair) before any shadow-
   mode data collection begins?
2. **Is the short-circuit-an-already-triggered-debate mechanism (O2b) the right shape**, or does
   the developer want reconciler-level suppression (O2a) considered later once 2b has a track
   record — accepting that 2a would need its own, separately-designed measurement approach since
   the existing verifier-replay counterfactual can't evaluate a debate that never happens?
3. **What should the initial audit-sample fraction be (O4b)** — is a number like D4's 5–10% spot-
   check or D24's ~10% cross-family sample a reasonable starting anchor once auto-skip goes live,
   or does the developer want to set this only once real shadow-mode volume exists to size it
   against?
4. **Should eligibility-whitelist and threshold changes go through a lighter process than D16's
   full RFC-gated MAJOR pattern** (O5b proposes a plain versioned-config-file change recorded in
   `decisions.md`, no RFC issue/objection window), given the blast radius here is a claim-type
   subset rather than the whole ontology — or does the developer want the heavier process reused
   verbatim for consistency?
5. **Is there a rough volume goalpost worth naming now** (e.g. "don't even look at ratifying a
   threshold before N eligible-claim-type debates have accumulated shadow-mode data," tied to
   D28's phase-1 language set) so this doesn't quietly stay "revisit later" indefinitely once
   phase-1 onboarding starts producing debates — or is leaving it fully open, exactly as
   `open-questions.md` currently has it, still the developer's preference?

## New brainstorm topics surfaced

None.
