# 19 — Website Deep-Dives

> Backlog brainstorm for LangAtlas. Scope per the checklist: on-site search (Pagefind vs API),
> feature-support-matrix component UX, syntax-preview validation & highlighting coverage for
> exotic languages, OG-image generation, privacy-first analytics loop, and trust-signal UX
> (rendering up to five per-fact signals without dashboard creep). Binding context:
> `context/decisions.md` D7/D8 (retrieval stack, MCP is agent-facing, the site reads structured
> data directly — SEO pages are never rendered from RAG), D10 (Astro, fully static, zero-JS
> knowledge-base pages, typography-first design, build-time Shiki, quiet numeric-superscript
> citation popovers via the native Popover API, stable `data-fact-id`), D13 (validated dataset
> bundle, `data-vN` build stamp), D18 (chat viewer as a v1.5 Astro island), D25 (three orthogonal
> status axes + ordinal confidence + four-level controversy score — the exact signal set this
> brainstorm's trust-signal sub-topic renders), D28 (14+1 languages, all with bundled Shiki
> grammars). Sibling brainstorm 18 (`18-contribution-funnel.md`, just completed) added a
> `/coverage/` page to the site IA and deliberately left the matrix component's interaction
> design, sorting/filtering, and "does it become an island" question to this brainstorm — this
> file does not relitigate 18's IA placement or three-state empty-cell semantics, only the
> component UX sitting inside that page. Five fairly independent sub-topics plus one cross-cutting
> concern; each gets its own options subsection rather than a single forced options list. All
> proposals here are *proposed* until the developer ratifies.

## 1. Problem framing

D10 committed the site to a hard constraint that every sub-topic here has to be checked against:
**fully static, zero JS on knowledge-base pages**. That constraint is why this brainstorm exists
as a single unit rather than five separate ones — search, a sortable matrix, OG images, and
analytics are the four surfaces on almost any content site where "just add a JS widget" is the
default instinct, and each one needs its own argument for why it does or doesn't get an exception
to zero-JS, rather than a blanket policy decided once. The fifth sub-topic (syntax-preview
coverage) is a data-completeness question, not a UI one, but it shares this file because it
touches the same build-time Shiki step D10 already ratified. The cross-cutting trust-signal
question is different in kind again: it's not "does this need JS" but "how do you show five
independent axes of epistemic status per fact without turning every page into a status-badge
farm" — the tension D25 left unresolved is a *data model* for the signals, not their *rendering*.

A second thread runs under all five: **build-time cost and complexity for a solo maintainer**
(CLAUDE.md: "favor boring, solo-maintainable technology"). Every option below is screened first
for whether it adds a service, a daemon, a third-party account, or ongoing maintenance burden
disproportionate to what a personal reference site needs at its likely traffic (P2 in the risk
register: SEO cold start is expected, not a failure).

## 2. Options with trade-offs

### 2.1 On-site search: Pagefind vs API

Two fundamentally different architectures compete here, and they aren't actually solving the same
problem.

**Option A — Pagefind.** A Rust-based static search library that indexes the built HTML output
at deploy time and ships a small WASM+JS runtime that queries the index entirely client-side —
no backend, no API key, no per-query cost, no server round-trip (Pagefind docs, 2026; adopted by
Astro's own Starlight theme as the zero-config default — Starlight docs, 2026). It reads the
rendered `/features/`, `/languages/`, and comparison pages after Astro builds them, so it indexes
exactly what a visitor sees, including citation text and syntax-preview code if desired.

**Option B — the existing FastAPI/MCP retrieval stack (D8) exposed to the site's search box.**
D8 already names this as the intended consumer: "a thin FastAPI adapter serves ... the site's
search box." This is semantic/hybrid search (BM25+vector+RRF per D7) over the same Postgres the
MCP server reads, so a query for "pattern matching exhaustiveness" can surface a feature page
even if that exact phrase never appears verbatim — Pagefind, being a lexical index over rendered
text, cannot do that.

**Option C — both, layered.** Pagefind as the zero-JS default (works with JS disabled, no
external call, indexes the actual page text visitors read); the FastAPI-backed hybrid search as
a progressively-enhanced upgrade — e.g. a "try smarter search" affordance, or the default for a
`/search/` results page that itself can be a small Astro island, while inline instant-search
widgets on every page stay Pagefind-only.

**Trade-offs.** Pagefind costs nothing to run (static asset, no server), fits D10's zero-JS
posture almost by definition (the *querying* is client-side JS, but there is no backend to
operate — closer in spirit to "no growth chrome"-style infra austerity than to the site's
per-page rendering rule), and needs zero query-cost budgeting. Its weakness is exactly the
knowledge base's own selling point (D19: typed concept graph, not full-text): a lexical index
can't answer "what's like pattern matching but without exhaustiveness checking" — the kind of
query the RAG stack (D7/D8) is built for. Exposing the FastAPI adapter to the public internet,
conversely, means the site is no longer purely static for that one endpoint — it needs uptime,
rate limiting against scraping/abuse, and a live Postgres connection reachable from outside the
docker-compose network, which is new infrastructure the "absent on purpose" list (D12) doesn't
currently include.

**Recommendation: Option A now, Option C as the natural fast-follow.** Ship Pagefind as the
default search experience — it is free, static, needs no new service, and correctly serves the
overwhelmingly common query shape ("rust pattern matching", "python vs go error handling").
Defer exposing the FastAPI search endpoint publicly until there's a concrete reason to believe
visitors need semantic search over lexical search (a logged-query analysis, §2.5, would be the
natural trigger) — this keeps day-one infra exactly at what D8 already built for agents, adding
no new public attack surface for a benefit that's speculative until traffic exists.

### 2.2 Feature-support-matrix component UX

Scope note: brainstorm 18 already decided the matrix's **page** (`/coverage/`), its **three
empty-cell states** (not-yet-swept / not-yet-onboarded / deferred), and that empty cells deep-link
to a prefilled `propose-coverage` issue. What's left is the **component**: how a visitor
sorts/filters/reads the matrix, and whether any part of it becomes an interactive island.

**Option A — fully static, several pre-baked views, no client-side interactivity.** Brainstorm 18
already leaned this way ("ship a handful of pre-baked static views at build time ... rather than a
live interactive table"). Concretely: `/coverage/` (overview, all languages × all features,
paginated or scoped to layer-1/2 features only to keep the grid legible), `/coverage/<language>/`
(one language's row expanded to full feature detail — this can just be the existing
`/languages/<x>/` page's coverage section), `/coverage/by-dimension/<d>/` (one layer-3 dimension's
column across all languages), and a `/coverage/gaps/` "biggest gaps" view sorted server-side by
empty-cell count. Each is a distinct static HTML page; "sorting" happens by picking which
pre-sorted page to load, "filtering" happens by picking which scoped page to load.

**Option B — CSS-only interactivity** (checkbox/radio hack, `:has()`, or `<details>`-based
show/hide) for column/row toggling within a single static page, no JavaScript at all. Modern CSS
(`:has()`, container queries) can do a surprising amount of client-side filtering without a
script tag — e.g. checkboxes bound via `:has()` selectors to hide non-matching rows. This keeps
the "zero JS" letter of D10 while giving a single page some of Option C's interactivity.
Trade-off: CSS-only filtering scales poorly past a handful of toggles (each filter dimension
roughly doubles the selector complexity) and produces markup that's hard to keep readable; a
14(-and-growing)-language × dozens-of-features grid has enough dimensions that this likely hits
a legibility wall the pre-baked-views approach doesn't.

**Option C — a small interactive Astro island** (a client-side sortable/filterable table,
hydrated only on `/coverage/`) using vanilla JS or a tiny library (no framework runtime beyond
what Astro islands already support). D10 already reserves islands for the Builder/Selector later
— this would be the first island on a knowledge-base-adjacent page, a real precedent to weigh
carefully. Pros: the actual best UX (live sort by any column, live filter by language family or
dimension, instant search-within-matrix) and the most legitimate reason yet to have earned an
exception ("it's not a KB fact page, it's a tool page"). Cons: sets a precedent that every future
"this would be nicer with JS" request can point to; a coverage matrix over 15+ languages ×
dozens of features is a genuinely large DOM/data payload to ship client-side, which cuts against
the site's stated performance-and-austerity ethos even where it's technically still "just an
island."

**Recommendation: Option A first, revisit B/C only if the pre-baked views prove genuinely
insufficient once real coverage data exists.** The matrix is at its most useful (and most honest
as brainstorm 18 intends — "genuinely useful knowledge-base furniture," not growth chrome) during
the exact period when most cells are empty (D28's four-phase rollout) — a handful of pre-sorted
static pages already answers "what's the biggest gap" and "what does this language have" without
inventing a new interaction pattern for the site. If, once phases 1–3 land, the grid becomes large
enough that pre-baked views genuinely can't cover the useful query shapes, revisit with Option C
first (a real island, done well) over Option B (CSS-only tends to become its own maintenance
trap once past trivial filtering).

### 2.3 Syntax-preview validation & highlighting coverage

D10 ratified build-time Shiki highlighting; D28 already confirmed "all 14(+VB) have bundled
Shiki grammars (no D10 risk)" for the initial language set. So the checklist's "exotic languages"
phrasing is stale relative to D28's resolution for the *initial* set — the live question is
narrower and two-part: (a) what happens to syntax highlighting for languages onboarded **after**
1.0 that might lack a bundled TextMate grammar, and (b) a separate, unaddressed question:
**validating that a syntax preview is actually well-formed/plausible code**, not just that Shiki
can color it.

**On (a) — highlighting coverage for future languages.** Shiki explicitly does not maintain
grammars itself; it consumes the community `textmate-grammars-themes` project, and coverage for
niche/DSL/research languages is uneven outside mainstream ones (Shiki docs, 2026 — "Shiki does
NOT control/maintain the grammars ... refer to textmate-grammars-themes"). D28's deferred list
already includes languages with exactly this profile (APL-family, e.g.) for other reasons.
**Recommendation:** treat missing-grammar risk as a per-language onboarding checklist item
(alongside the license/spec/Shiki audit brainstorm 34 already ran for the initial 14+1) rather
than a general site feature — a language proposed via D28's future phases gets a one-line
Shiki-grammar check before its sweep starts; if none exists, fall back to Shiki's plain-text
("txt") highlighting for that language's code blocks rather than blocking onboarding on writing a
custom TextMate grammar (a real but bounded side project Shiki's own docs describe as supported,
just not maintained by Shiki itself).

**On (b) — syntax-preview *validation*.** This is the sharper, currently-undesigned gap: nothing
in D9/D23's fact-schema work checks that a `syntax:` example (D23's keyed syntax examples,
carrying D14's `origin: original | adapted-from:<source-id>` field) is actually valid code in the
target language, as opposed to merely something Shiki can tokenize and color plausibly (Shiki
highlights based on lexical/grammar patterns, not semantic correctness — a snippet with a typo
still "looks" highlighted). Options:

- **Option A — no automated check; rely on source-adjacency.** Since D14 already requires
  syntax examples be original (not copied), and D24's verifier checks *claims* against sources,
  not code correctness, this would leave syntax examples as the one fact-adjacent artifact with
  no automated quality gate at all. Cheapest, but a real gap: a broken snippet is exactly the kind
  of low-severity, high-visibility embarrassment a solo maintainer notices from readers before
  they notice it themselves.
- **Option B — compile/parse-check where a toolchain exists in CI.** For languages with a fast,
  installable compiler/parser (most of D28's initial 14), run the snippet through the language's
  own parser (not full compilation — many snippets are intentionally partial/illustrative) as a
  CI check at commit time, alongside the existing D13 fast offline validators. For interpreted
  languages this can be a syntax-check-only invocation (e.g. `python -m py_compile`,
  `ruby -c`, `node --check`); for compiled languages, front-end-only parse where the toolchain
  supports it (`rustc --edition ... -Zparse-only`-style flags, `gcc -fsyntax-only`). Genuinely
  partial snippets (a function body without its enclosing module) need a documented convention —
  either a per-syntax-example `parseable: true|false` flag, or wrapping snippets in a minimal
  boilerplate harness before parse-checking.
- **Option C — LLM-based plausibility check** as part of the existing D24 verification pipeline
  (the entailment call already reads the claim; add "is this syntax example well-formed
  `<language>`" as a cheap side-question). Cheaper to stand up than per-language toolchains, but
  weaker: an LLM affirming "this looks like valid Rust" is exactly the kind of unverified
  assertion D4 was built to avoid trusting for factual claims — using it for code correctness
  reintroduces the same class of risk one level down.

**Recommendation: Option B, scoped to the languages where it's cheap, degrading gracefully
elsewhere.** Add a `syntax_check: parser | none` field per language in the registry (extending
D23's language registry); wire real parse-only checks for languages with a fast CLI syntax-check
mode (most of D28's initial set qualify) into the same fast offline validator suite D13 already
runs pre-commit; for languages without one, fall back to Option A (no check) rather than Option C
— an absent check is an honest gap; an LLM affirming code correctness without ground truth is a
disguised one, and would sit uncomfortably next to D4's entire premise.

### 2.4 OG-image generation

**Option A — static, hand-authored OG image(s).** One or a handful of generic images (one for
the site root, maybe one per top-level section: features/languages/coverage) reused across many
pages. Zero build complexity, but every shared/linked page (thousands of feature-instance and
comparison pages, per D10's IA) looks identical in a social-media preview — a missed opportunity
given how much of the site's content (a fact, a comparison verdict, a citation count) is
naturally headline-able.

**Option B — build-time dynamic generation via Satori + resvg.** Satori (Vercel-maintained)
converts a JSX/HTML+CSS template to SVG, then `resvg` rasterizes to PNG, both run as an Astro
build step (not a runtime endpoint) producing one static PNG per page at build time — the
standard pattern documented across the Astro ecosystem (dietcode.io 2026; egghead.io 2026; the
1200×630 OG dimension convention is treated as settled practice). Fully consistent with D10's
"fully static" posture: no server-side image generation at request time, just another build
artifact alongside the HTML.

**Option C — `astro-og-canvas`.** A purpose-built Astro integration using the Canvas API
(via `canvaskit-wasm`) instead of Satori's JSX→SVG→PNG pipeline; used by Astro's own
documentation site for its own OG images. Simpler integration surface (declarative config,
no JSX authoring) at the cost of less layout flexibility than Satori's HTML/CSS-like templating
— a real trade-off given the site wants distinct templates for a feature page (headline: feature
name + one-line description + citation count) vs a comparison page (headline: "X vs Y" + which
language wins on what) vs a language page.

**Recommendation: Option B (Satori + resvg) over C, generating per-entity images at build time.**
Two or three templates covering the IA's real page kinds (feature, language, feature-instance/
comparison) — pull the page's title, a one-line summary, and (where it exists) a citation count
or controversy badge glyph (kept as a small icon, not full text, to avoid rendering D25's status
vocabulary into a static image that can go stale relative to the live badge) directly from the
same structured data layer Astro already reads for the page itself (D10). Satori's flexibility
matters here specifically because comparison pages want a genuinely different layout (two-column,
"X vs Y") than a single-feature page — the kind of per-template variance `astro-og-canvas`'s more
declarative surface is a slightly worse fit for. This is pure build-time cost (adds image encoding
to the existing full-rebuild-per-push model D10 already accepted), no new runtime service.

### 2.5 Privacy-first analytics loop

The developer constraint "privacy matters" plus D10's already-ratified "no growth chrome" frame
this narrowly: analytics exist to answer the developer's own operational questions (is anyone
finding this via search, which pages get read, does the coverage page drive any issue filing) —
not to power a public dashboard or feed a contributor-facing vanity metric (which §2.6 of
brainstorm 18 already ruled out for contributor counts specifically; the same logic extends here).

**Option A — no analytics at all.** Cheapest, cleanest privacy story, but leaves the developer
blind to whether the frontloaded-research-phase corpus is reaching anyone, which pages are
actually useful, or whether the coverage-matrix recruitment surface (brainstorm 18) does anything
at all — a real cost against a project whose stated success metric (risk P2) is explicitly "corpus
quality + MCP usability, not traffic," but that metric still benefits from knowing whether *any*
signal exists.

**Option B — a cookieless, self-hosted, script-tag analytics tool** (GoatCounter, Plausible
self-hosted, or Umami self-hosted — all three are established, actively maintained, GDPR-oriented
options as of 2026 with no cookie banner required because they don't track individuals across
sessions; comparisons converge on: Umami is MIT-licensed, Docker/Node-friendly, and lightweight;
Plausible and GoatCounter use copyleft licenses (AGPL/EUPL) and are similarly lightweight;
GoatCounter ships as a single Go binary with no official Docker image, a minor friction point
against the project's docker-compose-first posture (D7); Plausible and Umami both offer either a
managed cloud tier or self-hosting). **Recommendation within B: self-hosted Umami**, run as one
more service in the existing docker-compose stack (D7 already runs Postgres there) — MIT-licensed
(consistent with the code-MIT stance, D12/D14), lightweight, and avoids GoatCounter's
Docker-packaging friction. A single `<script>` tag on site pages, no cookie, no PII, IP not
stored — satisfies "privacy-first" as a design constraint rather than a marketing label.

**Option C — a managed cloud analytics service** (Plausible Cloud, Umami Cloud, Fathom, Simple
Analytics). Zero self-hosting burden, but recurring cost (small, but "no cash budget" per
CLAUDE.md's developer constraints argues against any recurring spend when a free self-hosted
option satisfies the same need) and a third party (even a privacy-respecting one) sees the site's
traffic data — a minor but real regression against "public git repo + static site + no vendor
lock-in" austerity the rest of the architecture holds to.

**Recommendation: Option B, self-hosted Umami in the existing compose stack, added once the site
has actually shipped (not blocking initial launch)** — analytics is a low-priority, low-risk
addition entirely decoupled from the KB pipeline's own build/deploy story, and standing it up
before there's a live site to measure has no value. The "loop" the checklist names (closing the
loop from traffic data back into decisions) is intentionally kept manual and low-frequency: the
developer glances at page-view and search-query data periodically to inform which pages need
work or which languages readers are asking about — not a real-time dashboard, and specifically
**not** surfaced anywhere on the public site (keeping faith with D10's no-growth-chrome stance —
analytics is operational tooling for the developer, not a public-facing signal).

### 2.6 Trust-signal UX: rendering D25's five axes without dashboard creep

D25 already designed the *data model*: three orthogonal status axes (verification, freshness,
dispute) collapsed to one derived display status by fixed precedence, plus an independent
ordinal confidence (`high/medium/low`) and a four-level controversy score
(settled/noted-variance/contested/disputed). That's already four-to-five distinct values a single
fact could in principle carry (derived status, confidence, controversy, plus challenge-activity
as a separate accompanying value D21/D25 keep out of the score itself) — the open problem is
purely presentational: how much of that surfaces per fact without every fact card growing a row
of badges that reads like a build-status dashboard rather than a knowledge-base page.

**Option A — show everything, always, as a badge row.** Every fact gets up to five simultaneous
badges (status/confidence/controversy/freshness/challenge-activity). Maximally transparent, but
directly contradicts D10's typography-first, "opposite of Amazon" design ethos — a page with
dozens of facts, each carrying a five-badge row, reads exactly like the dashboard-y, growth-chrome
aesthetic the whole site design explicitly rejects.

**Option B — badge-free by default; all signals live inside the existing citation popover.**
D10 already put a quiet numeric-superscript citation marker with a Popover-API-driven popover on
every fact (`data-fact-id`). Extend that popover's existing content (source, "Challenge this
fact" per D9) with the status signals, rendered as **one line of plain, small-caps-style text**
inside the popover body rather than as separate colored badges — e.g. "Verified · high confidence
· settled" as prose, with `contested`/`disputed` facts additionally getting the one visual
exception (§2.6 Option C below). Nothing changes about the base page's visual density; a reader
who never opens a popover sees exactly what they see today.

**Option C — one visual exception: a single, minimal marker for the states that matter most.**
Not all five axes are equally actionable to a casual reader. Recommendation: only two states earn
any glyph on the base page (outside the popover) at all — a fact that is `disputed`
(controversy level 3) or has `dispute: contradicted/superseded` gets a small, single, consistently
-styled marker (one shape, one color, doing double duty for "there's something you should know
before trusting this at face value" — not a different badge per axis) directly adjacent to the
citation superscript; `partially-verified` facts (D25's ratified rule: "render publicly, visibly
marked with a badge — not suppressed") get the same single marker treatment, reusing one glyph
rather than minting a second one. Every other combination (verified/fresh/settled/high-confidence
— the large majority of facts, especially post-verification-gate) shows nothing extra at all: the
plain numeric superscript is the entire signal, exactly as D10 already designed it. All five axes
remain inspectable in the popover (Option B) for anyone who clicks in; only the subset that
changes what a reader should *do* with the fact (double-check it, expect it to change) earns
visual weight on the page itself.

**Trade-off analysis.** Option C is a considered middle ground, not a compromise for its own
sake: it follows the same principle 06/12's confidence-and-dissent design already established —
"verified" needing no badge (it's the default, unmarked state) while `partially-verified` earns
one (D25, ratified) is precisely the asymmetric-marking pattern Option C generalizes to the other
axes. It also matches an established UX pattern outside this project: status/trust indicators
that go unmarked in the common case and only interrupt visual flow for the minority of instances
that need attention avoid exactly the "everything is always badged, so nothing stands out"
failure mode dashboards fall into.

**Recommendation: B + C together** — full signal detail lives in the existing popover (extending
D10's popover content, not adding new UI surface), and exactly one shared glyph marks
`disputed`/`contradicted`/`superseded`/`partially-verified` facts on the base page, with every
other combination staying visually silent. Confidence and the settled/noted-variance controversy
levels never get their own base-page glyph at all — they're popover-only detail, consistent with
"presentation thresholds stay with the site" (D21/D25) being interpreted here as "thresholds
decide when to interrupt, not how many badges to draw."

## 3. Recommendation (*proposed*)

1. **§2.1 — search**: ship Pagefind (static, zero-cost, client-side lexical index over rendered
   pages) as the default; defer exposing the FastAPI/hybrid-search endpoint (D8) publicly until
   logged-query data shows lexical search is insufficient.
2. **§2.2 — coverage-matrix component**: several pre-baked static views (overview, per-language,
   per-dimension, "biggest gaps") satisfy the useful query shapes while most cells are empty
   (D28's phased rollout); revisit an Astro island only if that proves insufficient once real
   coverage data exists, and prefer a real island over CSS-only interactivity at that point.
3. **§2.3 — syntax-preview validation**: extend the language registry with a
   `syntax_check: parser | none` field; wire real parse-only checks (not full compilation) into
   the existing D13 fast offline validator suite for languages with a cheap CLI syntax-check mode;
   explicitly reject LLM-based plausibility checks for code correctness as inconsistent with D4's
   verified-ground-truth premise. Missing-Shiki-grammar risk is a per-onboarding-cycle checklist
   item (falling back to plain-text highlighting), not a new site feature.
4. **§2.4 — OG images**: build-time Satori + resvg generation, two-to-three page-kind templates
   (feature / language / comparison), pulling straight from the existing structured data layer;
   no runtime image service.
5. **§2.5 — analytics**: self-hosted Umami in the existing docker-compose stack (MIT-licensed,
   cookieless, no PII), added post-launch rather than blocking it, consumed manually and
   privately by the developer — never surfaced on the public site.
6. **§2.6 — trust-signal UX**: extend the existing D10 citation popover with a plain-text line
   covering all D25 axes; reserve a single shared base-page glyph for the disputed/contradicted/
   superseded/partially-verified minority of facts; every other status combination stays visually
   silent on the page itself.

## 4. Open questions for the developer

1. **§2.1** — is a `/search/` results page (vs. an inline instant-search box on every page, vs.
   both) the right shape for Pagefind's UI, and does the FastAPI hybrid-search fast-follow warrant
   its own future brainstorm once query-log data exists, or is this brainstorm's deferral
   sufficient direction for now?
2. **§2.2** — does "revisit an Astro island once pre-baked views prove insufficient" need a
   concrete trigger (e.g. a language/feature count threshold) decided now, or is "the developer
   notices the static views aren't working" an acceptable trigger to leave informal?
3. **§2.3** — for languages without a fast CLI syntax-check mode (Prolog and some future
   DSL-shaped languages, per topic 42's still-open `language_kind` question), is "no automated
   check" acceptable indefinitely, or should this be revisited once topic 42 settles what
   "language_kind" even means for non-mainstream language families?
4. **§2.4** — should the citation-count/controversy glyph on OG images be omitted entirely (to
   avoid any staleness risk between the static image and the live page), or is a coarse,
   rarely-stale icon (verified/disputed only, not the full badge) an acceptable inclusion?
5. **§2.5** — confirm self-hosted Umami over Plausible/GoatCounter self-hosted, given the
   MIT-license/Docker-friendliness argument — or does the developer have a standing preference
   from other projects that should override that reasoning?
6. **§2.6** — confirm the single-shared-glyph design (one marker doing double duty for
   disputed/contradicted/superseded/partially-verified) rather than distinguishing them visually
   at the base-page level — is collapsing four distinct D25 states into one visual signal an
   acceptable simplification, or does the developer want at least disputed-vs-partially-verified
   visually distinguished outside the popover?

## 5. New brainstorm topics surfaced

- **Search query-log analysis as an analytics feed** — once both Pagefind (§2.1) and Umami
  (§2.5) exist, logged on-site search queries are a direct, low-effort signal for which
  feature/language gaps readers actually want, potentially informing D28's onboarding-order
  decisions (topic 44, coverage analytics) — worth folding into that topic once both pieces ship
  rather than standing alone.
- **OG-image template design as part of brand identity** — §2.4's Satori templates need actual
  visual design (typography, accent color per D10, layout) that properly belongs with topic 31
  (brand identity & launch positioning), not this brainstorm; flagged so the template work isn't
  duplicated across both topics.
- **Per-onboarding-cycle tooling checklist** — §2.3's Shiki-grammar-check and syntax-check-mode
  audit items, alongside brainstorm 34's existing license/spec/Shiki audit, suggest a single
  reusable "new language onboarding checklist" artifact rather than scattering these checks
  across brainstorms 19, 34, and D28 — worth consolidating the next time a language-onboarding
  topic is revisited.

## Sources

- Pagefind (2026). *Pagefind — a fully static search library.* https://pagefind.app/
- Starlight docs (2026). *Site Search.* Astro Starlight documentation — Pagefind as the built-in,
  zero-config default. https://starlight.astro.build/guides/site-search/
- Shiki (2026). *Languages* and project README — grammar sourcing from the community
  `textmate-grammars-themes` project, not maintained by Shiki itself.
  https://shiki.style/languages · https://github.com/shikijs/shiki
- dietcode.io (2026). *Build-time, dynamic OpenGraph images with Astro & Satori.*
  https://dietcode.io/p/astro-og/
- Astro documentation and ecosystem integrations for `astro-og-canvas` (Canvas API/canvaskit-wasm
  based OG image generation, used by Astro's own docs site).
  https://astro.build/integrations?search=images
- OpenPanel Analytics (2026). *Self-Hosted Web Analytics 2026 — Plausible vs Matomo vs Umami vs
  OpenPanel.* https://openpanel.dev/articles/self-hosted-web-analytics
- dasroot.net (2026). *Privacy-Preserving Analytics: Plausible, Umami, GoatCounter.*
  https://dasroot.net/posts/2026/03/privacy-preserving-analytics-plausible-umami-goatcounter/
