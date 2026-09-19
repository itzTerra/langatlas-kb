# 65 — Schema plasticity in the research phase

> Ad hoc brainstorm requested by the developer on 2026-09-19, during cycle 1's (typing) first R4
> run. Topic: the Stage 3 machinery treats the brief's seed ontology structure (three layers, the
> concept/feature split, `realizes` → concept, the edge-type set, the dimension model) as a fixed
> contract that agent output must conform to. The developer's position is that the seed is **not**
> confirmed correct, and that the early research cycles are *the* way to find the right ontology,
> so the start of the phase must be as flexible as possible. All proposals below are *proposed*
> unless marked ratified. The developer ratified the direction in principle (steps 1–4 below)
> on 2026-09-19.

## Problem framing

[spec §7.4](../spec.md) already frames R3–R6 as turning "the brief's seed sketch (layer lists +
Jordan et al. 2015)" into ontology v1.0. The seed is the input to the research phase, not its
result. The Stage 3 machinery (sub-plans 3A–3F) nonetheless enforces the seed structure at every
step:

- **Schemas are closed.** `RECORD_KINDS` has exactly eleven kinds. A feature has exactly one of
  three layers. `realizes` may only name a concept. `dimensions.yaml` follows D39/D67's
  exclusivity model.
- **The ontologist's shape check rejects the whole run.** `_check_shape` in
  `tools/research/src/langatlas_research/draft/ontologist.py` raises `DraftOutputInvalid` on any
  carve that breaks the structure, so nothing the model proposed survives, including the parts
  that fit.
- **Debates can only challenge carves inside the structure.** R4's challenge vocabulary
  (`wrong-atomization | wrong-layer | missing-source | redundant-with | scope`) contests where a
  carve sits, never whether the structure has the right slots.
- **Findings have no "doesn't fit" type.** The ontologist's findings are `rule-candidate`,
  `cross-theme-edge`, `unmappable-candidate` and `missing-locator-backend`. `unmappable-candidate`
  means "I can't place this candidate", not "the model lacks a slot for this relation".
- **Minting is immediate and ids are immutable.** Under the 0.x ceremony, R4 mints each node as it
  clears the gate. A node minted under a wrong structure has to be undone later through
  redirects, tombstones and (once its theme settles) migration manifests.

### The concrete case that surfaced it

Cycle 1's `draft atomize` failed twice with the same shape. Without being asked, the ontologist
built **refinement chains between features**: `ad-hoc-polymorphism` (a layer-2 feature) with
`type-classes` realizing it, `parametric-polymorphism` with `let-polymorphism` and
`generic-parameters` under it, `algebraic-data-types` with `gadt` under it, and `gradual-typing`
with `retrofitted-type-system` under it. It expressed each chain as `realizes: [<feature-id>]`,
which the shape check rejects because `realizes` targets concepts only. The seed has no
feature→feature specialisation relation at all.

A first fix (prompt `r4-ontologist` v3, since withdrawn and never committed) told the model to
flatten these chains and describe the refinement in prose `note`. That made the run pass, but it
suppressed exactly the structural signal the research phase exists to collect. It was reverted.

## What is fixed and what is provisional

Not everything is up for revision. The line proposed here:

**Fixed (process and sourcing invariants — not ontology structure):**
- Every node is source-backed; priors steer only where to look; agent text is never citable (D4).
- The D24 verification gate as admissibility (D1/D4).
- Every agent chat is logged (D18); web/finding-aid content is data, never instructions (D31);
  finding aids are never citations (D29/D53).
- Developer sign-off before a cycle runs (D27).
- Git is the database; derived artifacts stay derived (D1).

**Provisional until the structure review (proposed):**
- The three layers and their definitions (`ontology/taxonomy/layers.yaml`, D2).
- The concept/feature split and what `realizes` means.
- The relation vocabulary (`ontology/taxonomy/edge-types.yaml`), including whether a
  feature→feature refinement relation exists.
- The dimension model (D39 exclusivity, D67 values-are-members, D50 `applies_to`).
- The seed quality vocabulary (D69, which already calls itself a seed).
- The record kinds themselves, where a structure finding argues for a new one.

## Options with trade-offs

### O1 — How the ontologist is told about the structure

**O1a — Keep enforcing the seed, tighten the prompt.** This is what the withdrawn v3 did. Runs pass
reliably and records mint immediately, but every misfit gets flattened into prose and lost. It
directly contradicts the developer's position. Rejected.

**O1b (recommended) — Present the structure as a hypothesis.** The prompt states that the layers,
the concept/feature split and the relation set are the current working model, not settled truth.
When a carve does not fit, the ontologist carves it the way the sources support *and* records a
new finding kind, `structure-friction`, naming the structural element at issue and what it would
need (for example, "feature→feature specialisation relation; see `type-classes` →
`ad-hoc-polymorphism`"). The run is not steered toward conformance.

### O2 — What the shape check does with a misfit

**O2a — Reject the whole run (today).** One misfit discards every good carve and the misfit's
information. Rejected.

**O2b (recommended) — Keep misfits in the plan as unmintable.** `_check_shape` splits its checks
in two. **Hygiene errors** (invalid slugs, duplicate keys, re-minting a committed id, exceeding the
node cap) still reject the run, because they are defects rather than information. **Structural
misfits** (`realizes` naming a non-concept, a layer outside the three, a layer-3 feature without a
dimension, and so on) are kept in the carve plan, flagged `blocked: structure`, and linked to a
`structure-friction` finding. If the model reported no finding, the check synthesises one. A
blocked carve can never mint, but it stays visible for the structure review.

**O2c — Accept anything, validate only at mint.** This keeps the most information but lets
hygiene errors through too, and pushes every problem to mint time. Too loose.

### O3 — How debates can contest the structure

**O3a (recommended) — Add a `wrong-structure` challenge type.** It sits beside `wrong-layer` and
the others. A challenger can argue that a carve is forced because the model lacks a slot. A
`wrong-structure` resolution doesn't change the carve. It files (or reinforces) a
`structure-friction` finding for the structure review.

**O3b — No debate path; findings only.** This is simpler but leaves the challengers unable to
say the most important thing they might notice. Rejected.

### O4 — When nodes are minted

**O4a — Mint per cycle, as today, with the structure easy to change.** Each restructure costs
redirects and tombstones. Every structure change after the first minted theme touches already
minted records, and immutable ids chosen under the old structure stay forever. Cheap to run,
expensive to change course.

**O4b (recommended) — Draft first, mint later.** The first cycles run R3 → R4 in **carve-plan-only
mode**: surveying, atomizing, contesting, debating and verifying all run, but nothing mints. After
several themes, a **structure review** (a developer checkpoint) reads every `structure-friction`
finding across the drafted themes and decides the schema changes. Only then are the drafted
themes' carve plans re-atomized or re-conformed against the revised structure and minted.
Later cycles mint per cycle as today, with structure findings still collected but expected to be
rare.

Running `draft verify` in carve-plan mode is still worthwhile. Whether a node's definition is
supported by its sources does not depend on the structure, so draft-mode verification catches
evidence problems early. Verdicts go to the private ledger as today (D68's alignment).

The cost is that the drafted cycles produce no committed nodes for a while. R5's questionnaire
compiler reads the committed ontology subtree, so R5 either waits for the post-review mint or
learns to compile from a carve plan (open question 3).

## Recommendation

O1b + O2b + O3a + O4b. Concretely:

1. The ontologist (and the edge drafter, which has the same finding vocabulary) is told that the
   structure is provisional, and gains a `structure-friction` finding kind.
2. The shape check keeps misfits as `blocked: structure` carves linked to a finding, and rejects a
   run only for hygiene errors.
3. Debates gain a `wrong-structure` challenge type whose resolutions feed the findings.
4. A **draft-only batch** of the first N themes runs R3 → R4 (through `draft verify`) without
   minting. Cycle 1 (typing) is the first member.
5. A **structure review** checkpoint reads all `structure-friction` findings across the batch.
   The developer decides the schema changes, which land as ordinary 0.x changes, and the batch's
   themes are then minted.
6. After the review, cycles mint per cycle as the runbook already describes.

This re-opens sub-plan 3C (ontologist, shape check, challenge vocabulary, draft finalize), touches
3A's cycle status machine (a drafted-but-unminted status) and the runbook's order. It gets its own
implementation plan.

## Open questions for the developer

> Answered 2026-09-19 (recorded in decisions.md D70): 1 → four themes; 2 → typing, memory-management,
> concurrency, syntax-layer-constructs; 3 → R5 stays out of the batch unless the structure is still
> unclear; 4 → yes; 5 → re-atomize, not by hand; 6 → ontology structure only, but findings carry an `area` tag so adjacent-schema friction is listed for case-by-case decisions; 7 → as proposed.

1. How many themes go in the draft-only batch before the structure review? Three is enough to see
   whether a misfit recurs across themes; all twelve delays minting until the whole landscape is
   drafted.
2. Which themes join typing in the batch? A spread that stresses different parts of the structure
   (for example memory management for layer-3 dimensions, higher-order programming for the
   concept/feature split) would surface more friction than neighbouring themes.
3. Does R5 run during the draft-only batch (compiling a questionnaire from the carve plan instead
   of the committed store), or wait until after the structure review's mint? Running it early
   yields more structural evidence (unfittable languages, uninhabited dimension values) but needs
   the compiler to read a carve plan.
4. Does the edge drafter run during the batch? Edges need committed endpoints to mint, but
   drafting them against carve-plan nodes would expose relation-vocabulary friction (such as the
   refinement relation) before the review.
5. After the structure review, are the batch's carve plans re-conformed by hand to the revised
   structure, or re-atomized by the ontologist from the same surveys? Re-atomizing is cleaner but
   costs a second Claude pass per theme.
6. Does the structure review also have authority over sourcing-adjacent schema (for example the
   `provenance` block or the fact-id scheme), or only over ontology structure (layers, kinds,
   relations, dimensions)? This brainstorm proposes the latter.
7. After the structure review, what happens when a later cycle raises a `structure-friction`
   finding? Proposed: it is recorded and reviewed at that cycle's R6, and a change that touches a
   settled theme goes through the settled-theme migration manifest.

## New brainstorm topics surfaced

- **Feature refinement relation.** Cycle 1's ontologist independently built feature→feature
  specialisation chains (`type-classes` → `ad-hoc-polymorphism`, `gadt` → `algebraic-data-types`,
  `let-polymorphism` → `parametric-polymorphism`, `retrofitted-type-system` → `gradual-typing`).
  Whether the ontology needs a `specializes`/`refines` relation (as an edge type, a field, or by
  promoting the parent to a concept), and how it would interact with layers, dimensions and the
  questionnaire compiler, is a structure-review decision that deserves its own brainstorm once the
  draft-only batch has produced more cases.
