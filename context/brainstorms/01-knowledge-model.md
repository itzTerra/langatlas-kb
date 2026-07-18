# 01 — Knowledge Model & Data Architecture

## Problem framing

Hermes needs one knowledge model that serves four consumers at once: (1) the human-facing
website (feature pages, language pages, source links on every bit of info — brief §1
"Knowledge Base"), (2) the builder's combination validator (required/impossible/problematic
combos, layer 4 emergent interactions), (3) RAG for developer-managed agents (owner
constraint §2.1–2.2), and (4) human experts who must be able to challenge any fact,
possibly via GitHub files (§2.5a). The brief already gives the ontology skeleton
(concept / feature / feature-instance / characteristic, §1 Terminology) and the edge
vocabulary (requires, enables, influences ±, conflicts-with, alternative-to,
implemented-by, expressed-as, improves-quality, hurts-quality — §1 "Graph representation
idea"). The design questions left open are: how literally to take "graph database", what
the atomic sourced unit ("fact") is, where syntax lives, how combination rules beyond
pairwise edges are expressed, and how the store round-trips with human-readable files.

Scale reality check, because it drives everything: the feature model in the brief is on
the order of low hundreds of features, a few dozen dimensions, and (ambitiously) ~100
languages. That is at most a few tens of thousands of feature instances and edges. This is
a *small* graph. Nothing here needs a graph database for performance; the question is only
which representation is most maintainable for a solo developer.

### Mapping the terminology to entities

A key observation: two of the nine edge types are not really edges between peer feature
nodes — they are entities in disguise.

- **implemented-by** (feature → language) *is* the feature-instance. Reify it: a
  FeatureInstance row/file with its own id, so syntax, per-language notes, sources, and
  discussion links (brief: "link to GitHub discussion under each feature and language")
  have something to hang off. An edge cannot comfortably own all that.
- **expressed-as** (→ syntax) is likewise the SyntaxExample entity attached to a
  FeatureInstance, honoring the brief's hard rule that "feature type (functionality) must
  be separate from its syntax."

That leaves five true feature↔feature edge types (requires, enables, influences ±,
conflicts-with, alternative-to) and two feature→quality edge types (improves-quality,
hurts-quality). The quality list is fixed and small (practicality/efficiency, performance,
ease of use/learnability, reliability, compiler complexity, plus the Jordan et al. "other
factors"), so Quality is a small controlled vocabulary table, not free-form nodes.

- **Concept** — the abstract idea (e.g. "linear types" as theory). Mostly serves the
  website's pedagogy and the similarity view; features point up to concepts via a
  `realizes` link. Keep it thin.
- **Feature** — the graph's primary node type; the thing the builder selects. Carries the
  layer (1 syntax / 2 semantic / 3 design-choice — brief "Layers") and, for layer 3, its
  dimension (e.g. `memory-management`), since layer-3 choices are "mostly mutually
  exclusive" within a dimension.
- **FeatureInstance** — feature × language, owns syntax examples and per-language notes.
- **Characteristic** — the brief defines it as "an observable property of a system or
  feature instance." Treat it as a measured/observed attribute (e.g. TIOBE rank, GC pause
  behavior) attached to a Language or FeatureInstance, distinct from Quality, which is an
  *evaluative axis* that features improve/hurt. These are close enough to confuse; flagged
  as an open question below.

### What a "fact" is

The owner's constraint is blunt: "Every user-facing fact needs a source" (§2.1). The
cleanest reading: a **fact is a reified, sourced assertion** — one human-readable sentence
bound to exactly one machine-readable claim. Machine-readable claims come in three shapes:

1. an edge assertion (`ownership --hurts-quality--> learnability`),
2. an attribute assertion (`Rust.memory-management = ownership`, i.e. a FeatureInstance
   exists / has some property),
3. a combination rule (see below).

Every edge, feature instance, and rule that surfaces on the site must be backed by ≥1
fact; facts carry the citations. Facts are also exactly the right granularity for the
vector store: one fact = one prose statement = one embedded chunk, so RAG retrieval
returns units that already have provenance attached — the agents' "self-backing net of
information" (§2.4) falls out for free. Granularity rule of thumb: if a sentence contains
two claims that could be challenged independently, it is two facts.

### Combination validation, four levels

1. **Dimension exclusivity** — layer-3 features sharing a `dimension` are alternative-to
   each other implicitly; the builder allows one pick per dimension (or explicitly marked
   multi-select dimensions, e.g. concurrency models can coexist). No edges needed; the
   dimension field *is* the alternative-to group. Keep explicit `alternative-to` edges only
   for cross-dimension alternatives.
2. **Hard pairwise** — `requires` and `conflicts-with` edges. Builder treats these like a
   package manager's dependency/conflict resolution (the brief's Cargo analogy), which at
   this scale is a trivial propagation loop, not a SAT solver.
3. **Soft pairwise** — `influences` with polarity (and optionally weight): "problematic
   combination" warnings and "strongly encourages" suggestions (ADTs → pattern matching).
4. **Emergent interactions (brief layer 4)** — genuinely multi-feature: "multiple selected
   features can probably enforce or forbid a different feature." Pairwise edges cannot say
   *{lazy evaluation, impurity} ⇒ problematic*. Model these as a separate **Rule** entity:
   an antecedent feature-set plus an effect (`requires` / `forbids` / `warns` + message),
   each rule backed by facts like everything else. Evaluate rules in application code by
   simple set-matching against the current selection — boring and sufficient.

## Options with trade-offs

### Option A — Postgres as the single database: graph-in-relational + pgvector, with a facts repo as the canonical human-editable layer

Nodes and edges as plain tables; traversals via recursive CTEs (rarely needed — most
queries are 1-hop: "neighbors of this feature"). Embeddings in the same database via
pgvector, one row per fact. Sources in normal tables (explicitly blessed by owner note
§2.3). The Git repo of YAML/Markdown files is the *canonical* store for curated knowledge
(concepts, features, instances, edges, rules, facts, sources); a one-way compile step
loads it into Postgres. Runtime/community data (votes, usage rates, accounts, builder
submissions, comments) lives only in Postgres and never round-trips.

- Pros: one database to run and back up; the "compile-and-sync-back" con the owner worried
  about in §2.5a disappears because sync is one-directional (repo → DB); challenges happen
  as GitHub PRs/discussions, which is the owner's stated preference for minimum effort;
  every fact's provenance and edit history is git history; agents can propose facts as PRs
  that a human (or reviewer-agent) merges — a natural moderation gate for §2.4.
- Cons: a build pipeline to write and keep green (schema validation in CI); IDs must be
  stable slugs managed in files; contributors editing YAML need decent tooling/templates;
  upvote-driven ranking data is split from the fact data (arguably a pro).

### Option B — Database-canonical (Postgres), with generated read-only exports to GitHub

Same schema, but the DB is the source of truth; a job renders human-readable files to a
repo for transparency, and challenges come back through a custom forum module (§2.5b) or
GitHub issues that a human manually applies.

- Pros: no parser/compiler for files; admin UI edits are immediate; simpler when agents
  write facts constantly (they just INSERT).
- Cons: this is exactly the "compiled-and-synced-back" problem the owner flagged; exported
  files are second-class so "challenge via PR" doesn't really work (a merged PR has no
  path back into the DB without the reverse sync you were avoiding); requires building a
  forum module — significant scope for a solo MVP.

### Option C — Real graph DB (Neo4j/Memgraph) + relational DB + dedicated vector DB (Qdrant)

The "use the right specialized tool for each" architecture.

- Pros: Cypher is pleasant for edge-heavy exploration; graph visualizations nearly free;
  Qdrant's filtering is nice for RAG.
- Cons: three stateful services for a solo dev on a PoC; cross-store consistency (a fact's
  source in Postgres, its node in Neo4j, its embedding in Qdrant) becomes the developer's
  problem; nothing in the workload needs it — the graph is tiny and traversals shallow;
  violates the boring-tech constraint. Only worth revisiting if deep transitive queries
  ("everything transitively enabled by X, ranked by path influence") become a headline
  feature.

### Sub-option: SQLite instead of Postgres

Viable for the PoC (sqlite-vec for embeddings, litestream for backup) and maximally
boring, but the public website + community features (votes, submissions, concurrent
writes) will want Postgres eventually; starting there avoids a migration. Weak preference
for Postgres; SQLite acceptable if hosting cost dominates.

## Recommendation

**Option A.** Postgres (with pgvector) as the only database; a public GitHub "facts repo"
of YAML files as the canonical, human-challengeable knowledge layer; one-way compile
repo → DB in CI; community/runtime data DB-only. Entities: Concept, Feature (typed,
layered, dimensioned), FeatureInstance (reified implemented-by), SyntaxExample (reified
expressed-as), Quality (controlled vocabulary), Characteristic (observation on
language/instance), Edge (5 feature↔feature types + 2 feature→quality types), Rule
(emergent interactions), Fact (sourced assertion, unit of embedding), Source (CSL-JSON —
the modern ".bib"; BibTeX export is a solved one-liner, satisfying §2.1's "most
universal/modern preferred").

### File formats (canonical, in the facts repo)

```yaml
# features/memory-management/ownership.yaml
id: ownership
name: Ownership & borrowing
layer: 3                 # 1 syntax | 2 semantic | 3 design-choice
dimension: memory-management   # implies alternative-to siblings in this dir
realizes: [linear-types]       # -> concepts/
summary: >
  Compile-time tracking of value lifetimes ...
edges:
  - {type: requires,        to: move-semantics,   fact: f-own-001}
  - {type: influences,      to: raii, polarity: +, fact: f-own-002}
  - {type: hurts-quality,   to: learnability,     fact: f-own-003}
  - {type: improves-quality, to: reliability,     fact: f-own-004}
facts:
  - id: f-own-003
    claim: "Ownership hurts learnability"        # machine-checkable binding
    statement: >
      Rust's ownership and borrowing rules are consistently reported as the
      steepest part of the language's learning curve.
    sources: [klabnik2019, rust-survey-2023]
```

```yaml
# languages/rust/instances/pattern-matching.yaml
feature: pattern-matching
language: rust
since: "1.0"
notes: "match is exhaustive; guards and bindings supported."
syntax:
  - title: Basic match
    code: |
      match msg {
          Message::Quit => ...,
          Message::Move { x, y } => ...,
      }
    source: rust-book-ch6
facts:
  - id: f-rust-pm-001
    claim: "rust implements pattern-matching"
    statement: "Rust provides exhaustive pattern matching via match expressions."
    sources: [rust-book-ch6]
```

```yaml
# rules/laziness-needs-purity.yaml
id: laziness-needs-purity
when-all: [lazy-evaluation, impure]
effect: warn            # requires | forbids | warn
message: "Lazy evaluation with unrestricted side effects makes evaluation order observable."
facts: [f-rule-001]
```

Sources live in `sources/*.json` as CSL-JSON items keyed by citation id.

### Relational schema sketch (compiled target + runtime data)

```sql
feature(id slug PK, name, layer int, dimension, summary, concept_id?)
feature_edge(id PK, from_feature, edge_type, to_feature?, quality?,
             polarity?, fact_id)          -- CHECK edge_type in the 7 types
feature_instance(id PK, feature_id, language_id, since, notes)
syntax_example(id PK, instance_id, title, code, source_id)
rule(id PK, effect, message);  rule_antecedent(rule_id, feature_id)
fact(id slug PK, claim_kind, claim_ref, statement text, status,  -- accepted/challenged
     repo_path, embedding vector)         -- pgvector column
fact_source(fact_id, source_id, locator)  -- locator = page/section
source(id slug PK, csl jsonb)             -- CSL-JSON blob + generated columns
-- runtime-only (never in repo):
vote(user_id, feature_id, ...), usage_stat(feature_id, count),
submission(...), comment(...)
```

RAG endpoint (for Claude Code via MCP, per §2.2): query → pgvector similarity over
`fact.embedding` → return statement + resolved citations + repo_path (so an agent can open
a PR against the exact file). This keeps constraint §2.3 satisfied: sources are plain
rows, only fact statements are embedded.

## Open questions for the owner

1. **Characteristic vs Quality**: the brief lists quality axes (performance, learnability,
   …) and separately defines "characteristic" as an observable property. Is a
   characteristic meant to be *evidence* for quality edges (measurements), or a distinct
   user-facing thing? This decides whether Characteristic is a real entity in the MVP or
   deferred.
2. **Language versioning**: does a FeatureInstance need version scoping (Python 2 vs 3;
   "since C++11") beyond a simple `since` field? Full version-range modeling is a big
   complexity step.
3. **Influences weight**: is polarity (+/−) enough, or do you want a magnitude
   (weak/strong) — e.g. "ADTs *strongly* encourage pattern matching"? Affects builder UX.
4. **Repo visibility and write path for agents**: are developer-managed agents allowed to
   merge their own fact PRs after automated checks, or is every merge human-reviewed?
   (§2.4 vs §2.5 tension.)
5. **Is the vector store agent-only** (per §2.6 "the site is for human eyes"), or should
   site search also use it? Affects whether embeddings need to be good, or just adequate.
6. **Layer-3 dimensions**: is the brief's list of design-choice dimensions closed (curated
   by you) while community contributions can only add layer-2 features and instances? A
   closed dimension set makes the builder and validator far more stable.

## New brainstorm topics surfaced

- **Facts-repo build pipeline & CI**: schema validation, slug/ID stability, dangling-edge
  detection, embedding generation on merge, deploy of compiled DB — this is its own
  workflow design, distinct from both the knowledge model and the agent debate loop.
- **Contribution ergonomics for the YAML layer**: templates, a web-based "propose a fact"
  form that generates a PR, and how GitHub Discussions map onto entity pages — sits
  between the knowledge model and the website but is owned by neither.
