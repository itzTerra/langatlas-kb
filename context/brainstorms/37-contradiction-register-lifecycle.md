# 37 — Contradiction-Register Lifecycle

> Backlog brainstorm for LangAtlas. Topic: the concrete schema for the contradiction-register
> records first named as a policy in D5 ("Contradictions are first-class records; many dissolve
> via `since`/version qualification") and required as an input/output surface by D24 (the
> `contradicted` verdict, the ratified requirement that `partial` verdicts be "logged in an
> identifiable, filterable way") and D25 (the `dispute: none | contradicted | superseded` axis,
> the controversy assessor's `signals` list referencing `contradiction:CTR-0142`-shaped ids).
> Binding context: D1 (git YAML, no PR gate), D5, D16/D23 (tombstones.yaml, content-keyed
> `f-<12-hex>` fact ids, chain-walk resolution), D24 (six-verdict vocabulary, admissibility
> rule), D25 (status axes, controversy score, assessor lane discipline), D35 (MCP caution
> contract, the tombstone-resolution precedent of inlining successor content); builds on
> brainstorm 09 (fact schema), 11 (verification pipeline), 12 (confidence/dissent/staleness),
> 19 (trust-signal UX, the shared disputed/contradicted/superseded/partially-verified glyph),
> 29 (tombstone chain-walking, site/MCP dead-id rendering — the closest existing precedent for
> everything this topic needs to design). All proposals below are *proposed*, not ratified, per
> the project's decision-hygiene convention — nothing here is binding until the developer signs
> off.

## Problem framing

Three prior brainstorms have all reached for "contradiction record" without ever designing it.
Brainstorm 04 (round 1, pre-dating D1's no-PR-gate pivot) first proposed contradictions as
first-class records surfacing from reconciler diffs. Brainstorm 11 defined the `contradicted`
verdict as a verification-pipeline output and, in its own ratified admissibility rule (D24),
already committed to behavior this topic must now schema out: "a `contradicted` verdict on one
citation of an otherwise-supported fact does not block admission — it auto-creates a
contradiction record and is a first-class input to the D21 controversy score." Brainstorm 12
built the `dispute: contradicted` status axis and the controversy assessor's `signals` list
*against* the assumption that contradiction records already exist with resolvable ids, and
explicitly surfaced this topic in its own "New brainstorm topics surfaced" section as unfinished
business. Nobody has written the YAML.

**The crux, which the checklist itself asks to be resolved: `contradicted` (D24) is not one
thing.** Read literally, D24's verification pipeline produces a `contradicted` verdict on a
**(claim, citation) pair** — the text located at one specific citation's locator asserts
something incompatible with the claim being checked. That is a narrower, more local event than
what D5 originally imagined: **two independently drafted, independently verified facts**
(each individually admissible on its own citations) asserting incompatible things about the
same subject. The two differ in almost every dimension that matters for a register schema:

| | Verification-type (`contradicted` verdict) | Cross-fact type |
|---|---|---|
| What conflicts | A fact vs. **its own** cited source | Fact A vs. fact B, each already `supported` |
| Discovered by | The D24 verifier, mechanically, per citation | A reconciler diff (D5), a periodic scan, or a human challenge |
| Typical cause | Wrong locator picked up adjacent contradicting text; a source the agent skimmed too fast; genuinely two things the source itself disagrees about internally | Two agents (or two sweep runs, or a challenge) drew on different sources that disagree; a genuine unsettled question in the literature |
| Severity | Usually low — the fact stays admitted via a different citation; this is closer to "one piece of evidence for this fact turned out to be bad" than "this fact is disputed" | The thing the site's disputed glyph and D25's controversy level 3 actually mean |
| Volume (expected) | Frequent-ish, mechanical, unglamorous | Rare, interesting, exactly the "arguably the most interesting content on the site" material brainstorm 12 called out |

Treating these as one undifferentiated "contradiction record" would either bury genuine field
disputes under a pile of one-bad-citation noise, or force the low-severity case through
machinery (site glyphs, controversy escalation, human-legible "two sides" rendering) built for
the high-severity case. **This document's central design move is to split them into two
`type` values sharing one schema shape and one ledger file**, resolved differently at mint
time, closed differently, and rendered with very different prominence. `partial` verdicts,
addressed in O5, turn out *not* to mint contradiction records at all under D24's own fold rule
— a second resolution the checklist's phrasing leaves ambiguous and that this document settles
explicitly.

Sub-problems to design, mirroring the checklist line exactly:

1. **Schema** — record shape, storage location, identity scheme, and precisely which triggers
   mint which `type`.
2. **Closure semantics** — what closes a record (automatic since/version-qualification checks,
   corrections, human challenge adjudication, or nothing — genuine open field disputes), who/
   what triggers it, and what a closed record leaves behind.
3. **Site/MCP rendering** — what lives behind brainstorm 19's shared glyph, whether a dedicated
   view is warranted, and how MCP tools expose contradiction content to agents (extending the
   D35 caution contract and the brainstorm-29 tombstone-inlining precedent).

Scale check (carried from 11/12/29): low hundreds of ontology nodes, tens of thousands of
derived facts, verification running at ~1,000–4,000 (claim, citation) pairs per overnight batch
(D24 §2.9). At that verification volume, even a low single-digit-percent `contradicted` rate
produces tens of verification-type records per batch in the steady state — which is exactly why
this document does not let them share visual or governance weight with the handful of genuine
cross-fact disputes the corpus will accumulate.

## Options with trade-offs

### O1 — One contradiction kind vs two (the crux, resolved)

**Option 1a — single unified `contradiction` record type**, differentiated only by a
free-form `cause` note. Simplest schema. Rejected: it forces one rendering policy onto two
severities that need different ones (see the table above), and it forces the controversy
assessor to re-derive severity from participant count every time instead of reading a field —
brittle, and contrary to D25's own stated preference for structured, machine-referenced signals
over inferred meaning.

**Option 1b — two `type` values, one shared schema shape (recommended): `verification` and
`cross-fact`.** Same record shape (id, status, participants, opened, closure) so one storage
file, one chain-walk-style resolver, and one MCP tool surface serve both; the `type` field and
a `participants` list whose cardinality naturally differs (1 for verification, 2+ for
cross-fact) drive every downstream policy difference — controversy weighting, site visibility,
MCP inlining verbosity — without needing a second file format or a second resolver
implementation. This is the same "one shape, two governance paths" move brainstorm 29 already
validated for folding topic 28's `edition-superseded` source tombstone into the ontology
migration tombstone shape (29 §1, §2.6) — reusing a proven pattern rather than inventing a
third one.

**Option 1c — no cross-fact type at all; model genuine field disputes purely as controversy
level 3, with no contradiction record.** Attractive for its minimalism (the controversy
assessor already has a level for "pipeline couldn't settle it" / "field hasn't settled it," per
D25), but rejected: the assessor's own input contract (12 §5.2) explicitly lists "the
contradiction register" as a *structured input* it reads, not something it derives on its own
— collapsing the register into the assessor would force the assessor to do relational
discovery work (which facts conflict with which), which is exactly the kind of unstructured
judgment D25 deliberately kept out of its lane (the assessor classifies over records fed to it;
it does not go find them). A structured input needs a structured source, hence O1b.

### O2 — Record identity & storage

Following D23/O1c's precedent (fact ids are content-keyed so independent agents converge on
the same id for the same claim) rather than D16's tombstone-ledger precedent (sequential,
append-only, minted once by whichever process fires the event):

**Option 2a — sequentially minted ids** (`ctr-0001`, `ctr-0002`, …), assigned by whichever
process first detects the contradiction. Simple, human-legible in changelogs. Rejected as the
sole scheme: under D1's no-PR-gate concurrent-commit model, two independent processes (e.g. the
nightly verifier batch and a same-night human-challenge resolution session) can discover the
*same* underlying conflict in the same window; sequential minting has no natural dedup and
would produce two records for one conflict, silently doubling the controversy signal.

**Option 2b (recommended) — content-keyed ids, mirroring D23's `f-<12-hex>` scheme:**
`ctr-<12-hex SHA-256 of a canonical string>`. Canonical string per type:

```
contradiction-verification(f-aa11bb22cc33, source-id, locator)
contradiction-cross-fact({f-3f9a1c04b2d7, f-91b2c4d8e610})   # participant fact ids, sorted
```

Two processes independently detecting the same conflict compute the same id and the second
mint is a no-op dedup (append nothing; the record already exists) — exactly the guarantee D23's
O6 built for facts themselves, reused here for free because it's the same hashing discipline.
Lowercase `ctr-` prefix to match the `f-` convention (brainstorm 12's illustrative
`contradiction:CTR-0142` was written before this scheme existed and should be read as
non-normative).

**Storage: one file, `contradictions.yaml` at repo root, sibling to `tombstones.yaml`
(recommended, matching D23's layout).** Unlike `tombstones.yaml`, entries here are **not**
append-only artifacts of a one-way supersession event — a contradiction record's `status` field
is mutated in place as it moves `open → closed` (git history is the audit trail per D1/D9,
exactly as it already is for every other canonical YAML edit in this project; no parallel
history log is needed inside the record). Volume estimate (O1's scale check) puts this at low
hundreds of entries over the corpus's lifetime, the overwhelming majority `type: verification`
and short-lived — nowhere near `tombstones.yaml`'s "shard if it becomes a merge-conflict magnet
later" threshold, so no sharding is proposed for v0; the same escape hatch (shard to
`contradictions/<year>.yaml`) is noted for parity with D23's own tombstone-ledger contingency.

### O3 — Minting authority: which process is allowed to write a new record

Following D25's lane discipline (the controversy assessor reads structured inputs; it never
does relational discovery itself, per O1b above), minting is restricted to three named,
mechanical/pipeline processes — never the assessor, never a bare agent decision:

1. **The D24 verifier**, at verdict-recording time (its own stage 4): whenever a `contradicted`
   verdict lands on a citation belonging to a fact that remains admissible via a *different*
   `supported` citation, mint (or dedup-match) a `type: verification` record. **A `contradicted`
   verdict on a fact's *only or primary* citation never mints a record** — the fact fails
   admission outright (D24's rule stands: admissible = ≥1 `supported` tier-A/B citation) and
   never enters the canonical store, so there is no public fact for a contradiction record to
   attach to. That failure is visible only in the verifier's own batch transcript (D18) and
   bounce-count bookkeeping (D24's 2-bounce budget) — a private pipeline event, not public
   corpus content, consistent with "agent-generated text is never itself citable" (D4) and with
   only *admitted* facts getting public-facing dispute machinery.
2. **The D5 reconciler/debate outcome**, when a structured debate over a conflicted
   questionnaire cell escalates or resolves with recorded standing dissent (rather than full
   convergence): mint a `type: cross-fact` record over the two (or more) resulting admitted
   facts. This is the direct descendant of brainstorm 04's original proposal.
3. **A new periodic cross-fact contradiction scan** (proposed as a *new* small job, not designed
   in full here — see "New brainstorm topics surfaced"): the D5 reconciler only ever compares
   facts drafted *within the same sweep run*; it cannot catch a fact added months later (a new
   language onboarding, a `since`-back-dating run, a human-challenge-driven counter-fact) that
   happens to conflict with an existing, already-admitted fact on the same subject without ever
   passing through a live debate. A lightweight nightly-batch-adjacent job — same "reconciler
   compares candidate claims" logic, just triggered by newly admitted facts against the
   existing corpus on the same anchor family (same feature-instance subject, same edge) rather
   than against sibling sweep-run drafts — mints `type: cross-fact` records for anything it
   finds. Kept explicitly out of scope for full design here (it needs its own cost/cadence/
   candidate-generation analysis, flagged below), but its *existence* is load-bearing: without
   it, cross-fact contradictions between facts added in different pipeline runs would simply
   never be discovered, which would silently understate controversy for exactly the kind of
   fact D25 calls "arguably the most interesting content on the site."
4. **Human-challenge resolution sessions** (D9): when a challenge investigation concludes that
   the challenger's cited counter-source produces a *new, independently verified* counter-fact
   that the correcting agent does not believe supersedes the original (as opposed to a plain
   in-place correction, which is ordinary tombstone churn, not a contradiction — see O4),
   mint `type: cross-fact` with `opened.mechanism: human-challenge` and the GitHub issue number
   recorded for audit.

No other path mints a contradiction record. This closes the ambiguity in the checklist's phrase
"minted by `contradicted`/`partial` verdicts" — see O5 for why `partial` is deliberately
excluded from this list.

### O4 — Closure semantics

Four ways a record's `status` moves off `open`, matching the checklist's four named
possibilities, plus the fifth (stays open) that is a non-event by design:

**1. Dissolves via since/version qualification (D5's named common case).** An automated check
runs **at mint time** (not later, as a queued job) comparing the participants' `since`/version-
scoping fields: if the two facts' subject ranges do not actually overlap (e.g. "Python lacks
pattern matching" sourced against Python 3.8 docs vs. "Python has pattern matching" sourced
against the 3.10 release notes — not a contradiction, a version-scoped pair of true statements)
the record is minted **already closed**: `status: dissolved`, `resolution_kind:
qualified-non-contradiction`, timestamped at mint. It never renders as `open` — no glyph, no
controversy signal — but the entry persists in `contradictions.yaml` as an audit artifact (see
below). This mechanical check is deliberately narrow (compares structured `since`/`status`
fields the two facts already carry, per D23's schema — no new inference): it will not catch
subtler scope qualifications hiding in prose ("hurts learnability *for beginners*," per
brainstorm 12's O3 note on scope qualifiers living in free text) — those stay genuinely open
until a human or a later pipeline pass narrows them, which is correct: the mechanical check
should never overreach into judgment territory just to shrink the open count.

**2. Superseded by a correction.** Either participant fact gets corrected (an ordinary D23
value-correction, or a D16 migration remap) and the correction's own tombstone entry names the
contradiction's other participant as no longer applicable. **Recommendation: the tombstone
writer checks `contradictions.yaml` for any open record naming the fact being tombstoned and
auto-closes it**, `status: superseded`, `resolution_kind: participant-corrected`,
`closure.tombstone_ref: <old_fact_id>` pointing at the `tombstones.yaml` entry that fired the
closure. This is the same cross-ledger reference pattern brainstorm 29 used for migration
tombstones referencing their `migration_id` — one small pointer field, not a merged ledger.

**3. Resolved by human expert challenge.** A challenge issue can reference a contradiction id
directly (extending D9's existing "challenge issue references a fact id" convention to also
accept a `ctr-` id). The resolution session's outcome is either (a) "these were never really in
conflict, here's why" → `status: dissolved`, `resolution_kind: human-qualified` (the same
outcome shape as #1, just human- rather than mechanically-triggered — the scope-qualification
the automated check missed), or (b) "one side is simply wrong" → triggers an ordinary
correction on the wrong side, which then closes the record via path #2. A challenge can also
explicitly **decline to resolve** ("both sides are legitimately sourced, this is a real open
question") — this does not close the record; it just adds a `closure_attempt` note (see the
schema below) documenting that a human looked and confirmed genuine disagreement, which is
itself a useful signal for the controversy assessor (a challenge-reviewed-and-confirmed dispute
is stronger evidence for level-3 `disputed` than a debate-escalated one that no human has ever
looked at).

**4. Stays open indefinitely.** The default outcome for genuine field disagreement and the
expected steady state for most `type: cross-fact` records with two independent tier-A/B-backed
sides — this is D25's controversy level 3 (`disputed`) territory, not a failure state. No
forced closure exists or should exist. The one refinement proposed: a **re-check trigger**
riding the same event list D25 already built for re-verification (O4c in brainstorm 12) — new
source ingestion touching either participant's subject re-runs the mechanical qualification
check from path #1, since a newly ingested source is exactly the kind of evidence that can
retroactively reveal a version-scoping distinction nobody had access to at mint time. No
calendar sweep is needed beyond that trigger; unlike stale facts, an untouched open
contradiction is not "rotting" — it is either still genuinely disputed (correct to stay open)
or waiting on new evidence (correctly triggered by the same event that would supply it).

**What a closed record leaves behind.** Per every path above: **closed records are never
deleted and never leave `contradictions.yaml`.** They persist as historical audit content — "a
past version of this fact used to look contradictory until X clarified it" — the same
"never suppress, always show your work" ethos D9/D25 apply everywhere else in the project
(D25's non-suppression policy for `partially-verified` facts is the direct precedent). The
*live* `dispute` axis (D25) is a **derived** read of a fact's *currently-open* contradiction
records only — closing the last open record naming a fact flips its `dispute` axis back to
`none` immediately, even though the historical record is still there for anyone who follows the
provenance link. This mirrors exactly how a closed GitHub challenge issue (D9) doesn't retract
the git history that shows a fact was once disputed — the register just formalizes the same
pattern for machine-detected contradictions instead of human ones.

### O5 — `partial` verdicts: contradiction records, or a separate ledger? (resolving the
checklist's ambiguity)

The checklist's own phrasing — "contradiction records minted by `contradicted`/`partial`
verdicts" — reads as if both verdicts mint the same kind of record. **This is not correct under
D24's own ratified fold rule, and this document corrects it explicitly.**

D24 §2.4's decomposition rule states: "all supported → `supported`; some → `partial`; none →
`unsupported`; **any contradicted → `contradicted`**." A verdict can only be `partial` when
*zero* of its atomic assertions came back contradicted — if even one had, the overall verdict
would already be `contradicted`, not `partial`. **`partial` and `contradicted` are therefore
mutually exclusive by construction**: `partial` means "the source is silent or under-specific
on some part of the claim," never "the source disagrees with part of the claim." A silent
source is not evidence of a contradiction with anything — it is evidence of incomplete
citation, a categorically different problem the contradiction register (built to hold two
*positively conflicting* claims/sources) has no natural field shape for.

**Recommendation: `partial` verdicts never mint contradiction-register records.** They already
have a home: D24's own ratification requires them "logged in an identifiable, filterable way,"
which this document reads as a **separate, flat `partial-verdicts.yaml` verification-side log**
(or equivalently, a queryable column in the build-side verification ledger D23 already keeps
verdicts in, per D23's ratified "verifier pass/fail is not written back into authored YAML, it
lives in a build-side ledger") — filterable by field, source, batch, so the developer's manual
audit pass (D24 §2.8) can pull every `partial` for review. `partial` verdicts remain a
first-class **input** to the controversy assessor exactly as D24/D25 already specify ("surviving
partials likewise" feed the assessor, brainstorm 11 §2.5) — that channel is unaffected by this
recommendation, which only concerns whether they *also* mint a contradiction record. They
don't, and shouldn't: doing so would flood the register with the single most common verdict
outcome in the pipeline (D24 §2.9 estimates ~5–15% of pairs escalate on partial/contradicted/
inconsistent) and defeat the whole point of O1's severity split.

### O6 — Site rendering

Brainstorm 19 already designed the base-page treatment (§2.6, Option B+C, ratified in spirit
though not yet formally ratified as a decision): one shared glyph marks
`disputed`/`contradicted`/`superseded`/`partially-verified` facts, full detail lives in the
existing D10 citation popover, nothing else changes on the base page. **This topic's job is to
define what actually renders behind that glyph and inside that popover for a contradicted
fact** — brainstorm 19 deliberately left that content unspecified.

**For `type: verification` records** (the common, low-severity case): the popover's existing
D25-axis prose line ("Verified · high confidence · settled") gains, only for facts with an open
verification-type record, one additional short clause naming the specific citation that failed
and why — e.g. "one additional citation (Foo FAQ, §3) was found not to support this claim on
review; the fact remains verified via [ISO/IEC 9899, §6.7.9]." No separate visual treatment,
no dedicated page — this is provenance detail, exactly the "popover-only" tier brainstorm 19
already established for lower-salience signals. The failing citation itself is simply dropped
from the fact's rendered `sources:` list once the record closes via O4 path #2 (superseded),
so most readers never see this state at all; it exists for the minority who open the popover
on a fact mid-flight.

**For `type: cross-fact` records** (the rare, high-severity case): the popover gains a compact
**"Sources disagree"** block — not prose-only, because two full sourced claims genuinely need
to be shown side by side to be legible, mirroring how brainstorm 12's O3 already renders
quality-assessment spread as a distribution rather than a sentence:

```
⚠ Sources disagree on this point
  Rust Reference (tier B) says: "…since version 1.0…" [source link]
  vs.
  Community survey (tier C) says: "…not until 1.26…" [source link]
  Open since 2027-01-09 · not yet resolved
```

Each side links to its own citation popover (recursion is fine — D10's popovers are already
per-fact); this is additional content *inside* the existing popover surface, not a new UI
component, keeping faith with brainstorm 19's no-new-chrome constraint.

**A dedicated view is proposed as an addition, not a replacement:** a small, low-chrome
`/disputed/` index page listing only **open, `type: cross-fact` records** (never verification-
type — those stay popover-only-forever per the severity split) — essentially "genuinely
unsettled questions the corpus has found," reusing brainstorm 12's own framing that level-3/
`disputed` content is "arguably the most interesting content on the site," not a defect to
hide. This is new site surface, so it is flagged as an open question (below) rather than folded
into the recommendation outright — brainstorm 19 was explicit that trust-signal presentation
thresholds are a site design call, and a dedicated page is a bigger commitment than the popover
extension above.

### O7 — MCP rendering

Two sub-questions, both resolved by direct analogy to precedent this project has already
ratified:

**Does `get_fact` on a contradicted fact return both sides?** Yes, following the exact pattern
D35/brainstorm 29 already established for tombstone resolution — "include the resolved
successor fact(s)' full content inline (not just their ids), each with its own mandatory
`caution` block" (29 §2.4). The same move applies here: a fact object with `dispute:
contradicted` (from an open `type: cross-fact` record) gets the other participant fact(s)
**inlined in full**, not just referenced by id, each carrying its own D35 `caution` block, plus
a plain-text-prepended note on the response ("this fact is disputed; a conflicting sourced
claim exists — see below") consistent with D35's non-null-caution-notes-in-text-content rule.
For `type: verification` records the existing `caution` block's note field is sufficient (a
short sentence, no inlined second object needed) — matching the popover treatment in O6, MCP
does not need special-case machinery for the low-severity case beyond what D35 already
specifies.

**Should MCP expose a way to list/inspect open contradictions?** Recommended: yes, as a small
extension to D8's read-only tool set, in the same spirit as D15 adding `search_sources`/
`get_source_section` for a need the original D8 five tools didn't cover. Proposed shape (not
fully specified here — implementation-level tool design belongs to whichever future pass
concretizes D8's extension list): `list_contradictions(status?, type?)` returning open (and
optionally closed) records with participant fact ids, and `get_contradiction(ctr_id)` returning
the full record with both participants inlined — mirroring `get_fact`'s existing shape. This
gives agent consumers a way to proactively survey known disputes (useful for an agent about to
draft a *new* claim on a contested subject — it can check first rather than discover the
conflict only after its own claim collides with an existing one) rather than only encountering
contradiction content reactively via `get_fact`.

## Recommendation

*Proposed* package:

1. **Two record types sharing one schema (O1b):** `type: verification` (a fact vs. one of its
   own citations — low severity, mechanical, common) and `type: cross-fact` (two independently
   verified facts disagreeing — the D5-originated, high-severity, rare case). One shared shape,
   one storage file, one resolver, differentiated governance and rendering weight.
2. **Content-keyed identity (O2b):** `ctr-<12-hex SHA-256>` over a canonical string per type
   (sorted participant fact ids, or fact+citation for verification-type), giving independent
   concurrent-commit processes automatic dedup — mirroring D23's fact-id scheme exactly. Stored
   in one root-level `contradictions.yaml`, sibling to `tombstones.yaml`, mutable `status` field
   (git history is the audit trail, no in-record change log needed), no sharding needed at
   projected volume.
3. **Minting restricted to three mechanical sources (O3):** the D24 verifier (only when the
   fact stays admitted via a different citation — a contradicted-primary-citation fact is never
   admitted and never gets a record), the D5 reconciler/debate outcome, and human-challenge
   resolution sessions producing a genuine counter-fact — plus a **new, separately-scoped**
   periodic cross-fact scan job (flagged, not designed, below) to catch conflicts between facts
   admitted in different pipeline runs. The controversy assessor never mints records itself,
   preserving its structured-input-only lane (D25).
4. **Closure (O4):** automated since/version-qualification check at mint time (the D5-named
   common case, closing the record immediately with no visible dispute state); auto-closure on
   participant correction via a tombstone cross-reference; human-challenge adjudication
   (qualify, correct, or explicitly confirm-as-genuinely-open); indefinite open status as the
   correct default for real field disagreement, re-checked only on new-source-ingestion events.
   Closed records are never deleted — they persist as audit content; the live `dispute` axis is
   always a derived read of currently-*open* records only.
5. **`partial` verdicts do not mint contradiction records (O5)** — corrects the checklist's own
   phrasing. `partial` and `contradicted` are mutually exclusive by D24's own decomposition
   rule (a contradicted assertion always bubbles the whole verdict to `contradicted`); partials
   get their own filterable build-side log per D24's existing ratification and continue
   feeding the controversy assessor as an input, unchanged from D24/D25's current design.
6. **Site rendering (O6):** verification-type records add one short clause to the existing
   D25-axis popover line; cross-fact records get a compact "Sources disagree" block inside the
   same popover, both riding brainstorm 19's shared base-page glyph with no new page chrome. A
   dedicated `/disputed/` index of open cross-fact records is proposed as a content/positioning
   opportunity but left as an open question rather than folded into the core recommendation.
7. **MCP rendering (O7):** `get_fact` on a `dispute: contradicted` fact inlines the conflicting
   participant fact(s) in full (mirroring the D35/29 tombstone-inlining precedent), each with
   its own `caution` block; a new small `list_contradictions`/`get_contradiction` read-only tool
   pair extends D8's set for proactive agent-side dispute discovery.

### Worked example: the schema in full

```yaml
# contradictions.yaml — sibling ledger to tombstones.yaml (D23); mutable `status`,
# git history is the audit trail (D1/D9); one file, both types, content-keyed ids.

# --- example 1: verification-type, low-severity, auto-resolved a week later ---
- id: ctr-1a2b3c4d5e6f
  type: verification
  status: superseded
  opened:
    mechanism: verifier
    run_id: 2027-02-01-verify-batch-041#msg-12
    date: 2027-02-01
  participants:
    - fact_id: f-aa11bb22cc33
      anchor: "fi.c.generics#exists"
  failing_citation:
    source: some-outdated-c-faq
    locator: "#generics"
    rationale: >-
      Located text discusses C++ template generics, not C; claim as cited is
      contradicted by the retrieved passage.
  summary: >-
    A secondary citation for "C has no generics" was found on re-read to be
    about C++ templates, not C. The fact remains admitted via its primary
    tier-A citation (ISO/IEC 9899:2023, §6.7.9).
  controversy_signal: false        # verification-type records never feed the assessor
  closure:
    resolved_at: 2027-02-08
    resolution_kind: participant-corrected
    tombstone_ref: null            # the failing citation was dropped in-place, not tombstoned
    note: "failing citation removed from record; see commit 9c1f0a2"

# --- example 2: cross-fact, dissolved instantly by the mechanical qualification check ---
- id: ctr-2b7e9f10c4a3
  type: cross-fact
  status: dissolved
  opened:
    mechanism: reconciler
    run_id: 2027-03-02-sweep-python-021
    date: 2027-03-02
  participants:
    - fact_id: f-3f9a1c04b2d7
      anchor: "fi.python.pattern-matching#since"
    - fact_id: f-91b2c4d8e610
      anchor: "fi.python.pattern-matching#status"      # a different Python *version's* record
  qualification_check:
    attempted: true
    result: dissolved
    note: >-
      Participant a asserts pattern matching present since 3.10; participant
      b asserts absent, sourced against 3.8 documentation. Ranges do not
      overlap — not a contradiction.
  controversy_signal: false
  closure:
    resolved_at: 2027-03-02          # same day; automated, at mint time
    resolution_kind: qualified-non-contradiction

# --- example 3: cross-fact, genuine open field dispute ---
- id: ctr-7f2a9c14b3e0
  type: cross-fact
  status: open
  opened:
    mechanism: contradiction-scan
    run_id: 2027-04-11-ctrscan-014
    date: 2027-04-11
  participants:
    - fact_id: f-c001d002e003
      anchor: "edge.hurts.checked-exceptions.maintainability#a-2027-01-claude-1"
    - fact_id: f-f004a005b006
      anchor: "edge.improves.checked-exceptions.maintainability#a-2027-03-kimi-2"
  qualification_check:
    attempted: true
    result: inconclusive
  summary: >-
    Independent quality assessments of checked exceptions' effect on
    maintainability disagree: one tier-A study finds a positive effect on
    large codebases, another tier-B retrospective finds a negative effect —
    a live disagreement in the literature, not a scoping artifact.
  controversy_signal: true          # feeds D25 assessor as signals: [contradiction:ctr-7f2a9c14b3e0]
  closure_attempt:                  # a human looked and confirmed it's genuinely open (O4 path 3b)
    - date: 2027-05-02
      by: human-challenge
      issue: 214
      outcome: confirmed-open
      note: "both sources are legitimate and reach opposite conclusions; leaving open."
  closure: null
```

This resolves the topic's own crux concretely: example 1 shows a fact-vs-its-own-source event
that never rises above provenance detail; example 3 shows the kind of standing, sourced,
site-worthy disagreement the `dispute: contradicted` axis and controversy level 3 actually exist
for; example 2 shows D5's "many dissolve via since/version qualification" happening exactly as
promised, leaving an audit trail without ever becoming visible dispute content.

## Open questions for the developer

1. **The core type split (O1b)** — does splitting `contradicted` into `verification` (fact vs.
   its own citation) and `cross-fact` (fact vs. fact) match your intuition for what "a
   contradiction" means on this project, or did you picture D24's `contradicted` verdict itself
   as already the site-visible dispute signal, with cross-fact conflicts as a separate concern
   entirely (a three-way split rather than two)?
2. **`partial` verdicts excluded from the register (O5)** — accept that `partial` and
   `contradicted` are mutually exclusive under D24's own fold rule, and that partials belong in
   a separate filterable log rather than the contradiction register? This directly corrects the
   checklist topic's own phrasing.
3. **The new contradiction-scan job (O3.3)** — is a periodic scan comparing newly admitted
   facts against the existing corpus on the same subject an acceptable new pipeline component
   to add (flagged as its own future topic, not designed here), or would you rather cross-fact
   contradictions between facts from different pipeline runs simply go undetected until a human
   challenge or coincidence surfaces them?
4. **Dedicated `/disputed/` page (O6)** — worth building as a content/positioning feature
   (leaning into "genuinely unsettled questions" as compelling reading, per brainstorm 12's own
   framing), or does it cut against D10's minimal-surface-area ethos strongly enough to leave it
   as popover-only indefinitely?
5. **Since/version qualification check scope (O4 path 1)** — is a mechanical since/status-range
   comparison the right first-pass filter, or should its scope extend to comparing any other
   structured scoping fields (e.g. dialect/edition, platform) beyond `since`/`status` at v0?
6. **Human-challenge-confirmed-open status (O4 path 3, `closure_attempt`)** — should a
   human-confirmed-genuinely-open contradiction carry any different weight in the controversy
   assessor's rubric than a machine-discovered one that's never been human-reviewed (the schema
   as drafted just logs the attempt; D25's rubric wasn't designed with this input in mind)?
7. **MCP tool extension (O7)** — add `list_contradictions`/`get_contradiction` now as part of
   this topic's implementation, or defer them to whichever future pass formally extends D8's
   tool list (the same way D15 did), with `get_fact` inlining as the only day-one MCP surface?

## New brainstorm topics surfaced

- **Cross-fact contradiction scan job design** — the concrete candidate-generation, cadence,
  and cost analysis for the periodic job proposed in O3.3 (which newly-admitted facts to
  compare against which existing facts — likely anchor-family/same-subject filtering plus an
  embedding-similarity candidate pool, then an LLM comparison call analogous to but distinct
  from D24's entailment call). Not designed here; needs its own brainstorm before it's built.
- **`/disputed/` index page as a positioning/content feature** — if the developer likes the
  idea raised in O6/open question 4, this deserves its own site-design pass (IA, how many
  cross-fact records are expected at launch, whether it's worth building before there's enough
  content to populate it) — candidate for folding into the existing website-deep-dives lineage
  (brainstorm 19) or the launch-positioning topic rather than standing alone.
- **MCP tool-set extension tracking** — this topic (O7) is the second brainstorm after D15 to
  propose adding tools to D8's original five-tool read-only set; worth a lightweight standing
  note (or its own small topic) tracking the full extended tool list in one place rather than
  letting each brainstorm that needs a new tool re-derive D8's boundary from scratch.

## Sources

No new external sources introduced; every constraint traces to D1–D25/D35 and brainstorms 04,
09, 11, 12, 19, 29. Jordan, H., et al. (2015) — cited already in `CLAUDE.md` and reused in
brainstorm 12 — remains the intellectual anchor for treating genuine cross-fact disagreement
(the `type: cross-fact`, indefinitely-open case in O4) as first-class content rather than a
defect to resolve away: feature/quality value is application-dependent, so an unresolved
disagreement between tier-A sources is frequently the correct, honest end state, not a pipeline
failure.
