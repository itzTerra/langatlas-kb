# 42 — Domain-Specific Languages in the Ontology

> Backlog brainstorm for LangAtlas. Topic: how the ontology represents languages that are not
> general-purpose (SQL-class query languages, and by extension shell/config/build/markup
> languages at the boundary) — a `language_kind` field on the Language record, per-dimension
> "applicability" declarations, or ruling DSLs out of scope entirely — and how that
> representation avoids corrupting the absence-semantics state space brainstorm 41 just
> finished designing. Binding context: D2 (the knowledge model — Feature/dimension/layer-3
> model, four-level combination validation, "nothing is developer-curated/closed"); D16
> (ontology versioning — additive-schema-is-PATCH/MINOR-cost precedent, the `cross_cutting`
> affordance landed pre-emptively for the same reason this topic needs a pre-emptive
> affordance); [brainstorm 30](30-cross-cutting-concern-modeling.md) (the `dimensions.yaml`
> `exclusivity: exclusive | multi` field this topic's design directly parallels, and its
> "default requires zero edits to existing entries" cost discipline); [brainstorm 41](41-absence-and-unknown-semantics.md)
> (the `no-record`/fact-object state-space split, D46's ratified "no per-language sweep-item
> filtering" principle, and the explicit warning this topic must not collapse "inapplicable"
> into "absent" or "not-yet-swept"); D28/[brainstorm 34](34-initial-language-selection.md)
> (the 14-language curated set, SQL and TypeScript explicitly deferred, SQL's ISO/IEC 9075
> spec named as paywalled with no free draft — a *separate* blocker from this topic's); D46/
> [brainstorm 38](38-questionnaire-compiler.md) (the sweep-item compiler, its language-agnostic
> item emission, and the ratification note this topic must not appear to violate); D32/D33
> (the `/coverage/` matrix's three empty-cell states and D33's note that syntax-check tooling
> is "acceptable indefinitely, not conditioned on topic 42 settling `language_kind` first" —
> i.e. the developer already anticipated this topic minting that field). All proposals below
> are *proposed*, not ratified, per the project's decision-hygiene convention.

## Problem framing

D28 deferred SQL from the initial 15-language set with two independent stated reasons:
brainstorm 34's paradigm audit found "most layer-2/3 dimensions (memory management,
concurrency model, parameter passing, module systems…) are inapplicable or apply only to
vendor procedural dialects," and separately, ISO/IEC 9075 is paywalled with no freely
published working draft (unlike C, C++, Prolog's Deransart-et-al. substitute, or every other
onboarded language). The second problem is a sourcing-acquisition question, already scoped and
tracked by topic 34/D28 — this brainstorm does not re-litigate it. **The first problem is this
topic's entire job**: the ontology, as currently specified, has no way to say "this dimension
does not apply to this language" that is distinguishable from every other way a cell can be
empty or negative.

That distinction matters more than it might look, because brainstorm 41 just spent an entire
session establishing exactly the state space this topic risks corrupting. Topic 41's headline
finding: for a (language, feature) pair, there are states where *no fact record exists*
(`not-yet-onboarded`, `not-yet-swept`, `deferred`) and states where *a sourced fact record
exists* (`present`, `partial`, `absent` — all the same `instance-exists` claim kind). The
entire point of that design was refusing to let "nobody has looked yet" collapse into "the
answer is no." A DSL's inapplicable dimensions are neither of those things, and treating them
as either one is a distinct, third failure mode:

- **Inapplicable ≠ `status: absent`.** `absent` is a sourced, verified, challengeable claim: a
  sweep agent read SQL's reference, argued the source is comprehensive over some category
  (per topic 41's new `absence_scope` field), and the verifier's `completeness-check` confirmed
  the feature genuinely doesn't appear. That machinery is built for "the language could
  plausibly have this feature; a competent reader determined it doesn't." Asking whether SQL
  (as a language, not a vendor's procedural extension) has a "concurrency model" in the layer-3
  sense the dimension was designed to classify is not that kind of question — there is nothing
  for a sweep agent to read and confirm-absent, because the dimension is not describing a
  choice SQL's designers ever faced. Forcing every DSL through the `absent` path would mean
  fabricating an `absence_scope` argument and a `completeness-check` verification for a
  question that was never coherent to ask, for every inapplicable dimension, for every DSL —
  real verifier cost spent manufacturing evidence for a non-question, and a misleading site
  presentation ("SQL: concurrency model — not present" reads as a genuine competitive gap,
  not a category mismatch).
- **Inapplicable ≠ `no-record: not-yet-swept`.** `not-yet-swept` promises the cell is real,
  unanswered work — exactly what D32's coverage page invites a contributor to fill via
  `propose-coverage.yml`. An inapplicable dimension is not unanswered work; inviting a
  contributor to research SQL's memory-management strategy is asking them to do the
  manufactured-evidence exercise above.
- **Inapplicable ≠ `no-record: deferred`.** Topic 41 defined `deferred` as "an explicit scoping
  decision, not a pipeline gap" — closer, but still wrong shape: `deferred` in D28/D32's usage
  is a *per-language* roadmap decision (SQL as a whole is deferred pending sourcing) tracked in
  prose on a roadmap document, re-evaluated by the developer language by language. Inapplicable
  is a *per-(language-kind, dimension)* structural fact, mechanically derivable from schema
  data the moment a language's `language_kind` is set — it should never need a human to
  maintain a per-cell deferred list the way `deferred` does today.
- **Inapplicable ≠ a `cross_cutting`/`exclusivity: multi` dimension (brainstorm 30).** That
  topic solved a different problem — a language accumulating *multiple* values from one
  dimension (Rust has try/catch-adjacent panics *and* Result types *and* unwinding). This topic
  is about a dimension having *zero possible values* for an entire class of language, which
  brainstorm 30's `exclusive | multi` axis has no room to express (both values still assume the
  dimension is askable at all).

So the concrete design question is: what schema affordance makes "this question is not
coherent for this language" a first-class, mechanically-derived, non-fact state — distinct from
all five of topic 41's states — and how does it interact with the D2 four-level combination
validation and the D46 sweep-item compiler without reopening D46's "no per-language filtering"
ban.

## Options with trade-offs

### O1 — Should DSLs be represented in the ontology at all, or ruled out of scope?

**O1a — Out of scope entirely.** The KB only ever models general-purpose languages; SQL stays
permanently deferred (not just pending sourcing); no schema change needed. Cheapest possible
answer, and defensible — nothing in D1–D46 mandates DSL coverage.

Rejected as the sole answer. Brainstorm 34 already treated SQL's deferral as *pending an
ontology position*, not a rejection — D28's own text says "SQL (needs an ontology position on
DSLs first)," and SQL carries real, independently-argued audience/search-volume value (brainstorm
34 §"Audience relevance," TIOBE #8). Foreclosing DSLs permanently also forecloses a real
positioning opportunity: SQL is the single highest-traffic "does X have Y" query surface outside
the mainstream OOP/imperative cluster, and D19's typed-concept-graph wedge is precisely the kind
of feature that differentiates "SQL has 3-valued logic and set-based semantics" from a page that
just says "not applicable" with no structure behind that claim. Out-of-scope is the right call
*for languages that aren't really "programming languages" at all in the KB's sense* (see O1c),
but not for SQL.

**O1b — In scope, but only as a documentation/prose exception, no schema change.** Onboard SQL,
and when a sweep agent hits an inapplicable dimension, write a prose note in the instance file
explaining why, without a controlled field. Rejected: unstructured prose can't drive the
coverage matrix, the MCP `no-record` envelope, or the D46 compiler's item-emission logic — it
would need to be re-parsed by every consumer, exactly the kind of unstructured-data smell the
project has consistently rejected elsewhere (D2's "everything traces to a structured record,"
D25's typed axes over free-text).

**O1c — In scope for languages with a real, citable spec/reference and a genuine feature
surface worth mapping (SQL-class); explicitly out of scope for things that aren't "programming
languages" in the KB's working sense at all (data/config formats like YAML/TOML/HCL, markup
like Markdown, and embedded mini-languages like a single regex dialect) — a scoping line drawn
by *editorial judgment on a case-by-case basis*, not a schema field.** This mirrors how D28
already treats language selection generally (curated, argued per-candidate, not a mechanical
rule) and keeps the schema question (this topic) separate from the "is X a language at all"
question (an ordinary D28-style onboarding decision made once, per candidate, when it comes
up — SQL now, others later or never).

**Recommendation: O1c.** DSLs are in scope in principle; the *schema* mechanism this topic
designs (O2/O3 below) is what makes any specific DSL onboardable, but whether a given borderline
candidate (regex, HCL, jq, a build DSL) actually gets onboarded stays a per-candidate D28-style
call, not something this topic tries to settle globally. This directly unblocks SQL's ontology
side while leaving SQL's separate sourcing-acquisition blocker (topic 34/D28) untouched.

### O2 — `language_kind` field, dimension applicability masks, or both

**O2a — `language_kind` only.** Add a controlled field to the Language record —
`language_kind: general-purpose | domain-specific` — and let downstream consumers (site,
compiler, Builder-future) branch on it directly wherever they currently assume every language
gets every dimension. Pro: minimal, one field. Con: pushes the actual applicability logic
(*which* dimensions a `domain-specific` language skips) into every consumer separately, with no
single source of truth — the compiler, the coverage matrix, and a future Builder would each need
their own hard-coded "if domain-specific, skip these dimensions" list, which drifts the moment a
second DSL with different applicable dimensions (e.g. a shell language, which *does* have a
meaningful "evaluation strategy" and "module system" story unlike SQL) gets onboarded.

**O2b — Dimension applicability masks only, no `language_kind` field.** Add an `applies_to`
list directly on each dimension record naming which *specific languages* (or an open list) it
applies to, with no intermediate classification. Pro: maximally precise, no taxonomy to get
wrong. Con: with only one DSL on the table, this means hand-listing every dimension's
applicable-language set with no reusable grouping — the moment a second DSL arrives, every
dimension record needs a fresh per-language edit rather than inheriting a classification. It
also gives the site/compiler nothing cheap to badge with ("this is a domain-specific language")
independent of the dimension-by-dimension detail, which brainstorm 34 already flagged as useful
positioning content ("SQL... stresses the ontology as a DSL, not as a general-purpose language").

**O2c (recommended) — Both, with `language_kind` as the coarse classification and dimension
applicability keyed off it, not off individual languages.** Concretely:

1. **`language_kind: general-purpose | domain-specific`** on the Language record (`languages/
   <lang>/language.yaml`, per the existing registry brainstorm 34/D28's phase gating already
   reads). Default `general-purpose` — every currently-onboarded language needs zero edits,
   matching D16/brainstorm 30's "additive change costs nothing at the existing-data level"
   discipline. A `domain` free-text tag (e.g. `"query"`, `"shell"`, `"config"`) rides alongside
   `domain-specific` for future site copy and for narrower applicability rules if a second DSL
   ever needs them — deliberately *not* a controlled sub-taxonomy yet (see open question 3):
   with exactly one DSL candidate on the table, minting a closed enum of DSL sub-kinds now would
   be exactly the kind of premature taxonomy-before-evidence D2's "nothing is
   developer-curated/closed" principle warns against.
2. **`applies_to: [language_kind, ...]`** on each dimension record in `dimensions.yaml`
   (parallel field to brainstorm 30's `exclusivity`, same file, same additive-cost story).
   **Default `[general-purpose]`** — the opposite default from `exclusivity`'s "default requires
   zero edits," and deliberately so: every dimension authored to date (and for the foreseeable
   research phase, since it's being designed against 15 general-purpose languages per D28) was
   designed against general-purpose languages exclusively; defaulting to "applies everywhere"
   would silently mis-scope every existing dimension the moment `domain-specific` becomes a real
   value, whereas defaulting to `[general-purpose]` costs nothing today (no domain-specific
   language exists yet to be mis-scoped by it) and only requires an edit at the one moment it
   actually matters — when a dimension turns out to be genuinely universal (e.g. "Typing
   discipline" plausibly widens to include SQL's type system; "Paradigm" may already need to
   name "declarative/relational" as a value) and gets explicitly opted in as the research phase
   reaches it.
3. **Feature-level override, same field name, for the rarer case.** Layer-1/2 features (no
   `dimension` per D2) inherit `applies_to` from nothing by default (implicitly universal, since
   most layer-1/2 syntax/semantic features genuinely are language-agnostic questions like "does
   the language have a function-definition syntax"); an individual feature may set its own
   `applies_to` to override its dimension's (or supply one directly if dimensionless) for the
   rare case where applicability doesn't cleanly follow the dimension it lives in. No new field
   name, no new mechanism — same key, narrower scope, feature-level always wins over
   dimension-level when both are present.

Pro: one small, additive, backward-compatible schema change (MINOR/PATCH under D16, same
blast-radius class as brainstorm 30's `exclusivity` field); a single source of truth the
compiler/site/coverage-matrix/future-Builder all read the same way; scales to a second DSL for
free (a shell language gets its own `language_kind: domain-specific, domain: "shell"` and only
needs *dimension* overrides for the handful of dimensions where it diverges from SQL's
applicability, not a fresh per-language dimension audit). Con: two fields to keep mentally
distinct (coarse kind vs. per-dimension applicability) — mitigated by the same kind of lint rule
brainstorm 30 proposed for `cross_cutting`/`exclusivity` agreement (a dimension's `applies_to`
list and a language's `language_kind` are checked for consistency at compiler time, not by a
human).

### O3 — How the compiler/coverage-matrix/MCP consume `applies_to` without violating D46

This is the reconciliation the task brief specifically flagged, and it deserves a precise
answer rather than a wave at "it's fine." D46's ratification note (quoted directly in topic 41's
binding context) says filtering sweep items would make the compiler "render a pre-evidence
judgment call about a language" — the compiler must never guess, for a specific
general-purpose language, that a feature probably isn't present and skip asking. That ban is
about **per-language, evidence-shaped guesses** ("Python probably doesn't have algebraic
effects, skip it"). It says nothing about **per-dimension, taxonomy-shaped scoping decisions**
made once in `dimensions.yaml`, entirely before any specific language is considered, driven by a
classification (`language_kind`) that is itself a one-time, cheap, essentially undisputed fact
about the language (SQL is definitionally a query language; nobody will file a
`challenge-fact.yml` disputing that) rather than a prediction about a feature's presence.
Concretely: the compiler already reads `dimensions.yaml`'s `exclusivity` field mechanically
(brainstorm 30) to decide how to group/validate a sweep item — it should read `applies_to` the
same way, as ordinary schema, not as language-specific reasoning:

> For each (language, feature) pair the compiler would otherwise emit: if the feature's
> effective `applies_to` (feature override, else dimension default, else universal) excludes
> the language's `language_kind`, do not emit a sweep item; instead, mark that pair with the new
> `no-record` reason **`not-applicable`** (extending topic 41's `reason` enum:
> `not-yet-swept | not-yet-onboarded | deferred | not-applicable`) at compile/build time, purely
> mechanically, no agent judgment involved.

This is the same category of decision D46 already implicitly accepts elsewhere — the compiler
already doesn't emit items for dimensions/features that don't exist yet in the ontology, or for
languages not yet onboarded; `not-applicable` is one more mechanically-derived non-emission
case, not a new kind of guess. The distinguishing test: **would a `challenge-fact.yml` on this
cell make sense?** For `not-yet-swept`, yes (someone can go answer it). For `absent`, yes
(someone can dispute the sourcing). For `not-applicable`, no — disputing it means disputing
`language_kind` or `applies_to` itself, which is an ordinary ontology/taxonomy edit (topic 29's
migration tooling), not a fact challenge. That test is worth stating explicitly in the eventual
schema docs so a future contributor doesn't reach for the wrong mechanism.

**Coverage matrix (D32/D33) and MCP (D35, extended by topic 41's O5) consequence:** a fourth
cell state, visually and semantically distinct from all three of D32's existing empty states and
from a filled `absent` cell — grayed/hatched "N/A," non-clickable (no `propose-coverage.yml`
deep link, since there's nothing to propose), reusing topic 41's `no-record` envelope shape with
`reason: "not-applicable"`. Exact visual treatment is left to topic 19/33 territory (pointer
only, per the same discipline topic 41 used for its own coverage-page notes) — this brainstorm's
job is only to establish that the *reason value* exists and where it's derived from.

### O4 — Interaction with D2's four-level combination validation

Walking D2's four levels against `applies_to`, the same way brainstorm 30 walked them against
`cross_cutting`:

- **Dimension exclusivity.** Already dimension-scoped; `applies_to` is an orthogonal axis on the
  same record (brainstorm 30's `exclusivity` answers "how many values may co-occur," this
  topic's `applies_to` answers "does this dimension even apply") — no interaction, both fields
  coexist on the same `dimensions.yaml` row with no shared logic to reconcile.
- **Hard pairwise requires/conflicts, soft influences, Rules.** All three are feature-graph-level
  (does feature A relate to feature B *in the abstract*), never per-instance, exactly as
  brainstorm 30 already established for `cross_cutting`. `applies_to` only ever gates whether a
  *sweep item* gets emitted for a *specific language*; it has no bearing on whether two features
  can relate to each other in the ontology's abstract graph. **No change needed at this level**,
  same conclusion brainstorm 30 reached for the same structural reason.
- **Future Builder (topic 52, deferred, pointer only).** Topic 41's O6 already established that
  any future Builder consuming per-instance data must treat `no-record` as a first-class third
  value, never defaulting it to `false`. This topic adds nothing new here beyond noting that
  `not-applicable` is one more `no-record` reason the Builder must not collapse into "the
  composed language lacks this feature" — same guardrail, one more enum value.

## Recommendation

*Proposed* package:

1. **DSLs are in scope in principle (O1c)** — not ruled out globally, but each specific
   candidate (SQL now, others later) is still evaluated case-by-case per D28's existing
   selection discipline. This topic removes the *ontological* blocker D28 named for SQL; SQL's
   separate ISO/IEC 9075 paywall problem (topic 34) is untouched and remains its own gate.
2. **Schema (O2c):** add `language_kind: general-purpose | domain-specific` (default
   `general-purpose`, zero edits to existing languages) to the Language record, with a free-text
   `domain` tag for `domain-specific` languages; add `applies_to: [language_kind, ...]` to
   `dimensions.yaml` (default `[general-purpose]`, so every dimension authored before this topic
   or during the general-purpose-only research phase needs zero edits, and is explicitly widened
   only when a dimension is confirmed genuinely universal); allow the same `applies_to` field as
   a per-feature override for the rarer dimensionless or divergent case. Both fields are
   additive, MINOR/PATCH-cost under D16, same class of change as brainstorm 30's `exclusivity`
   field, and should land before any DSL is onboarded (no urgency relative to the general-purpose
   research phase, which is unaffected either way).
3. **Compiler (O3):** the D46 questionnaire compiler reads `applies_to` mechanically alongside
   `exclusivity` and never emits a sweep item for a (language, feature) pair the language's
   `language_kind` doesn't reach — this is a taxonomy-driven, one-time, pre-language-specific
   scoping decision, not the per-language evidentiary guess D46 banned, and the two are
   distinguishable by a concrete test: would a `challenge-fact.yml` on the cell make sense? (Yes
   for every fact-bearing state, no for `not-applicable`.)
4. **State space extension (O3):** topic 41's `no-record` reason enum grows a fourth value,
   `not-applicable`, mechanically derived from `language_kind` × `applies_to` at build time —
   distinct from `absent` (a sourced, verified, challengeable negative claim), `not-yet-swept`
   (real unanswered work), and `deferred` (a per-language roadmap decision a human maintains).
   The coverage matrix and MCP `no-record` envelope both extend to carry this fourth reason with
   its own non-clickable, non-fact rendering; exact visual design deferred to topic 19/33.
5. **Combination validation (O4):** no change needed at the requires/conflicts/influences/Rules
   levels — same structural reasoning brainstorm 30 already established for `cross_cutting`,
   since none of those three levels are per-instance. The future Builder (topic 52, pointer only)
   inherits `not-applicable` as one more `no-record` reason it must never silently coerce to
   "feature absent."
6. **SQL, concretely:** once (2) is ratified, SQL's *ontology* blocker is removed. Its remaining
   blocker is sourcing: ISO/IEC 9075 has no free draft. Recommend the same substitution pattern
   D28 already used for Prolog (Deransart et al. 1996 in place of purchasing ISO/IEC 13211-1
   directly) — a permissively-licensed vendor-dialect reference (e.g. the PostgreSQL
   documentation, PostgreSQL License, or the SQLite documentation, public domain) as SQL's tier-A/
   B backing text in place of the paywalled standard, explicitly documented as "vendor dialect,
   not the ISO standard" per the tier system (D3) the same way spec-vs-implementation provenance
   is already flagged as its own surfaced topic (brainstorm 34). This is a developer decision,
   not something this topic can ratify unilaterally (open question 5 below).

## Open questions for the developer

1. **Ratify `language_kind`/`applies_to` as specified (O2c)?** In particular the asymmetric
   defaults — `language_kind` defaults to `general-purpose` (zero edits), `applies_to` defaults
   to `[general-purpose]` (also zero edits today, but the opposite polarity from brainstorm 30's
   `exclusivity` default) — or would the developer prefer a single consistent default-permissive
   posture across all these additive dimension-level fields for mental-model simplicity, even
   though it would be the wrong default here?
2. **Is `not-applicable` the right name for the fourth `no-record` reason**, or does it read as
   too close to `deferred` in casual use (both are "you won't find an answer here, and it's not
   a pipeline gap") such that the distinction (mechanically derived vs. developer-maintained)
   needs a more differentiated label, e.g. `out-of-scope-for-kind`?
3. **Should `domain` stay unconstrained free text, or does the developer want a closed
   vocabulary now** (`query | shell | config | build | markup | template`) even though only one
   candidate (SQL, `query`) currently exists? The recommendation above deliberately deferred
   this as premature taxonomy, but if the developer already has, say, a shell language or a
   build-config DSL in mind as the *next* DSL candidate, minting the vocabulary now might be
   cheaper than a later migration.
4. **Is O1c's case-by-case DSL-candidate scoping line acceptable**, or does the developer want a
   more mechanical rule now (e.g. "any language with a spec §title containing 'query language' or
   similar" — almost certainly overkill) to avoid relitigating "is X really a programming
   language" every time a borderline candidate (regex, HCL, jq) comes up?
5. **Greenlight the SQL vendor-dialect sourcing substitute** (recommendation item 6) — PostgreSQL
   docs or SQLite docs as tier-A/B backing in place of the paywalled ISO/IEC 9075, mirroring the
   Prolog/Deransart precedent — or does the developer want to keep pursuing the ISO text itself
   (university acquisition, as was available for Prolog) before SQL enters an actual onboarding
   phase?
6. **Does SQL onboarding get its own phase-5-style slot in D28's phased plan**, or does it enter
   whichever phase is current once both this topic's schema and item 5's sourcing question are
   settled? (No urgency — flagging only so it doesn't fall through a gap between two decision
   documents.)

## New brainstorm topics surfaced

- **Coverage-matrix N/A-cell visual treatment** — fold into topic 19/33 (already the designated
  home for coverage-matrix component UX per D33): the fourth cell state (`not-applicable`) needs
  a rendering distinct from all three of D32's existing empty states and from a filled `absent`
  cell; no new topic number needed, this is a direct extension of work already scoped there.
- **DSL sub-kind taxonomy** — whether `domain` needs to graduate from free text to a controlled
  vocabulary once a second DSL candidate is seriously proposed (open question 3 above). Not
  worth a standalone topic today with only one candidate on the table; worth a one-line note on
  this topic's own follow-up if/when a second DSL is proposed, rather than a new backlog number
  now.
- **Golden-set stratum for applicability misclassification** — a `language_kind`/`applies_to`
  value that's simply wrong (e.g. a dimension marked general-purpose-only that a DSL genuinely
  does have a coherent answer for) is a different failure mode from anything in D44's existing
  13-stratum perturbation taxonomy or topic 41's proposed absence-check strata — it's a
  taxonomy-authoring error, not a verification-pipeline error, so it likely belongs in an
  ordinary ontology-review/RFC checklist (D16) rather than the golden-set framework at all. Worth
  a one-line fold-in note wherever D16's RFC template next gets touched, not a new topic.
- **Spec-vs-implementation provenance for vendor-dialect DSL sourcing** — this topic's SQL
  recommendation (PostgreSQL/SQLite docs as tier-A/B backing instead of the paywalled ISO
  standard) is a concrete instance of the "several onboarded languages are defined by an
  implementation, not a standard" topic already surfaced by brainstorm 34 (Python/CPython,
  R/GNU R, Rust pre-FLS). No new topic needed — this is additional evidence for that
  already-backlogged item, worth noting when it's picked up.

## Sources

No new external sources introduced; all constraints trace to ratified decisions D1–D49 and to
brainstorms 09, 22, 30, 34, 38, 41 cited inline above.
