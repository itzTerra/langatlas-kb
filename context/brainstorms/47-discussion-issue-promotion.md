# 47 — Discussion→Issue Promotion Tooling

> Backlog brainstorm for LangAtlas. Scope per the checklist: whether the manual GitHub
> Discussion→Issue conversion named in brainstorm 18 §2.3 ever needs automating (a bot proposing
> promotion once a Discussion accumulates enough concrete detail) once volume justifies it — an
> explicit "whether it's ever needed" question, not a "design it now" mandate. Brainstorm 18 kept
> promotion manual by design, citing solo-developer bandwidth and zero launch-time volume, and
> listed automating it as a possible future topic only "if volume ever justifies it." Binding
> context: D32 (giscus Discussions scoped to feature/language pages only, the fixed category set,
> the four typed Issue Forms `challenge-fact.yml` / `propose-coverage.yml` / `request-language.yml`
> / `general-question.yml`, and the explicit Issues-resolve-into-commits / Discussions-are-
> open-ended division of labor stated in `CONTRIBUTING.md`), D36 (narrowly-scoped GitHub App
> pattern — `Contents/Issues: write`, `Checks/Statuses: read`, no `Pull requests` scope on the
> runner's own App; a *second*, separately-scoped App named as the escalation path once the D32
> external-PR skim needs `Pull requests` access, establishing "new trust surface gets its own App,
> not a widened existing one" as house pattern), D18 (every automated actor's activity is logged;
> no bot posts go unrecorded), D30/D46 (this project's established shadow-mode-before-live-rollout
> pattern for any automation that trades a human judgment call for a heuristic one). Builds
> directly on brainstorm 18 §2.3, which is the primary source of context here — this brainstorm
> does not re-litigate the Issues-vs-Discussions split itself, only whether the one remaining
> manual step in that split (recognizing when a Discussion is ready to promote) should stay manual.
> All proposals below are *proposed* until the developer ratifies.

## 1. Problem framing

D32 settled what a Discussion is for (open-ended debate, "I think this dimension is
under-modeled," "does anyone know a source for X") and what an Issue is for (a concrete,
resolvable claim that ends in a commit). The seam between them is a judgment call: a Discussion
thread starts as unstructured chatter and, sometimes, accumulates enough concrete detail — a
specific claim, a citable source, several people converging on the same correction — that it
*should* become one of D32's typed Issues. Today that recognition and the conversion itself are
both manual: the developer (or any participant, since GitHub's native "convert discussion to
issue" affordance is available to anyone with write access) has to notice the thread has
crystallized and act on it.

Two failure modes motivate even asking the question, both currently absorbed by low volume rather
than solved:
1. **Missed promotions** — a genuinely actionable claim sits in a Discussion thread indefinitely
   because nobody with write access happened to reread it after the point it became actionable.
   The claim never enters the D24 verification pipeline at all, silently defeating the entire
   point of having a promotion path.
2. **Developer toil at scale** — even if nothing is missed, triaging every active Discussion
   thread to ask "has this crystallized yet" is a recurring, unbounded-by-content-volume
   demand on a solo developer's attention, the exact category of cost D32 §2.6 already worries
   about elsewhere ("no growth chrome" — the funnel exists to reduce friction, not create a new
   monitoring job).

Against that: at any volume near launch, neither failure mode has a real cost. Zero Discussions
exist before the giscus embed ships (D32 hasn't itself been ratified/built yet as of this
writing), and even once it has, D28's phased language onboarding means the whole *site* has low
traffic for a long stretch of the project's life. Building promotion tooling now would be
automation in search of a problem — the checklist's own framing ("whether it's *ever* needed")
already anticipates that the honest answer might be "not yet, possibly not for a long time,"
and this brainstorm should not talk itself into recommending a build just because the mechanism
is interesting to design.

## 2. Options with trade-offs

### O1 — Stay fully manual indefinitely (the D32 §2.3 baseline)

No new tooling. The developer (or any maintainer) rereads active Discussions when they think to,
and uses GitHub's native "Convert to issue" button or manually opens one of D32's Issue Forms
referencing the Discussion. Pros: zero build cost, zero new bot identity, zero false-positive
risk — the two failure modes in §1 are real but, at near-zero Discussion volume, both have a
near-zero expected cost too. Cons: doesn't scale; the missed-promotion failure mode is silent
(nobody gets a signal that something was missed), so its cost is invisible right up until it
becomes real, which is a genuine argument for having *some* nudge before volume is large enough
to actively hurt.

### O2 — A threshold-triggered bot that proposes (or performs) promotion

The mechanism the checklist names outright: instrument each Discussion thread against a set of
signal heuristics, and once a thread crosses a threshold, take some automated action. Four
sub-questions this option has to answer regardless of whether it's ever built, because they're
the actual design content the checklist is asking for:

**2a — What signals indicate "ready to promote."** Candidates, roughly in order of how much
they individually indicate *concrete, actionable content* versus mere *activity*:
- **Concrete claim + source pairing present** — the strongest signal and the hardest to detect
  cheaply. A regex/keyword heuristic (a URL, a page/section locator pattern, a quoted string) is
  a weak proxy; an LLM classification pass ("does this thread contain a specific, sourceable
  claim about a feature or language, distinct from open-ended discussion?") is the accurate
  version but costs a Claude call per evaluated thread — directly implicating D6's "Claude never
  does volume" constraint if run on every comment rather than on a coarse schedule.
- **Distinct participant count** (e.g. ≥3 people, not one person posting three times) — a proxy
  for "this isn't just one person's pet theory," but participant count alone says nothing about
  whether the content is actionable; a thread can have five participants agreeing on something
  vague forever.
- **Reaction counts** (👍 on a specific comment) — the weakest signal on its own (cheap to game,
  cheap to ignore, and GitHub reactions don't distinguish "I agree this is true" from "I agree
  this is worth discussing"), but useful as a tiebreaker alongside the claim+source signal to
  identify *which comment* in a long thread is the one worth promoting.
- **Reply count / thread length** — a volume proxy, not a content proxy; a long thread can be
  pure bikeshedding, a short one can contain a single decisive claim+source comment. Useful only
  as a pre-filter to decide which threads are even worth spending an LLM classification call on.
- **Staleness** (no activity for N days) — the inverse signal: a thread that stopped getting
  replies is either resolved-by-silence (nothing to promote) or abandoned-before-crystallizing
  (also nothing to promote), so staleness is really a *stop evaluating this thread* signal, not
  a promotion trigger — worth noting because it's easy to mis-design as "promote stale threads"
  when its actual job is closing the evaluation loop, not opening one.

The only combination that avoids both spamming (github noise from mis-fires) and missing real
cases is a two-stage funnel: cheap structural signals (reply count, participant count, staleness)
filter which threads are worth the expensive step, and the expensive step (an LLM
claim+source-presence classification) decides whether to actually act. This mirrors D46's own
recently-ratified pattern of a cheap mechanical pre-filter feeding a judgment-requiring step,
rather than a single blended score.

**2b — How it interacts with D32's four Issue Forms.** This is the sharpest design question and
the one GitHub's own tooling answers badly. GitHub's native "Convert discussion to issue"
affordance is one-directional and structurally lossy for this project's purposes: it copies the
discussion's opening post verbatim into a new, untyped issue body — it does not, and cannot,
populate one of D32's typed Issue Forms (`challenge-fact.yml` fields like `fact_id`/
`current_value`/`proposed_correction`, or `propose-coverage.yml`'s `feature_id`/`language_id`).
A converted issue would land outside D32's auto-labeling scheme entirely, defeating the whole
point of the typed-form set (a machine-sortable queue for the D27 agent-runner and the
developer). The better mechanic, if this is ever built, is the bot **drafting a fresh Issue Form
submission** — populating the appropriate template's fields from the classified claim/source and
posting it as a genuinely typed, labeled issue, with a comment on the originating Discussion
linking to the new issue (not using GitHub's native convert button at all). This requires the
bot to also decide *which* of the four templates fits — `challenge-fact` if the claim disputes an
existing fact, `propose-coverage` if it's about a currently-empty cell, otherwise no good
existing template fits and the safe default is to *not* auto-file, just flag for a human to
route (see 2d below on why auto-filing into the wrong template is worse than not filing at all).

**2c — GitHub API mechanics.** GitHub Discussions are exposed only through the **GraphQL API**,
not REST (`discussion`, `discussionComment` types, `addDiscussionComment` mutation to post the
promotion proposal or the "filed as #NNN" follow-up comment); Issues (including issue-form
submissions) remain REST-or-GraphQL either way. A bot needs read access to discussion threads and
comments (to evaluate 2a's signals), write access to comment on a Discussion (to propose
promotion or confirm it happened), and write access to create Issues (to file the promoted item)
— three distinct capabilities, none of which the D36 runner App currently holds (that App is
scoped to `Contents/Issues: write` + `Checks/Statuses: read`, with Discussions untouched because
D36 predates D32's Discussions feature entirely).

**2d — Bot identity and scope, tied to D36.** D36 already establishes the pattern this decision
should reuse rather than reinvent: a new trust surface gets a new, narrowly-scoped GitHub App,
not a widened grant on an existing one (the concrete precedent: the external-PR skim gets its
*own* second App once it needs `Pull requests` scope, rather than the runner App growing that
permission). A Discussion-promotion bot is a third distinct trust surface — it's the first
automated actor that posts *into a public community space* rather than only committing to the
KB repo or filing issues against the runner's own findings — and arguably carries a **higher**
reputational cost per mistake than either existing App: a bad auto-revert or a wrongly-filed
runner issue is an internal pipeline hiccup, but a bot publicly proposing a wrong or
tone-deaf promotion, or worse, mis-attributing/mangling someone's comment into an issue, happens
in front of the exact human contributors D32 §1's "invested outsider" and "would-be co-author"
personas are trying to court. **Recommendation if built: a third App**, scoped to
`Discussions: write` + `Issues: write` only (no `Contents` — this bot never touches the KB repo's
record files), named distinctly in its bot identity (not reusing `langatlas-bot[bot]` from D36,
so a human glancing at a Discussion comment can tell "community-facing bot" from "pipeline bot"
at a glance) — matching D36's own reasoning almost exactly, just at the Discussions layer instead
of the Contents/PR layer.

**False-positive cost:** the dominant risk of O2, and the reason its design content matters more
than its build cost. Three concrete failure shapes: (i) the bot proposes promotion on a thread
that was actually just enthusiastic agreement with no real new claim, reads as noise/pestering;
(ii) the bot auto-files an issue that mis-transcribes or truncates the actual claim (an LLM
classification error, not a mechanical one), creating a queue item that wastes a future agent
session's time chasing a claim nobody actually made that way; (iii) the bot picks the wrong Issue
Form template, filing a `propose-coverage` where a `challenge-fact` was meant (or vice versa),
producing a mislabeled item the D27 agent-runner's auto-labeling assumptions don't expect. All
three argue for the bot **proposing, not performing** promotion at least initially (post a
comment: "this looks like it might be ready to promote to a `challenge-fact` issue — react 👍 to
confirm" rather than silently filing) — cheaper to build than full auto-filing, avoids the worst
of (ii) and (iii) by keeping a human in the loop for the one step (transcription accuracy,
template choice) an LLM is least reliable at, and is a strict subset of the mechanism needed for
full auto-filing later if the propose-only version proves itself.

### O3 — A private developer-facing digest instead of a public-facing bot

A cheaper middle ground: rather than a bot that posts *into* Discussions, a scheduled job (using
the same 2a signal heuristics) that surfaces "these N Discussion threads look like they might be
ready to promote" as a private report the developer reads — a `tools/community/report.py`
subcommand in the same style as D41's observability CLI and D44's coverage CLI, or even just a
periodic email/notification — with promotion itself staying a manual click exactly as O1 already
has it. Pros: solves the *missed-promotion* failure mode (§1's real cost) without touching the
public-facing false-positive risk at all — nothing is ever posted where a contributor can see it
misfire; reuses existing CLI/reporting infrastructure patterns (D41, D44) rather than inventing a
new bot identity or App; strictly cheaper to build than O2 (no GraphQL write path, no new App, no
template-selection logic, no risk of a public mis-fire) while still addressing the real problem
O2's threshold logic was trying to solve. Cons: doesn't reduce the developer's actual triage
labor the way a fully automated pipeline would — it converts "reread every thread" into "read a
shorter, pre-filtered list," which is real leverage but not the "bot handles it end to end"
version the checklist's framing gestures at; still needs 2a's signal design and, if the digest is
to be genuinely useful rather than noisy, still benefits from the same cheap-filter-then-LLM-
classify funnel described in 2a.

## 3. Recommendation *(proposed)*

**Stay on O1 (fully manual) until Discussions exist and accumulate real volume; when a nudge
becomes worth building, build O3 (private digest) before ever considering O2 (public-facing
bot), and treat O2 as a possible later escalation of O3, not a separate project.**

Concretely, in sequence:

1. **Ship nothing for this topic now.** D32 hasn't itself shipped yet (the giscus embed doesn't
   exist as of this brainstorm), so there is no Discussion volume to instrument against — building
   promotion tooling ahead of any Discussions existing at all would be designing against zero
   real data, the same anti-pattern brainstorm 46 already flagged for auto-skip thresholds.
2. **Trigger condition to revisit:** once giscus is live and Discussions accumulate real traffic,
   the concrete signal that "manual is starting to cost something" is the developer noticing
   either (a) a recurring pattern of promotions happening *late* (a thread sat crystallized for
   longer than feels right before someone noticed), or (b) promotion triage itself consuming a
   noticeable, recurring chunk of maintenance time — not a specific thread count or Discussion
   count picked in the abstract, since (per D30/D46's own established caution about premature
   numeric thresholds) there's no principled way to name "N threads/month" as the trigger before
   real Discussion behavior is observed. This mirrors D32 §2.5's own graduated-posture pattern
   ("revisit once the channel has a track record") applied to a different lane of the same
   funnel.
3. **When that trigger fires, build O3 first** — the private digest, reusing 2a's signal design
   (cheap structural pre-filter: reply count / participant count / staleness-as-stop-signal,
   feeding an LLM claim+source classification pass only on the pre-filtered subset) but with zero
   public-facing action. This is the cheapest version that actually removes the §1 failure modes'
   cost, and it's a strict logical prerequisite for O2 anyway: nothing about O2's harder design
   questions (2b template selection, 2c write-path mechanics, 2d bot identity) can be validated
   without first knowing the digest's classification step is accurate enough to trust, which O3
   is the natural place to observe.
4. **Only escalate to O2 if O3's own volume, over time, makes *developer-in-the-loop* triage
   itself the bottleneck** — i.e. the digest is accurate and useful, but there are now enough
   flagged threads per week that even reading the digest and clicking "promote" is a real time
   cost. At that point O2's public-facing propose-a-promotion-comment variant (never the silent
   auto-file variant, per §2's false-positive discussion) is the next step, gated by its own new
   App per 2d, itself gated by D18's logging (every bot-posted comment captured like any other
   automated actor's activity) and ideally a shadow period where O3's digest and O2's proposed
   promotions are compared before the bot is trusted to post unsupervised — the same shadow-
   mode-before-live pattern D46 already established for auto-skip.

The crux the checklist itself names — "whether it's ever needed" — resolves to: **probably
eventually, in the O3 form; possibly never, in the O2 form**, because O3 already captures most of
the real value (nothing silently missed) at a fraction of O2's build cost and reputational risk,
and O2 only earns its keep if O3's own volume proves the triage step, not just the noticing step,
has become the bottleneck.

## 4. Open questions for the developer

1. **Confirm the recommended sequencing** (O1 now → O3 once real Discussion volume exists →
   O2 only if O3's triage load itself becomes the bottleneck), or does the developer want to
   commit to skipping O3 and building the full public-facing bot (O2) whenever this topic is next
   revisited, accepting the higher false-positive/reputational risk in exchange for actually
   reducing triage labor rather than just surfacing it faster?
2. **Confirm the qualitative trigger condition** (§3.2 — "promotions happening late" or "triage
   consuming noticeable time," developer-judged, no numeric threshold) as the right signal to
   revisit this topic, or does the developer want a concrete proxy metric named now even before
   any Discussion data exists (e.g. tied to a future coverage-analytics-style report once one
   exists for community activity)?
3. **If/when O2 is eventually built, confirm the propose-only mechanic** (bot comments proposing
   promotion, a human confirms/reacts before an issue is filed) as the required first version,
   never a silent auto-file straight to a filed issue — or does the developer consider silent
   auto-filing acceptable once the classification step has enough of a shadow-mode track record?
4. **Confirm the third-App identity recommendation (§2d)** — a distinctly-named, narrowly-scoped
   GitHub App (`Discussions: write` + `Issues: write` only) separate from both the D36 runner App
   and the D36-named future external-PR-skim App — or would the developer prefer this ride on the
   external-PR App instead, on the reasoning that both are "community-facing, not pipeline-facing"
   surfaces even though their concrete permissions don't overlap?
5. **If/when O3 (the digest) is built, where should it live** — a new subcommand on an existing
   CLI (D41's observability tool or D44's coverage tool), or a standalone small script, given it
   doesn't cleanly fit either existing tool's current scope (pipeline observability vs.
   coverage-gap analytics)?

## 5. New brainstorm topics surfaced

None. The trust-domain/App-scoping questions this topic raises (2d) are fully answered by
extending D36's existing pattern rather than opening new ground, and the false-positive/community-
trust concerns in §2 are specific to this one bot's design rather than a cross-cutting theme big
enough to warrant its own session.
