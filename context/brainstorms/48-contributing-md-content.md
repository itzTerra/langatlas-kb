# 48 — CONTRIBUTING.md Content

> Backlog brainstorm for LangAtlas, item 48 (checklist: "the actual document stating the three
> contribution lanes (challenge / discuss / propose-coverage-or-source) referenced throughout
> topic 18; likely a doc-writing task rather than a full brainstorm, kept here so it isn't lost —
> from 18"). This is explicitly the lighter-weight kind of checklist item: the substance was
> already settled in **D32** (Contribution funnel & ergonomics — the four typed GitHub Issue Forms,
> the giscus Discussions scope, the graduated external-authorship posture, "no growth chrome"), so
> this session does not re-open any of that. Binding context: **D1** (agents commit directly, no
> PR gate — the reason a human PR is a *different* trust domain, per D32 §2.5); **D9** (the
> original "Challenge this fact" channel, formalized by D32 into `challenge-fact.yml`); **D32**
> itself (all four lane/channel decisions, ratified in full — see `context/decisions.md`); **D42**
> (licensing follow-ups: CC BY-SA 4.0 corpus / MIT code, attribution name "LangAtlas contributors,"
> the published takedown email + `legal-complaint.yml`); **D36** (agent-runner commit protocol —
> specifically its DCO carve-out: the GitHub App installation is the pipeline's one-time sign-off,
> while `Signed-off-by:` trailers are reserved for human-submitted PRs, which is exactly the
> distinction a human-facing CONTRIBUTING.md needs to state correctly). Also skimmed: brainstorm 47
> (Discussion→Issue promotion tooling), which stays fully manual (O1) for now per its own
> recommendation and so introduces nothing this document needs to describe — no bot posts into
> Discussions yet, no promotion mechanic to explain to a human reader. The deliverable is the
> drafted `CONTRIBUTING.md` **content**, embedded below; per the task instructions no file is
> created at the repo root — the repo isn't public yet, and landing it is the developer's call.

## 1. Problem framing

There isn't much left to *decide* here. D32 already fixed every substantive question a
CONTRIBUTING.md would normally have to answer on its own: which channels exist (four typed Issue
Forms + giscus Discussions), how they divide labor (Issues resolve into commits, Discussions are
open-ended and get manually promoted), what a human PR can and can't do right now (source/
candidate-proposal PRs welcome, full fact-authoring PRs not yet, auto-merge not yet), and how DCO
applies (D36's carve-out: bot commits are covered by the App installation itself, human PRs need
per-commit `Signed-off-by:`). D42 fixed the licensing facts that need to appear (CC BY-SA 4.0
corpus, MIT code, "LangAtlas contributors" as the attribution name, the takedown channel). Nothing
here needs weighing against alternatives the way a normal brainstorm's §2 would.

What's actually left is copywriting: how to sequence and word a single onboarding document so a
stranger who has never seen this project can self-route into the right lane in under a minute,
without contradicting the density and precision the rest of this project's `.md` files use. Three
narrow structural choices are worth naming explicitly (kept proportionate, per the task
instructions) before the draft itself, since they're genuine (if small) judgment calls rather than
things D32 already answered:

1. **Lead with the three lanes, or lead with project context first?** A stranger arriving from a
   GitHub search or a "help wanted" link off `/coverage/` (D32 §2.4) needs the fastest possible
   answer to "what do I click." The draft below leads with a two-sentence project one-liner (so the
   reader isn't asked to act before they know what LangAtlas is) and then the three lanes
   immediately after, before any of the deeper mechanics (DCO, licensing, PR posture) — those are
   real but secondary to a first-time reader's actual question.
2. **How much of D32's internal reasoning to surface vs. just state the resulting rule?** A
   CONTRIBUTING.md is not a brainstorm file — it should state outcomes, not rehearse trade-offs.
   The draft states each rule plainly (e.g. "we don't yet accept full fact-authoring PRs") with at
   most one clause of *why*, never the full D32 §2.5 analysis. Readers who want the reasoning have
   `context/decisions.md` linked at the bottom.
3. **Tone**: match this project's own established voice — plain, declarative, no marketing register
   ("join our community!" is explicitly the thing D32 §2.6 rejects). The draft avoids exclamation
   points, avoids "we'd love your help," and states the coverage-gap framing as fact ("every empty
   cell is real, unclaimed work") rather than as an appeal.

No options table follows this section — there is nothing here proportionate to weigh beyond the
three points above, which are folded directly into the draft's construction rather than argued as
separate alternatives.

## 2. Recommendation (*proposed*) — drafted CONTRIBUTING.md content

The following is the full proposed content for a root-level `CONTRIBUTING.md` on `langatlas-kb`.
It is **not** written to the repo root per the task scope — the developer lands it when the repo
goes public. Placeholder links (issue form URLs, license page, contact email) use the project's
already-decided repo/domain names (D17 `langatlas-kb`, `langatlas.dev`) in the obvious shape;
the developer should swap in the real URLs once the GitHub org (D17's one still-open action) and
the `legal-complaint.yml`/`propose-coverage.yml` etc. files actually exist.

```markdown
# Contributing to LangAtlas

LangAtlas is a sourced knowledge base mapping programming languages onto a structured model of
programming-language concepts. Every fact on the site is tied to a citation; most of the corpus is
written by AI agents and checked by an automated verification gate, not by a human editor — which
is exactly why human expertise matters here. If something is wrong, thin, or missing, this page is
how you tell us, discuss it, or (in a few specific cases) fix it yourself.

There are three ways to contribute. You don't need write access to the repo for any of them.

## 1. Challenge a fact

Every fact on the site has a "Challenge this fact" link in its citation popover. It opens a
prefilled GitHub Issue ([`challenge-fact.yml`][challenge-fact]) with the fact's ID, its current
value, and its existing citation already filled in — you only need to describe what's wrong and,
ideally, point to a better source. You can also open this form directly from the
[issue tracker][new-issue] if you know the fact ID or file path.

What happens next: the issue is picked up in a future agent session, which re-argues the fact
against the evidence, and — if the challenge holds — commits the correction. You'll be
`@`-mentioned when it's resolved. Nothing about this requires you to write YAML or understand the
schema; describing the problem in plain language is enough.

## 2. Start or join a discussion

Use [Discussions][discussions] for anything that isn't yet a concrete, resolvable claim: "I think
this whole area is under-modeled," "does anyone know a good source for X," open debate about how a
feature is scoped, or general questions. Discussions live on feature and language pages (the
comment box at the bottom of each) and in the repo's Discussions tab.

The distinction that matters: an **Issue** is for something specific enough to end in a commit; a
**Discussion** is for everything before that point. If a discussion thread turns into a concrete,
sourceable claim, anyone with write access can convert it into an Issue — feel free to ask for that
if a thread has crystallized and nobody's moved it yet.

## 3. Propose new coverage or a new source

If you've noticed a gap — a feature that isn't documented for a language you know, or a language
that isn't in LangAtlas at all yet — there are two ways to flag it:

- **[Propose coverage][propose-coverage]** — for a specific feature × language cell. The
  [`/coverage/`][coverage-page] page lists every gap as a clickable cell; clicking one opens this
  form with the feature and language already filled in. You can optionally note a source you
  already know about, or flag that you'd like to help research it yourself.
- **[Request a language][request-language]** — for a language that isn't on the roadmap at all.
  Tell us why it matters and, if you know it, whether it has a usable spec or reference docs and
  what license they're under.

**If you can write a compliant record yourself**, two categories of pull request are open to
external contributors right now:

- A new **source record** (bibliographic data for a book, spec, or reference document) — this is
  mechanically checkable (it's either bibliographically correct or it isn't) and doesn't require
  any editorial judgment on our part.
- A **coverage or language proposal file** — the same structured content the issue forms above
  collect, just submitted as a PR instead of an issue, if you'd rather work in your editor.

We don't yet accept full fact-authoring PRs (a PR that adds or edits an actual sourced claim about
a language feature) — that content currently comes only from the agent pipeline, which runs the
same claims through an automated source-verification gate before anything is committed. This is a
near-term limit on the *channel*, not a judgment about contributor expertise: as the source/
proposal channel builds a track record, we expect to open a reviewed path for full fact PRs too.
There's no fixed date for that; watch this file, it'll be updated when it changes.

All pull requests require a **Developer Certificate of Origin** sign-off
(`git commit -s`) — see [DCO below](#developer-certificate-of-origin).

## What LangAtlas doesn't have (on purpose)

No forum, no contributor leaderboard, no badges, no "N people helped this week" counter. If you're
looking for an entry point, the most honest one we can offer is the [`/coverage/`][coverage-page]
page: every empty cell there is real, unclaimed work, not a marketing device.

## Developer Certificate of Origin

Every pull request must be signed off under the [DCO][dco] (`git commit -s`), certifying that you
wrote the contribution or otherwise have the right to submit it under the project's license. This
applies to human-submitted PRs only — commits made by the project's own automated pipeline are
covered by that pipeline's own one-time authorization and don't carry per-commit sign-offs.

## Licensing

- Code (pipeline, tooling, site) is **MIT**-licensed.
- The knowledge-base corpus (facts, features, instances, edges, sources) is **CC BY-SA
  4.0**, attributed as **"LangAtlas contributors."** If you reuse data from this project, you need
  to attribute it and share derivative datasets under the same license — see the
  [license page][license-page] for the full explanation.
- If you believe something in this repository infringes your rights, see the
  [licensing/takedown contact][license-page] for how to reach us; we also accept a
  [`legal-complaint.yml`][legal-complaint] issue form as an alternative to email.

## Questions

If none of the above fits — you're not sure which lane applies, or you just want to ask something
— open a [general question][general-question], which points you to the right place instead of
asking you to guess.

[challenge-fact]: https://github.com/langatlas/langatlas-kb/issues/new?template=challenge-fact.yml
[propose-coverage]: https://github.com/langatlas/langatlas-kb/issues/new?template=propose-coverage.yml
[request-language]: https://github.com/langatlas/langatlas-kb/issues/new?template=request-language.yml
[general-question]: https://github.com/langatlas/langatlas-kb/issues/new?template=general-question.yml
[legal-complaint]: https://github.com/langatlas/langatlas-kb/issues/new?template=legal-complaint.yml
[new-issue]: https://github.com/langatlas/langatlas-kb/issues/new/choose
[discussions]: https://github.com/langatlas/langatlas-kb/discussions
[coverage-page]: https://langatlas.dev/coverage/
[license-page]: https://langatlas.dev/license/
[dco]: https://developercertificate.org/
```

### Notes on choices embedded in the draft (not separate open questions — implementation detail)

- The **"What happens next" paragraph under lane 1** exists because D9's resolution loop
  (challenge → agent re-argues → commit → `@`-mention → CI rebuild) is exactly the kind of thing a
  first-time visitor benefits from knowing *before* filing, not after — it sets expectations that
  no human will manually triage their issue, which is a feature of this project's design, not an
  apology for it.
- The **licensing section deliberately keeps to three bullets**, deferring detail to the D42
  `/license/` page rather than re-explaining CC BY-SA/§ 31/DCO mechanics inline — CONTRIBUTING.md's
  job is to state the obligation exists and point onward, not to be the licensing doc itself.
- The **DCO section's wording ("covered by that pipeline's own one-time authorization")**
  intentionally does not explain the GitHub-App-installation mechanism (D36) in any depth — that
  detail belongs to the pipeline's own internal docs, not a contributor-facing page; a human reader
  only needs to know "you have to sign off, the bot doesn't have to per-commit" to avoid confusion
  when they notice bot commits lack `Signed-off-by:` trailers.
- The **`legal-complaint.yml` link is included** even though it's a fifth issue form outside D32's
  four-template set — D42 explicitly ratified it as an addition "alongside D32's four," so it
  belongs here even though this document is nominally about D32's three lanes; it doesn't get its
  own numbered lane because it's a narrow, rarely-used escalation path, not a contribution channel.
- **No mention of `/changelog/ontology/` or ontology-MAJOR RFCs** (D16) — that governance channel
  is a different audience (someone proposing a taxonomy change, not a typical fact/coverage
  contributor) and wasn't in this checklist item's scope; if the developer wants ontology RFC
  process linked from here too, that's a one-line addition, flagged as an open question below
  rather than added speculatively.

## 3. Open questions for the developer

1. **Land it now or hold?** The task scope explicitly says not to create the file yet since the
   repo isn't public. Confirm: does the developer want this content landed as the actual
   `CONTRIBUTING.md` now (private-repo contributing docs are harmless even pre-launch), or held
   until the public launch checklist (tied to brainstorm 31's positioning work)?
2. **Real URLs**: the draft's link block uses placeholder GitHub org/path (`langatlas/langatlas-kb`)
   and domain (`langatlas.dev`) matching D17's naming decision. D17 flags the GitHub org name as
   still not confirmed — should this document wait on that confirmation, or land with placeholders
   flagged inline (e.g. an HTML comment marking them TODO) so the doc can be drafted and reviewed
   before the org name is locked?
3. **Ontology-RFC mention (§2 notes, last bullet)**: should a one-line pointer to the D16
   ontology-MAJOR RFC process be added to this document (for the rare visitor proposing a taxonomy
   change rather than a fact/coverage item), or is that intentionally out of scope for a
   contributor-facing doc and better left to a `docs/ontology-governance.md` the developer hasn't
   asked for yet?
4. **Tone check**: does the drafted voice (plain, declarative, "here is unclaimed work" rather than
   "join our community") land the way D32 §2.6's "no growth chrome" principle intends, or does the
   developer want it warmer/more inviting in specific spots (e.g. the opening paragraph)?

## 4. New brainstorm topics surfaced

None. This was a doc-writing task as the checklist item itself predicted; nothing here surfaced a
question big enough to need its own brainstorm session.
