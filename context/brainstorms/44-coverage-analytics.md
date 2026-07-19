# 44 — Coverage Analytics

> Backlog brainstorm for LangAtlas. Scope (checklist item 44): research-phase coverage dossier
> tooling (topic 25's exit criteria, O6) + post-sweep coverage-gap analytics (`<2` corroborating
> instances per dimension value) driving language-onboarding order + on-site search query logs
> (topic 19, once Pagefind + Umami both exist) as a signal for reader-wanted gaps. Binding
> context: `context/decisions.md` D27 (R0–R6 research-phase structure, the O6 dossier's six
> items), D28 (14-language phased onboarding, D34's own forward pointer: "prioritization past the
> curated 15 should draw on coverage-gap analytics (topic 44)"), D33 (Pagefind default search,
> self-hosted Umami post-launch, private-only), D38 (ontology change tooling's blast-radius script
> and tombstone/redirect machinery), D41 (the `tools/observability/report.py` CLI pattern: no
> dashboard, subcommand-based reporting over existing logs, ephemeral markdown output), D46
> (questionnaire compiler's `tools/questionnaire/` shape), D48 (validator CLI's `tools/validate/`
> shape), D49 (the `no-record` reason enum: `not-yet-onboarded | not-yet-swept | deferred |
> not-applicable`, and the `aliases: []` feature field). Direct inputs: brainstorm 25 (R0–R6
> design + O6 dossier definition), brainstorm 34 (14-language selection + its own forward
> pointer to this topic), brainstorm 19 (the `/coverage/` page's pre-baked static views and the
> search-query-log signal it explicitly deferred here). All proposals below are *proposed* until
> the developer ratifies.

## Problem framing

Three genuinely different questions have been filed under one checklist number, at three
different points in the project's own calendar, over three different data sources:

1. **The research-phase exit dossier** (brainstorm 25 §O6) — computed each R6 consolidation
   cycle, entirely **pre-1.0.0**, over ontology data plus whatever the sampled R5 reality checks
   produced. Brainstorm 25 named six things the dossier must contain but never designed how any
   of them get computed; it explicitly left that to "coverage-audit tooling... relates to topic
   29's blast-radius tooling" as a surfaced topic, which is this one.
2. **Post-sweep coverage-gap analytics** — meaningful only **after real per-language sweep data
   exists** (D5), i.e. from partway through D28's phase 1 onward, over instance/fact data rather
   than ontology data. This is the `<2 instances per dimension value` question the checklist
   names, and it is D34's own forward reference ("a data-driven successor to this document's
   manual audit") for choosing which languages to onboard next, past the curated 15.
3. **Search-query-log-as-signal** — meaningful only **post-launch**, once both brainstorm 19's
   Pagefind (client-side, no server log by default) and self-hosted Umami (the only piece of the
   stack with a database) exist. This is reader-demand data, not corpus-completeness data.

The checklist's framing risks reading these as one artifact with three inputs; they are better
understood as **three reports at three different points in the project's lifecycle, sharing a
narrow computational core and a common tooling shape** — not because bundling them is
architecturally required, but because the project has already twice validated the same shape
(D41's `report.py`, D46's `compile.py`) for exactly this situation: developer-only, on-demand,
non-daemon CLIs that read from data that already exists and print markdown. Inventing three
independent one-off scripts would repeat the "half-built dashboards" mistake D38 §2.7 and D41
§2.7 both explicitly rejected once already (three producers writing three incompatible logs
instead of one shared shape); building one dashboard-shaped tool to cover data that isn't even
simultaneously available yet (dossier data exists pre-1.0, gap data mid-sweep, demand data
post-launch — there is no calendar moment when all three inputs are populated at once) would be
solving a problem the project doesn't have.

A second thread: the `<2` threshold, as stated in the checklist, has no origin in any ratified
decision — it is the checklist's own shorthand, not a number the developer has committed to. Per
this project's now-consistent posture (D16's v1.0.0 threshold, brainstorm 25's dossier bars, all
explicitly "advisory, developer's discretionary judgment"), this brainstorm treats `2` as a
sensible *default*, not a number to hard-code as a trigger for anything automatic.

## Options with trade-offs

### O1 — One coverage-analytics surface, or fold into an existing tool, or three separate scripts?

**1a — fold everything into D41's `tools/observability/report.py`.** That tool already has the
right *shape* (subcommand CLI, markdown to stdout, ephemeral by default) and already owns "the
developer's own reporting habit." But its read side is transcripts + the D26 cost log + the
private pipeline ledger — *pipeline-run* data. This topic's three reports read ontology YAML,
instance/fact data, and (for `demand`) an Umami export — *corpus-content and audience* data, a
different domain entirely. Folding them in would blur D41's own stated boundary ("operational
telemetry, not corpus content... conflates two different audiences") between pipeline health and
KB coverage, the exact distinction D41 §2.1 Option B already drew when it rejected publishing
pipeline stats on the public site. Reject.

**1b — three independent one-off scripts, built separately as each need arises.** Cheapest to
start, but repeats a mistake this project has now explicitly named and avoided twice: D38 §2.7
("one combined view rather than three half-built dashboards") and D41 §2.7 (the unified
`sourcing_queue`, built for the identical reason). The three reports here share a real
computational core (§O2 below) that a common library prevents from drifting into three
inconsistent notions of "how many languages instantiate this feature."

**1c (recommended) — a new sibling CLI, `tools/coverage/report.py`**, mirroring D41's exact shape
(subcommands, markdown to stdout, optional gitignored local snapshot, no daemon, no new service,
never committed as canonical data) but as its own tool because its data domain is genuinely
distinct from D41's. Subcommands: `dossier`, `gaps`, `demand`. All three import a shared
`langatlas_coverage.metrics` module computing the one primitive all three need — "for each
(feature | dimension-value | language) pair, how many languages have a `present`/`partial`
instance, keyed by immutable node `id` (D16), not slug" — the same "compute once, three views
read it" move D41 already made for its own `replay_verdict` (§2.6 there) and D38 already made for
its shared migration-manifest interpreter. This keeps the "small Python CLI, no daemon" family
(`tools/observability/`, `tools/questionnaire/`, `tools/validate/`, `tools/orchestrator/`)
consistent by adding one more member with the same shape rather than growing an existing one
past its stated boundary.

### O2 — What the research-phase dossier concretely computes (brainstorm 25 §O6's six items)

Brainstorm 25 named six dossier contents without a mechanism. Walking through what each actually
needs:

1. **External-checklist coverage** — the brief's layer-2/3 lists, Jordan et al. (2015)'s feature
   model, and the Van Roy & Haridi (2003) concept index are all *prose*, not machine-readable.
   This item cannot be computed from nothing; it needs a **one-time authored artifact**,
   `ontology/exit-checklists/<source>.yaml`, transcribing each external list into
   `{checklist_item: node_id | disposition}` pairs — mapped once during R0/R1 (ideally by the
   same developer QA-skim session brainstorm 25 already earmarked for golden-set authoring, since
   both are "read the source, record a structured judgment" work), then diffed against the live
   ontology by `report.py dossier` every R6 cycle. Without this file, "external-checklist
   coverage" cannot mean anything more than a developer manually re-reading the brief each cycle
   — exactly the toil the dossier exists to remove.
2. **Sourcing integrity** — fully mechanical: reads the same D24 verifier ledger `report.py
   verifier` already reads (this topic's `dossier` subcommand calls into D41's existing verifier
   summary function rather than re-querying the ledger itself), scoped to ontology-node
   existence/definition facts.
3. **Reality-check results (R5)** — needs R5 sessions to emit **structured findings**, not prose
   summaries: a small `research/reality-checks/<cycle>-<theme>.yaml` recording, per sampled
   language × feature, `mappable: true|false` and a note. This is a light addition to brainstorm
   25's R5 design (which specified R5's *purpose* but not its *output format*) — without it, "%
   unmappable" is not computable from anything the dossier tool can read.
4. **Churn trend** — mechanical: git log over `ontology/` scoped to commits after a theme's
   "settled" marker (D27/O3c), cross-referenced against D38's migration-manifest count for that
   theme.
5. **Graph health** — mechanical: orphan-node and edge-degree queries directly over the ontology
   YAML tree, no external input needed.
6. **Pipeline readiness** — mechanical: reads the D22 golden-set eval's committed pytest output
   plus a count of open GitHub issues labeled for R5 shakedown.

Four of six are pure computation over data that already exists by construction; two (#1, #3) need
a small, explicitly-named authored artifact each, both cheap and both already implicitly assumed
by brainstorm 25's own text without ever being named as deliverables. This brainstorm's
contribution is naming them.

### O3 — The `<2 instances` threshold: origin, configurability, and what it triggers

**Origin.** Not a ratified number — it is the checklist's own shorthand for "not enough
corroborating language instances to present a dimension value with confidence." Two corroborating
`present` instances is the same bar D25's confidence model already uses for *sources* (tier ×
independent-corroboration count) — reusing that intuition at the *instance* level (does more than
one language actually show this dimension value, not just one book-cited theoretical existence)
is a reasonable default, not a derived constant.

**Configurability.** Recommend a single global default (`--min-instances 2`), not a per-dimension
override in `dimensions.yaml`. A per-dimension override would mirror D39's `exclusivity` field
pattern, but D39 needed per-dimension variance because dimension *shape* genuinely differs
(exclusive vs. multi); coverage *confidence thresholds* have no comparable ratified reason to
differ per dimension yet. Start with one flag; add a per-dimension override only if a real case
demands it later (matching this project's repeated "don't build the general mechanism before a
concrete second instance exists" discipline — e.g. D30's own "no partial-exclusivity mode until a
real case needs it").

**What it triggers.** Nothing automatic — consistent with every other threshold this project has
set (v1.0.0's dossier bars are "advisory only, none binding," per D27's ratification). `report.py
gaps` prints a sorted list of thin (dimension, value) pairs; two purely manual downstream uses:

- The developer manually adds/updates a language-onboarding candidate note (D28-style, in
  `decisions.md`/`open-questions.md` or wherever future-phase planning lives) when a gap looks
  worth acting on — not an automated backlog write.
- A **coarse visual marker on `/coverage/by-dimension/<d>/`** (a page brainstorm 19 §2.2 Option A
  already proposed) becomes possible once this data exists, but the actual glyph/UX design is
  explicitly **not** this topic's job — it folds into topic 19/33's already-established
  trust-signal/matrix-component ownership (the same fold-in pattern D39 used for the
  `exclusive`/`multi` visual distinction).

Note the important timing caveat this option surfaces: `gaps` is close to meaningless before
phase 1 completes. D28 phase 1 was deliberately designed so "every layer-3 dimension has ≥2
distinct *values* instantiated" — a dimension-breadth guarantee, not a per-value
*instance-count* guarantee. A value can be the phase-1 stress-test's only representative (e.g.
Prolog is currently the sole logic-paradigm carrier) and correctly show as a gap the day phase 1
finishes; that is expected, not a tooling bug, and `gaps`' report should say so in its own output
header rather than let the number read as alarming on day one.

### O4 — Interaction with topic 29's ontology-change tooling ("touches 29")

The checklist flags a "touches" relationship, not a structural dependency, and that turns out to
be correct once checked concretely. Neither D38's blast-radius script nor its migration-manifest
machinery needs to change for this topic, and this topic owes topic 29 nothing new, for one
reason: **there is no cache to invalidate.** Every subcommand here recomputes from current
ontology/instance/fact data on each run (matching D41 §2.1's explicit "regenerable at will from
data that already is" posture) rather than maintaining any persisted, incrementally-updated
coverage index. A dimension split, merge, or `exclusive→multi` flip (D39) simply changes what the
*next* `report.py gaps` run aggregates — there is nothing stale to detect or repair.

The one real, if minor, interaction: every metric here must key by **immutable node `id`**, never
by renameable `slug` (D16's own id/slug split), so a rename mid-theme doesn't spuriously appear
as "feature X's coverage dropped to zero, feature Y's coverage appeared from nowhere" between two
report runs. This is a straightforward application of a rule the project already ratified for
every other id-referencing tool (D23's fact ids, D38's blast-radius script, D46's compiler
anchors) — not a new design obligation this topic invents. If the developer chooses to keep
historical dated snapshots of `dossier`/`gaps` output (open question below), those snapshots will
reference slugs current at the time of writing; a later rename resolves through the existing
redirect/tombstone map exactly as any other historical document referencing an old slug would —
again, nothing new.

### O5 — Search-query-log-as-signal, without a second live analytics pipeline

Brainstorm 19 §5 already framed this correctly and explicitly deferred it here: "once both
Pagefind (§2.1) and Umami (§2.5) exist, logged on-site search queries are a direct, low-effort
signal... worth folding into that topic once both pieces ship rather than standing alone." The
concrete mechanics:

**The instrumentation gap.** Pagefind is a fully client-side static index (brainstorm 19 §2.1) —
by design it has no backend and therefore no query log of its own. Umami is the only piece of the
stack with a database. The two must be bridged with a small, deliberate addition: fire an Umami
**custom event** (Umami supports arbitrary named events beyond page views) on each Pagefind
search — `pagefind-search` with `{query, result_count}` — from the same inline
instant-search-box JS D33 already ratified (ctrl+click-friendly instant search). This is a small
increment to JS that already exists on the page, not a new JS-on-KB-pages precedent; it is,
however, a genuinely new decision (capturing query text, even as non-PII operational data) that
the developer should confirm explicitly rather than have it default in silently as a side effect
of this brainstorm (see open questions).

**No new live pipeline.** A periodic (monthly, matching the cadence already established for
D37's link-checker and D41's capability probe) export job pulls Umami's stored custom events via
its own API into the same private, build-side ledger location D41 §2.7 already established for
`sourcing_queue` — one more `kind` of private log, not a new storage mechanism. `report.py demand`
reads that export and does two things: (a) surfaces raw zero/low-result query frequency, sorted;
(b) does a cheap match against the feature `aliases: []` field D49 already ships (originally for
absence-claim verification, "plausibly useful for search/terminology mapping too" per its own
ratification note) to distinguish "reader searched a known synonym we should have matched" from
"reader searched something genuinely absent from the corpus" — the latter being the actually
actionable signal for content prioritization.

**Privacy.** Query text about programming-language features carries negligible sensitivity risk
relative to Umami's existing cookieless/no-PII posture (D33); this is stated for completeness,
not because it changes the recommendation.

### O6 — Single artifact vs. three audience-specific reports

Recommend three subcommands, not one merged report, for a reason stronger than "different
audiences": **the three inputs are never simultaneously populated in this project's own
timeline.** `dossier` needs ontology + R5 data that exists only pre-1.0.0; `gaps` needs real
per-language sweep instance data that starts appearing partway through D28 phase 1 and only
becomes non-trivial from phase 2 on; `demand` needs Pagefind + Umami data that exists only
post-launch, after the site has shipped and accumulated traffic. A single "coverage report" run
today would have two of its three sections permanently empty for most of the project's life. Three
subcommands under one tool (§O1c) gets the shared-tooling benefit (one library, one CLI
convention, one place a future contributor looks for "coverage stuff") without pretending the
three questions are answerable at the same time.

## Recommendation

*Proposed* — the developer ratifies (or amends) before this becomes a decisions.md entry:

1. **One new sibling CLI, `tools/coverage/report.py`**, matching D41/D46/D48's established
   `tools/<domain>/` shape exactly (subcommand dispatch, markdown to stdout, optional gitignored
   snapshot, no daemon, never committed as canonical data) — a distinct tool from D41's
   `tools/observability/report.py` because its read side (ontology + instance/fact data, plus an
   Umami export) is a different data domain from D41's (transcripts + cost log + pipeline
   ledger). Three subcommands: `dossier`, `gaps`, `demand`, all built on one shared library,
   `langatlas_coverage.metrics`, computing the single shared primitive ("instance count per node,
   keyed by immutable id") once.
2. **`dossier`** implements brainstorm 25 §O6's six items per §O2 above: four are pure
   computation over existing data; two (external-checklist mapping, R5 structured findings) need
   small named authored artifacts this brainstorm identifies as owed deliverables —
   `ontology/exit-checklists/<source>.yaml` (authored once, R0/R1) and
   `research/reality-checks/<cycle>-<theme>.yaml` (authored per R5 cycle, a light format addition
   to brainstorm 25's existing R5 design).
3. **`gaps`** computes `<dimension, value>` corroborating-instance counts against a configurable
   `--min-instances` flag (default `2`, no per-dimension override for now, per §O3), with an
   explicit caveat in its own output that the metric is close to meaningless before D28 phase 1
   completes. Output is a purely advisory sorted list; nothing automatic is triggered. Any
   coverage-page visual treatment of thin values is explicitly out of this topic's scope, folded
   into topic 19/33's existing trust-signal/matrix-component ownership.
4. **`demand`** reads a monthly Umami custom-event export (`pagefind-search` events, wired via a
   small addition to the already-ratified inline search-box JS, per §O5), matched against the
   D49 `aliases: []` field to separate "known synonym miss" from "genuinely absent content,"
   feeding the developer's manual content-prioritization judgment — no automated issue filing at
   this stage (see open questions for whether that should be a future topic).
5. **No structural interaction with topic 29 is required** (§O4): every metric here recomputes
   from current data on each run; the only obligation is keying by immutable node `id`, which is
   already the project-wide convention, not a new one this topic introduces.

## Open questions for the developer

1. **Tool boundary (§O1)** — confirm a new sibling `tools/coverage/report.py` over folding into
   D41's existing `tools/observability/report.py`, given the different data domain argument
   above?
2. **External-checklist transcription (§O2 item 1)** — confirm `ontology/exit-checklists/
   <source>.yaml` as a new R0/R1-authored deliverable this topic owes (the brief, Jordan et al.
   2015, and the Van Roy & Haridi 2003 concept index each transcribed once), rather than assuming
   this mapping already exists somewhere?
3. **R5 structured-findings format (§O2 item 3)** — confirm requiring R5 sessions to emit a
   small `research/reality-checks/<cycle>-<theme>.yaml` file (not just a prose summary) as a
   light retroactive addition to brainstorm 25's R5 design, needed to make dossier item 3
   mechanically computable?
4. **`--min-instances` default (§O3)** — confirm `2` as the default threshold with no
   per-dimension override for now, and confirm the recommendation that crossing it triggers
   nothing automatic (report-only, developer-discretionary follow-up)?
5. **Report persistence** — should `dossier`/`gaps`/`demand` output default to ephemeral
   (stdout + optional gitignored snapshot, mirroring D41's own still-open question 1 there), or
   does the developer want dossier snapshots specifically *committed* somewhere as a dated audit
   trail, given each R6 cycle's dossier is a real input to the eventual v1.0.0 declaration and
   might be worth keeping as a permanent record distinct from D41's purely-ephemeral precedent?
6. **Pagefind→Umami event wiring (§O5)** — is adding a `pagefind-search` custom-event call to the
   already-ratified inline search-box JS acceptable as a small increment under D33's existing
   search ratification, or does capturing query text (even non-PII, even privacy-respecting)
   warrant its own explicit sign-off separate from D33?
7. **`demand` cadence** — monthly export (matching D37/D41's other periodic jobs), or purely
   on-demand, run manually whenever the developer wants to look?

## New brainstorm topics surfaced

- **Reader-demand → issue-draft automation** — once `demand` data exists and has run for a while,
  should a recurring zero-result query pattern get any semi-automated path into brainstorm 18's
  `propose-coverage`/`request-language` issue forms (e.g. a periodic script drafting a candidate
  issue for the developer to review, never auto-filed), rather than staying a purely
  developer-read report forever? Speculative and strictly post-launch — worth its own future
  brainstorm once real `demand` data exists to design against, not now.
- **Coverage-page thin-value visual treatment** — `gaps`' output makes a concrete "which
  dimension values are thin" signal available for the first time; the actual glyph/placement on
  `/coverage/by-dimension/<d>/` belongs with topic 19/33's existing trust-signal and
  matrix-component ownership (worth folding into that checklist item's description rather than
  standing alone, matching how the `exclusive`/`multi` distinction was folded in for D39).
