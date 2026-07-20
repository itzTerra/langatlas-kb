# LangAtlas — Full Project Specification

> Consolidated 2026-07-20 from every **ratified** decision in
> [decisions.md](decisions.md) (D1–D62) and the full detail of the brainstorm files that
> produced them ([brainstorms/](brainstorms/)). All content below is the *current amended
> state*: where a decision was later superseded or amended by a dated note, only the final
> state is written here. decisions.md remains the decision authority; the brainstorm files
> remain the trade-off analyses; this document is the single readable build spec.
>
> Two companion sections close the document: **§14 Unclear points found during spec
> writing** (items owed further brainstorming) and **§15 Timeline & developer checklist**
> (all future steps, including the deferred brainstorm backlog and deferred open
> questions).

---

## 1. Product definition

### 1.1 What LangAtlas is

A **sourced knowledge base mapping many programming languages onto a structured model of
programming-language concepts**, built incrementally by developer-managed AI agents and
correctable by human experts, with three surfaces:

1. **Knowledge base** — features of programming languages, their per-language realizations
   with syntax previews, quality impacts, and a typed graph of relationships (requires /
   enables / influences ± / conflicts-with / alternative-to / affects-quality). Every
   user-facing fact links to a structured source record.
2. **Agent-facing RAG** — the same knowledge exposed to AI agents (Claude Code via MCP,
   other providers via a thin API) so agents can argue about the topic and grow the corpus
   with new sourced facts — a self-backing net of information.
3. **Public website** — SEO-focused, for human eyes (not an AI information source), clean
   typography-first design, per-fact citations, and an easy "challenge this fact" path for
   human experts.

**LangAtlas is a build pipeline, not an online application.** The canonical store is a
public git repo of human-readable YAML files; Postgres, the MCP server, and the fully
static site are one-way derived build artifacts.

### 1.2 Terminology (fixed vocabulary)

- **concept** — any idea or principle, often (not necessarily) grounded in theory.
- **feature** — a realisation of a concept within a family of related systems (here:
  programming languages).
- **feature instance** — a realisation of a feature in a specific system (a particular
  language).
- **characteristic** — an observable property of a system or feature instance.
- **developer** (never "owner") — the person operating the pipeline and making project
  decisions; **contributor** — anyone participating. The project is designed for multiple
  people.

### 1.3 Naming, positioning, brand (D17, D19, D40 — brainstorms 23, 31)

- **Name: LangAtlas** (WALS — World Atlas of Language Structures — pedigree). The former
  working title "Hermes" is retired everywhere except historical brainstorm documents
  (publicly unusable: Meta's Hermes JS engine owns the SERP; luxury-brand trademark).
  Repos: `langatlas-kb`, `langatlas-site`, `langatlas-transcripts`. Tagline pattern:
  *"LangAtlas — a sourced map of programming-language features. Every fact cited."*
- **Domain**: `langatlas.dev` is available (primary); `langatlas.io` is taken;
  `lang-atlas.io` available defensively. Registration + GitHub-org confirmation happen
  purely on the developer's own independent decision — **no trigger criterion exists**
  (D40 superseded the earlier "trigger" language).
- **Positioning wedge (D19)**: the typed concept graph *first*, per-fact sourcing
  *second* — in that order, vs PLDB/Hyperpolyglot.
- **Positioning statement (D40)**: three nested lengths — a 3-sentence hero paragraph
  (homepage/about; ships **with the named PLDB/Hyperpolyglot comparison sentence cut**,
  rest of the wording as drafted in brainstorm 31: graph-first, sourcing-second,
  "narrower on purpose"); a compressed 1-sentence derivative (meta description, OG
  images); D17's tagline as the shortest form.
- **Launch framing (HN/lobste.rs)**: title foregrounds the typed graph + sourcing claim
  (independently checkable); the "AI agents wrote this" disclosure goes in the first or
  second body sentence, framed as *why* the sourcing claim is credible ("there's no human
  review gate — the citation check *is* the gate"). lobste.rs shifts relative emphasis
  toward ontology/versioning design.
- **Wordmark**: wordmark-only launch (standard open-source geometric/humanist sans,
  monogram favicon); a parametrically-generated isogloss-line SVG mark (2–3 open Bézier
  contour paths, built as a small reproducible script under version control) is a
  fast-follow; a commissioned logo is rejected.
- **Accent color**: warm amber/ochre — starting range `#B5540A`–`#C9691A` light /
  `#E8A33D`–`#F0AE4A` dark, exact hexes fixed by an implementation-time contrast audit.
  (Real contour-line/isogloss map ink convention; avoids dev-tool blue and the LangChain
  brand association.)
- **OG images (D33/D40)**: build-time Satori + resvg; three templates — feature/language
  (shared skeleton), comparison (two-column, accent-color center divider echoing the
  isogloss-crossing metaphor), homepage (tagline + wordmark, centered) — on a shared
  warm-paper visual language. **No live-changing numbers or status glyphs on any
  template** (staleness risk between static image and live page).

### 1.4 Scope: what is deferred and what is out

- **Deferred entirely** (kept as schema affordances only): Language Builder,
  public library of built languages, Language Selector, upvotes/rankings, TIOBE stats,
  comments/forum.
- **Explicitly unrealistic / out of scope**: auto language standards, auto compilers,
  automatic language-to-language translators.
- **No artificial MVP slice (D11)**: the round-1 "3 languages × 5 features" plan is
  rejected. A heavy frontloaded research phase (§7.6) designs the generic feature
  landscape first; the per-language sweep pipeline (§7.2) is retained for onboarding
  languages afterwards. Personal hobby project: no deadline, no shortcuts that damage the
  long-term product.

### 1.5 Developer constraints (bind every design choice)

Solo developer; proof-of-concept posture. Resources: Claude Code Pro (session/usage
limits) plus a **small programmatic SDK credit pool** (D6, 2026-07-20 — never for volume;
reserved for the pipeline steps requiring the highest-quality judgment); no GPU for local
inference; a fairly slow university-hosted model API (which **does** host embedding and
reranker models); no additional cash budget. Every user-facing fact needs a source with a
structured, modern bibliographic identity. The RAG system must connect to Claude Code and
ideally other/local providers. Facts must be trivially challengeable by human experts.
Favor boring, solo-maintainable technology. English-only (D7) — no translations planned.

---

## 2. Architecture overview

### 2.1 Git is the database (D1)

The canonical store for all curated knowledge (features, feature instances, edges, rules,
sources) is a **repo of human-readable YAML files**. Everything downstream — Postgres,
vector index, static site — is a **one-way derived build artifact** compiled by CI. There
is no sync-back problem because nothing downstream is ever authoritative.

- **No PR gate for agent-produced facts.** Agents commit directly; a fact is admissible
  because it is backed by a verified source (D4/D24), not because a human reviewed it.
  Controversial/conflicting facts are **auto-flagged** (surfaced on the site and in a work
  queue), never routed to developer review — the pipeline must not depend on the
  developer's review bandwidth. Human expert challenges (§6.7) remain the correction
  mechanism.
- **Every agent chat is logged** (§7.10); a fact optionally links to the chat that
  produced it.
- **Public repos from day one**; **exactly two product repos** (D13): `langatlas-kb`
  (data + schema + pipeline + agents + MCP + compose; receives fact challenges) and
  `langatlas-site` (Astro + deploy; receives website issues), plus the public
  `langatlas-transcripts` repo (§7.10). A third tooling repo is rejected.
- Never commit embeddings, page snapshots, or binaries — build outputs only.
- Community/runtime data (votes, usage stats, submissions) is future DB-only state, never
  round-tripped.

### 2.2 Component map

```
langatlas-kb (git, public, canonical)
  ontology/  concepts/  features/  languages/  edges/  rules/  sources/
  tombstones.yaml  contradictions.yaml  sources/_tombstones.yaml
  prompts/  config/  tools/  tests/
        │  agent runner commits directly (GitHub App identity, §7.9)
        ▼
  CI: validate → derive facts → verify ledger join → build bundle
        │  green main only ("last-green publication")
        ▼
  GitHub Release: data-vN  =  langatlas-data-vN.sqlite.zst + manifest.json   (§8.4)
        │                          │
        ▼                          ▼
  langatlas-site (Astro, static)   Postgres (docker compose; pgvector + FTS)  (§8.5)
     Pagefind search, giscus            ▲ blue-green loader
     islands only                       │
                                   stdio MCP server (read-only, 7 tools)      (§9)
                                   thin FastAPI adapter (deferred public search)

private tier (dev machine, tarball-backed): source snapshot store, source_chunks
  extracted text, knowledge_embeddings data, D26 call cache, cost log,
  orchestrator checkpoints
```

**Where Postgres lives (D58, 2026-07-20)**: Postgres serves the RAG/MCP local agentic
workload on developers' machines (the kb repo's compose stack) — its only role at launch.
A site-side Postgres becomes relevant only later, if the deferred public FastAPI search
(D33) or live modules (Builder library, D34) ship.

### 2.3 Absent on purpose (D12)

Graph DB (plain tables / in-memory graph at build time), message queues,
Kubernetes/microservices, managed vector DBs, CMS, custom forum, custom auth (site
static; challenges ride GitHub auth; MCP local), daemons of any kind, LiteLLM, dashboards
(CLIs reading logs instead), interactive graph-diff libraries.

---

## 3. Knowledge model (D2, D23 — brainstorms 01, 09)

### 3.1 Entities

- **Concept** — thin, pedagogical. Excluded concepts (scope, exceptions, security,
  naming) enter via Concept-first staging and later atomize through ordinary splits
  (D16); Concept records carry an optional `excluded_rationale`.
- **Feature** — the primary node; `layer`: 1 syntax / 2 semantic / 3 design-choice;
  layer-3 features carry a `dimension`; feature-level `cross_cutting: true` flag (pure
  metadata — site badging, RFC triage; lint-checked for agreement with its dimension's
  `exclusivity`); feature-level `aliases: []` synonym list (ships now, D49 — used by
  absence verification, search/synonym matching, and the `demand` report).
- **FeatureInstance** — feature × language, the reified `implemented-by` edge; the D20
  authoring unit; `status: present | absent | partial`.
- **SyntaxExample** — reified `expressed-as`; functionality stays separate from syntax;
  carries `origin: original | adapted-from:<source-id>` (D14).
- **Quality** — small controlled vocabulary in `ontology/taxonomy/qualities.yaml`.
- **Characteristic** — a fact listed under a language feature (an observable property),
  which can serve as evidence feeding a quality edge. **Not** a separate page type — it
  renders as sourced facts under the feature/instance it describes.
- **Edge** — 5 feature↔feature types: `requires`, `enables`, `influences` (± polarity
  only, no magnitude), `conflicts-with`, `alternative-to`; plus **one signed
  `affects-quality` feature→quality edge** carrying polarity + strength (D23 consolidated
  D2's original `improves-quality`/`hurts-quality` pair).
- **Rule** — multi-feature emergent interactions (`when_all` conjunctive antecedents in
  v0; `when_any`/`unless` are additive later; `effect: requires | forbids | warn`).
- **Fact** — one human-readable sourced sentence bound to exactly one machine-readable
  claim; two independently challengeable claims = two facts. Facts are the embedding unit
  for fact-RAG so retrieval always returns provenance.
- **Source** — CSL-JSON vocabulary authored as YAML (§4).

**Nothing is developer-curated / closed** — the layer-3 dimension list, the feature set,
everything is subject to change through the normal evidence + challenge process.

### 3.2 Fact granularity (D20) and the two-part fact identity (D23)

The authoring unit is **one record per feature instance with per-field `sources:`
lists**; challengeable per-field facts with stable IDs are **derived at build time** from
(record, field) paths. `facts/` does not exist in the repo — the fact table is a build
artifact.

Fact identity is two-part, reconciling D16 (immutable ids) with D20 (per-field derived
facts):

- **anchor** = `(record-id)#(field-path)` with immutable sub-keys for list entries —
  e.g. `fi.rust.pattern-matching#since`,
  `fi.rust.pattern-matching#characteristics[c-exhaustive]`. List entries are addressed by
  their own stable sub-key, never by list position.
- **fact id** = `f-` + first **12 hex** chars of SHA-256 of the canonical claim string
  (§3.5). The id changes iff the claim changes; the anchor never changes while the record
  exists. CI fails the build on any hash collision (then bump corpus-wide to 16 hex — a
  mechanical change, since fact ids are derived, not stored).
- A corrected value mints a new id sharing the anchor; the old id resolves via the
  append-only root `tombstones.yaml` (`superseded_by`, `derived_from`, `migration_id`).
- The site's `data-fact-id` and challenge-issue prefills carry **both**. URL fragments
  use the fact id; superseded ids resolve through the tombstone chain to the successor.

### 3.3 Record identity and directory layout

Records never mint free identities — record ids are deterministic compositions of
immutable node ids:

| Record | id pattern | example |
|---|---|---|
| Feature / Concept / Language | minted node id | `pattern-matching`, `rust` |
| FeatureInstance | `fi.<language>.<feature>` | `fi.rust.pattern-matching` |
| Edge | `edge.<type>.<from>.<to>` | `edge.influences.algebraic-data-types.pattern-matching` |
| Rule | `rule-` prefixed node id | `rule-laziness-needs-purity` |
| Source | minted slug id (D3) | `vanroy-haridi-2003` |
| Syntax example | `<instance-id>.sx.<key>` | `fi.rust.pattern-matching.sx.basic-match` |

Sub-keys (`sx.<key>`, characteristic `c-<key>`, assessment keys) are minted once and
immutable (renaming = supersession). `alternative-to` endpoints are stored in
lexicographic order (CI-enforced) so the edge id is canonical. Only one `influences`
edge per ordered pair — polarity is a field, not part of the id; flipping polarity is a
supersession of the same edge record's fact.

Layout (chosen so concurrent no-PR-gate agent commits rarely touch the same file):

```
ontology/            VERSION  CHANGELOG.md  schema/  migrations/  redirects.yaml
                     taxonomy/{layers,dimensions,edge-types,qualities}.yaml
                     claim-templates/<kind>.yaml          (D47)
concepts/<concept-id>.yaml
features/<feature-id>.yaml
languages/_registry.yaml                                   (language-id mint authority)
languages/<language-id>/language.yaml                      (Language record)
languages/<language-id>/instances/<feature-id>.yaml        (one record per file, D20)
edges/<from-id>/<type>--<to-id>.yaml                       (one file per edge, sharded)
rules/<rule-id>.yaml
sources/<source-id>.yaml           sources/_tombstones.yaml   (D38 fold-in)
tombstones.yaml                    contradictions.yaml        (both canonical ledgers)
```

Edges are one-file-per-edge sharded by from-feature (hot features would make a shared
file a permanent merge-conflict magnet under concurrent commits); `tombstones.yaml` is
append-only and CI-checked (shard to `tombstones/<year>.yaml` later if conflicts become
real — a PATCH-level change).

### 3.4 Record schemas (v0 — brainstorm 09 §O7, as ratified)

JSON Schemas live in `ontology/schema/`. Shared sub-schemas:

```yaml
# one entry in any `sources:` list
- source: rust-reference-match-expr        # id in sources/
  locator: "#match-guards"                 # §4.3 grammar; REQUIRED (D4 source-first)
  quote: "…"                               # optional (D3), ≤50 words (D14)

# provenance block — record-level default, per-field override when a later run edits a field
provenance:
  proposer: { agent: lang-sweep/rust, model: …, prompt: sweep-v3 }
  claim_origin: source-derived             # source-derived | prior  (D4)
  debate_id: null
  chat_run_id: 2026-07-18-sweep-rust-003   # optional link into langatlas-transcripts
  candidate_source: pldb                   # optional, NON-PUBLIC enum (D29): pldb |
                                           # wikidata | hyperpolyglot | internal-survey |
                                           # sweep-questionnaire | challenge
  sampling: { temperature: …, top_p: …, seed: … }   # optional (D47) — populated only
                                           # when deviating from pipeline defaults
```

**Verifier verdicts are NOT written back into authored YAML** (D23 ratification,
superseding brainstorm 09's write-back draft): they live in a private build-side ledger.
The `sources:` field (the citations backing a claim) does live in the public YAML from
the start, agent-authored and human-correctable.

**Feature** (`features/pattern-matching.yaml`): `id` (immutable), `slug` (renameable;
history in `ontology/redirects.yaml`), `name`, `layer`, `dimension` (required iff layer
3), `cross_cutting`, `aliases: []`, `realizes: [<concept-ids>]`, fact-bearing `summary:`
block (`text` + `sources` — also the embedding text for `feature-description` rows in
`knowledge_embeddings`, D62), `provenance`. Edges are *not* listed in feature files.

**FeatureInstance** (worked example, `languages/rust/instances/pattern-matching.yaml`):

```yaml
feature: pattern-matching
language: rust                  # redundant with path; CI cross-checks
status: present                 # present | absent | partial
since:
  value: "1.0"
  sources: [{ source: rust-reference-match-expr, locator: "#match-expressions" }]
notes: >-
  match is an expression; exhaustiveness is compiler-checked; guards supported.
characteristics:
  - key: c-exhaustive           # immutable sub-key
    text: >-
      The Rust compiler rejects match expressions that do not cover every
      possible value of the scrutinee's type.
    sources: [{ source: rust-reference-match-expr, locator: "#match-expressions",
                quote: "…" }]
syntax:
  - key: basic-match
    title: Basic match with destructuring
    origin: original            # D14: never copied from SA-licensed comparisons
    code: |
      match msg { … }
    sources: [{ source: rust-reference-match-expr, locator: "#match-expressions" }]
provenance: { … }
```

Derived facts from this one record (build output): `#exists`, `#since`,
`#characteristics[c-exhaustive]`, `#syntax[basic-match]` — each with its own fact id,
sources, provenance, and status. Correcting `since` changes one fact id, appends one
tombstone line, and leaves the other facts untouched.

- **`status: partial` is kept** (D23), carrying associated notes typed
  `limitation | extra | alternative` describing the missing or additional aspect
  (concrete schema shape: see §14, unclear point U2).
- **`status: absent` records are first-class sourced facts** with a **required
  `absence_scope`** free-text field (D49) — the sweep agent's argument for why the cited
  source(s) can be trusted as comprehensive over the feature's category. No file at all
  means *unknown/not yet swept* — a distinction every surface must preserve (§6.6).

**Edge**: `id`, `type`, `from`, `to`, `polarity` (influences only), fact-bearing
`statement:` block (`text` + `sources`), `provenance`.

**`affects-quality` edge**: same file shape with `to: <quality-id>`; instead of a single
statement it carries a keyed **`assessments:` list** — D2's "attributed assessments with
recorded spread, no forced consensus". Each assessment is one independently challengeable
derived fact: `key`, `assessor` (agent/model/prompt), signed polarity, `strength: weak |
moderate | strong`, `statement`, `sources`. The build derives a **distribution summary**
per (feature, quality) — counts per polarity, strongest tier per side — which the site
renders ("sources disagree: 1 says improves, 1 says hurts"), never averaged or voted.
Under D47 each assessment has a **split identity**: a templated existence-claim plus a
free-text statement-claim.

**Rule**: `id`, `when_all: [<feature-ids>]`, `effect`, `then`, `message` + `sources`,
`provenance`. The rule's existence + message is one derived fact.

**Language record** (`language.yaml` + `languages/_registry.yaml`): the registry is the
mint authority for language ids (community-conventional ASCII: `cpp`, `csharp`,
`javascript` — not `js`). Registry/record fields accumulated across decisions:
`language_kind: general-purpose | domain-specific` (default `general-purpose`) + free-text
`domain` tag (open vocabulary in practice — map onto existing values first; D50);
`syntax_check: parser | none` (D33); **identification metadata** (file extensions,
first-appeared year — D29, 2026-07-20): ungated registry data pulled as single attributed
data points from PLDB/Wikidata, never passing the admissibility gate; the tier-D citation
is recorded for attribution only.

### 3.5 Canonical claims, templating, normalization (D23, D47, D48)

**Canonical claim** = a single normalized S-expression-like string over node ids and
normalized values, one fixed template per claim kind:

```
instance-exists(fi.rust.pattern-matching, status=present)
instance-field(fi.rust.pattern-matching, since, "1.0")
characteristic(fi.rust.pattern-matching, c-exhaustive, sha256-16=<hash of normalized sentence>)
edge-exists(edge.requires.ownership.move-semantics)
edge-polarity(edge.influences.algebraic-data-types.pattern-matching, +)
quality-assessment(edge.affects-quality.ownership.learnability, <assessment-key>)
rule-exists(rule-laziness-needs-purity, sha256-16=…)
syntax-valid(fi.rust.pattern-matching.sx.basic-match, sha256-16=<hash of normalized code>)
```

Value normalization before hashing: strings NFC + trimmed + whitespace-collapsed;
free-text sentences additionally lowercased and stripped of terminal punctuation
(**copyedit-tolerant hashing**, D23 — typo fixes don't mint new fact ids; a semantic
rewrite does); dates ISO-8601; version values verbatim. Dedup at commit time = exact
canonical-claim match; fuzzy near-duplicate detection is a work-queue concern, never an
identity concern. English sentences are *rendered from* claims — claims never derive from
renderings.

**Template registry (D47)**: `ontology/claim-templates/<kind>.yaml`, one file per claim
kind, each carrying a frozen `claim_pattern` (the S-expression grammar —
documentation/CI cross-check only) plus an editable `render:` block (the English
wording), content-hash versioned. Deliberately separate from the `prompts/` LLM registry
— rendering is pure deterministic interpolation, no model call. Change management:
`claim_pattern` edits are ontology-schema surgery through D16/D38 migration machinery;
`render:` wording edits are **always re-rendered** (free, every build),
**blast-radius-surfaced before re-embedding** (`--kind claim-template` on D38's script;
re-embed folds into the scheduled cadence, no on-demand trigger), and **never trigger
re-verification**. Scoped to the five templated claim kinds; free-text kinds rely on
copyedit-tolerant hashing.

**Slug/id minting**: `[a-z0-9]+(-[a-z0-9]+)*`, ≤48 chars, ASCII, no leading digit. Node
ids are minted as the initial slug and never change; slugs may diverge via
`ontology/redirects.yaml`. Feature ids prefer the literature's noun phrase, never
language-specific names.

**YAML normalization** (enforced by `normalize_record` in `tools/validate/`, §7.12):
YAML 1.2, UTF-8, NFC; 2-space indent; keys in schema-declared order; one record per file;
no anchors/aliases/tags; prose in `>-` folded blocks, code in `|` literal blocks;
100-column soft wrap; dates as quoted ISO-8601 strings; keyed lists sorted by `key`;
`sources` lists in authored order (citation order is meaningful); edge file names must
equal their `id` (CI check). Idempotent; runs pre-commit in the agent runner so diffs are
always semantic.

### 3.6 Combination validation, dimensions, cross-cutting, DSLs (D2, D39, D50)

Combination validation in four levels:

1. **Dimension exclusivity** — reads the `exclusivity: exclusive | multi` field on each
   record in `ontology/taxonomy/dimensions.yaml` (default `exclusive`; D39). `exclusive`
   enforces at-most-one-feature; `multi` skips the check entirely. Deliberately **no
   partial/counted mode** ("at most 2 of 4") — permanently; anything more nuanced is a
   Rule entity's job.
2. **Hard pairwise `requires`/`conflicts-with`** — package-manager-style propagation.
3. **Soft `influences` warnings.**
4. **Rule entities** for multi-feature interactions.

Levels 2–4 are feature-pairwise/feature-set machinery, indifferent to dimension shape —
cross-cutting features need no change there.

**The Exceptions resolution (D39)**: the brief's literal `Exceptions:
checked/unchecked/effect-system` layer-3 dimension is mis-specified — renamed **"Error
handling mechanism"**, marked `exclusivity: multi`; the deliberately-excluded "Exceptions"
Concept remains the pedagogical parent that atomized mechanism-features
(`checked-exceptions`, `result-type-error-handling`, `panic-unwind`, …) link under via
`realizes`. This lands as a pre-emptive schema fix before the first layer-3 dimension is
authored.

**DSLs stay in scope in principle (D50)**, evaluated case-by-case per candidate.
`applies_to: [language_kind, ...]` on `dimensions.yaml` (default `[general-purpose]` —
opposite polarity from `exclusivity`, deliberately: dimensions authored against the
general-purpose research phase need no edits and are widened only when confirmed
universal; the same field name works as a rarer per-feature override). The questionnaire
compiler reads `applies_to` mechanically and never emits a sweep item for an unreachable
(language, feature) pair; such cells derive a `no-record` reason `not-applicable` at
build time (§6.6). Litmus test distinguishing this from a banned per-language evidentiary
guess: would a `challenge-fact.yml` on the cell make sense?

### 3.7 Versioning: `since` (D2, D25)

A `since` field on feature instances is sufficient versioning — but the verifier must
check the cited source actually supports the `since` value, and a dedicated later
pipeline **back-dates** `since` to the earliest supportable value: monotone earlier-only,
source-first through the normal gate, tagged `since_status: as-cited | back-dated`
(`earliest-known` is deliberately not claimable); batch-run per language after its sweep
stabilizes, re-run when new sources for that language enter the corpus. Claude is
consulted only for ambiguous cases (a feature existing earlier in restricted form is
usually a new, distinct fact, not a back-date).

---

## 4. Sources & citations (D3, D14, D37, D51 — brainstorms 02, 15, 28, 43)

### 4.1 Source records

- Canonical bibliographic format: **CSL-JSON field vocabulary authored as YAML** in
  `sources/`; human-readable slug IDs (`vanroy-haridi-2003`); generated `.bib` export for
  academics. LangAtlas extras under the `custom` key: `tier`, `archive_url`, `accessed`,
  `added_by`, `locator_kinds` (which locator grammars are admissible for this source),
  `edition` + optional `edition_check_url` (D37), `canonical_source` flag +
  `acquisition_note` (D37), `grounding` (D51), `superseded_by` (edition tombstoning).
- **Quality tiers**: **A** peer-reviewed/spec, **B** official docs/textbook, **C**
  talks/known community references, **D** blogs/popularity indexes.
- **Verbatim quotes are optional.** When present a quote strengthens verification; when
  absent, verification works from locator + retrieved source text. Quote cap ~50 words,
  ~300-word per-page aggregate warning in CI (D14).
- **Community sources (PLDB, Hyperpolyglot, wikis) are corroboration only** — never the
  sole backing for a fact; CC BY-SA sources are finding aids + corroborating citations
  only, never copied (cells/prose/examples).
- Web sources archived via Wayback SavePageNow on mint; version-pinned permalinks
  preferred. Dedup on mint by DOI/ISBN/normalized URL, then fuzzy title match. New
  sources are minted by agents with automated dedup + tier assignment; registry changes
  are logged, not human-gated.
- **Site citation style: numeric `[1]` superscripts with popovers.**

### 4.2 Grounding (D51)

`custom.grounding: formal-spec | reference-implementation-docs | design-doc |
third-party-reference` (four values — `vendor-dialect-docs` folded into
`reference-implementation-docs`), orthogonal to tier: tier answers document
quality/authority; grounding answers what kind of authority the document holds over the
language's true definition. Default `third-party-reference`; a one-time retroactive pass
classifies D28 **phase-1's six languages only** at first ingestion (phases 2–4 classify
at their own ingestion time).

- Derived per-fact **`basis` rollup** at build time (union of citations' groundings) —
  a descriptive label joining the display-derived-axes family, never a fifth status axis,
  never gating admissibility.
- Design docs (PEPs/JEPs/RFCs/TC39): `grounding: design-doc`, tier per D3 unmodified (B
  once accepted/final, C in-flight); locator grammar row `<doc-kind> <number> ["§"
  <section>]` (e.g. `PEP 634 §Overview`); `doc-kind` stays an open, undocumented-enum
  string indefinitely.
- D4/D24 entailment is unchanged by grounding; the design-doc-intent-vs-current-behavior
  edge case is covered by existing overstated-claim handling (a D44 golden-set coverage
  note).
- Downstream hooks: a **flat shorter edition-check interval for every non-`formal-spec`
  grounding** (no per-implementation-speed variance), and one plain-text popover
  disclosure line when `basis` isn't `formal-spec` (v0 wording as drafted: "Sourced from
  [Python]'s reference implementation's documented behavior, not a formal language
  specification").
- Per-language: Python, R → `reference-implementation-docs` (PEPs `design-doc`); Rust
  splits per claim between the Reference (`reference-implementation-docs`) and the FLS
  (`formal-spec`), preferring the FLS wherever it covers a claim (sweep-agent
  instruction only, no mechanical recheck); TypeScript permanently
  `reference-implementation-docs`; SQL's vendor-dialect substitute (PostgreSQL/SQLite
  docs) `reference-implementation-docs`; Prolog `formal-spec` via Deransart et al. 1996.

### 4.3 Locator grammar (D23/D37 — one grammar, shared verbatim with `source_chunks`)

CI-regex-validated locator *strings*, machine-produced at chunk time and copied into
records verbatim (never manually invented):

| Source type | Grammar | Example |
|---|---|---|
| Book / paper (PDF) | `p. N` \| `pp. N–M` (en dash) | `pp. 492–495` |
| Numbered spec/section | `§N(.N)*` | `§13.2.1` |
| Named chapter/section | `ch. N` \| `§ <verbatim heading>` | `§ Match expressions` |
| Web page / docs | `#<url-fragment>` | `#match-expressions` |
| Multi-page docs site | `<path>#<fragment>` relative to source URL | `reference/expressions/match-expr.html#match-guards` |
| Repo file | `<commit-sha7>:<path>#LN-LM` | `a1b2c3d:src/lib.rs#L10-L25` |
| Video/talk | `t=HH:MM:SS` | `t=00:41:20` |
| Design doc (D51) | `<doc-kind> <number> ["§" <section>]` | `PEP 634 §Overview` |

URL-kind locators **always pin to the archived snapshot**, never the live page.
Multi-entry `sources:` lists keep OR-semantics (a conjunctive `all_required` mode stays
unbuilt in reserve). The verifier joins fact→chunk on `(source_id, locator)` with
page/section-range **overlap**, not string equality. One shared `validate_locator`
routine (§7.12) serves pre-commit, CI, and the verifier. A pending small extension —
`scope: toc | index | full-document` locator kinds for absence claims — is owed whenever
the grammar is next touched (checklist fold-in from topic 41).

### 4.4 Ingestion QA, editions, link-checking, sourcing queue (D37)

- **Extraction-quality harness** in the ingestion CLI: garbled-text detectors
  (encoding/mojibake, OCR heuristics, extraction collapse, length-distribution outliers)
  plus an outline-coverage diff (chunker's `section_path` set vs the source's own ToC).
  Encoding/extraction-collapse failures **hard-gate** promotion into `source_chunks`;
  outline gaps and softer hits produce a structured per-source QA report consumed during
  the developer's existing manual skim. Sources with no machine-readable outline: silent
  no-op.
- **Edition pinning**: a **quarterly** edition-check job (plain page fetch, no
  re-ingestion) opens a triage-queue entry on mismatch, never auto-reingests. Adopting a
  new edition ingests it as a new versioned `source_id`, tombstones the old via
  `custom.superseded_by` (in `sources/_tombstones.yaml`, §5.4), and fires an
  `edition-superseded` staleness trigger on D25's re-verification queue.
- **Monthly link-checker** over URL-locator sources only: resolution, anchor presence,
  content-hash drift as three independent signals. Content drift feeds the
  `snapshot-drift` trigger; a dead live link **never retroactively unverifies** a fact
  verified against its archived snapshot. A single retry suffices before flagging
  `link_status: dead`.
- **Sourcing queue**: one private `sourcing_queue` table with a `kind` discriminator
  spanning pending-source / link-checker / edition-check entries (D41); entries typed
  `not-ingested | partially-ingested | paywalled | access-pending | acquisition-failed`,
  tracking `bounce_count` (budget 2) and `age_days` (14-day alarm). Claims citing
  un-ingested sources park in `pending-source` and auto-resume when the source ingests.
  Genuinely inaccessible sources stay visibly parked indefinitely.
- **Corpus/mirror integrity**: `custom.canonical_source` flag (prefer official
  publishing-body URLs at ingestion) + mandatory `custom.acquisition_note` on every
  non-canonical source (CI-enforced presence); the structural backstop against a subtly
  wrong mirror is the existing multi-source corroboration machinery — the residual risk
  of a single-sourced claim is named, not solved (no extra confidence ceiling). The R1
  initial corpus gets a one-time retroactive backfill of both fields.

### 4.5 Finding aids (D29, D53 — brainstorms 14, 45)

Bulk import of PLDB (public domain) and Wikidata (CC0) as fact content is **rejected** —
D3's corroboration-only rule already forbids it and it would gut the positioning wedge.
PLDB, Wikidata, Hyperpolyglot, Wikipedia are **finding aids only**: coverage checklists
and candidate (language, feature) pairs, never copied into `sources:` or claim text. No
new fact-status tier. Two carve-outs: identification metadata (§3.4, ungated registry
data) and PLDB's language *list* (names only) as a future target-selection input (D34).

**Finding-aid tooling (D53)**: one `langatlas_finding_aids` package, two consumption
modes — `tools/finding-aids/report.py` (`checklist` for R3 batch surveys, `lookup` ad
hoc) and a live **`search_finding_aids`** tool via the provider layer for D5 sweep point
lookups, available to every agent session type, **never on the public MCP**. Per-source
adapters: live throttled/cached clients for Wikidata (scoped SPARQL template) and
Wikipedia (REST API); **monthly-refreshed local mirrors** for PLDB (git-clone-style
mirror of its published repo) and Hyperpolyglot (scoped scrape respecting robots.txt/TDM
opt-outs), all reads served from mirrors for reproducibility. Caching/rate-limiting/
logging ride `RunContext` as a fifth channel. Non-citability enforced three ways: a typed
`FindingAidResult` envelope the fact schema has no slot for; a tool-description caveat
restating D29/D3 once per session; the D31 instruction-pattern scan **from day one**.
`provenance.candidate_source` is populated as advisory bookkeeping;
`mint_identification_source` is the separate explicit path minting a real tier-D
attribution citation (ungated, per D29).

---

## 5. Ontology lifecycle (D16, D38, D39 — brainstorms 22, 29, 30)

### 5.1 Ids, slugs, semver

- **Split immutable node `id` from renameable `slug`** (facts and content keys reference
  `id`; every historical slug lives in `ontology/redirects.yaml`) — renames are PATCH
  events. Adopted before the research phase mints any nodes.
- **One semver in `ontology/VERSION`, defined by fact blast radius**: MAJOR = some
  fact's meaning/validity affected (split/merge/semantic move/removal/breaking schema);
  MINOR = purely additive, auto-bumped by CI; PATCH = cosmetic. `0.x` during the research
  phase; **`1.0.0` is declared by the developer at a coverage threshold of their own
  choosing** — the exit dossier is advisory, none of its bars binding.

### 5.2 Migrations and the casebook

One PR = taxonomy/schema edit + idempotent `migrate.py` + the migrated corpus diff +
machine-readable manifest + agent-drafted impact report; CI replays the script for
determinism; rollback = `git revert`; derived stores are always rebuilt, never migrated.

Casebook defaults (each row's default disposition seeds the drafted `fact_remap`):

- **split** → per-fact disposition (remap + cheap re-verify vs requeue); the old URL
  becomes a **hub page** (not a 301).
- **merge** → mechanical remap + fast-path re-verify; both URLs 301.
- **layer/dimension move** → touches only classification-asserting facts (URLs never
  encode layer/dimension) — requeue those only.
- **removal** → tombstone.

Superseded fact ids always leave tombstones (`derived_from`/`superseded_by`) so challenge
links and chat logs never orphan. **Staleness** derives from migration manifests
(precise) with the `ontology_version` stamp as coarse backstop; staleness is a visible
fact status.

### 5.3 Governance

Ontology MAJORs are the **one human-gated exception** to D1's no-review rule — RFC issue
+ objection window + developer merging on *process* criteria (not content authority);
MINOR/PATCH stay ungated. MAJORs batch ~monthly with an urgent-correction exception.
Objection-window auto-merge is written into the RFC template as the stated successor once
a real expert community exists. No mechanical CI/bot enforcement of the objection window
— trusted to developer process discipline.

### 5.4 Change tooling (D38)

- **Blast-radius script** (`--kind ontology-node | source | claim-template`): computes
  direct/indirect fact references, affected URLs, cost-log-derived re-verification cost,
  downstream artifact touch counts; drafts a starting `fact_remap` from casebook
  defaults — editable, never a blank form. Scope stays facts/edges/rules only
  (`source_chunks`, debate records, chat logs not counted).
- **RFC intake**: a fifth GitHub Issue Form with a `change_type` dropdown routing to the
  casebook row and a required dissenting-evidence field; committed `impact.md` splits
  into an auto-generated section (CI diff-checked against a fresh blast-radius run) and
  an authored rationale.
- **Disposition DSL**: typed `op` (`split | merge | move | remove`) carrying a
  `fact_remap` list of matcher→action entries from a closed four-action vocabulary
  (`remap | requeue | tombstone | untouched`); `migrate.py` is a thin shared interpreter.
  `action: untouched` is a valid implicit default (CI does not require every discovered
  anchor listed); a matcher resolving to **zero** anchors is a hard CI failure.
- **Tombstone resolution**: migration tombstones extend `tombstones.yaml` (one added
  `migration_id` field); one shared depth-capped chain-walking routine serves the Astro
  build (static never-404 tombstone pages; hub pages for splits) and MCP (`get_fact` on a
  dead id returns `{status: superseded, successor(s), chain}` with successor content
  inline under the caution contract; `get_feature` on a split's old node id returns the
  hub content directly in normal feature-object shape; `get_source` auto-walks to the
  latest edition transparently).
- **Source tombstones**: `sources/_tombstones.yaml` reuses the identical schema one
  level up, adding op `supersede` and action `flag-stale` (the only action never touching
  fact content/id/verification), written automatically by the quarterly edition-check job
  — job-triggered and ungated, vs the RFC-gated `ontology/migrations/`.
- **Diff visualization**: a build-time static diff table/tree (nodes
  added/removed/renamed/split/merged/moved, fact-disposition counts), generated once and
  reused for RFC review and a public **`/changelog/ontology/<migration-id>/`** page (one
  static page per migration, its own top-level site-IA slot).

---

## 6. Verification & trust model (D4, D24, D25, D44, D45, D49, D54, D59 — brainstorms 11, 12, 36, 37, 41, 46, 56)

### 6.1 Grounding rules (D4)

- **Source-first workflow**: an agent may not assert a fact without `source_id` +
  `locator`; priors guide search but only sources make facts
  (`claim_origin: prior | source-derived`).
- **Independent verifier**: a context-blind checker validates that the located source
  text supports the claim — including its `since` value. Unverified claims cannot enter
  the canonical store; with no human merge gate, this gate is load-bearing.
- **Agent-generated text is never itself citable** — prevents the self-backing net from
  becoming self-referencing (risk K1).

### 6.2 The verification pipeline (D24)

The gate is a pipeline of increasingly expensive filters, not one LLM call, run as a
nightly batch. **Index-only evidence**: the verifier reads exclusively from the
`source_chunks` table (§8.2), never live-fetches at verdict time — reproducible verdicts
against content-hashed snapshots; proposer and verifier read the same text; one
compliance point (the ingestion fetcher). Un-ingested citations park claims in
`pending-source` (§4.4). One escape hatch: a registry-existence-only check for citations
whose claim *is* the source's existence.

Per (claim, citation) pair — the verifiable unit; a field with three sources yields three
pairs:

```
0. schema + referential checks (plain code): source_id resolves? locator shape valid?
1. evidence resolution: ingested? → pending-source | locate chunks at locator
   resolution ladder: exact locator match → containment (range overlap) → scoped hybrid
   retrieval as a BOUNCE HINT only (a strong hit far from the claimed locator =
   locator-not-found + hint; rescue never silently passes a wrong locator)
   small-to-big: offer parent_section text when the chunk is <~300 tokens / mid-argument
2. quote fast path (only if quote present): NFKC-normalized token-level fuzzy match —
   ≥0.90 pass, ≤0.80 quote-mismatch, LLM adjudicates between (OCR vs fabrication);
   a miss at the locator searches the whole source (quote-found-elsewhere annotation,
   locator auto-correctable). Mechanical extras: `since` token-presence precheck,
   quote-cap compliance.
3. entailment (university-API LLM, context-blind): claim DECOMPOSITION into atomic
   assertions (presence, syntax form, since, qualifiers), each marked
   supported/not-supported/contradicted with a grounding span; overall verdict by fixed
   rule; structured JSON, temperature 0. A matched quote NEVER waives entailment —
   quote-real-but-overstated is the core K1 laundering pattern.
4. verdict recording: private build-side ledger (never written into authored YAML, D23);
   batch-transcript anchor recorded; fact status updated per the admissibility rule.
```

**Verdict vocabulary** per pair: `source-unavailable | locator-not-found | supported |
partial | unsupported | contradicted` (six verdicts; `quote-mismatch`/
`quote-found-elsewhere` are stage-2 annotations, not verdicts).

**Admissibility rule**: a derived fact enters the canonical store iff **≥1 citation is
`supported` from a tier-A/B source** (C/D corroborate only). `partial`-only facts bounce
once for claim narrowing; `unsupported`/`contradicted` never enter and bounce with
rationale. A `contradicted` verdict on a *secondary* citation of an otherwise-supported
fact admits the fact but mints a contradiction record (§6.5) and feeds the controversy
assessor. `partial` verdicts are logged in an identifiable, filterable way for manual
inspection; `verified-with-partials` stays provenance-only (no extra site marker).

**`since` semantics**: entailment distinguishes *since-supported* (source supports the
exact origin) from *as-of-supported* (source only bounds from above — a legitimate
`partial`: presence enters, `since` gets `as-of` status and lands in the back-dating
queue, §3.7). This dissolves the largest class of false rejects.

**Models**: primary `deepseek` (reasoning off); escalation to `deepseek-thinking` on
`partial`/`contradicted`/inconsistent per-assertion output (~5–15% of pairs); `mini`
(gpt-oss-120b) as a **cross-family second opinion on ~10% of `supported` verdicts** —
a drift gauge (rising disagreement = earliest rubber-stamping signal). Claude is never in
the verification loop (D6), except as a manual developer spot-check instrument. If
measured false-accept misses target, the `mini` sample hardens into a mandatory second
vote for `supported`.

**Context blindness is structural**: the verifier is a separate batch process whose input
is whitelist-built — `{fact_id, canonical claim text, since, source_id, locator, quote}`
only; never notes, `claim_origin`, proposer identity/persona, debate/chat context, or
other citations' verdicts (pairs judged independently). The verifier has **no tools**
(pure text-in/JSON-out; retrieval done by the runner beforehand); evidence text is
delimited as data (§7.8); a lexical scan flags instruction-like patterns into the
transcript.

**Calibration**: committed golden set (~200–300 stratified items, §6.4), targets
**false-accept ≤2% / false-reject ≤10%** (extreme cost asymmetry: an FA poisons a public
RAG-recycled corpus; an FR costs one retry), rerun on any verifier prompt/model change;
per-batch **known-bad canaries halt the batch on a pass**; the **measured error rates
are published** on the site as an honesty feature (and in the bundle manifest).

**Cost/throughput**: ~4–6k tokens and ~1.15 university-API calls per pair;
~1,000–4,000 pairs per 8-hour overnight window at concurrency 4 — verification is not
the bottleneck; cash cost zero.

**Logging**: one transcript per verification batch (`<date>-verify-<slug>-<seq>`),
per-claim `#msg-N` anchors in the manifest; ledger verdict blocks carry
`{verdict, per_assertion, model, prompt_version, run_id, anchor, date,
evidence_chunk_ids}` so verdicts are re-derivable and each fact's "AI chat" link lands on
the exact entailment exchange.

**Completeness-check method (D49)** — for `status: absent` claims, extending the same
ladder and verdict vocabulary: (1) tier-A/B + locator resolution; (2) a corpus-wide
negative full-text grep across every chunk of the cited source using the feature's
`aliases: []`; (3) an inverted-framing entailment stage verifying the agent's own
`absence_scope` argument rather than searching for a supporting quote. A source that
actually documents the feature yields `contradicted`, blocking admission — guarding the
inverse of K1 (false-absence laundering). Absence confidence caps at `medium` on a single
source (§6.3).

### 6.3 Status axes, confidence (D25)

Fact status is **three orthogonal axes**, never one lifecycle:

1. **`verification`** — `unverified | verified | partially-verified | failed` (fold over
   per-pair verdicts; `failed` exists only transiently in queues, never on the site).
   "Verified" always means **machine-verified** — no human-endorsement state exists;
   absence of challenges proves nothing (D9).
2. **`freshness`** — `fresh | stale`, from migration manifests with the
   `ontology_version` stamp as backstop; clears automatically when re-verification lands.
3. **`dispute`** — `none | contradicted | superseded`, a derived read of currently-open
   contradiction records + tombstones.

A single **display status** is derived by fixed precedence: `superseded > stale >
contradicted > partially-verified > verified > unverified`. GitHub challenge state is
**never** stored in canonical YAML — derived at build time only
(`challenge_activity: {open, resolved, last_activity}` ships in the bundle as a separate
value). **`partially-verified` facts render publicly with a visible badge** — never
suppressed.

**Confidence** is an ordinal `high | medium | low` derived by lookup — never
hand-edited, never numeric:

| Level | Rule (first match) |
|---|---|
| `high` | verified; ≥1 tier-A/B source fully supports; ≥1 additional *independent* corroborating source (any tier) |
| `medium` | verified; exactly one tier-A/B source, uncorroborated — or tier-C sole backing with ≥1 independent corroboration |
| `low` | verified; tier-C sole backing uncorroborated — or `partially-verified` at any tier |
| (none) | `unverified` facts carry no confidence value |

Independence: two sources corroborate independently only if they share no author and no
publisher/venue (mechanically checkable from CSL records; borderline defaults to *not*
independent). Community/tier-D sources can lift a level but never establish verification.
Confidence never decreases from challenges or controversy (those are other axes); it must
be explainable in one rendered sentence.

**Re-verification** is event-driven — migration manifests, source-snapshot drift
(the fact **stays verified against the archived snapshot** while queued for refresh),
challenge resolutions, verifier MAJOR bumps (oldest-verdicts-first under budget),
back-dating runs, `edition-superseded` (D37) — plus an **18-month rolling backstop
sweep**, oldest/weakest-backed first, budgeted ~200 facts/night.

### 6.4 Controversy score (D21, D25) and golden sets (D44)

**Controversy** is an ordinal score assigned by a dedicated assessor agent. **Four
levels** (level 4 folded into 3 at ratification):

| Level | Name | Semantics |
|---|---|---|
| 0 | `settled` | No disagreement signal anywhere |
| 1 | `noted-variance` | Weak, resolved signals: debate converged after revision; clearly-outweighed minority assessment/partial verdict |
| 2 | `contested` | Live disagreement inside the pipeline: debate-resolved conflicts with standing dissent; credible-but-unequal quality-spread; partials on load-bearing fields |
| 3 | `disputed` | Non-convergence: escalated/unresolved debate, standing contradiction record, conflicting verdicts across admissible sources — including genuine field disagreement between independent tier-A/B sources |

Assessor = university-API `thinker` (deepseek-v4-pro-thinking) over a fixed rubric and
**structured inputs only**: debate records, reconciler conflicts + contradiction
register, verification verdicts, mechanically-computed source-strength context,
assessment spread. **Explicitly excluded: everything human-challenge-derived** — GitHub
activity, and (per the 2026-07-20 withdrawal) even a contradiction record's
`closure_attempt.outcome: confirmed-open`; open contradiction records feed the assessor
only through their machine-produced content. Claude is the golden-set calibrator and the
escalation target for adjacent-level ambiguity and **all level-3 assignments**. Runs
event-driven in nightly batches (unchanged inputs ⇒ unchanged level). Output is a
machine-written block in the canonical record (absent block = level 0) whose `signals`
list of machine references **is** the justification — no free-prose rationale. The
controversy assessor never mints contradiction records. Presentation thresholds belong
to the site.

**Golden-set methodology (D44)** — one shared perturbation taxonomy, **13 strata**:
correct; **overstated claim** (first-class, separately reported — the only stratum
exercising `partial`'s intended meaning and the K1 defense); fabricated locator; wrong
`since` off-by-one; wrong `since` off-by-major; contradicted; right-claim-wrong-source;
category error; fabricated feature-instance combination; quote-mismatch;
quote-found-elsewhere; OCR-noisy; paraphrase-heavy correct. Construction: LLM-generated
candidates (volume, decorrelated from the verifier model) curated by the developer during
R1 QA skims; ~40% correct / 60% wrong, overstated-claim and wrong-`since` over-weighted.
**Contamination defense** is structural: perturb toward counterfactual,
specifically-invented wrongness (invented version numbers, swapped similar-language
attribution, altered loci) rather than famous-facts-stated-wrong; obscure-locus
targeting; the cross-family sample doubles as a passive contamination gauge; a ~10–15
item fully-developer-authored held-out audit slice. **Controversy cases**: ~50 target via
a bootstrap lane (~15–20 synthetic structured-input cases at project start) + an
opportunistic lane (the Claude-escalation reviews produce real hand-labeled cases);
genuine field-dispute cases minted as opposing tier-A/B literature arrives. **Retrieval
golden queries**: derived-first from the verifier golden set's own correct-stratum
(claim, locator) pairs; hand-authoring reserved for paraphrase-hard and cross-source
bands. Layout: `tests/golden/{verifier,controversy,retrieval,debates}/`,
scored/threshold-gated — distinct from the diff-reviewed
`tests/fixtures/providers/regression/` family. Staleness enforcement on golden items is
soft/log-only. Public benchmark: stretch goal only (if ever pursued: public-sample +
private-held-out split, CC0).

### 6.5 Contradiction register (D45) and the cross-fact scan (D59)

Two record types, one schema, in a root-level content-keyed **`contradictions.yaml`**
(`ctr-<12-hex SHA-256>` over sorted participant ids, so concurrent processes dedup
automatically; mutable `status`; closed records never deleted):

- `type: verification` — a fact vs one of its own citations; low-severity; minted by the
  verifier only when the fact stays admissible via a different citation (a contradicted
  primary/only citation blocks admission and mints nothing).
- `type: cross-fact` — two independently verified facts disagreeing; the rare,
  high-severity case behind controversy level 3 and the site's disputed glyph.

Minting is restricted to the D24 verifier, the D5 reconciler/debate outcome,
human-challenge resolution sessions, and the cross-fact scan job. **`partial` verdicts
never mint records** (mutually exclusive with `contradicted` under the decomposition fold
rule). **Closure**: automated since/version-qualification at mint time (v0 scope:
`since`/`status` comparison only) → `dissolved`, no visible dispute state; auto-closure
on participant correction via tombstone cross-reference; human-challenge adjudication
(qualify / correct / confirm-as-genuinely-open); indefinite `open` is the correct default
for genuine field disagreement, re-checked only on new-source-ingestion events. The live
`dispute` axis is always a derived read of currently-open records.

**Cross-fact scan job (D59)** — catches conflicts between facts admitted in different
runs, which the reconciler can't see. Candidate generation: free same-anchor-family
filtering via record ids, then embedding top-k (k=10–20, cosine floor ≈0.75) from
`knowledge_embeddings` (§8.3). Cadence: event-driven off new-fact commits, plus a rare
backstop re-scan on embedding-model swaps. Comparison call (university API,
`deepseek`/`deepseek-thinking` tiering): a distinct **four-verdict claim-vs-claim
vocabulary** — `no-conflict | qualified-non-conflict | conflict | inconclusive` —
deliberately not reusing the six-verdict claim-vs-source set; the since/version
qualification check folds into the same call for this minting path only (accepted
asymmetry with the other paths). Findings mint straight into `contradictions.yaml`
(`mechanism: contradiction-scan`); surfaced via `report.py cross-fact-scan`; orchestrated
as one more `driver.py` job kind. No cross-family drift sampling at v0. Its comparison
call's golden set routes through D44's methodology when calibration is needed.

Site rendering: verification-type records add one clause to the popover status line;
cross-fact records get a compact "Sources disagree" block in the same popover, riding the
shared base-page glyph. **A dedicated `/disputed/` page is declined** — popover-only
indefinitely. MCP: `get_fact` on a disputed fact inlines the conflicting participant
fact(s) in full, each with its own caution block; `list_contradictions`/
`get_contradiction` ship in the public tool set (§9).

### 6.6 Absence & unknown semantics (D49, D50)

Six states, two categories, preserved on every surface:

- **No record exists** — `not-yet-onboarded`, `not-yet-swept`, `deferred`, plus the
  build-derived `not-applicable` (D50). None are facts: nothing to verify, dispute, or
  embed.
- **A record exists** — `present`, `partial`, `absent`: all the same `instance-exists`
  claim kind differing only in `status`, equally first-class, equally verified. An
  `absent` cell renders as a normal filled cell ("Not present" + sourced summary, same
  fact-popover machinery, distinguished only by a status chip — no visual muting) and
  gets a real feature-instance page.

MCP: exactly two typed response shapes — an ordinary fact object (present/partial/absent
uniformly, full caution block) and a **`no-record` envelope**
`{status: "no-record", reason: not-yet-swept | not-yet-onboarded | deferred |
not-applicable, language, feature}` (no caution block — it isn't a fact; no
`coverage_url` field for now). `search_knowledge`/`get_neighbors` never synthesize an
absence conclusion from a missing hit — the MCP caution text states this explicitly. The
Builder (deferred) must consume the split as three-valued logic, never defaulting unknown
to false.

### 6.7 Human challenges (D9)

- No custom forum. Every fact page has a **"Challenge this fact"** action deep-linking to
  a prefilled GitHub issue form (fact ID, anchor, file path, current value, citations,
  page URL) on the kb repo. The GitHub-account requirement is accepted.
- Resolution loop: challenge issue → agent session re-argues with the debate machinery
  and commits the correction (verification-gated) → challenger @-mentioned → CI rebuilds
  → git history is the audit trail.
- **"Verified" comes only from the machine gate** — never from a fact having gone
  unchallenged.
- **An accepted human challenge is a hard override** (2026-07-20): the re-argued
  correction still enters through the normal verification gate, but no subsequent machine
  verdict may reinstate a value a human challenge overturned.
- giscus-style embedded Discussions as a fast follow (§10.3).

### 6.8 Challenger-round auto-skip (D54) and constraint disputes (D61)

**Auto-skip (D54)** — mechanism designed now, thresholds later (no real "debate changed
nothing" rate exists yet). Initial eligibility, deliberately narrow: layer-1 syntax
claims only × `grounding: formal-spec` backing only × fuzzy-match ≥0.90 × no `since`
back-dating; expansion is per-type on that type's own measured data, never inherited.
Mechanism: a **short-circuit inside an already-triggered D5 debate** (reconciler conflict
detection untouched; only the challenger/moderator sub-step is skippable, and only after
the pre-challenge draft clears the verifier at the required tier). `replay_verdict` gains
stratified logging (claim type × grounding × fuzzy-match bucket), a widened
undebated-facts denominator, and a D44-taxonomy-tagged breakdown of what changed in
debates that did matter. Rollout: **shadow mode first**, then live with a permanent kill
switch and a **never-tapering audit sample** (initial fraction anchored to D4's 5–10%
spot-check / D24's ~10% cross-family sample). Governance: a small versioned
`config/auto_skip.yaml`, changed only by explicit developer decision recorded in
decisions.md.

**Constraint-violation resolution (D61, superseding D46's "no separate path")** — when a
sweep answer mechanically violates a `requires`/`conflicts-with` edge or Rule: the D5
debate machinery still adjudicates whether the evidence on each side is solid and whether
a since/version qualification dissolves it. One-side-weak resolves as an ordinary fact
outcome (reject/qualify the weak claim). A new outcome, **`constraint-disputed`**
(evidence solid on both sides, nothing dissolves it), lands a pre-filled
`constraint-dispute`-typed **RFC issue draft in a work queue for manual promotion**
(never auto-opened) — "is the ontology rule itself wrong" belongs to D16's human-gated
carve-out. The FeatureInstance records land and render visibly flagged throughout, never
blocked.

---

## 7. Agent pipeline

### 7.1 Model tiering & budget (D6)

**Claude never does volume; the academic API never has the last word.** Claude handles
schema design, high-judgment drafting, debates, reconciliation, moderation; the
university API + plain code handle bulk drafting, verification/entailment, embeddings.
Budget = full Claude Pro limits + reasonable academic API use + a **small SDK credit pool
reserved for the highest-judgment pipeline steps only** (never bulk; supersedes the
earlier "bulk defaults to Haiku-tier" clause). Track cost-per-accepted-fact (research
phase: cost-per-accepted-node). No deadline pressure; no long-term-damaging shortcuts.

University API environment (chat aliases): `glm`→glm-5.2, `kimi`→kimi-k2.7,
`deepseek`→deepseek-v4-pro (reasoning off), `deepseek-thinking`/`thinker`→
deepseek-v4-pro-thinking, `mini`→gpt-oss-120b, `coder`/`agentic`→qwen3.5-122b.
Embedding/reranking: `qwen3-embedding-4b` (40,960-token context, 2560-dim),
`qwen3-reranker-4b`, `nomic-embed-text-v1.5`/`v2-moe`, `mxbai-embed-large`,
`multilingual-e5-large-instruct`. English-only models are eligible.

### 7.2 Per-language sweep pipeline (D5)

**No free-chat debates.** Independent per-language questionnaire sweeps, source-first; a
reconciler diffs answers; only conflicted cells trigger structured debates (proposer +
2 challengers + fresh-context moderator, ≤6 messages, typed challenges), resolutions
recorded as structured blocks. Personas are real but mild ("the Rust expert," no
engineered biases). Contradictions are first-class records; many dissolve via
since/version qualification. Full provenance on every fact: proposer agent + model +
prompt version, debate id, verifier result, timestamps, optional `chat_run_id`. The sweep
is the mechanism for **adding new languages** after the research phase; at many-language
scale it stays unchanged near the curated set (D34 — no batching/lineage-reuse across
similar languages: it would anchor answers and undermine the reconciler's independence).
Sweep launches are **always developer-initiated by hand**, never cron (D43).

### 7.3 Questionnaire compiler (D46)

A deterministic CLI, `tools/questionnaire/compile.py`, turns the ontology tree into the
sweep questionnaire — never a hand-maintained document, never a live per-sweep
re-derivation. Emits sweep items **only for the four fact-bearing FeatureInstance fields**
(`exists`/`since`/`characteristics`/`syntax`); everything ontology-authored (feature/
edge/rule existence, polarity, quality assessments, `exclusivity`, `layer`,
`cross_cutting`) is never re-asked per language — hard edges and rules compile instead to
a separate `constraints:` list the reconciler validates answers against. Schema:
per-dimension grouped items (carrying `exclusivity` context once) + standalone flat items
for layer-1/2 features; every item's `anchor_prefix` matches the `fi.<lang>.<feature>`
anchor scheme. Six mechanical steps, zero judgment calls. **Language-agnostic spec** — no
per-language candidate filtering (that would be a pre-evidence judgment call), except the
mechanical `applies_to` mask (D50). Drift prevention is structural (no independently
editable questionnaire state); a schema-shape regression fixture (starting `mode: soft`,
D48) guards vocabulary drift. Every compiled spec is stamped with its `ontology_version`
(no separate questionnaire semver in v0; `questionnaire_schema_version` deferred until a
real version has shipped); sweep-run manifests record the spec version answered.
Migration disposition for in-flight answers reuses the D38 DSL via a
**delta-questionnaire diff** (compare two spec versions by `anchor_prefix`; requeue
scoped to exactly the changed anchors). Compiled output is a **committed artifact**
(diffable in git). Invoked on demand at R6/first-sweep-launch and at each onboarding
phase start — never cron.

### 7.4 Frontloaded research phase (D11, D27 — brainstorm 25)

The research phase turns the brief's seed sketch (layer lists + Jordan et al. 2015) into
**ontology v1.0**: sourced, debated, layered nodes stable enough for sweeps. Every node
must be source-backed (priors steer only *where to look*); the phase designs features,
not instances — languages appear only as reality checks.

**Subphases R0–R6**, with a repeating per-theme R3→R5 loop:

| # | Subphase | Nature |
|---|---|---|
| R0 | Infrastructure preflight | ingestion CLI + `source_chunks`; `ontology/` scaffolding at `0.1.0` with id/slug machinery + schemas (brainstorm 09 and 28's locator grammar are R0 prerequisites); D18 logging; D13 validators; provider wrapper with cost logging. Exit test: "an agent can run `search_sources`, mint a node file that validates, and the run is logged." |
| R1 | Corpus assembly & ingestion | D15 seed list + language specs + acquisitions, per-source extraction QA; the developer's QA skims double as golden-set co-authoring time |
| R2 | Embedding benchmark (D22) | on a pilot corpus (3–4 sources), §8.6 |
| R3 | Thematic survey (divergent) | per theme (~12: typing; memory management; concurrency; higher-order programming; ADTs & pattern matching; modules; metaprogramming; evaluation & parameter passing; effects & exceptions; dispatch & inheritance; syntax-layer constructs; qualities vocabulary — the final theme list is itself an early R3 deliverable): university-API bulk passes tag corpus chunks with candidate terms; a Claude surveyor synthesizes a candidate inventory, each entry with 1–3 evidence chunks and cross-book aliases. **Each cycle's theme list requires explicit developer sign-off before the cycle runs.** |
| R4 | Ontology drafting (convergent) | a Claude ontologist atomizes candidates into nodes, assigns layers/dimensions, drafts edges, every carve annotated with evidence; contested carves go through the D5 debate machinery with schema-dispute challenge types (`wrong-atomization | wrong-layer | missing-source | redundant-with | scope`) |
| R5 | Language reality checks | a **rotating 4–5-language sample per cycle** (paradigm spread) classified against draft dimensions — surfacing unmappable features, uninhabited dimension values, unfittable languages; also the deliberate shakedown of the sweep pipeline (questionnaire format, verifier, commit protocol) at small scale; each session emits `research/reality-checks/<cycle>-<theme>.yaml` |
| R6 | Consolidation & exit dossier | cross-theme edge pass (per-theme work systematically under-collects boundary-crossing edges), dedup/alias audit, slug polish, dossier recompute |

**Agent role loadout**: corpus tagger (university API, embarrassingly parallel);
surveyor, ontologist, challengers ×2, moderator, edge drafter, source scout (Claude —
kept as separate roles; a merged "researcher" would carve to match its own harvest);
verifier + coverage auditor (code + university API). Web content = data, never
instructions.

**Graduated 0.x minting ceremony (vs full D16)**: from the first node — immutable ids,
content keys, schema+referential validation, logging; while a theme is in active
iteration — restructures are ordinary commits, CI auto-bumps MINOR, splits/merges need
only a redirect/tombstone line; once a theme passes R5 it is **settled** — restructures
need a lightweight migration manifest but no RFC; the full RFC-gated D16 process switches
on at `1.0.0`.

**Source strategy**: curated-corpus-first. Seed = the D15 list + Jordan et al. (2015) +
the D28 language specs. **Acquisitions (ratified in full)**: Scott *Programming Language
Pragmatics*; Turbak & Gifford *Design Concepts in Programming Languages*; Harper *PFPL*
(free); Krishnamurthi *PLAI* (free); Sebesta *Concepts of Programming Languages*;
Kaijanaho 2015 (free thesis — empirical evidence for quality edges). Gap-driven internet
scouting (typical for post-2010 features) into papers and official design docs (Rust
RFCs, PEPs, JEPs), batched per theme; paid titles via university library access.

**Exit dossier** (five items after the D27/D52 amendment dropped external-checklist
coverage): sourcing integrity (100% of nodes with ≥1 verified tier-A/B
existence/definition fact; edge verification %; pass-rate trend); reality-check results
(advisory bar: <5% unmappable in the final cycle; zero exclusivity violations); churn
trend (settled-theme restructures ≈ 0 across the last two cycles); graph health (orphans,
degree distribution, cross-theme edge coverage); pipeline readiness (eval green, R5
shakedown issues closed, compiler producing valid sweeps). **All bars advisory** — the
v1.0.0 declaration is the developer's discretionary judgment.

**Budget sanity**: R3+R4 ≈ 2–3 Claude sessions × ~12 themes ≈ 30–40 sessions, plus
~10–15 for debates/R5/R6 — spreadable over weeks under Pro limits. University-API work is
overnight-batch and effectively free. The largest engineering cost is R0/R1 (~1–2 focused
weeks ingestion + 0.5–2 h QA per book).

**Handoff artifacts to the sweep pipeline**: ontology v1.0.0; the compiled questionnaire;
the ingested + QA'd corpus incl. language specs; the benchmarked retrieval stack; a
shaken-down verifier and commit protocol. Post-1.0 carve failures re-enter as ordinary
D16 RFCs. The fact-index embedding decision is deferred to sweep-pipeline start.

### 7.5 Initial language selection (D28 — brainstorm 34)

**15-language curated set** — TIOBE July 2026 top 10 minus SQL and Visual Basic, plus
Haskell, OCaml, Prolog, Erlang, Elixir, Go, Swift — onboarded in phases that are
**strictly sequential** (later phases gated on completing earlier phases' sweeps, even
post-1.0.0):

- **Phase 1 — ontology stress set (6)**: Python, C, Java, Rust, Haskell, Prolog — every
  layer-3 dimension gets ≥2 distinct values inside this phase alone; cheap free
  references mature the ingestion pipeline first. Prolog's tier-A backing: Deransart,
  Ed-Dbali et al., *Prolog: The Standard Reference Manual* (1996) — acquired; no ISO/IEC
  13211-1 purchase needed.
- **Phase 2 — mainstream weight (4)**: C++, C#, JavaScript, R — highest sweep/ingestion
  cost, run against a phase-1-hardened ontology.
- **Phase 3 — landscape completers (5)**: OCaml, Erlang, Elixir (both BEAM/actor
  representatives get language pages), Go, Swift — functors/effect handlers, actors,
  CSP + structural interfaces, ARC + protocol-oriented design; all free
  permissively-licensed references.
- **Phase 4 — optional cheap completeness**: Visual Basic (near-zero novel facts;
  restores literal "TIOBE top 10 covered").
- **Phase 5 — SQL** (D50): gated on the `language_kind`/`applies_to` schema and the
  greenlit PostgreSQL/SQLite vendor-dialect sourcing substitute; otherwise undesigned.
- **Deferred, revisit post-1.0**: TypeScript (no normative spec), Scheme/Racket,
  APL-family, Julia.

Oz and Coq/Rocq stay **concept-source-only** (facts sourced at feature level from CTM /
*Software Foundations*; no language pages, no sweeps). Spec editions: pin the **latest
available** per language (C23/N3220; JLS SE 25; current ECMA-262; Haskell 2010 + latest
GHC guide), re-pinning as editions ship. All languages have bundled Shiki grammars.
Positioning line: "the most-used languages of the TIOBE top 10, plus the languages that
define the rest of the feature landscape."

**Onboarding checklist (D57)**: a markdown template (nine items: selection sanity —
narrative only; license/access class; grounding resolution; `language_kind`/`domain`;
Shiki-grammar presence; `syntax_check` mode; source-record fields; ingestion-cost note;
phase sign-off), copied per language and filled at onboarding start; items that are
schema fields just point at the field (schema + validator remain the enforcement
surface). **Nested under `context/`** (amended from `ontology/onboarding-checklists/`);
the D48 required-field-presence fold-in was dropped (both items stay manual). **Build
deferred until closer to D28 phase 2/3.**

### 7.6 Provider abstraction (D26 — brainstorm 13)

One thin policy layer, two channel types, no frameworks. **Completion channel**
(university API + future local models): plain `openai` Python SDK with `base_url`
swapped (the gateway is OpenAI-compatible; auth `x-litellm-api-key: Bearer TOKEN`; model
metadata at `/v1/model/info`); LiteLLM rejected; rerank is a small hand-rolled `httpx`
call (no `/v1/rerank` route documented). **Claude channel**: stays agentic via the
Claude Agent SDK / Claude Code sessions, never flattened into `chat()`. Both share one
policy core, **`RunContext`**, which owns: the D18 transcript writer, the cost log (same
code path so they can't disagree), budget enforcement (`max_calls/tokens/wall_seconds`
per run manifest, hard-stop with resumable checkpoint), and a SQLite content-addressed
cache keyed on resolved-model-id + messages + sampling + schema + `prompt_id@version`.
**There is deliberately no way to call a provider without a `ctx`** — that is what makes
logging non-bypassable. Structured output via a per-alias **probed** capability table
(`config/provider_capabilities.yaml`; schema-constrained decoding where supported, else
json-mode + pydantic validate + one repair turn + one retry). Rate limits: none
documented — conservative token-bucket default set at implementation time. Alias drift:
pin the resolved model at run start, abort on drift. Local-model config space reserved
(schema only). Cache lives inside the D15 snapshot store (same backup). Pure Python
library in `langatlas-kb`, no daemon; record/replay fixtures at the wrapper interface.
Out of scope: streaming to UIs, tool loops on the completion channel, multi-provider
routing, fine-tuning, exact tokenization, queueing.

### 7.7 Prompt registry & observability (D41 — brainstorm 32)

No new service or dashboard: `tools/observability/report.py` (subcommands `cost`,
`verifier`, `debates`, `sourcing-queue`, `capabilities`, `verifier-drift`, plus D59's
`cross-fact-scan`) reads the transcripts repo, the cost log, and the private verification
ledger; output is **ephemeral markdown** (stdout / gitignored snapshot), never committed
— the bundle manifest already publishes the one legitimately public number (verifier
error rates). **Prompt registry**: `prompts/<prompt_id>/v-<8hex-content-hash>.md`,
content-addressed versions with a human-readable alias in a per-prompt CHANGELOG; new
versions trigger a soft (log-only) regression re-run. Capability probes run **monthly**
via `probe_capabilities.py` (diff-and-flag, never auto-commit). **Claude usage-limit
telemetry**: a typed reactive `ClaudeLimitSignal` (no proactive quota API exists on Pro)
raised by the Claude channel, logged, distinguishable from self-imposed budget stops.
Shared library function `replay_verdict` serves both debate instrumentation (D30) and
bulk verifier-drift reporting (and D54's stratified logging).

### 7.8 Prompt-injection posture (D31 — brainstorm 17)

Fetched web/source content is **data, never instructions** — the verifier's
delimiting convention generalized project-wide, enforced once inside `RunContext` (not
per-prompt discipline), plus a cheap shared lexical instruction-pattern scan on every
fetch/search tool result, logged per D18. Flagged hits **always log-and-continue**, never
hard-block. A dedicated low-privilege reader/actor split and a parallel
injection-specific gate are rejected (bounded severity: no private data, no exfiltration
channel, git history makes landed bad facts discoverable/revertable); the split is the
escalation path if logged flags become evidence of real manipulation. The
delimiter/scan convention is documented in the wrapper implementation notes, no separate
spec doc. The R3 live-web-fetch tool may run its first iteration without the wrapper
treatment (retrofit before it's relied on heavily) — except `search_finding_aids`, which
gets the scan from day one (D53).

### 7.9 Agent-runner commit protocol & failure bot (D36 — brainstorm 27)

- **Landing**: persistent local clone; `git fetch` + `git rebase origin/main` +
  fast-forward-only push; retry on non-fast-forward, give up after **5 retries or 3
  minutes** → `contention_exhausted` (never loops forever, never drops the record).
  Per-file sharding keeps the common case a content-free rebase.
- **Identity**: a narrowly-scoped GitHub App, `langatlas-bot[bot]` — `Contents: write`,
  `Issues: write`, `Checks: read`, `Statuses: read`; deliberately **no PR scope**. A
  second, separately-scoped App is confirmed for the future external-PR skim; a third for
  the eventual Discussions bot (D55). Token refresh owned by `RunContext`, never logged.
  DCO: a documented CONTRIBUTING carve-out treats the App installation as the one-time
  sign-off; per-commit `Signed-off-by:` is for human PRs only.
- **Granularity**: one commit per touched record file, with trailers
  `LangAtlas-Record-Key` (content hash + path — the idempotency key) and
  `LangAtlas-Chat-Run-Id`.
- **Is-main-green gating**: only the final push checks `main`'s CI status;
  prep/verification proceed regardless; on red/unknown the record holds in a local
  ready-to-land queue → `blocked_red_main` (time spent blocked is exempted from the run's
  budget/wall-clock hard-stop). The runner never fixes a red main itself.
- **Auto-revert requires all four**: failing commit is main's tip; author is the bot;
  deterministic validator failure reproduced once; `git revert` applies cleanly — else
  halt + file an issue. Circuit breaker: **2 reverts per run**. Content disputes,
  controversy flags, and anything the verifier gated are out of scope — those land and
  render visibly flagged.
- **Interface**: typed `LandResult` union — `landed | blocked_red_main |
  contention_exhausted | reverted | unsafe_halt`. Idempotent resume = check the
  `LangAtlas-Record-Key` trailer against main's reachable history before any push.
- **Multi-runner**: no queue now (optimistic retry); a Contents-API `RUNNER_LOCK` lease
  is the named escalation. External-PR abuse: GitHub's native first-time-contributor
  approval setting; the "provenance/scope skim" = three mechanical checks (permitted file
  types, single-topic PR, resolvable bibliographic identifiers) as a validator-CLI
  extension.

### 7.10 Chat logging & transcripts (D18 — brainstorm 24)

Capture from day one (cannot be retrofitted): the provider wrapper persists every call;
Claude Code/SDK runs export through the same normalizer; one run = `manifest.yaml` +
`transcript.jsonl`, `run_id = <date>-<kind>-<slug>-<seq>`, `debate_id` maps 1:1.
Storage: the public **`langatlas-transcripts`** repo (JSONL sharded `YYYY/MM/<run_id>/`,
one commit per run; ~hundreds of MB/year). Pipeline-run logging mandatory; interactive
sessions opt-in. Redaction: content-only logging, secret scrub + gitleaks CI, large
fetched-source tool results truncated to excerpt+hash (copyright), system prompts
published, escaped-text viewer only; **force-push escape hatch** allowed only for
secret/copyright/takedown incidents, each recorded in a public `REDACTIONS.md`
(category taxonomy broadened to takedown-driven rewrites, D42). Fact provenance carries
optional `chat_run_id` → "AI chat" link in the citation popover (v0: raw GitHub link;
v1.5: a noindexed `/chats/<run_id>/` Astro-island viewer). Verification batches: one
transcript per batch with `#msg-N` anchors. Debate-history retrieval for agents:
structured resolution records first (exact-key lookup); a `chat_chunks` index +
pipeline-only `search_debate_history` tool is v2, parked until real volume exists (D60).
License: **CC0 1.0** (D42), distinct from the corpus's CC BY-SA 4.0; embedded third-party
excerpts remain governed by their rightsholders.

### 7.11 Run orchestrator & scheduling (D43 — brainstorm 35)

A thin driver library, `tools/orchestrator/driver.py`, no daemon: enumerate work items →
call provider layer / commit protocol → interpret typed result → checkpoint →
continue/pause/halt; parameterized per job by a batch-spec YAML in `config/jobs/`
(`kind`, `work_item_source`, `budget`, `checkpoint_path`). One invocation = one
`RunContext`-scoped run; a new job kind = one enumerator function + one YAML. Checkpoint
grain = whatever the job's work-item source enumerates (sweep cell, theme, fact, source);
storage = a local private non-git SQLite file (driver bookkeeping only — the
`LangAtlas-Record-Key` git trailer stays ground truth, so checkpoint and repo state can
never disagree). Budget hard-stops: `RunContext` raises typed `BudgetExceeded` before
crossing a cap; in-flight item checkpoints as `blocked`; resume = plain re-invocation.
`ClaudeLimitSignal` → a conservative fixed **4-hour cool-down** before resume; too-early
re-invocation no-ops. Alerting = the run halting + `orchestrator/status.json` (one more
`report.py` subcommand); no cron mail, no notification service.

**Scheduling**: plain cron on the developer's machine; a committed
`config/jobs/crontab.example` documents intended cadence. **Full periodic-job inventory**
(2026-07-20): nightly verification/controversy batch; monthly link-checker,
capability probe, finding-aid mirror refresh, and Umami `demand` export; quarterly
edition-check; the 18-month backstop sweep (checked monthly, no-ops until due).
Event-driven work (contradiction scan, re-verification triggers) rides commit/pipeline
events, not cron. Sweeps are always launched by hand.

### 7.12 Validator/normalizer CLI (D48 — brainstorm 40)

Library-first package `tools/validate/` (module `langatlas_validate`) with a thin
`cli.py`; installable console script via `pyproject.toml [project.scripts]` (uv-in-Docker
packaging). Three call-site contracts:

- `langatlas-validate precommit <files…>` — fast, scoped to touched files + direct
  referential neighbors; **always phase-1-only locator checks** (no auto-upgrade even
  when Postgres is reachable); refuses to commit on nonzero exit.
- `langatlas-validate ci` — full corpus scan, phase-2 locator resolution, fact-id
  collision check, migration-manifest validation, full regression run.
- `from langatlas_validate.locators import validate_locator` — imported directly inside
  the verifier's stage-2 step with its own open `SourceChunksIndex` handle.

`validate_locator` is two-phase: `validate_locator_shape` (pure regex vs the grammar
table, zero I/O, always) and full resolution against `source_chunks`
(dependency-injected). Migration-manifest checks: matcher resolvability (zero-anchor
matcher = **hard CI failure**), target resolvability, per-op required fields, closed
action vocabulary scoped by ledger kind, `impact.md` auto-section diff-check; explicitly
does **not** require every discovered anchor in `fact_remap`. One regression-fixture
convention (`fixture_id`, `kind`, `mode: hard|soft` as fixture metadata) under
`tests/fixtures/providers/` with one runner (`langatlas-validate regression run`) and a
pluggable checker registry (`provider-record-replay`, `schema-shape`,
`questionnaire-shape`, `prompt-version-rerun`) — distinct from `tests/golden/`'s
scored/threshold harness. `normalize.py` single-sources `normalize_record` (whole-file
formatting, idempotent; pre-commit writes, CI verifies) and `normalize_value`
(copyedit-tolerant claim normalization feeding fact-id hashing).

### 7.13 Debate instrumentation (D30 — brainstorm 16)

Two cheap zero-new-infrastructure scripts, reusing existing logs: (a) the
**verifier-replay counterfactual** — re-score a debate's pre-challenge draft through the
verifier to see whether the challenger round changed anything detectable (sufficient on
its own for now; the downstream dispute-rate comparison stays deferred until
post-phase-2/3 volume — its selection-effect confound isn't worth accepting early);
(b) a **cost join** computing Claude-messages-per-accepted-fact segmented by `debate_id`.
R4 schema-dispute debate outcomes are also tracked against later D16 MAJOR churn (did a
carve that survived R4 sign-off later get reverted). Regression harness = the D26
record/replay fixtures + a hand-curated regression subset in
`tests/fixtures/providers/regression/`, human-diff-reviewed (not CI-blocking). Scored
golden sets for fact debates wait for phase-1 volume (then D44 owns them).

---

## 8. Data & retrieval stack

### 8.1 Postgres (D7)

**Postgres (+ pgvector + tsvector FTS) from day one — no SQLite serving phase** — under
docker compose. Always a derived, regenerable artifact built from the canonical YAML;
retrieval stays behind a small library interface. Search: filter-first, then hybrid
BM25/FTS + vector fused with RRF, k=5, relevance floor; the university reranker is an
eval-driven upgrade. Eval: committed golden set (30–60 queries → expected IDs), Recall@5
+ MRR in pytest, grown from logged agent misses.

### 8.2 Full-source RAG: `source_chunks` (D15 — brainstorm 21)

The production-side research foundation: a second table in the same Postgres. Ingestion
CLI (Docling-class PDF extraction, trafilatura for HTML) → structure-aware 400–800-token
chunks with breadcrumb prefixes and page/§/anchor locators + `parent_section_id`
(small-to-big expansion) → overnight batch embed on `qwen3-embedding-4b` → hybrid
FTS+vector with RRF and **`qwen3-reranker-4b` default-on**. Extracted text and embeddings
stay out of git (private snapshot store: a plain directory on the dev machine with
periodic tarball backup; revisit when multi-machine). Two pipeline-only agent tools:
`search_sources`, `get_source_section` — never public. Retrieved chunks carry
machine-produced locators that flow directly into source-first claims, and **the
verifier reads the same table** — one index serving discovery and verification (directly
attacks K1). Initial corpus: the developer's collection (Van Roy & Haridi CTM; Pierce
TAPL + ATTAPL; Cardelli & Wegner 1985; two Elsevier papers; *Software Foundations*
vol. 2) + the D28 language specs/docs (official specs/reference chapters only) + the D27
acquisitions. Paywalled papers arrive via university access (agents request, developer
drops the PDF into the snapshot store). Cost at ~30 sources: ~12–20k chunks, ~200 MB;
the real cost is the ingestion pipeline (~1–2 focused weeks) + 0.5–2 h QA per book.

### 8.3 Fact-embedding index: `knowledge_embeddings` (D62 — brainstorm 61)

One table, `chunk_type IN ('fact', 'feature-description')` discriminator; primary key
`(embedding_model_id, chunk_type, subject_id)`; `vector(N)` at the dimension D22's
benchmark selects (HNSW-vs-IVFFlat also deferred to the benchmark); `rendered_text`
(D47's precomputed string) is the exact embedded text; filter metadata `feature_id`,
`language_id`, `status`, `controversy_level`. `feature-description` rows embed the
Feature/Concept `summary.text` field. Embeddings are computed once during the
bundle-build pipeline (via `RunContext`) — but **stay out of the public bundle**
(2026-07-20, reaffirming D13's embeddings-stay-private clause): delivered through the
private tier (the snapshot store), read from there by the loader. Refresh: no calendar
job — incremental re-embed rides bundle-build cadence (unchanged `rendered_text` reuses
its vector via cache keying); a full re-embed falls out free on an embedding-model swap.
Consumers: the contradiction scan (raw cosine top-k) and `search_knowledge` (filtered
hybrid RRF gated to publicly-safe status: `verified` and `partially-verified` pass;
`unverified`/`failed` don't); site search stays Pagefind — a different layer. This table
*is* the loader's embedding-cache lookup table; `RunContext`'s content-addressed cache
stays the separate API-call dedup layer underneath.

### 8.4 Dataset bundle contract (D35 — brainstorm 26)

Two GitHub Release assets per `data-vN` tag (cut **daily, only on days with changes**,
D13): `langatlas-data-vN.sqlite.zst` (zstd SQLite — an interchange format only; live
services still run Postgres) + `langatlas-data-vN.manifest.json`. Three version axes:
`data_tag` (rollback driver), `ontology_version` (provenance/display only), and
**`bundle_schema_version`** (semver over the bundle's own structure; starts `1.0.0` at
implementation; consumers pin a compatibility range and **hard-refuse on MAJOR
mismatch**). Manifest also carries `git_commit`, `built_at`, `embedding_model_id`
(nullable), integrity hashes, per-table row counts, the published verifier error rates,
and a `license` field (D42; plus a `NOTICE.txt` release asset). Tables: a **flat
precomputed `facts` table** (one row per derived fact: `fact_id`, `anchor`,
`canonical_claim`, `rendered_text`, `sources_json`, `provenance_json`, all status axes —
computed once, never re-derived by consumers) + record-shaped tables (`instances`,
`edges`, `rules`, `sources`, `features`, `concepts`, `languages`) +
`tombstones`/`redirects`. Snapshots always full, never incremental (tens of MB
compressed). **MCP lite mode** (bundle-direct, no Postgres, FTS5-only lexical search,
every response tagged `"retrieval_mode": "lexical-fallback"`) is documented but **not
built in v0**.

### 8.5 Postgres loader (D58 — brainstorm 53)

`tools/loader/load_bundle.py`: stdlib `sqlite3` + `psycopg` v3, JSON-in-TEXT → `jsonb`.
**Blue-green**: each load builds into a fresh schema named for the `data_tag`
(`data_v418`) — bulk copy + pgvector/FTS index rebuilds happen there with zero live
impact — then one atomic transaction of `CREATE OR REPLACE VIEW current.<table>` flips
everything; MCP/FastAPI query `current.*` via role grants (roles set up by a separate
compose init script, not the loader). MAJOR bundle bumps need DROP VIEW + recreate.
Pre-swap validation: row-counts-vs-manifest + hand-picked smoke queries only (the
golden-set eval stays a separate pipeline check). Embedding reuse keyed
`(embedding_model_id, fact_id)` — fact-id stability *is* content stability — via
`knowledge_embeddings`; a looser per-fact content-hash match lets unchanged facts skip
re-embedding across an otherwise-changed publish. Rollback: failed build = orphaned
shadow schema (drop, retry); post-swap = reverse view-swap; **exactly two live schemas**
retained (current + previous); deeper rollback re-runs the loader on an older `data-vN`.
Invocation: the site repo's `repository_dispatch` build (when a site-side Postgres
becomes relevant), a scheduled job on the kb repo's own compose stack, and manual local
loads for MCP testing.

### 8.6 Embedding-model benchmark (D22 — brainstorm 25 §O4)

A dedicated research-phase subphase (R2), on a pilot corpus. Candidates: the
university-hosted models (§7.1) + one local-CPU fastembed representative as the
"does free-and-local suffice" floor; short-context models tested honestly
(breadcrumb-prefixed chunks truncated as in production). Use cases: source-corpus
retrieval (benchmark now); fact index (proxy run late in the phase, real re-run at sweep
start); debate history (deferred, v2). Variants: vector-only vs hybrid+RRF vs
hybrid+reranker; 400 vs 800 chunk size as a secondary axis. Golden set: 40–60 queries in
three difficulty bands (exact-term / paraphrase-concept / cross-source survey),
co-authored by the developer during R1 QA skims, grown from logged misses. Metrics:
Recall@5, nDCG@10 post-rerank, Recall@50 pre-rerank, MRR, latency, indexing throughput,
storage. Decision rules: incumbent `qwen3-embedding-4b` stays unless beaten by ≥5 pts
Recall@5 or matched within 2 pts by a local model; reranker stays default-on unless it
adds <2 pts nDCG@10; hybrid-vs-vector follows the same 2-point rule. Per-table verdicts
(the two indexes may choose different models).

### 8.7 CI & publication (D13 — brainstorm 10)

The kb repo's CI, on every green push to `main`, publishes the compiled validated bundle
as Release assets (`latest-green` rolling tag + immutable `data-vN` tags); the site repo
consumes only that bundle (`repository_dispatch` trigger, daily cron fallback,
one-parameter rollback to any `data-vN`). Never submodules or HEAD checkouts. Breaking
schema changes cost two sequenced deploys (~30 min, a few times a year); in exchange,
agents never touch deploy credentials and the site can only build from validated data.
No-PR-gate safety: the runner runs the same fast offline validators pre-commit;
publication is last-green (red main publishes nothing); the failure bot auto-reverts only
mechanically-safe tip commits (§7.9). GitHub App for both dispatch and runner identity
(no PATs). The site displays its `data-vN` build stamp. The embeddings cache stays
private (reaffirmed 2026-07-20 against D62).

---

## 9. Provider connectivity & MCP (D8, D35, D60 — brainstorms 03, 26, 57)

One Python retrieval core; a **read-only stdio MCP server** registered in `.mcp.json`
for Claude Code and MCP-speaking local models; returned chunks carry inline citation
keys. A thin FastAPI adapter serves non-MCP providers (the public search endpoint is
deferred, D33). The website reads structured data directly — SEO pages are never
rendered from RAG. The write path is the agent pipeline only.

**Public tool set (7)**: `search_knowledge`, `get_fact`, `get_feature`,
`get_neighbors`, `get_source`, `list_contradictions`, `get_contradiction`.
**Pipeline-only, never public**: `search_sources`, `get_source_section` (D15),
`search_finding_aids` (D53), `search_debate_history` (D18 v2, unbuilt — parked until the
transcripts repo has real volume). **Boundary test (D60)**: a tool is public only if
every possible return is an admitted/verified fact or citable KB structure;
pipeline-only if any output is raw pre-verification evidence, non-citable finding-aid
content, or agent chat text. Future brainstorms proposing MCP tools append a row to
brainstorm 57's tracking file rather than re-deriving the boundary; ratifications
touching a listed tool update its status column in the same pass (manual upkeep).

**Caution contract (D35)**: every fact object in every response carries a mandatory
`caution` block (status/confidence/verification/dispute/note — note null only when fully
settled); non-null notes are also prepended as plain-text caveats in the returned text;
tool descriptions state the contract so it loads once per session. The
`(status, dispute)` → note-sentence template table lives in the MCP server's code, not
the bundle. No fact is ever suppressed for low confidence or high controversy;
`search_knowledge` keeps relevance as primary sort, confidence/controversy as per-result
annotations. A structural `attribution` field (BY-SA, "LangAtlas contributors") rides
alongside on every fact object, and tool descriptions state the reuse obligation once per
session (D42). Dead-id resolution per §5.4; `no-record` envelope per §6.6.

---

## 10. Website (D10, D32, D33 — brainstorms 06, 18, 19)

### 10.1 Platform & IA

**Astro, fully static**, static-first hosting. Core knowledge-base content renders fully
without JS; the inline Pagefind search box and giscus embeds are scoped JS islands;
builder/selector later as islands. Full rebuilds accepted initially; language-count
scale needs no architectural change (rebuild time is the only metric to watch, D34).

IA: `/features/`, `/features/<x>/`, `/features/<x>/<lang>/`,
`/features/<x>/<a>-vs-<b>/` (alphabetical canonical; only above a data-richness
threshold), `/languages/`, `/languages/<x>/`, `/coverage/` (top-level, D32),
`/changelog/ontology/<id>/` (top-level, D38), `/license/` (D42). Internal links derived
from graph edges; stable slugs + 301 policy; hub pages for splits, never-404 tombstone
pages. JSON-LD from the data layer (TechArticle, ComputerLanguage + Wikidata `sameAs`,
SoftwareSourceCode, citation nodes from CSL records, per-page `license` field).

Design: typography-first (Stripe/MDN/gwern lineage), build-time Shiki highlighting, one
accent color (§1.3), dark mode, **no growth chrome** (no leaderboards, badges,
counters). Citations as quiet numeric-superscript popovers (native Popover API, no-JS
references-section fallback); row-level popovers in tables; "Challenge this fact" inside
the popover; stable `data-fact-id` everywhere.

### 10.2 Website deep-dives (D33)

- **Search**: Pagefind, as an inline instant-search box on every page (not a `/search/`
  page), supporting ctrl+click to open results in new tabs; the public FastAPI hybrid
  endpoint stays deferred until logged-query evidence shows lexical search insufficient.
  The search box emits a `pagefind-search` Umami custom event feeding the `demand`
  report (D52).
- **Coverage matrix**: pre-baked static views (overview, per-language, per-dimension,
  "biggest gaps"), zero-JS; an Astro island only if the developer notices static views
  aren't working (informal trigger). Cell states: three empty (not-yet-swept /
  not-yet-onboarded / deferred — each deep-linking to a prefilled `propose-coverage`
  issue), a fourth non-clickable `not-applicable` rendering (D50), and filled cells
  (present/partial/absent — absent gets equal filled-cell treatment, §6.6).
  `multi`-exclusivity dimensions are visually distinguished from `exclusive` ones (D39).
  A thin-value treatment for `<min-instances` dimension values arrives once the `gaps`
  report computes them (owed to this component).
- **Syntax-preview validation**: `syntax_check: parser | none` registry field wiring
  real parse-only checks into the offline validator suite for languages with a cheap CLI
  syntax-check mode; LLM plausibility checks explicitly rejected; "no automated check"
  is acceptable indefinitely for languages without a fast CLI mode (Prolog etc.);
  missing-Shiki-grammar handling is an onboarding-checklist item with plain-text
  fallback.
- **Analytics**: self-hosted Umami (MIT, cookieless, no PII) added to the compose stack
  post-launch, consumed manually and privately, never surfaced publicly.
- **Trust-signal UX**: the citation popover carries a plain-text line covering all
  status axes (verification/freshness/dispute/confidence/controversy) plus the
  grounding-disclosure line (D51) and contradiction clauses (D45); exactly **one shared
  base-page glyph** marks the disputed/contradicted/superseded/partially-verified
  minority — every other combination stays visually silent outside the popover.

### 10.3 Contribution funnel (D32 — brainstorm 18)

**Five typed GitHub Issue Forms** on the kb repo (replacing a generic template):
`challenge-fact.yml`, `propose-coverage.yml`, `request-language.yml`,
`general-question.yml` (redirects to Discussions), plus D38's RFC form (and optionally
D42's `legal-complaint.yml`), auto-labeled and deep-linkable with pre-filled query
params — this *is* the "propose a fact" web form; no form backend or third-party service.
giscus Discussions scoped to feature and language pages only (`pathname` mapping, lazy
thread creation, small fixed category set; no comparison pages until they exist at all);
the Issues-vs-Discussions division of labor is documented in CONTRIBUTING.md.
Not-yet-onboarded languages get no stub pages — recruitment lives on `/coverage/` only;
no hand-curated "good first gap" list (waits for coverage analytics data).

**Graduated external-authorship posture** (for the would-be human co-author D1's
no-PR-gate never covered): source/candidate-proposal PRs only for now (mechanically
checkable), escalating to developer-skimmed full fact-PRs once the channel has a track
record; unqualified auto-merge-on-green reserved indefinitely.

**Discussion→Issue promotion (D55)**: fully manual until Discussions accumulate real
volume; trigger to revisit is qualitative (promotions late, or triage consuming
noticeable time). Then: a private developer digest first (a standalone script; cheap
structural pre-filter → LLM claim+source classification; promotion stays a manual
click); a public propose-only bot (comments, human confirms — never silent auto-file)
only if the digest's own triage load becomes the bottleneck, under its own third
narrowly-scoped GitHub App (`Discussions: write` + `Issues: write`).

**CONTRIBUTING.md (D56)**: fully drafted (see brainstorm 48) — project one-liner, the
three lanes (challenge / discuss / propose coverage-or-source), the graduated PR
posture, DCO (bot carve-out vs human sign-off), licensing (CC BY-SA 4.0 corpus / MIT
code, "LangAtlas contributors", takedown contact), "no growth chrome" close. **Held
unlanded** until the public-launch checklist; real URLs wait on the GitHub-org
confirmation (no placeholder-TODO version in the interim); no ontology-RFC mention.

### 10.4 Coverage analytics (D52 — brainstorm 44)

`tools/coverage/report.py` on a shared `langatlas_coverage.metrics` library ("instance
count per node, keyed by immutable id"), three subcommands for three lifecycle moments,
output ephemeral: **`dossier`** (the R6 exit dossier, five items; consumes
`research/reality-checks/<cycle>-<theme>.yaml`); **`gaps`** (per `<dimension, value>`
corroborating-instance counts vs `--min-instances` default 2, no per-dimension override,
report-only — explicitly near-meaningless before phase 1 completes); **`demand`**
(monthly Umami export of Pagefind queries matched against `aliases:` to split "known
synonym miss" from "genuinely absent content"). No cache; every run recomputes.

---

## 11. Licensing & legal (D12, D14, D42 — brainstorms 15, 33)

- **Code: MIT. Corpus: CC BY-SA 4.0 (final).** Transcripts: CC0 1.0. Three-layer
  plain-English LICENSE note; **DCO, not CLA**.
- Structural safety: uncopyrightable facts in LangAtlas's own words; Czech § 31
  quotation right for short attributed quotes; EU TDM exceptions (DSM Arts. 3–4) bless
  the private snapshot/index pipeline. The university API has no ToS restriction on
  third-party copyrighted content — paywalled PDFs may flow through the private
  pipeline.
- Rules: quote cap ~50 words + ~300-word per-page aggregate CI warning; "no source
  content in public repos" is a *legal* rule; SA-licensed comparisons never copied;
  syntax examples original (`origin` field); TIOBE-class proprietary indexes = single
  attributed data points only; fetcher respects robots.txt/TDM opt-outs; language names
  as text only, no logos.
- **Attribution rendering (D42)**: site-wide BY-SA footer + `/license/` page + JSON-LD
  `license`; MCP per-session statement + per-fact `attribution` field; bundle
  `license` manifest field + `NOTICE.txt` + `_meta` row. Attribution name: **"LangAtlas
  contributors"**.
- **Takedown runbook**: a published project-alias email (primary) + optional
  `legal-complaint.yml`; solo triage into legal-vs-not; default safe action = unpublish
  the contested quote/excerpt, never the underlying fact; ordinary forward-fixing commit
  except genuine severity, which reuses the `REDACTIONS.md` force-push hatch; **no
  stated acknowledgment SLA** (purely best-effort). Lawyer triggers unchanged: public
  snapshot hosting, rightsholder complaint, monetization, deliberate bulk ingestion of a
  proprietary/SA database.

---

## 12. Scale-up posture (D34 — brainstorm 20)

The ambition to eventually exceed the curated 15 toward PLDB-adjacent breadth is real; a
future tiered **"stub sweep"** (small fixed field subset, upgradeable without schema
migration) is the release valve (backlog topic 50); prioritization past the curated set
draws on `gaps` analytics + audience demand; PLDB's language *list* (names only) is a
legitimate target-selection input. No site-side badge distinguishing stub-depth from
full-depth (the `/coverage/` framing covers it). The Builder splits into a backend-free
combination-validation + sharing island (client-side rules engine reading `exclusivity`;
URL/localStorage permalinks — ship first when picked up) vs the public library, the one
piece needing a live writable store (separate non-derived community Postgres schema +
GitHub OAuth; third-party BaaS rejected) — greenlit purely at developer discretion.

---

## 13. Top risks (brainstorm 08)

1. **K1 citation laundering** — countered by the D24 gate: fabricated sources die at
   the registry, fabricated locators at resolution, fabricated quotes at fuzzy match,
   real-quote-overstated-claim at decomposition entailment, verifier gullibility at
   golden set + canaries + cross-family sampling, verifier contamination at structural
   context blindness, false absence at the completeness-check.
2. **K2 ontology/schema instability** — countered by the frontloaded research phase +
   ontology versioning/migration machinery.
3. **P1 differentiation vs PLDB/Hyperpolyglot** — countered by D19/D40 positioning.
4. **S1 solo scope collapse** — countered by the deferred-modules list + incremental
   checklist-driven work.
5. **P2 SEO cold start** — success metric is corpus quality + MCP usability, not
   traffic.

---

## 14. Unclear points found during spec writing

Six items were found; all are now tracked outside this document (nothing lives only
here). Disposition as of 2026-07-20:

- **U1 — Concrete schema of the consolidated `affects-quality` edge** and **U2 — shape
  of the typed `limitation | extra | alternative` notes on `status: partial`
  instances**: filed as **open questions 1–2 in
  [open-questions.md](open-questions.md)**; resolved during the Stage-1 R0
  schema-authoring work (brainstorm 09 is done and won't be revisited — these are
  schema-pass tasks, not brainstorm fold-ins).
- **U3 — stale Elixir entry in D28's deferred list**: **fixed in decisions.md
  2026-07-20** (editorial, with dated note).
- **U4 — human-challenge hard-override mechanics (D9, 2026-07-20 amendment)**: no
  designed mechanism exists (where the override is recorded, how the
  verifier/back-dating/auto-revert paths consult it, interaction with D25
  re-verification). Filed as **backlog brainstorm topic 62** in
  [brainstorm-checklist.md](brainstorm-checklist.md); scheduled as a Stage-6 task —
  brainstorm run + implementation **before the challenge channel goes live**.
- **U5 — retrieval-tool mediation split for university-API agents** and **U6 — the
  authoritative per-pair-verdict → fact-level `verification` fold table**: filed as
  **open questions 3–4 in [open-questions.md](open-questions.md)**, owed in the
  D26/D53 implementation notes (before the sweep drafting role is built) and the D24
  verifier implementation respectively — Stage-1/Stage-2 tasks.

## 15. Timeline & developer checklist

Ordered by dependency, not calendar (no deadlines exist, D6/D11). Each stage lists its
gating condition. Deferred brainstorm topics (from
[brainstorm-checklist.md](brainstorm-checklist.md)) and deferred questions (from
[open-questions.md](open-questions.md)) are folded in at the stage whose trigger they
wait on.

### Stage 0 — anytime, developer-discretionary (no trigger)

- [ ] Register `langatlas.dev` (+ optionally defensive `lang-atlas.io`) and confirm the
      `langatlas` GitHub org name (D17/D40 — explicitly not gated on anything).
- [x] Editorial fix U3 (drop Elixir from D28's deferred list) — done 2026-07-20.

### Stage 1 — R0: infrastructure preflight (gates everything else)

- [ ] Repo scaffolding for `langatlas-kb`: directory layout (§3.3), `ontology/` at
      `VERSION 0.1.0`, id/slug machinery, JSON Schemas in `ontology/schema/`
      (incl. `exclusivity`, `applies_to`, `aliases`, `absence_scope`, `language_kind`,
      `syntax_check`, `grounding` fields — all pre-emptive, before the first node).
      **Resolves open questions 1–2** (U1 consolidated `affects-quality` edge schema;
      U2 typed partial-notes shape) as part of this schema pass.
- [ ] Answer open question 3 (U5) — write the retrieval-mediation split into the
      D26/D53 implementation notes before any university-API agent role is built.
- [ ] `tools/validate/` (D48): normalizer, precommit/ci contracts,
      `validate_locator_shape`, regression-fixture runner.
- [ ] Provider abstraction + `RunContext` (D26): openai-SDK channel, Claude channel,
      cost log, cache, budget signals, data-not-instructions delimiting + lexical scan
      (D31).
- [ ] Transcript logging (D18): wrapper persistence, normalizer, `langatlas-transcripts`
      repo (CC0 license file), gitleaks CI, `REDACTIONS.md` convention.
- [ ] Prompt registry `prompts/` + `config/provider_capabilities.yaml` + first probe run
      (D41).
- [ ] D15 ingestion CLI + `source_chunks` schema + extraction-QA harness (D37) +
      snapshot store layout.
- [ ] Claim-template registry `ontology/claim-templates/` (D47).
- [ ] Agent-runner commit protocol (D36): GitHub App, trailers, land loop, is-main-green
      gate, failure bot.
- [ ] CI: validated-artifact pipeline skeleton (D13) — validators, fact derivation,
      collision check, last-green publication, `data-vN` tagging.
- [ ] Orchestrator `tools/orchestrator/driver.py` + `config/jobs/` +
      `crontab.example` (D43).
- [ ] R0 exit test: an agent can run `search_sources`, mint a node file that validates,
      and the run is logged.

### Stage 2 — R1/R2: corpus & benchmark

- [ ] Acquire the six ratified texts (Scott, Turbak & Gifford, Harper, Krishnamurthi,
      Sebesta, Kaijanaho) via university library/purchase (D27).
- [ ] Ingest the seed corpus + phase-1 language specs; identify the two Elsevier papers
      at ingestion (D15); QA skim per source; retroactive
      `canonical_source`/`acquisition_note` backfill (D37) and phase-1 `grounding`
      classification (D51).
- [ ] Co-author the retrieval golden set (40–60 queries) during QA skims; author the
      verifier golden set (D44 taxonomy, ~200–300 items) + the ~10–15-item held-out
      slice + the ~15–20 bootstrap controversy cases.
- [ ] R2: run the D22 embedding benchmark on a pilot corpus; record per-table verdicts.
      *(Deferred question folded here: "Embedding-model choices — D22's benchmark
      decides per use case." The fact-index re-run happens at Stage 5.)*
- [ ] Stand up the D24 verifier against the golden set; calibrate to FA ≤2% / FR ≤10%;
      wire canaries. **Resolves open question 4 (U6)**: write the authoritative
      per-pair-verdict → fact-level `verification` fold table as part of the verifier
      implementation.

### Stage 3 — R3→R5 theme cycles (repeat per theme, ~12 themes)

- [ ] Developer signs off each cycle's R3 theme list (hard checkpoint, D27).
- [ ] R3 survey → R4 drafting/debates (schema-dispute challenge types; D30
      verifier-replay + cost-join scripts watching) → R5 reality checks (rotating 4–5
      languages; emit `research/reality-checks/*.yaml`; shakedown of questionnaire
      compiler D46, verifier, commit protocol).
- [ ] Mark themes settled; run `coverage report.py dossier` each R6 consolidation pass.
- [ ] Track R4 debate outcomes against later MAJOR churn (D30).

### Stage 4 — v1.0.0 exit

- [ ] R6 global consolidation: cross-theme edge pass, dedup/alias audit, slug polish.
- [ ] Developer reads the five-item dossier and declares `1.0.0` (discretionary; flips
      on full D16 governance: RFC-gated MAJORs, staleness machinery, ~monthly MAJOR
      batching).
- [ ] Compile the first sweep questionnaire (D46) and freeze the handoff artifacts.

### Stage 5 — sweep pipeline & language onboarding (strictly sequential phases, D28)

- [ ] Re-run the fact-index embedding benchmark; pin the `knowledge_embeddings` model,
      dimension, index type (D62/D22).
- [ ] Build the onboarding-checklist template under `context/` (D57 — deferred until
      closer to phase 2/3, but the phase-1 audit rows exist in brainstorm 34).
- [ ] Phase 1: Python, C, Java, Rust, Haskell, Prolog — sweeps hand-launched; nightly
      verification/controversy batches; `since` back-dating batches per stabilized
      language; contradiction scan riding new-fact commits (D59).
- [ ] D54 auto-skip: shadow mode during phase 1; go live (kill switch + audit sample)
      only on real measured rates. *(Deferred question folded here: "what threshold of
      'debate changed nothing' justifies simplifying the challenger round" — revisit
      once D30's instrumentation has real numbers.)*
- [ ] Phases 2 → 3 → 4 (optional VB), each gated on the previous phase's completed
      sweeps; grounding classification at each phase's ingestion.
- [ ] Phase 5 (SQL): design once `language_kind`/`applies_to` are exercised and the
      vendor-dialect sourcing lands (D50).

### Stage 6 — site build & public launch (can overlap Stage 5 once real facts exist)

- [ ] `langatlas-site` repo: Astro build from the bundle, IA pages, popovers +
      trust-signal line + shared glyph, coverage matrix pre-baked views, Pagefind box
      (+ `pagefind-search` event), OG templates (D40 visual language), JSON-LD,
      `/license/`, `/changelog/ontology/`, build stamp.
- [ ] Postgres loader (D58) + blue-green swap + compose role-init script; MCP server
      with the 7 public tools, caution + attribution contracts, `no-record` envelope,
      tombstone chain-walking.
- [ ] **Run brainstorm 62** (human-challenge hard-override mechanics, U4) and implement
      its outcome — hard gate: must land **before the challenge channel goes live**
      (the first `challenge-fact.yml` resolution must already respect the override
      rule).
- [ ] Issue forms (5–6), giscus wiring, deep links from site surfaces (D32).
- [ ] Land CONTRIBUTING.md (D56 — gated on org-name confirmation for real URLs).
- [ ] Finalize positioning copy (D40: hero paragraph with the named-comparison sentence
      cut — *deferred question folded here*), wordmark, accent-color contrast audit.
- [ ] Launch posts (HN/lobste.rs framing per D40); isogloss-line SVG mark as a
      fast-follow script.
- [ ] Post-launch: add self-hosted Umami to compose (D33); start the monthly `demand`
      export (D52).

### Standing periodic jobs (once their subsystems exist — D43 inventory)

- Nightly: verification/controversy batch.
- Monthly: link-checker (D37), capability probe (D41), finding-aid mirror refresh
  (D53), Umami `demand` export (D52).
- Quarterly: edition-check (D37).
- 18-month rolling: backstop re-verification sweep (~200 facts/night budget).
- Event-driven (not cron): contradiction scan (D59), re-verification triggers (D25),
  questionnaire recompiles (D46), blast-radius runs (D38).

### Deferred — waiting on a specific future trigger

Deferred brainstorm topics (checklist backlog):

- [ ] **50 Stub-sweep tier design** — when the developer moves on scaling past the
      curated 15: field subset, stub→full promotion path, mixed-depth presentation.
- [ ] **51 Community write-path schema & moderation** — when the Builder's public
      library is greenlit: separate community Postgres schema, GitHub OAuth, abuse/spam
      handling, backup strategy for the first non-derived live DB.
- [ ] **52 Builder combination-validation engine** — when the Builder is picked up:
      client-side rules engine + JSON/WASM payload built from the graph; must read
      `dimensions.yaml`'s `exclusivity`.
- [ ] **54 MCP lite-mode design** — if greenlit: FTS5 quality bar, packaging (bare
      `.sqlite`, no Docker), documentation prominence.
- [ ] **55 Eval-contamination monitoring** — only if the public golden-set benchmark
      (D44 stretch goal) is ever greenlit.
- [ ] **58 Language-specific quality-edge nuance** — if the research phase or an early
      sweep surfaces a real, sourceable per-instance quality case ("learnability worse
      in Zig than Rust specifically"): schema extension vs out-of-scope.
- [ ] **60 Reader-demand → issue-draft automation** — strictly post-launch, after real
      `demand` data accumulates: a periodic script drafting candidate issues (never
      auto-filed) from recurring zero-result queries.
- New from this spec pass — none of these wait on a trigger; all are scheduled above:
  **U1/U2/U5/U6** are open questions 1–4 in
  [open-questions.md](open-questions.md) (Stages 1–2); **U4** is backlog brainstorm
  topic 62, scheduled in Stage 6 before the challenge channel goes live.

Deferred questions (open-questions.md, triggers restated):

- [ ] Domain/org registration — no trigger, developer discretion (Stage 0).
- [ ] Positioning-paragraph wording — ship per D40 at launch (Stage 6).
- [ ] Embedding-model choices — D22 benchmark per use case (Stages 2 and 5).
- [ ] Challenger-round simplification threshold — after D30 instrumentation produces
      real rates (Stage 5).
- [ ] Upvote/usage-rate rankings — deferred with the Builder; votes' home and
      volatility decided then.
- [ ] Whole-language comparison pages — until non-thin data exists.
- [ ] `/concepts/` as separate pages vs grouping metadata — Concept pages will exist
      eventually per D16's Concept-first staging; decide with site IA growth.
- [ ] Indexing user-generated `/library/` submissions — moot until the Builder.
- [ ] Challenge-resolution SLA statement — disputed badge immediate, resolution
      best-effort (restate in CONTRIBUTING/site copy at launch).
- [ ] Transcript corpus as a citable/publishable dataset — licensing decided (CC0,
      D42); the citation format lands with the dataset-export work.
