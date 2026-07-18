# 22 — Ontology Versioning

> Round-2 brainstorm. Topic: a system for future schema/ontology changes. Binding context:
> git YAML repo is canonical (D1); nothing is owner-curated — the feature model itself is
> open to community/agent-driven change (D2 amendment); a heavy frontloaded research phase
> produces ontology v1 (D11) but changes WILL keep coming; stable URLs (D10); facts hang
> off ontology nodes; Postgres + embeddings are derived (D7). Addresses risks K2
> (ontology/schema instability) and K4 (ontology validity) from 08-services-risks.md.

## Problem framing

The ontology is Hermes' load-bearing wall and, per D2, it is deliberately *not* frozen:
new features, re-atomizations ("pattern matching" splitting into destructuring + guards +
exhaustiveness), layer moves, and dimension restructurings are expected outcomes of the
evidence-and-challenge process, not failure modes. Every such change ripples through four
coupled artifacts:

1. **Facts** — each fact binds a sourced sentence to a machine claim *about an ontology
   node*. Change the node's meaning and the fact may no longer say what it verified.
2. **Fact IDs** — D11 mandates deterministic content-keyed IDs. If the content key
   includes the node reference, every node change churns IDs, breaking cross-references,
   challenge deep-links (D9), and `data-fact-id` anchors on the site (D10).
3. **URLs** — D10 promises stable slugs + a 301 policy; SEO equity and inbound links hang
   on `/features/<slug>/`.
4. **Derived stores** — Postgres, the vector index, the static site. By D1/D7 these are
   one-way build artifacts, which is the great simplifier: *no derived store ever needs a
   migration*. Rebuild from the repo is the only downstream operation. (Embeddings
   confirmed a non-issue below.)

Two distinct things get versioned and they change at very different rates:

- **Structural schema** — the JSON Schemas for entity files (Feature, FeatureInstance,
  SyntaxExample, Edge, Rule, Fact, Source, Concept). Changes here are classic data-schema
  evolution: add a field, tighten a constraint, restructure a file layout. Tooling
  problem, well understood.
- **Taxonomy** — the actual node set: the feature tree, the layer assignments, the
  dimension list, the edge-type and quality vocabularies. Changes here are *semantic*:
  they alter what existing facts are about. This is the hard part, because "the API" is a
  corpus — a version bump doesn't break compilers, it silently un-verifies sentences.

The absence of a human merge gate for facts (D1) sharpens the question in §5: fact-level
noise is self-correcting via challenges, but a bad taxonomy change is a corpus-wide
contamination event. Does the "nothing is owner-curated" principle still permit a gate on
*ontology* changes?

A scale sanity check keeps this honest: low hundreds of features, tens of thousands of
facts. Any corpus-wide migration is a script over a few thousand YAML files that runs in
seconds and produces a reviewable git diff. The machinery below is process discipline,
not infrastructure.

### The single most important prerequisite: separate node identity from node slug

Almost every hard case below becomes tractable if a taxonomy node has **two names**:

- `id` — an immutable opaque-ish identifier minted once at node creation (it can *start*
  as the initial slug for readability, e.g. `pattern-matching`, but it never changes
  thereafter, even if the display name and URL do).
- `slug` — the URL/display identity, renameable, with every historical slug preserved in
  a versioned redirect map.

Facts, edges, rules, and content keys reference `id`, never `slug`. Then a **rename is a
patch-level event** (redirect entry + display change, zero fact churn), and only genuine
semantic events (split/merge/move) touch facts. Without this separation, every rename is
a fake "major" and the version signal drowns in noise. This refines, not contradicts,
D11's content-keyed IDs: the content key hashes the canonical claim *with node `id`s
substituted*, so it stays deterministic and rename-proof.

## Options with trade-offs

### O1 — What "the ontology" is as an artifact, and the version scheme

**Option 1a: one monolithic semver for schema + taxonomy together.**
A single `ontology/VERSION` covering JSON Schemas and the node set.
- Pros: one number to stamp on facts; one changelog; consumers reason about one axis.
- Cons: during the research phase and the open-contribution era, *additive* taxonomy
  changes (new feature, new instance) are near-daily; either the minor version spins like
  an odometer (harmless but noisy) or people stop bumping it (worse).

**Option 1b: two versions — `schema_version` (structural) and `taxonomy_version`
(semantic).**
- Pros: structural and semantic change genuinely have different consumers (validators vs
  fact-verifiers) and different cadences.
- Cons: two numbers to stamp, explain, and keep coherent; every process doc doubles its
  conditionals; in practice the schema and taxonomy co-evolve (a split often needs a new
  field), so the split is less clean than it looks.

**Option 1c: one semver, with semantics defined by blast radius on facts (recommended
shape).** The version is a *contract about the corpus*, not about file formats:

- **MAJOR** — at least one existing fact's *meaning or validity* is affected: feature
  split or merge, layer/dimension move that changes exclusivity semantics, edge-type
  semantics change, removal of a node or field, tightening validation in a way existing
  files fail. Requires a migration script + impact report (see O2, O5).
- **MINOR** — purely additive; every existing fact remains byte-identical and valid: new
  feature/dimension/concept, new optional schema field, new edge type, new language.
  Auto-bumped by CI when a merged commit adds nodes; no migration needed.
- **PATCH** — no data-semantic change at all: description wording, slug rename (thanks to
  id/slug separation), schema doc-comments, validation additions that the whole corpus
  already passes, redirect-map entries.

Facts additionally record the git commit they were authored at (they get this almost for
free from git), so the coarse semver is a human-legible summary while the commit is the
precise coordinate.

**Concrete artifact layout** (KB repo):

```
ontology/
  VERSION                # single semver, e.g. 2.3.0
  CHANGELOG.md           # human log, one entry per bump; MAJOR entries link their RFC
  schema/                # JSON Schemas, one per entity type
    feature.schema.json
    feature-instance.schema.json
    fact.schema.json
    ...
  taxonomy/
    layers.yaml          # layer definitions (1 syntax / 2 semantic / 3 design-choice)
    dimensions.yaml      # dimension list + exclusivity mode (exclusive|multi)
    edge-types.yaml      # the 7 edge types + semantics prose
    qualities.yaml       # controlled quality vocabulary
  redirects.yaml         # versioned slug history: old-slug -> current id (feeds 301 map)
  migrations/
    0001-split-pattern-matching/
      migrate.py         # idempotent, operates on the YAML tree
      manifest.yaml      # machine-readable: nodes touched, fact disposition rules
      impact.md          # agent-drafted impact analysis (see O5)
features/ ... languages/ ... facts/ ... sources/   # the corpus itself
```

Note the feature *files themselves* are corpus, not `ontology/` — but the ontology's
"node set" is simply the set of feature files, so taxonomy changes are ordinary corpus
commits that CI classifies (additive → minor; manifest present → major).

### O2 — Migration discipline

Little genuine disagreement here; the options are about strictness.

**Option 2a: migrations as reviewed, committed scripts; migrated corpus committed in the
same PR (recommended).** A MAJOR change ships as one PR containing (i) the schema/
taxonomy edit, (ii) `migrations/NNNN-*/migrate.py`, (iii) the *result of running it* —
the full corpus diff, and (iv) the impact report. CI re-runs the script from the parent
commit and asserts the tree matches the committed result (determinism check), then runs
full corpus validation (schema, referential integrity, dangling edges, citation
integrity, redirect-map completeness). Rollback = `git revert` of one commit, then
rebuild derived stores. No down-migration scripts ever — git is the down-migration, and
derived stores are rebuilt, not migrated (D1/D7).

**Option 2b: migrations applied by CI after merge (script-only PRs).** Cleaner diffs to
review, but the canonical repo briefly disagrees with what was reviewed, and a failed
post-merge migration leaves main broken. Rejected: at this corpus size the full diff is
reviewable and having reviewed-tree == deployed-tree is worth more.

**Option 2c: no scripts, hand-edit the corpus.** Fine for one file; corpus-wide semantic
changes hand-edited across thousands of files is exactly the "silent data loss" of risk
S3. Rejected for anything beyond patch-level edits.

Standing CI invariants regardless of option: every commit validates the *whole* corpus
against the current schemas; the YAML normalizer (D11) runs so diffs are semantic;
`redirects.yaml` must cover every slug that has ever existed (a CI check keeps a
slug-history ledger and fails if one goes missing).

### O3 — The semantic-change casebook

The core policy choice, per change type: **remap** (mechanically rewrite the fact's node
reference; claim text untouched) vs **invalidate-and-requeue** (fact drops to a
non-verified status and re-enters the verification pipeline of D4, possibly redrafted).
The dividing line: *did the subject's extension change?* If the new node denotes the same
set of things the source was talking about, remap; if the node's meaning narrowed,
widened, or split, the source-supports-claim judgment must be redone.

| Change | Facts | Fact IDs (content-keyed) | Slugs / URLs | Embeddings |
|---|---|---|---|---|
| **Rename** (display/slug only) | Untouched (facts reference `id`) | Unchanged | Old slug → 301 via `redirects.yaml` | Rebuild (label appears in rendered card) |
| **Split** (pattern-matching → destructuring + guards + exhaustiveness) | Agent drafts a per-fact disposition: facts whose claim clearly concerns one child → remap to it, **but re-verify** (the verifier is cheap, academic-API tier, and the claim's subject changed); ambiguous or umbrella facts → invalidate-and-requeue for redraft against the right child. Old node either dies or survives demoted to a **Concept** (thin, pedagogical) that `realizes`-links the children | Change for remapped facts (subject id differs). New fact records `derived_from: <old-fact-id>`; old ID kept as a tombstone entry so challenge links and external references resolve to a "superseded by" page | **No 301** — old URL becomes a hub/disambiguation page for the children (or the Concept page). 301-ing to one child would misdirect; a hub preserves SEO and reader intent | Rebuild |
| **Merge** (A + B → C) | Mechanical remap A→C, B→C; claim text unchanged, so re-verification is a fast-path entailment check (subject broadened — usually still entailed). Duplicate claims dedupe by content key. Contradictory A-facts vs B-facts become first-class contradictions (D5) — a feature, not a bug: merges surface hidden disagreement | Change (subject id differs); `derived_from` + tombstones as above | Both old URLs 301 → new slug | Rebuild |
| **Layer move** (2 ↔ 3) / **dimension move or restructure** | Facts *about the feature* (edges, instances, qualities) untouched — their subject didn't change meaning. Facts that assert the classification itself ("X is a design-choice in dimension Y") invalidate-and-requeue. Dimension exclusivity is derived from `dimensions.yaml`, so Rules and `alternative-to` edges in the affected dimension enter a review queue (exclusivity semantics may have flipped) | Unchanged for untouched facts | Unchanged — D10's flat `/features/<slug>/` IA deliberately does **not** encode layer or dimension in URLs; this is why. Never add hierarchy to feature URLs | Rebuild |
| **Node removal** (feature judged not-a-thing) | Invalidate all; facts tombstoned with reason + link to the RFC | Tombstoned | URL → 301 to nearest ancestor Concept or a "retired features" page with the story | Rebuild |

**Embeddings — confirmed non-issue.** The vector index is a derived artifact (D7) rebuilt
by `make index`; the university API exposes embedding models at no cash cost (D6), the
corpus is tens of thousands of short chunks, and the content-hash cache means only
touched facts re-embed. The only rule worth writing down: the embed-cache key must hash
the *rendered fact card* (which includes node names and ontology labels), not just the
fact file, so renames and remaps correctly invalidate cache entries. Postgres likewise:
`make db` from scratch, never `ALTER`.

**Tombstones.** A tiny `facts/_tombstones.yaml` (or per-fact `status: superseded` stubs)
mapping dead fact IDs → successor ID(s) + migration ID. Cost: near zero. Benefit: D9
challenge deep-links, agent chat logs (D1), and external citations of fact IDs never
404 into confusion. The site renders a "this fact was superseded during migration NNNN"
page. Without tombstones, content-keyed IDs make every split/merge silently orphan
history.

### O4 — Provenance and staleness

**Option 4a: stamp facts with `ontology_version` at authoring; staleness =
authored-major < current-major.** Simple, but coarse both ways: a fact authored under
v2 whose nodes were never touched by v3's migration is flagged stale for nothing, and
version alone doesn't say *what* to re-check.

**Option 4b: migration manifests are the source of staleness; the version stamp is a
backstop (recommended).** Every MAJOR migration's `manifest.yaml` lists touched node ids
and the disposition applied per fact (remapped / requeued / untouched-but-flag). "Stale"
is then precise: a fact is stale iff some migration since its authored version touched
its subject nodes *and* its disposition demanded re-verification that hasn't completed.
Facts also carry `ontology_version` (+ authored commit, via git) so the coarse rule
"authored-under < current-major ⇒ include in the next audit sweep" still exists as a
safety net for anything a manifest missed. Staleness is a first-class fact status
feeding the brainstorm-12 status model and the D1 work queue, and renders on the site as
"verified under ontology v2; re-verification pending" rather than silently presenting as
current.

### O5 — Governance: who may change the ontology

Facts have no human merge gate (D1) — admissibility is source-backed verification. Can
ontology changes ride the same rail?

**Option 5a: fully ungated, same as facts.** Most consistent with "nothing is
owner-curated." But the D4 verifier is category-mismatched here: it checks that a source
supports a *claim*; it cannot check that a taxonomy carve is coherent, that the
migration's fact dispositions are sensible, or that the blast radius is acceptable.
A major change is also not independently challengeable the way one fact is — by the time
a human expert objects, thousands of facts have been remapped and re-verified against the
new carve. Unattended majors turn K2 from a risk into a routine.

**Option 5b: human (owner) merge gate on MAJOR changes only; MINOR/PATCH ride the
ungated rail (recommended).** The reconciliation with D2's "nothing is owner-curated":
the owner gates *process*, not *content*. The change itself must arrive as an RFC —
anyone (agent or human) opens an issue with motivation and evidence, then a PR per O2
containing the migration + corpus diff + an **agent-drafted impact report**: N facts
remapped / M requeued / K tombstoned, URLs redirected, dimensions whose exclusivity
changed, estimated re-verification cost, dissenting evidence. The owner's merge decision
is a checklist ("RFC had its objection window; CI green; dispositions per the O3
casebook; impact acceptable"), not a judgment on whether guards are *really* distinct
from destructuring — that judgment lives in the RFC's cited evidence and any structured
debate (D5) it triggered. Crucially, the *common* community action — adding a feature,
dimension, instance, or edge — is MINOR and stays ungated, so the open-contribution
promise holds for 95% of taxonomy activity. This is the same shape as D1's own carve-out:
verification gates exist; they're just not human — except here, where no automated
verifier for the property in question exists yet.

**Option 5c: objection-window auto-merge (no human, majors merge after e.g. 14 days
without unresolved structured objections, with an agent quorum re-review).** The
principled endpoint if the owner wants zero human gates. Workable later, once there is a
community whose silence means something; today (no experts lined up, D9) a timeout gate
is just 5a with latency. Recommend writing it into the RFC template as the *stated
successor* to 5b — the owner gate is explicitly transitional — which keeps the
philosophy honest without betting the corpus on it now.

**Frequency guard.** MAJORs should be batched: RFCs accumulate, and migrations land in
occasional coordinated version bumps (e.g. at most monthly outside the research phase)
so re-verification sweeps amortize and the site's "under ontology vN" story stays
legible. During the D11 research phase, pre-v1.0 (0.x) semantics apply: everything is
fluid, majors are cheap, and no staleness machinery runs until v1.0.0 is declared at
research-phase exit.

### O6 — Later entry of the deliberately-excluded concepts (scope, exceptions, security, naming)

These were excluded as "hard to atomize," not "not real." The versioning system should
make their eventual entry an ordinary event:

1. **Concept-first staging.** Each excluded notion can enter *today* as a thin Concept
   node (D2) with sourced facts hanging off it, no feature atomization required.
   Concepts don't participate in the builder or combination validation, so this is MINOR
   and risk-free. The Concept page accumulates the evidence that later justifies an
   atomization RFC. This gives the excluded four a home without forcing the model.
2. **Atomization as a standard split.** When evidence matures, "scope" atomizes into
   features (lexical scoping, dynamic scoping, block scope…) via the O3 split machinery —
   the concept stays as the pedagogical parent. Nothing new to invent.
3. **Cross-cutting concerns need one schema affordance now:** an optional
   `cross_cutting: true` marker (or equivalently, dimensions flagged `multi` +
   features allowed to carry edges into *many* dimensions) so that when
   exceptions/security enter, they aren't forced into single-dimension exclusivity that
   misrepresents them. Adding the optional field now is PATCH; needing it later without
   having it would force a MAJOR.
4. **Watch the existing collision:** the brief *both* excludes "Exceptions" as a concept
   *and* lists an `Exceptions: checked/unchecked/effect-system` dimension in layer 3.
   That dimension will likely be the first customer of the split/move machinery once the
   exceptions Concept matures — a good early test that the process works.
5. **Naming** may never atomize into checkboxable features and that's fine: it can live
   permanently as a Concept with `influences` edges into feature pages ("Haskell's
   pattern-matching naming cuts across…"). The model doesn't break because the model
   never required every concept to become a feature.

## Recommendation

1. **Split node `id` (immutable, minted once) from `slug` (renameable, redirect-mapped).**
   Facts and content keys reference `id` only. This single rule converts renames from
   corpus-wide churn into PATCH events and is a prerequisite for everything else. Adopt
   before the research phase mints any nodes.
2. **One semver in `ontology/VERSION`, defined by fact blast radius** (O1c): MAJOR =
   some fact's meaning/validity affected (split, merge, move with semantic effect,
   removal, breaking schema change); MINOR = purely additive (auto-bumped by CI);
   PATCH = no data-semantic change. `0.x` until the D11 research phase exits, then
   `1.0.0`. Artifact layout per O1c: `ontology/{VERSION, CHANGELOG.md, schema/,
   taxonomy/, redirects.yaml, migrations/}`.
3. **Migration discipline per O2a:** MAJOR = one PR with schema/taxonomy edit +
   idempotent `migrate.py` + the migrated corpus diff + manifest + impact report; CI
   replays the script and asserts determinism, then full-corpus validation. Rollback is
   `git revert` + rebuild; derived stores (Postgres, vectors, site) are always rebuilt,
   never migrated. No down-migrations exist.
4. **Semantic-change casebook per O3**, headline rules: split → agent-drafted per-fact
   disposition, remap-with-cheap-re-verify where the claim clearly concerns one child,
   requeue the rest; old split URL becomes a hub page, *not* a 301; merge → mechanical
   remap + fast-path re-verify, both old URLs 301; layer/dimension moves touch only
   classification-asserting facts (URLs never encode layer/dimension — keep D10's flat
   IA); every superseded fact leaves a tombstone (`derived_from` / `superseded_by`) so
   content-keyed ID churn never orphans challenge links or chat-log references.
   **Embeddings confirmed a non-issue** — rebuild from the repo with a content-hash cache
   keyed on the rendered card.
5. **Provenance per O4b:** facts stamp `ontology_version` at authoring; precise
   staleness comes from migration manifests (which fact, which disposition, re-verified
   or pending); the coarse "authored-major < current-major" rule is the audit-sweep
   backstop. Staleness is a visible fact status on the site, feeding the brainstorm-12
   status model.
6. **Governance per O5b:** ontology MAJORs are the *one human-gated exception* to D1 —
   RFC issue → objection window → PR with migration + agent-drafted impact analysis →
   owner merges on process criteria, not content authority. MINOR/PATCH (the vast
   majority of community taxonomy activity: new features, dimensions, instances, edges)
   stay on the ungated verified-fact rail. Write the O5c objection-window auto-merge into
   the RFC template as the stated successor once a real expert community exists. Batch
   MAJORs into occasional coordinated bumps.
7. **Excluded concepts enter via Concept-first staging** (O6): thin Concept nodes now,
   atomization later as ordinary splits; add the `cross_cutting` affordance to the
   feature schema up front; expect the layer-3 `Exceptions` dimension to be the first
   real exercise of the machinery.

## Open questions for the owner

1. **Do you accept being the merge gate for ontology MAJORs** (O5b) as the single
   exception to "nothing is owner-curated," on the understanding that you gate process
   (RFC held its window, CI green, casebook followed) rather than content? If not,
   choose: fully ungated majors (5a) or objection-window auto-merge from day one (5c)?
2. **Node `id` vs `slug` split** — confirm. It slightly weakens "IDs are human-readable
   slugs" from D3's spirit: after a rename, the immutable id (`pattern-matching`) and
   the current slug (`match-expressions`) can diverge. Acceptable cosmetic cost?
3. **Split-page policy:** old feature URL becomes a hub/disambiguation page rather than
   a 301 — happy with that as the standing SEO policy for splits (301s reserved for
   renames and merges)?
4. **Re-verification budget:** after a split, remapped facts get a cheap re-verify pass
   on the academic API. Is "re-verify everything touched" the default even when the
   remap looks mechanical (merges), or may merges skip re-verification entirely to save
   queue time? (Recommended: fast-path check even for merges — it's nearly free and
   K1-adjacent.)
5. **When is v1.0.0 declared?** Proposed trigger: research-phase exit criteria met
   (backlog brainstorm 25 should define them). Do you want a fixed feature-count /
   language-count threshold instead?
6. **MAJOR batching cadence:** is "at most ~monthly coordinated bumps" acceptable, or
   should genuinely urgent corrections (an actively-misleading carve) be allowed to land
   immediately?

## New brainstorm topics surfaced

- **Research-phase exit criteria & v1.0 declaration** — concrete definition of "the
  frontloaded phase is done," ontology quality metrics (coverage vs Jordan et al. /
  Van Roy & Haridi checklists), and the 0.x → 1.0 ceremony. (Extends backlog topic 25.)
- **RFC template + agent impact-analysis tooling** — the actual issue/PR templates and
  the script that computes fact blast radius, URL effects, and re-verification cost for
  a proposed taxonomy change; also the disposition DSL for migration manifests.
- **Tombstone & supersession rendering** — how superseded facts, retired features, and
  hub pages render on the site and resolve in the MCP server (`get_fact` on a dead ID
  should return the successor chain, not a 404).
- **Ontology diff visualization** — a human-legible "what changed between ontology v2
  and v3" page generated from manifests + changelog; doubles as the transparency artifact
  that makes the owner gate (or its 5c successor) auditable.
- **Cross-cutting concern modeling** — a dedicated pass on how `cross_cutting` features
  interact with the builder's combination validation (dimension exclusivity assumes
  tree-shaped choices; security/exceptions won't be tree-shaped).
