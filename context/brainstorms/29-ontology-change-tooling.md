# 29 — Ontology Change Tooling

> Backlog brainstorm for LangAtlas. Topic: the concrete tooling that makes D16's (topic 22)
> ratified ontology-versioning *policy* executable — the RFC + impact-analysis templates and the
> blast-radius script that feeds them; a machine-replayable migration-manifest disposition DSL
> (the concrete shape `migrate.py` scripts consume/produce, which D16 ratified as
> "migrations-as-idempotent-scripts" without designing the manifest format itself); how
> tombstoned/superseded facts and nodes render on the site and resolve through the MCP server
> (`get_fact` on a dead id must not just 404); and an ontology diff visualization. Binding
> context: D16 (id/slug split, blast-radius semver, migrations-as-committed-scripts with a
> corpus diff + manifest + impact report, the split/merge/move/removal casebook, tombstones via
> `derived_from`/`superseded_by`, ontology MAJORs as the one human-gated exception to D1's
> no-review rule); D23 (two-part fact identity — `(record-id)#(field-path)` anchor +
> content-keyed `f-<12-hex>` fact id — and the append-only `tombstones.yaml` that already exists
> for corrected-value fact churn, which this topic's migration tombstones must share rather than
> duplicate); D8 (the read-only MCP tool set — `search_knowledge`, `get_fact`, `get_feature`,
> `get_neighbors`, `get_source` — whose dead-id behavior this topic specifies); D35 (the MCP
> caution contract: every fact object carries a mandatory `caution` block, non-null notes also
> prepended as plain-text caveats, nothing ever suppressed — the shape any tombstone/successor
> response must fit into); D10 (static-first, zero-JS site; stable slugs + a 301 policy for
> renames/merges, hub pages — not 301s — for splits); D37/brainstorm 28 (the topic-28
> `edition-superseded` source-registry tombstone, `custom.superseded_by` on a source record when
> a spec gets a new edition, explicitly named by both 22 and 28 as belonging in this topic's
> disposition-DSL shape "one level up" from fact/ontology-node tombstones); D25 (the `freshness`
> axis and event-driven re-verification queue that both migration-triggered staleness and
> edition-superseded staleness ride). All proposals below are *proposed*, not ratified, per the
> project's decision-hygiene convention — none of this is binding until the developer signs off.

## 1. Problem framing

D16 ratified *what* happens on an ontology MAJOR (a human-gated RFC, an idempotent migration
script, a committed corpus diff, an impact report, a per-change-type casebook of fact
dispositions, tombstones so IDs never orphan) but deliberately stopped at policy — it named four
follow-up tooling gaps in its own §"New brainstorm topics surfaced" and this is where they get
built: the RFC/impact template pair (so "impact report" is a filled form, not a blank page every
time), the manifest's actual on-disk shape (so `migrate.py` has something structured to read
instead of ad hoc per-migration Python), successor resolution at read time (so a tombstoned id is
useful to whoever hits it — a human clicking an old bookmark, an agent calling `get_fact` on a
citation it logged months ago), and a diff view that makes the RFC's blast radius legible to a
human reviewer without them re-deriving it from the corpus diff by hand.

The fifth piece — folding topic 28's `edition-superseded` source-registry tombstone into this same
shape — is not a bolt-on request but a genuine test of whether the disposition-DSL design
generalizes: source-edition supersession is structurally the same event as an ontology-node split
or merge (an old identifier stops being current, a successor exists, things that pointed at the
old identifier need a policy for what happens to them) but sits one layer up the reference graph
(sources are cited *by* facts, not *are* facts) and rides a completely different governance path
(D37's quarterly edition-check job fires it automatically, no RFC, no human gate — it is
definitionally a MINOR-weight event on the ontology's own semver, since it never touches a fact's
*subject*, only a citation's freshness). If the DSL can't accommodate that without a parallel
mechanism, it isn't actually one shape — it's two shapes wearing the same name.

Scale check (carried from 22/25/28): low hundreds of ontology nodes, tens of thousands of facts,
MAJORs batched ~monthly outside the research phase (0.x is exempt from the whole governance
apparatus per D27's graduated minting ceremony). Every tool this topic designs runs against that
scale — a corpus-wide grep-and-diff is a script that finishes in seconds, not an indexing
infrastructure problem.

## 2. Options with trade-offs

### 2.1 The blast-radius script

D16's O5b already named this as the mechanical input to the impact report; nobody has specified
what it actually computes.

**What it's given:** a target node reference — an ontology node `id` (`fi.rust.pattern-matching`,
`feature.iterator-protocol`) for the ontology-node case, or, per §2.6 below, a `source_id` for the
source-registry case. Same script, one extra `--kind` flag, because the underlying operation
("find everything that cites this identifier") is identical regardless of what kind of identifier
it is.

**What it computes, mechanically (no LLM call — this is a corpus grep + join, not a judgment
call):**

- **Direct fact references** — every fact anchor `(record-id)#(field-path)` whose `record-id`
  decomposes (D23) to include the target node id: feature-instance records for that feature,
  edges where the node is `from` or `to`, rules whose body references it, quality-edge
  assessments on it. Output: a list of `(fact_id, anchor, record file path)` tuples.
- **Indirect structural references** — `alternative-to`/`requires`/`conflicts-with` edges whose
  *other* endpoint is unaffected but whose semantics depend on the target's current dimension/layer
  (relevant for layer/dimension moves specifically, per D16's O3 casebook row on that change type);
  Rule entries in the same dimension as a moved node, since dimension exclusivity is what a
  dimension move can silently flip.
- **Slug/URL surface** — the node's current slug(s) from `redirects.yaml`, so the impact report can
  state which URLs are affected before the migration decides 301 vs. hub-page policy.
- **Estimated re-verification cost** — `count(facts requiring reverify) × avg-verifier-cost-per-claim`,
  reading the existing D26 cost log for the average, giving the RFC a real number instead of "some
  facts will need re-checking."
- **Downstream artifact touch count** — how many rendered site pages, MCP `get_neighbors` responses,
  and (per D26) precomputed `facts` table rows change, purely for the impact report's "this affects
  N pages" line — not a build trigger itself.

**Option 2.1a — the script only counts, doesn't propose dispositions.** It answers "what is
affected," full stop; the RFC author (human or agent) still writes the `fact_remap` entries in
§2.3's manifest by hand, informed by the count.
**Option 2.1b — the script also drafts a *starting* manifest** (every directly-referenced fact
defaulted to `action: requeue` unless the change type's casebook rule allows a mechanical default,
e.g. merge facts default to `action: remap, reverify: fast-path` since D16's casebook already
says merges are near-always safe to auto-remap). The RFC author edits the draft rather than
writing it from a blank list.
**Recommendation: 2.1b.** The casebook (D16 O3) already encodes exactly the kind of "what's the
safe default per change type" logic a script can apply mechanically — split defaults to
`requeue` (ambiguous until judged otherwise), merge defaults to `remap`/`fast-path`, layer/
dimension moves default to `untouched` except classification-asserting facts which default to
`requeue`, removal defaults to `tombstone`. Producing this draft is strictly less work than
requiring a human or agent to enumerate potentially hundreds of fact anchors by hand from the raw
count in 2.1a, and it's still fully editable — the script proposes, the RFC's author (and,
per D16 O5b, the developer's process-gate review) disposes.

### 2.2 RFC + impact-analysis templates

**RFC template** (a GitHub Issue Form, matching D32's existing four-template pattern for
consistency — same repo, same UX convention, one more typed form):

- `title`, `motivation` (free text + citations, author-year per project convention where new
  external evidence is introduced), `change_type` (`split | merge | layer-move | dimension-move |
  removal | schema-breaking`, a dropdown — this single field is what lets tooling route the issue
  through the right casebook branch), `affected_node_ids` (one per line — seeds the blast-radius
  script), `proposed_disposition_draft` (either pasted output from running the blast-radius script
  locally, or "not yet run" — a checkbox gate before the PR stage), `dissenting_evidence` (a
  required field, even if "none identified" — forces the RFC author to have looked, mirroring D5's
  structured-debate discipline for ordinary facts), `objection_window_ends` (auto-computed:
  issue-open date + the batching cadence D16 already ratified, displayed not enforced — see open
  question 6).
- The issue form's own description text states D16 O5b's framing explicitly: the developer gates
  *process* (RFC held its window, CI green, casebook followed), not content authority — so
  objectors know what kind of pushback is in scope (missing evidence, wrong disposition mapping,
  understated blast radius) versus what isn't (re-litigating whether the split is linguistically
  "correct," which is what the RFC's own cited evidence and any triggered debate settle).

**Impact-analysis template** (`impact.md`, committed inside the migration's PR per D16's
`migrations/NNNN-<slug>/` layout) — split into an auto-generated section and an authored section,
so the two don't drift:

- **Auto-generated (rendered verbatim from the blast-radius script's JSON output, never
  hand-edited — CI can diff-check this section against a fresh script run and fail the PR if
  they've drifted):** fact counts by disposition action, affected URL list with old→new/hub
  mapping, estimated re-verification cost, dimension-exclusivity flags touched, a machine table of
  every `(fact_id, anchor, action)` triple.
- **Authored (the RFC/PR author's own prose, one required paragraph per heading):** rationale
  (why this carve is right — usually lifted from the RFC), alternatives considered and rejected,
  what the dissenting-evidence field surfaced and how it was weighed, and an explicit
  acknowledgment of the casebook row being invoked (e.g. "this is a split; old node
  `pattern-matching` demotes to a Concept per D16 O3, not tombstoned outright").

**Recommendation:** build both templates now, before the first real MAJOR lands (which per D27's
graduated ceremony won't happen until 1.0.0 or an urgent correction) — cheap to write, and having
them ready removes any temptation to skip the impact report under time pressure during the one
process step D16 made human-gated on purpose.

### 2.3 The migration-manifest disposition DSL

This is the concrete gap: D16 said manifests are "machine-readable: nodes touched, fact
disposition rules" and sketched the artifact layout (`migrations/NNNN-*/manifest.yaml`) but never
fixed the schema. Two shape options:

**Option 2.3a — one manifest = one flat list of `(anchor-pattern, action)` pairs**, with no
grouping by "operation." Simple, but loses the semantic context a reader needs (why is this fact
`requeue`d — because of a split? a removal?) and makes the auto-generated impact-report section
harder to render meaningfully (it'd just be a giant flat table with no narrative structure).

**Option 2.3b (recommended) — a small typed `op` vocabulary matching D16's own O3 casebook rows
exactly**, each op carrying its own required fields, with a shared `fact_remap` list of matcher →
action entries nested under it:

```yaml
migration_id: "0007-split-pattern-matching"
rfc_issue: "https://github.com/langatlas/langatlas-kb/issues/312"
ontology_version_before: "0.4.2"
ontology_version_after: "0.5.0"

dispositions:
  - op: split                          # matches D16 O3's "Split" casebook row
    from: fi.rust.pattern-matching
    to:
      - { id: fi.rust.destructuring,          slug: destructuring }
      - { id: fi.rust.guards,                 slug: guards }
      - { id: fi.rust.exhaustiveness-checking, slug: exhaustiveness-checking }
    old_node_disposition: demote-to-concept    # | tombstone-only
    url_policy: hub                            # never 301 for splits, per D16 O3
    fact_remap:
      - match: { anchor: "fi.rust.pattern-matching#characteristics[c-exhaustive]" }
        action: remap
        target: fi.rust.exhaustiveness-checking
        reverify: fast-path
      - match: { anchor: "fi.rust.pattern-matching#characteristics[c-guard-syntax]" }
        action: remap
        target: fi.rust.guards
        reverify: fast-path
      - match: { anchor: "fi.rust.pattern-matching#syntax[*]" }
        action: requeue
        reason: ambiguous-subject

  - op: merge                          # matches D16 O3's "Merge" casebook row
    from: [feature.iterator-protocol, feature.iterable-protocol]
    to: feature.iteration-protocol
    url_policy: redirect-301           # both old URLs 301, per D16 O3
    fact_remap:
      - match: { anchor: "feature.iterator-protocol#*" }
        action: remap
        target: feature.iteration-protocol
        reverify: fast-path
      - match: { anchor: "feature.iterable-protocol#*" }
        action: remap
        target: feature.iteration-protocol
        reverify: fast-path

  - op: move                           # matches D16 O3's "Layer/dimension move" row
    node: feature.tail-call-optimization
    to_layer: 3
    to_dimension: optimization-strategy
    url_policy: unchanged               # D10's flat IA never encodes layer/dimension
    fact_remap:
      - match: { anchor: "feature.tail-call-optimization#classification" }
        action: requeue
        reason: classification-assertion
      - match: { anchor: "feature.tail-call-optimization#*", exclude: "#classification" }
        action: untouched

  - op: remove                         # matches D16 O3's "Node removal" row
    node: feature.some-retired-thing
    url_policy: redirect-to-retired-index
    fact_remap:
      - match: { anchor: "feature.some-retired-thing#*" }
        action: tombstone
        reason: node-removed
```

Four `action` values, shared across every `op` (this is the part that generalizes — see §2.6):
`remap` (rewrite the fact's subject node id; content-keyed id changes; `reverify:
none|fast-path|full` per D16 O3's per-change-type default), `requeue` (drop to non-verified
status, re-enters the D24 verifier's stage-1 queue as a fresh claim, may get redrafted), `tombstone`
(dead end, no successor content — used for pure removals), `untouched` (explicitly recorded as
considered-and-unaffected, so the auto-generated impact-report table has a row for it instead of a
gap that looks like an oversight).

`migrate.py` is a thin, mechanical interpreter over this file: for each `fact_remap` entry, glob
the matcher against the corpus, apply the action (rewrite anchor/content-key, write a
`tombstones.yaml` entry, or no-op), then run the D23 normalizer. **The manifest is the source of
truth; `migrate.py` should need near-zero migration-specific logic** — the whole point of fixing
this DSL is that most migrations don't need bespoke Python at all, just a manifest and the shared
interpreter. A migration only needs custom script code for a transformation the DSL genuinely
can't express (rare, and D16's "idempotent script" language already anticipates that escape
hatch existing).

**Recommendation: 2.3b**, with the four-action vocabulary treated as closed (adding a fifth action
type is itself a tooling change worth its own review, not something individual migrations should
invent ad hoc).

### 2.4 Tombstone & supersession rendering — site + MCP

**The tombstone/redirect data already exists in two places that need reconciling, not
duplicating:** D23's `tombstones.yaml` (fact-id level, from ordinary corrected-value churn) and
D16's migration manifests (which are the *cause* of a subset of those same tombstone entries when
a `remap`/`tombstone` action fires). **Recommendation: migrations do not get a separate tombstone
ledger.** A `remap`/`tombstone` action in a manifest, when applied by `migrate.py`, appends to the
*same* `tombstones.yaml` D23 already defined, with an added `migration_id` field on the entry so
provenance is traceable back to the RFC without needing a second file format:

```yaml
- old_fact_id: f-3a9c1e7b2f04
  successor_fact_ids: [f-91b2c4d8e610]     # empty list for pure tombstone/removal
  reason: split                             # split | merge | move | removal | corrected-value
  migration_id: "0007-split-pattern-matching"   # null for ordinary corrected-value tombstones
  superseded_at: "2027-02-14T00:00:00Z"
```

**Resolution algorithm (shared by site build and MCP, one implementation):** given a fact id,
check `tombstones.yaml`; if present, follow `successor_fact_ids` — which may themselves be
tombstoned (a fact remapped in one migration, then remapped again in a later one) — recursively
until reaching terminal, live fact ids or an empty successor list (pure tombstone). Cap the walk
at a small fixed depth (e.g. 5 hops) with a loud error if exceeded, since an unbounded chain would
indicate a data bug, not a legitimate migration history.

- **Site rendering:** a tombstoned fact's old `data-fact-id` anchor (D10) resolves to a small
  static page (not a 404): "This fact was superseded during migration
  [0007-split-pattern-matching](link to changelog entry, §2.5) — see current fact(s): [list,
  linked]." A pure-tombstone (no successor) renders "This fact was retired: [reason], see [RFC
  link]." For **node-level** supersession (a split/merge/removal's old feature/instance page, not
  an individual fact), this rides D16 O3's existing URL policy — a hub/disambiguation page for
  splits (not a redirect), a 301 for merges, a "retired features" index entry for removals — this
  topic adds nothing new to that policy, just confirms the fact-level tombstone page follows the
  same "never a bare 404" principle.
- **MCP rendering (`get_fact`):** on a tombstoned id, return a structured object rather than an
  error — `{status: "superseded", old_fact_id, successor_fact_ids: [...], migration_id, reason,
  chain: [...]}` — and, per D35's already-ratified caution contract, **include the resolved
  successor fact(s)' full content inline** (not just their ids), each with its own mandatory
  `caution` block, plus a plain-text-prepended note on the *response* itself ("this id was
  superseded on {date}; showing current fact(s) instead") so a consuming agent that logged this id
  months ago gets the current answer without a second round-trip. A pure tombstone (empty
  successor list) returns the same shape with `successor_fact_ids: []` and the reason in the note,
  never a bare not-found. **`get_feature`/`get_neighbors` on a dead node id** get the analogous
  treatment, but the payload differs by casebook row: a split's old node returns the *hub content*
  itself (children list + concept description — the hub page has real content, unlike a dead fact
  id, so there's nothing to "resolve through," per open question 4 below), a merge's old node
  returns a redirect-shaped pointer to the merged node, a removal returns the pure-tombstone shape.

**Recommendation:** one shared resolution routine (chain-walk with depth cap) reused by the Astro
build (static tombstone pages) and the MCP server (structured `get_fact`/`get_feature` responses),
built on the *existing* `tombstones.yaml` format with one added field, not a parallel ledger.

### 2.5 Ontology diff visualization

**What it's for** — the brainstorm-22 topics list floated this as serving two purposes at once:
RFC review (so the developer, gating on process per D16 O5b, can actually see the blast radius
without reading raw YAML diffs) and a public changelog/transparency artifact (so the "MAJORs are
the one human-gated exception" story is auditable by anyone, not just legible to the developer).
Both purposes want the same underlying data (§2.1's script output + the manifest + the
CHANGELOG.md entry) rendered two ways: a review-time view (attached to the PR, seen once) and a
permanent public view (a site page, seen by anyone curious why a URL now redirects).

**How heavy a tool, given D10's zero-JS static-first constraint and "boring, solo-maintainable
technology":**

- **Option 2.5a — a full interactive graph-diff tool** (D3-force-directed before/after graph,
  Cytoscape.js, or similar), rendering the taxonomy as a navigable node-link diagram with
  added/removed/changed nodes highlighted. Rejected outright: at low hundreds of nodes and
  ~monthly MAJORs, this is disproportionate infrastructure for a solo-maintained project — it's a
  new client-side library, a new failure surface, and a new thing to keep in sync with the schema,
  for a use case (a human reviewing one migration's blast radius) that a table already serves.
- **Option 2.5b (recommended) — a structured, static diff table**, generated at build time
  straight from the manifest + CHANGELOG entry, no client JS: nodes added / removed / renamed /
  split (with children) / merged (with source nodes) / moved (old → new layer/dimension), plus the
  fact-disposition summary counts already computed for the impact report (§2.1/2.2). For the two
  relational change types (split, merge) where a flat table loses the parent↔child shape, an
  **indented plain-text tree** (no graph rendering, just nested list markup — same technique
  already used for section breadcrumbs in D15's source chunks) is sufficient to show "pattern-
  matching → {destructuring, guards, exhaustiveness-checking}" without a layout engine.
- Publish as `/changelog/ontology/<migration-id>/` under the site IA (matching D10/D19's existing
  "generated from the structured data layer, no runtime service" pattern) for the public view; the
  identical render (same generator, different output target — a PR comment or committed
  `impact.md` fragment) serves the RFC-review use case, so there is exactly one diff renderer, not
  two.

**Recommendation:** 2.5b — a build-time static diff table/tree, one generator feeding both the
RFC-review artifact and the public changelog page; explicitly reject an interactive graph library
as scope the project's scale and maintenance posture don't justify.

### 2.6 Wiring topic 28's `edition-superseded` source tombstone into the same shape

D37 already ratified the *policy*: a new spec edition ingests as a new versioned `source_id`, the
old one gets `custom.superseded_by: <new-source-id>`, and this fires a freshness-staleness trigger
on facts citing it — explicitly *not* an automatic remap or re-verification (facts stay verified
against their archived snapshot; only their `freshness` axis flips to `stale`). The question this
topic has to answer is purely structural: does that already-decided mechanism *reuse* §2.3's DSL,
or does it need its own?

**It reuses the same four-field shape, one op lighter.** Source-edition supersession maps onto
§2.3's vocabulary almost exactly:

```yaml
# sources/_tombstones.yaml — a sibling ledger, same shape as ontology/migrations manifests,
# but append-only and NOT gated by an RFC (see governance note below)
- op: supersede                      # the fifth op — source-registry-scoped, not node-scoped
  kind: source                       # distinguishes this ledger's entries from ontology-node ops
  from: source.ecma-262-2025
  to: source.ecma-262-2027
  reason: edition-superseded
  detected_by: edition-check-job     # vs "rfc" for every ontology-node op above
  fact_remap:
    - match: { citing_source: source.ecma-262-2025 }
      action: flag-stale             # a fifth action, source-scoped: sets freshness=stale,
                                      # reason=edition-superseded — never remap/requeue/tombstone,
                                      # since D37 was explicit that facts stay verified against
                                      # their archived snapshot and re-verification is opt-in, not
                                      # automatic
  superseded_at: "2027-06-01T00:00:00Z"
```

**Where it differs, and why that's still "the same shape one level up" rather than a different
mechanism:**

- **Node kind, not fact kind.** `from`/`to` reference `source_id`s, not ontology node ids — the
  DSL's matcher (`fact_remap[].match`) already needed to key off arbitrary reference fields (it
  matches on `anchor` for ontology ops), so keying on `citing_source` instead is the same
  matcher machinery pointed at a different join column (facts → `sources:` list entries rather
  than facts → subject node id).
- **A new `action: flag-stale`**, not a reuse of `remap`/`requeue`/`tombstone`/`untouched`. This is
  the one genuinely new piece of vocabulary this topic adds, and it's deliberately narrow: it only
  ever flips the D25 `freshness` axis, never touches a fact's content, id, or verification status —
  exactly matching D37's ratified "never retroactively unverifies" rule. §2.3's four-action set
  stays closed *for ontology-node ops*; this is a fifth action scoped to `kind: source` entries
  only, not a reopening of the ontology-node vocabulary.
- **Different trigger and governance path — this is the actual "one level up," not a detail.** An
  ontology-node op is authored by a human/agent RFC and gated by D16 O5b's process review. A
  `supersede` entry is authored automatically by D37's quarterly edition-check job with **no RFC
  and no human gate** — because, as D37 already established, it never touches a fact's *meaning*,
  only a citation's freshness, so it doesn't meet D16's own MAJOR bar ("a fact's meaning or
  validity affected") in the first place. It is closer to a MINOR/PATCH-weight event that happens
  to live in the same ledger shape as MAJOR-weight ones. Concretely: **`sources/_tombstones.yaml`
  is a separate append-only file from `ontology/migrations/*/manifest.yaml`**, sharing the schema
  (so one interpreter and one diff/rendering tool handle both, per below) but not the location or
  the write path — the edition-check job writes directly, an ontology-node op only ever lands via
  the RFC→PR→merge pipeline.

**Consequences for the rest of this topic's tooling, now that this is confirmed as one shape:**

- **§2.1's blast-radius script** already supports `--kind source` (stated there) — running it
  against a source id returns "N facts cite this source" the same way it returns "N facts
  reference this node" for an ontology id; the edition-check job can call it to populate the
  `fact_remap` list automatically (every fact citing the old source gets a `flag-stale` entry —
  fully mechanical, no draft-then-edit step needed the way §2.1b's ontology-node drafting does,
  since there's only one possible action).
- **§2.4's resolution routine** extends to `get_source`: querying a superseded `source_id` returns
  the same `{status: "superseded", successor_id, reason, chain}` shape `get_fact` returns for a
  dead fact id, chain-walked the same way (a source could in principle be superseded twice before
  any fact re-verifies — the walk logic is identical). The site's per-source citation popover
  (D10) gains one line when the cited source is superseded: "a newer edition exists" with a link,
  reusing the exact rendering component built for fact-level tombstone pages.
- **§2.5's diff visualization** does *not* need a source-supersession view of its own — it's a
  routine freshness event, not a taxonomy change, and doesn't belong on the ontology changelog
  page; it already has a home in D25's staleness/re-verification reporting, which this topic
  doesn't need to touch.

**Recommendation:** confirm the fold-in as structural, not cosmetic — one `op`/`action` vocabulary,
one blast-radius script, one resolution routine, shared across `ontology/migrations/` (RFC-gated,
MAJOR-weight) and `sources/_tombstones.yaml` (job-triggered, ungated, freshness-weight only),
distinguished by `kind` and by *where* the ledger lives and who's allowed to write to it — never by
a second parallel schema.

## 3. Recommendation (*proposed*)

1. **Blast-radius script** (§2.1): one mechanical tool, `--kind {ontology-node|source}`, computing
   direct/indirect fact references, affected URLs, estimated re-verification cost from the D26
   cost log, and downstream artifact touch counts; drafts a starting `fact_remap` list using each
   casebook row's default action (split→requeue, merge→remap/fast-path, move→requeue only for
   classification-asserting facts, removal→tombstone), fully human/agent-editable afterward.
2. **RFC + impact templates** (§2.2): a fifth GitHub Issue Form matching D32's existing pattern,
   with a `change_type` dropdown that routes to the right casebook row and a required
   dissenting-evidence field; an `impact.md` template split into an auto-generated section (CI
   diff-checked against a fresh blast-radius run, never hand-edited) and an authored rationale
   section. Build both before the first real MAJOR needs to happen.
3. **Migration-manifest disposition DSL** (§2.3): a typed `op` vocabulary (`split | merge | move |
   remove`) matching D16 O3's casebook rows one-to-one, each carrying a `fact_remap` list of
   matcher→action entries from a closed four-action set (`remap | requeue | tombstone |
   untouched`); `migrate.py` becomes a thin shared interpreter over this manifest, needing
   migration-specific code only for transformations the DSL genuinely can't express.
4. **Tombstone/supersession rendering** (§2.4): migration-triggered tombstones append to D23's
   existing `tombstones.yaml` (one added `migration_id` field) rather than a parallel ledger; one
   shared chain-walking resolution routine (depth-capped) serves both the Astro build (static
   never-404 tombstone pages, hub pages for splits per D16's existing URL policy) and the MCP
   server (`get_fact`/`get_feature`/`get_neighbors` on a dead id return a structured
   `{status: superseded, successor(s), chain}` object with resolved successor content inline,
   wrapped in D35's mandatory caution-block contract — never a bare not-found).
5. **Ontology diff visualization** (§2.5): a build-time static diff table/tree (nodes
   added/removed/renamed/split/merged/moved, fact-disposition counts), generated once from the
   manifest + CHANGELOG and reused for both the RFC-review artifact and a public
   `/changelog/ontology/<migration-id>/` page. Explicitly reject an interactive graph-rendering
   library as disproportionate for low-hundreds-of-nodes, ~monthly-MAJOR scale.
6. **Topic-28 fold-in** (§2.6): confirmed structural — `sources/_tombstones.yaml` reuses the exact
   same `op`/`fact_remap`/action schema as `ontology/migrations/*/manifest.yaml`, adding one new
   op (`supersede`, source-scoped) and one new action (`flag-stale`, the only action that never
   touches fact content/id/verification status, matching D37's "never retroactively unverifies"
   rule), written automatically by the D37 quarterly edition-check job with no RFC and no human
   gate — the governance split (RFC-gated ontology-node ops vs. job-triggered ungated source ops)
   lives in *where the ledger is and who writes to it*, not in a second schema.

## 4. Open questions for the developer

1. **Blast-radius script scope** — should it also count `source_chunks`, debate records, and chat
   logs referencing a node (a fuller "who's affected" picture for the impact report), or stay
   scoped to facts/edges/rules per D16's original blast-radius definition, leaving those other
   corpora out of the RFC's stated blast radius entirely?
2. **Disposition-DSL exhaustiveness** — should CI hard-require every fact anchor the blast-radius
   script finds to appear in some `fact_remap` entry of the submitted manifest (an exhaustiveness
   check that fails the PR on any gap), or is `action: untouched` allowed to be an implicit default
   for anchors the manifest's author simply didn't enumerate?
3. **Ontology changelog page placement** — one static page per migration under
   `/changelog/ontology/<id>/`, or a single rolling page listing all migrations chronologically
   with per-entry detail sections? Does it need its own top-level site IA slot, or fold under an
   existing docs/about section?
4. **`get_feature` on a split's old node id** — since the old node becomes a hub page with real
   content (children + concept description) rather than a dead reference, should `get_feature`
   return that hub content directly in the normal feature-object shape, or wrap it in the same
   `{status: superseded, ...}` envelope `get_fact` uses for dead fact ids, even though there's
   nothing dead about a hub page's content?
5. **Source-tombstone chain depth in practice** — if a spec undergoes two edition bumps before any
   citing fact re-verifies, should `get_source` auto-walk to the latest edition transparently (per
   §2.4's chain-walk), or stop at the first hop and require the caller to re-query, on the theory
   that a caller citing a specific edition may have meant that edition specifically?
6. **RFC objection-window enforcement** — is a mechanical CI/bot check (blocking merge until the
   issue has been open for the batching-cadence duration) worth building, or does this stay trusted
   to the developer's own process discipline, consistent with D16 O5b already framing the merge gate
   as a developer-run checklist rather than an automated one?

## 5. New brainstorm topics surfaced

- **Disposition-DSL exhaustiveness/validation as a CI check** — a mechanical validator (does every
  blast-radius-discovered anchor appear in the manifest's `fact_remap`? does every `target` in a
  `remap` action reference a node the manifest itself declares in `to`?) is exactly topic 40's
  stated scope ("the one offline tool shared by CI and the agent runner's pre-commit gate") —
  **fold into topic 40**, not a new number.
- **Ontology changelog page's site-IA placement** — where `/changelog/ontology/` sits relative to
  the rest of the site (a top-level nav item vs. tucked under an existing docs area) is a routine
  IA decision of the kind topic 06/19 already made for the rest of the site — **fold into topic 19
  (website deep-dives)** as a small addendum rather than a new number, since 19 already owns
  "trust-signal UX" and static page-kind templates in the same spirit.
- **Blast-radius script's non-fact corpora (chat logs, `source_chunks`)** — if open question 1 is
  answered "yes, broaden the scope," reading debate/chat-log references into an impact report
  overlaps with topic 32's pipeline-observability surface ("whether `provenance.candidate_source`
  belongs in a broader 'why did the pipeline look here' telemetry model") — **fold into topic 32**
  if and when that broadening is greenlit, not designed here speculatively.
- No genuinely new, undesigned topic emerged beyond the four backlog items brainstorm 22 already
  named (RFC/impact tooling, the disposition DSL, tombstone rendering, diff visualization) — this
  brainstorm designed all four plus the topic-28 fold-in, closing out that list rather than
  extending it.
