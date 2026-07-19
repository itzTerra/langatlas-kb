# 18 — Contribution Funnel & Ergonomics

> Backlog brainstorm for LangAtlas. Scope per the checklist: challenge issue templates, a
> "propose a fact" web form, GitHub Discussions mapping to entity pages, a coverage-matrix page
> as contributor recruitment, and giving the developer's "actively invite programmer
> collaboration" amendment (D2) concrete mechanics rather than leaving it as an aspiration.
> Binding context: `context/decisions.md` (esp. D1 no-PR-gate for agent facts, D2 "the project
> actively invites collaboration between programmers," D4/D24 verification gate, D9 challenge
> channel, D10 static zero-JS site, D12 absent-on-purpose no custom auth/forum, D14 DCO, D16
> ontology-MAJOR human gate as a governance precedent, D28 phased language onboarding, D29
> finding-aid-only corpus bootstrap); builds on brainstorms 05 (expert challenge — already
> settles the core "Challenge this fact" mechanics), 01, 07. Related backlog: topic 19 (website
> deep-dives — owns the feature-support-matrix *component UX*, not addressed here), topic 27
> (agent-runner commit protocol — a different trust domain: the project's own GitHub App, not
> external humans), topic 44 (coverage analytics — the data feed this brainstorm's recruitment
> surface would consume once it exists). All proposals here are *proposed* until the developer
> ratifies.

## 1. Problem framing

D9 already answered the narrowest version of "how does a human correct a wrong fact": a
prefilled GitHub issue on `langatlas-kb`. That answer is settled and this brainstorm does not
re-litigate it. What's still open is everything upstream and downstream of that one interaction:
how a stranger who has never heard of LangAtlas discovers there is something to do, what the
lowest-effort and highest-effort versions of "doing it" look like, and — the sharper question the
checklist's C12 reference is really asking — whether a programmer who wants to *add* something
(not just flag an error) has any channel to do that at all, given D1's design deliberately routes
fact-authorship through agents, not humans.

Three contributor personas make the funnel concrete:

1. **The drive-by expert** — lands on a feature or language page from search, notices one fact is
   wrong or stale, wants to say so in under a minute, then leaves. D9 serves this persona now.
2. **The invested outsider** — a programmer who cares enough to file more than one correction, or
   who notices a *pattern* of gaps (their favorite language is thin, a whole dimension is
   missing) and wants a lower-friction way to say "I'd help with this" than writing prose in an
   issue every time.
3. **The would-be co-author** — someone technically able to write a fact record correctly (they
   could read `09-fact-schema-and-ids.md`'s YAML shapes and produce a compliant file) and wants
   to actually *contribute content*, not just report on someone else's. D1 built the whole
   pipeline around agents committing directly with no human PR gate; it says nothing about
   whether an external human's PR is welcome, and if it is, whether it goes through the identical
   automated gate or some other path. D14 already assumes external PRs exist enough to need a
   DCO — but a DCO answers "how do we prove you can legally contribute," not "what happens to
   your PR once you open it." That gap is this brainstorm's least-settled question.

A structural tension runs under all three: D10's design ethos is explicitly "opposite of Amazon,"
typography-first, "no growth chrome" — but a *contribution funnel* is, by definition, a growth
mechanism. The honest brief here is to build genuine, low-friction on-ramps without the site
acquiring a leaderboard, a contributor-count badge, or a "join our community!" banner — the
invitation has to live in the *content* (visible gaps that are literally work items) rather than
in social/gamification chrome bolted onto the design.

## 2. Options with trade-offs

### 2.1 Challenge issue templates

D9 sketched one generic prefilled issue (fact ID, file path, current value, citations, page URL).
That covers persona 1's single use case (correct this fact) but nothing else reaching the tracker
needs a different shape: a coverage-gap report has no existing fact ID to embed; a "please
onboard language X" request has no fact or feature context at all; a schema/ontology suggestion
is a different kind of claim entirely (and per D16 routes to the RFC process, not this funnel).

**Option A — one generic template, freeform body.** What D9 already implies. Cheap, but every
intent gets crammed into the same shape, which means the D27 agent-runner (or the developer,
pre-27) has to parse free text to figure out what kind of action is being requested before a
session can act on it.

**Option B — a small set of typed GitHub Issue Forms** (`.github/ISSUE_TEMPLATE/*.yml`), each with
structured required/optional fields and an auto-applied label, matched to the personas above:
   - `challenge-fact.yml` — fact ID, file path, current value, proposed correction, citation(s)
     with locator (D9's existing shape, formalized as a YAML issue form instead of a URL-encoded
     freeform body).
   - `propose-coverage.yml` — feature id + language id (both pre-fillable via query params from a
     coverage-matrix cell, §2.4), optional "I have a source" field, optional "I'd like to help
     research this" checkbox.
   - `request-language.yml` — for a language not yet in the D28 roadmap at all: name, why it
     matters, license/spec availability if known (feeds a future D28 revision, not an immediate
     commitment).
   - `general-question.yml` — GitHub's issue-form syntax supports redirecting a template choice
     straight to Discussions instead of opening an issue at all (GitHub Docs, 2026), which is the
     natural home for anything that isn't yet a concrete, actionable claim.

Pros: issue forms render as a real structured form in GitHub's UI (dropdowns, required fields,
validation) — this *is* "propose a fact web form" without building anything, addressed further in
§2.2; auto-applied labels give the agent-runner (topic 27) and the developer a machine-sortable
queue for free; each site surface (fact popover, coverage-matrix cell, language-index page) can
deep-link to the specific template with the specific fields pre-filled, rather than one template
that has to explain itself in every context.

Cons: four templates to maintain instead of one; GitHub issue forms have some real limits (no
conditional field logic, a cap on total fields) that a custom form wouldn't have — acceptable
given the low field count each template actually needs.

**Recommendation: B.** Matches "boring, solo-maintainable technology" better than it sounds —
these are static YAML files in the repo, no runtime, no new service, and they compound with §2.2
and §2.4 rather than sitting alongside them as separate work.

### 2.2 "Propose a fact" web form

The checklist names this as if it were its own artifact, but D10 (static site, zero JS on KB
pages) and D12 (no custom auth, no custom forum — explicitly "absent on purpose") box the design
space in hard.

**Option A — no dedicated form; funnel everything through prefilled GitHub issues.** This is
what §2.1's Option B already delivers: GitHub's own issue-form rendering *is* the form. Zero
new infrastructure, zero new auth surface (GitHub account requirement already accepted for
challenges per D9), fully consistent with git-history-as-audit-trail.

**Option B — a client-side form on the static site that posts to a serverless relay** (Cloudflare
Worker / similar) which mints a GitHub issue or PR via the GitHub API on the visitor's behalf,
without requiring them to have or use a GitHub account. Pros: lowest possible friction for a
non-technical domain expert who doesn't want a GitHub account. Cons: this is a real backend with
a real trust boundary — an unauthenticated public endpoint that creates content in the repo needs
its own abuse handling (rate limiting, spam/bot filtering, likely a CAPTCHA), its own hosting and
monitoring, and it breaks the one property D9 and D1 both lean on: that every contribution is
already attributable to a GitHub identity before it lands. It also reopens the anonymous-intake
question D9 explicitly deferred ("revisit anonymous intake only if experts bounce off the GitHub
account requirement" — *[developer 2026-07-18: GitHub account requirement is acceptable]*) — i.e.
the developer already ruled on the underlying question this option exists to route around.

**Option C — a third-party form service** (Typeform/Google Forms/Formspree) feeding a spreadsheet
or inbox the developer triages by hand. Pros: near-zero build effort. Cons: creates a second,
parallel, non-git-native intake channel that duplicates the issue tracker's job without its audit
trail, its labels, or its `@`-mention resolution loop (D9) — pure operational overhead for a
solo maintainer with no corresponding benefit over Option A.

**Recommendation: A.** No dedicated form gets built; §2.1's typed issue-form set *is* the answer,
deep-linked from every relevant site surface with fields pre-populated by query string exactly as
D9 already does for fact challenges. This is a case where "propose a fact web form" turns out to
already be satisfied by tooling GitHub gives away for free — building a bespoke form would be
solving an already-solved problem at the cost of a new backend that conflicts with D10/D12's
absent-on-purpose list.

### 2.3 GitHub Discussions mapping to entity pages

D9 already named giscus-style embedded Discussions as a fast follow to the Issues-based challenge
channel, without designing the mapping. Two questions: which pages get a Discussion widget, and
how do Issues and Discussions divide labor so they don't become two competing inboxes for the
same content.

**Granularity options:**
- **Per-fact** (one Discussion thread per `data-fact-id`, mirroring the popover-level granularity
  D10 already uses for "Challenge this fact"). Rejected: thousands of near-permanently-empty
  threads; giscus (and GitHub Discussions generally) work best with a modest, browsable set of
  threads, not one per atomic claim.
- **Per-page, scoped to feature and language pages** (`/features/<x>/`, `/languages/<x>/`) —
  giscus's `pathname` mapping creates the backing Discussion lazily, on first comment, so
  most pages never mint an empty thread at all (giscus, 2026). *[proposed]* This is the natural
  grain: a feature or language page is a meaningful unit to have an opinion about ("does anyone
  disagree with how we've scoped Rust's trait system"), where an individual fact usually isn't.
- **Per-comparison-page** (`/features/<x>/<a>-vs-<b>/`) as a secondary mapping once those pages
  exist (D10 gates them on a data-richness threshold) — natural home for "which of these is
  actually more idiomatic" discussion.

**Category structure:** GitHub Discussions categories are repo-global, not per-entity, so the
mapping is: a small fixed category set (`Feature talk`, `Language talk`, `Q&A` for genuinely
open questions, one `Announcements`-style category the developer posts to, e.g. for phase
onboarding milestones) rather than one category per feature/language (which would need constant
manual category creation as the ontology grows — an operational cost with no real benefit over
letting the `pathname` mapping do the per-entity scoping).

**Issues-vs-Discussions division of labor** (the part D9 left implicit): an Issue is for a
concrete, resolvable claim that ends in a commit (D9's existing lifecycle: challenge → agent
session → correction → close); a Discussion is for anything that isn't yet at that stage —
open-ended debate, "I think this whole dimension is under-modeled," "does anyone know a good
source for X," general interest/enthusiasm. A Discussion that crystallizes into an actionable
claim gets manually promoted into an Issue (GitHub supports converting a Discussion to an Issue
natively) — no bot needed for v1; automating that promotion is listed as a possible future
topic (§5) if volume ever justifies it.

**Recommendation:** ship the giscus embed scoped to feature and language pages only, mapped by
`pathname`, with the small fixed category set above; state the Issues-vs-Discussions split
explicitly in `CONTRIBUTING.md` (see §2.5) so contributors self-route correctly from day one.

### 2.4 Coverage-matrix page as contributor recruitment

D28 phases 15 languages in over four stages, meaning for a long stretch of the project's life
most feature × language cells are genuinely empty — not because a fact was rejected, but because
nobody has looked yet. That's an unusually honest kind of "help wanted" list: every empty cell
*is* a real, well-scoped, source-backed-when-you're-done unit of work, which is close to the
open-source "good first issue" convention (GitHub's own docs recommend curated, well-scoped
entry points to lower the notoriously high barrier newcomers face orienting themselves in an
unfamiliar codebase — Steinmacher et al., 2015, catalog exactly this "narrow entry socialization"
barrier as one of the most common reasons newcomer contributions stall before a first success).

**Design questions to settle, not deferred to topic 19 (which owns matrix *component* UX):**

1. **Does an empty cell mean "not yet covered" or "not yet onboarded at all"?** Per D28, a
   language not yet in its onboarding phase has no page, no instances, nothing — so the matrix
   must visually distinguish *"onboarded language, feature not yet swept"* from *"language not
   yet onboarded in any phase"* from *"deferred/out of scope"* (SQL per D28/D14 rule 7). Three
   distinct empty states, not one blank cell.
2. **What does clicking an empty cell do?** Recommendation: it deep-links to the
   `propose-coverage.yml` issue form (§2.1) with `feature_id` and `language_id` pre-filled from
   the cell's coordinates — the single mechanism that turns "I noticed a gap" into "I filed
   something actionable" without the visitor typing either ID by hand.
3. **Where does this page live in the site IA?** D10's IA has `/languages/` and `/features/`
   index pages already; a dedicated `/coverage/` page (or a coverage *view* folded into
   `/languages/`) is new territory this brainstorm proposes adding to that IA, not a topic-19
   concern (19 owns how the matrix *component* renders/sorts once it exists as a page).
4. **Static-site constraint:** a large sortable/filterable matrix is exactly the kind of surface
   that tempts a zero-JS site into needing client-side interactivity. Recommendation: ship a
   handful of pre-baked static views at build time (by language, by dimension, "biggest gaps"
   sorted server-side into the page itself) rather than a live interactive table — matches D10's
   zero-JS-on-KB-pages posture, and the actual interactive-sort UX question is explicitly topic
   19's to design in depth.

**Recommendation:** add `/coverage/` to the site IA now (a build-time-generated page, several
pre-sorted static views, three-state empty cells, each empty cell linking to a pre-filled
`propose-coverage` issue) as this brainstorm's concrete answer to "coverage-matrix page as
contributor recruitment"; leave the matrix's detailed interaction design (sorting, filtering
UX, whether it becomds an island) to topic 19.

### 2.5 The would-be co-author: does a human PR pathway exist at all?

This is the sharpest open question and the one the checklist's C12 reference is really pointing
at. D1 built the write path around agents committing directly, gated by automated verification,
with **no PR gate** — but that decision was scoped to *the project's own agent fleet*, running
under a GitHub App identity (D13, D27). It says nothing about what happens when an external
human, who has no such identity and no track record, opens a PR against `langatlas-kb` adding a
hand-written (or locally-sweep-tool-generated) fact record. D14 already assumes this happens often
enough to need a DCO. Three postures:

**Option A — no human authorship pathway; contribution stays report-only.** Programmers can
challenge (D9), discuss (§2.3), and flag gaps (§2.4), but cannot themselves author a fact record
that gets merged — all content authorship stays inside the agent pipeline. Pros: zero new trust
boundary; the verification gate never has to be adversarially hardened against a human trying to
game it, only against honest LLM mistakes (K1's original framing). Cons: rings hollow against
D2's explicit "the project actively invites collaboration between programmers" — a technically
able contributor who wants to add their own knowledge has nothing more to do here than a
non-technical reader does.

**Option B — full fact-authoring PRs, gated identically to agents, auto-merged on green CI.**
A contributor forks the repo, writes (or generates via the sweep tooling run locally) a
compliant fact/instance file citing sources, signs off via DCO, opens a PR; CI runs the exact
same D4/D24 verification gate the agent runner uses, and a merge bot merges on green — literally
the same treatment D1 already gives agent commits, just from a different committer. Pros: the
most literal possible answer to "invite collaboration" — a stranger's well-sourced contribution
lands as fast as an agent's; philosophically consistent with D1's own justification ("admissible
because backed by a verified source, not because a human reviewed it") applying without
exception. Cons: this exports the no-human-review trust model, designed and calibrated for the
project's own controlled agent fleet, to the open internet. An adversarial human (unlike an
honestly-mistaken LLM) can *deliberately* probe the verifier for its weak spots — a new,
harder-to-detect instance of K1 (citation laundering), now backed by intent rather than error,
and needing no compromise of any system, just a GitHub account and patience. It also gives no
protection against low-content-quality but gate-passing spam (a technically true, correctly
cited, but trivial or off-topic fact) — the D24 gate checks entailment, not editorial judgment.

**Option C — a narrower human PR pathway scoped to *sources* and *coverage proposals*, not full
claims.** A contributor can add a new `Source` YAML record (bibliographic data for a book/spec
they vouch for) or a `candidate-feature`/`candidate-language` proposal file — both low-stakes,
mechanically checkable contributions (a Source record is either bibliographically correct or
it isn't; no entailment judgment involved) — while full fact/claim authorship stays pipeline-only
for now. Pros: gives the invested-outsider and would-be-co-author personas something concrete and
genuinely useful to do, at a risk level barely above D9's existing challenge channel; sidesteps
the adversarial-verifier-probing risk entirely because sources/proposals aren't claims the site
displays as sourced fact. Cons: a real Rust expert who wants to contribute a Rust *fact* directly
still can't — the invitation is narrower than Option B's, and narrower than "actively invite
programmer collaboration" arguably calls for.

**Recommendation: graduated posture, C now → B with a developer skim as the near-term
escalation → full auto-merge (unqualified B) reserved for much later, if ever.** This mirrors a
pattern the project already uses elsewhere: D16 keeps ontology MAJORs as "the one human-gated
exception" to an otherwise fully automatic pipeline, and D30 explicitly defers a heavier
instrumentation option until real volume exists to justify it rather than deciding in the
abstract. The same shape applies here: an external, no-track-record submitter is a different
trust domain than the project's own GitHub App, in the same way an ontology MAJOR is a different
blast radius than a MINOR — worth one narrow, cheap human checkpoint (not full content review,
just "does this PR look like a legitimate, single-topic, non-abusive contribution" — a provenance/
scope skim, not a fact-accuracy judgment D1 already delegated to the verifier) until the channel
has a track record. Ship Option C immediately (cheapest, safest, still a real invitation); revisit
full fact-PRs once source/proposal-PR volume shows the channel attracts genuine contributors
rather than spam, at which point the *level* of human involvement (developer-skimmed vs.
auto-merge-on-green) is itself the next decision, not something to pre-commit to now.

### 2.6 Avoiding growth chrome while still recruiting

Named in §1 as a tension: D10 explicitly wants "no growth chrome," but a coverage-matrix
recruitment page and a "help wanted" framing are, functionally, growth mechanics. The dividing
line this brainstorm proposes: invitation lives in **content that is also genuinely useful
knowledge-base furniture** (a coverage matrix is a legitimate reference page even to a reader who
never contributes anything — it answers "does language X support feature Y" as directly as any
other page) rather than in **social signaling chrome** (contributor leaderboards, badges, "N
people helped this week" counters, a wall of avatars). Concretely: no contributors page, no
GitHub-star counter embedded in the site, no per-contributor attribution beyond what git history
and GitHub already show natively. The invitation is: "here is a real, well-scoped gap, here is
exactly how to fill it" — not "join our community."

## 3. Recommendation (*proposed*)

1. **§2.1 — typed issue-form set**: replace D9's single generic template with `challenge-fact.yml`,
   `propose-coverage.yml`, `request-language.yml`, plus a `general-question.yml` that redirects to
   Discussions. All in `.github/ISSUE_TEMPLATE/` on `langatlas-kb`, auto-labeled per type.
2. **§2.2 — no dedicated web form**: GitHub's native issue-form rendering, deep-linked with
   pre-filled query params from every relevant site surface, *is* the "propose a fact" form.
   Explicitly reject a serverless-relay backend or a third-party form service — both conflict
   with D10 (static site) / D12 (no custom auth) and add operational surface with no benefit over
   an already-accepted GitHub-account requirement (D9).
3. **§2.3 — giscus Discussions scoped to feature and language pages** (`pathname` mapping, lazy
   thread creation), a small fixed category set, with an explicit Issues-vs-Discussions division
   of labor stated in `CONTRIBUTING.md`: Issues resolve into commits, Discussions are for
   open-ended debate that may later be promoted into an Issue.
4. **§2.4 — add `/coverage/` to the site IA**: a build-time-generated feature × language matrix
   with three distinct empty-cell states (not-yet-swept / not-yet-onboarded / deferred), each
   empty cell deep-linking to a pre-filled `propose-coverage` issue. Several pre-baked static
   views (by language, by dimension, "biggest gaps") satisfy D10's zero-JS posture for v1; the
   matrix's interactive UX is topic 19's to design.
5. **§2.5 — graduated human-authorship posture**: start with source/candidate-proposal PRs only
   (Option C), gated by mechanical checks, no fact-authoring PRs yet; escalate to full fact-PRs
   with a developer skim once the channel has a track record; defer auto-merge-on-green for
   external PRs indefinitely, revisited only with real volume evidence, mirroring how D16 and D30
   already handle comparable trust-boundary questions elsewhere in the project.
6. **§2.6 — no growth chrome**: no contributors page, no counters, no badges; the invitation is
   the coverage matrix's honest gaps plus a `CONTRIBUTING.md` that states the three lanes
   (challenge / discuss / propose-coverage-or-source) plainly.

## 4. Open questions for the developer

1. **Ratify the graduated external-PR posture (§2.5)**: source/proposal PRs now, developer-skimmed
   full fact-PRs as the next step, auto-merge reserved for much later? Or does the developer want
   to commit further now — e.g. straight to developer-skimmed full fact-PRs, given D14 already
   assumes a DCO-signing external-contributor population exists?
2. **Confirm the giscus scope (§2.3)**: feature + language pages only, or should comparison pages
   (`/features/<x>/<a>-vs-<b>/`) get discussions from day one rather than once they exist per
   D10's data-richness threshold?
3. **Confirm the typed issue-form set (§2.1)** — four templates as proposed, or does the developer
   want fewer/more (e.g. folding `request-language` into `propose-coverage` with a language-only
   variant)?
4. **`/coverage/` page placement in the IA (§2.4)** — a standalone top-level page, or nested under
   `/languages/`? Does its existence conflict with anything topic 19 is already assuming about
   where matrix UX lives?
5. **Do not-yet-onboarded (D28 later-phase) languages get any page at all pre-sweep** (a stub
   page purely so a recruitment link has somewhere to land, stating "phase 3, not yet started"),
   or does all recruitment for those live only on `/coverage/` with no per-language stub?
6. **"Good first gap" curation (§2.4)** — should the developer hand-pick a small initial "help
   wanted" list to seed the coverage page before topic 44's coverage analytics exists, or wait
   for that data and never hand-curate?

## 5. New brainstorm topics surfaced

- **External-PR abuse handling** — rate limiting/first-time-contributor friction, CI cost of
  spam PRs, what a "provenance/scope skim" concretely checks for in §2.5's Option-C-then-B
  escalation; could fold into topic 27 (agent-runner protocol) since both touch the repo's commit
  hygiene, or stand alone if it grows.
- **Discussion→Issue promotion tooling** — whether the manual conversion in §2.3 ever needs
  automating (a bot that proposes promotion when a Discussion accumulates enough concrete detail)
  once volume justifies it.
- **`CONTRIBUTING.md` content design** — the actual document stating the three contribution lanes
  or channel choices (challenge / discuss / propose) referenced throughout this brainstorm; likely
  just a doc-writing task rather than a full brainstorm, flagged here so it isn't lost.

## Sources

- GitHub Docs (2026). *Syntax for GitHub's form schema* (issue forms: required fields, dropdowns,
  auto-labeling, redirect-to-Discussions support).
  https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-githubs-form-schema
- giscus (2026). *giscus — a comments system powered by GitHub Discussions* (pathname mapping,
  lazy discussion creation, category configuration). https://giscus.app/
- Steinmacher, I., Silva, M. A. G., Gerosa, M. A., & Redmiles, D. F. (2015). A systematic
  literature review on the barriers faced by newcomers to open source software projects.
  *Information and Software Technology*, 59, 67–85.
  https://doi.org/10.1016/j.infsof.2014.11.001
- Dabbish, L., Stuart, C., Tsay, J., & Herbsleb, J. (2012). Social coding in GitHub: transparency
  and collaboration in an open software repository. *Proceedings of CSCW 2012*, 1277–1286.
  https://doi.org/10.1145/2145204.2145396
