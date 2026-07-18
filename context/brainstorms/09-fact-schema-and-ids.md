# 09 — Fact Schema & Stable ID Scheme

> Round-3 brainstorm. Topic: concrete v0 YAML schemas for all canonical entities and the
> stable derived-fact-ID scheme. Binding context: D1 (git YAML repo canonical, no PR gate),
> D2 (entity semantics), D3 (CSL-JSON-as-YAML sources), D4/D5/D18 (provenance +
> verification fields), D14 (syntax-example `origin` field, quote cap), D15/brainstorm 21
> (locator conventions shared with the source-chunk index), D16 (immutable `id` vs
> renameable `slug`, content-keyed IDs, tombstones), D20 (one record per feature instance,
> per-field `sources:`, facts derived at build time from (record, field) paths).
> Everything below is *proposed* until the developer ratifies.

## Problem framing

D20 settled the philosophy: contributors and agents author **records** (one YAML file per
feature instance, per edge, per rule…), and the build derives **facts** — the
challengeable, embeddable, per-field units with stable IDs — from those records. This
brainstorm has to turn that into concrete artifacts:

1. **Schemas** for every canonical entity: feature, concept, feature instance (with
   embedded syntax examples and characteristics), edge, rule, source. Qualities are a
   controlled vocabulary, not per-record files. Characteristic, per the D2 amendment, is
   not a page type — it must appear in the schema as fact-bearing entries under an
   instance, not as its own entity file.
2. **The ID scheme** — three distinct identity problems that D16 and D20 together create:
   node ids (immutable, minted once), record ids (deterministic from node ids), and
   derived fact ids (stable, content-keyed, tombstoned on change). The tension to resolve:
   D20 wants fact IDs "derived from (record, field) paths" (stable anchors), while D16
   wants content-keyed IDs (a changed claim is a *different* fact). Both are right about
   different halves of the identity.
3. **Directory layout** — where files live, chosen so that many agents committing
   directly (D1, no PR gate) rarely touch the same file, and so the per-language sweep
   (D5) and the research phase (D11) each have a natural writing surface.
4. **Conventions** that make determinism real: slug policy, locator grammar (must join
   against the `source_chunks` locators from brainstorm 21, because the D4 verifier reads
   both sides), canonical claim phrasing for dedup, and YAML normalization rules (D11's
   normalizer needs a spec to enforce).

Scale check (carried from brainstorm 01): low hundreds of features, ~10 languages
initially, tens of thousands of derived facts. Every design below must survive a corpus
that is 100% machine-written but 100% human-readable — the YAML is the UI for the human
expert who arrives via a challenge link.

### What the build derives from a record

One instance record like "pattern matching in Rust" yields several independently
challengeable facts: *that* Rust has the feature (existence), *since when* (the `since`
value), each characteristic sentence, each syntax example's claim of validity. Each of
those carries its own `sources:` list in the record; the build walks a fixed map of
fact-bearing fields, renders one human-readable sentence per (record, field) from a
template (or takes the authored sentence verbatim for free-text fields), computes the
canonical claim, mints the fact ID, and attaches sources + provenance + status. Facts are
never authored as files — `facts/` does not exist in the repo; the fact table is a build
artifact (with the one exception of the tombstone ledger, which must be canonical because
it outlives the records that produced it).

## Options with trade-offs

### O1 — Fact identity: path-keyed vs content-keyed vs two-part

**Option 1a: path-keyed fact IDs** (`rust/pattern-matching#since`). Maximally stable —
the challenge link survives value corrections. But then a fact whose value was corrected
keeps its ID while its meaning changed, so "verified" status, embeddings, and challenge
threads silently refer to different claims over time. Violates D16's content-keying and
re-opens exactly the confusion tombstones exist to prevent.

**Option 1b: pure content-hash IDs** (`f-3f9a1c04b2d7`). Correct semantics (new claim =
new fact), but opaque: nothing in the ID says where the fact lives, page anchors churn,
and humans can't eyeball a diff.

**Option 1c (recommended): two-part identity — a stable human-readable *anchor* plus a
content-keyed *fact id* that embeds it.**

- **anchor** = the (record, field) path with node *ids*:
  `fi.rust.pattern-matching#since`, `edge.requires.ownership.move-semantics#exists`,
  `fi.rust.pattern-matching#characteristics[c-exhaustive]`. List entries are addressed by
  their own stable sub-key, never by list position (positions are not stable under
  normalization).
- **fact id** = `f-` + first 12 hex chars of SHA-256 of the **canonical claim string**
  (O6), which itself contains the anchor and the normalized value. So the id changes iff
  the claim changes, per D16; the anchor never changes while the record exists.
- The site's `data-fact-id` and the challenge-issue prefill carry **both** (`fact_id` for
  identity, `anchor` for locating the file/field to edit). URL fragments use the fact id
  (`…/rust/#f-3f9a1c04b2d7`); a superseded id resolves through the tombstone ledger to
  its successor (D16), which shares the anchor, so the reader lands on the corrected
  claim with a "superseded" note.
- 12 hex chars = 48 bits; at ~10⁵ facts the birthday-collision probability is ~10⁻⁴ and
  CI fails the build on any collision (then bump to 16 chars corpus-wide — a mechanical
  MAJOR-free change since fact ids are derived, not stored in records).

### O2 — Record identity

Records never mint free identities; their ids are deterministic compositions of node ids
(D16 makes node ids immutable, so record ids are immutable too):

| Record | id pattern | example |
|---|---|---|
| Feature | minted node id | `pattern-matching` |
| Concept | minted node id | `unification` |
| Language | minted node id | `rust` |
| FeatureInstance | `fi.<language>.<feature>` | `fi.rust.pattern-matching` |
| Edge | `edge.<type>.<from>.<to>` | `edge.influences.algebraic-data-types.pattern-matching` |
| Quality edge | `edge.<improves\|hurts>.<feature>.<quality>` | `edge.hurts.ownership.learnability` |
| Rule | minted node id, `rule-` prefixed | `rule-laziness-needs-purity` |
| Source | minted slug id (D3) | `vanroy-haridi-2003` |
| Syntax example | `<instance-id>.sx.<key>` | `fi.rust.pattern-matching.sx.basic-match` |

Sub-keys (`sx.<key>`, characteristic `c-<key>`) are short kebab keys minted once inside
the parent record and immutable thereafter (renaming a sub-key is a supersession event,
same as deleting + re-adding). `alternative-to` is symmetric: CI enforces that the
endpoint pair is stored in lexicographic id order, so the edge id is canonical and dedup
is trivial. `requires`, `enables`, `influences`, `conflicts-with` are directional as
authored. Only one `influences` edge per ordered pair (polarity is a field, not part of
the id) — flipping polarity is a supersession of the same edge record's fact, which is
exactly what we want.

**Considered and rejected:** hashing record contents into record ids (churn for no
benefit — the composition is already unique) and UUIDs (opaque, hostile to the
git-diff-as-audit-trail story).

### O3 — Directory layout

**Option 3a: per-feature instance dirs** (`features/pattern-matching/instances/rust.yaml`).
Nice for feature-page builds; but the per-language sweep (D5) and language onboarding
write across hundreds of directories per run.

**Option 3b (recommended): per-language instance dirs, standalone edge files.**

```
ontology/                    # exactly as ratified in D16 / brainstorm 22
  VERSION  CHANGELOG.md  schema/  taxonomy/{layers,dimensions,edge-types,qualities}.yaml
  redirects.yaml  migrations/
concepts/<concept-id>.yaml
features/<feature-id>.yaml
languages/<language-id>/
  language.yaml                       # the Language record (+ its characteristics)
  instances/<feature-id>.yaml         # one FeatureInstance record per file (D20)
edges/<from-id>/<type>--<to-id>.yaml  # one Edge record per file, incl. quality edges
rules/<rule-id>.yaml
sources/<source-id>.yaml              # CSL-JSON vocabulary as YAML (D3)
tombstones.yaml                       # fact + node supersession ledger (canonical!)
```

Why one-file-per-edge instead of edge lists inside feature files (the brainstorm-01
sketch): with no PR gate, concurrent agent runs are the norm; hot features
(`pattern-matching` will accumulate dozens of edges) would make the feature file a
permanent merge-conflict magnet, and per-edge provenance + attributed quality assessments
(D2) are too bulky to inline pleasantly. One record per file also makes the D20 rule
"authoring unit = record" literal: one file = one record = one commit-able unit. The
build composes feature pages from the graph; files don't need to.

Sharding `edges/` by from-feature keeps directories browsable (a flat `edges/` with 10⁴
files is hostile to humans). `tombstones.yaml` is append-only and CI-checked; if merge
conflicts on it become real, shard to `tombstones/<year>.yaml` later (PATCH-level
change).

### O4 — Provenance placement: per-record vs per-field

Every derived fact needs full D5/D18 provenance (proposer agent + model + prompt version,
debate id, verifier result, optional `chat_run_id`). Repeating a full provenance block on
every field of every record would double file sizes for no information — in the common
case one agent run wrote the whole record.

**Recommended: record-level `provenance:` block as the default, per-field
`provenance:` override on any fact-bearing entry later edited by a different run.** The
build stamps each derived fact with the nearest enclosing block. Verifier results are
per-fact by nature, so they live in the per-field `verification:` sub-block (the gate
writes it back into the file when it passes/flags the claim — the one machine write-back
into authored records, which is fine because the gate is part of the commit path, D13).
`ontology_version` and the authoring commit are *not* stored in records — git and
`ontology/VERSION` at build time supply them (brainstorm 22, O4b).

### O5 — Locator conventions (shared with brainstorm 21's `source_chunks`)

Brainstorm 21 already committed chunks to normalized locator *strings* (`pp. 492–495`,
`§13.2.1`, `url#anchor`). Two options:

**Option 5a: structured locators** (`{kind: pages, start: 492, end: 495}`). Cleaner to
validate, but diverges from the chunk table, so the verifier needs a parser anyway on one
side; and agents copy locators from retrieved chunks verbatim (brainstorm 21's "no manual
locator invention" rule) — strings copy better.

**Option 5b (recommended): one canonical locator string grammar, CI-regex-validated,
identical on both sides.** Machine-produced at chunk time, copied into records verbatim:

| Source type | Grammar | Example |
|---|---|---|
| Book / paper (PDF) | `p. N` \| `pp. N–M` (en dash) | `pp. 492–495` |
| Numbered spec/section | `§N(.N)*` | `§13.2.1` |
| Named chapter/section | `ch. N` \| `§ <verbatim heading>` | `§ Match expressions` |
| Web page / docs | `#<url-fragment>` (source record holds the page URL) | `#match-expressions` |
| Multi-page docs site | `<path>#<fragment>` relative to source `URL` | `reference/expressions/match-expr.html#match-guards` |
| Repo file | `<commit-sha7>:<path>#LN-LM` | `a1b2c3d:src/lib.rs#L10-L25` |
| Video/talk | `t=HH:MM:SS` | `t=00:41:20` |

A `custom.locator_kinds` hint on the source record (D3 `custom` key) tells CI which
grammars are admissible for that source. The verifier joins fact→chunk on
`(source_id, locator)` with page/section-range overlap, not string equality — the grammar
exists so overlap is computable.

### O6 — Canonical claim phrasing (dedup + content key)

The content key (D16) must be independent of prose wording, slug renames, and YAML
formatting. **Proposed: the canonical claim is a single normalized S-expression-like
string over node *ids* and normalized values, one fixed template per claim kind:**

```
instance-field(fi.rust.pattern-matching, since, "1.0")
instance-exists(fi.rust.pattern-matching, status=present)
characteristic(fi.rust.pattern-matching, c-exhaustive, sha256-16=<hash of normalized sentence>)
edge-exists(edge.requires.ownership.move-semantics)
edge-polarity(edge.influences.algebraic-data-types.pattern-matching, +)
quality-assessment(edge.hurts.ownership.learnability, a-2026-07-18-claude-1)
rule-exists(rule-laziness-needs-purity, sha256-16=<hash of normalized antecedent+effect>)
syntax-valid(fi.rust.pattern-matching.sx.basic-match, sha256-16=<hash of normalized code>)
```

Value normalization before hashing: strings NFC + trimmed + internal whitespace
collapsed; free-text sentences additionally lowercased and stripped of terminal
punctuation (so cosmetic copyedits don't mint new facts — a *semantic* rewrite still
does, which is correct); dates ISO-8601; version values verbatim strings. Dedup at
commit time = "does this canonical claim already exist in the derived fact table?" —
exact string match, no fuzzy matching in the identity path (fuzzy near-duplicate
*detection* is a work-queue concern, not an identity concern).

**Considered:** hashing the rendered English sentence (rejected — template copyedits
would churn every fact id; templates render *from* claims, claims never derive from
renderings).

### O7 — The schemas (v0, proposed)

JSON Schemas live in `ontology/schema/`; below are the shapes by example. Shared
sub-schemas first:

```yaml
# --- shared: one entry in any `sources:` list (D3, D4) ---
- source: rust-reference-match-expr        # id in sources/
  locator: "#match-guards"                 # O5 grammar; REQUIRED (D4 source-first)
  quote: "A match behaves differently depending on whether or not the scrutinee expression is a place expression or value expression."   # optional (D3), ≤50 words (D14)

# --- shared: provenance block (D5/D18; record-level default, per-field override) ---
provenance:
  proposer: { agent: lang-sweep/rust, model: claude-sonnet-4-6, prompt: sweep-v3 }
  claim_origin: source-derived             # source-derived | prior  (D4)
  debate_id: null                          # set when a structured debate produced it
  chat_run_id: 2026-07-18-sweep-rust-003   # optional link into langatlas-transcripts (D18)

# --- shared: verification block, written back by the D4 gate, per fact-bearing field ---
verification:
  result: verified                         # verified | flagged | failed
  method: entailment                       # quote-match | entailment | mechanical
  model: deepseek-v4-pro
  run: 2026-07-18-verify-batch-012#msg-41  # batch transcript + per-claim anchor (D18)
  date: 2026-07-18
```

**Feature** (`features/pattern-matching.yaml`):

```yaml
id: pattern-matching            # immutable node id (D16)
slug: pattern-matching          # renameable; history in ontology/redirects.yaml
name: Pattern matching
layer: 2                        # 1 syntax | 2 semantic | 3 design-choice
dimension: null                 # required iff layer 3; id from taxonomy/dimensions.yaml
cross_cutting: false            # D16/O6 affordance
realizes: [term-rewriting]      # -> concepts/ (node ids)
summary:                        # fact-bearing: one sentence-bundle field
  text: >-
    Dispatch and destructuring driven by the shape of data: a scrutinee is tested
    against structural patterns which may bind variables on match.
  sources:
    - { source: vanroy-haridi-2003, locator: "pp. 490–492" }
provenance: { ... }
```

Edges are *not* listed here (O3); qualities and dimensions live in `ontology/taxonomy/`.
**Concept** is the same minus `layer`/`dimension`/`cross_cutting`, plus an optional
`excluded_rationale` for the four D2-excluded concepts staged concept-first (D16).

**FeatureInstance** (`languages/rust/instances/pattern-matching.yaml`) — the D20
authoring unit; full example in O8. Fields: `feature`, `language` (redundant with the
path; CI cross-checks), `status: present | absent | partial`, `since` (+ `sources`),
`notes`, `characteristics` (keyed list — the D2 "characteristic = a fact listed under a
language feature"), `syntax` (keyed list of syntax examples, each with
`origin: original | adapted` + `adapted_from` per D14), record `provenance`.
**Absence is a record too** (`status: absent`, with sources): "C has no pattern
matching" is a challengeable, sourced fact, and the sweep questionnaire (D5) produces
these naturally. No file at all means *unknown/not yet swept* — an important
distinction the site and RAG must not conflate.

**Edge** (`edges/algebraic-data-types/influences--pattern-matching.yaml`):

```yaml
id: edge.influences.algebraic-data-types.pattern-matching
type: influences                # requires|enables|influences|conflicts-with|alternative-to
from: algebraic-data-types
to: pattern-matching
polarity: "+"                   # influences only (polarity-only per D2)
statement:                      # fact-bearing; the human sentence for the edge fact
  text: >-
    Algebraic data types strongly encourage pattern matching as the natural
    elimination form for sum types.
  sources:
    - { source: vanroy-haridi-2003, locator: "pp. 175–177" }
provenance: { ... }
verification: { ... }
```

**Quality edge** — same file shape with `type: improves-quality | hurts-quality`,
`to: <quality-id>` (from `taxonomy/qualities.yaml`), and instead of a single statement an
**`assessments:` keyed list** (D2: attributed assessments with recorded spread — no
forced consensus, each assessment is its own derived fact):

```yaml
id: edge.hurts.ownership.learnability
type: hurts-quality
from: ownership
to: learnability
assessments:
  - key: a-2026-07-18-claude-1
    assessor: { agent: quality-panel, model: claude-sonnet-4-6, prompt: qa-v2 }
    strength: strong            # small ordinal vocab: weak | moderate | strong
    statement: >-
      Ownership and borrowing are consistently reported as the steepest part of
      Rust's learning curve.
    sources:
      - { source: rust-survey-2024, locator: "#learning-curve" }
  - key: a-2026-07-19-kimi-1
    assessor: { agent: quality-panel, model: kimi-k2.7, prompt: qa-v2 }
    strength: moderate
    statement: >-
      The difficulty concentrates in the first months and is offset by compiler
      diagnostics.
    sources:
      - { source: fulton-2021-usability, locator: "pp. 4–6" }
```

The spread (strong vs moderate) stays visible; the site renders it; the D21 controversy
assessor reads it.

**Rule** (`rules/rule-laziness-needs-purity.yaml`): `id`, `when_all: [<feature-ids>]`
(v0 keeps only conjunctive antecedents — `when_any`/`unless` are additive schema changes
when a real rule needs them), `effect: requires | forbids | warn`,
`then: <feature-id> | null`, `message` + `sources`, `provenance`. The rule's existence +
message is one derived fact.

**Source** (`sources/rust-reference-match-expr.yaml`) — CSL-JSON vocabulary as YAML,
exactly per D3/brainstorm 02, with `custom.{tier, archive_url, accessed, added_by,
locator_kinds}`. Nothing new here; this brainstorm just confirms the shape and adds
`locator_kinds`.

## Recommendation

*Proposed* package:

1. **Two-part fact identity (O1c):** stable human-readable **anchor** =
   `(record-id)#(field-path-with-stable-sub-keys)`; **fact id** = `f-` + 12-hex SHA-256
   of the canonical claim string. Anchors locate; ids identify. Challenge prefills and
   `data-fact-id` carry both; superseded ids resolve via `tombstones.yaml`
   (`superseded_by`, sharing the anchor).
2. **Deterministic record ids (O2)** composed from immutable node ids
   (`fi.<lang>.<feature>`, `edge.<type>.<from>.<to>`); `alternative-to` endpoints stored
   in lexicographic order; sub-keys (syntax examples, characteristics, assessments)
   minted once and immutable.
3. **Layout (O3):** per-language `instances/` dirs, one record per file, one file per
   edge sharded by from-feature, no `facts/` directory (facts are build artifacts), a
   canonical append-only `tombstones.yaml`.
4. **Provenance (O4):** record-level `provenance:` default with per-field override;
   per-field `verification:` written back by the D4 gate; ontology version + commit
   supplied at build time, never stored.
5. **Locators (O5b):** one CI-validated string grammar shared verbatim with the
   brainstorm-21 chunk table; `custom.locator_kinds` on source records; verifier joins
   on range overlap.
6. **Canonical claims (O6):** fixed per-kind templates over node ids + normalized values;
   free-text claims hash their normalized sentence; dedup = exact canonical-claim match;
   English sentences are *rendered from* claims (templates in the build), never hashed.
7. **Schemas (O7):** as sketched — including `status: absent` instance records (absence
   is a sourced fact; missing file = unknown), keyed `characteristics:` lists as the D2
   characteristic realization, and quality edges carrying keyed `assessments:` lists as
   the D2 spread representation.

### O8 — Worked example: pattern matching in Rust

`languages/rust/instances/pattern-matching.yaml` (with a Python sibling at
`languages/python/instances/pattern-matching.yaml` differing in `since: "3.10"` and a
`match` statement example citing PEP 634):

```yaml
feature: pattern-matching
language: rust
status: present
since:
  value: "1.0"
  sources:
    - { source: rust-reference-match-expr, locator: "#match-expressions" }
notes: >-
  match is an expression; exhaustiveness is compiler-checked; guards and
  bindings supported.
characteristics:
  - key: c-exhaustive
    text: >-
      The Rust compiler rejects match expressions that do not cover every
      possible value of the scrutinee's type.
    sources:
      - source: rust-reference-match-expr
        locator: "#match-expressions"
        quote: "The match expression must have an arm that matches every possible value of the scrutinee."
    verification: { result: verified, method: quote-match, model: null,
                    run: 2026-07-18-verify-batch-012#msg-41, date: 2026-07-18 }
syntax:
  - key: basic-match
    title: Basic match with destructuring
    origin: original            # D14: never copied from SA-licensed comparisons
    code: |
      match msg {
          Message::Quit => quit(),
          Message::Move { x, y } => move_to(x, y),
          other => log(other),
      }
    sources:
      - { source: rust-reference-match-expr, locator: "#match-expressions" }
provenance:
  proposer: { agent: lang-sweep/rust, model: claude-sonnet-4-6, prompt: sweep-v3 }
  claim_origin: source-derived
  debate_id: null
  chat_run_id: 2026-07-18-sweep-rust-003
```

Derived facts from this one record (build output, shown as the compiled table rows):

| anchor | canonical claim | rendered sentence (template) |
|---|---|---|
| `fi.rust.pattern-matching#exists` | `instance-exists(fi.rust.pattern-matching, status=present)` | "Rust implements pattern matching." |
| `fi.rust.pattern-matching#since` | `instance-field(fi.rust.pattern-matching, since, "1.0")` | "Rust has had pattern matching since version 1.0." |
| `fi.rust.pattern-matching#characteristics[c-exhaustive]` | `characteristic(fi.rust.pattern-matching, c-exhaustive, sha256-16=…)` | the authored sentence verbatim |
| `fi.rust.pattern-matching#syntax[basic-match]` | `syntax-valid(fi.rust.pattern-matching.sx.basic-match, sha256-16=…)` | "In Rust, pattern matching is expressed as: …" |

Each row gets `f-<12hex>`, the record's sources for that field, the record provenance,
and its own status/verification. Correcting `since: "1.0"` → `"0.8"` changes one fact id,
appends one tombstone line, and leaves the other three facts untouched — exactly the D20
challengeability granularity.

### Slug & id minting policy (*proposed*)

- Grammar: `[a-z0-9]+(-[a-z0-9]+)*`, ≤ 48 chars, ASCII only, no leading digit.
- Node ids are minted as the initial slug (D16) and never change; slugs may diverge later
  via `ontology/redirects.yaml`.
- Language ids follow the community-conventional ASCII names: `cpp`, `csharp`, `fsharp`,
  `javascript` (not `js`), `python`, `rust`, `go`, `java`, `c`, `sql` — a small
  `taxonomy`-adjacent registry file (`languages/_registry.yaml`) is the authority, so
  agents can't mint `c-plus-plus` and `cpp` for the same language.
- Feature ids prefer the literature's noun phrase (`pattern-matching`,
  `algebraic-data-types`), singular vs plural as the literature has it; no
  language-specific names (`match-expression` is a Rust *syntax* title, not the feature
  id).

### YAML normalization rules (*proposed*, enforced by the D11 normalizer + CI)

YAML 1.2, UTF-8, NFC; 2-space indent, no tabs; keys in schema-declared order; one record
per file, no multi-doc streams; no anchors/aliases/merge keys; no custom tags; strings
plain-scalar unless quoting is required, then double quotes; prose in `>-` folded blocks,
code in `|` literal blocks (trailing newline preserved); 100-column soft wrap for prose;
dates as quoted ISO-8601 strings (never YAML timestamps); `null` spelled `null`; keyed
lists sorted by `key`, `sources` lists in authored order (citation order is meaningful),
edge files' names must equal their `id` fields (CI check). The normalizer is idempotent
and runs pre-commit in the agent runner (D13) so diffs are always semantic.

## Open questions for the developer

1. **12-hex fact-id length** — comfortable with 48 bits + a CI collision check (and a
   corpus-wide re-render to 16 hex if one ever fires), or pre-commit to 16 hex now for
   permanence at the cost of uglier anchors in URLs and issues?
2. **Copyedit-tolerant hashing of free-text claims** (O6: lowercase + punctuation-strip
   before hashing characteristic/notes sentences) — accept that a small wording change
   may *not* mint a new fact id even though the rendered sentence changed? The
   alternative (hash verbatim) means every typo fix is a supersession event.
3. **`status: partial`** for feature instances (e.g. "Python has pattern matching but no
   exhaustiveness checking") — keep it in v0, or drop it and force partial support to be
   expressed as `present` + characteristics? Fewer statuses = simpler builder logic;
   `partial` is more honest per-language.
4. **Verifier write-back into authored records** (O4) — the D4 gate editing
   `verification:` blocks inside record files is the one machine write into canonical
   YAML. Acceptable, or should verification results live only in a separate build-side
   ledger (cleaner files, but then a record alone doesn't show its verification state to
   a human reading it on GitHub)?
5. **Quality-assessment vocabulary** — is `strength: weak | moderate | strong` the right
   ordinal for D2's "attributed assessments with recorded spread", or do you want
   polarity folded in (an `improves`/`hurts` edge pair per quality vs one `affects-quality`
   edge with signed assessments)? v0 as drafted keeps the two edge types from D2.
6. **Language registry** — confirm `languages/_registry.yaml` as the mint authority for
   language ids, and the convention choices `cpp`/`csharp`/`javascript`.

## New brainstorm topics surfaced

- **Fact statement templating** — the per-claim-kind English templates (and their change
  management: template edits re-render sentences without changing fact ids; when is a
  template change big enough to warrant re-embedding or re-verification?).
- **Validator/normalizer CLI design** — the concrete `langatlas validate` / `langatlas
  fmt` tools implementing these schemas and normalization rules, shared by CI and the
  agent runner pre-commit hook (extends D13's "same fast offline validators").
- **Absence & unknown semantics downstream** — how `status: absent` vs missing-file
  (unknown) render on the site, flow through the MCP tools, and interact with the
  builder's combination validation.
- **Sweep questionnaire ↔ schema binding** — the D5 per-language questionnaire should be
  generated from the fact-bearing field map so the sweep and the schema can never drift
  apart.

## Sources

No new external sources introduced; all constraints trace to the input brief and
decisions D1–D22. Rust reference and survey records shown in examples are illustrative
source-registry entries, not citations made by this document.
