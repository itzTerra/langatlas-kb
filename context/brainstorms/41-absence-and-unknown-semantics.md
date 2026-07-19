# 41 — Absence & Unknown Semantics

> Backlog brainstorm for LangAtlas. Topic: `status: absent` vs. missing FeatureInstance record
> across the site, MCP, and future Builder validation; the existence/definition fact type's
> schema and verification semantics, specifically for *negative* claims. Binding context: D23/
> topic 09 (FeatureInstance schema — `status: present | absent | partial`, "absence is a sourced
> fact, not a skip," missing file = unknown/not-yet-swept; the `instance-exists` canonical-claim
> template; two-part fact identity); D46/topic 38 (the questionnaire compiler emits a sweep item
> for every candidate feature regardless of expected presence — language-agnostic, no per-language
> filtering, because filtering would make the compiler render a pre-evidence judgment call about a
> language, "contradicting D23's absence is a sourced fact, not a skip principle" — the ratification
> note that is this topic's direct trigger); D25 (three orthogonal status axes, confidence lookup
> from source tier × corroboration count, controversy score); D32 (the `/coverage/` page's three
> empty-cell states — not-yet-swept / not-yet-onboarded / deferred — and its "every empty cell is a
> real, well-scoped unit of work" framing); D33 (coverage-matrix component UX, the single shared
> status glyph); D24 (claim↔source verification pipeline, six verdicts, the filter ladder, K1
> citation-laundering defense); D3 (source tiers, community sources as corroboration-only); D45
> (contradiction register — verification-type vs. cross-fact-type records); D8/D35 (MCP tool set,
> the mandatory `caution` block on every fact object, the tombstone-chain-walking precedent of
> returning a structured typed object rather than null on a dead reference); D2 (four-level
> combination validation — dimension exclusivity, hard requires/conflicts, soft influences, Rules —
> which the deferred Builder module will eventually need to run against real per-language data).
> All proposals below are *proposed*, not ratified.

## Problem framing

D23 already drew the headline distinction in one sentence: "absence is a sourced fact, not a
skip." That sentence has been quoted approvingly twice since — once in its own brainstorm, once
in D46's ratification note — without ever being unpacked into the concrete mechanics a build
pipeline, a website, an MCP server, and (eventually) a Builder actually need. Three things stay
genuinely underspecified:

1. **The state space.** For a given (language, feature) pair, there are at minimum four distinct
   states a naive reader might conflate into "the cell is empty": the language was never
   onboarded at all (D28 phase gating); the language is onboarded but this feature's sweep item
   hasn't been answered yet (no FeatureInstance file exists); the language is onboarded, the
   feature was swept, and the sourced answer is `status: absent`; and the language/feature
   combination is explicitly out of scope (D28's deferred set, e.g. SQL under a DSL-ontology
   question that hasn't been settled). D32 already named three of these as the coverage page's
   empty-cell taxonomy — but it named them *before* D46 forced the sharper question of whether
   "verified absent" is a fourth empty state or isn't an empty state at all. This brainstorm has
   to answer that question explicitly, not leave it implied.
2. **Verification of a negative claim.** Every other fact kind in the schema (D23) is verified by
   finding a source that *says* something and checking the claim doesn't overstate it (D24's
   entailment ladder). An absence claim inverts the shape of the evidence: the source has to be
   read as **not saying** something, over some scope, and "a source doesn't mention X" is
   evidence of absence only if the source can be argued to be *comprehensive* over the category X
   belongs to — otherwise "not mentioned in the chapter I read" is just as consistent with
   "not looked for" as with "doesn't exist." This is a known hard case for entailment-based
   verification generally (absence of evidence vs. evidence of absence), and D24's existing
   six-verdict ladder was designed against positive claims; it needs a concrete extension, not a
   hand-wave that "the same gate handles it."
3. **Cross-surface consistency.** The site, the MCP server, and the future Builder each need to
   render/return/reason about the same four-way (really five-way, counting the ontology-level
   "deferred") state space without silently collapsing it. D35 already set the precedent that
   "no fact is ever suppressed, and every fact object carries a mandatory caution block" — but
   *no record at all* isn't a fact object, and returning bare `null` from `get_fact` for "not yet
   swept" would be the one place in the API that breaks D35's own "never a silent null" ethos.
   This needs a designed typed response, symmetric with how tombstones (D38) and superseded
   sources (D38) already get typed envelopes instead of dying silently.

### The state space, named precisely

| State | What exists on disk | Who/what causes it | Is it a "fact"? |
|---|---|---|---|
| **not-yet-onboarded** | No `languages/<lang>/` directory at all | D28 phase gating hasn't reached this language yet | No — there is no language record to be a fact about |
| **not-yet-swept** | Language dir exists; no `instances/<feature>.yaml` for this feature | The D46 compiler emitted a sweep item; no sweep session has landed an answer for it yet (mid-phase, budget-stopped, or simply not reached) | No — this is the absence of a record, not a record |
| **deferred** | No instance file, and the (language, feature) pair is out of D28's current scope by developer/ontology decision (e.g. SQL pending a DSL-ontology position) | An explicit scoping decision, not a pipeline gap | No — same shape as not-yet-onboarded at the data level, distinguished only by *why*, which lives in D28's roadmap document, not in per-cell data |
| **swept, present** | `instances/<feature>.yaml`, `status: present` | A sweep agent answered, sourced | **Yes** — a first-class, challengeable `instance-exists` fact |
| **swept, partial** | same file, `status: partial` + typed `notes` | Same | **Yes** — same fact kind, third value |
| **swept, absent** | same file, `status: absent` + `sources:` | Same | **Yes** — same fact kind, same anchor (`fi.<lang>.<feature>#exists`), same verification obligation as `present`/`partial` |

The first three rows share one property that matters a great deal downstream: **there is no file,
no anchor, no fact id, and nothing to verify, dispute, or embed.** They are not degraded facts;
they are the absence of a fact record, full stop. The last three rows share the opposite property:
**all three are the same claim kind** (`instance-exists`, D23's canonical-claim template already
parameterizes on `status=<value>`), differing only in which of three values the sourced answer
took. Conflating "no record" with "record says absent" is exactly the bug this topic exists to
close — and conflating "record says absent" with "record says present" (i.e., treating `absent`
as some kind of second-class or non-fact) is the mirror-image bug, which is the one D46's
ratification note was specifically warding off by refusing per-language item filtering.

## Options with trade-offs

### O1 — Does `status: absent` need anything new in the FeatureInstance schema itself?

**O1a — No schema change; `absent` already exists (D23), ship as-is.** The `status` field's third
value is already defined, already carries `sources:` at the record level (same as `present`), and
the canonical-claim template (`instance-exists(fi.<lang>.<feature>, status=absent)`) already
produces a distinct fact id from the `present` variant, so correcting `absent` → `present` later
is an ordinary tombstone-and-remint event, not a special case. Nothing to design here structurally.

**O1b — Add a required `notes` field on `absent` records, mirroring the existing requirement on
`partial`.** D23 already requires typed `notes` (`limitation | extra | alternative`) when
`status: partial`, to say *what's* missing/extra/alternative. An `absent` record has an analogous
need: the sweep agent should be forced to state *why* the cited source(s) can be trusted to be
comprehensive over the relevant category — this is exactly the information O3 below needs the
verifier to check mechanically. Recommend adding one **required** free-text field
`absence_scope` on `absent` records: "the claim that supports treating the cited source as
exhaustive over this feature's category" (e.g. "the complete statement-form grammar in Appendix A
of the language reference enumerates every statement kind; pattern-matching constructs do not
appear among them"). This is not optional the way `partial`'s notes are additionally typed — it's
the load-bearing argument the whole negative claim rests on, and without it a human reader (or the
verifier) has no way to distinguish "I looked everywhere and it's not there" from "I read one
paragraph and didn't see it mentioned."

**Recommendation: O1a + O1b.** No new top-level entity, one new required field scoped to
`status: absent` records.

### O2 — Coverage-page rendering: is `absent` a fourth empty-cell state, or not empty at all?

This is the question D32's own framing left open and D46's ratification note forced back to the
surface. Two readings:

**O2a — Add a fourth empty-cell state: "verified absent."** Treat the coverage matrix as
fundamentally about "is there content here," and since `absent` records are typically short (one
sentence + notes, no syntax examples, often no characteristics), visually group them with the
other sparse/empty-looking cells. Rejected: this is precisely the conflation the whole topic
exists to prevent. A `status: absent` record is a **completed, sourced, challengeable research
result** — exactly as much "coverage" as a `present` record, just with a negative answer. Grouping
it visually with "nobody has looked yet" actively misinforms a visitor (and a would-be
contributor deciding what to work on) about which cells are actually open work items.

**O2b (recommended) — `absent` is a normal, filled, non-empty cell; the coverage page's
empty-cell taxonomy stays exactly the three states D32 already named.** A `status: absent` cell
renders with real content — a short "Not present" chip/label plus the sourced one-line summary on
hover/detail, using the same fact-popover machinery (D10, D25's axes, D33's shared status glyph)
that a `present` cell's summary uses — not the dashed-border/CTA-link treatment D32 already
specified for genuinely empty cells. Concretely, the matrix's per-cell states become:

| Render | Data condition | Clickable action |
|---|---|---|
| Filled — "Present" (+ link to instance page) | `status: present` | Navigate to the feature-instance page |
| Filled — "Partial" (+ notes summary) | `status: partial` | Navigate to the feature-instance page |
| Filled — "Not present" (+ absence_scope summary) | `status: absent` | Navigate to the feature-instance page (yes — an absent instance still gets a real page; there is real sourced content to show, per D23's existing "absence is a record too") |
| Empty — dashed, "not yet covered" | No file; language onboarded, feature not deferred | Deep-links to `propose-coverage.yml` (D32) |
| Empty — dashed, "not yet onboarded" | No file; language not in current D28 phase | Deep-links to `request-language.yml` or informational only, per D32's existing "no per-language stub" ratification |
| Empty — dashed, "deferred" | No file; explicitly out of scope | Non-clickable or links to the relevant open question / roadmap note |

This is a direct, minimal edit to D32/D33's existing design, not a redesign: it clarifies that the
matrix's "empty cell" concept was always meant to track *absence of a record*, and confirms
(rather than expands) the three-state taxonomy already ratified. **No fourth empty-cell state is
needed** — the fourth logical state (`absent`) was never actually an empty-cell case; it just
hadn't been explicitly excluded from that bucket before now.

**Feature-instance page for `absent`:** gets built the same way a `present` page does — it is not
suppressed, hidden, or redirected. `/features/<x>/<lang>/` renders normally with the `absent`
status prominently stated up top (distinct typographic treatment from `present`, e.g. a small
"not implemented" badge next to the language name, per D33's existing single-shared-glyph
minimalism — no new glyph family, reuse the existing caution/status line for the D25 axes and add
one plain-text "status: not present" line, matching how `partial` already needs its own visible
statement).

### O3 — Verifying a negative claim: extending D24's ladder

D24's existing six verdicts (`source-unavailable | locator-not-found | supported | partial |
unsupported | contradicted`) and its filter ladder (mechanical → fuzzy quote match → entailment)
were designed around claims a source *states*. An absence claim needs the same six verdicts to
remain meaningful (reusing the ladder's plumbing, its logging, its golden-set infrastructure) but
needs a **different method at the entailment stage**, because there is no positive quote to fuzzy-
match against.

**O3a — Treat absence claims exactly like any other claim (no special-casing).** The verifier
looks for a quote supporting "X is absent" and, finding none (sources don't usually say "we do not
have pattern matching"), returns `unsupported` for essentially every legitimate absence claim.
Rejected outright — this would make `status: absent` unverifiable in practice, defeating D23's own
premise that absence is a sourced, admissible fact.

**O3b (recommended) — A new verification method, `completeness-check`, applied only when the
claim kind is `instance-exists` with `status=absent`.** Concretely, three stages:

1. **Mechanical (free, always runs):** the cited source(s) must be tier A or B (D3) — community
   sources (tier D) can corroborate but, per D3's existing rule, never solely back any claim,
   least of all a negative one where corroboration matters more, not less. The locator must
   resolve (D24 stage 1 unchanged).
2. **Corpus-wide negative grep (mechanical, cheap, new):** rather than checking only the cited
   locator range, the verifier runs a full-text search across **every** `source_chunks` row
   belonging to the cited `source_id` (not scoped to the locator) for the feature's name and a
   small controlled list of aliases/synonyms (a new optional `aliases: []` field on the *feature*
   record, D23 — e.g. `pattern-matching` aliases `["destructuring", "match expression",
   "structural matching"]`). Zero hits across the whole source is the strong positive signal for
   absence; any hit routes to LLM adjudication (below) rather than auto-failing, since a hit could
   be an unrelated use of an overloaded word (e.g. "pattern" meaning a regex pattern, not
   pattern-matching-the-feature).
3. **LLM entailment, inverted framing (only on an ambiguous grep hit, or always as a lighter
   cross-check on zero-hit cases at a sampled rate mirroring D24's `mini` drift gauge):** the
   prompt is not "does this text support the claim" but **"does the cited source purport to be a
   comprehensive treatment of the category this feature belongs to (e.g. a complete statement-form
   grammar, a complete standard-library index, a complete keyword list), and does the retrieved
   text corroborate that no described mechanism matches the feature under any of its aliases?"**
   The agent's own `absence_scope` field (O1b) is fed into this prompt as the argument to check,
   not to trust blindly — the model is verifying *that argument*, exactly as D24's existing
   entailment stage verifies a positive claim's own stated reasoning rather than taking the
   agent's word for it.

Verdict mapping is then a direct extension of D24's existing six values, not a seventh:
`supported` = tier-A/B source, zero corpus-wide hits (or hits dismissed as unrelated-sense by the
LLM stage), and the source's comprehensiveness argument holds; `partial` = an ambiguous
near-synonym hit the LLM stage can't confidently dismiss (logged in the same filterable
partial-verdict channel D24 already ratified); `unsupported` = source doesn't plausibly cover the
relevant category at all (e.g. citing a marketing blog post as if it were exhaustive); `contradicted`
= the corpus-wide grep or the LLM stage finds the source **does** describe the feature — this
blocks admission outright, exactly as a contradicted primary citation already does for positive
claims (D24) — a sweep agent claiming "absent" against a source that actually documents the
feature is the single most important failure mode this design has to catch, since it's the
directly K1-adjacent laundering pattern turned inside out (a false negative is just as much a
citation-laundering risk as a false positive, and arguably cheaper for an adversarial or lazy
agent to produce, since "I didn't find it" requires less work than fabricating a supporting
quote).

**Confidence (D25) amendment, narrowly scoped:** an absence claim backed by exactly one tier-A/B
source caps at `medium` confidence by default (never `high`) unless a second, independent tier-A/B
source's completeness-check also passes — a targeted tightening of D25's existing tier×
corroboration-count lookup, justified because "the one source I checked doesn't mention it" is
inherently weaker evidence than "the one source I checked explicitly states it," even holding
source tier constant. This does not change D25's lookup mechanism, only adds one conditional cap
specific to `instance-exists` claims where `status=absent`.

### O4 — Cross-fact contradiction between two absence-adjacent claims

No new machinery needed: if one sweep marks a language `absent` for a feature and a later
challenge or re-sweep marks it `present` (e.g. a missed library-level realization, or a version
that later gained the feature), that's handled entirely by D23's existing tombstone-and-remint
path if it's the *same* record being corrected, or by D45's `cross-fact` contradiction type if two
independently-verified records genuinely disagree (rare, since there's only one FeatureInstance
record per (language, feature) pair — the more likely shape is a **since-boundary dissolution**
per D5/D25's existing "many contradictions dissolve via since/version qualification" pattern: an
`absent` record with no upper-bound qualifier and a later `present` record with a `since` value
are not in tension at all once both carry accurate `since`/point-in-time framing, and D45's
automated since/version-qualification check at mint time already closes exactly this shape of
apparent conflict with no human involvement. Nothing new to design here — flagging only that this
topic's negative-claim verification (O3) is what makes an `absent` record trustworthy enough for
that existing dissolution logic to have a real claim to check in the first place.

### O5 — MCP semantics for a (language, feature) pair with no record

D35 already committed the MCP server to two hard rules that bind this design directly: (1) no
fact is ever suppressed, and (2) every fact object carries a mandatory `caution` block — meaning
bare `null` is already foreign to this API's philosophy anywhere a fact *does* exist. The gap D35
left open is what happens when a fact **doesn't** exist yet, which this topic must close.

**O5a — Return `null` / omit the field for "no record."** Cheapest, but breaks symmetry with every
other "dead reference" case the project already designed a typed envelope for: a superseded fact
id returns `{status: superseded, successor, chain}` (D38), a superseded source auto-walks to the
latest edition (D38), a `dispute: contradicted` fact inlines its conflicting participants (D45).
`null` would be the one place in the whole MCP surface where "there's nothing here" isn't
explained. Reject.

**O5b (recommended) — A typed `no-record` envelope, symmetric with the tombstone/supersession
pattern.** `get_fact` (and any lookup keyed on an anchor that would resolve to
`fi.<lang>.<feature>#exists` if it existed) returns, when no instance file exists for that
(language, feature) pair:

```json
{
  "status": "no-record",
  "reason": "not-yet-swept",
  "language": "zig",
  "feature": "garbage-collection",
  "coverage_url": "https://langatlas.dev/coverage/#zig-garbage-collection"
}
```

with `reason` taking exactly the three D32 values (`not-yet-swept | not-yet-onboarded | deferred`)
— the same three-state taxonomy the coverage page uses, reused rather than reinvented, so the site
and the MCP describe the same state space in the same vocabulary. `reason` is derivable
mechanically from the D28 language registry (is the language onboarded? in what phase?) plus a
static deferred-language list, with no judgment call at query time — this is a pure lookup, not a
new classifier. **This object is explicitly not a fact and carries no `caution` block** — D35's
caution contract is scoped to fact objects, and a no-record response is a statement about the
*absence of any fact*, not a low-confidence fact, so conflating the two schemas would blur exactly
the distinction this topic exists to keep sharp. A `status: absent` FeatureInstance, by contrast,
returns an ordinary fact object — full content, full `caution` block, full provenance — through
the exact same code path a `present` instance uses, differing only in the payload's `exists` field
value. This is the concrete, implementable version of "return null vs. a typed absent object vs. a
typed unknown object" the checklist question named: the answer is **two** typed shapes, not three
— a real fact object (covers both `present`/`partial`/`absent`, since all three are the same claim
kind) and a `no-record` envelope (covers all three no-file states, since none of them is a claim at
all).

`get_neighbors` and `search_knowledge` inherit this for free: a `no-record` pair simply produces no
fact rows to return (there's nothing to embed or graph-traverse for a record that doesn't exist),
so no special handling is needed there beyond ensuring `search_knowledge` never *synthesizes* an
implied-absent result from the mere absence of a hit — an important guardrail, since a naive RAG
consumer could otherwise misread "no fact retrieved" as "this language lacks the feature," exactly
inverting the not-yet-swept/verified-absent distinction this topic protects. The MCP tool
descriptions (already carrying the D35 caution-contract text once per session) get one added
sentence stating this explicitly: *"the absence of a search result for a (language, feature) pair
never implies the feature is absent — query `get_fact` on the specific anchor to distinguish
'not yet researched' from 'researched and found absent.'"*

### O6 — Future Builder validation: three-valued logic over per-instance data

The Builder is an explicitly deferred module (D11), and D39 already scoped its consumption of
`exclusivity` as a pointer, not a design, for the same reason. This topic does the same: name the
requirement precisely enough that a future Builder brainstorm doesn't have to rediscover it, without
designing the Builder itself.

D2's four-level combination validation (dimension exclusivity, hard requires/conflicts, soft
influences, Rules) is **entirely feature-graph-level, not per-instance** — a hypothetical
Builder-composed language has no FeatureInstance records at all (it isn't a real, swept language),
so those four validation levels run unchanged regardless of this topic: they check "can feature A
and feature B coexist in *any* language," never "does language X have feature A." Per-instance
absence data only becomes relevant the moment the Builder does something that *references* a real
existing language — e.g. a "how does your build compare to Rust?" feature, or a "languages closest
to your build" recommender (Selector-adjacent, also deferred). For that class of future feature,
the three-valued logic this topic has already established for MCP/site applies unchanged: a
comparison against Rust must be able to say "present," "absent" (with its own caution/confidence,
per O3), or "not yet known" (a `no-record` state) for each compared feature, and must never let
"not yet known" silently render as "absent" — the exact bug this whole topic exists to prevent,
now recurring one layer up in a not-yet-designed surface. No schema change is needed to support
this later: the same fact-object/no-record-envelope split from O5 is already sufficient; the only
thing worth stating now, for whoever designs the Builder, is that it must **consume `no-record` as
a first-class third value in any UI it builds, not default it to false**.

## Recommendation

*Proposed* package:

1. **State space (O-table above) confirmed as the full picture**: `not-yet-onboarded`,
   `not-yet-swept`, and `deferred` are all "no record exists" states (not facts); `present`,
   `partial`, and `absent` are all "a record exists" states (all three are the same
   `instance-exists` claim kind, differing only in the `status` value) and are equally
   first-class, equally challengeable, equally verified facts.
2. **Schema (O1):** no new entity; one new required field, `absence_scope` (free text), on
   `status: absent` records — the sweep agent's argument for why the cited source(s) can be
   trusted as comprehensive over the feature's category. This is the field O3's verifier checks.
3. **Coverage page (O2):** `status: absent` is **not** a fourth empty-cell state and is **not**
   grouped with empty cells at all — it renders as a normal filled cell ("Not present" + summary),
   using the same fact-popover machinery as `present`/`partial`. D32's three empty-cell states
   (`not-yet-swept | not-yet-onboarded | deferred`) stand exactly as ratified, now with an explicit
   note that `absent` was always meant to be excluded from that bucket. Feature-instance pages for
   `absent` records get built and served normally, not suppressed or redirected.
4. **Verification (O3):** a new method, `completeness-check`, extends D24's existing six-verdict
   ladder — reusing the verdict vocabulary, not inventing new ones — via a three-stage check
   (tier-A/B + locator resolution; a corpus-wide negative full-text grep across every chunk of the
   cited source, using a new optional feature-level `aliases: []` field; an inverted-framing LLM
   entailment stage that verifies the agent's own `absence_scope` argument rather than searching
   for a supporting quote). A positive hit for the feature inside a source cited as supporting its
   *absence* is a `contradicted` verdict, blocking admission outright — the same rule D24 already
   applies to a contradicted primary citation on a positive claim, now guarding the inverse
   laundering pattern. Confidence (D25) for `absent` facts caps at `medium` on a single tier-A/B
   source, requiring a second independent corroborating source to reach `high` — one narrow,
   targeted tightening of D25's lookup, scoped only to negative `instance-exists` claims.
5. **Contradiction handling (O4):** no new machinery — D45's cross-fact type and D25's existing
   since/version-qualification dissolution logic already cover an apparent present/absent
   disagreement across time or across independently-verified records; this topic's contribution is
   only making the underlying `absent` claim trustworthy enough (via O3) for that machinery to have
   something real to check.
6. **MCP (O5):** two typed response shapes, not three — an ordinary fact object (covering
   `present`/`partial`/`absent` uniformly, full `caution` block, full provenance) and a new
   `no-record` envelope (`{status: "no-record", reason: not-yet-swept | not-yet-onboarded |
   deferred, language, feature, coverage_url}`, no `caution` block, since it is not a fact) for the
   three no-file states — reusing D32's three-value `reason` vocabulary rather than minting a
   parallel one. `search_knowledge`/`get_neighbors` never synthesize an absence conclusion from a
   missing hit; the MCP tool-description caution text gets one added sentence stating this
   explicitly.
7. **Builder (O6, deferred, pointer only):** whenever a future Builder brainstorm designs
   comparison/recommendation features that reference real languages, it must consume the same
   fact-object/`no-record` three-valued split from O5 as a first-class distinction, never defaulting
   `no-record` to `false`. D2's four validation levels themselves are unaffected by this topic —
   they are feature-graph-level and never touch per-instance data.

## Open questions for the developer

1. **`absence_scope` as a required field (O1b)** — acceptable as a hard requirement on every
   `absent` record (extra sweep-agent burden on what might otherwise be the "quick no" answer in a
   sweep), or should it be optional-but-verifier-penalized (missing scope argument caps the
   verdict at `partial` rather than blocking the record entirely)?
2. **Feature-level `aliases: []` (O3)** — worth adding now as a general schema field (useful beyond
   absence-checking, e.g. for search/synonym matching too), or scoped narrowly to only exist when
   at least one language's sweep has produced an `absent` record for that feature (lazier, avoids
   populating aliases for features nobody has ever needed to argue absence against)?
3. **Confidence cap for single-sourced absence claims (O3)** — is capping at `medium` (never
   `high` on one source) the right conservatism, or is this over-correcting given D25 already has a
   general "community sources can lift a level but never establish verification" safety valve that
   arguably already covers the spirit of this concern without a claim-kind-specific carve-out?
4. **Coverage-page visual treatment of `absent` cells (O2)** — confirm "same filled-cell treatment
   as present/partial, distinguished only by a status chip/label," or does the developer want
   `absent` cells visually muted/de-emphasized relative to `present` (e.g. a lighter background)
   even though both are equally "real, sourced content" — a purely aesthetic question this
   brainstorm doesn't have standing to settle unilaterally, since it borders on topic 19/33's
   matrix-component and trust-signal UX territory.
5. **`no-record` envelope's `coverage_url` field (O5)** — worth the extra field (a convenience
   deep-link for an MCP-consuming agent that might itself want to file a `propose-coverage` issue,
   e.g. a future "agent notices a gap and flags it" workflow), or is that speculative given no such
   agent workflow exists yet, and should the field be dropped until one does?

## New brainstorm topics surfaced

- **Golden-set strata for absence claims** — D44's 13-stratum perturbation taxonomy (correct,
  overstated, fabricated locator, wrong `since`, contradicted, right-claim-wrong-source, category
  error, fabricated combination, quote-mismatch, quote-found-elsewhere, OCR-noisy,
  paraphrase-heavy-correct) has no stratum exercising the `completeness-check` method this topic
  designs (O3) — e.g. "absence claim, source actually does mention it under a synonym"
  (should verify as `contradicted`) or "absence claim, source genuinely silent but not actually
  comprehensive" (should verify as `unsupported`). Worth folding into topic 36's golden-set
  methodology as an additional stratum pair before the verifier's `completeness-check` path gets
  calibrated, rather than shipping it uncalibrated against the existing positive-claim-oriented
  golden set.
- **Feature-level alias/synonym schema field** — surfaced directly by O3's design (a feature needs
  a small controlled `aliases: []` list for the negative-grep check to be effective against
  terminology variance) but has plausible uses beyond absence-checking (search relevance, cross-
  language terminology mapping); worth a small dedicated look, or a fold-in note on topic 09's
  schema, rather than being decided as a side effect of this topic alone.
- **Whole-source-scope locator convention** — O1b's `absence_scope` field and O3's corpus-wide
  grep both work around the fact that brainstorm 09's existing locator grammar (pp./§/url-fragment
  ranges) has no way to cite "the source's claim to comprehensiveness as a whole" as a first-class
  locator kind. Whether this deserves an actual grammar extension (e.g. a `scope: toc | index |
  full-document` locator kind) or should stay implicit in the free-text `absence_scope` argument is
  unresolved and small enough to fold into a future locator-grammar touch-up rather than needing
  its own brainstorm.

## Sources

No new external sources introduced; all constraints trace to ratified decisions D1–D46 and to
brainstorms 09, 18, 24, 25, 32, 33, 38, 45 cited inline above.
