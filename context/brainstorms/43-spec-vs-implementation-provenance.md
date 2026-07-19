# 43 — Spec-vs-Implementation Provenance

> Backlog brainstorm for LangAtlas. Topic: distinguishing "the spec says" from "the reference
> implementation does" for implementation-defined languages (Python, R, Rust pre-FLS,
> TypeScript), tier assignment per case, and a design-doc source class (RFCs/PEPs/JEPs) with
> locator conventions. Binding context: D3 (source quality tiers A–D and the CSL-JSON-as-YAML
> source record, `custom` key for LangAtlas extras); D4/D24 (the claim↔source verification
> pipeline — six-verdict ladder, entailment over decomposed atomic assertions, admissibility =
> ≥1 `supported` tier-A/B citation); D25 (confidence as tier × corroborating-source-count,
> controversy score); D37 (`custom.canonical_source`/`custom.acquisition_note` — the mirror-vs-
> canonical distinction this topic's spec-vs-implementation distinction sits directly next to);
> [brainstorm 34](34-initial-language-selection.md) (D28's 14-language set; the per-candidate
> spec table that first named Python/CPython, R/GNU R, Rust pre-FLS, and TypeScript's missing
> spec as open problems, and surfaced this topic verbatim); [brainstorm 42](42-dsl-in-ontology.md)
> (D50 *proposed*; the SQL vendor-dialect recommendation — PostgreSQL/SQLite docs standing in
> for the paywalled ISO/IEC 9075 — named as "a concrete instance of" this topic's pattern and
> explicitly deferred here). All proposals below are *proposed*, not ratified, per the project's
> decision-hygiene convention.

## Problem framing

D3 gives every source a single intrinsic quality tier (A peer-reviewed/spec, B official docs/
textbook, C talks/community references, D blogs/popularity indexes) and D25 derives a fact's
confidence from the strongest admissible tier among its citations plus corroborating-source
count. That model has an implicit assumption baked in: that "the spec" and "the docs of the
canonical implementation" are two points on the *same* quality ladder, differing only in how
authoritative they are, the way a peer-reviewed paper outranks a blog post. For a genuine
standards body language — C's ISO/IEC 9899, C++'s ISO/IEC 14882, ECMA-262, the JLS — that
assumption holds: there is one normative document, and everything else (compiler docs, books,
blogs) is downstream commentary on it, correctly tiered by how carefully it explains what the
spec already fixed.

Several of D28's onboarded and gap-filler languages break that assumption in a different way,
already flagged in brainstorm 34's per-candidate table:

- **Python**: "The Python Language Reference" (PSF-2.0, free HTML) exists and is tier-A/B by
  D3's letter, but it is famously incomplete and in places aspirational — CPython's actual
  behavior (reference-counting semantics, GIL interactions, dict ordering before it was
  specified, C-API-adjacent edge cases) has repeatedly been the *de facto* answer where the
  Language Reference is silent or vague. PEPs are Python's design-decision record, not a spec —
  brainstorm 34 explicitly calls them "design docs, not a complete language spec."
- **R**: the R Language Definition (CRAN manual) is R's only reference-manual-class document,
  but R's actual behavior is defined by GNU R's C/R source and its `NEWS`/changelog; there is no
  separate standards body at all — "R is defined by GNU R" is brainstorm 34's own framing.
- **Rust**: the Rust Reference explicitly disclaims being a formal spec; the Ferrocene Language
  Specification (FLS) is the first document that *is* one, and it postdates most of Rust's
  history (Rust 1.0 shipped 2015; FLS work began circa 2022–2023 for safety-certification
  purposes). Every fact about Rust's behavior before the FLS existed — and arguably every fact
  about a Rust edition the FLS hasn't caught up to — is grounded in "the reference compiler is
  the spec," in the language's own community's phrasing.
- **TypeScript**: there is no separate specification body at all (an early spec draft was
  archived years ago and never resumed); the Handbook and the compiler's own observable behavior
  *are* the only ground truth, permanently, not just historically. This is a stronger version of
  the Rust case: there is no future FLS-equivalent moment where the gap closes.
- **SQL, by extension** (brainstorm 42/D50, not re-litigated here): the *general standard* is
  ISO/IEC 9075, paywalled with no free draft; the practical sourcing plan is PostgreSQL or
  SQLite's own documentation — a **vendor dialect's implementation docs standing in for the
  standard**, the same shape of problem, just triggered by an access/cost blocker rather than a
  "the spec doesn't fully exist" blocker.

Three distinct sub-problems, worth separating cleanly because they don't all want the same fix:

1. **A tier-only model can't express "spec-grounded" vs. "implementation-grounded" as anything
   other than a quality difference**, when for these languages it usually isn't one — CPython's
   documented behavior is not *lower-quality* evidence about what Python does than the Language
   Reference; for many claims it's the *more* reliable evidence, because it's what the Language
   Reference itself is trying (and sometimes failing) to describe. Tier answers "how much do we
   trust this document's care and authority," not "does this document constitute a fixed,
   contractual definition of the language, or a description of one implementation's current
   choices" — two orthogonal questions D3 currently conflates into one field.
2. **Design-doc genre (RFCs/PEPs/JEPs/TC39 proposals) is neither a spec nor implementation
   docs**, and doesn't fit either bucket cleanly. A PEP records *why* a decision was made and
   what was debated — genuinely useful, often the *only* citable source for "this feature exists
   because of trade-off X," a distinctly valuable evidentiary role — but citing "PEP 634 says
   pattern matching works this way" is a different epistemic claim than citing "the Language
   Reference §6.14 says pattern matching works this way," even when they agree, because a PEP is
   a point-in-time design proposal that may have been amended, superseded, or partially
   implemented differently than proposed.
3. **D4/D24's verification pipeline currently has no way to weight "this claim could change in
   next Tuesday's point release" differently from "this claim is fixed until the next MAJOR
   ontology-adjacent spec revision."** A claim sourced only to observed CPython 3.13 behavior is
   verifiably true today and is a meaningfully different kind of claim from one sourced to JLS
   §15.28 — not because the entailment check differs (the verifier still checks "does the source
   text support this claim," mechanically identical either way) but because of what happens
   *after* verification: whether the claim should be flagged more aggressively for the D25
   staleness/re-verification machinery when its source's next edition ships, and whether a
   contributor's "is this still true in the new release" challenge should be treated as routine
   maintenance rather than a genuine dispute.

The core design questions from the task brief, restated against this framing: does the spec-vs-
implementation distinction belong on the Source record (D3), on the Fact/claim (which already
carries `sources:` per D23), or split across both? Does design-doc genre need its own source
type and locator convention? And does D4/D24 need to treat implementation-grounded claims
differently at verification time, or only downstream of it?

## Options with trade-offs

### O1 — Where does the spec-vs-implementation distinction live: Source, Fact, or both?

**O1a — Source-record field only.** Add a field to the Source record's `custom` block (parallel
to D37's `custom.canonical_source`) classifying *what kind of document this is*:
`grounding: formal-spec | reference-implementation-docs | design-doc | third-party-reference`.
A fact's grounding is then read off whichever source(s) back it.

- Pros: one field, one place to look, consistent with D37's precedent of adding classification
  metadata to the source record rather than duplicating it per-citing-fact; a source's
  documentary genre doesn't change per claim, so it belongs on the thing that's intrinsically
  true about the document, not on every fact that happens to cite it (avoiding the redundancy
  D23's whole per-field-fact model works hard to avoid elsewhere).
- Cons: a single source can, in principle, serve both roles depending on which sentence is
  cited — a book like Klabnik & Nichols's *The Rust Programming Language* is squarely
  reference-implementation-docs-in-spirit for most claims, but might quote the Reference or FLS
  verbatim in places. In practice this is rare enough (most of D28's per-language corpus is one
  canonical spec/reference-manual-class source, matching D15/D28's "one primary spec source per
  language" ingestion pattern) that it's a tolerable edge case, not a real objection — flagged
  as a known limitation rather than grounds for rejecting O1a.

**O1b — Fact-level field only.** Add `grounding:` to each fact's citation entry
(`sources: [{source, locator, quote, grounding}]`) rather than to the Source record, so the same
claim could in principle mix a formal-spec citation and a reference-implementation citation with
different `grounding` values on each.

- Pros: theoretically most precise — captures the (rare) mixed-citation case exactly.
- Cons: redundant for the overwhelming majority case (one source, one grounding, repeated on
  every fact that cites it) — exactly the anti-pattern D20/D23 already solved once by moving
  fact granularity to per-field records with derived ids rather than duplicating metadata
  per-claim. Also wrong home conceptually: whether a document is a spec or implementation docs
  is a property of the *document*, not of the *claim citing it* — a fact doesn't make a source
  more or less authoritative by citing it.

**O1c (recommended) — Source-level `grounding` field (as O1a), with a derived, not authored,
fact-level rollup.** `grounding` lives on the Source record only, exactly as O1a proposes. At
build time, each fact's *effective grounding* is computed as the union of its citations'
`grounding` values (typically one value, since typically one primary source per language) and
exposed as a read-only derived field alongside D25's other derived axes
(`verification`/`freshness`/`dispute`) — call it `basis`, matching the "one more orthogonal
axis" shape D25 already established, not a new lifecycle state, just a new label. This gives O1b's
mixed-citation precision for free at the one point it's actually consumed (fact rendering, MCP
`caution` block) without authoring redundancy anywhere.

**Recommendation: O1c.** It's the natural extension of the existing D25 "orthogonal axes,
computed not authored" pattern (verification/freshness/dispute already work exactly this way),
costs one field on the Source record (near-zero — same shape as D37's `canonical_source`), and
sidesteps the redundancy O1b would introduce.

### O2 — The `grounding` vocabulary itself

Candidate values, informed by brainstorm 34's four flagged cases plus brainstorm 42's SQL case:

- `formal-spec` — a standards-body document with a defined amendment process (ISO/IEC 9899, JLS,
  ECMA-262, the Haskell 2010 Report, the Ferrocene FLS once/where cited for post-FLS Rust facts).
- `reference-implementation-docs` — documentation of one canonical (often the *only*, or
  overwhelmingly dominant) implementation's observed behavior, treated by its own community as
  the practical ground truth in the absence of (or gaps in) a formal spec: CPython's Language
  Reference + CPython's own behavior/changelog, the R Language Definition + GNU R's behavior, the
  Rust Reference (pre-FLS-relevant claims, or post-FLS claims about behavior the FLS doesn't yet
  cover), the TypeScript Handbook + `tsc`'s observed behavior.
- `vendor-dialect-docs` — documentation of *one vendor's* implementation of a language that *does*
  have a formal, independent standard elsewhere, cited as a practical substitute because the
  standard is inaccessible (paywalled, no free draft) rather than because no standard exists:
  PostgreSQL/SQLite docs standing in for ISO/IEC 9075 (brainstorm 42's SQL case), Deransart et al.
  (1996) or the SWI-Prolog manual standing in for ISO/IEC 13211-1 (D28's already-ratified Prolog
  precedent). Distinguished from `reference-implementation-docs` by *why* the substitution
  happened — the R28/D50 corpus already treats these as parallel cases, and the distinction
  matters for a contributor reading the citation: "SQL genuinely has one true, purchasable
  standard behind this substitute" is a different disclosure than "Python genuinely has no fuller
  formal spec than this."
- `design-doc` — RFCs, PEPs, JEPs, TC39 proposals, Rust RFCs: process/decision records, addressed
  fully in O3 below.
- `third-party-reference` — everything else already covered by D3's tier system without needing a
  grounding value at all: books, blog posts, community wikis. Default value when a source is
  none of the above; existing tiers (mostly B/C/D) already capture their authority correctly, so
  `grounding` for this bucket is mostly inert metadata, not a working field — included in the
  enum for completeness rather than because it changes downstream behavior.

Each `grounding` value is **orthogonal to D3's tier**, not a replacement for it — a
`reference-implementation-docs` source can still be tier A or B (the CPython documentation is
tier-A/B-quality prose; it just isn't a formal spec) and a `formal-spec` source is not
automatically tier A if it's a weak/dated one. This is the load-bearing design choice of this
whole brainstorm: **tier answers "how carefully was this written and how authoritative is its
publisher," `grounding` answers "what kind of authority does it actually carry over the
language's true behavior."** The two questions look similar but diverge exactly in the cases
this topic exists to address — a CPython behavior note in the official docs can be simultaneously
tier B (official docs, not peer-reviewed/spec by D3's letter) *and* the single most reliable
grounding available for a claim about Python's actual semantics, which is precisely the
information a tier-only model can't express.

### O3 — Design-doc source class: own type, or `grounding: design-doc` plus locator convention?

Two questions bundled in the task brief: does design-doc get its own *source type/tier*, and
does it need its own *locator convention*.

**On source type/tier**: `grounding: design-doc` (from O2) already gives design docs their own
classification without needing a fifth D3 tier or a parallel type system. Tier assignment for a
design doc follows D3's existing letter unmodified — PEPs/JEPs/accepted Rust RFCs/finalized TC39
proposals are official project-published documents, squarely **tier B** (official
docs/textbook-class — a PEP is exactly as "official" as the Language Reference it complements,
just a different genre of official document); an unaccepted/withdrawn/still-in-flight proposal
drops to **tier C** (community reference — it documents a live discussion, not a settled
project position) until it's finalized. No new tier letter needed; this is squarely a
`grounding`-axis question, not a tier-axis one, reinforcing O2's orthogonality argument.

**On locator convention**: design docs need a locator grammar entry the existing D23/D37 grammar
(shared with brainstorm 21's chunk table, per D23) doesn't yet have a natural slot for — most
existing locator kinds (`p.`, `§`, URL `#fragment`, commit SHA + line range) assume either a
paginated document or a live repository file; a PEP/JEP/RFC is neither, it's a numbered,
individually-URLed, section-structured document. Recommended locator shape, added as one more
row in the existing grammar table (owned by whichever brainstorm/topic holds the canonical
grammar — brainstorm 09/D23, per this file's binding context):

```
design-doc  ::=  <doc-kind> <number> ["§" <section>]
doc-kind    ::=  "PEP" | "JEP" | "RFC" | "TC39-proposal" | ...
```

e.g. `PEP 634 §Overview`, `JEP 440 §Description`, `Rust RFC 2071 §Summary`. This mirrors the
existing `§` convention already used for spec section locators, keeping the grammar's shape
familiar rather than inventing a new locator style. `doc-kind` is deliberately an open,
documented-by-convention string (matching the way `source type` in CSL-JSON already accepts
project-specific values) rather than a closed enum — new design-doc families (Go proposals,
Swift Evolution proposals) will keep appearing as new languages onboard, and a closed enum would
need a schema-migration edit for each one, disproportionate for a purely cosmetic locator prefix.
The design doc's own canonical numbered/permalinked URL (`peps.python.org/pep-0634/`,
`openjdk.org/jeps/440`, the Rust RFC repo's file path at a pinned commit) is the source record's
`URL`, archived per D3's existing Wayback-on-mint policy — no change needed there.

### O4 — Interaction with D4/D24's verification pipeline

The task brief asks specifically whether an implementation-grounded claim needs different
verification handling than a spec-grounded one. Two places this could bite: the entailment
*check itself*, and what happens *after* a passing verdict.

**At verification time**: no change needed. D24's six-verdict ladder (`source-unavailable |
locator-not-found | supported | partial | unsupported | contradicted`) and its entailment stage
already operate purely on "does the cited source text support this claim" — that question is
identical in shape whether the source is a formal spec or CPython's docs; the verifier reads
`source_chunks`, resolves the locator, and checks entailment exactly the same way regardless of
`grounding`. Building a second verification code path keyed on `grounding` would duplicate D24's
already-calibrated machinery for no accuracy gain — the grounding classification says something
about the *nature of the fact*, not about how hard it is to check whether a document supports a
sentence.

**One narrow exception worth naming explicitly**, because it's the one place `grounding`
plausibly *should* touch verification logic: a `design-doc`-grounded claim about **current**
language behavior (as opposed to a claim about *why a design decision was made*, which a design
doc is always the right source for) risks the citation-laundering-adjacent failure of citing a
proposal's *stated intent* for a feature that shipped differently than proposed. This is not a
new verifier mechanism — it is already covered by D24's existing atomic-decomposition +
per-assertion entailment: if the claim asserts current behavior and the design doc's text only
supports "this was proposed," the entailment check already fails that assertion on its own terms
(the source text doesn't support the overstated claim), the same `partial`/`unsupported`
distinction D24 already draws for every other overstated-claim pattern. Named here as a
reason to make sure the D44 golden-set's overstated-claim stratum includes at least one
design-doc-sourced example, not as a new pipeline requirement.

**After verification, at the D25 status-axis layer**: this is where `grounding` earns its keep.
Two concrete, additive hooks, both extending existing D25/D37 machinery rather than inventing new
states:

1. **Freshness/staleness weighting.** D25's re-verification triggers already include
   source-snapshot drift and edition supersession (D37). A `reference-implementation-docs`- or
   `vendor-dialect-docs`-grounded claim is drawn from a document whose "edition" (the
   implementation's version) changes far more often than a `formal-spec`-grounded claim's
   document (a spec revision is a rare, deliberate event; a point release is routine and
   frequent). Recommend: D37's existing quarterly edition-check job treats
   `reference-implementation-docs`/`vendor-dialect-docs` sources with a shorter check interval
   than `formal-spec` sources by default (a config default keyed on `grounding`, not a new job) —
   this is a scheduling-cadence tweak to an already-built mechanism, not new pipeline surface.
2. **Contributor-facing disclosure.** The site's per-fact citation popover (D10/D33's trust-signal
   UX, already extended once by D42/D45 for licensing and contradiction clauses) gets one more
   plain-text line when `basis` (O1c's derived rollup) is anything other than `formal-spec`:
   something in the shape of "Sourced from [Python]'s reference implementation's documented
   behavior, not a formal language specification" — matching the existing "extend the popover
   with one more plain-text clause" pattern rather than new page chrome, and directly serving
   D9's "trivially challengeable by human experts" mandate: a Python expert reading "this is
   CPython's documented behavior, not a spec clause" knows exactly what kind of correction would
   land (a counter-citation to the same kind of evidence) versus what kind wouldn't (disputing a
   settled spec clause is a different, harder argument).

Neither hook changes admissibility (D24's `≥1 supported tier-A/B citation` rule is untouched —
`grounding` never gates whether a claim can enter the canonical store, only how it's scheduled
for recheck and how it's disclosed) and neither introduces a new D25 axis with its own precedence
rules — `basis` stays a descriptive/derived label, not a fifth orthogonal status axis competing
with verification/freshness/dispute for display precedence.

### O5 — Concrete per-language resolution

Walking the task brief's named cases against O1–O4:

- **Python/CPython**: primary source stays the Python Language Reference (PSF-2.0, tier B per
  D28's existing table), `grounding: reference-implementation-docs` — not `formal-spec`, despite
  its name, because it is explicitly non-normative in places and the community treats CPython's
  actual behavior as the tiebreaker. Where a claim needs to cite CPython behavior the Language
  Reference doesn't cover (e.g. a specific GIL interaction, an implementation-detail-adjacent
  ordering guarantee), the CPython `Doc/` reference chapters and, if needed, `What's New in
  Python X.Y` changelog entries are additional `reference-implementation-docs` sources at the
  same tier. PEPs cited for *design rationale* claims ("Python adopted structural pattern
  matching because of X") get `grounding: design-doc`, tier B once accepted/final.
- **R/GNU R**: primary source is the R Language Definition (CRAN manual, tier B per D28),
  `grounding: reference-implementation-docs` — there is no separate standards body, so this is
  the R case in its purest form; no `formal-spec` document exists for R at all, unlike Python
  where the Language Reference at least aspires to the role.
- **Rust pre-FLS vs. post-FLS**: this is the one case where `grounding` should vary *by claim*,
  not just by source, because Rust genuinely has two eras. The Rust Reference (tier B,
  `grounding: reference-implementation-docs`, explicitly self-described as non-normative) backs
  claims about behavior the FLS doesn't cover or that predate the FLS's scope. The Ferrocene
  Language Specification (tier A once cited — a genuine formal spec with a defined change
  process, `grounding: formal-spec`) backs claims it explicitly covers. Because D28 already
  pins "the latest available edition" per language and re-pins on new editions, the practical
  rule is: **prefer an FLS citation over a Rust Reference citation whenever the FLS covers the
  claim**, falling back to the Reference (with its weaker `grounding`) only for FLS gaps — a
  sweep-agent instruction, not a schema mechanism, since the schema already supports either
  choice correctly once `grounding` exists.
- **TypeScript**: still deferred per D28 (no normative spec named as its deferral reason) — this
  topic doesn't reopen that deferral, but resolves what its *eventual* sourcing would look like:
  the TypeScript Handbook, `grounding: reference-implementation-docs`, tier B, with `tsc`'s own
  observed compiler behavior as a secondary corroborating source for claims the Handbook doesn't
  fully specify (structural/gradual typing edge cases especially). Unlike Rust, there is no
  future moment this graduates to `formal-spec` — TypeScript's `basis` stays
  `reference-implementation-docs` permanently, which is itself useful, stable information for the
  site's disclosure line (O4 hook 2) rather than a temporary placeholder.
- **SQL (vendor-dialect case, from brainstorm 42/D50)**: distinguished from the other four by
  `grounding: vendor-dialect-docs` rather than `reference-implementation-docs` — the PostgreSQL or
  SQLite documentation isn't standing in for *the absence of a spec* (ISO/IEC 9075 genuinely
  exists and is purchasable, per D28's Prolog precedent) but for *inaccessibility* of the spec
  LangAtlas has chosen not to acquire yet. This is the concrete instance brainstorm 42 flagged as
  needing this topic's machinery; D50's SQL recommendation is otherwise unchanged by this
  brainstorm, only now expressible in schema (`grounding: vendor-dialect-docs`) rather than only
  in prose. Prolog's existing Deransart et al. (1996) sourcing is `grounding: formal-spec`
  (it's an ISO-standard-adjacent reference manual co-authored with the standard's editors, not a
  vendor's own docs) — worth noting as a *don't* for the SQL case: SQL's situation is
  `vendor-dialect-docs` specifically because PostgreSQL/SQLite are independent implementations
  documenting their own dialects, not a book documenting the standard itself.

## Recommendation

*Proposed* package, extending D3 without touching D4/D24's admissibility rule:

1. **New Source-record field, `custom.grounding`** (O1c): one of `formal-spec |
   reference-implementation-docs | vendor-dialect-docs | design-doc | third-party-reference`,
   orthogonal to D3's existing tier — tier answers document quality/authority, `grounding`
   answers what kind of authority the document holds over the language's true definition.
   Default `third-party-reference` (matching the "additive field, existing sources need no
   audit" discipline D37/D39/D50 all follow) with a **one-time retroactive pass** classifying the
   D28 phase-1 corpus's primary spec/reference sources at ingestion time, mirroring D37's own
   "R1 initial-corpus ingestion gets a one-time retroactive pass" precedent for
   `canonical_source`/`acquisition_note`.
2. **Derived, not authored, per-fact `basis` rollup** (O1c): computed at build time as the union
   of a fact's citations' `grounding` values, joining D25's existing display-derived-axes family
   (verification/freshness/dispute) as a descriptive label — never a fifth axis with its own
   display precedence, never gating admissibility.
3. **No new tier letter for design docs** (O3): `grounding: design-doc` classifies them; tier
   assignment follows D3's existing letter unmodified (B once accepted/final, C while in-flight).
4. **New locator grammar row for design docs** (O3): `<doc-kind> <number> ["§" <section>]`
   (`PEP 634 §Overview`, `JEP 440`, `Rust RFC 2071 §Summary`), `doc-kind` an open documented
   string, added to the existing shared locator grammar (brainstorm 09/D23's table) alongside the
   existing `p.`/`§`/URL-fragment/commit-SHA kinds.
5. **No change to D4/D24's entailment mechanism** (O4): the existing six-verdict ladder and
   atomic-decomposition entailment already handle implementation-grounded and design-doc-sourced
   claims correctly by construction; the one worth watching (a design doc's stated intent cited
   for current behavior) is already caught by existing overstated-claim handling, flagged only as
   a D44 golden-set coverage note, not a new mechanism.
6. **Two additive downstream hooks keyed on `grounding`/`basis`** (O4): a shorter default
   edition-check interval for `reference-implementation-docs`/`vendor-dialect-docs` sources
   (D37's existing job, config-tuned, not rebuilt), and one added plain-text disclosure line in
   the existing citation popover when `basis` isn't `formal-spec` (D10/D33's existing popover
   pattern, extended the same way D42/D45 already extended it).
7. **Per-language resolution** (O5): Python and R get `reference-implementation-docs` on their
   primary sources (PEPs get `design-doc`); Rust splits by claim between the Reference
   (`reference-implementation-docs`) and the FLS (`formal-spec`), preferring the FLS wherever it
   covers a claim; TypeScript's eventual sourcing (still deferred by D28) is pre-resolved as
   permanently `reference-implementation-docs`; SQL's brainstorm-42-recommended vendor-dialect
   substitute gets its own value, `vendor-dialect-docs`, distinguishing "spec exists but is
   inaccessible" from "no fuller spec exists at all" — the two failure modes this topic set out
   to tell apart.

This keeps the fix scoped to what D3/D25/D37 already do (one additive source-classification
field, one derived rollup, two config-level hooks on existing jobs) rather than growing a
parallel verification or tiering system, and it gives brainstorm 42's SQL recommendation and
D28's Prolog precedent a shared, named vocabulary instead of leaving each as one-off prose.

## Open questions for the developer

1. **Ratify the `grounding` vocabulary as specified** (`formal-spec | reference-implementation-
   docs | vendor-dialect-docs | design-doc | third-party-reference`) — or does the developer want
   `vendor-dialect-docs` folded into `reference-implementation-docs` (accepting that "spec exists
   but paywalled" and "no fuller spec exists" collapse into one disclosure), given only SQL
   currently needs the distinction and Prolog's resolved precedent doesn't?
2. **Retroactive classification scope**: should the one-time retroactive `grounding` pass (item 1
   of the recommendation) cover only D28 phase-1's six languages at first ingestion, or the full
   14-language set up front, given phases 2–4 haven't started sweeping yet and their sources
   aren't ingested yet either? (Likely resolves itself by ingestion order regardless of what's
   decided here — flagged so it isn't silently assumed.)
3. **Design-doc `doc-kind` vocabulary governance**: is an open, undocumented-enum string
   (O3's recommendation) acceptable indefinitely, or does the developer want a lightweight
   registered list (`docs/design-doc-kinds.md` or similar) the moment a second or third kind
   beyond PEP/JEP/Rust-RFC actually gets cited, purely for locator-rendering consistency (e.g.
   deciding whether Swift Evolution proposals get cited as `SE-<number>` or `Swift-Evolution
   <number>`)?
4. **Edition-check interval tuning** (recommendation item 6, first hook): is a flat "shorter
   interval for non-formal-spec groundings" acceptable, or does the developer want the interval
   to vary further by how fast-moving the specific implementation actually is (CPython's roughly
   annual release cadence vs. a rolling-release tool), which would need a second config
   dimension beyond `grounding` alone?
5. **Popover disclosure wording** (recommendation item 6, second hook): is the draft phrasing
   ("Sourced from [Python]'s reference implementation's documented behavior, not a formal
   language specification") acceptable as a v0 template, or does the developer want to review
   final wording alongside D33/D42's other popover-clause additions as one batch before any of
   them ship, to keep the popover's growing clause list visually/tonally consistent?
6. **Rust's per-claim FLS-preference rule** (O5): is "prefer FLS whenever it covers the claim,
   fall back to the Reference otherwise" acceptable as a sweep-agent instruction only (no schema
   enforcement), or does the developer want a mechanical check (e.g. flagging any Rust claim
   sourced only to the Reference for a manual "does the FLS now cover this" recheck on a fixed
   cadence, given the FLS is actively growing post-2026)?

## New brainstorm topics surfaced

- **Locator-grammar consolidation pass** — this topic adds one new row (`design-doc`) to the
  shared locator grammar first specified in brainstorm 09/D23 and already extended informally by
  D37 (URL-kind pinning) and this topic; no standalone brainstorm needed, but worth a one-line
  fold-in note wherever brainstorm 09's grammar table is next touched (e.g. alongside topic 40's
  validator work, since `validate_locator_shape` is the mechanical enforcement point) so the
  grammar table doesn't end up documented across four separate brainstorm files with no single
  canonical listing.
- **`grounding`-aware edition-check cadence as a general config axis** — this topic's
  recommendation item 6 (shorter default interval for non-formal-spec sources) is a narrow
  instance of a more general question D37 left implicitly flat (one quarterly cadence for every
  source regardless of how fast its underlying document actually changes). Not worth a dedicated
  topic on its own evidence (one config default, tunable later without a design session), but
  worth folding into topic 28/D37's next revision if the developer ever wants a fuller
  per-source-type cadence model rather than the binary split proposed here.

## Sources

No new external sources introduced beyond what brainstorms 09, 34, 37, 42 and their cited
references already establish (PSF, R Core Team, Rust Project/Ferrocene, Ecma International, ISO,
PostgreSQL/SQLite documentation, Deransart et al. 1996 — see [brainstorm 34](34-initial-language-selection.md)'s
Sources section for full bibliographic entries). The Ferrocene Language Specification itself is
worth a first citation here as it wasn't separately listed in brainstorm 34's table:

- Ferrous Systems / Ferrocene (2026). *The Ferrocene Language Specification.*
  https://spec.ferrocene.dev/
