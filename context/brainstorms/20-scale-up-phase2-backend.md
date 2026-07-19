# 20 — Scale-Up & Phase-2 Backend Sketch

> Backlog brainstorm for LangAtlas. Two loosely related questions bundled under one checklist
> entry: (a) what changes in the per-language sweep pipeline once the language count grows well
> beyond the curated D28 set (dozens to potentially 100+, PLDB-scale territory), and (b) a short
> forward-looking one-pager for the day the future Language Builder module needs a dynamic
> (non-static) backend, given D10 commits the site to a fully static Astro build today. Ontology
> schema-stability mechanics under scale (versioning, migrations, blast radius) are **not**
> re-litigated here — that half of the original brainstorm-04/08 scope moved to topic 22 (D16)
> and is treated as settled. Binding context: `context/decisions.md` D1 (git-is-the-database), D5/
> D11 (sweep pipeline retained for onboarding at scale), D6 (model tiering & budget), D10
> (static-first website), D13 (CI/dataset-bundle), D15/D21 (source-corpus RAG), D16 (ontology
> versioning, referenced not redesigned), D26 (`RunContext` provider layer), D28 (current
> 15-language phased set); CLAUDE.md's "later modules" section (Builder/Selector explicitly
> deferred); brainstorms 04, 08, 19 (website deep-dives), 25 (research-phase design), 34 (initial
> language selection). Backlog topics 27 (agent-runner commit protocol), 35 (run orchestrator &
> checkpointing), and 38 (questionnaire compiler) are adjacent open infrastructure this brainstorm
> flags dependencies on but does not itself design. All proposals here are *proposed* until the
> developer ratifies.

## 1. Problem framing

### 1.1 Many-language scale

D28 ratified a **15-language** curated set (14 core + Elixir) onboarded across four gated phases.
That number was chosen to stress the ontology (paradigm diversity) and serve the popularity
audience, not as a ceiling — D11 explicitly retains the per-language sweep pipeline (D5) "as the
mechanism for adding new languages later," and the checklist frames this brainstorm around
"incremental sweeps at many-language scale." The natural question: what happens if the developer
later wants to go from 15 to, say, 60, or to the low hundreds — PLDB itself catalogs several
thousand languages, giving a sense of the addressable ceiling if LangAtlas ever chased broad
coverage rather than curated depth (PLDB, n.d.). D29 already settled the adjacent question of
whether PLDB's *content* can be bulk-imported (rejected — corroboration-only, per D3/D19); it did
not address whether PLDB's *language list* is a legitimate input to a future target-selection
exercise, which is a distinct and much lower-stakes question (a list of names to consider
onboarding is not "fact content").

Three things plausibly break or strain as N (language count) grows well past 15, none of them the
ontology itself (that's D16/topic 22's territory, held constant here):

1. **Sweep-pipeline throughput and cost.** D5's sweep is deliberately per-language and
   independent (source-first questionnaire answers, reconciler diff, structured debate only on
   conflicted cells) — cost scales roughly linearly with N, and D28's own per-candidate cost
   table (ingestion + sweep cost, low/medium/high) already shows real spread even across 15
   languages (C++ and JavaScript rated "high" sweep cost; Python/R/Rust "low–medium"). At 100+
   languages the aggregate cost is a large multiple of what's been budgeted so far, even though
   D6's budget posture ("full Claude Pro + reasonable academic API use, no deadline") is
   generous and open-ended.
2. **Orchestration and commit-protocol load.** Running many sweeps — sequentially or with some
   concurrency — needs a batch driver with resumable checkpoints and budget hard-stops (topic 35,
   not yet designed) and a commit protocol that survives multiple sweep runners' outputs landing
   under D1's no-PR-gate rule without racing each other (topic 27, not yet designed). Both are
   currently open dependencies, not implemented gaps this brainstorm can paper over.
3. **Prioritization: which languages, in what order, and how deep.** D28's four phases were
   ordered by ontology-stress value, not popularity. Past the curated set, the ordering logic
   changes — there's no more "stress the ontology" argument once the ontology is stable at
   `1.0.0`+ (D16), so the driver becomes coverage-gap analytics (topic 44) and/or plain audience
   demand, and the deeper question of whether *every* newly onboarded language deserves the same
   full-depth sweep the curated 15 got.

### 1.2 The Builder's eventual dynamic backend

CLAUDE.md lists the Language Builder (a PC-part-picker-style feature-combination tool + public
library of built languages) as an explicitly deferred later module. D10 commits the website to
"Astro, fully static... builder/selector later as islands" — meaning the *plan already
anticipates* the Builder eventually needing more than static HTML, without saying what that "more"
concretely requires. This half of the brainstorm is deliberately scoped as a one-pager: not a
Builder design (out of scope per CLAUDE.md and D11), but a sketch of *what kind of dynamic backend
work gets triggered, and how much*, so that whenever the developer picks the Builder back up, this
document is the starting orientation rather than a blank page.

## 2. Options with trade-offs

### 2.1 What actually needs to change in the sweep pipeline at scale

**Option A — Run D5's sweep pipeline unchanged, just more times.** No new mechanism: every new
language gets the same independent questionnaire sweep, reconciler pass, and conflicted-cell
debate as the curated 15, gated only by topics 27/35 existing to make many sequential/concurrent
runs operationally safe.

- Pros: zero new design surface; matches D11's stated intent exactly ("the per-language sweep
  pipeline is retained as the mechanism for adding new languages later" — no asterisk about scale
  in that decision); every language gets uniform quality, avoiding a two-tier-content perception
  problem on the site.
- Cons: pure linear cost scaling with no batching economy; at 100+ languages, aggregate
  Claude-judgment-tier cost (debates, reconciliation escalations per D6) adds up even under a
  generous no-deadline budget, and the *slow university-hosted model* (a standing CLAUDE.md
  constraint) means wall-clock time, not just dollars, becomes the binding constraint — many
  overnight unattended batches, each depending on topic 35's checkpointing to be safe to leave
  running.

**Option B — Batch/group sweeps by lineage to reuse answers across similar languages** (e.g.
seed a new ML-family language's questionnaire draft from OCaml's already-reconciled answers as a
prior, since "me-too" languages in the same family share most feature values).

- Pros: could meaningfully cut cost for long-tail languages that are minor variants of an already-
  onboarded relative (e.g. a hypothetical future Elixir-adjacent BEAM language, or an ML-family
  cousin of OCaml).
- Cons: directly undermines the property that makes D5's reconciler meaningful — *independent*
  per-language answers are what let the reconciler's cross-checks catch genuine divergence;
  seeding one sweep from another's answers introduces anchoring bias exactly where the pipeline is
  supposed to be source-first and independent. Also adds real complexity to the questionnaire
  compiler (topic 38, not yet designed) to track lineage relationships. **Rejected for now** —
  the independence property is load-bearing for the reconciler's whole reason for existing, and no
  cost data yet demonstrates the linear-scaling cost is actually a problem (topic 16's
  instrumentation, once it has sweep-pipeline data rather than only R4 schema-dispute debates,
  is the right place to revisit this if evidence emerges).

**Option C — Tiered onboarding depth: full sweep for "primary" languages, a cheaper "stub sweep"
(a small fixed subset of highest-value fields) for long-tail languages, upgradeable later.**

- Pros: the only option that makes a 100+-language future economically plausible without an
  unboundedly large sweep bill; the schema already has the vocabulary for partial coverage
  (`status: partial` per D23, absence semantics under active design in topic 41), so a stub sweep
  is not a new *kind* of data, just a smaller *amount* of it per language; naturally reversible —
  a stub language can be promoted to a full sweep later without a schema migration, just more
  facts added under the same record ids.
- Cons: introduces a visible two-tier quality perception on the site (a language with 5 answered
  fields next to one with 80) that needs its own UX treatment — arguably a **welcome**
  reframe of D18/19's existing coverage-recruitment page (brainstorm 18's `/coverage/` page
  already handles "empty cell" states; a stub language is just a language-shaped version of the
  same "help wanted" framing) rather than a new problem, but it's still a decision the site design
  has to make consciously, not by accident. Needs its own criterion for "which languages qualify
  for full-depth treatment" — audience demand, TIOBE rank (per D14 rule 7, single attributed data
  points only), or developer discretion.

**Recommendation:** Option A stays the *only* mechanism while the language count remains in the
D28 curated-set neighborhood — there is no evidence yet that linear cost scaling is actually a
problem, and inventing a tiering scheme pre-emptively risks exactly the kind of premature
engineering CLAUDE.md's "no shortcuts that damage the long-term product" cuts both ways against
(shortcuts in either direction — under- or over-building — are shortcuts). Option C is the
*proposed future release valve*: the point at which the developer's ambition moves from "curated
depth" (D28's framing) to "broad coverage" (PLDB-adjacent breadth) is the trigger to introduce a
stub-sweep tier, not before. Option B stays rejected pending topic-16-style cost evidence.

### 2.2 Does the fully static site (D10) need to change at scale?

Largely no, and this is worth saying plainly rather than leaving as an implicit worry. Static
site generators routinely handle sites with many thousands of pages; the D13 CI publish
mechanism (validated dataset bundle as release assets, `data-vN` tags) doesn't change shape with
more languages, and the D15 source-corpus cost model already notes that even dozens of full
language specs stay in the tens-of-thousands-of-chunks / low-hundreds-of-MB range — trivial for
Postgres+pgvector regardless of language count. Brainstorm 19 already identified the actual site-
side scale trigger, independent of language count per se: "revisit an Astro island once pre-baked
coverage-matrix views prove insufficient" (an open question in that brainstorm, still
unresolved). This brainstorm doesn't re-decide that trigger; it just confirms that "many-language
scale" is a **pipeline-cost problem first, a site-architecture problem a distant second** — full
static rebuild time is the one site-side metric worth watching (a build-time regression as
language/feature/comparison-page count grows), and if it ever becomes painful, Astro's incremental
build options are a narrow, well-trodden fix, not a rearchitecture.

### 2.3 What would the Builder actually need beyond static data?

Unpacking "the Builder" into its two structurally different pieces (per CLAUDE.md's own
description — "combination tool" + "public library of built languages") clarifies that they have
very different backend needs:

**Combination validation** (checking a user-selected set of features against the graph's
`requires`/`enables`/`conflicts-with`/`alternative-to` edges, per brainstorm 01/22's
"combination-validation rules" and D16's `cross_cutting` exception handling) is, in principle, a
pure function of the already-published graph data. If the full ruleset ships as a static JSON/WASM
payload the island loads once, validation itself can run **entirely client-side, with no backend
at all** — matching D10's static-first ethos and its own stated plan ("builder... later as
islands," not "later as a service"). This is the most important observation in this brainstorm:
**a Builder MVP does not automatically need a dynamic backend.**

**Sharing a built configuration** (a permalink to "here's the language I assembled") can plausibly
stay backend-free too: encode the selection in the URL (query string or a compact hash) or
`localStorage`, decode client-side — no server round-trip, no database row, nothing to moderate.

**The public library of built languages** — a persistent, browsable, presumably-writable
collection of *other people's* built configurations — is the one piece that structurally requires
a live, writable data store, because "public library" implies content surviving past one visitor's
session and being discoverable by others, which a static site fundamentally cannot do without
some server-side write path. This is also where D1's "community/runtime data... is future DB-only
state, never round-tripped" carve-out already anticipated the need, and where upvotes/usage stats
(also flagged, deferred with the Builder in D1/decisions.md) live.

So the honest trigger for "the day the Builder needs a dynamic backend" is not "the Builder
ships" — it's specifically **"the public library ships,"** a strictly later and smaller-scoped
event than the Builder MVP itself.

**Option A — Extend the existing stack with a small writable service.** Reuse D8's FastAPI
adapter (already planned for non-MCP providers/site search) and add a genuinely separate Postgres
schema/database for community data (accounts, submitted configurations, votes) — explicitly *not*
part of the derived-from-git KB schema, so D1's "everything downstream is derived" invariant stays
true for the KB tables specifically, with one clearly-labeled exception. Auth via GitHub OAuth,
consistent with the project's existing GitHub-centric contributor identity (DCO, issue-form
challenges, GitHub App commit identity).

- Pros: minimal new infrastructure — Postgres and FastAPI are already standing investments;
  GitHub OAuth needs no new account system; matches "boring, solo-maintainable technology."
- Cons: introduces the project's first genuinely live, non-derived, non-rebuildable database —
  needs its own backup story (distinct from "rebuild from git"), its own migration tooling
  (ordinary schema migrations, not D16's ontology-migration machinery), and its own abuse-handling
  surface (spam/moderation for user-submitted content) that nothing in the current design
  addresses, because everything current is either agent-authored-then-verified or a prefilled
  GitHub issue — this would be the first raw, low-friction, anonymous-adjacent write path into
  the project.

**Option B — Offload to a third-party backend-as-a-service** (e.g. a hosted Postgres/auth/storage
bundle) to keep the KB repo/stack untouched by community-write concerns entirely.

- Pros: isolates blast radius from the KB pipeline cleanly; less custom code to write and
  maintain.
- Cons: adds an external vendor dependency the project has otherwise avoided — brainstorm 19
  already chose self-hosted Umami over a hosted analytics alternative specifically on
  self-maintainability grounds, and this would cut against that established preference for a
  much more central piece of infrastructure (a write path with user accounts, not a passive
  analytics collector). **Not recommended** unless a concrete reason emerges to distrust
  self-hosting a small writable service (e.g. abuse volume the developer doesn't want to
  moderate personally).

**Option C — Defer the public library indefinitely past the Builder MVP itself**, shipping only
the backend-free combination-validation island + shareable-URL permalinks, and treat "the
library" as its own future deferred module rather than an assumed component of "the Builder."

- Pros: applies D11's own module-deferral logic recursively — defer the *sub-feature that needs a
  backend*, ship the *sub-feature that doesn't* — which is exactly the kind of scoping discipline
  the project has already applied at the module level (Builder/Selector deferred; this just
  applies the same knife one level deeper, inside the Builder). Gets most of the Builder's user-
  facing value (the actual combination/validation experience) with zero new infrastructure.
- Cons: none structurally — this is a sequencing choice, not a capability trade-off; the library
  can always be added later without redesigning the validation island.

**Recommendation:** Option C first (ship a backend-free combination-validation island +
URL/localStorage-encoded permalinks whenever the Builder is picked up), Option A only if/when the
public library specifically is greenlit, Option B not at all absent a concrete reason to distrust
self-hosting. This keeps the "day the Builder needs a dynamic backend" as far in the future as
honestly possible, and when that day arrives, points at reusing the stack already built (Postgres,
FastAPI) rather than adding a new vendor.

## 3. Recommendation (*proposed*)

1. **Sweep pipeline at scale:** keep D5's independent per-language sweep unchanged (§2.1 Option
   A) while the language count stays in the curated-set neighborhood; no new batching/lineage-
   reuse mechanism (§2.1 Option B rejected pending cost evidence). Adopt a **tiered "stub sweep"**
   (§2.1 Option C) as the proposed release valve for if/when the developer's ambition shifts from
   curated depth toward PLDB-adjacent breadth — not designed in detail here, flagged as its own
   future brainstorm (§5).
2. **Prioritization past the curated 15** should draw on coverage-gap analytics (topic 44) and
   audience/demand signals rather than the ontology-stress logic that ordered D28's phases (which
   stops applying once the ontology is stable).
3. **The static site (D10) does not need architectural change for language-count scale** — the
   one metric worth watching is full-rebuild time, with Astro's incremental-build features as the
   narrow fix if it ever matters; the actual site-side scale trigger already identified
   (brainstorm 19: pre-baked coverage-matrix views proving insufficient) is orthogonal to language
   count and stays that brainstorm's open question, not re-decided here.
4. **The Builder does not automatically need a dynamic backend.** Split it into
   combination-validation + sharing (both backend-free, client-side/URL-encoded, matching D10's
   static-first plan) versus the public library (the one piece that genuinely needs a live
   writable store). Ship the backend-free half first (§2.3 Option C); defer the library as its own
   later decision point.
5. **When the library is greenlit,** extend the existing Postgres+FastAPI stack with a clearly
   separate, non-derived community schema and GitHub OAuth (§2.3 Option A), explicitly not a
   third-party backend-as-a-service (§2.3 Option B rejected absent a concrete reason to distrust
   self-hosting).
6. **This brainstorm does not touch ontology-versioning mechanics** (id/slug split, blast-radius
   semver, migrations-as-scripts) — D16/topic 22 remains the authority there regardless of
   language count.

## 4. Open questions for the developer

1. **Is there an actual ambition to go past the curated 15-to-~15-language set** toward broad
   PLDB-adjacent coverage, or is "curated depth over a fixed set, forever" the intended long-term
   shape of the project? This brainstorm's §2.1 tiering proposal only matters if the answer is
   "yes, eventually" — if the project is meant to stay a deep, curated reference rather than a
   broad catalog, the stub-sweep idea can be dropped entirely rather than merely deferred.
2. **Should PLDB's language list (names only, not content) be usable as a future target-selection
   input** for "which languages to consider onboarding next," distinct from D29's already-settled
   rejection of PLDB as fact *content*? This seems like a clear "yes" given the content/metadata
   distinction, but wasn't explicitly asked when D29 was ratified.
3. **What's the actual trigger for greenlighting the public-library half of the Builder** — a
   fixed criterion (e.g. "once the KB itself has N verified facts" or "once the site has organic
   traffic"), or purely developer discretion whenever they feel like building it? No urgency to
   answer this now (the module itself is far off), but worth having an instinct on record.
4. **Does the stub-sweep tier (if ever adopted) need a visible site-side badge distinguishing
   full-depth from stub-depth languages**, or does the existing coverage-page "help wanted" framing
   (brainstorm 18) already cover this adequately without a new visual signal?

## 5. New brainstorm topics surfaced

- **Stub-sweep tier design** — if/when the developer confirms ambition to scale past the curated
  set (open question 1), a dedicated brainstorm to design the actual field subset, promotion path
  from stub to full, and site presentation of mixed-depth coverage.
- **Community write-path schema & moderation** — when the public library is greenlit (§2.3 Option
  A, open question 3), a focused design pass on the community schema, GitHub OAuth flow, abuse/
  spam handling, and backup strategy for the project's first non-derived live database.
- **Builder combination-validation engine** — explicitly out of scope here and still deferred per
  CLAUDE.md/D11, but flagged as the concrete next design step whenever the Builder itself is
  picked up (client-side rules-engine shape, how the JSON/WASM payload is built from the graph).

## Sources

- PLDB (n.d.). *Programming Language Database.* http://pldb.info/ (referenced only for its scale
  as an addressable-ceiling data point — not as a source of fact content, per D29's existing
  corroboration-only ruling).
