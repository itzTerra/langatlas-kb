# 05 — Human Expert Challenge Workflow

## Problem framing

Every user-facing fact in Hermes (feature definitions, per-language feature instances, syntax
previews, quality-impact claims, graph edges like *requires*/*conflicts-with*) is produced or
curated by AI agents from cited sources (brief §2.1, §2.4). The owner's hard requirement (§2.5):
a human expert who knows better than the agents must be able to challenge any fact with trivial
effort, and that challenge must actually flow into a corrected, re-cited fact.

Constraints that shape the answer:

- **Solo developer, PoC MVP** (§2.7) — anything requiring built-from-scratch auth, spam defense,
  or moderation tooling is a project-killer.
- **Agents also write facts** (§2.4) — the challenge channel and the agent-write channel must
  converge on one canonical store, or they will diverge and neither can be trusted.
- The site itself is for human eyes, not an AI source (§2.6) — so the challenge UI must live on
  fact pages, but the truth can live elsewhere.
- The Notion page already asks for "link to GitHub discussion/thread under each feature and
  language" and "source code link for every bit of info on the site" (§1, Knowledge Base) — the
  owner's instinct already points at GitHub.

The real questions are: (1) is a git repo a viable canonical store at plausible corpus sizes,
(2) which direction does sync flow, (3) how does a non-programmer linguist actually file a
challenge, and (4) what closes the loop from challenge to corrected fact.

## Repo-size reality check (do the math)

Fact corpus dimensions, from the brief's own feature model:

- **Features/concepts**: layer 2 + layer 3 of the architecture notes enumerate roughly 60–100
  atoms today; a mature model might reach **200–400 features** (with sub-abilities).
- **Languages**: MVP realistically **10–30**; an ambitious long-term corpus (pldb-scale) is
  **500–1,000**, but most niche languages will have sparse coverage (say 30–60% of features
  applicable/known).
- **Feature instances** (the dominant fact type, language × feature): MVP ≈ 20 × 150 ≈ **3,000**;
  long-term ≈ 500 × 300 × 0.4 coverage ≈ **60,000**.
- **File size**: a YAML fact file with id, structured fields, a syntax snippet, 2–4 citation keys,
  and status metadata is **1–3 KB** (syntax-heavy instances maybe 5 KB).

| Scenario | Files | Raw size | Verdict |
|---|---|---|---|
| MVP (20 langs × 150 features + feature/edge/source files) | ~4–5 k | **~10 MB** | Trivial |
| Mid-term (100 langs) | ~20 k | ~50 MB | Trivial |
| Max plausible (500+ langs, full model) | ~60–80 k | **~200 MB** | Fine; GitHub's soft limit is 1 GB, hard guidance 5 GB |

Git handles tens of thousands of small text files without trouble if sharded into directories
(`facts/<language>/<feature>.yaml`); pldb itself runs ~5,000-file corpora as a plain GitHub repo.
History bloat from agent churn is text-diff-sized, so negligible. **The "space concern" in the
brief is a non-issue.** The only real caveat: never commit embeddings or binary artifacts —
those are build outputs, not facts.

## Options with trade-offs

### Option A — Facts as YAML files on GitHub, feedback via GitHub (brief option a, pure)

- **Pros**: zero infrastructure; free auth, spam filtering, notifications, review UI, CI; full
  audit trail (git history = provenance); the diff *is* the challenge resolution; agents and
  humans use the same channel (PRs); matches the Notion page's "link to GitHub discussion under
  each feature" wish.
- **Cons**: raw GitHub is intimidating for non-programmer academics (finding the right file,
  YAML syntax, fork/PR dance); "sync with production DB" is unspecified in this pure form —
  if the DB is also writable, you get a two-master conflict nightmare.

### Option B — Custom forum module in the app (brief option b)

- **Pros**: zero-friction for any visitor; discussion lives exactly where the fact is rendered;
  no GitHub account needed.
- **Cons**: solo dev must build and operate auth, spam defense, moderation queues, notifications,
  and an entirely separate challenge→fact-edit pipeline; a forum thread does not resolve into a
  diff — someone still has to translate consensus into a data change by hand; moderation burden
  lands entirely on one person with no tooling. For a PoC MVP this is a second product. **Reject
  for MVP.**

### Hybrid H1 — Docs-as-code: git repo canonical, production DB as build artifact (recommended)

The repo is the *single source of truth*. The production stack (relational/graph DB for the site,
vector DB for RAG) is a **derived, disposable build artifact** compiled by CI on every merge to
`main`. Sync is therefore strictly one-way (repo → DB); there is no "sync back" problem because
nothing but the repo is ever authoritative.

- **Agent writes**: agents never touch the DB. Each agent run works on a branch and opens a PR
  ("agent proposes, human disposes"). CI validates schema, citation-key resolution, and the
  brief's combination rules (required/impossible/problematic — §1) before the solo dev merges.
  This turns the multi-agent workflow (topic 04) into reviewable, revertible units.
- **Rebuild cost**: CI re-embeds only changed files (diff-driven), loads DB incrementally or
  rebuilds wholesale — at ≤200 MB of text, wholesale rebuild stays in minutes.
- **Conflict story**: git merge on small per-fact files; conflicts are rare (one fact = one file)
  and resolved in review like any code conflict.

### Hybrid H2 — "Challenge this fact" button → prefilled GitHub issue (recommended, on top of H1)

Every fact page gets a visible **Challenge** button that deep-links to
`github.com/.../issues/new?template=challenge.yml&title=...&body=...` with an issue form
prefilled with: fact ID, file path, current value, current citations, page URL. The expert only
types *what is wrong and what source says otherwise*. GitHub issue forms give structured fields
(claimed correction, counter-source, expertise context) without the expert touching YAML or PRs.
Cost: a URL template — near-zero code. Friction: requires a (free) GitHub account; acceptable
for the linguist/academic audience at MVP, and it doubles as a spam gate.

### Hybrid H3 — giscus-style embedded GitHub Discussions under each fact page

Embed a Discussions thread per fact/language page (the Notion page literally asks for this).
Good for open-ended debate that isn't yet a concrete challenge. Costs one widget include; reuses
GitHub auth/moderation. Slight SEO/perf/cleanliness tension with the "clean and pretty" design
goal (§2.6) — lazy-load below the fold. **Nice-to-have, phase after the button.**

### Hybrid H4 — Anonymous web form → server creates the issue via API

Removes the GitHub-account requirement entirely. But it removes the spam gate too, and the solo
dev becomes the spam filter. Defer until there is evidence that the GitHub account requirement
is actually losing valuable challenges.

## The challenge lifecycle (H1 + H2 end-to-end)

1. Expert clicks **Challenge this fact** on the site → prefilled GitHub issue (labeled
   `challenge`, fact ID embedded).
2. Solo dev triages (or auto-label by fact area). Obvious spam closed with one click.
3. Dev triggers an agent session (Claude Code) on the issue: the agent reads the challenge,
   hunts for the cited counter-source, re-argues against the existing citations (reusing the
   topic-04 debate machinery), and **opens a PR** editing the fact file — corrected value, new
   citation, and a `history:`/changelog note referencing the issue.
4. The challenging expert is @-mentioned on the PR; they can confirm or push back in review.
5. Merge → CI validates schema + citations → rebuilds DB and re-embeds changed facts → site
   shows the corrected fact; git blame/history is the public audit trail ("source code link for
   every bit of info" from the Notion page, fulfilled literally).
6. Optional fact metadata: `status: proposed | verified | challenged | disputed` so the site can
   badge contested facts while the issue is open.

Moderation burden for the solo dev = triaging labeled issues and reviewing agent PRs — work that
is already required by the agent workflow anyway; the challenge channel adds no new operational
surface.

## Recommendation

**For the MVP: H1 + H2.** Git repo of per-fact YAML files as the canonical store
(`facts/<language>/<feature>.yaml`, plus `features/`, `edges/`, `sources/`); production
relational/graph DB and vector index are one-way build artifacts of CI; agents contribute only
via PRs; human challenges arrive via a "Challenge this fact" button that opens a prefilled
GitHub issue form; resolution is an agent-drafted, human-merged PR. Add giscus-style embedded
Discussions (H3) as a fast follow. Build no forum (B); revisit anonymous intake (H4) only if
real experts demonstrably bounce off the GitHub account requirement. The size math shows the
repo concern is unfounded (~10 MB MVP, ~200 MB worst case), and the one-way build direction
dissolves the sync-back concern by construction.

This choice also quietly settles an architecture question for topics 01/03: the vector DB and
site DB need no write path from the app at all for facts — a large simplification.

## Open questions for the owner

1. Are per-fact YAML files acceptable as the *authoring format* for agents (topic 01 must define
   the schema), or does the graph model demand a different canonical serialization (e.g. one
   file per node + one per edge)?
2. Public repo from day one? Public is required for outside PRs/issues and is the spirit of the
   idea, but it exposes half-built data early — is that acceptable?
3. Should community *upvotes* (used for ranking, §1) live in GitHub reactions on Discussions, or
   in the app DB? (Reactions are free but coarse; app-side votes reintroduce a write path.)
4. May agents auto-open PRs unattended (e.g. via CI/scheduled runs), or must every agent run be
   dev-initiated? Affects Claude Code Pro budget (topic 04) and review load.
5. What SLA/expectation should the site state for challenge resolution, given a solo maintainer?
   (E.g. a "disputed" badge appears immediately, resolution is best-effort.)
6. Is requiring a GitHub account for challengers acceptable for the target expert audience?

## New brainstorm topics surfaced

- **Fact-file schema & repo layout design** — the concrete YAML schema, ID scheme, directory
  sharding, and CI validation rules (extends topic 01; needed before any agent writes a fact).
- **CI build pipeline: repo → DB + embeddings** — incremental re-embedding of changed facts,
  deploy atomicity, rollback story (extends topic 03).
- **Contested-fact UX** — how `challenged/disputed` status renders on a clean SEO site without
  undermining trust (feeds topic 06).
- **Agent PR etiquette & batching** — PR size/granularity for agent runs so a solo dev can
  actually review them (feeds topics 04 and 07).
