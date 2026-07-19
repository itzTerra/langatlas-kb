# 30 — Cross-Cutting Concern Modeling

> Backlog brainstorm for LangAtlas. Topic: how `cross_cutting` features interact with
> combination validation once concerns like exceptions, security, and naming enter the ontology
> for real — because D2's dimension exclusivity (one of the four combination-validation levels)
> assumes layer-3 features are tree-shaped, pick-exactly-one-value-per-dimension choices, and
> exceptions/security/naming are not that shape: a language can have try/catch **and** Result
> types **and** panics all at once. Binding context: D2 (the knowledge model — layer 1/2/3
> features, layer-3's `dimension` field, and the four combination-validation levels: dimension
> exclusivity, hard pairwise requires/conflicts, soft influences warnings, Rule entities for
> multi-feature interactions; "nothing is developer-curated/closed" — the layer-3 dimension list
> and feature set are subject to change through the normal evidence + challenge process); D16
> (ontology versioning, topic 22 — ratified the `cross_cutting` schema affordance as a PATCH-cost
> placeholder added now so that exceptions/security/naming don't force a MAJOR later; O6's closing
> note that the layer-3 `Exceptions: checked/unchecked/effect-system` dimension already collides
> with the deliberately-excluded "Exceptions" Concept, and named that collision as the machinery's
> "first real test"; the split/move casebook, whose dimension-move row already anticipates
> "exclusivity semantics may have flipped" as a review-queue trigger). This is a **knowledge-model
> design question**, not an implementation task for the Builder's rules engine (topic 52, deferred
> alongside the whole Builder module per D11/CLAUDE.md) — the job here is to say what shape the
> ontology data needs so that whenever the Builder (or any other combination-validation consumer:
> the D4 verifier, a future coverage-gap report) reads it, cross-cutting features don't get
> silently mismodeled as tree-shaped choices. All proposals below are *proposed*, not ratified,
> per the project's decision-hygiene convention.

## 1. Problem framing

D2 defines four combination-validation levels: **dimension exclusivity** (a language picks
exactly one value from a layer-3 dimension — e.g. "Memory management strategy: manual |
GC-tracing | GC-refcount | ownership-borrowing" — a language is in exactly one bucket),
**hard pairwise requires/conflicts** (edge-level, package-manager-style propagation), **soft
influences warnings** (polarity-only nudges), and **Rule entities** (multi-feature emergent
interactions that don't reduce to a pairwise edge). Only the first of these — dimension
exclusivity — bakes in a *structural* assumption: that layer-3 features partition into
dimensions, and each dimension is a discrete choice set where a feature instance belongs to
exactly one value. That assumption holds for most of what layer 3 is actually for (memory
management strategy, type-system strictness, evaluation strategy — a language really does pick
one). It does not hold for exception handling, security features, or naming conventions:

- **Exceptions**: a single language can have unwind-based try/catch, algebraic Result/Option
  types, AND unrecoverable panics simultaneously (Rust has all three; Java has checked
  exceptions, unchecked exceptions, and increasingly Optional). These aren't mutually exclusive
  values of one dimension — they're independently present-or-absent mechanisms, each with its
  own requires/conflicts relationships to other features (Result types relate to sum-type
  support; checked exceptions relate to method-signature syntax) regardless of which "bucket"
  they'd naively be filed under.
- **Security**: constant-time-operations support, memory-safety guarantees, capability-based
  imports, sandboxed execution — a language accumulates these additively; there is no single
  "security dimension" a language picks one value from.
- **Naming**: a Concept per D16's O6, not even a feature yet, but the same additive shape once
  (if ever) it atomizes — case conventions, keyword-vs-identifier collision rules, module-path
  syntax don't compete with each other.

D16 already named this exact tension and pre-committed to a cheap fix: add a `cross_cutting: true`
schema affordance now (PATCH cost) so that when these concepts atomize into features later, they
aren't forced into single-dimension exclusivity. But D16 stopped at "add the marker" — it didn't
specify what the marker *does* to the validation semantics, i.e. what a `cross_cutting: true`
feature's relationship to `dimension` actually is, and whether dimension exclusivity itself needs
a second mode or whether a marker is enough. That's this topic's job. Two sub-problems follow
directly from D16's own text:

1. **The Exceptions collision** (O6 point 4): the layer-3 ontology already lists an `Exceptions:
   checked/unchecked/effect-system` dimension (an example value list from the original brief),
   while "Exceptions" is simultaneously named as a deliberately-excluded, non-tree-shaped Concept.
   Those two can't both be right in their current form — either the dimension's value list is
   wrong (it's actually additive, not exclusive), or "Exceptions" the Concept and "Exceptions
   handling mechanism" the dimension are two different, non-colliding things that happen to share
   a name. This brainstorm has to resolve that collision concretely, not just flag it again.
2. **What "any subset" does to the other three validation levels.** If dimension exclusivity
   grows a non-exclusive mode, do hard requires/conflicts, soft influences, and Rules need any
   change to keep working across cross-cutting features, or was the assumption baked only into
   the exclusivity level in the first place (in which case the other three already "just work"
   because they're pairwise/multi-feature machinery that never assumed tree shape to begin with)?

## 2. Options with trade-offs

### 2.1 What shape fits a cross-cutting feature

**Option A — Cross-cutting stays a pure flag; the feature still lives in exactly one dimension,
just a dimension whose exclusivity is loosened.** `cross_cutting: true` is metadata only (drives
site badging, RFC triage, maybe a "these don't compete" tooltip) and does no validation work
itself. The actual fix is entirely at the dimension level (see 2.2): a dimension gains an
`exclusivity: exclusive | multi` field, and cross-cutting features simply live in `multi`
dimensions. Pro: one field to reason about, no new relationship type, `cross_cutting` keeps the
narrow "staging marker" meaning D16 already gave it. Con: still assumes each feature has exactly
one home dimension — doesn't handle a feature that is legitimately part of two *different*
concerns (e.g. a security-relevant naming rule) without inventing a dimension for every
combination.

**Option B — Cross-cutting features carry a multi-valued dimension-membership list instead of a
single `dimension` field**, i.e. a feature can be tagged into N dimensions it doesn't need to
dominate/exclude within. This is what D16's O6 point 3 floated as the alternative phrasing
("features allowed to carry edges into many dimensions"). Pro: handles a feature that
legitimately straddles two concerns (Result-type-as-exception-mechanism also arguably touches the
type-system dimension) without forcing a choice of primary home. Con: bigger schema change
(`dimension: str` → `dimensions: [str]` is not additive-compatible at the field level, and every
existing tree-shaped layer-3 feature would need to migrate its single value into a one-element
list purely for schema uniformity — churn disproportionate to the actual problem, since the vast
majority of layer-3 features are genuinely single-dimension).

**Option C — Introduce a distinct `dimension_kind: choice | tag` on the dimension itself (not the
feature), with `choice` = today's exclusive pick-one-value dimension and `tag` = a dimension that
is really just a labeled bucket of independently-present features.** Functionally close to Option
A's `exclusivity` field but reframes the semantics: a `tag`-kind dimension isn't "a dimension with
loose exclusivity," it's a *different kind of grouping entity* — closer to a Concept-adjacent
umbrella than a partition. This matters because a `tag` dimension's "values" aren't mutually
exclusive alternatives a language picks between, they're just the set of features that happen to
share the label; nothing in the schema should imply competition between them. Pro: names the
distinction honestly rather than bolting a boolean onto the tree-shaped machinery and hoping
downstream consumers remember to check it. Con: two names for what is, mechanically, the same
one-bit field as Option A (`exclusivity: exclusive|multi` vs `dimension_kind: choice|tag`) — the
extra vocabulary needs to earn its keep or it's just bikeshedding a field name.

**Recommendation for this sub-problem: Option A/C merged** — keep `cross_cutting: true` on the
*feature* exactly as D16 ratified it (unchanged, zero new churn, still PATCH-cost), and add one
new field on the *dimension* record: `exclusivity: exclusive | multi` (Option A's mechanism,
Option C's honesty about what `multi` means — a `multi` dimension is a tag bucket, not a
partition, and the field comment in `dimensions.yaml` should say so explicitly rather than
leaving `multi` to be inferred). This is additive to `dimensions.yaml` (default `exclusive` for
every dimension that doesn't specify — the existing tree-shaped dimensions need zero edits) and
keeps `cross_cutting` on features as informational metadata that should, by construction, always
agree with its dimension's `exclusivity: multi` (a lint rule, not new schema). Option B's
straddle case (a feature genuinely touching two unrelated concerns) is handled the cheap way
instead: **that's what `influences`/`requires` edges are for** — a feature lives in one home
dimension and reaches into other concerns via ordinary edges, not via a second dimension
membership. Multi-dimension membership is deferred until a concrete case actually needs it (none
has surfaced yet — see §5).

### 2.2 Does dimension exclusivity itself need to change

Given 2.1's recommendation, the change to D2's dimension-exclusivity validation level is small
and precisely scoped: the validator reads `dimensions.yaml`, and for each dimension checks
`exclusivity`. If `exclusive` (the default, unchanged behavior): a feature instance may hold at
most one feature from that dimension — today's rule, verbatim, zero regression risk for the
dimensions that already work fine as trees (memory management strategy, evaluation strategy,
type-system strictness, and most of the rest of layer 3 probably stay `exclusive` forever). If
`multi`: the exclusivity check is skipped entirely for that dimension — any subset of its
features may co-occur, full stop. There is deliberately no partial mode ("at most 2 of 4",
"exactly 2 of N") — if a concern turns out to need a genuinely more constrained co-occurrence
rule than "totally free" (e.g. "you can't have both `unchecked-only` and `effect-system` as your
*primary* exception idiom, but you can have secondary mechanisms") that constraint is exactly
what **Rule entities** already exist for (2.3) — dimension exclusivity itself should stay binary
(one-of vs any-of) and push anything more nuanced down to the Rule layer rather than growing a
constraint mini-language of its own.

**Alternative considered and rejected: retire dimension exclusivity as a validation level
entirely, folding all "pick one" enforcement into Rule entities too.** Rejected — the vast
majority of layer-3 dimensions really are simple partitions, and a cheap, structural, no-agent-
judgment-needed check (derived straight from `dimensions.yaml`, no Rule authoring required) is
worth keeping as the default for the common case. Forcing every tree-shaped dimension to instead
be enforced via an authored Rule would turn free structural validation into corpus-authoring
burden for no gain.

### 2.3 Do the other three validation levels need adjustment

Walking D2's remaining three levels against a cross-cutting feature:

- **Hard pairwise requires/conflicts (edges).** Already feature-to-feature, already indifferent
  to which dimension (or whether any dimension) either endpoint lives in. A `conflicts-with` edge
  between "checked exceptions" and some other feature works identically whether "checked
  exceptions" sits in an `exclusive` or `multi` dimension. **No change needed** — this is exactly
  the O6-anticipated case where the exclusivity assumption was never baked into the edge
  machinery, only into the dimension-exclusivity level.
- **Soft influences warnings.** Same conclusion — polarity edges are pairwise and
  dimension-agnostic. **No change needed.**
- **Rule entities.** Also already feature-set-based (a Rule fires on a combination of features,
  not on dimension membership) — **no change needed**, and per 2.2 this is where any
  finer-grained cross-cutting constraint ("at most one of these is your primary mechanism")
  belongs if one is ever needed, rather than inventing new dimension-exclusivity modes.

**Net finding: only the dimension-exclusivity level needed a fix (the `exclusivity` field from
2.1); the other three levels already handle cross-cutting features correctly today, because they
were never dimension-shaped to begin with.** This is a reassuring result — it means the ontology
schema change is genuinely small (one new field, default-backward-compatible) rather than a
validation-engine redesign, and the Builder's future rules-engine work (topic 52) inherits a
simpler contract: "read `dimensions.yaml`'s `exclusivity` per dimension; everything else is
already flat feature-graph traversal you'd have built anyway."

### 2.4 Resolving the Exceptions collision (O6 point 4)

Concretely, under the 2.1 recommendation: the brief's layer-3 `Exceptions:
checked/unchecked/effect-system` value list is a **mis-specified `exclusive` dimension that
should instead be a `multi` dimension** (or several `multi`-dimension features, see below) —
languages don't pick one exception idiom, they accumulate mechanisms. The deliberately-excluded
"Exceptions" **Concept** (D16 O6) is a different, higher-level thing: the pedagogical umbrella
page that explains what exception handling *is* as an idea, under which the atomized features
(`checked-exceptions`, `result-type-error-handling`, `panic-unwind`, `effect-system-errors`, …)
eventually hang as children, each independently `cross_cutting: true` and living in a
`multi`-exclusivity "Error handling mechanism" dimension. So: no actual naming collision needs to
survive — "Exceptions" the Concept becomes the pedagogical parent, "Error handling mechanism"
(renamed from the brief's literal "Exceptions" dimension label to avoid the name doing double
duty) becomes the `multi` dimension its children populate. This is exactly the kind of
dimension-restructure D16's split/move casebook already anticipates ("dimension moves touch only
classification facts... Rules and `alternative-to` edges in the affected dimension enter a review
queue") — so when this atomization actually happens during the research phase, it rides ordinary
migration machinery (topic 29's tooling), not a special case. Flagging that a new field
(`exclusivity`) shipping now is what lets that future migration be a plain dimension-restructure
rather than a schema MAJOR forced by a missing affordance — same logic D16 already used to justify
`cross_cutting` itself.

## 3. Recommendation (*proposed*)

1. **Add `exclusivity: exclusive | multi` to `dimensions.yaml`'s per-dimension record** (per
   brainstorm 22's artifact layout, `ontology/taxonomy/dimensions.yaml`), defaulting to
   `exclusive` when absent so every currently-tree-shaped dimension needs zero edits. This is a
   MINOR/PATCH-cost additive schema change under D16, not a MAJOR.
2. **Dimension-exclusivity validation (D2 level 1) reads this field**: `exclusive` enforces
   today's at-most-one-feature rule unchanged; `multi` skips the check entirely (any subset may
   co-occur). No partial/counted mode — anything more nuanced than one-of/any-of is a Rule
   entity's job (D2 level 4), not a new dimension-exclusivity mode.
3. **`cross_cutting: true` on a feature (already ratified by D16) stays feature-level metadata**,
   used for site badging, RFC triage, and a lint rule asserting it agrees with its home
   dimension's `multi` exclusivity — it does no validation work on its own; the dimension's
   `exclusivity` field is what the validator actually consults.
4. **The other three combination-validation levels (hard requires/conflicts, soft influences,
   Rules) need no schema or semantics change** — they were already feature-pairwise/feature-set
   machinery, never dimension-shaped, so cross-cutting features interact with them exactly like
   any other feature today.
5. **Resolve the Exceptions collision by treating it as a dimension mis-specification, not a
   modeling gap**: rename the brief's literal "Exceptions" dimension to something like "Error
   handling mechanism," mark it `exclusivity: multi`, and let the deliberately-excluded
   "Exceptions" Concept remain the pedagogical parent the atomized mechanism-features
   (`checked-exceptions`, `result-type-error-handling`, `panic-unwind`, …) eventually link under
   via `realizes` — exactly the Concept-first-staging-then-atomize path D16 already prescribed.
   Treat this as the concrete worked instance of O6 point 4's "first real test," ready to execute
   whenever the research phase reaches exception handling, using ordinary dimension-restructure
   migration machinery (ties to topic 29).
6. **No ontology content exists yet to migrate.** As of this writing the frontloaded research
   phase (D11/topic 25) has not started minting layer-3 dimensions or features — this is a
   pre-emptive schema fix, not a corrective migration. The practical instruction is: **land the
   `dimensions.yaml` `exclusivity` field before the research phase mints its first layer-3
   dimension**, so no dimension is ever authored under the wrong assumption to begin with, and no
   topic-29-flavored migration is needed later purely to correct this. If a handful of dimensions
   do get minted `exclusive` by default before this is read and later turn out to be additive,
   correcting them is an ordinary dimension `exclusivity` flip — cheap, and explicitly the kind of
   change topic 29's blast-radius tooling and migration-manifest DSL are built to carry (§5 below
   makes this connection explicit; it is not re-designed here).

## 4. Open questions for the developer

1. Does the `dimensions.yaml` `exclusivity: exclusive | multi` field name/shape read right, or
   would you rather fold this into `cross_cutting` more directly (e.g. inferring a dimension's
   exclusivity from whether any of its member features are `cross_cutting: true`, rather than a
   separate explicit per-dimension field)? The explicit field was chosen so the rule is legible
   straight from `dimensions.yaml` without cross-referencing every feature file, but it does mean
   the two fields (feature-level `cross_cutting`, dimension-level `exclusivity`) must be kept in
   agreement by a lint rule rather than being definitionally the same fact.
2. Is "Error handling mechanism" (renamed from the brief's "Exceptions") an acceptable dimension
   label, or should the research phase just inherit whatever name falls out of R0/R1 survey work
   rather than this brainstorm pre-naming it? (Flagged here only so the collision D16 named isn't
   silently forgotten — not meant to bind the actual research-phase naming.)
3. Should `multi`-exclusivity dimensions be visually distinguished from `exclusive` ones on the
   site's feature-matrix / coverage pages (topic 19/44), or is that purely a later site-IA
   decision this brainstorm shouldn't reach into?
4. Is the "no partial/counted exclusivity mode — anything more nuanced is a Rule" line (§2.2) the
   right permanent stance, or is there a cross-cutting concern you can already picture (beyond
   exceptions/security/naming) that would need a genuinely counted constraint at the dimension
   level rather than at the Rule level? If none comes to mind, this stays as recommended.
5. Confirm the deferred scope: this brainstorm intentionally does **not** design topic 52's
   Builder rules-engine consumption of the `exclusivity` field, and does **not** re-derive topic
   29's migration tooling for the eventual Exceptions dimension restructure — both stay pointers.
   Is that boundary right, or did you want a sketch of the Builder-side consumption here too?

## 5. New brainstorm topics surfaced

None judged to need a new standalone backlog entry. Two existing backlog items should absorb a
one-line addition when this brainstorm is reflected into the checklist, since both are explicitly
touched by this topic's output but neither needs a new number:

- **Topic 52 (Builder combination-validation engine)** — should note, whenever it's picked up,
  that its dimension-exclusivity check needs to read `dimensions.yaml`'s `exclusivity` field
  (this topic's output) rather than assuming every dimension is a partition; the rest of its
  rules-engine shape is unaffected since edges/Rules already handle cross-cutting features
  without change (§2.3).
- **Topic 29 (Ontology change tooling)** — should note that a dimension's `exclusive → multi`
  flip (or the eventual Exceptions Concept-to-feature atomization from §2.4) is a concrete
  worked instance of exactly the "dimension move or restructure" migration row its casebook
  already has a slot for, usable as the casebook's first real worked example when topic 29's
  tooling gets exercised for real.

Option B's multi-dimension-membership idea (§2.1) is explicitly deferred rather than promoted to
a topic — no concrete feature has surfaced yet that needs a second home dimension rather than an
ordinary edge into an adjacent concern, so there's nothing to design until one does.
