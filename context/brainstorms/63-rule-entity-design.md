# 63 — Rule Entity Design

> Ad hoc brainstorm requested directly by the developer 2026-07-25 (not surfaced by a prior
> round). Topic: the **Rule** entity (§3.1, §3.3, §3.6 of `spec.md`) has only ever appeared as a
> side mention inside other brainstorms — 01 (introduced the 4-level combination-validation
> model), 09 (gave it a record shape and canonical-claim form), 30 (used it only as the
> "anything more nuanced" escape hatch), 38 (rules compile to a sweep `constraints:` list), 59/D61
> (designed what happens when a Rule is *violated*, not how one is authored). No session has ever
> designed the entity itself: `then`/`effect` semantics, who authors a Rule and when, and whether
> `when_any`/`unless` need more shape than "additive later." The developer also asked two
> collapsing questions explicitly: can `warn` fold into `influences`, and can hard pairwise
> `requires`/`conflicts-with` edges fold into Rules — i.e., can the 4-level model shrink to fewer
> primitives. All proposals below are *proposed*, not ratified, per the project's decision-hygiene
> convention.

## Problem framing

Everything decided about Rule so far:

- Record shape (brainstorm 09 / spec §3.3, §3.4): `id`, `when_all: [<feature-ids>]`,
  `effect: requires | forbids | warn`, `then`, `message` + `sources`, `provenance`; stored
  `rules/<rule-id>.yaml`, one file per rule; canonical claim `rule-exists(rule-id, sha256-16=…)`.
- Role in combination validation (spec §3.6): level 4 of 4 — dimension exclusivity, hard pairwise
  edges, soft `influences` warnings, then Rules for "multi-feature emergent interactions,"
  `when_all` conjunctive-only in v0, `when_any`/`unless` explicitly deferred as additive.
- What's *not* decided: the internal shape of `then` (a feature id? a list? does it mean
  different things per `effect`?), who mints a Rule and under what evidence bar, whether a
  1-antecedent Rule is even legal, how `when_all` is canonicalized for hashing/dedup, and the two
  collapsing questions below.

This is a schema-completeness gap, not a schema-change gap — nothing here is a D16 ontology MAJOR
(no new entity type, no new taxonomy dimension). It's filling in a record type that was named but
never fully specified.

## Options with trade-offs

### O1 — `then` field shape and per-`effect` semantics

**O1a (recommended) — `then` is a list of feature ids, interpreted per `effect`:**

- `effect: requires` — every feature in `then` must be present whenever every feature in
  `when_all` is present (the joint antecedent triggers a joint consequent); `then` must be
  non-empty (≥1 feature) — a `requires` Rule with nothing to require is meaningless.
- `effect: forbids` — no feature in `then` may be present whenever `when_all` holds (the N-ary
  generalization of `conflicts-with`); `then` must be non-empty for the same reason.
- `effect: warn` — `then` names the feature(s) the caution concerns, but may be **empty** — a
  warning can be entirely about the antecedent combination itself ("A+B together often confuses
  newcomers even though technically valid") with no third feature implicated.

```yaml
id: rule-laziness-needs-purity
when_all: [lazy-evaluation, side-effects-allowed]
effect: forbids
then: [referential-transparency]
message: >-
  Lazy evaluation combined with unrestricted side effects makes evaluation order
  observable, which breaks the referential transparency that pure functional
  languages otherwise guarantee — hence Haskell's insistence on purity wherever
  laziness is pervasive.
sources: [...]
provenance: {...}
```

**O1b — rejected: `then` as a single feature id, no list.** Real multi-feature interactions
plausibly imply more than one downstream consequence at once (e.g., "A+B jointly require both C
and D"). A singular `then` would force splitting that into two Rules sharing an identical
`when_all`, duplicating the antecedent and its sourcing for no benefit — a list costs nothing
extra to validate and avoids the duplication.

**O1c — rejected: a richer `then` supporting nested boolean expressions (e.g. "C or D").** Nothing
in the four active brainstorms or the spec's worked examples has ever needed disjunctive
consequents, and `when_any`/`unless` (O3 below) already carries the project's appetite for
richer boolean shape on the *antecedent* side, deliberately deferred. Building disjunctive
`then` now would be speculative design against no concrete case — YAGNI.

### O2 — Authoring workflow: who mints a Rule, and when

Per the developer's steer, both the frontloaded research phase *and* per-language sweep agents
can propose new Rules — this is not confined to the research phase the way, say, a new taxonomy
dimension would be.

**O2a (recommended) — minting a Rule is an ordinary content addition, gated exactly like a fact,
not a D16 MAJOR.** A Rule is a new *instance* of an already-existing entity type (same category
of event as minting a new `edge.requires.<a>.<b>` file), not a schema/taxonomy change — no human
gate is owed beyond the same admissibility rule every fact already clears (≥1 `supported`
tier-A/B citation grounding `message`). Concretely:

- **Research-phase agents** mint Rules while building the generic feature-landscape ontology,
  same as they mint edges — this is the common case and needs no new machinery beyond what
  edge-authoring already has (registry lookup to confirm every `when_all`/`then` feature id
  exists, admissibility-gated `sources`, direct commit, auto-flag if controversial).
- **Sweep agents** may also propose a *new* Rule mid-sweep when a language's realized feature
  combination exhibits an effect no existing edge or Rule explains. The proposing agent mints the
  Rule the same way (registry lookup, sourced `message`, direct commit) — it is not required to
  route through any human-gated path merely because it fired mid-sweep rather than during
  research. A sweep-authored Rule is exactly as challengeable afterward as any other fact
  (`rule-exists` is itself a derived fact per spec §3.5) — the normal human-challenge path is
  the correction mechanism, not a pre-commit review gate.
- **Consequence surfaced for topic 38 (see "New brainstorm topics surfaced" below):** topic 38's
  questionnaire compiler derives a sweep's `constraints:` list from the ontology at
  handoff-stamp time (`ontology_version`). A sweep agent minting a *new* Rule mid-sweep changes
  the ontology out from under a questionnaire that's already in flight for that same language —
  structurally the same problem topic 38 already solved for migrations (its "in-flight-answer
  disposition after migrations reuses D38's disposition DSL via a new delta-questionnaire diff").
  This brainstorm doesn't re-solve it; it flags that a self-authored mid-sweep Rule needs to run
  through that same disposition path rather than being treated as new territory.

**O2b — rejected: sweep-authored Rules require a human-gated review before commit.** Nothing else
in the no-PR-gate architecture (D1) singles out sweep-time content for extra review merely by
timing — the entire premise of "agents commit facts directly... admissibility comes from the
automated source-verification gate, controversial facts are auto-flagged" (CLAUDE.md) applies
uniformly. Special-casing Rules born mid-sweep would be an inconsistent carve-out with no stated
reason stronger than "it happened at sweep time."

### O3 — `when_any`/`unless`: design now, or stay deferred

**O3a (recommended) — stay deferred exactly as ratified, with one forward-compatibility note and
no further design work now.** The v0-conjunctive-only scope is an existing decision, not an open
question this brainstorm was asked to revisit, and no concrete case from any brainstorm to date
has needed disjunctive or negated antecedents — designing the mechanism now would be speculative.
The only addition worth making: when `when_any`/`unless` do land, they should be **sibling keys**
on the same record (`when_all` stays; `when_any: [...]`, `unless: [...]` get added later as
optional fields), not a restructuring of the antecedent shape — so today's `rules/<id>.yaml`
files never need migrating when that day comes, only new files start using the new keys.

**O3b — rejected: fully design `when_any`/`unless` semantics now (short-circuit evaluation order,
interaction with `then`, etc.).** Explicitly out of scope per the developer's own framing
("additive later") and no trigger has arrived to revisit that timing — this would be exactly the
kind of speculative future-proofing the project's own conventions warn against.

### O4 — Canonical form for `when_all` (dedup/hashing)

**O4a (recommended) — `when_all` is canonicalized as a lexicographically sorted list before
hashing into the rule's claim string**, mirroring `alternative-to`'s existing precedent (§3.3:
"`alternative-to` endpoints are stored in lexicographic order (CI-enforced) so the edge id is
canonical"). Without this, two agents independently authoring the same conjunctive rule with
`when_all` written in a different order would mint two different content hashes for what is
semantically one claim — exactly the false-negative-dedup failure D23's canonical-claim
normalization exists to prevent everywhere else. `then` is *not* order-sorted (its order can
carry authored meaning, e.g. "primary consequence listed first" — nothing forces this, but
nothing requires stripping it either); only `when_all`, the unordered conjunctive set, gets
canonicalized.

**O4b — rejected: leave `when_all` order-sensitive.** Would silently defeat dedup for the exact
scenario (independent agents converging on the same real-world interaction) the whole
canonical-claim system was built to catch.

### O5 — Explicit question 1: can `warn` fold into `influences`?

**Answer: no, don't merge the effect types — but yes, most *individual* `warn` Rules people would
be tempted to author today are miscategorized and belong in `influences` instead.** The two
constructs overlap heavily at arity 2 but diverge exactly where Rule's reason for existing lives:

- `influences` is **strictly pairwise** (`edge.influences.<from>.<to>`, ± polarity, no
  magnitude) — it can express "A softly cautions about B," full stop.
- A `warn`-effect Rule with `when_all` of size 1 and `then` of size ≤1 is **exactly** that same
  shape wearing a different hat — same information, more ceremony (freely-minted slug id,
  message field, no polarity sign), no expressive gain.
- But a `warn`-effect Rule with `when_all` of size **≥2** expresses something `influences`
  structurally cannot: "A and B *together* warrant caution about C, but neither alone does."
  Modeling that as two separate `influences` edges (A→C, B→C) silently changes the meaning from
  conjunction to independent-either-one-triggers-it — a real semantic loss, not just a style
  difference.

So the fold-in doesn't happen at the type level (`warn` stays a valid Rule effect, `influences`
stays a valid edge type); it happens at the **arity boundary** — see O6, which gives this a
mechanical enforcement point rather than leaving it a matter of authoring taste.

### O6 — Explicit question 2: can hard pairwise edges fold into Rules?

**Answer: no, and for the same structural reason as O5 — but the arity boundary is the thing
worth hardening, not the type distinction.** Three reasons to keep `requires`/`conflicts-with` as
edges rather than degenerate 1-antecedent Rules:

1. **Identity/dedup machinery is cheaper and stricter for edges.** `edge.<type>.<from>.<to>` is a
   *deterministic composed* id — two agents can never mint duplicate `requires` edges for the
   same ordered pair even before any content-hash dedup runs, because the id itself is the
   dedup key. Rules use freely-minted slugs (`rule-` + node id) precisely because an N-ary
   antecedent (N≥2) has no natural deterministic composition the way a 2-actor pair does. Folding
   2-arity content into Rules would trade a stronger, cheaper identity guarantee for a weaker,
   more expensive one, for zero expressiveness gain.
2. **The 4-level combination-validation model is an existing design invariant other brainstorms
   already build on.** Brainstorm 30 used "anything more nuanced... is a Rule entity's job" as a
   load-bearing boundary; topic 52 (Builder combination-validation engine, still open) is
   explicitly scoped around "edges/Rules already handle cross-cutting features without change" —
   i.e., as two distinct, independently-stable machinery types. Collapsing them would ripple into
   an already-open topic's stated scope for no expressive gain.
3. **Sharding/merge-conflict reasoning (§3.3) is edge-type-specific.** `edges/<from-id>/` is
   sharded by from-feature specifically *because* pairwise edges have exactly one from-feature to
   shard by — that storage optimization has no equivalent for an N-ary Rule (which from-feature
   would a 3-antecedent rule shard under?). Moving 2-arity content into `rules/` would either
   lose that sharding benefit or need a parallel scheme invented for content that already has a
   working one.

**The actionable fix (recommended): a CI-enforced arity floor, `len(when_all) ≥ 2`, on every Rule
record** — enforced in `tools/validate/normalize_record` alongside the other structural checks
already run there (§3.5). A candidate Rule failing this floor is a signal the agent should have
authored the corresponding edge instead:

| Rule `effect` with `len(when_all) == 1` | Correct edge type instead |
|---|---|
| `requires` | `requires` edge |
| `forbids` | `conflicts-with` edge |
| `warn` | `influences` edge (negative polarity) |

This single mechanical check resolves *both* explicit fold questions the same way: the boundary
between "2-actor pairwise" (edges) and "≥3-actor emergent" (Rules) already exists conceptually in
the spec's own language ("multi-feature emergent interactions") — it was just never given teeth.
Enforcing it closes the gap in both directions: an agent tempted to author a degenerate
1-antecedent "Rule" gets redirected to the cheaper, stricter edge machinery; an agent modeling a
genuine ≥2-antecedent interaction as a set of ad hoc pairwise edges (silently losing the
conjunctive "only together" meaning) has no valid edge type to reach for instead, so the Rule
path is the only one left standing for that case.

## Recommendation

*Proposed* package:

1. **`then` (O1):** a list of feature ids; `requires`/`forbids` require it non-empty, `warn`
   permits empty (caution about the antecedent combination itself).
2. **Authoring (O2):** minting a Rule is an ordinary admissibility-gated content addition (same
   bar as a fact), not a D16 MAJOR — legal both during frontloaded research and mid-sweep; no
   extra human gate for the sweep-triggered case. A sweep-minted Rule's interaction with an
   already-handed-off questionnaire (topic 38) is flagged as a fold-in, not solved here.
3. **`when_any`/`unless` (O3):** stay deferred exactly as already ratified; only addition is a
   forward-compatibility note — they'll land as new sibling keys on the existing record shape,
   never a restructuring of `when_all`.
4. **Canonical form (O4):** `when_all` is lexicographically sorted before hashing into the
   claim string (mirrors `alternative-to`'s existing precedent); `then` stays authored-order.
5. **`warn`/`influences` fold (O5):** not merged at the type level; resolved via the arity floor
   in (6) below — a 1-antecedent `warn` Rule is miscategorized and belongs in `influences`.
6. **Hard-edge/Rule fold (O6):** not merged; instead, a new CI check enforces
   `len(when_all) ≥ 2` on every Rule, mechanically redirecting degenerate 1-antecedent candidates
   to the matching edge type (`requires`→`requires`, `forbids`→`conflicts-with`,
   `warn`→`influences`). This single check answers both explicit fold questions.

Net effect: no entity types removed, no ontology MAJOR, one new CI validation rule, one schema
completion (`then`'s per-effect semantics), and the authoring-workflow question resolved by
recognizing Rule-minting as ordinary content authorship rather than a special case.

## Open questions for the developer

1. **Arity floor as the resolution to both fold questions (O6)** — confirm `len(when_all) ≥ 2`
   as a CI-enforced hard requirement on every Rule record, with the conversion table above as
   authoring guidance.
2. **`then` empty-only-for-`warn` validation (O1)** — confirm `requires`/`forbids` Rules must
   have non-empty `then`, while `warn` Rules may have an empty `then`.
3. **Sweep-triggered Rule minting needs no extra human gate (O2)** — confirm a sweep agent
   proposing a brand-new Rule mid-sweep is gated exactly like any other fact (admissibility rule,
   direct commit, auto-flag if controversial), not routed through any review path reserved for
   ontology MAJORs.
4. **`when_all` canonical sort order for hashing (O4)** — confirm lexicographic sort, matching
   `alternative-to`'s precedent, with `then` left in authored order.

## New brainstorm topics surfaced

None new. One fold-in: **topic 38 (Questionnaire compiler)** should have its description amended
to note that a sweep agent minting a *new* Rule mid-sweep is the same shape of problem topic 38
already solved for ontology migrations landing while a questionnaire is in flight (reuse of the
disposition DSL via a delta-questionnaire diff) — not a new topic, just an additional trigger for
machinery topic 38 already designed.
