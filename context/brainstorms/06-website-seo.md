# 06 — Website & SEO Architecture

> Brainstorm output for Project Hermes. Scope: framework choice, build pipeline, URL/information
> architecture for programmatic SEO, structured data, per-fact citation rendering, the
> "challenge this fact" affordance, and design direction. Source of truth: `context/input-brief.md`.

## Problem framing

The site is the human-facing surface of the knowledge base (brief §1 Modules, §2.6). Its defining
tensions:

1. **SEO-heavy + data-driven.** Thousands of pages (features × languages × comparisons) are
   *generated from structured data*, not hand-written prose. This is programmatic SEO: the value
   per page must be high enough that Google doesn't classify it as thin/doorway content.
2. **Mostly static, but with islands.** Knowledge-base pages are read-only and cacheable forever
   (until a fact changes). The later language builder and selector are genuinely interactive —
   but they are *islands*, not a reason to ship a full SPA runtime to every KB page.
3. **Facts change asynchronously.** AI agents add/revise facts on their own schedule (brief §2.4).
   The pipeline must support cheap incremental rebuilds — rebuilding 5,000 pages because one
   syntax snippet changed is unacceptable for a solo dev's CI minutes and iteration speed.
4. **Every fact is cited and challengeable** (brief §2.1, §2.5, §1 "extremely easy and visible
   contribution options") — but the design must stay clean ("opposite of Amazon"). Citations and
   challenge affordances must be *present everywhere yet visually quiet*.
5. **Solo dev, PoC MVP** (brief §2.7). One framework, one deployment target, minimal moving parts.

Non-goals restated from the brief: the site is *not* an information source for AI agents (no need
to optimize for LLM scraping), and it is not a wiki (no user-editable pages in-app; challenges go
through GitHub or a forum module — see brainstorm topic for module 05/challenge workflow).

## Options with trade-offs

### A. Framework

| Option | Pros | Cons |
|---|---|---|
| **Astro** | Zero-JS-by-default → best-in-class Core Web Vitals for free; islands architecture is literally the framework's core model (builder = one `client:visible` island in any UI lib, or vanilla); Content Layer API loads data from *any* source (DB, JSON, remote API) at build time; first-class MD/MDX for essay-style feature explanations; small API surface for a solo dev | Weakest story for a future heavily-dynamic app (builder with accounts, comments, votes) — server endpoints exist (Astro actions, SSR adapter) but the ecosystem for full-app patterns is thinner than Next's |
| **Next.js (App Router)** | ISR (incremental static regeneration) is the most mature incremental-rebuild story — `revalidatePath('/languages/rust')` when an agent commits a fact; strongest ecosystem if builder/library/accounts grow into a real app; one codebase from KB to app | Ships a React runtime on every page — fighting the framework to get Astro-level lightness on static KB pages; App Router complexity tax is real for a solo dev; Vercel-shaped (self-hosting ISR is doable but fiddly) |
| **SvelteKit** | Pleasant DX; small bundles; prerender + islands-ish patterns possible | Prerendering thousands of data-driven routes is less ergonomic than Astro's `getStaticPaths`/content collections; no ISR equivalent as polished as Next; smaller ecosystem — you'd pick it for love of Svelte, not for this workload |
| **Pure SSG (Hugo/Eleventy)** | Fastest builds (Hugo renders 10k pages in seconds — full rebuilds so cheap that "incremental" stops mattering); dead simple hosting | Interactive islands are entirely DIY (separate bundler, manual mounting); templating a typed feature graph in Go templates or Nunjucks is painful vs. real components; the builder would effectively be a second project |

### B. Build pipeline: build-from-git-files vs build-from-database

This interacts with the challengeability decision (brief §2.5a vs §2.5b):

- **Git-files as source of truth (§2.5a).** Facts live as YAML/JSON files in a repo; agents commit
  via PRs; site builds from the checked-out files (Astro content collections natively, or a small
  loader). Pros: the site build is trivially reproducible, every fact has a commit + PR + GitHub
  discussion URL for free (feeding both citation links and the challenge affordance), rebuild
  trigger is just "push → CI". Cons: the vector DB / relational DB must be *derived* from the
  files (sync job on merge); very large fact counts strain git ergonomics (though text facts are
  tiny — 100k facts of ~1 KB is a 100 MB repo, fine).
- **Database as source of truth (§2.5b).** Agents write to Postgres/vector DB; site build queries
  the DB (Astro Content Layer loader, or Next fetch + ISR). Pros: no file/DB sync problem; natural
  fit if the forum/challenge module lives in-app. Cons: builds now depend on a live service;
  reproducibility and history require your own audit tables; "source code link for every bit of
  info" (brief §1) becomes something you must build rather than something GitHub gives you.
- **Hybrid (likely best):** git files are canonical for *facts and citations*; DB is derived
  (embeddings for RAG, aggregates like upvotes/usage-rate). Volatile data (vote counts, builder
  usage stats) is fetched client-side into a tiny island or injected at the edge, so fact edits —
  not vote ticks — are the only rebuild trigger.

**Incremental rebuilds when agents add facts:** with git-files + CI, the diff tells you exactly
which entities changed. Options: (1) accept full rebuilds if under ~2 min (Astro on a few thousand
pages typically is; measure before optimizing); (2) Astro's incremental content caching + a CI
cache; (3) Next ISR with on-demand revalidation webhooks from the merge event — the most surgical,
at the cost of running a server. For MVP scale, (1) is honestly fine.

### C. URL / information architecture (programmatic SEO)

Target long-tail queries people actually type: "does rust have pattern matching",
"pattern matching rust vs haskell", "languages with algebraic data types".

Proposed IA (flat, guessable, hackable URLs — every prefix is a real page):

```
/features/                          feature index, grouped by layer (syntax / semantic / design-choice)
/features/pattern-matching/         concept page: definition, quality impacts, related features, language support matrix
/features/pattern-matching/rust/    feature-instance page: syntax preview, semantics notes, citations
/features/pattern-matching/rust-vs-haskell/   comparison page (canonical: alphabetical order, redirect the reverse)
/languages/                         language index (+ stats: TIOBE etc.)
/languages/rust/                    language detail: structured feature view with syntax previews
/languages/rust-vs-go/              whole-language comparison (later; only if it can be non-thin)
/concepts/higher-order-programming/ optional layer above features, mirroring the brief's concept/feature split
/build/                             language builder (interactive island; noindex the configurator state, index a landing page)
/library/<slug>/                    public built-language submissions (indexable, user-generated — moderate before indexing)
/select/                            language selector (indexable landing + interactive island)
```

Programmatic-SEO guardrails:

- **Comparison pages are the SEO goldmine** (features × language-pairs is combinatorially huge) and
  the thin-content risk. Generate only pairs where *both* languages have substantive data
  (e.g. ≥ N facts each, differing type/values); otherwise link but `noindex` or don't generate.
  Canonicalize A-vs-B with alphabetical slugs.
- Every generated page needs unique `<title>`/`<meta description>` templated from the data, an
  actual data-derived difference summary (not just two columns), breadcrumbs, and cross-links
  along graph edges (requires/enables/alternative-to → related-pages sections = internal linking
  structure Google loves, for free from the typed graph).
- Sitemap.xml generated from the same data; segment it (features / languages / comparisons) so
  Search Console shows which class of page is being indexed.
- Slugs are permanent identifiers — decide slug policy (kebab-case of canonical feature name) once,
  early; renames get 301s.

### D. Structured data (schema.org)

There is no schema.org type for "programming language feature", so compose from what exists:

- `TechArticle` or `Article` on feature and comparison pages (headline, dateModified from the
  fact's last commit — genuinely accurate freshness signals).
- `ComputerLanguage` (a real schema.org type) on `/languages/<x>/`, with `sameAs` links to
  Wikidata (the brief already cites Wikidata Q-IDs — reuse them) — cheap knowledge-graph
  entity reconciliation.
- `SoftwareSourceCode` with `programmingLanguage` for syntax previews.
- `citation` property (on Article/TechArticle) pointing at `CreativeWork`/`ScholarlyArticle`
  nodes generated from the .bib-style structured source records (brief §2.1) — the citation
  pipeline feeds JSON-LD directly.
- `BreadcrumbList` everywhere; `FAQPage` sparingly and only for genuine Q&A content (Google has
  restricted FAQ rich results — don't build strategy on it).
- Emit as JSON-LD in `<head>`, generated by one shared helper from the same structured records
  that render the page — never hand-maintained.

### E. Rendering per-fact citations without clutter

Options considered:

1. **Inline bracketed numbers `[3]` Wikipedia-style** — familiar but visually noisy at
   fact-density this high (nearly every line is a fact); exactly the clutter to avoid.
2. **Footnote popovers (recommended):** each cited fact gets a small, muted superscript marker or
   a subtle dotted underline; hover/tap opens a popover with formatted citation (from the .bib
   record), link to the source, link to the fact's file/commit on GitHub, and the challenge
   action. Progressive enhancement: with no JS, markers anchor-link to a per-page references
   section (which should exist anyway — it's crawlable citation content and a schema.org
   `citation` mirror). The native Popover API + CSS anchor positioning make this nearly free
   in 2026 (check `modern-web-guidance` skill when implementing).
3. **Per-section sidenotes** (Tufte-style, in the margin on wide screens, collapsing to popovers
   on narrow) — the most elegant for essay-like concept pages; overkill for dense tables.
4. **Row-level "sources" affordance** for tabular views (feature matrices, comparisons): one quiet
   icon per row opening the popover listing all citations for that row — per-cell markers in a
   matrix would be unreadable.

Likely blend: dotted-underline + popover for prose facts, row-level popovers for tables,
sidenotes as a nice-to-have on concept pages, references section always rendered at page bottom.

### F. "Challenge this fact" affordance

- **Placement: inside the citation popover** as the second row — "Challenge this fact" next to
  "View source". This unifies "where did this come from" and "I disagree" into one quiet entry
  point, keeping page chrome clean while satisfying "extremely easy and visible contribution"
  via *ubiquity* (every fact has it) rather than *loudness*.
- Plus one page-level affordance: a small footer/header block per page — "Something wrong on this
  page? Discuss on GitHub · Contribution guide" — covering people who don't discover popovers,
  and hosting the per-feature/per-language GitHub discussion link the brief mandates.
- Target of the challenge link (depends on §2.5 decision): with git-files-canonical, deep-link to
  a prefilled GitHub issue/discussion (`?title=Challenge: <fact-id>&body=<fact text + source>`)
  or directly to the YAML line on GitHub. With an in-app forum, link to the fact's thread. The
  affordance design is identical either way — only the href changes, so this doesn't block the
  §2.5 decision.
- Each fact needs a **stable fact ID** surfaced in the DOM (`data-fact-id`) so challenges,
  citations, GitHub links, and the RAG store all key off the same identifier. This is a data-model
  requirement to feed back to the knowledge-base schema brainstorm.

### G. Design direction

Typography-first reference-site aesthetic. Exemplars to study:

- **Stripe docs** and **MDN** — dense technical reference that still feels calm; MDN's
  browser-compat tables are the closest existing pattern to a feature-support matrix.
- **caniuse.com** — support-matrix UX (the "does X have Y" interaction), though its visual design
  is dated; steal the model, not the skin.
- **Rust Book / mdBook** and **gwern.net** — long-form typographic restraint; gwern for
  sidenotes/popover citations done seriously.
- **Practical Typography (Butterick)** — the typography-first north star.
- **learnxinyminutes.com** — syntax-preview density done minimally.
- **PCPartPicker** itself — for the builder module's list/compatibility UX (the brief's explicit
  analogy), reskinned to the site's aesthetic.

Concrete direction: one excellent text face + one monospace for syntax (system stack or one
self-hosted variable font — also a CWV win); generous whitespace and a strict type scale; muted
neutral palette with one accent; syntax previews as first-class, beautifully highlighted blocks
(server-side highlighting at build time — e.g. Shiki — zero client JS); graph relationships
rendered as quiet tag-chips ("requires ownership", "alternative to GC") rather than heavy
diagrams; dark mode from day one (developer audience). No ads, no cookie-wall, no newsletter
modals — the anti-Amazon stance is itself the brand.

## Recommendation

- **Astro**, statically generated, deployed to static-first hosting (Cloudflare Pages / Netlify /
  GitHub Pages). It is the best-fit tool for "mostly static, SEO-heavy, data-driven, islands of
  interactivity, solo dev": zero-JS KB pages by default, content collections/Content Layer for the
  fact data, and the builder as a lazily-hydrated island later (UI library chosen then; Astro is
  agnostic). Revisit only if the builder/library/accounts side grows into a real app — and even
  then, Astro SSR endpoints or a small separate API service likely suffice before a Next rewrite
  would.
- **Hybrid pipeline, git-files canonical:** facts + citations in the repo, site builds from the
  checkout in CI on merge; vector DB and aggregates derived. Accept full rebuilds for MVP; add
  incremental caching only when build time actually hurts.
- **IA as sketched in section C**, with the thin-content guardrails: generate comparison pages
  only above a data-richness threshold, canonical alphabetical pair slugs, internal links derived
  from graph edges, stable slugs with 301 policy.
- **JSON-LD from the data layer:** TechArticle + ComputerLanguage (+ Wikidata `sameAs`) +
  SoftwareSourceCode + citation → CreativeWork, emitted by one shared helper.
- **Citations as quiet popovers** (native Popover API) with a no-JS references-section fallback;
  row-level source popovers in tables; **"Challenge this fact" lives inside the popover** plus a
  per-page GitHub-discussion footer link; every fact carries a stable `data-fact-id`.
- **Design:** typography-first, Stripe/MDN/gwern lineage, build-time syntax highlighting, one
  accent color, dark mode, zero growth-hacking chrome.

## Open questions for the owner

1. **Domain & naming** — nothing in the brief names the product/domain; slugs, canonical URLs, and
   branding all hang off this. Any candidates?
2. **Comparison-page scope for MVP:** feature-scoped comparisons only
   (`/features/x/a-vs-b`), or also whole-language `/languages/a-vs-b`? The latter is a bigger SEO
   prize but much harder to keep non-thin.
3. **Where do challenges land** (GitHub prefilled issue/discussion vs in-app forum)? The popover
   affordance works with either, but the choice decides whether the site stays fully static.
4. **How volatile are upvotes/usage-rate rankings** (brief §1: "ranked by upvotes + usage rate")?
   If they must be near-live on KB pages, that forces a small client-side data island or
   edge-injection; if daily-refresh is fine, they can bake into the build.
5. **i18n:** English-only for MVP? (Programmatic SEO × languages multiplies everything; recommend
   explicitly deferring, but it should be a decision, not an accident.)
6. **Indexing user-generated `/library/` submissions:** index publicly (SEO upside, spam/quality
   risk) or noindex until a moderation story exists?
7. **Is a `/concepts/` layer wanted as separate pages**, or are concepts just grouping metadata on
   feature pages? The brief's terminology distinguishes them; the IA can go either way.

## New brainstorm topics surfaced

- **Stable identifier scheme** for facts/features/languages (slugs + fact IDs shared by site,
  RAG store, GitHub files, and challenge links) — belongs with the knowledge-base schema topic.
- **Syntax-preview pipeline:** where snippets live, how they're validated (do agents compile/run
  them?), highlighting grammar coverage for exotic languages (Shiki/TextMate grammar gaps).
- **Search on-site:** static search (Pagefind) vs API-backed — cheap with Pagefind on a static
  Astro site; worth a small dedicated decision.
- **Analytics & SEO feedback loop** without cookie banners (privacy-first analytics, Search
  Console monitoring of the programmatic page classes) — informs which page types to invest in.
- **Feature-support matrix UX** as its own design problem (caniuse/MDN-compat-table hybrid over a
  typed graph, with per-row citations) — likely the site's signature component.
- **Open-graph/social card generation** for programmatic pages (build-time OG images per
  feature/language/comparison) — cheap distribution win, fits the same build pipeline.
