# 31 — Brand Identity & Launch Positioning

> Backlog brainstorm for LangAtlas. Scope per the checklist: the wordmark/logo (isogloss-line
> motif), the accent color, the OG-image template's actual visual design, the A2 positioning
> paragraph vs PLDB/Hyperpolyglot, and HN/lobste.rs launch framing. Binding context: D17 (naming —
> **LangAtlas**, WALS pedigree, tagline pattern "LangAtlas — a sourced map of programming-language
> features. Every fact cited.", `langatlas.dev` available and unregistered); D19 (positioning wedge
> vs PLDB/Hyperpolyglot is **the typed concept graph, primarily, plus per-fact sourcing**, in that
> order — the one-paragraph public statement is this topic's job); D10 (Astro, fully static,
> typography-first design in the Stripe/MDN/gwern lineage, one accent color, dark mode, no growth
> chrome); D33 (topic 19 fixed the OG-image *mechanism* — build-time Satori + resvg, two-to-three
> page-kind templates, no runtime service, no citation-count/controversy glyph on the image itself
> to avoid staleness — and explicitly deferred the templates' actual visual design to this topic).
> Also reads brainstorm 23 (naming), which floated a follow-on "brand identity & typography" topic
> and named the isogloss-line motif as "an obvious, ownable visual" once **Isogloss** was still a
> live candidate — the developer chose **LangAtlas** instead (D17), but the isogloss-line visual
> motif survives the name choice on its own merits (WALS pedigree, dialect-boundary-map metaphor)
> and the checklist line for this topic explicitly keeps it. All proposals below are *proposed*,
> not ratified, per the project's decision-hygiene convention.

## 1. Problem framing

Three genuinely different design problems share this topic only because they all gate the same
event — the KB repo (and eventually the site) going public — and none of them can be designed in
isolation from the other two: the positioning paragraph has to fit inside the OG-image templates'
text budget and inside an HN title's character limit; the accent color has to work across the OG
templates, the site's dark mode, and (if a mark exists) the mark itself; the wordmark has to
survive being rasterized into a 1200×630 OG image and a 16×16 favicon at the same time.

The developer constraints that discipline every option here: **solo-maintainable, boring
technology** (CLAUDE.md), **no growth chrome** (D10), and a **public repo from day one** with no
deadline pressure (D11) — so nothing here should require an ongoing design-vendor relationship,
a build step outside the existing Astro/Satori pipeline, or a decision that can't be cheaply
revised later if it turns out wrong. The risk register already names the sharpest version of this
problem as **P1 — differentiation vs PLDB/hyperpolyglot**, with the positioning statement flagged
as still owed; this topic is where P1 finally gets addressed rather than deferred again.

A second, HN/lobste.rs-specific tension runs under the launch-framing sub-problem: this audience
is simultaneously the *best possible* audience for a rigorously sourced, typed-graph reference
project and the *most allergic* audience to anything that reads as "look what AI generated." D1's
own architecture — agents commit directly, no PR gate, admissibility comes from an automated
verification gate — is the single fact about this project most likely to get read either as its
strongest engineering story or as exactly the red flag this audience distrusts, depending entirely
on how it's framed. That tension has to be resolved by this topic's launch-framing section, not
finessed around.

## 2. Options with trade-offs

### 2.1 The A2 positioning paragraph

D19 already fixed the *ordering* (typed concept graph first, per-fact sourcing second) and D17
already validated a tagline *pattern*. What's missing is the actual paragraph, and it has to do
real differentiating work against two specific, real competitors rather than reading as generic
"trust us" copy.

**What PLDB and Hyperpolyglot actually are, stated plainly (so the paragraph can be honest about
the comparison rather than strawmanning either):** PLDB is a large, broad, largely
single-maintainer-curated flat database covering thousands of languages with shallow per-language
fields and minimal inline sourcing — its strength is breadth and structured metadata (file
extensions, first-appeared year, GitHub/StackOverflow signal), not depth or citation density.
Hyperpolyglot is a hand-authored comparison cheat-sheet (a handful of language families,
side-by-side syntax tables) — its strength is fast lookup for someone who already knows one
language and wants another's equivalent idiom, with essentially no sourcing or relationship
modeling at all. Neither models *relationships between features* (requires/enables/conflicts/
influences) as first-class typed data, and neither treats an individual factual claim as an
independently sourced, independently challengeable unit. That's the real gap LangAtlas fills, and
the paragraph should name it precisely rather than vaguely gesturing at "better quality."

**Option A — lead with the graph, land on sourcing, one long paragraph (3 sentences).**

> "LangAtlas maps programming-language features as a typed graph — which features require,
> enable, conflict with, or influence which others, and how each is actually realized in a given
> language — rather than a flat list of trivia. Every fact in that graph is a single sourced claim,
> checked against its cited source by an independent verification pass before it's published, and
> visibly flagged the moment agents or expert reviewers disagree. Where PLDB trades depth for
> breadth and Hyperpolyglot trades sourcing for speed, LangAtlas is narrower on purpose: fewer
> languages, but every relationship typed and every claim traceable to a citation."

This most directly executes D19's stated ordering and is honest about the trade — it doesn't claim
LangAtlas is simply "better," it claims a different, narrower value proposition (depth + typed
structure + citations) against two real alternatives' different strengths (breadth, speed). Risk:
three sentences is already near the ceiling for a homepage hero paragraph and an OG-image
description line simultaneously; some trimming is likely needed per surface (see 2.5).

**Option B — descriptive-first, graph-and-sourcing folded into one sentence, shorter.**

> "LangAtlas is a sourced, typed map of programming-language features — every relationship and
> every fact backed by a citation you can check."

Punchier, fits comfortably in a meta-description and an OG image, but compresses D19's explicit
two-part ordering into a single clause rather than giving the graph claim room to land before the
sourcing claim — loses some of the differentiation specificity against PLDB/Hyperpolyglot by name
(it doesn't reference either, so a reader unfamiliar with those products gets no comparison
context at all).

**Option C — lead with sourcing rigor, graph second** (D19's ordering reversed). Rejected outright
— D19 already ratified the ordering after weighing this exact trade-off (graph primary, sourcing
secondary, because the graph is the harder-to-copy structural moat and the sourcing claim alone
invites "so does everyone who cites sources" skepticism if led with). Reversing it here would
relitigate a settled decision without new information.

**Recommendation: Option A as the canonical "about" / homepage-hero statement, with Option B as
the compressed derivative** used specifically where character budget is tight (meta description,
OG image, HN one-liner) — one long-form paragraph plus one short-form derivative, not two
competing statements. D17's existing tagline ("LangAtlas — a sourced map of programming-language
features. Every fact cited.") survives as the even-shorter title-tag-length version underneath
both — three nested lengths for three different surfaces, all saying the same two things in the
same order.

### 2.2 HN/lobste.rs launch framing

The honest starting point: **the "agents wrote this" fact should be in the title or the first two
sentences, not discovered by a commenter three replies in.** Burying it reads as either naive (not
realizing it's the first question) or evasive (hoping nobody asks) — both worse than leading with
it on a forum that reflexively distrusts unstated AI provenance and rewards projects that show
their work. The framing question isn't *whether* to disclose, it's *what specifically* to lead
with about the disclosure, because "AI agents wrote this" and "AI agents wrote this, but nothing
gets published without a machine-checked citation" are read completely differently by this
audience — the second sentence is the entire pitch, not a caveat on the first.

**Option A — lead with the AI-agent angle as the hook.** Title like "Show HN: I built an AI agent
pipeline that can't publish a fact without a citation to back it." Pro: maximally honest, and
frames the *interesting engineering problem* (verification-gated autonomous publishing with no
human merge gate) as the headline rather than a footnote — HN specifically rewards "here's the
hard problem I solved" framing over "here's a product." Con: risks the discussion becoming
entirely about AI-content skepticism in the comments rather than about the knowledge base itself,
especially if the title reads as AI-boosterism before the citation-rigor payoff lands.

**Option B — lead with the domain/graph, disclose the pipeline prominently in the opening
paragraph but not the title.** Title like "Show HN: LangAtlas – a sourced, typed graph of
programming-language features." Body opens: "The catalog is built by AI agents against a
machine-verified citation gate — no fact is committed unless an independent check confirms the
cited source actually supports it. [one or two sentences on why that's a real constraint, not a
disclaimer]." Pro: leads with the thing HN can independently evaluate (the graph, the citations,
whether the facts are actually right) before asking anyone to trust a claim about the pipeline;
the AI-agent framing arrives immediately, in the reader's own time, rather than being the first
word they see. Con: a sliver of readers who'd have appreciated the direct engineering-problem hook
of Option A won't get it from the title alone.

**Option C — omit or minimize the AI-agent framing, foreground only sourcing/graph.** Rejected —
this is the one option genuinely inconsistent with the project's own architecture (D1's no-PR-gate
posture is a headline decision, not an implementation detail) and the one most likely to backfire
if discovered rather than disclosed; HN's own norms treat undisclosed AI generation as worse than
disclosed AI generation with real safeguards, even among skeptics.

**Recommendation: Option B.** Title foregrounds the graph and the sourcing claim (the two things
D19 already ordered as the differentiators), because those are independently checkable by any
reader who clicks through — "is this fact actually cited, is the citation real, does it say what
the claim says" is a five-minute verification any HN reader can do themselves, which is a much
stronger trust-building move than asserting trustworthiness in the title. The AI-pipeline
disclosure moves to the first or second sentence of the body, framed as the mechanism that makes
the sourcing claim credible rather than as a separate announcement — concretely: *"Every fact is
committed by an AI agent, but none of them can commit a fact without a citation, and an
independent verification pass checks that the citation actually supports the claim before it goes
in — there's no human review step, the citation check is the review step."* That sentence does
double duty: it answers the "wait, no human checks this?" objection before it's asked, and it
turns the no-PR-gate architecture (D1) from a liability into the most interesting technical claim
in the post.

**A suggested opening paragraph, concretely:**

> "LangAtlas is a sourced, typed graph of programming-language features — which features require,
> enable, conflict with, or influence which others, and how each shows up in a given language,
> with every individual fact traced to a citation. It's built by AI agents, but none of them can
> commit a fact without a source, and an independent verification pass checks that the cited
> source text actually supports the claim before anything is published — there's no human review
> gate, the citation check *is* the gate. I'm not trying to hide that AI wrote most of the prose;
> I'm trying to make sure nothing gets published that isn't actually backed by a real, checkable
> source, which is a different and I'd argue harder bar than either PLDB or Hyperpolyglot set for
> themselves."

**lobste.rs framing differs in one respect.** lobste.rs skews more toward PL-theory-literate
readers and has a `programming-languages` and `databases` tag surface where this project's typed
graph and ontology-versioning design (D16) would land well as *technical* content independent of
the AI-provenance question — the same disclosure sentence still belongs up front (lobste.rs is no
less allergic to undisclosed AI content than HN, arguably more given its smaller, more
engineering-dense community), but the framing can afford to spend relatively more of the post on
the ontology/versioning design and relatively less on pre-empting AI skepticism, since the typed
graph itself is the kind of thing that community self-selects for interest in.

### 2.3 Wordmark/logo direction

**The isogloss-line motif, made concrete.** An isogloss is the boundary line drawn on a dialect
map marking where a linguistic feature is/isn't present — visually, on real dialectology maps,
this is a single, often gently undulating contour line, sometimes with a small tick or hatch
marking which side has the feature, frequently drawn in a single ink color against a plain
background. That's a genuinely simple, geometric primitive: **one or a small number of open,
mildly wavy line paths**, not a pictorial illustration of anything (no globe, no book, no
brain-and-circuit-board cliché). It is buildable as plain SVG — a hand-tuned cubic Bézier path or
two, not a commissioned illustration — which matters directly for the "solo-maintainable, boring
technology" constraint: this is a shape a developer can iterate on in a text editor and version in
git alongside the rest of the repo, not an asset that requires re-engaging a designer for every
refinement.

**Option A — wordmark only, no icon, from day one.** "LangAtlas" set in a distinctive but standard
typeface (a well-chosen open-source geometric or humanist sans — e.g. something in the Inter/
Söhne/IBM Plex family already common in the Stripe/MDN/gwern lineage D10 cites), no accompanying
mark at all. The favicon is a monogram or the bare wordmark's initial letterform on a solid accent
background. Pro: zero design risk, zero asset-maintenance burden, ships literally today with a
`<title>` and a CSS font stack — matches D14's existing "text-only language names, no logos"
precedent (a different context — trademark risk on third-party language logos — but the same
underlying "we default to typography, not iconography" instinct already present in this project's
license work). Con: no ownable visual mark at all going into the HN/lobste.rs launch, which is
exactly the moment a distinctive mark has the most one-time value (social-preview thumbnails,
being recognizable across repeat mentions).

**Option B — a simple geometric isogloss-line SVG mark alongside the wordmark, built (not
commissioned), from day one.** Two or three overlapping open contour lines (parametrically
generated — e.g. a fixed sine/Bézier formula with a small phase offset between lines, so the mark
is reproducible from a short script rather than freehand-drawn) in the single accent color,
sitting to the left of or above the wordmark. At favicon size (16×16), a mark this simple survives
legibility better than most illustrative logos would — a bold single or double curved line reduces
gracefully, the way a minus-sign-adjacent glyph or a single accent stroke does, whereas anything
with more than two or three line-weights or any fine detail (hatching, ticks) reads as mud at
16px and should be dropped from the favicon variant even if present in the full-size mark. Pro:
genuinely on-brand (WALS/dialect-map pedigree, D17), cheap to build (a script, not a commission),
gives the launch something visually distinctive to anchor OG images and repeat mentions around.
Con: real, if small, design-iteration time before launch; a first attempt at a geometric line mark
can easily read as "random squiggle" rather than "isogloss" without a few rounds of refinement
against an actual dialect-map reference, and a bad mark is worse than no mark for a launch
first-impression.

**Option C — commission a custom-drawn logo from a professional designer.** Rejected outright
against the "boring, solo-maintainable technology" constraint and the "no cash budget" developer
constraint (CLAUDE.md) — this is a solo hobby project with no deadline pressure and no marketing
budget; a commissioned mark also becomes an asset only the original designer can cleanly revise,
which is the opposite of solo-maintainable. Nothing about this project's positioning (technical
rigor, sourcing discipline, typed graph) benefits from professional illustration polish the way a
consumer product's brand might.

**Recommendation: Option A for the actual launch, Option B as a fast-follow once there's slack to
iterate on the mark properly.** Do not let the isogloss-mark's design-iteration risk block or
delay the HN/lobste.rs launch — a clean wordmark plus the accent color (2.4) plus well-designed OG
images (2.5) is already a coherent, professional-reading brand presence with zero mark-legibility
risk. Build the parametric line-mark script as a small, revisitable side task afterward (a single
SVG-path-generating script under, e.g., `assets/brand/`, checked into the repo like everything
else per D1's git-is-the-source-of-truth posture) and swap it into the favicon/header/OG templates
once it's actually good, rather than shipping a rushed first attempt under launch-day time
pressure. This is explicitly reversible either direction: if the wordmark-only look still feels
sufficient once the mark exists, keep both in reserve and ship whichever tests better on an actual
rendered favicon.

### 2.4 Accent color

D10 already committed to exactly one accent color plus dark mode; this sub-problem is narrower
than a full palette — pick the one hue and confirm it reads correctly in both themes.

**Candidate families, screened against the isogloss/atlas metaphor and the
Stripe/MDN/gwern typography-first lineage:**

- **Indigo/violet-blue** (Stripe's own family, also broadly "trustworthy tech" default). Pro:
  extremely safe, high familiarity, easy to source an accessible dark-mode variant (well-trodden
  design-system territory). Con: generic — this is the single most common SaaS accent color choice
  in 2026, and D10's own "opposite of Amazon"/distinctive-typography-first framing argues for a
  color that doesn't read as "yet another dev-tool blue." Also risks reinforcing the LangChain
  "Lang*"-prefix confusion D17 already flagged as a naming risk (LangChain's own brand also leans
  blue/violet).
- **Warm amber/ochre/terracotta.** Pro: this is the actual ink color used for contour lines and
  isoglosses on real topographic and dialectology maps (brown/orange contour-line conventions
  predate and are independent of any tech-brand association), so it's the one candidate that
  directly reinforces the atlas/map metaphor rather than sitting beside it; distinctive against
  the sea of tech-blue competitors; warm ambers read well against both a light cream/paper
  background (reinforcing the "atlas/map" print-cartography feel) and a dark near-black background
  (ambers glow rather than clash in dark mode, unlike cooler hues that can look sickly against
  near-black). Con: amber-family accents skew slightly toward "warning/caution" color association
  in some UI conventions (a solvable problem — the site never uses the accent color for actual
  status/warning semantics, per D33's separate single-glyph trust-signal design, so no clash
  actually occurs in practice, but worth naming as a reason a rushed implementation could
  accidentally create confusion if the accent color and a future status glyph were ever drawn from
  the same hue family).
- **Deep forest/moss green.** Pro: also a legitimate map-convention color (vegetation/terrain
  green), reads calm and "reference-book" rather than "product." Con: green accents skew toward
  either "success/confirmed" status semantics (same caution-color-collision risk as amber, in
  reverse) or environmental/sustainability branding associations that have nothing to do with this
  project; less distinctively tied to the isogloss-line motif specifically than amber's direct
  contour-line-ink connection.

**Recommendation: warm amber/ochre** (a concrete starting point: something in the `#B5540A`–
`#C9691A` range for light-mode text/accent use, shifted to a brighter, higher-luminance
`#E8A33D`–`#F0AE4A`-range variant for dark mode to maintain WCAG AA contrast against a near-black
background — exact hex values are an implementation-time contrast-audit task, not a decision to
lock here). This is a single accent hue with a light/dark luminance adjustment, which is standard
practice and does not violate D10's "one accent color" rule (the color identity stays one named
hue; only its lightness shifts per theme, exactly like how a single brand blue is typically
lightened for dark-mode use across any professionally executed dark-mode implementation). Ties
directly to the isogloss/atlas metaphor (real contour-line ink color), avoids the LangChain-blue
association risk D17 already flagged, and is distinctive against the dev-tool-blue default without
reading as an unusual or hard-to-pair choice.

### 2.5 OG-image template visual design

D33 fixed the mechanism (Satori + resvg, build-time only, two-to-three page-kind templates,
1200×630, pulled straight from the structured data layer, explicitly **no citation-count/
controversy glyph** to avoid staleness between a static image and a live page) and explicitly
deferred the actual layout to this topic. Four page kinds actually need distinct treatment given
the site's IA (D10): homepage, feature page, language page, and comparison page — the
recommendation below treats "feature" and "language" as one shared template with swapped content
(same layout skeleton, different headline/subhead source fields) since both are single-entity
detail pages, while comparison genuinely needs a different two-column skeleton, keeping D33's
"two-to-three templates" count.

**Shared visual language across all templates**, set once and reused: the accent color (2.4) used
sparingly — as a single thin rule/underline beneath the headline and as the color of a small
isogloss-line mark (2.3, once it exists — or omitted cleanly if the wordmark-only phase is still
current at whatever point OG generation ships) in a corner, never as a filled background block
(matching D10's typography-first, no-growth-chrome restraint — the image should read like a page
of a well-typeset reference book, not a marketing card); a warm off-white/cream background in
light-mode-equivalent images (OG images are generated once per page, not theme-aware, so pick one
consistent background — a warm paper-white reinforces the atlas/reference-book feel better than a
stark white or a dark card, and avoids the "everything is a dark-mode gradient" genre-default look
common to build-time OG images in 2026); the "LangAtlas" wordmark set small, bottom-left, in the
same typeface as the site body; a one-line descriptive tag (2.1's Option B compressed statement,
or a page-kind-specific equivalent) set small, bottom-right or directly under the wordmark.

**Feature/language template.** Large headline = the feature or language name, set in the site's
primary heading typeface at a size that dominates the frame (this is the one piece of information
a social-preview thumbnail most needs to convey instantly). One short subhead line beneath it:
for a feature page, its one-line pedagogical description (already authored per D2's Concept/
Feature model); for a language page, a short descriptor drawn from the language registry (e.g.
"systems language" / "functional language" — whatever short classification field already exists
or is cheap to add) rather than any numeric count (avoiding exactly the staleness risk D33 already
flagged for citation counts, generalized to any live-changing number). No badge, no icon
representing verification/controversy status, matching D33's explicit ratified omission.

**Comparison template** (only generated once comparison pages exist above D10's data-richness
threshold). Two-column skeleton: the two language names as twin headlines split left/right with a
visible vertical divider rule in the accent color down the center — a deliberate echo of the
isogloss metaphor at the page-content level (a comparison page *is* an isogloss crossing, per
brainstorm 23's own framing: "two isoglosses crossing"), giving the comparison template a reason
to look structurally different from the single-entity template beyond mere content difference. No
"winner" framing on the image itself (matches D10's non-growth-chrome, non-clickbait posture) —
just the two names and the feature/dimension being compared as a small centered label between
them (e.g. "pattern matching" between "Rust" and "Haskell").

**Homepage template.** The tagline (D17's exact wording, or 2.1's short-form derivative) set large
and centered, with the wordmark above it rather than in the corner (the one template where the
brand name itself is the headline, since there's no entity name to lead with) — the isogloss mark,
once built, gets its most prominent single placement here, as a small decorative element near the
tagline rather than a corner watermark.

**Recommendation:** three templates (feature/language shared, comparison, homepage), built as
described, all pulling directly from the same structured data Astro already reads for the page
itself (no new data dependency), consistent with D33's "pure build-time cost, no new runtime
service" framing. Ship with the wordmark-only brand identity (2.3 Option A) at launch — the
templates degrade gracefully with just the wordmark in the corner and no mark — and simply add the
isogloss-line mark into the reserved corner/tagline slot once 2.3's fast-follow lands, with no
template restructuring needed at that point.

## 3. Recommendation (*proposed*)

1. **§2.1 — positioning paragraph**: adopt the three-sentence Option A statement as the canonical
   about/homepage-hero paragraph (graph first, sourcing second, per D19), with the shorter Option
   B sentence as its compressed derivative for meta descriptions, OG images, and any other
   character-constrained surface; D17's existing tagline stays the shortest form underneath both.
2. **§2.2 — launch framing**: Option B for both HN and lobste.rs — title foregrounds the typed
   graph and sourcing claim (independently checkable by any reader), the AI-agent-pipeline
   disclosure moves to the first or second sentence of the body, framed as the mechanism that
   makes the sourcing claim credible ("the citation check *is* the review step") rather than as a
   separate announcement to brace for. lobste.rs framing shifts emphasis toward the ontology/
   typed-graph/versioning design given that community's PL-theory density, keeping the same
   disclosure-up-front structure.
3. **§2.3 — wordmark/logo**: ship Option A (wordmark only, no icon, standard open-source geometric/
   humanist sans, monogram favicon) for the actual launch; build the parametric isogloss-line SVG
   mark (Option B) as a fast-follow once there's time to iterate on it properly, checked into the
   repo as a small reproducible script rather than a one-off commissioned asset (Option C rejected
   outright — inconsistent with the solo-maintainable, no-cash-budget constraints).
4. **§2.4 — accent color**: warm amber/ochre as the single accent hue (concrete starting range
   given, exact hex values an implementation-time contrast-audit task), with a brighter dark-mode
   luminance variant of the same hue — chosen for its direct tie to real contour-line/isogloss map
   conventions, its distinctiveness against the dev-tool-blue default, and its avoidance of the
   LangChain-blue association risk D17 already flagged.
5. **§2.5 — OG-image templates**: three templates (feature/language shared skeleton, comparison,
   homepage) built on a shared warm-paper visual language (thin accent-color rule, small corner
   mark once it exists, bottom-corner wordmark + tag line), no live-changing numbers or status
   glyphs on any template (extending D33's citation-count-glyph omission to every numeric field),
   comparison template's two-column divider deliberately echoing the isogloss-crossing metaphor.

## 4. Open questions for the developer

1. **§2.1** — adopt the three-sentence Option A statement as written, or does the wording need a
   pass (tone, exact phrasing of the PLDB/Hyperpolyglot comparison) before it's usable verbatim on
   the site and in launch posts?
2. **§2.2** — confirm Option B's title-vs-body split (graph/sourcing in the title, AI-pipeline
   disclosure in the opening body sentence) over Option A's more direct "I built an AI agent
   pipeline..." title-first framing — is the more conservative disclosure placement the right call,
   or does the developer want to lead harder with the pipeline-engineering angle?
3. **§2.3** — is a wordmark-only launch (no icon at all) acceptable for the actual HN/lobste.rs
   launch, deferring the isogloss-line mark to a fast-follow, or does the developer want the mark
   built and tested before launch even at the cost of some delay?
4. **§2.4** — confirm warm amber/ochre as the accent-color direction, or would the developer prefer
   a different candidate family (indigo/blue for safety, forest green for the alternate map-
   convention option) run through the same screening?
5. **§2.5** — should feature/language OG templates omit numeric fields entirely (as recommended,
   generalizing D33's citation-count-glyph omission), or is a build-time-only, clearly-labeled
   count (e.g. "swept as of data-vN") an acceptable inclusion given the site already displays its
   `data-vN` build stamp (D13) elsewhere, making a similarly-stamped number less of a staleness risk
   than an unstamped one?
6. **Timing** — does this topic's launch-readiness work (positioning paragraph finalized, HN/
   lobste.rs post drafted, wordmark shipped) become the trigger for finally registering
   `langatlas.dev` and confirming the `langatlas` GitHub org (the one item still sitting in
   open-questions.md's deferred section since D17), or should domain/org registration happen
   independently and earlier, not gated on this topic's completion?

## 5. New brainstorm topics surfaced

- **Brand asset repository & style-guide artifact** — once the wordmark (and later the isogloss
  mark) exist as real SVG/font-stack decisions, a small concrete question follows: where do the
  actual asset files live (a `assets/brand/` directory in `langatlas-kb`, a dedicated location in
  `langatlas-site`, or duplicated in both), and does a one-page internal style-guide artifact
  (accent-color hex values, type stack, mark-usage rules) get written down anywhere, or does it
  stay tribal knowledge in this brainstorm file. Small enough that it likely doesn't need its own
  full brainstorm — flagged here so it isn't lost, probably resolved as a short implementation-time
  note rather than a dedicated topic.
- **Concrete typeface selection for the site body/heading stack** — D10 committed to a
  "typography-first, Stripe/MDN/gwern lineage" design direction and this topic assumed "a
  well-chosen open-source geometric or humanist sans" for the wordmark without naming one; the
  actual site-wide type-stack decision (heading face, body face, monospace face for code/citations,
  self-hosted vs system-font-stack trade-off) is real design work this topic deliberately didn't
  do, since it's a full-site decision rather than a brand-identity one. Worth folding into whichever
  future website-implementation pass actually builds the Astro theme, rather than a standalone
  backlog topic.
