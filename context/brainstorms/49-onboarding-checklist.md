# 49 — Per-Onboarding-Cycle Tooling Checklist

> Backlog brainstorm for LangAtlas. Scope per the checklist: consolidate topic 19's
> Shiki-grammar-check and `syntax_check: parser | none` audit items with brainstorm 34's existing
> license/spec/Shiki per-language audit into one reusable "new language onboarding checklist"
> artifact, rather than scattering these checks across brainstorms 19, 34, and D28 as has happened
> so far. This is a consolidation task, not a from-scratch design — every individual check already
> exists, ratified, somewhere in decisions.md; the job is to give them one home and decide what
> kind of artifact that home is. Binding context: D28 (14-language, four/five-phase onboarding
> plan — Python/C/Java/Rust/Haskell/Prolog now onboarded as phase 1, C++/C#/JavaScript/R as
> phase 2, OCaml/Erlang/Go/Swift as phase 3, Visual Basic as optional phase 4, SQL as a
> not-yet-designed phase 5 per D50's amendment), D34 (brainstorm 34's per-candidate spec/license/
> Shiki audit table and phase structure), D33 (`syntax_check: parser | none` language-registry
> field and the missing-Shiki-grammar-becomes-a-checklist-item ruling, both already stated in
> brainstorm-19-derived prose as belonging here), D50 (`language_kind: general-purpose |
> domain-specific` on the Language record, gating whether `applies_to` dimension masks matter for
> a given language), D51 (`custom.grounding: formal-spec | reference-implementation-docs |
> design-doc | third-party-reference` on Source records, with a documented per-language
> resolution precedent for Python/R/Rust/TypeScript/SQL), D37 (locator grammar, extraction-QA
> harness, `custom.edition`/`edition_check_url`, `custom.canonical_source`/`acquisition_note`,
> all already-built ingestion-time machinery a new source must satisfy), D48 (the `tools/<domain>/`
> package convention — `tools/validate/`, `tools/coverage/` — and the regression-fixture
> convention this artifact should NOT try to imitate), D44/D52 (the `tools/coverage/report.py`
> shape, and the now-**cancelled** `ontology/exit-checklists/<source>.yaml` authored-artifact
> precedent — cancelled by the developer on 2026-07-19, so it is a naming precedent to avoid
> repeating literally, not a live pattern to extend). All proposals here are *proposed* until the
> developer ratifies.

## 1. Problem framing

Four ratified decisions each independently produced a piece of "things to check before/while
onboarding a new language," and none of them point at each other:

- **D34** (via brainstorm 34) ran a one-time audit table — spec availability, license/access
  class, ingestion cost, sweep cost, Shiki grammar presence — over the *initial* 14(+VB+SQL)
  candidates, as a **selection** exercise. Its table format is exactly checklist-shaped but was
  authored as a one-off spreadsheet-in-prose for a specific decision, not as a template meant to
  be re-run.
- **D33** (via brainstorm 19 §2.3) states, almost as an aside, that missing-Shiki-grammar risk
  for *future* (post-1.0) languages "becomes a per-onboarding-cycle checklist item... rather than
  a new site feature," and that `syntax_check: parser | none` is a registry field to set per
  language — but never says which document holds that checklist, or when in the onboarding
  sequence it's filled in.
- **D50** adds `language_kind`/`domain` classification and its `applies_to` compiler consequence
  as a decision that has to be made once, early, per language — currently living only in
  decisions.md prose, not in any per-language runbook.
- **D51** adds `custom.grounding` classification per source (and by extension, informally, per
  language — "does this language have a formal-spec or only reference-implementation-docs")
  with a documented resolution for five languages but no stated mechanism for resolving the
  *next* one.

None of these four decisions is wrong on its own terms — each is scoped correctly to the topic it
was ratified under. The gap is structural: **there is no single artifact a developer or agent
opens at the start of a language's onboarding and works through top to bottom.** Today, "onboard
language N" means separately remembering to: recheck brainstorm 34's audit table (which stops
covering the language the moment it's outside the original 14+VB+SQL candidate list), recheck
D33's aside about Shiki grammars, decide `language_kind`/`applies_to` from D50's prose, decide
`grounding` per source from D51's prose and its five-language precedent, and satisfy D37's
ingestion-time source-record requirements (`edition`, `canonical_source`, `acquisition_note`) —
five different documents, none of which cross-references the others by checklist item, all easy
to half-remember a year from now when SQL (D28 phase 5) or a genuinely new post-1.0 candidate
comes up.

The cost of *not* consolidating is concrete and dated: D28 already has an undesigned phase 5
(SQL) and an explicitly deferred backlog (TypeScript, Scheme/Racket, APL-family, Julia, Elixir)
that will need exactly this sequence re-run, plus D34 §Open questions already flags phase-3/4
gating and edition-repinning as recurring, not one-time, concerns. The research phase (D27) is
still mid-flight, so this is not urgent relative to phase-1 work already in progress — but it is
cheap to build now, while the shape of "what does onboarding a language actually require" is
still fresh from having just been assembled piecemeal across five decisions, and expensive to
reconstruct correctly from scratch once that context has faded.

## 2. What the checklist actually needs to contain

Pulling every scattered onboarding-relevant check found in decisions.md (not brainstorm prose —
decisions.md is the binding surface), in the order a developer or agent would naturally hit them:

1. **Selection sanity** (D28/D34 pattern, not literally re-run per language but the shape to
   follow for any *new* candidate beyond the ratified 14+VB+SQL): does this language pull its
   weight on landscape coverage, audience relevance, or both? Not a gate — D34's own Option D
   discussion shows popularity-only or diversity-only answers are both defensible — but a
   one-line justification the checklist should force someone to write down, mirroring D34's
   per-candidate "unique contribution" column.
2. **License / access class** (D34's audit column, generalized): what license governs the
   primary spec/reference source, and does it clear D14's private-TDM-indexing-is-fine-regardless
   / quotation-cap / no-bulk-copy bar? Record the license and access class explicitly rather than
   re-deriving D14's reasoning per language.
3. **Spec/formal-source availability, tied to D51's `grounding` field**: does this language have
   a `formal-spec` grounding, or only `reference-implementation-docs` / `design-doc` /
   `third-party-reference`? This is the item that ties directly to D51's per-language precedent
   table (Python/R → `reference-implementation-docs`; Rust → split by claim, FLS preferred;
   TypeScript → permanently `reference-implementation-docs`; SQL → vendor-dialect substitute,
   also `reference-implementation-docs`) — the checklist item is "resolve and record this
   language's grounding disposition before sweep start," not "re-litigate D51's rule."
4. **`language_kind` / `domain` classification (D50)**: `general-purpose` (the default, no
   action) or `domain-specific` (+ a `domain` tag, reusing an existing tag where one fits per
   D50's informal-vocabulary discipline)? This one-time classification decision gates whether
   `applies_to` dimension masks matter for this language's sweep — get it wrong and D46's
   questionnaire compiler either emits nonsensical sweep items or silently skips real ones.
5. **Shiki grammar availability (D33/D34)**: does `tm-grammars` bundle a grammar for this
   language? If yes, no action (true for all 14+VB+SQL per D34's audit). If no, the
   already-ratified fallback is plain-text highlighting — not a blocker, not a custom-grammar
   side project unless the developer chooses to do one.
6. **`syntax_check` mode determination (D33)**: does a fast, installable CLI syntax-check-only
   invocation exist for this language (`python -m py_compile`-class for interpreted languages,
   `-fsyntax-only`-class for compiled ones)? Set `syntax_check: parser` if yes (and confirm the
   fast offline validator suite has been wired for it), `syntax_check: none` if no (an accepted,
   indefinite state per D33's ratification — not conditioned on D50 settling first, and D33
   explicitly already resolved that "no automated check" is fine forever for languages like
   Prolog).
7. **Source-record ingestion fields (D37)**: for each primary source ingested — `custom.edition`
   (+ optional `edition_check_url`), `custom.canonical_source` (preferring the official
   publishing body) with its mandatory `custom.acquisition_note`, and confirmation the source
   clears the D37 extraction-QA harness (encoding/collapse hard-gate, outline-coverage soft
   report). These are mechanically enforced elsewhere (D37/D48's `validate-locator` and the
   ingestion CLI) but the checklist item is the *human* step: has this language's sources
   actually been run through ingestion at all yet, prerequisite to any sweep.
8. **Corpus/ingestion cost note** (D34's audit column, carried forward as a one-line record, not
   a re-derivation): rough size/complexity of the primary spec, informing scheduling but not
   blocking anything.
9. **Sign-off / phase placement**: which D28 phase (or, for anything beyond the ratified list, a
   new phase-N slot) does this language belong to, and does that phase's prerequisite phase
   already have a completed sweep (D28's ratified "later phases don't interleave" rule)?

Notably absent from this list, on purpose: nothing about combination-validation rules, edges, or
Rules (D2/D30/D50 all agree these are feature-graph-level, unaffected by which language is being
onboarded), and nothing about the sweep questionnaire's actual field list (D46 already owns
deriving that mechanically from the ontology — the checklist's job stops at "sources are ingested
and classified," D46's compiler takes it from there).

## 3. Options with trade-offs

### O1 — Pure documentation: a single markdown template, hand-copied per language

A file like `context/onboarding-checklist-template.md` (or, matching this project's existing
`context/` vs `ontology/` split, something living wherever the developer decides authored-but-
not-canonical-data artifacts belong — see §4) with the nine items above as a markdown checklist
(`- [ ]` syntax, per CLAUDE.md's existing plan-checkbox convention), copied to a new per-language
file and filled in by hand or by an agent each time a language is onboarded.

- Pros: zero engineering cost, ships today, trivially editable as the project's understanding of
  "what onboarding requires" evolves (which it clearly still is — D50/D51 both landed *after*
  D28/D34's original audit and each added a new checklist row). Matches D48's existing config
  file for validators reading fields the checklist would ask a human to set (`syntax_check`,
  `language_kind`, `custom.grounding`, etc.) — the checklist and the schema are separate concerns,
  not one artifact trying to be both.
- Cons: nothing enforces that the checklist was actually run, or run completely, before a sweep
  starts. A skipped item (e.g. forgetting to set `syntax_check`) fails silently — the registry
  field just keeps its default or stays unset until something downstream notices. No mechanical
  link between "checklist says done" and "registry actually reflects it."

### O2 — Validator-CLI-checked structured file, tying into D48's `tools/validate/` family

A structured YAML file per language (e.g. `ontology/languages/<lang>/onboarding.yaml`, or folded
directly into the existing language-registry record D33/D50/D51 already extend) with typed fields
mirroring the nine checklist items, checked by a new `langatlas-validate onboarding <lang>`
subcommand (or a check folded into the existing `precommit`/`ci` contracts) that fails if a
required field is missing or a Shiki-grammar/syntax-check-mode claim doesn't match what's
mechanically verifiable (e.g. cross-checking `syntax_check: parser` actually has a working CLI
invocation configured somewhere).

- Pros: closes O1's enforcement gap — a language can't reach "swept" status with an incomplete
  onboarding record, the same load-bearing-gate posture D24/D48 already apply to facts and
  locators. Fits the established `tools/<domain>/` shape (D48's own package, or a new sibling
  matching D44/D52's `tools/coverage/` precedent) rather than inventing a new mechanism.
- Cons: over-engineered relative to the actual cadence. D28 onboards languages in four ratified
  phases plus (per this session's D50 amendment) one undesigned SQL-shaped phase 5 — call it
  roughly 5–6 onboarding *events* total before 1.0, then whatever trickles in post-1.0 from the
  explicitly-deferred backlog (TypeScript, Scheme/Racket, APL-family, Julia, Elixir) at a pace
  nobody has estimated. Several of the nine items (selection sanity, cost note, sign-off/phase
  placement) are inherently narrative judgment calls, not machine-checkable facts — forcing them
  into a schema either produces an enum too coarse to be useful or a free-text field the validator
  can't meaningfully check anyway, and the "prove no cross-domain rule needed" bar D50 itself sets
  for schema additions (would a `challenge-fact.yml` on this cell make sense?) argues against
  minting new canonical-YAML fields for what is fundamentally a workflow runbook, not a content
  fact. It would also be the first `tools/validate/` check whose failure mode is "a human forgot
  a step" rather than "the corpus contains a structural defect" — a different risk category than
  everything else that gate currently guards.

### O3 — Hybrid: markdown template for judgment items + reuse of existing registry fields for the mechanically-checkable ones

Keep the checklist itself as O1's markdown template (narrative, human-run, cheap to evolve), but
for the subset of items that are *already* schema fields living on canonical records anyway
(`syntax_check`, `language_kind`/`domain`, `custom.grounding`, `custom.edition`/
`canonical_source`/`acquisition_note`) — don't duplicate them into a separate structured
checklist file at all. The checklist's job for those items is just "go set this field" with a
pointer to where; the *actual* enforcement (a language shouldn't reach sweep-ready without them
set) is either already covered by existing validators (D37/D48's `validate-locator` and
extraction-QA harness already gate source-record completeness) or, where it isn't yet covered
(nothing currently checks that `syntax_check`/`language_kind` got set at all, as opposed to being
correct once set), is a small, separately-scoped fold-in to D48's existing `precommit`/`ci`
contracts — a schema-completeness check on the language registry, not a new "onboarding" concept.

- Pros: avoids O2's category error (workflow runbook vs. content-integrity gate) while still
  closing its real enforcement gap for the items that matter mechanically. No new file format, no
  new validator subcommand family — a couple of new required-field checks slot into machinery
  D48 already owns. The narrative items (selection sanity, cost note, phase sign-off) stay in the
  cheap, human-editable markdown template where forcing structure would only produce a
  false-precision schema. Keeps the checklist itself genuinely reusable/copyable per D34's own
  audit-table format (which this option deliberately keeps as its ancestor) rather than
  reinventing the presentation.
- Cons: two places to look (the template for narrative items, the registry schema + validator for
  mechanical ones) instead of one — a small ongoing cost to whoever runs onboarding, mitigated by
  the template itself linking to the exact registry fields it's asking to be set.

## 4. Recommendation

**O3.** Ship one reusable markdown template, `ontology/onboarding-checklists/language-template.md`
(directory choice explained below), covering the nine items from §2 as a `- [ ]` checkbox list
per CLAUDE.md's existing checkbox-plan convention, copied to
`ontology/onboarding-checklists/<lang-id>.md` and filled in at the start of each language's
onboarding (D27 R3/R4/R5 cycle boundary, or D28's phase-boundary sign-off, whichever a given
onboarding is riding on). Items 4–7 (`language_kind`/`domain`, `custom.grounding`, Shiki-grammar
presence → `syntax_check`, D37 source fields) each link directly to the registry field they set,
rather than restating the field's semantics — the template is a *sequencing and completeness*
aid, not a second copy of the schema. Separately, fold one small addition into D48's existing
`tools/validate/` `precommit`/`ci` contracts: a required-field-presence check (not a correctness
check — that stays D24/D37's job) confirming every language in the registry that has reached
`not-yet-swept`-or-later status has `language_kind` and `syntax_check` set to *something* (not
necessarily the "right" something — that's still a human judgment call the checklist walks
through), closing O1's silent-skip gap for exactly the two fields where a missing value would
otherwise fail invisibly downstream (an unset `syntax_check` looks identical to a deliberate
`none`; an unset `language_kind` breaks D46's compiler silently rather than loudly).

**Directory choice.** Not `ontology/exit-checklists/` — that precedent existed only as a proposed
brainstorm-44 deliverable and was explicitly **cancelled** by the developer on 2026-07-19 (see
D52's dated amendment); reusing its name would misleadingly suggest a live convention that no
longer exists. `ontology/onboarding-checklists/` is chosen instead because: (a) it sits alongside
this project's other small authored-but-not-generated `ontology/` artifacts (e.g.
`ontology/claim-templates/`, D52's `research/reality-checks/<cycle>-<theme>.yaml` precedent for
"small named YAML/markdown artifact living near, but distinct from, the canonical content
directories"), and (b) it is explicitly *not* under `tools/<domain>/` (D48/D44/D52's convention)
because it is not a CLI package — it has no `cli.py`, no importable library, nothing to dispatch;
putting a markdown template inside `tools/` would misrepresent it as code.

This also directly answers the brainstorm's own framing question ("is this a static template
file, a validator-CLI-checked structured file, or pure documentation?"): it's neither purely O1
nor fully O2 — it's O1's artifact shape with a narrowly-scoped borrowing from O2's enforcement
idea, applied only where an existing validator family can absorb it cheaply.

### Worked example — Rust (D28 phase 1)

Filled-in illustration, `ontology/onboarding-checklists/rust.md` (values as ratified/recorded in
D28/D34/D51, i.e. this is what the completed checklist for an already-onboarded language would
look like, not a live TODO):

```markdown
# Onboarding checklist — Rust (`rust`)

- [x] Selection sanity: phase-1 ontology-stress-set member (D28) — ownership/trait system,
      largest-surface concurrency-vocabulary contribution among phase-1 languages.
- [x] License/access: Reference + Ferrocene Language Specification, MIT OR Apache-2.0, free
      (Rust Project 2026) — clears D14 without qualification.
- [x] Grounding (D51): split by claim — Ferrocene FLS (`formal-spec`) preferred wherever it
      covers a claim; Rust Reference (`reference-implementation-docs`) otherwise. Sweep-agent
      instruction, not schema-enforced per-claim.
- [x] `language_kind` (D50): `general-purpose` (default, no `domain` tag).
- [x] Shiki grammar: `rust` present in `tm-grammars` (D34 audit) — no fallback needed.
- [x] `syntax_check`: `parser` — `rustc --edition ... -Zparse-only`-class front-end-only check
      available; wired into the D13/D48 offline validator suite.
- [x] D37 source-record fields: `custom.edition` set per source; `custom.canonical_source` /
      `acquisition_note` recorded at R1 retroactive pass (D37, phase-1 scope per D51's own
      retroactive-pass note).
- [x] Ingestion cost note: low–medium (Reference + FLS, well-structured, free).
- [x] Phase placement: D28 phase 1, sweep-ready once phase-1 ingestion QA clears.
```

## 5. Open questions for the developer

1. Confirm the directory choice (`ontology/onboarding-checklists/`) over alternatives — e.g.
   nesting the template under `context/` instead, given it's arguably closer in spirit to a
   process document than to ontology content; or attaching it directly inside each language's
   existing registry record directory once one exists.
2. Confirm the narrow D48 fold-in (required-field-presence check for `language_kind` and
   `syntax_check` only) is worth the small addition, versus leaving both as O1's fully-manual,
   unenforced template items — the failure mode being guarded against (a silently-unset field
   breaking D46's compiler or producing a false "no check" state) has not yet actually happened,
   since D28 phase 1 is still the only completed onboarding.
3. Should the template's item 1 ("selection sanity") stay purely narrative, or does it warrant
   pulling in D34's original per-candidate audit-table columns verbatim as a reusable sub-table
   format, for whenever a genuinely new (non-D28-list) candidate is proposed via D32's
   `request-language.yml` issue form?
4. Timing: build this now (cheap, and the shape is fresh from this consolidation pass) or defer
   until closer to D28 phase 2/3, given phase 1 is the only onboarding that has actually
   happened and every item in §2 was in practice figured out ad hoc for it without a template?

## 6. New brainstorm topics surfaced

None.
