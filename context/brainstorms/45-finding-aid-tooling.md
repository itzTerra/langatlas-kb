# 45 — Finding-Aid Tooling for the Research Phase

> Backlog brainstorm for LangAtlas. Scope (checklist item 45): a concrete
> `search_finding_aids`/checklist-generator tool querying PLDB/Wikidata/Hyperpolyglot/Wikipedia
> during D27's R3 survey subphase and the D5 per-language sweep, distinct from the D15/D21
> full-source RAG tools (`search_sources`/`get_source_section`, which are citable). Binding
> context: D14 (structural licensing analysis — Hyperpolyglot/Wikipedia are CC BY-SA finding aids,
> never bulk-copied), D29 (corpus bootstrap decision — PLDB/Wikidata/Hyperpolyglot/Wikipedia are
> finding aids only, never fact content, no new fact-status tier, an optional non-public
> `provenance.candidate_source` enum `pldb | wikidata | hyperpolyglot | internal-survey |
> sweep-questionnaire | challenge`, plus a narrow identification-metadata carve-out for single
> attributed data points), D15 (the citable `source_chunks` full-source RAG index and its
> `search_sources`/`get_source_section` tools, pipeline-only, never on the public MCP per D8), D27
> (R0–R6 research-phase structure; R3 = divergent thematic survey producing candidate
> concept/feature inventories with evidence chunks), D5 (the per-language sweep pipeline,
> questionnaire-driven per D46), D31 (fetched content is data, never instructions, enforced once in
> the `RunContext`/provider wrapper plus a shared lexical instruction-pattern scan, log-and-continue
> only), D26 (provider-abstraction layer — `RunContext`, budget/cache, the completion channel), D46
> (questionnaire compiler — `tools/questionnaire/compile.py`, the D5 sweep's fact-bearing field
> map), D41 (the `tools/<domain>/` CLI family shape: `tools/observability/`, `tools/coverage/`,
> `tools/questionnaire/`, `tools/validate/`, `tools/orchestrator/`), D8 (MCP is read-only,
> five-tool, public-facing — this tool is never registered there). Direct inputs: brainstorm 14
> (the finding-aid policy this topic operationalizes), brainstorm 25 (R3's survey design),
> brainstorm 38 (the compiler's `compile.py` shape as the closest sibling precedent for a
> deterministic small tool feeding both research-phase and sweep-phase agents). All proposals below
> are *proposed* until the developer ratifies.

## Problem framing

D29 settled the policy question cleanly: PLDB, Wikidata, Hyperpolyglot, and Wikipedia are
**finding aids, never fact content** — they may point agents at candidate language↔feature pairs
and coverage gaps, and (via D29's narrow carve-out) supply single attributed identification data
points (file extensions, first-appeared year), but nothing from them may land in a `sources:` list
or claim text, and D3's "community sources are corroboration only, never sole backing" rule already
forbids using them as citation backing even secondarily. What D29 did not do — and explicitly
deferred, per this checklist item's own framing — is specify the mechanism: today, "finding aid"
means an agent could in principle open a browser tab, which is not a pipeline component, not
logged uniformly, not rate-limited, not distinguished in its outputs from the citable
`search_sources` tool an agent might call moments later, and produces nothing durable that R3's
survey output or D46's compiled questionnaire can consume as structured input.

Four sources, four different technical postures:

- **PLDB** — no public API; the practical shape is a bulk data export (PLDB publishes its dataset,
  CSV/JSON-ish, as a GitHub-hosted repo) rather than a live query endpoint. Public domain per D14.
- **Wikidata** — a real SPARQL endpoint (`query.wikidata.org`) plus a REST API, both free, both
  rate-limited by convention (no hard published quota, but abusive query patterns get throttled).
  CC0 per D14/D29.
- **Hyperpolyglot** — a small hand-maintained static comparison-table site, no API at all; only
  option is scraping specific pages. CC BY-SA per D14 (finding-aid-only, same restrictiveness as
  the others despite the more permissive corroboration norms elsewhere).
- **Wikipedia** — a real, generous, well-documented REST API (`/api/rest_v1/` and the newer
  MediaWiki Action API), CC BY-SA per D14.

A tool that pretends these four are symmetric would either over-engineer the two static/scrape-shaped
sources into a fake "API client," or under-engineer the two real APIs down to Hyperpolyglot's
lowest common denominator. The design below treats "one query interface, four adapters with very
different internals" as the actual shape, matching how D26 already treats the completion channel
(one policy core, provider-specific adapters underneath).

A second thread the checklist name surfaces but doesn't resolve: **"search tool" vs
"checklist-generator" are two different consumption patterns.** R3 (survey) wants breadth — "what
candidate features/languages exist that our ontology draft hasn't considered yet," an offline batch
job producing a structured artifact for R4 drafting to consume. The D5 sweep wants a point lookup
— "does PLDB or Wikidata know anything about Rust's macro system," an on-demand call inside a live
per-language-per-feature loop. These are not the same interface even though they hit the same four
sources.

## Options with trade-offs

### O1 — Interface shape: one callable tool, or a batch CLI, or both?

**1a — a single callable tool only** (`search_finding_aids(query, sources=[...])`), invoked live by
both R3 survey agents and D5 sweep agents. Simple, one code path. But R3 explicitly wants a
*checklist*, a durable artifact D27 says feeds R4 drafting — a per-call tool result vanishing into
an agent's context window at survey time is exactly the kind of undurable output D27/D38/D41 have
each independently rejected elsewhere (D38 §2.7, D41 §2.7's "half-built dashboards" pattern: ad hoc
per-call results instead of one shared artifact). Reject as the sole shape.

**1b — a batch CLI only** (`tools/finding-aids/generate_checklist.py --theme <x>`), producing a
committed or gitignored artifact, with no live-callable interface. Fits R3 well. Fails the D5
sweep's actual usage pattern: a sweep agent mid-questionnaire-answer for `fi.rust.macros` needs a
point lookup ("does Wikidata know Rust has a macro system, and if so under what item/claim"), not a
pre-generated static file it has to have anticipated needing.

**1c (recommended) — both, sharing one library.** A `langatlas_finding_aids` Python package
(matching D38/D41/D46/D48's `langatlas_<domain>` library-first pattern) exposes:
- a **library function per source** (`query_pldb`, `query_wikidata`, `query_hyperpolyglot`,
  `query_wikipedia`) returning one normalized result shape;
- a **CLI**, `tools/finding-aids/report.py` (matching the family's `tools/<domain>/` naming — see
  §O5), with a `checklist` subcommand for R3 batch generation and a `lookup` subcommand for ad hoc
  developer/debugging queries;
- a thin **provider-abstraction-layer tool wrapper** (D26) exposing the same library functions as a
  callable `search_finding_aids` tool inside agent sessions, for the D5 sweep's live point-lookup
  need. One library, two call sites (batch CLI, live tool), exactly the D38/D46 "compute once, N
  consumption modes" pattern this project has now used three times (D38's blast-radius script, D41's
  `replay_verdict`, D44's coverage metrics module).

### O2 — Per-source adapter shape, given four genuinely different backends

**PLDB.** No live API — adopt a **periodic local mirror**: a job (D43-orchestrator-scheduled,
matching the cadence already established for D37's link-checker/edition-check and D41's
capability-probe monthly jobs) pulls PLDB's published dataset export into a local flat file/SQLite
table, refreshed monthly. All `query_pldb` calls read the local mirror, never live-fetch. This
sidesteps "PLDB has no API to rate-limit" entirely and gives R3's checklist generation a fast,
offline, fully-reproducible-per-run data source — the same "index-only, no live-fetch-at-verdict-
time" discipline D24 already applies to the verifier's own evidence reads, applied here by analogy
for the same reason (reproducibility, no live-dependency fragility in an unattended batch run).

**Wikidata.** Live SPARQL query against `query.wikidata.org`, scoped by a fixed, versioned query
template (`programming language` instances, `Q9143` and subclasses, selected properties: paradigm,
influenced-by, influenced, first appeared, file extension) — not free-text search. A thin
`httpx`-based client under the shared D26 `RunContext` (rate-limited, cached, logged — see §O3)
with conservative self-imposed throttling (Wikidata has no hard published quota but is well known
in tooling circles for throttling abusive query bursts; treat it the same way D26 already treats
the university gateway's undocumented rate limits — "no published ceiling exists, set a
conservative default rather than waiting on a number that isn't coming").

**Hyperpolyglot.** No API, small static site — a **periodic scrape into a local mirror**, same
shape as PLDB's mirror (monthly refresh, offline reads), scoped to the specific comparison-table
pages relevant to the D28 language set, respecting `robots.txt`/TDM opt-outs per D14 rule 8's
existing fetcher discipline. Given the site's small, hand-maintained size, this is a light job —
tens of pages, not a crawl.

**Wikipedia.** Live REST API (`/api/rest_v1/page/summary/<title>` for quick lookups,
`/w/api.php` action API with `action=query&prop=extracts|categories|links` for richer pulls),
well-documented rate limits (200 req/s anonymous burst-limited in practice, generous enough that no
mirror is needed) — a thin client under the same `RunContext` throttling/caching, no mirror
required.

This asymmetry (two live clients, two periodic mirrors) is a direct, honest reflection of what each
source actually offers, not an arbitrary design choice — building a fake unified "API" over PLDB
and Hyperpolyglot would mean either scraping live on every call (fragile, slow, disrespectful of two
small community-run resources) or building a mirror anyway and pretending it's an API. The mirror
approach also gives the CI-adjacent `checklist` batch runs (R3) determinism across a run — the same
discipline D24's index-only verifier evidence already established for a different reason
(reproducibility of verdicts).

### O3 — Caching, rate-limiting, and logging: reuse D26, don't reinvent

**3a — build a bespoke cache/throttle layer for this tool.** Rejected outright: D26 already built
exactly this (a `RunContext`-owned SQLite content-addressed cache, budget enforcement, transcript
logging) and D26 explicitly designed the completion channel's `httpx`-based rerank call as the
precedent for "small hand-rolled HTTP call under the same policy core" (D26 ratification note on
the rerank endpoint). Finding-aid queries are structurally the same shape: a small outbound HTTP
call that should be cached, rate-limited, and logged identically to every other externally-fetched
result in the pipeline.

**3b (recommended) — finding-aid calls are a fifth "channel" under the same `RunContext` policy
core**, not a new mechanism: content-addressed cache keyed on `(source, query-shape, params)`
(mirroring D26's `(resolved-model-id, messages, sampling, schema, prompt_id@version)` key, adapted
— there is no model/prompt here, so the key collapses to source + normalized query), the same
D18 transcript logging (every finding-aid call is a `RunContext`-mediated call, so it rides D18's
existing "capture from day one, cannot be retrofitted" logging for free), and the same token-bucket-
style conservative throttling default D26 already established for the university gateway's
undocumented limits, tuned per source: Wikidata and Wikipedia get real per-call throttles (live
APIs); PLDB and Hyperpolyglot effectively never throttle in practice since normal usage reads the
local mirror, not the live site (only the monthly refresh job hits the live source, and at a
deliberately slow, small-page-count pace).

### O4 — Non-citability: how results stay visibly non-authoritative in agent hands

This is the checklist item's sharpest requirement and the one place a sloppy implementation could
quietly violate D29/D3. Three enforcement layers, mirroring the multi-layer pattern D35 already
used for the MCP `caution` contract (structured field + inline text caveat + tool-description
framing) and D31's data-not-instructions treatment of fetched content generally:

1. **Structural**: every `search_finding_aids`/`query_*` result is wrapped in a typed envelope
   (`FindingAidResult{source, item, retrieved_at, non_citable: true}`), never a bare string — there
   is no code path that lets a finding-aid result flow into a `sources:` YAML field without an
   explicit, separately-typed conversion the schema doesn't offer (D23's `sources:` field expects a
   `source_id` referencing a minted `sources/` YAML record via the D4 verification gate; a
   finding-aid result is never a `source_id` and the schema gives no field shape that would accept
   one).
2. **Tool-description framing**: the tool's description (loaded into agent context once per session,
   exactly the D35 caution-contract precedent for MCP tool descriptions) states plainly: "results
   from this tool are leads, never citations — they may suggest what to look for and where, but
   every fact you commit still needs an independently verified tier-A/B source per D4; never put a
   finding-aid result in a `sources:` list." This mirrors D42's "MCP tool descriptions state the
   BY-SA reuse obligation once per session" pattern — restating a binding policy at the point of use
   rather than trusting an agent to recall D29 from training-adjacent project context.
3. **D31 data-not-instructions**: finding-aid results are externally-fetched text like any other
   source D31 already covers — delimited as evidence, scanned by the same shared lexical
   instruction-pattern check, logged per D18, log-and-continue on a hit (no hard block, matching
   D31's ratified stance). D31's own ratification explicitly noted the R3 live-web-fetch tool
   "does not need the same wrapper treatment from day one" as an acceptable initial gap — this
   tool is exactly that R3 tool becoming concrete, so the developer should decide now whether to
   retrofit D31's scan onto it immediately or defer, since D31's deferral was framed as temporary
   ("retrofit before it's relied on heavily") and this brainstorm is the retrofit trigger point (see
   open questions).

Given all three, "distinct from D15/D21 (citable)" from the checklist description is satisfied by
construction: the citable `search_sources`/`get_source_section` tools return chunks with locators
that flow directly into `sources:` fields (D15's own stated design); `search_finding_aids` returns
an envelope type the schema has no slot for. The distinction is enforced by the type system and the
build-time YAML schema validator (D48), not by agent discipline alone.

### O5 — `provenance.candidate_source` population: automatic, but narrow

D29 already specifies the field (`pldb | wikidata | hyperpolyglot | internal-survey |
sweep-questionnaire | challenge`) and its purpose (pipeline analytics only, never public). This
tool is the natural point to populate it: when a D5 sweep agent's fact-proposal was triggered by a
`search_finding_aids` result (i.e., the agent's own reasoning trace shows it queried the tool before
drafting the claim), the drafting call sets `provenance.candidate_source` to the matching source
enum value. This is **advisory bookkeeping, not a hard link** — there's no verification that the
finding-aid hint was in fact the proximate cause of the draft (an agent could query PLDB, get
nothing useful, and draft anyway from its own priors); D26's `RunContext` already logs the full
call sequence per D18, so a more precise "was this specific fact caused by this specific query"
reconstruction remains possible from the transcript later if ever needed (matching D41's own ruling
that `provenance.candidate_source` doesn't need a broader "why did the pipeline look here" model —
D18 transcript logging already gives the full trace). The identification-metadata carve-out (D29's
narrow exception: file extensions, first-appeared year as single attributed data points) is a
**separate code path**, not this tool's default output — it produces an actual `sources:`-eligible
citation (a properly minted `source_id` pointing at the specific PLDB/Wikidata page, tier D per D3)
rather than a `FindingAidResult` envelope, since D29 explicitly allows that narrow class of claim to
be sourced, unlike everything else this tool surfaces. Concretely: a distinct helper,
`mint_identification_source(source, item, field)`, produces a `sources/` YAML stub through the
normal D4 gate — this tool's main path never does that automatically.

### O6 — Where this lives in the repo

Following the `tools/<domain>/` family exactly (D41 `observability`, D44 `coverage`, D46
`questionnaire`, D48 `validate`, D43 `orchestrator`): **`tools/finding-aids/`**, Python module
`langatlas_finding_aids`, with `report.py` as the CLI entry (`checklist`, `lookup` subcommands per
§O1c), a `sources/` submodule holding the four adapters (`pldb.py`, `wikidata.py`,
`hyperpolyglot.py`, `wikipedia.py`), a `mirror/` submodule for the PLDB/Hyperpolyglot periodic-pull
jobs (scheduled via D43's orchestrator, same job-config shape as D37's link-checker/edition-check
entries), and the `RunContext`-facing tool wrapper (the piece D26's provider-abstraction layer
exposes into agent sessions) living either here or under the existing provider-abstraction package,
whichever the developer's current code layout for D26 already favors (flagged as an implementation-
time detail, not a design fork). This keeps the "small Python CLI, no daemon" family internally
consistent while giving finding-aid queries their own package, matching D44's own reasoning for why
`tools/coverage/` earned a sibling rather than folding into `tools/observability/` — a genuinely
distinct data domain (external community sources, not pipeline-internal data) deserves its own home
even though the shape (subcommands, markdown/structured output, no daemon) is identical to its
siblings.

## Recommendation

*Proposed* — the developer ratifies (or amends) before this becomes a decisions.md entry:

1. **One library, two consumption modes** (§O1c): `langatlas_finding_aids` exposes per-source query
   functions; `tools/finding-aids/report.py` wraps them into a `checklist` batch subcommand (R3) and
   a `lookup` ad hoc subcommand; a thin D26 tool wrapper exposes the same functions as a live
   `search_finding_aids` callable tool for the D5 sweep's point-lookup need.
2. **Per-source adapters matching each backend's real shape** (§O2): live throttled/cached clients
   for Wikidata (scoped SPARQL template) and Wikipedia (REST API); monthly-refreshed local mirrors
   for PLDB (dataset export pull) and Hyperpolyglot (small scoped scrape respecting robots.txt/TDM
   opt-outs per D14), with all `checklist`/`lookup`/live-tool reads served from the mirrors for
   reproducibility and to avoid live-hitting two small community-run resources on every call.
3. **Caching/rate-limiting/logging ride the existing D26 `RunContext` policy core** (§O3) as a fifth
   channel type — no bespoke mechanism, conservative self-imposed throttling on the two live
   sources, effectively-unthrottled reads on the two mirrored sources, D18 transcript logging for
   free by virtue of going through `RunContext`.
4. **Non-citability enforced structurally, three layers** (§O4): a typed `FindingAidResult` envelope
   the fact schema has no slot for, a stated tool-description caveat restating the D29/D3 policy
   once per session (mirroring D35/D42's precedent), and D31's data-not-instructions scan applied to
   finding-aid results from day one — this tool is the concrete retrofit point D31's own ratification
   flagged as deferred-but-owed.
5. **`provenance.candidate_source` populated as advisory bookkeeping** at drafting time when a
   finding-aid query precedes a fact proposal (§O5), with the D29 identification-metadata carve-out
   implemented as a genuinely separate, explicit path (`mint_identification_source`) that produces a
   real tier-D `sources/` citation through the normal D4 gate — never the tool's default output.
6. **Location: `tools/finding-aids/`** (§O6), matching the established `tools/<domain>/` family
   shape, module `langatlas_finding_aids`, never registered on the public MCP (D8's read-only
   five-tool set is fact-serving; this is a research/sweep-internal tool, same non-public posture as
   D15's `search_sources`/D18's proposed `search_debate_history`).

## Open questions for the developer

1. **D31 retrofit timing (§O4.3)** — build the shared lexical instruction-pattern scan into this
   tool from day one (the recommendation above), or accept the same "acceptable initial gap, retrofit
   before relied on heavily" posture D31's own ratification granted the R3 live-web-fetch tool, given
   this tool is arguably that same tool becoming concrete?
2. **Mirror refresh cadence (§O2)** — monthly, matching D37/D41's other periodic jobs, or does the
   R3 survey's own cadence (developer sign-off gated per theme, per D27's ratification) argue for a
   coarser "refresh once per theme cycle, on demand" cadence instead of a calendar-driven monthly
   job?
3. **PLDB mirror mechanics** — does the developer want to confirm PLDB's dataset is pulled via a
   git-clone-style mirror of its published repo (simplest, matches how the source corpus itself is
   already a directory pull) versus a scraped/API-shaped pull, before implementation locks in the
   adapter's shape?
4. **Tool wrapper placement (§O6)** — does the D26 `RunContext`-facing tool wrapper for
   `search_finding_aids` live inside `tools/finding-aids/` itself or inside the existing
   provider-abstraction package's tool registry, matching whatever precedent the D26 implementation
   has already set for other agent-facing tool wrappers (e.g. how `search_sources`/`get_source_section`
   from D15 are packaged)?
5. **Live-tool availability scope** — should `search_finding_aids` be available to *every* agent
   session type (R3 survey, R4 drafting, D5 sweep, human-challenge-response sessions), or scoped
   only to R3 and D5 as the checklist item's own description names, with other session types
   deliberately excluded to keep the "these are leads, not citations" framing from leaking into
   contexts where an agent might be more tempted to lean on them (e.g. a challenge-response session
   under time pressure)?

## New brainstorm topics surfaced

- **Fold into topic 57 (MCP tool-set extension tracking)**: this tool is explicitly never on the
  public MCP (matching D15's `search_sources`/D18's `search_debate_history` precedent), so it
  belongs in topic 57's standing tracking note as one more example of the project's growing
  non-public/pipeline-only tool surface, alongside D15's pair and D37's `list_contradictions`/
  `get_contradiction` — worth a one-line addition to topic 57's description rather than its own
  session.

None beyond the topic-57 fold-in above.
