# 33 — Licensing Follow-ups

> Backlog brainstorm for LangAtlas. Scope per the checklist: attribution rendering spec (BY-SA
> format on pages + MCP responses), takedown/complaint runbook, machine-readable dataset export
> with embedded attribution, transcript-corpus dataset licensing. Follows up on brainstorm 15
> (legal & licensing statement, D14) and brainstorm 24 (chat logging & publishing, D18), neither
> of which is re-litigated here — D14's core legal analysis (facts vs. expression, § 31
> quotation, TDM exception, CC BY-SA 4.0 final) stands; this topic is the operational plumbing
> D14 explicitly deferred. Binding context: D3/D10 (citation popover, JSON-LD), D9 (challenge
> channel), D14 (license package, lawyer-trigger list), D18 (chat capture/publishing,
> `REDACTIONS.md` precedent), D24/D25 (fact status axes shown publicly), D32 (four typed issue
> forms), D35 (dataset bundle manifest, MCP caution contract), D40 (brand/positioning).

## 1. Problem framing

D14 shipped the legal *analysis* (LangAtlas is structurally safe; corpus CC BY-SA 4.0; code MIT;
DCO; quote caps) but left four concrete operational artifacts as its own named follow-up
brainstorm ("New brainstorm topics surfaced," 15 §New topics). None of them are legal questions
anymore — they are rendering, ops-runbook, and file-format questions that happen to sit
downstream of a legal decision already made:

1. **Attribution rendering** — CC BY-SA 4.0 §3(a)(1) requires attribution "in any reasonable
   manner based on the medium" (author/title/source/license) whenever the *licensed material*
   (the corpus) is shared or adapted. This has two distinct audiences that are easy to conflate:
   readers of the LangAtlas site itself, who need to see *LangAtlas's own* BY-SA notice (this is
   about LangAtlas attributing itself as licensor, not about citing Van Roy & Haridi — that's
   D3's separate § 31 quotation-attribution machinery, already solved), and downstream
   *consumers* of LangAtlas content (a re-publishing site, a training-set builder, an MCP-calling
   agent that repeats a fact elsewhere) who need machine- or human-readable attribution data to
   satisfy their own BY-SA obligation when they reuse LangAtlas.
2. **Takedown/complaint runbook** — D14's lawyer-trigger list names "a rightsholder complaint" as
   one of four events that graduate from self-service policy to needing real legal advice. That
   list tells the developer *when* to call a lawyer; it says nothing about what to do in the
   hours/days before that call, which is exactly when a solo maintainer with no legal team is
   most likely to freeze or overreact. D1's public-git-from-day-one architecture also makes
   "taking something down" structurally different from a normal CMS: nothing is silently
   deletable, so the runbook has to say what "taking down" concretely *means* here.
3. **Dataset export attribution** — D35 already designed the machine-readable bundle (zstd SQLite
   + JSON manifest) as two GitHub Release assets. It carries rich provenance per-fact
   (`sources_json`, `provenance_json`, D25's status axes) but nothing yet says *"this whole bundle
   is CC BY-SA 4.0, here is how to attribute it"* at the document level — a different, coarser
   obligation than per-fact source citation.
4. **Transcript-corpus licensing** — D18 built the `langatlas-transcripts` repo and its capture/
   redaction/publishing mechanics in full, but the brainstorm never assigned it a license,
   because at the time the corpus-license brainstorm (15) was still in flight. Raw LLM output has
   genuinely unsettled copyright status (US Copyright Office guidance holds that content without
   human authorship isn't protectable at all), which makes "just inherit CC BY-SA 4.0 like
   everything else" a real choice rather than an obvious default.

None of these four reopen whether CC BY-SA 4.0 is the right corpus license, whether DCO beats a
CLA, or whether quoting Van Roy & Haridi is safe — all settled. They are about making the
already-ratified policy legible and enforceable in concrete files and workflows.

## 2. Options with trade-offs

### 2.1 Attribution rendering spec

**On-page (site, D10 static/zero-JS):** the missing piece is a site-wide, corpus-level notice —
distinct from D10's existing per-fact numeric citation popovers, which handle § 31
quotation-attribution for *sources cited inside* LangAtlas, not attribution *of* LangAtlas as a
BY-SA work.

- **Option A — footer-only static notice.** A one-line, every-page footer: "Content licensed
  under CC BY-SA 4.0 · LangAtlas contributors · [full license text]" plus a link to a `/license/`
  page with the three-layer plain-English note D14 §R5 already asked for (facts vs. expression vs.
  database right). Cheapest, matches Wikipedia's own footer convention (a de facto BY-SA norm
  reusers already recognize), zero build complexity, satisfies "reasonable manner based on the
  medium" for a text-heavy static site.
- **Option B — JSON-LD `license` field on every page's structured data**, in addition to A. D10
  already emits JSON-LD (TechArticle/ComputerLanguage nodes); adding a `license:
  "https://creativecommons.org/licenses/by-sa/4.0/"` property is a one-field addition to an
  existing build step, costs nothing new, and gives search engines/scrapers a machine-readable
  attribution signal independent of whether they render the footer.
- **Option C — per-fact attribution string**, e.g. embedding "LangAtlas contributors, CC BY-SA
  4.0" inside every fact card's DOM. Rejected: BY-SA's attribution unit is the *work* (here: the
  corpus/page), not a re-attribution requirement on every atomic sentence — this would visually
  clutter every fact card for an obligation the footer + JSON-LD already discharge once per page.

**Recommendation: A + B.** A static footer notice (linking to a `/license/` explainer page) plus a
`license` JSON-LD property on every page — no new component, no runtime cost, matches D10's
existing patterns exactly.

**MCP responses (D8, D35):** the sharper question, because an MCP-calling agent that repeats
LangAtlas content elsewhere is exactly the kind of BY-SA-triggering reuse the corpus license is
meant to reach, and MCP responses are consumed by agents, not humans reading a footer.

- **Option A — say it once in the tool description.** MCP tool descriptions already load into a
  consuming agent's context once per session (this is precisely the pattern D35 already
  establishes for the `caution` block's non-suppression policy). Add one sentence to every
  read-tool's description: "Content returned by this server is licensed CC BY-SA 4.0
  (https://creativecommons.org/licenses/by-sa/4.0/); if you reuse or republish it, attribute
  LangAtlas and license your derivative work under the same terms." Zero per-response payload
  cost.
- **Option B — a per-response `attribution` field**, sitting alongside D35's mandatory `caution`
  block on every fact object: `{license: "CC-BY-SA-4.0", license_url, attribution_text:
  "LangAtlas contributors <https://langatlas.dev>", page_url}`. Slightly heavier (every response
  object grows one more field) but means an agent that only inspects the returned data — never
  reads the tool description text, which is plausible for a naive integration — still has the
  attribution machine-readable and attachable if it repeats the fact downstream.
- **Option C — both.** Tool-description sentence for cheap one-time context-loading (matches the
  established D35 pattern) + the `attribution` field for agents that programmatically re-emit
  facts without threading tool-description text through. Marginal cost over B alone is one static
  string in a config file.

**Recommendation: C**, reusing D35's own justification for its `caution` block verbatim (say it
once at the session level *and* carry it structurally on every object, because you cannot assume
which layer a downstream agent actually reads) — this is the same shape as an already-ratified
decision, not a new pattern.

### 2.2 Takedown/complaint runbook

**Intake channel.** D32 already ships four typed GitHub Issue Forms, none scoped to legal
complaints — `challenge-fact.yml` assumes a good-faith accuracy correction with a fact ID in hand,
which is the wrong shape for "you quoted three paragraphs of my book" or "take down this page
about my product."

- **Option A — fold into the existing `challenge-fact.yml` template.** Rejected: conflates two
  different intents (accuracy correction vs. legal notice) under one label, and a rightsholder
  filing a real complaint is unlikely to want to create a GitHub account and navigate an
  issue-form UI as their first move — many expect email.
- **Option B — a dedicated `legal-complaint.yml` GitHub Issue Form**, mirroring D32's pattern
  (structured fields: contested URL, work claimed, nature of claim, contact info) but requires the
  same GitHub-account friction D9 already accepted for challenges is now imposed on a population
  (rightsholders, their lawyers) least likely to tolerate it.
- **Option C — a published email address** (e.g. a project alias, not necessarily the developer's
  personal inbox, in `LICENSE`, `CONTRIBUTING.md`, and the site footer's `/license/` page) as the
  *primary* channel, with the GitHub issue form as an equally valid secondary option for
  complainants who prefer it. Matches how essentially every open-source project and every
  DMCA-style process the developer will have seen actually works — email is the load-bearing
  channel, issues/forums are the courtesy alternative.

**Recommendation: C.** One published email address as the front door (works for non-technical or
legally-represented complainants with zero friction), `legal-complaint.yml` issue form available
for anyone who'd rather use GitHub — both funnel into the same private triage, described next.

**Triage & resolution steps** (mirrors the shape of D9's existing challenge-resolution loop, but
for a different trust/urgency profile):

1. **Acknowledge fast, resolve at best-effort pace** — matches the posture D9 already set for
   ordinary fact challenges ("resolution best-effort," per `open-questions.md`'s existing note).
   Propose: acknowledge within 5 business days (a number, not a legal deadline — there is no
   statutory clock here since this isn't a DMCA safe-harbor notice-and-takedown regime; LangAtlas
   publishes its own generated content, it doesn't host third-party user uploads, so the usual
   DMCA machinery doesn't strictly apply — but responding promptly is good practice regardless).
2. **Triage into one of two buckets, immediately, before anything else:**
   - **Bucket 1 — a plausible copyright/legal issue** (quote genuinely too long, a snapshot leaked
     into a public repo, a claim of database-right infringement, defamation-adjacent language
     complaint). Default safe action *while triaging*: unpublish the contested quote/snapshot/page
     element — not the underlying fact, since facts are never anyone's property (this restates
     D14/15 §R8's existing guidance: "facts can stay; they were never theirs" — this runbook does
     not change that call, it operationalizes it).
   - **Bucket 2 — not actually a legal issue** (someone disputing a correctly-cited, correctly
     quoted fact because they dislike it; a request to remove an accurate but unflattering
     characteristic). Redirect to the ordinary `challenge-fact.yml` channel (D9) — no special
     runbook needed, it's just a contested fact.
3. **Who decides:** the developer, solo, on process criteria (is this plausibly a real
   claim, does the safe default of unpublishing the contested excerpt resolve it) — not on
   content authority or legal expertise, matching the same posture D16 already established for
   ontology-MAJOR gating ("developer merging on *process* criteria, not content authority").
4. **What "taking down" means, concretely, given D1:**
   - **Default path — edit going forward.** Shorten/remove the contested `quote` field (or an
     over-length excerpt) in the YAML record and commit normally. Git history still shows the old
     version — this is not a contradiction to resolve, it is simply what "public git repo as
     database" always meant, and it is the same trade-off D1 already accepted project-wide.
   - **Escalation path — history rewrite**, reserved for genuine severity (e.g. an entire
     copyrighted PDF got accidentally committed, not just an overlong quote): reuse D18's existing
     force-push escape hatch verbatim — a force-push is allowed, logged in the existing
     `REDACTIONS.md` (extend its category taxonomy, don't create a sibling log — see open question
     5) with date, affected path/commit, and reason category. This is not a new precedent; it's
     the same mechanism D18 already built for secret leaks, now explicitly scoped to also cover
     copyright incidents (which D18's `REDACTIONS.md` design already lists as one of its two
     named trigger categories — "allowed only for secret/copyright incidents").
   - **What never happens:** silent, unlogged deletion. Every takedown action — whether a normal
     forward-fixing commit or a rare force-push — leaves a trace, either in ordinary git history
     or in `REDACTIONS.md`.
5. **Escalate to an actual lawyer** exactly per D14's existing trigger list — this runbook is that
   trigger's operationalization, not a new decision. Concretely: if bucket-1 triage surfaces
   monetization, deliberate bulk ingestion, or a rightsholder who is not satisfied by the
   unpublish-and-shorten default and threatens formal action, that's the line where the developer
   stops self-triaging and gets real advice (university legal office, per D14 §Lawyer-if list, is
   a free first stop given the university-API relationship already in place).
6. **Close the loop:** reply to the complainant (email or issue) stating what was changed and
   linking the commit; if the resolution involved a `REDACTIONS.md` entry, that log is itself the
   public audit trail — no separate public "we got a complaint" announcement is needed or wanted.

### 2.3 Machine-readable dataset export with embedded attribution

D35's bundle already ships `manifest.json` with license-adjacent fields absent (only
`bundle_schema_version`, `ontology_version`, `data_tag`, hashes, row counts, verifier error rates).
Someone who downloads `langatlas-data-vN.sqlite.zst` directly — bypassing the website entirely —
has no attribution text unless it's embedded in the artifact itself.

- **Option A — a manifest field only.** Add `license: {corpus: "CC-BY-SA-4.0", corpus_url,
  code: "MIT", attribution_text: "LangAtlas contributors <https://langatlas.dev>, CC BY-SA 4.0"}`
  to `manifest.json`. Cheapest, machine-consumable, but a human skimming the bundle's contents
  (someone who unzips it and never opens the JSON) sees nothing.
- **Option B — a companion human-readable `NOTICE.txt` file, as a third Release asset.** Mirrors
  how open-data dumps (Wikidata, OSM) ship a plain-text NOTICE alongside machine formats. Costs one
  more small static file per release; trivial given D35's "low tens of MB compressed" scale.
- **Option C — a `_meta` table row inside the SQLite file itself**, since D35's Postgres loader
  already stamps a `_meta` table from manifest fields. A consumer who loads the bundle into their
  own Postgres/SQLite and never looks at `manifest.json` or `NOTICE.txt` still finds the license
  by querying the data itself.
- **Recommendation: all three, cheaply.** One manifest field (machine-readable, feeds MCP's `_meta`
  table per D35 already), one `NOTICE.txt` release asset (human-readable, standard convention,
  near-zero cost), and the `_meta` table carries the same field through the existing D35 loader
  path with no new code — it's the same three fields threaded through three surfaces that already
  exist, not three new artifacts.

This does not reopen D35 — it is a small additive field/file, matching the *pattern* D35 already
used for adding `embedding_model_id` and hash fields to the manifest without a redesign.

### 2.4 Transcript-corpus dataset licensing

D18 shipped the `langatlas-transcripts` repo (public, JSONL, one commit per run) with capture/
redaction/publishing fully designed, but assigned it no license — an oversight this brainstorm
closes, not a re-opening of D18's mechanics.

- **Option A — CC BY-SA 4.0, same as the corpus.** Simplest mental model: one license story for
  every human-readable public artifact the project produces. Consistent with treating transcripts
  as part of "the corpus" broadly. Cost: share-alike is a genuine drag on the exact downstream use
  case the checklist item names — "if someone wants to build their own eval/training set from the
  transcripts" — because a share-alike obligation on a derived training/eval corpus is legally
  murky (does fine-tuning on BY-SA text create a "derivative work" requiring the fine-tuned model
  or its outputs to also be BY-SA? unsettled, and ML practitioners largely avoid share-alike
  training data for exactly this reason) and would be a friction most such reusers would rather
  route around than resolve, defeating the purpose of publishing at all.
- **Option B — CC0 1.0 (public domain dedication), transcripts only.** Rationale specific to this
  artifact, not a general project stance: (1) LangAtlas's own copyright claim over an
  agent-authored transcript is thin-to-nonexistent in the US (no-human-authorship doctrine) and
  murky elsewhere — CC0 doesn't give away much that was solidly owned to begin with; (2)
  transcripts are explicitly framed (D24 §1) as *audit trail*, not the *product* — "the structured
  residue is the product; transcripts are the audit trail" — which argues for treating them like CI
  logs (maximally reusable, no one expects a share-alike claim on build logs) rather than like the
  corpus's protected expression; (3) directly serves the stated downstream use case (eval/training
  set construction) without a share-alike cloud over it; (4) third-party copyrighted material
  embedded in transcripts (fetched source excerpts) is unaffected either way — LangAtlas dedicating
  its *own* rights to the public domain cannot license away content it never owned, and D18 already
  truncates large fetched excerpts to hash+short-excerpt specifically to bound this exposure, so
  the residual risk is the same under either license choice.
- **Option C — MIT, treating transcripts as code-adjacent structured fixtures.** Rejected: MIT is
  a software license; applying it to prose chat logs is legally unusual and would confuse
  downstream users about whether the "software" framing (permission to copy/modify/sublicense
  *code*) actually covers a JSONL corpus of natural-language debate transcripts. CC-family licenses
  (or CC0) are the well-understood vocabulary for this kind of artifact; don't reach for a
  code license just because the *repo* mechanics resemble a code repo.

**Recommendation: B — CC0 1.0 for `langatlas-transcripts` specifically**, distinct from the
corpus's CC BY-SA 4.0. This is a genuinely different artifact with a genuinely different
risk/reuse profile (audit trail vs. product; thin-to-none original copyright claim vs. the
corpus's real curatorial/verification investment that justifies BY-SA's protective share-alike in
the first place), so giving it its own, more permissive license is consistent with D18's framing
rather than in tension with it. Add a short voluntary-attribution convention to the transcripts
repo's README (cite LangAtlas as origin — a courtesy norm, not a license term) so downstream
researchers still credit the project even though CC0 doesn't require it. No conflict with prompt
files: those live in `langatlas-kb` under the project's MIT code license (D41's prompt registry) —
a different artifact in a different repo, already cleanly separated by D18's own repo split.

## 3. Recommendation

1. **Attribution rendering (§2.1):** site gets a footer BY-SA notice linking to a new `/license/`
   explainer page (the three-layer note D14 already asked for) plus a `license` JSON-LD property
   on every page. MCP tool descriptions state the BY-SA reuse obligation once per session
   (D35-pattern), and every fact object carries a structural `attribution` field alongside D35's
   existing `caution` block.
2. **Takedown/complaint runbook (§2.2):** publish a dedicated email address (project alias, not
   necessarily personal) in `LICENSE`/`CONTRIBUTING.md`/`/license/`, plus an optional
   `legal-complaint.yml` issue form as a GitHub-native alternative — both funnel into one private
   triage: bucket into legal-vs-not-legal immediately, default safe action is unpublish-the-quote-
   not-the-fact, "takedown" means an ordinary forward-fixing commit except for genuine severity
   which reuses D18's existing `REDACTIONS.md` force-push escape hatch (broadened to explicitly
   cover this case, which D18 already scoped for), developer decides solo on process criteria, D14's
   existing lawyer-trigger list is the unchanged escalation line.
3. **Dataset export attribution (§2.3):** add one `license` field to D35's `manifest.json`, ship a
   companion `NOTICE.txt` Release asset, and carry the same field into the `_meta` table the D35
   loader already writes — three surfaces, one field, no bundle redesign.
4. **Transcript-corpus licensing (§2.4):** `langatlas-transcripts` gets its own license, CC0 1.0,
   distinct from the corpus's CC BY-SA 4.0 — reflecting that it's audit trail rather than product,
   has a thin-to-nonexistent original copyright claim, and directly serves the eval/training-set
   reuse case the checklist names. Voluntary attribution convention noted in the repo README, not
   enforced by license terms.

## 4. Open questions for the developer

1. **Ratify CC0 1.0 for `langatlas-transcripts`** (Option B, §2.4), distinct from the corpus's CC
   BY-SA 4.0 — or prefer license-uniformity (Option A, same BY-SA as the corpus) despite the
   share-alike friction on the eval/training-set use case the checklist itself names as the
   motivating scenario?
2. **Complaint intake email**: confirm publishing a dedicated project-alias address (e.g. something
   under the `langatlas.dev` domain once registered, per the still-open D17 registration item) as
   the primary takedown-complaint channel, with a `legal-complaint.yml` issue form as the
   GitHub-native alternative (§2.2) — or is a single GitHub-only channel acceptable, accepting the
   friction for rightsholders?
3. **`REDACTIONS.md` scope**: confirm broadening its existing category taxonomy to explicitly cover
   takedown-driven history rewrites (it already lists "copyright incidents" per D18, so this may be
   purely a documentation clarification, not a new mechanism) rather than standing up a sibling
   `TAKEDOWNS.md` log.
4. **Attribution text wording**: is "LangAtlas contributors" the right attribution name for the
   footer/JSON-LD/MCP/`NOTICE.txt` string, or does the developer want a different formal name
   (e.g. tied to whatever legal entity, if any, ever holds the project) — low-stakes now, but worth
   fixing one string used in four places rather than drifting.
5. **Acknowledgment SLA number**: is 5 business days an acceptable stated (non-binding, good-faith)
   acknowledgment target for takedown complaints, mirroring D9's existing "best-effort" resolution
   posture for ordinary challenges — or does the developer want no stated number at all, keeping
   it purely best-effort with nothing to point to if missed?

## 5. New brainstorm topics surfaced

None. This topic closes out all four items brainstorm 15 named as its own follow-ups (attribution
rendering, takedown runbook, dataset export attribution, transcript licensing) without surfacing
new downstream design work — the recommendations above are additive fields/files/conventions
layered onto D18/D32/D35's already-designed mechanics, not new systems.

## Sources

- Creative Commons (2013). *CC BY-SA 4.0 Legal Code*, §3(a) (attribution and ShareAlike
  conditions). https://creativecommons.org/licenses/by-sa/4.0/legalcode.en
- Creative Commons (2021). *CC0 1.0 Universal — Public Domain Dedication*.
  https://creativecommons.org/publicdomain/zero/1.0/legalcode
- U.S. Copyright Office (2023). *Copyright Registration Guidance: Works Containing Material
  Generated by Artificial Intelligence* (human-authorship requirement).
  https://www.federalregister.gov/documents/2023/03/16/2023-05321
- GitHub Docs (2026). *About DMCA takedown notices* (for contrast: LangAtlas is not a UGC host and
  does not rely on DMCA safe-harbor mechanics the way a platform does).
  https://docs.github.com/en/site-policy/content-removal-policies/dmca-takedown-policy
