# 38 — Questionnaire Compiler

> Backlog brainstorm for LangAtlas. Topic: deriving the D5 sweep questionnaire from the
> ontology's fact-bearing field map so schema and sweep can't drift; the ontology→sweep
> handoff contract. Binding context: D5 (multi-agent workflow — independent per-language
> questionnaire sweeps, source-first; a reconciler diffs answers; only conflicted cells
> trigger structured debates); D11 (frontloaded research phase, separate from the
> per-language sweep pipeline retained for onboarding new languages later); D16 (ontology
> versioning — immutable node `id` vs renameable `slug`, blast-radius semver, migrations
> as idempotent scripts, the graduated 0.x ceremony); D23/topic 09 (concrete v0 YAML
> schemas for feature/concept/feature-instance/edge/rule/source, per-field `sources:`
> lists, the two-part fact-identity scheme — anchor `(record-id)#(field-path)` + content-
> keyed `f-<12hex>` fact id, canonical claim phrasing as fixed per-kind templates over node
> ids); D27/topic 25 (R0–R6 research-phase staging; R6 names this topic explicitly as owning
> the "questionnaire compiler deriving the D5 sweep questionnaire from the ontology's
> fact-bearing field map," and flags topic 09 as an R0 prerequisite this topic inherits);
> D28 (initial language selection & the four-phase onboarding schedule the compiler's
> output serves); D30/topic 16 (sweep-pipeline fact debates deferred to phase-1
> onboarding — this compiler's output is the artifact those debates eventually run
> against); D38/topic 29 (ontology change tooling — the blast-radius script, migration-
> manifest disposition DSL, and tombstone/redirect machinery a live questionnaire must not
> silently outrun); D39/topic 30 (the `exclusivity: exclusive | multi` dimension field the
> compiler must read to know whether a dimension's questionnaire items are one-of or
> any-of). All proposals below are *proposed*, not ratified, per the project's
> decision-hygiene convention.

## Problem framing

D5 settled the sweep pipeline's shape: an agent independently answers a fixed
questionnaire for one language, a reconciler diffs answers across languages, and only
conflicted cells trigger a structured debate. D27's R6 named the open gap plainly:
*something* has to turn "the ontology" into "the questionnaire," and that something must
be a **compiler** — a deterministic build step — rather than a document someone edits by
hand, because a hand-maintained questionnaire and an evolving ontology are two independent
sources of truth that will diverge the moment either one changes without the developer
remembering to touch the other.

This brainstorm has to make that concrete in four ways:

1. **What counts as "fact-bearing"** in D23's v0 schemas — which fields of a
   FeatureInstance/Edge/Rule record actually require a sweep agent to go find and cite
   evidence, versus which are structural (derived, defaulted, or simply not askable of a
   sweep agent because they're ontology-authored, not language-authored).
2. **The compiler as an artifact** — a real code tool with defined inputs (the ontology
   YAML tree), a defined output (a questionnaire spec, itself a versioned artifact), and a
   defined algorithm for turning `layer`/`dimension`/`exclusivity` structure into
   questionnaire items.
3. **The handoff contract** — what's actually versioned and hand over the wall between the
   research phase (which owns the ontology) and the sweep pipeline (which consumes the
   questionnaire), and what happens to in-flight sweep answers when the ontology changes
   under them mid-sweep or between onboarding phases.
4. **Where compilation sits operationally** — one-shot batch run at R6/sweep-launch, or a
   live/incremental process that has to keep re-running as D28's later onboarding phases
   proceed against an ontology that (per D16) can still take MINOR/PATCH changes, and
   occasionally MAJORs, after `1.0.0`.

### Worked example: what compiles out of one dimension feature

Take a single layer-3 feature the research phase might mint during R4: `memory-management`
as a **dimension** (`ontology/taxonomy/dimensions.yaml`, `exclusivity: exclusive`, per
D39's default) with candidate feature members `garbage-collection`,
`manual-memory-management`, `ownership-borrowing`, `reference-counting`. Assume the ontology
also carries one requires-edge (`ownership-borrowing` → `move-semantics`) and one
`affects-quality` edge (`ownership-borrowing` → `learnability`, per D23's consolidated
signed edge type) with an `assessments:` list already seeded by the research phase's own
quality-panel role (per D23's O7 worked example — quality assessments are *not*
per-language; they're feature-level judgments, orthogonal to the sweep).

When a new language — say Zig, a hypothetical phase-3/4 addition — reaches the sweep
pipeline, the compiler must have already turned `memory-management`'s four candidate
features into **exactly these compiled items**, and no others:

| Compiled item | Source field (D23 anchor shape) | Kind |
|---|---|---|
| "Does Zig implement garbage collection?" (+ since, if present) | `fi.zig.garbage-collection#exists`, `#since` | per-feature existence + since |
| "Does Zig implement manual memory management?" | `fi.zig.manual-memory-management#exists`, `#since` | per-feature existence + since |
| "Does Zig implement ownership/borrowing?" | `fi.zig.ownership-borrowing#exists`, `#since` | per-feature existence + since |
| "Does Zig implement reference counting?" | `fi.zig.reference-counting#exists`, `#since` | per-feature existence + since |
| (grouped) "Which of the above, if any, characterize Zig's memory-management approach, and are they mutually exclusive in practice?" | derived from `dimensions.yaml#memory-management.exclusivity` | **dimension-level guidance annotation**, not a fact-bearing field itself |
| "What characteristics of Zig's memory-management feature(s) are notable (free-text, cited)?" per present feature | `fi.zig.<feature>#characteristics[*]` | open per-feature characteristic slots (agent proposes keys) |
| "Provide a syntax example for each present feature" | `fi.zig.<feature>#syntax[*]` | open per-feature syntax slots |
| "Does Zig's `ownership-borrowing` (if present) require `move-semantics` (per the ontology's edge)?" | `edge.requires.ownership-borrowing.move-semantics` — **existence is ontology-authored, not language-authored** | **not a sweep item** — see below |

The last row is the crux of "fact-bearing vs. structural." The edge `requires.
ownership-borrowing.move-semantics` is a *feature↔feature* fact, sourced once during the
research phase (R3/R4) against the general literature — it says nothing about Zig
specifically and is true or false independent of which languages exist. It is **not**
re-asked per language. What a sweep agent *is* asked, if Zig's instance record answers
`present` for `ownership-borrowing`, is a validation obligation the compiler encodes as a
constraint check rather than a question: "the ontology says `ownership-borrowing` requires
`move-semantics` — if you mark `ownership-borrowing: present`, you must also produce a
`fi.zig.move-semantics` record or flag the combination as a contradiction for the
reconciler." This is D2's level-1/2 combination-validation machinery (dimension
exclusivity + hard requires/conflicts), executed by the compiler as a **cross-item
constraint** attached to the questionnaire, not rendered as an item of its own.

Similarly, the `affects-quality` edge and its `assessments:` list are never sweep
questions — no sweep agent is asked "does ownership hurt learnability in Zig?" That
judgment lives at the feature level (produced by the research-phase quality-panel role,
D23 O7), is not per-instance, and the compiler's job there is exactly zero: it emits
nothing into the questionnaire for quality edges. (A future *language-specific* nuance on
a quality edge — "learnability is worse in Zig than in Rust because X" — would need a new
schema affordance before it could even be asked; out of scope here, flagged below.)

Rules (`rules/rule-*.yaml`, `when_all` conjunctive antecedents over feature ids) are the
other structural case: a rule's *existence and message* is minted once by the research
phase, sourced generically, and never re-asked per language. What the compiler *does*
derive from a rule is another cross-item constraint: if `rule-laziness-needs-purity` says
`when_all: [laziness, purity]` `effect: forbids` `then: unrestricted-mutation`, and a sweep
agent marks a language `present` on both `laziness` and `unrestricted-mutation`, that's a
contradiction the reconciler needs surfaced (potentially against the rule itself, not the
sweep answer — see "handoff" below).

**So the fact-bearing/structural line, stated generally:**

- **Fact-bearing (compiles to a sweep item):** every field on a *FeatureInstance* record
  that D23 lists as carrying its own `sources:` — `status` (`present|absent|partial`,
  with its `notes` for `partial`), `since`, each `characteristics[*]` entry, each
  `syntax[*]` entry. These are the only places a sweep agent's own source-first research
  produces a claim.
- **Structural (never a sweep item, but may compile to a cross-item *constraint*):**
  everything ontology-authored — feature/concept/dimension/edge/rule existence, edge
  polarity, edge `assessments:`, dimension `exclusivity`, `layer`, `cross_cutting`. These
  are already sourced once, generically, by the research phase; asking a sweep agent to
  re-derive or re-source them would be redundant work and a schema-integrity risk (two
  independently-sourced "facts" about the same node, one per-language, one general, that
  could drift apart with no mechanism to reconcile them).
- **Structural, and not even a constraint:** `slug`, `id`, `realizes`, `summary` — pure
  ontology metadata with no per-language dimension at all.

## Options with trade-offs

### O1 — Is the compiler a real code tool, and what does it read/emit?

**O1a — A prompt template, hand-assembled per sweep by whoever launches it.** Cheapest to
build (nothing to build), but this *is* the drift failure mode the checklist item exists
to prevent: a human (or an agent following loose instructions) re-derives "what to ask"
from memory of the ontology each time a sweep launches, and the two sources of truth
silently diverge the first time a dimension gets renamed or a feature gets split. Reject
outright — this is precisely what D27's R6 flagged as needing a *compiler*, not a
convention.

**O1b — A deterministic Python tool, `tools/questionnaire/compile.py`, reading the
ontology tree exactly as CI/the D13 validators already do, emitting a versioned
questionnaire spec file.** Inputs: `ontology/taxonomy/{layers,dimensions,edge-types,
qualities}.yaml`, every `features/<id>.yaml`, every `concepts/<id>.yaml` (concepts are
never swept directly, but a feature's `realizes` link is descriptive context an agent may
want), every `edges/**/*.yaml`, every `rules/*.yaml`, and `ontology/VERSION`. Output: one
`questionnaire/<language-id>/spec-<ontology_version>.yaml` (or, per O2 below, a
language-agnostic spec the sweep launcher instantiates per language) — a build artifact,
never hand-edited, matching D23's "facts are pure build artifacts" precedent for the
`facts/` directory that doesn't exist. This is the recommended shape: it reuses the
project's existing "schema in, validated deterministic artifact out" pattern (the fact
table itself, D26's dataset bundle, D38's blast-radius script) rather than inventing a
new one, and it means the compiler can run as an ordinary CI-adjacent step, testable with
fixture ontologies the way D26 already tests the provider wrapper via record/replay.

**O1c — Fold compilation into the sweep-agent's own runtime prompt (the agent reads the
ontology live and figures out its own questionnaire at sweep time).** Removes a build
step, but reintroduces exactly the risk O1a has — now every sweep session re-derives
"what's fact-bearing" from a system prompt's interpretation of the schema, with no single
point where a schema change is guaranteed to be reflected consistently across every
concurrent sweep session (D1's no-PR-gate world has multiple agent runs in flight). It
also makes the "did the questionnaire ever silently drift from the schema" question
unanswerable after the fact — there's no artifact to diff. Reject: the whole point of
"compiler" in the checklist's own phrasing is a build step with an inspectable output.

**Recommendation: O1b.** A small, testable, CI-adjacent Python tool — not a service, not a
daemon, matching the project's "boring, solo-maintainable technology" posture (same shape
as D38's blast-radius script and D41's `report.py`).

### O2 — Questionnaire schema: per-item flat list vs. per-dimension grouped vs. per-feature nested

**O2a — Flat list, one item per fact-bearing (feature, field) pair.** Simplest to generate
mechanically (literally: walk every feature, walk its fact-bearing fields, emit one item
each) and simplest for a sweep agent to iterate — a todo list, essentially. But it throws
away the dimension/layer structure that the worked example above shows genuinely matters
(exclusivity guidance, grouped "what's your language's story on X" framing that helps an
agent give a coherent answer rather than four independent yes/no's that might individually
look fine but jointly violate exclusivity). A flat list also can't easily attach
cross-item constraints (the requires/rules checks above need to know which items belong
to which feature/dimension to validate against).

**O2b — Per-dimension grouped items, flat items for layer-1/2 features outside any
dimension.** Every layer-3 dimension compiles to one **item group**: a short shared
preamble (dimension name, `exclusivity`, the candidate features and their one-line
`summary` text as context) followed by the per-feature existence/since/characteristics/
syntax sub-items from O1's fact-bearing list. Layer-1 (syntax) and layer-2 (semantic)
features, which by D2's model don't belong to a dimension, compile to standalone flat
items (each still fact-bearing on the same field set). This is the recommended shape: it
lets the compiler attach the `exclusivity` constraint once per group (rather than
re-deriving it per item), gives the sweep agent enough context to reason about a coherent
answer across a dimension's features in one pass (better than four cold, isolated
existence questions), and maps naturally onto D5's actual working unit — "sweep" already
means "answer everything for one language in one session," and grouping by dimension is
the natural sub-batching inside that session.

**O2c — Per-feature nested (every feature is its own object carrying all its fact-bearing
sub-fields, dimension membership as just one more attribute, no separate grouping
construct).** Structurally simpler than O2b (no group-vs-item distinction in the schema),
and it's what the D23 FeatureInstance record shape itself already looks like — so O2c's
argument is "the questionnaire item shape should mirror the record shape it's populating,
one-to-one." Reasonable, but it pushes the exclusivity-guidance and grouped-framing
benefits of O2b into agent-prompt convention rather than schema structure — the compiler
would still need to compute "which features share a dimension" and thread that into the
per-feature item's own metadata (a `dimension_context` field referencing sibling items),
which is most of O2b's complexity without the readability win of an explicit group
object.

**Recommendation: O2b.** Concrete schema sketch:

```yaml
# questionnaire/spec-0.7.0.yaml  (language-agnostic; instantiated per language at sweep launch)
ontology_version: "0.7.0"
compiled_at: 2026-08-02T00:00:00Z
compiler_version: "1.2.0"          # the compile.py tool's own version, O1b
groups:
  - kind: dimension
    dimension: memory-management
    exclusivity: exclusive
    context: >-
      Candidate memory-management approaches recognized by the ontology; per
      the ontology's exclusivity setting, a language should not present as
      unambiguously combining mutually exclusive strategies without an
      explanatory characteristic.
    items:
      - feature: garbage-collection
        anchor_prefix: "fi.<lang>.garbage-collection"
        fields: [exists, since, characteristics, syntax]
        feature_summary: "Automatic reclamation of unreachable memory..."
      - feature: manual-memory-management
        anchor_prefix: "fi.<lang>.manual-memory-management"
        fields: [exists, since, characteristics, syntax]
      - feature: ownership-borrowing
        anchor_prefix: "fi.<lang>.ownership-borrowing"
        fields: [exists, since, characteristics, syntax]
      - feature: reference-counting
        anchor_prefix: "fi.<lang>.reference-counting"
        fields: [exists, since, characteristics, syntax]
  - kind: standalone
    feature: pattern-matching
    layer: 2
    anchor_prefix: "fi.<lang>.pattern-matching"
    fields: [exists, since, characteristics, syntax]
constraints:
  - kind: requires
    if_present: ownership-borrowing
    then_present: move-semantics
    source_edge: edge.requires.ownership-borrowing.move-semantics
  - kind: rule
    rule_id: rule-laziness-needs-purity
    when_all: [laziness, purity]
    effect: forbids
    then: unrestricted-mutation
```

Each `items[*]` entry carries `fields: [exists, since, characteristics, syntax]` rather
than spelling out full per-field guidance text inline — the sweep-agent prompt template
(a separate, hand-authored artifact, not compiled) supplies the generic "how to answer an
`exists`/`since`/`characteristics`/`syntax` item" instructions once, and the compiled spec
supplies only *which* items exist and their ontology context. This split matters for O2
because it keeps the compiler's output purely mechanical (facts about the ontology's
shape) and keeps the "how should an agent phrase a good sweep answer" judgment where D6's
tiering already puts high-judgment work — a Claude-authored, versioned prompt template
(D41's prompt registry), not baked into generated YAML.

`status: absent` and "no file / not yet swept" stay distinct per D23 — the compiler emits
an item for every candidate feature regardless of expected presence; the sweep agent's
answer of `absent` (with sources, per D23's "absence is a fact too") is a legitimate
first-class answer, not a skip.

### O3 — Handling layer-1/2/3 distinctions, exclusivity, and rules concretely

Already substantially covered by the worked example and O2b's schema, but the compiler
algorithm needs to be stated precisely since it's the actual "so schema and sweep can't
drift" mechanism:

1. Walk `features/*.yaml`. For each feature with `status` implied absent from the
   ontology itself (features are never "absent" at the ontology level — only instances
   are), record `(id, layer, dimension, summary)`.
2. Group by `dimension` where non-null; features with `dimension: null` become standalone
   items. Attach each dimension group's `exclusivity` from `taxonomy/dimensions.yaml`
   (D39) directly — no inference, no duplicated logic, single source of truth.
3. For every feature, emit the fixed field list `[exists, since, characteristics, syntax]`
   — this is *not* configurable per feature; D23's schema makes every FeatureInstance
   record carry the same shape regardless of layer, so the compiler doesn't need
   layer-specific item logic beyond the dimension grouping already handled in step 2.
   (Layer only affects *grouping*, never *field selection* — worth stating explicitly
   since it's a natural place to over-engineer.)
4. Walk `edges/**/*.yaml` where `type in {requires, conflicts-with}` (the D2 hard-pairwise
   validation levels) and both endpoints are features (not quality edges — those never
   compile to constraints, per the worked example). Emit one `constraints[].kind: requires`
   or `kind: conflicts` entry per edge, referencing the edge's own `id` so a later
   constraint violation can cite back to the exact sourced edge record that justifies it.
5. Walk `rules/*.yaml`. Emit one `constraints[].kind: rule` entry per rule, carrying
   `when_all`/`effect`/`then` verbatim (rules are already a closed, compiler-friendly
   shape per D23's v0 schema — `when_all` conjunctive only in v0, matching the schema's
   own "additive when a real rule needs `when_any`/`unless`" note).
6. `influences` (soft, polarity-only) edges and `affects-quality` edges are read for
   descriptive context text only (folded into a feature's `feature_summary`/notes if
   useful for framing) — never emitted as constraints, since D2 already scopes soft
   influences as warnings, not sweep-checkable hard rules, and quality edges are feature-
   level judgments with no per-language dimension at all (§ above).

This is deliberately mechanical — no judgment calls inside `compile.py` beyond "read the
schema, apply the fixed field list, group by dimension, emit constraints for the two hard
edge types and rules." That's what makes it a compiler rather than a design activity: any
two runs against the same `ontology_version` commit produce byte-identical output (modulo
the `compiled_at` timestamp), which is the property the drift-prevention argument (O4
below) actually depends on.

### O4 — Drift prevention: naming the failure mode and how compilation structurally blocks it

**The concrete failure mode**, stated precisely: during R3/R4's per-theme iteration
(D27), a theme's dimension gets restructured — say `memory-management` splits into two
dimensions (`memory-reclamation-strategy` and `ownership-model`) because R5's reality
checks against the topic-34 language set found languages that don't cleanly fit the
original four-way split (e.g. a language with both GC *and* an ownership-adjacent borrow
checker for a subset of types). Under a hand-maintained questionnaire (O1a), the person
who made that ontology change would have to remember to separately go edit a
questionnaire document, in a different location, days or weeks before any sweep actually
runs against it — a step with no CI check, no build failure, and no natural trigger. If
they forget (easy, since the ontology-editing session and the "hey let's onboard Zig"
session could be months apart per D28's phased schedule), the sweep pipeline asks about a
dimension shape that no longer exists in the ontology, producing FeatureInstance records
whose `feature:` fields don't resolve against `features/*.yaml` — caught eventually by
D13's referential-integrity validators, but only *after* an agent has already spent a
sweep session's worth of Claude messages producing now-worthless output, and the reconciler
has nothing sensible to diff.

**How O1b (compile as a build step) structurally prevents this, not just discourages it:**
the questionnaire is never a second document that can fall out of sync — it is *always*
regenerated from the current `ontology/` tree immediately before a sweep launches (or, per
O5 below, pinned to a specific `ontology_version` at launch time and regenerated fresh for
the next language). There is no state to forget to update, because there is no
independently-editable questionnaire state at all — only a cached, versioned *output* of a
pure function over the ontology tree. This is the same structural argument D23 already
made for facts themselves ("facts are never authored as files... the fact table is a
build artifact") and D26 made for the dataset bundle ("facts are computed once in the
build pipeline and shipped as data, never re-derived independently by each consumer") —
this topic is the same pattern applied one layer up the pipeline, turning "ontology
structure" into "sweep questions" instead of "record fields" into "derived facts."

A second, subtler drift mode this also blocks: **schema/sweep vocabulary drift**, where a
schema field gets renamed or a new fact-bearing field is added to D23's FeatureInstance
schema itself (not the ontology content, the *schema* — e.g. a future `custom.notes`
field) but the questionnaire's hand-written item templates never learn about it. Because
O1b's field list (`[exists, since, characteristics, syntax]`, step 3 above) is itself
read from — or at minimum tested against — the same JSON Schema files D23 already commits
to `ontology/schema/`, a schema change that adds/removes a fact-bearing field is a natural
place to add a regression fixture (mirroring D26/D30's record/replay fixture pattern) that
fails if `compile.py`'s field list and the schema disagree, rather than trusting a human to
notice.

### O5 — The ontology→sweep handoff contract

What's actually handed off, concretely, at the R6→sweep-launch boundary and at every later
onboarding-phase boundary (D28):

**O5a — A single global "the" questionnaire, implicitly always current.** The sweep
pipeline always compiles fresh against whatever `ontology/VERSION` currently is, with no
pinning. Simplest mental model, but breaks D28's "later onboarding phases are gated on
completing earlier phases' sweeps — they do not interleave" rule in a subtle way: if
ontology work continues between phase 1 and phase 2 (plausible — MINOR/PATCH churn doesn't
stop just because a sweep phase is running), a phase-1 language's sweep and a phase-2
language's sweep could be answering *different* questionnaires without that being visible
anywhere, making the reconciler's cross-language diff silently apples-to-oranges for any
feature that changed shape between the two compilations.

**O5b (recommended) — Every compiled questionnaire is stamped with the exact
`ontology_version` (and, per O1b's spec schema, `compiler_version`) it was compiled
against, and every sweep run's manifest (the same `manifest.yaml` D18 already requires
per run) records which questionnaire version it answered.** This is the direct analogue
of D26's dataset-bundle version stamping and D35's `ontology_version` provenance field —
the project already has this exact pattern for "a derived artifact needs to declare which
source-of-truth snapshot it was built from," so this topic adopts it rather than inventing
a parallel scheme. Concretely, the handoff artifact set at R6/sweep-launch is:

1. **The compiled questionnaire spec** itself (O1b/O2b), one file (or one per language, if
   language-specific candidate-feature filtering ever becomes real — v0 keeps it
   language-agnostic per O2's sketch, since nothing in D23's schema is language-specific
   at the ontology level).
2. **A `questionnaire_version` = the `ontology_version` it was compiled from** — *not* an
   independent semver of its own in v0, since the questionnaire has no content beyond what
   the ontology already versions; a separate `questionnaire_schema_version` (mirroring
   D35's `bundle_schema_version`) would only be needed if the *compiled-output shape*
   itself changes independent of ontology content (e.g. O2's grouping algorithm changes)
   — flagged as a v1 concern, not designed now, since the compiler tool doesn't exist yet
   to have a version-compatibility history worth managing.
3. **The constraint list** (O3 step 4/5) bundled in the same spec file, so validation
   logic travels with the questionnaire rather than needing a separate ontology fetch at
   sweep-answer-validation time.

**In-flight answers when the ontology changes mid-sweep or between phases**: per D28,
sweeps are always developer-initiated by hand (never cron-driven, per D43), and later
phases don't interleave with earlier ones — so the realistic scenario is narrower than
"the ontology changes while an agent is mid-questionnaire" (a single sweep session, per
D5/brainstorm-04's batching discipline, is one bounded Claude session answering one
already-fixed compiled spec; it does not re-poll the ontology mid-session). The real
question is what happens to a **completed** sweep's answers, already landed as
FeatureInstance records under the old `questionnaire_version`, when the ontology later
takes a MAJOR (D16/D38) that reshapes the dimension the sweep answered against — e.g. the
`memory-management` split from O4's example, discovered *after* phase-1's six languages
already answered the old four-feature questionnaire.

This is not a new problem this topic needs to solve from scratch — **it is exactly D38's
migration-manifest disposition DSL, applied to FeatureInstance records instead of the
edges/rules D38 designed it for.** A dimension split is a `split`-kind migration under
D16's casebook; D38's blast-radius script already computes "direct/indirect fact
references" for any ontology-node kind, and its `fact_remap` list with the four-action
vocabulary (`remap | requeue | tombstone | untouched`) already has a disposition for
exactly this case: per-instance, the split's casebook default is "per-fact disposition
(remap + cheap re-verify vs requeue)" (D16's own wording). So: a completed sweep answer
whose feature got split needs **requeuing** — not a full re-sweep of the whole
questionnaire, just a targeted re-ask of the narrower set of items the split produced,
scoped by the existing migration manifest's `fact_remap` matcher, landing as an ordinary
D36-protocol commit against the already-existing FeatureInstance record file. The
questionnaire compiler's only new obligation here is that **a migration affecting a
dimension/feature the compiler has ever emitted items for must be able to produce a
"delta questionnaire"** — re-running `compile.py` against the post-migration ontology and
diffing its output against the pre-migration spec (by `anchor_prefix`) yields exactly the
set of items that are new/changed/removed, which is the requeue candidate list D38's
`fact_remap` needs. This delta-diff is a small addition to `compile.py` (diff two spec
files by anchor), not new machinery — flagged as an explicit deliverable in the
Recommendation below rather than left implicit.

### O6 — Where compilation sits operationally: one-shot vs continuous

**O6a — Continuous/live**, re-compiling on every ontology commit and keeping a running
"current questionnaire" the sweep pipeline always reads fresh. Matches how D13's CI
already validates every commit, but produces churn with no consumer for most of the
project's life: MINOR/PATCH ontology edits happen constantly during R3/R4 (D27), while no
sweep is running at all (per D28, sweeps only start after `1.0.0`, and even then run in
phases gated by developer initiation). Compiling on every commit optimizes for a read
pattern (sweep launch) that happens rarely, at the cost of running (harmlessly, but
pointlessly) on every commit that happens often.

**O6b (recommended) — On-demand, invoked explicitly at two trigger points: (1) R6/first
sweep launch, producing the v1.0.0 questionnaire; (2) at the start of every subsequent
D28 onboarding phase, and additionally whenever D38's migration tooling flags a migration
that touches any node the last-compiled spec referenced (the delta-questionnaire case,
O5).** This mirrors D43's orchestrator philosophy directly: "no daemon... a thin driver
library," jobs triggered by an explicit batch-spec invocation, not a live service —
`compile.py` is exactly the shape of tool D43's `tools/orchestrator/driver.py` already
expects to shell out to (a `kind: questionnaire-compile` job entry in `config/jobs/`,
enumerating "compile fresh, diff against last-compiled spec, report the delta" as its one
unit of work, run by hand before each onboarding phase per D28's "always
developer-initiated by hand" sweep-launch rule — never via cron, matching D5's own sweep
launches). No new infrastructure: it's one more subcommand alongside D41's `report.py`
and D38's blast-radius script, all cut from the same "small Python CLI, no daemon, no
new service" cloth this project has used for every comparable tool so far.

## Recommendation

*Proposed* package:

1. **The fact-bearing/structural line (worked example, §Problem framing):** the compiler
   emits sweep items only for the four D23 FeatureInstance fields —
   `exists`/`since`/`characteristics`/`syntax` — and never for anything ontology-authored
   (feature/edge/rule existence, edge polarity, `affects-quality` assessments, dimension
   `exclusivity`, `layer`, `cross_cutting`). Ontology-authored facts that *constrain*
   per-language answers (hard `requires`/`conflicts-with` edges, `rules/*.yaml`) compile
   to a separate `constraints:` list the reconciler validates sweep answers against,
   never to sweep questions themselves.
2. **A real code tool (O1b): `tools/questionnaire/compile.py`.** Deterministic, pure
   function of the `ontology/` tree at a given commit → a versioned spec file; no prompt-
   template guessing (O1a) and no live per-sweep re-derivation (O1c).
3. **Schema (O2b): per-dimension grouped items** (dimension context + `exclusivity` once
   per group) **plus standalone flat items** for layer-1/2 features outside any dimension;
   every item carries the fixed four-field list and an `anchor_prefix` matching D23's
   `fi.<lang>.<feature>` anchor scheme so compiled items and derived facts share
   vocabulary by construction. Concrete YAML shape given above.
4. **Algorithm (O3):** mechanical, six deterministic steps over `features/`,
   `taxonomy/dimensions.yaml`, `edges/**`, `rules/*.yaml` — no judgment calls inside the
   compiler itself, which is what makes "compiled" a meaningful guarantee rather than a
   label.
5. **Drift prevention (O4)** is structural, not procedural: the questionnaire is never an
   independently-editable artifact, so there is no state that can fall out of sync by
   omission — matching D23's "facts are build artifacts" and D26's "computed once, shipped
   as data" precedents, applied one layer up. A schema-shape regression fixture (shared
   pattern with D26/D30) catches the rarer schema-vocabulary-drift mode.
6. **Handoff contract (O5b):** every compiled spec is stamped with the `ontology_version`
   it was compiled from (no independent questionnaire semver in v0); every sweep-run
   manifest records which spec version it answered, mirroring D26/D35's existing
   version-provenance pattern. In-flight-answer disposition after a later ontology
   migration is **D38's existing migration-manifest disposition DSL**, applied to
   FeatureInstance records — this topic's only new deliverable is a **delta-questionnaire
   diff** (`compile.py`, diff two spec versions by `anchor_prefix`) feeding D38's
   `fact_remap` requeue list, not a parallel re-sourcing mechanism.
7. **Operational placement (O6b):** on-demand, invoked at R6/first-sweep-launch and at the
   start of each subsequent D28 onboarding phase (plus ad hoc whenever a migration
   touches previously-compiled nodes), as one more `config/jobs/` entry for D43's driver —
   never a live/continuous service, and never cron-triggered (sweep launches, like the
   compilation that precedes them, stay developer-initiated by hand per D43's existing
   ratification).

## Open questions for the developer

1. **Language-agnostic vs. per-language spec filtering** — v0 as designed compiles one
   questionnaire spec covering every candidate feature regardless of which language will
   answer it (O2b). Is there value in ever filtering candidate features per language up
   front (e.g. skip asking a garbage-collected-only language about
   manual-memory-management items) — or does that risk the compiler making judgment calls
   about a language before any evidence exists, which contradicts the "absence is a
   sourced fact, not a skip" principle (D23) the schema already commits to?
2. **Constraint violations: who resolves them?** O3's `constraints:` list gives the
   reconciler a mechanical way to detect a sweep answer that violates a `requires`/
   `conflicts-with` edge or a rule. Should a detected violation route into the existing
   D5 conflicted-cell debate machinery unchanged (treating "sweep answer contradicts an
   ontology-level constraint" the same as "two languages' sweep answers disagree"), or
   does it need its own resolution path (e.g. auto-flagging the *ontology* edge/rule as
   possibly wrong, since a sweep agent's fresh source-first evidence about a real language
   contradicting a general rule is itself informative)?
3. **Delta-questionnaire granularity** — when a migration produces a delta questionnaire
   (O5), should the requeue always be scoped to exactly the changed anchors (minimal
   re-ask), or should it always requeue the *whole dimension group* the change belongs to
   (safer against subtle cross-item exclusivity implications the split might have
   introduced, at the cost of re-asking items that didn't actually change)?
4. **Questionnaire-schema versioning (O5b's flagged v1 concern)** — confirm that a
   separate `questionnaire_schema_version` (independent from `ontology_version`, tracking
   changes to the *compiled-output shape* itself, e.g. O2's grouping algorithm) is
   genuinely deferrable until the compiler has shipped at least one real version, rather
   than worth stubbing in now the way D35 stubbed in `bundle_schema_version` from the
   start?
5. **Where `tools/questionnaire/compile.py` output is committed, if at all** — should the
   compiled spec be a committed artifact (visible in git history, diffable across
   ontology versions, matching the project's general "human-readable YAML in git" bias),
   or should it stay an ephemeral build output regenerated on demand and never committed
   (matching D41's `report.py` precedent of "ephemeral, never committed canonical data")?
   The delta-diff mechanism (O5) works either way, but committed history would make past
   questionnaire versions independently auditable without needing to recompile against an
   old ontology commit.

## New brainstorm topics surfaced

- **Language-specific quality-edge nuance** — the worked example notes that
  `affects-quality` assessments are feature-level, not per-instance, in the current v0
  schema (D23), so a sweep agent has no way to record "learnability is worse in Zig than
  in Rust specifically" even if that's a genuinely sourceable claim. Whether this needs a
  schema extension (a per-instance quality-nuance field) or is deliberately out of scope
  is unresolved and worth its own brainstorm if the research phase or an early sweep
  surfaces a real case.
- **Constraint-violation resolution path** — open question 2 above (route into D5's
  existing debate machinery vs. a dedicated resolution path for "sweep evidence
  contradicts an ontology-level rule") is substantive enough that, if the developer wants
  it designed rather than just decided informally, it could become its own brainstorm
  rather than being settled inline here.
- **Compiler regression-fixture design** — §O4's proposed schema-shape regression fixture
  (catching drift between D23's JSON Schema fact-bearing fields and `compile.py`'s
  hardcoded field list) is a small piece of a larger pattern (shared with D26/D30's
  record/replay fixtures and D41's regression-check gate) that could use a single unified
  treatment across all these "does the generated artifact still match its source schema"
  checks, rather than each topic inventing its own fixture convention independently.

## Sources

No new external sources introduced; all constraints trace to the input brief and
ratified decisions D1–D43, and to brainstorms 04, 09, 16, 25, 29, 30 as cited inline
above.
