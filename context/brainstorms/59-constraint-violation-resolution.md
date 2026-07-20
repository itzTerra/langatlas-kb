# 59 — Constraint-Violation Resolution Path

> Backlog brainstorm for LangAtlas. Topic: when a sweep answer mechanically violates an
> ontology-level `requires`/`conflicts-with` edge or a Rule (topic 38's compiled `constraints:`
> list), whether it routes into the existing D5 conflicted-cell debate machinery unchanged or
> needs its own resolution path that can also flag the ontology-level edge/rule itself as
> possibly wrong — since fresh source-first sweep evidence about a real language contradicting a
> general rule is informative in its own right. Binding context: D2 (the knowledge model — the
> four combination-validation levels: dimension exclusivity, hard pairwise requires/conflicts,
> soft influences, Rule entities); D5 (multi-agent sweep workflow — independent per-language
> questionnaire sweeps, a reconciler diffs answers, only *conflicted cells* trigger structured
> debates: proposer + 2 challengers + fresh-context moderator, ≤6 messages, typed challenges);
> D16 (ontology versioning — migrations-as-idempotent-scripts, MAJOR bumps as the one human-gated
> exception to D1's no-PR-gate rule, the split/merge/move/removal casebook); D25 (fact status as
> three orthogonal axes — verification/freshness/dispute — and the ordinal controversy score,
> assessed structurally, GitHub-challenge activity kept separate); D36 (agent-runner commit
> protocol — content disputes and D25 controversy flags are explicitly *out of* auto-revert's
> scope: "those are supposed to land and render visibly flagged, not get reverted"); D38 (ontology
> change tooling — the blast-radius script, the RFC + impact-analysis GitHub Issue Form with a
> `change_type` dropdown, the migration-manifest disposition DSL, all gated by D16's human-gated
> RFC process); D39 (cross-cutting concern modeling — confirms the other three D2 validation
> levels, including hard requires/conflicts and Rules, are feature-pairwise/feature-set machinery
> with no dimension-shape assumption baked in, so this topic's constraint violations are exactly
> as "mechanical" for cross-cutting features as for tree-shaped ones); D46 (questionnaire
> compiler, topic 38 — mints the `constraints:` list this topic consumes, and already carries a
> **quick developer ratification of this exact question**: "constraint violations route into the
> existing D5 conflicted-cell debate machinery unchanged — no separate resolution path or
> auto-flagging of the ontology-level edge/rule itself." That ratification was a fast batch-review
> answer to brainstorm 38's open question 2, given without the dedicated design pass brainstorm 38
> itself suggested the question deserved ("substantive enough... it could become its own
> brainstorm"). This topic is that dedicated pass — it treats D46's answer as the developer's
> working default, not as settled beyond reopening, and checks it against a concrete worked
> example rather than re-asking the same abstract question). All proposals below are *proposed*,
> not ratified, per the project's decision-hygiene convention; where they diverge from D46's
> existing text, that divergence is flagged explicitly for the developer to accept, refine, or
> reject.

## Problem framing

D46 (topic 38) drew a clean line between two kinds of ontology-authored facts a sweep agent's
answer interacts with: **fact-bearing fields** (existence, `since`, characteristics, syntax — the
only things a sweep agent researches and sources itself) and **structural facts** (feature/edge/
rule existence, polarity, dimension `exclusivity` — authored once by the research phase, never
re-asked per language). Hard `requires`/`conflicts-with` edges and Rules fall in the second
category, but they aren't inert the way `layer` or `summary` are: they compile to a
`constraints:` list (topic 38 §O3, steps 4–5) that the reconciler mechanically checks every
sweep answer against. **This topic is about what happens the moment that check fails.**

### What "mechanically violates" means, precisely

Three distinct trigger shapes, all mechanical (no LLM judgment needed to *detect* them — that's
the whole point of compiling constraints in the first place):

1. **A `requires` violation** — a sweep agent marks `fi.<lang>.<feature-a>: present` where the
   ontology carries `edge.requires.<feature-a>.<feature-b>`, but the same sweep produced no
   `fi.<lang>.<feature-b>` record, or produced one marked `absent`. Worked example: Zig's sweep
   marks `ownership-borrowing: present` (say a hypothetical future language with a novel
   borrow-adjacent mechanism that doesn't actually need move semantics) but marks
   `move-semantics: absent` — directly contradicting `edge.requires.ownership-borrowing.
   move-semantics`, an edge the research phase sourced once, generically, against the general
   literature on ownership systems.
2. **A `conflicts-with` violation** — a sweep agent marks two features `present` that the
   ontology declares mutually impossible, e.g. `edge.conflicts-with.laziness.strict-evaluation-
   by-default` both marked `present` for the same language.
3. **A Rule violation** — a sweep agent's answers jointly satisfy a rule's `when_all` antecedent
   and the `forbids`-typed consequent, e.g. `rule-laziness-needs-purity`'s `when_all: [laziness,
   purity]` `effect: forbids` `then: unrestricted-mutation` fires because a sweep marked
   `laziness: present`, `purity: present`, AND `unrestricted-mutation: present` for the same
   language.

**Why this is not the same shape as D5's existing conflicted-cell case.** D5's structured debate
exists for *disagreement between agents* — two independent sweeps (or a sweep and an existing
record) produce different claims about the same `(language, feature)` cell, and the debate's job
is to adjudicate which claim the evidence actually supports. A constraint violation is a different
kind of event: **there is no second claimant.** One sweep agent, working alone, produced a set of
answers that are internally consistent with each other as *observations of a real language* but
inconsistent with a *generalization the ontology asserts about all languages*. The open question
is not "which of two agents is right" — it's "is the fresh, single-language, source-backed
evidence right, or is the general rule right, or are both right and the rule's phrasing is simply
too coarse (a "since"/scope qualification that dissolves the contradiction, per D5's existing
"many contradictions dissolve via since/version qualification" precedent)?" That last question is
squarely an **ontology-content question**, not a **which-agent-answer question** — and the
project already has a separate, purpose-built process for exactly that kind of question (D16's
RFC gate via D38's tooling), distinct from D5's per-fact debate.

## Options with trade-offs

### Option A — Route straight into D5's existing conflicted-cell debate machinery, unchanged

This is D46's current text. A constraint violation is treated as just one more kind of
"conflicted cell": the reconciler flags the `(language, feature)` pair(s) involved, spins up a
proposer + 2 challengers + fresh-context moderator, and the debate settles it in ≤6 messages the
same way any other disagreement is settled.

**Pros:**
- Zero new machinery — reuses infrastructure that already exists and will already be well
  exercised by ordinary agent-disagreement debates before constraint violations are common.
- Consistent mental model for anyone reading a debate log: "a conflicted cell went to debate" has
  one meaning everywhere, not two.
- Cheap in the common case, and the common case may genuinely be common: many "violations" will
  turn out to be sourcing errors (an agent mis-marked a feature `present` when the source doesn't
  actually support it) or `since`-qualification gaps (D5's own precedent — "Rust historically
  lacked X, gained it in edition Y" dissolves a lot of apparent contradictions) rather than
  genuine ontology errors. A debate whose challengers include "does the evidence actually support
  `present`" as a typed challenge already covers that majority case adequately.

**Cons:**
- **The debate participants are debating the wrong question by default.** D5's proposer/
  challenger roles are built to argue about a *fact* ("is `ownership-borrowing: present` for
  Zig correct"), not about whether a *rule* is correct. Nothing in the debate's typed-challenge
  vocabulary or its ≤6-message budget is aimed at "should `edge.requires.ownership-borrowing.
  move-semantics` itself be revised" — that's simply out of scope for what a debate resolves
  (structured resolution blocks per D5 record a *fact* outcome, not an ontology-edit proposal).
  If the debate concludes "yes, the evidence for both `present` marks is solid, and no `since`
  qualification saves it," the *ontology* question ("is this edge overgeneralized") never gets
  asked by anyone, because nothing in the machinery asks it.
- **The debate has no legal move that satisfies both facts at once.** If the evidence really is
  solid on both sides, a debate forced to produce a single resolved fact will either (a) reject
  one of the two well-sourced sweep answers to make the ontology's rule hold — actively mangling
  a correct, sourced observation about a real language to fit an incorrect generalization, which
  is exactly the "silently mangling the fact to fit" failure mode the task framing warns against
  — or (b) resolve as "unsettled," which parks the disagreement as a controversy-scored dispute
  (D25) with no path to actually revising the rule that's disputed. Either way, the rule itself
  stays unexamined, potentially forever, since nothing downstream of a D5 resolution routes back
  into D16/D38's RFC machinery.
- This is precisely the informativeness the task framing flags: fresh source-first evidence
  about a real language contradicting a *general* claim is a different-in-kind signal than two
  agents disagreeing about a *specific* claim, and Option A discards that signal by filing it
  under the wrong bucket.

### Option B — A distinct resolution path: constraint violations never go to D5 debate at all

Under this option, the reconciler detects a constraint violation and immediately treats it as an
**ontology-suspect event**, not a fact dispute. The sweep agent's answer still gets recorded (with
its own sourcing, per the ordinary sweep-answer commit path), but the mechanical validator
additionally opens a new kind of record — "ontology edge/rule `<id>` is suspected wrong, per
sweep evidence for `<language>`" — which routes through something close to D38's RFC + impact-
analysis machinery: a `change_type` (a sixth value, `constraint-dispute`, alongside `split | merge
| layer-move | dimension-move | removal | schema-breaking`) on the existing RFC Issue Form,
carrying the two contradicting sweep answers and their citations as the "dissenting evidence"
D38's RFC template already requires as a field.

**Pros:**
- Sends the question to the machinery actually built to answer it: D16's RFC gate exists
  precisely for "is a piece of the ontology wrong," with a human-gated review, a blast-radius
  script, and casebook-driven fact disposition — none of which D5's debate apparatus replicates.
- Never asks a debate to adjudicate something outside its designed scope (no proposer/challenger
  session is ever put in the position of "resolve this by rejecting a well-sourced fact").
- Matches D16's existing philosophy precisely: **ontology-level correctness is the one thing this
  project deliberately keeps human-gated**, even though D1 explicitly removes the human gate from
  ordinary fact commits. A constraint violation, by definition, is a question about whether an
  *ontology-level* generalization holds — squarely inside the one carve-out D16 already created,
  not a fact question that D1's no-PR-gate default should govern.

**Cons:**
- **Skips a cheap, high-value filter D5's debate already provides for free.** Not every mechanical
  violation is a real ontology problem — plenty will be ordinary sourcing mistakes ("the agent
  over-read a source and marked something `present` that isn't") or `since`-qualification gaps
  that a fast, cheap debate already resolves without ever needing to touch the ontology. Routing
  *every* violation straight to the RFC-weight process (a GitHub Issue Form, dissenting-evidence
  field, blast-radius script run, human objection window) is disproportionate for the common case
  and would flood the RFC queue with what turn out to be sourcing errors, undermining D16's own
  "MAJORs batch ~monthly, not routinely" cadence.
- **Skips the fact-level "is the evidence actually solid" adjudication D5 is good at.** An RFC
  process is built to reason about ontology-wide blast radius, not to interrogate whether one
  sweep agent's citation for `ownership-borrowing: present` actually supports that claim at the
  quote/entailment level — that's D24's verifier and D5's challenger-round territory, and an RFC
  reviewer shouldn't have to re-derive it from scratch.
- Doubles the resolution surface for what might, most of the time, be a mundane fact question —
  contributors and future maintainers now need to reason about two separate machineries for what
  looks, from the sweep agent's chair, like "my answer got flagged."

### Option C (hybrid) — D5 debate settles the fact question; a solid violation triggers a separate ontology-suspect flag

The immediate, mechanical constraint violation still opens a D5 conflicted-cell debate exactly as
Option A proposes — but the debate's scope is narrowed to the question D5 is actually built to
answer: **"is the evidence for each of the contradicting sweep answers solid, and does any
`since`/version qualification dissolve the apparent contradiction?"** This reuses every part of
D5 that already works (proposer/challenger roles arguing about evidence quality, the fresh-context
moderator, the ≤6-message budget, structured resolution blocks) without asking it to also
adjudicate ontology correctness.

The debate's resolution block gets **one new possible outcome**, alongside D5's existing ones
(resolved-as-A, resolved-as-B, resolved-as-both-with-since-qualification, unsettled): **"evidence
solid on both sides, no qualification dissolves it — constraint disputed."** That outcome is what
triggers Option B's ontology-suspect path: the reconciler auto-opens (or auto-drafts, for
developer confirmation) a `constraint-dispute`-typed RFC issue via D38's existing Issue Form,
pre-filled with the debate's own resolution block as the required "dissenting evidence" field —
so the RFC author isn't starting from a blank page, the same "draft, don't force a blank form"
principle D38 §2.1b already applies to the blast-radius script's starting manifest.

**Pros:**
- Cheap common case handled by the cheap machinery (D5), expensive/rare case (genuine ontology
  error) handled by the expensive/rare machinery (D16/D38's RFC gate) — proportionate to actual
  likelihood, matching the project's general "boring, cost-proportionate tooling" posture.
- No machinery is ever asked to do a job outside its designed scope: D5 only ever adjudicates
  evidence quality; D16/D38 only ever adjudicates ontology correctness. Neither is stretched.
- The informativeness the task framing flags is preserved rather than discarded: a debate that
  concludes "constraint disputed" is exactly the case where fresh sweep evidence about a real
  language *is* informative about the ontology, and this option is the only one of the three that
  gives that signal a concrete downstream destination.
- Fits neatly into D25's existing three-axis status model with **zero new axis or vocabulary
  needed**: the sweep answer's `dispute` axis is set to `contested`/`disputed` (already-existing
  values) with a note that the dispute is constraint-level, not fact-level; the controversy-score
  assessor (D25) already has "agent debate non-convergence" as one of its structured inputs, so a
  "constraint disputed" resolution naturally feeds a higher controversy score without inventing a
  parallel scoring path.
- Directly consistent with D36's already-ratified stance that "content disputes and D25
  controversy flags... are supposed to land and render visibly flagged, not get reverted" — this
  option's "land the fact, flag it, and separately open the RFC" behavior is the literal
  concretization of that existing sentence for this specific trigger, not a new policy invented
  for this topic.

**Cons:**
- One more resolution-outcome value to add to D5's structured-block vocabulary, and one new
  `change_type` value on D38's RFC Issue Form dropdown — genuinely small schema additions, but not
  literally zero-new-machinery the way Option A is.
- Requires the reconciler to know, at constraint-check time, which debates are "ordinary
  conflicted-cell" debates versus "constraint-violation" debates, so it can apply the narrower
  scope framing and watch for the new outcome value — a small addition to the reconciler's own
  logic (deciding *how to frame the debate's prompt*, not new agent infrastructure).

## What happens to the sweep in the meantime

Across all three options, the FeatureInstance record(s) involved in the violation should be
**committed, not blocked** — this follows directly from already-ratified project policy rather
than needing a fresh decision here:

- D1 already establishes no-PR-gate commits with auto-flagging for controversial/conflicting
  facts, never developer-review-gated commits.
- D36 explicitly excludes "content disputes, D25 controversy flags, and anything the D24 verifier
  already gated" from auto-revert's scope, stating plainly that these "are supposed to land and
  render visibly flagged, not get reverted."
- D25's `dispute` axis already has the vocabulary for this (`none | contradicted | superseded`,
  extendable to carry a constraint-scoped variant) — a derived display status already exists for
  "this fact is currently disputed" without inventing new schema.

So: the sweep agent's two (or more) contradicting FeatureInstance answers land as ordinary commits
the moment they clear D24 verification (same as any other sweep answer — the mechanical
constraint check is a reconciler-side cross-item validation, not a verifier-side admissibility
gate, per D46/D38's own framing of constraints as reconciler input, never sweep questions). The
reconciler's constraint check fires *after* landing (or as part of the same reconciler pass that
already diffs sweep answers against each other), flips the affected records' `dispute` axis, and
— under the recommended Option C — opens the debate and, on a "constraint disputed" outcome, the
RFC. Nothing blocks; the record is visibly flagged (site badge, MCP `caution` block per D35's
existing mandatory-caution-contract precedent) from the moment the violation is detected until the
debate (and, if triggered, the RFC) resolves it.

## Recommendation

**Option C (hybrid), refining D46's existing quick ratification rather than overturning it
wholesale.** Concretely:

1. A mechanically detected constraint violation (`requires`/`conflicts-with`/Rule, per topic 38's
   `constraints:` list) still opens a **D5 conflicted-cell debate** — reusing existing
   infrastructure for the part D5 is actually good at: adjudicating whether the contradicting
   sweep answers' evidence is solid and whether a `since`/version qualification dissolves the
   apparent contradiction. This part of D46's ratified text is **kept unchanged**.
2. D5's structured resolution-block vocabulary gains **one new outcome value**: `constraint-
   disputed` (evidence solid on both sides, no qualification dissolves it) — distinct from
   `unsettled` (evidence itself is weak/ambiguous on one or both sides, an ordinary controversy
   case with no ontology implication).
3. A `constraint-disputed` resolution **auto-drafts a `constraint-dispute`-typed RFC issue** via
   D38's existing Issue Form (a sixth `change_type` value), pre-filled with the debate's own
   resolution block as the required dissenting-evidence field — never auto-merged, since this is
   squarely inside D16's one human-gated carve-out; the developer decides whether the rule needs
   revision, stays as-is with the sweep answers recorded as a rare noted exception, or needs a
   `since`/scope refinement that's itself a small ontology edit.
4. **This is the one piece of D46's ratified text this brainstorm proposes to amend**: "route into
   the existing D5 debate machinery unchanged" becomes "route into D5, with a narrowed evidence-
   only scope and one added outcome value that can trigger D38's existing RFC path" — not a
   parallel resolution mechanism, just D5 plus a documented exit ramp into machinery that already
   exists for exactly this question.
5. **The sweep's FeatureInstance records land and render visibly flagged**, never blocked —
   direct application of D36's already-ratified auto-revert exclusion and D25's existing dispute
   axis, no new commit-protocol policy needed.

This keeps the "reuse D5, don't build a parallel debate mechanism" instinct behind D46's original
answer, while giving the genuinely-informative case (evidence solid, rule wrong) a real, already-
designed destination (D38's RFC tooling) instead of silently discarding that signal inside a
debate resolution that was never built to hold it.

## Open questions for the developer

1. **Does the refinement to D46 stand, or does the original quick ratification hold as-is?**
   D46 currently reads "no separate resolution path or auto-flagging of the ontology-level edge/
   rule itself" — this brainstorm's Option C recommendation directly proposes adding exactly that
   auto-flagging (gated through an RFC draft, not a silent auto-edit). Confirm whether this
   supersedes D46's existing text (with a dated amendment note, per the project's decision-hygiene
   convention) or whether the original "no" stands and Option A should be re-confirmed instead.
2. **Auto-draft or fully manual RFC trigger?** Should a `constraint-disputed` debate outcome
   *automatically* open the `constraint-dispute` RFC issue (pre-filled, unopened by a human until
   the developer looks at it), or should it instead land as a work-queue item (matching D1's
   existing "controversial facts are auto-flagged... surfaced... in a work queue" pattern) that a
   human or agent manually promotes into an RFC when they choose to act on it? This mirrors
   backlog topic 47's discussion-issue-promotion question and may want the same answer for
   consistency.
3. **Debate-outcome vocabulary naming** — is `constraint-disputed` the right label, distinct
   enough from D25's existing `disputed` controversy level (level 3) to avoid confusion between
   "this fact's controversy score is `disputed`" and "this debate's resolution outcome was
   `constraint-disputed`"? An alternative naming (e.g. `rule-suspect`) may read more clearly.
4. **What if only one of the two contradicting answers is well-sourced?** The worked examples
   above assume both sides are solidly sourced. If the debate instead finds one answer weakly
   sourced (say, `ownership-borrowing: present` cites only a tier-D blog post) and the other side
   solid, does that resolve as an ordinary D5 fact outcome (reject/qualify the weak claim, no RFC
   needed) with no further constraint-dispute machinery invoked at all — or should even a
   partially-solid violation still leave a lightweight note against the edge/rule for future
   pattern-spotting (e.g. "this rule has now had N debate-level challenges, even though none
   individually reached `constraint-disputed`")? This brainstorm assumes the former (no RFC unless
   both sides are solid) but flags the pattern-spotting idea as a nice-to-have, not designed here.
5. **Scope of the narrowed debate prompt** — should the reconciler's constraint-violation debate
   variant explicitly tell the proposer/challengers "you are only adjudicating evidence quality,
   not ontology correctness" as prompt-level framing, or is that implicit enough from the typed-
   challenge vocabulary already in place that no prompt change is needed? Concretely a topic-32
   (prompt registry) implementation detail, flagged here so it isn't lost.

## New brainstorm topics surfaced

- **RFC auto-draft vs. manual promotion, as a cross-cutting pattern** — open question 2 above
  ("does a mechanically detected event auto-open a human-gated review artifact, or land in a
  work queue for manual promotion") is structurally the same question backlog topic 47
  (discussion-issue-promotion) already asks for a different trigger (community GitHub Discussion
  threads promoted to issues). Worth folding this topic's instance into topic 47's eventual
  brainstorm as a second worked case, rather than deciding the general auto-vs-manual-promotion
  stance twice independently — **fold into topic 47**, not a new number.
- **Debate-resolution vocabulary as a small, shared registry** — this topic adds one new outcome
  value (`constraint-disputed`) to D5's resolution-block vocabulary; if future topics keep adding
  outcome values piecemeal (this one, plus whatever brainstorm eventually designs D30's "debate
  changed nothing detectable" threshold question left open), the vocabulary itself might deserve
  a single consolidated schema treatment rather than accreting one value at a time across
  unrelated brainstorms. Not substantive enough alone to warrant a dedicated topic yet — flagged
  for awareness only, revisit if a third such addition shows up.

## Sources

No new external sources introduced; all constraints trace to ratified decisions D1, D2, D5, D16,
D25, D36, D38, D39, D46, and to brainstorms 29, 30, 38 cited inline above.
