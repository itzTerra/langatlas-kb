# 56 — Cross-Fact Contradiction Scan Job Design

> Backlog brainstorm for LangAtlas. Topic (checklist item 56): the concrete candidate-generation,
> cadence, and cost analysis for the periodic job proposed in brainstorm 37 (O3.3) that catches
> conflicts between facts admitted in different pipeline runs — a gap the D5 reconciler cannot
> see, since it only ever compares facts drafted within the same sweep run. Binding context: D45/
> brainstorm 37 (the `contradictions.yaml` schema, the `type: verification` vs `type: cross-fact`
> split, the three existing minting authorities, closure semantics, the content-keyed `ctr-`
> identity scheme — all reused verbatim here, not redesigned); D5 (reconciler scope: same-sweep-
> run only); D23 (content-keyed `f-<12-hex>` fact ids, the `record-id#field-path` anchor scheme,
> the per-instance/per-edge record layout); D24 (the six-verdict entailment pipeline this job's
> comparison call is modeled on, and explicitly distinct from — see §2.4); D26 (`source_chunks`
> embeddings, `qwen3-embedding-4b`, the provider-abstraction `RunContext`/cost log/cache); D41/
> brainstorm 32 (`tools/observability/report.py`'s subcommand pattern, the private build-side
> ledger, the `replay_verdict` shared-function precedent this topic's comparison call should
> follow); D43 (the `tools/orchestrator/driver.py` batch-spec/checkpoint pattern this job should
> slot into as one more job kind, not a bespoke scheduler). All proposals below are *proposed*,
> not ratified, per the project's decision-hygiene convention.

## Problem framing

Brainstorm 37 built the full `contradictions.yaml` schema and settled who is *allowed* to write
a `type: cross-fact` record (the D24 verifier's own narrow case aside): the D5 reconciler at
debate time, human-challenge resolution sessions, and — named but explicitly *not* designed — "a
new periodic cross-fact contradiction scan." That job's necessity is not in question; it was
ratified as an acceptable future pipeline component (D45) and is already tracked as this backlog
topic. What's missing is everything brainstorm 37 deliberately punted: **which facts get
compared against which**, how often the job runs, what it costs, and what the actual comparison
call looks like.

The gap this job exists to close is structural, not incidental. D5's reconciler is a same-batch
diffing step — it materializes when independent per-language sweep answers for the *same
sweep run* land in the same reconciliation pass. Anything that enters the corpus outside that
window is invisible to it:

- **A new language onboarded months later** (D28's phase 2/3/4 onboarding) that happens to touch
  a feature/quality edge an earlier-phase language already has a fact about, sourced from a
  different reference that disagrees.
- **A `since`-back-dating run** (D2/D25) that revises an existing feature instance's version
  scoping in a way that newly conflicts with an unrelated fact drafted at a different time.
- **A human-challenge-driven counter-fact** (D45 minting source 4) that itself gets compared
  against its *own* challenge target at mint time, but never against every *other* existing fact
  on the same subject.
- **Ontology restructuring** (D16 splits/merges) that brings two previously separate
  feature-instance records into a shape where their facts are now directly comparable, when they
  weren't before the split/merge.

Without this job, D25's controversy level 3/4 (`disputed`/`unsettled-in-the-field`) — "arguably
the most interesting content on the site" per brainstorm 12 — silently under-populates for every
disagreement that doesn't happen to route through a live debate or a lucky human challenge. The
corpus would look more settled than it is, which is a positioning risk (D19's per-fact-sourcing
wedge loses credibility if the site's own "sources disagree" surface systematically misses real
disagreements sitting quietly in already-admitted facts).

**Scale grounding, carried from brainstorm 37/12/25.** Low hundreds of ontology nodes (D27's
research-phase exit target), tens of thousands of derived per-field facts (D23's derived-ID
scheme), 14–15 languages across four onboarding phases (D28). The corpus is not static: it grows
in bursts (a whole onboarding phase lands over weeks, not a steady daily trickle) with quiet
stretches between phases and during the R3/R4 research-phase cycles that precede phase-1 onboarding
entirely (D27). Any cadence and cost design has to fit that bursty growth shape, not assume a
smooth daily arrival rate.

Three sub-problems, matching the checklist line exactly:

1. **Candidate generation** — narrowing the full fact corpus to a tractable, cheap-to-compare
   pool for any newly admitted fact.
2. **Cadence** — how often the job runs, weighed against the corpus's bursty growth.
3. **Cost analysis** — candidate-pool size vs. LLM comparison-call cost, and which provider tier
   (D6/D26) does the work.

Plus the comparison call's own design (analogous to, but distinct from, D24's entailment call)
and where findings land (reusing D45's `contradictions.yaml` shape and D41's `report.py` CLI
pattern rather than inventing new infrastructure).

## Options with trade-offs

### O1 — Candidate generation: what narrows the corpus to a comparable pool

The naive approach — compare every newly admitted fact against every existing fact — is
quadratic and wasteful: tens of thousands of facts means hundreds of millions of pairs, the
overwhelming majority of which share no subject at all (a Rust pattern-matching fact and a
Python GIL fact have nothing to conflict about). Two independent filters, applied in sequence,
each cutting the pool by roughly an order of magnitude before the expensive step:

**O1a — Anchor-family / same-subject filtering (recommended, first pass).** D23's record-id
scheme already encodes exactly the locality this job needs for free: `fi.<lang>.<feature>` for
feature-instance facts, `edge.<type>.<from>.<to>` for edge facts, with the field-path half of the
anchor (`#since`, `#characteristics[...]`, `#status`) further narrowing *what kind* of claim is
being made about that subject. Two facts can only meaningfully contradict if they assert
something about the **same subject at the same or an overlapping field granularity** — the
worked example in brainstorm 37 (Python pattern-matching `#since` vs `#status`, both on
`fi.python.pattern-matching`) is exactly this shape. Concretely: for a newly admitted fact with
anchor `fi.rust.generics#characteristics[c-monomorphized]`, the candidate pool is every other
*currently admitted* fact sharing the same record id (`fi.rust.generics`) — trivial, an indexed
lookup, zero LLM cost — plus, for edge facts specifically, every fact on the *reverse-direction*
edge if one exists (`edge.conflicts-with.a.b` and `edge.conflicts-with.b.a` assert about the same
relationship from either endpoint and must agree). This alone eliminates the overwhelming
majority of the corpus at zero marginal cost per newly admitted fact, since most facts share no
record id with each other at all.

Cross-language and cross-feature contradictions (e.g. a *quality-edge* assessment claiming
"checked exceptions hurt maintainability" vs. a different quality-edge fact reaching the opposite
verdict on a *related but not identical* feature) are not caught by same-record-id filtering
alone — this is exactly the O1b problem below.

**O1b — Embedding-similarity candidate pool over claim text (recommended, second pass, catches
what O1a can't).** For facts that pass O1a with no exact-record-id sibling to compare against
(the common case — most newly admitted facts have no same-anchor sibling at all, which is
correctly a fast no-op), and separately for cross-subject conflicts O1a structurally cannot see
(different feature-instance records making claims about the same underlying phenomenon — the
brainstorm-37 worked example 3, checked-exceptions-vs-maintainability across two different
`edge.affects-quality.*` records), embed the fact's canonical claim string (D23's per-kind claim
template — the same string the fact id itself hashes) and retrieve the top-k most similar
*existing, currently-admitted* claim embeddings, thresholded by cosine similarity, as the
candidate pool for the comparison call.

**Does this need its own embedding index, or can it piggyback `source_chunks`?** These are
different content, different lifecycle, and different consumers, and should **not** share a
table:

- `source_chunks` (D15/D26) embeds *source excerpts* (400–800-token chunks with locators) for
  retrieval and verifier entailment — its content is the raw literature, re-ingested rarely, and
  its consumer is claim↔source matching.
- This job needs to embed *fact claim strings* — short, canonical, one-sentence-per-fact
  (D23's claim templates), re-embedded every time a new fact is admitted, and its consumer is
  fact↔fact matching, a categorically different retrieval task (compare a claim's *meaning*
  against another claim's *meaning*, not a claim against source prose).
- D7 already names a **separate fact-embedding index** as a build artifact ("embed: fact cards,
  feature descriptions, source excerpts... each with `{chunk_type, ...}` metadata") distinct from
  `source_chunks` — this job's candidate pool is simply **a new use of an index the project
  already planned to build**, not a new infrastructure decision. The `chunk_type: fact` rows in
  the existing Postgres+pgvector fact index (D7) are exactly the embeddings this job retrieves
  against; no new table, no new embedding job, just an additional query pattern (`ORDER BY
  embedding <=> :new_fact_embedding LIMIT k`) against a table that will already exist for the
  site's own search box and the agent-facing RAG surface (D8's `search_knowledge`).
- **Model choice**: reuse whichever embedding model D22's fact-index benchmark selects (D27
  explicitly defers the fact-index model decision to sweep-pipeline start, separate from the
  source-corpus benchmark) — this job has no reason to pick its own model ahead of that decision;
  it just consumes the fact index's chosen embedding, whatever it ends up being.

**O1c — rejected: LLM-based candidate triage** (ask a cheap model "which of these N facts might
this new fact conflict with?" as a pre-filter instead of embeddings). Rejected as an unnecessary
LLM call sitting *in front of* the LLM call this job already needs (§2.4) — pure retrieval
(embedding similarity, which is what embeddings are for) is strictly cheaper and already
available once O1b's index exists; there is no quality gap embeddings leave that an LLM triage
step would close at this stage, since the actual judgment work (does this candidate pair
genuinely conflict) is exactly what the comparison call in §2.4 already does properly.

**Recommendation: O1a then O1b, sequenced, both feeding one deduplicated candidate pool per newly
admitted fact.** Same-anchor-family facts always enter the pool (cheap, exact, catches the
brainstorm-37 worked examples directly); embedding-similarity retrieval adds a top-k (proposed
k=10–20, tunable) pool of cross-subject candidates above a similarity floor (proposed ≥0.75
cosine on whatever model D22 selects, calibrated empirically once real fact volume exists — this
is exactly the kind of threshold D25's own re-verification and D24's own quote-fuzzy-match
thresholds were tuned by observation, not fixed a priori). A newly admitted fact with zero
same-anchor siblings and zero embedding neighbors above the floor skips the comparison call
entirely at zero cost — the expected common case for most facts, especially early in the
corpus's life when few facts exist to conflict with.

### O2 — Cadence

Three shapes considered, weighed against the corpus's bursty growth (research-phase cycles
producing few atomic facts vs. an onboarding-phase sweep landing hundreds of facts over days):

**O2a — Nightly, alongside D25's other nightly batches** (the controversy assessor, D24's
verifier batches). Simple to reason about, fits the existing "nightly batch" mental model this
project already uses everywhere (D24 §2.9, D25's 18-month backstop sweep). But nightly cadence
during quiet stretches (most of the research phase, per D27's R0–R2 subphases, where fact volume
is near zero) wastes a scheduled run finding nothing to compare, and during a burst (a whole
onboarding-phase sweep landing in days) nightly batching means a conflicting fact sits
undetected for up to 24 hours — acceptable, but not obviously the right trade-off given the job
is cheap per newly admitted fact (§O3).

**O2b (recommended) — event-driven, triggered per newly-admitted-fact batch, not calendar time.**
Every batch of facts committed by any of the three producers D45 already tracks (verifier
admission, reconciler/debate resolution, human-challenge correction) — plus this job's own
distinct trigger, *any commit to the canonical YAML store that adds a new fact anchor* — enqueues
those new facts' ids for a scan pass. This mirrors D25's own event-driven re-verification
philosophy exactly ("re-verification is event-driven... plus an 18-month budgeted rolling
backstop sweep") rather than introducing a second, inconsistent cadence philosophy into the
project. Batching at the *commit* or *sweep-run* granularity (not per-individual-fact) keeps the
job's own overhead proportional to actual corpus growth: a quiet research-phase week triggers
zero scans; an onboarding-phase sweep landing 500 facts over three days triggers a handful of
scan batches, each amortizing its embedding-index query cost across many new facts at once.

**O2c — a rolling backstop sweep**, mirroring D25's 18-month full-corpus re-verification
backstop, re-scanning the *entire* corpus periodically regardless of trigger events, to catch
anything the event-driven trigger might miss (e.g. an embedding-model swap that changes what
counts as "similar," surfacing candidate pairs the old model's threshold missed). **Recommended
as a light complement to O2b, not a replacement**: run at a long interval (proposed: annually, or
triggered whenever D22's fact-index embedding model is swapped/re-benchmarked) rather than D25's
18-month fact-freshness cadence, since this job's failure mode (a missed embedding-similarity
match) is a different risk profile from staleness (an unrefreshed source) — it degrades only when
the retrieval layer itself changes, not with the mere passage of time.

**Recommendation: O2b as the primary trigger (event-driven, batched per commit/sweep-run), O2c as
a rare backstop tied to embedding-model changes rather than a calendar interval.** No fixed
nightly/weekly/monthly cadence is proposed — it would either run needlessly during the research
phase's quiet stretches or under-serve an onboarding burst, and D25 already established the
event-driven precedent this job should follow instead of inventing a third cadence philosophy.

### O3 — Cost analysis

Per D6/D26's provider split (Claude does judgment work; the university API does volume; neither
crosses into the other's lane), this job's volume characteristics point unambiguously at the
university API doing the comparison calls, exactly as D24's entailment pipeline already does —
this is not a new provider-tiering decision, it is the same decision D24 already made, applied to
a structurally similar workload.

**Volume estimate.** Per O1's candidate generation: most newly admitted facts produce zero or a
handful of candidates (same-anchor siblings are rare per fact; embedding neighbors above a 0.75
floor are, by construction, uncommon — most facts are *not* near-duplicates of an existing
claim). A conservative estimate, calibrated against D24's own §2.9 volume language ("~1,000–4,000
(claim, citation) pairs per overnight batch" for verification): if an onboarding-phase sweep
lands ~500 new facts, and each produces on average 1–3 real candidates (same-anchor siblings +
embedding neighbors combined, after floor-thresholding), that's ~500–1,500 comparison calls per
onboarding-phase batch — comfortably inside the same order of magnitude as a single D24
verification overnight batch, using the same `deepseek`-tier model (D24's primary verifier
model), at effectively the same per-call cost. During quiet research-phase stretches the volume
is near zero (O2b's event-driven trigger fires rarely because few new facts are added). There is
no scenario in the corpus's projected lifetime (low hundreds of nodes, tens of thousands of
facts, D27's scale check) where this job's LLM-call volume approaches, let alone exceeds, D24's
own verification volume — it is a strict subset of the corpus (only newly admitted facts trigger
it) compared against a filtered candidate pool (not the full corpus), so it is structurally
cheaper than the verification pipeline it rides alongside.

**Embedding cost.** Embedding one new fact's canonical claim string per admission is a single
short-text embedding call — negligible against D15's own cost estimate for the (much larger)
source corpus ("~12–20k chunks... trivial"). Re-embedding is needed only when a fact's claim text
actually changes (a correction, per D23/D16) — copyedit-tolerant hashing (D23) already means
typo fixes don't even mint a new fact id, so they don't trigger re-embedding either.

**Where the cost shows up in `report.py` (D41).** This job's LLM-call volume and cost are exactly
the kind of number D41's `report.py cost` subcommand already exists to surface
(`claude_messages_per_accepted_fact`-style joins, segmented by job kind) — no new reporting
surface needed; this job's calls simply join into the existing D26 cost log under their own
`prompt_id` the same way every other pipeline call does, and `report.py` picks them up for free
once a `cross-fact-scan` prompt id exists in the join.

**Recommendation: university-API `deepseek` tier (matching D24's primary verifier model),
escalating to `deepseek-thinking` on ambiguous verdicts, exactly mirroring D24's own
primary/escalation-tier split** — this is not a new cost-tiering decision, it is D24's existing
one, reapplied. No cross-family drift sampling (D24's `mini` 10% check) is proposed for this job
at v0: that check exists to catch verifier-model idiosyncrasy on an admissibility-gating pipeline
where false-accepts have real consequences (a bad fact enters the public corpus); this job is
lower-stakes by construction (a missed contradiction just means D25's controversy score stays
`settled` a little longer than accurate — recoverable at the next O2c backstop or a later human
challenge, not a silent admissibility failure), so the added cost of a drift-sampling pass isn't
justified at v0. Revisit if false-negative rate (via O2c's backstop re-runs) turns out worse than
expected.

### O4 — The comparison call: analogous to, but distinct from, D24's entailment call

D24's entailment call answers: *does this cited source text support this claim?* — a
claim-vs-source-text relation, decomposed into atomic assertions with per-assertion grounding
spans, yielding one of six verdicts (`source-unavailable | locator-not-found | supported |
partial | unsupported | contradicted`).

This job's comparison call answers a structurally different question: *do these two
independently-sourced, independently-admitted claims assert something logically incompatible
about the same subject?* — a claim-vs-claim relation. The two calls share a family resemblance
(both are LLM entailment-style judgments over structured text) but cannot reuse the same prompt
or verdict vocabulary, for reasons the brainstorm-37 table already established: this job's inputs
are two *already-admissible* facts (each individually `supported` by its own tier-A/B citation),
not a claim against raw source prose, so "unsupported"/"source-unavailable" don't apply here at
all — both sides are, by definition, sourced.

**Proposed verdict vocabulary for this call (distinct from D24's six):**

```
no-conflict            # claims are compatible (including trivially — different subjects
                        # slipped through the candidate filter, or genuinely orthogonal aspects
                        # of the same subject)
qualified-non-conflict  # claims conflict on their face, but the pair carries structured
                        # since/status scoping fields whose ranges don't actually overlap —
                        # this verdict is what triggers D45's O4-path-1 automated
                        # qualification check to fire the record already `dissolved`, not
                        # `open`, at mint time (i.e. this call can settle the qualification
                        # check itself in the same pass, rather than requiring a second
                        # mechanical step afterward)
conflict                # claims genuinely disagree about the same subject at the same scope —
                        # mints a `type: cross-fact` record, `status: open`
inconclusive            # the model cannot confidently classify (ambiguous scope, underspecified
                        # claim wording) — escalates to `deepseek-thinking`, mirroring D24's own
                        # escalation-on-ambiguity policy; if still inconclusive after escalation,
                        # mint the record `open` with `qualification_check.result: inconclusive`
                        # (the same field brainstorm 37's worked example 3 already shows) rather
                        # than silently dropping the candidate pair
```

This maps directly onto D45's existing schema with **no schema changes needed**: `conflict` and
post-escalation `inconclusive` both mint `type: cross-fact, status: open`; `qualified-non-conflict`
mints `type: cross-fact, status: dissolved, resolution_kind: qualified-non-contradiction` — the
exact shape of brainstorm 37's worked example 2; `no-conflict` mints nothing at all (the
overwhelming majority of comparison-call outcomes, expected to dominate given the candidate pool
already passed an embedding-similarity floor that only guarantees *topical* proximity, not
*logical* incompatibility).

**Why the qualification check belongs inside this call, not as a separate mechanical step.**
Brainstorm 37's O4 path 1 describes an "automated check... comparing the participants'
since/version-scoping fields" as a distinct mechanical pre-step before a record would even open.
For *this job's* mint path specifically, folding that check into the same LLM call is cheaper
than a separate structured-field comparison pass: the model already has both facts' full content
in context to render a conflict/no-conflict judgment, and since/status fields are part of that
same content, asking it to also flag scope-non-overlap in the same call costs nothing extra.
(This does not change brainstorm 37's own recommendation for the *other* two minting paths —
reconciler-debate-time and human-challenge-time — where the qualification check remains a
separate mechanical step exactly as D45 already specifies; this job is simply positioned to fold
it in because it's already paying for one LLM call over the same two facts.)

**Model tier**: `deepseek` primary, `deepseek-thinking` escalation on `inconclusive` —
identical tiering to D24's own primary/escalation split (§O3 above), reusing the same
`RunContext`/cache/cost-log machinery (D26) rather than a bespoke call path.

### O5 — Where findings land

**Contradiction records.** Every `conflict`/`inconclusive`-after-escalation verdict mints (or
content-key-dedups against, per D45's `ctr-<12-hex SHA-256 of sorted participant fact ids>`
scheme) a `type: cross-fact` record in the existing `contradictions.yaml`, with
`opened.mechanism: contradiction-scan` — exactly the mechanism value brainstorm 37's own worked
example 3 already uses (`run_id: 2027-04-11-ctrscan-014`), confirming this job's output was
already anticipated by the schema and needs no new field. `qualified-non-conflict` verdicts mint
the record already `dissolved`, per D45's O4 path 1. This job adds **zero new schema** to
`contradictions.yaml` — it is a new *producer* writing into a ledger brainstorm 37 already fully
specified.

**Developer-facing triage surface.** Recommended: fold into D41's `report.py` as one more
subcommand, `report.py cross-fact-scan`, following the exact pattern D41 already established for
`sourcing-queue`/`verifier-drift` (a markdown view over a private/build-side data source, run on
demand). Concretely: `report.py cross-fact-scan` surfaces (a) how many comparison calls ran in
the last N batches, segmented by verdict, mirroring `report.py verifier`'s own "verdict
distribution" framing for D24; (b) newly opened `type: cross-fact` records since the last report
(a direct read of `contradictions.yaml` filtered to `opened.mechanism: contradiction-scan`); (c)
cost (Claude-message-free, university-API-call count and estimated cost, per §O3), joined the same
way every other `report.py` subcommand already joins D26's cost log. No new storage, no new CLI
tool, no new reporting philosophy — this is the same "reporting layer over existing logs" move
D41 already made for every other pipeline stage, extended to one more producer.

**Orchestration.** This job slots into D43's `tools/orchestrator/driver.py` as one more job kind
(a batch-spec YAML under `config/jobs/`, per D43's existing pattern), triggered by O2b's
event — new fact commits — rather than needing its own scheduling mechanism. No new orchestrator
concept is required; this is "add one enumerator function + one YAML file," exactly D43's stated
cost for a new job kind.

## Recommendation

*Proposed* package:

1. **Candidate generation (O1):** same-anchor-family filtering (free, exact, via D23's existing
   record-id scheme) as the first pass, unioned with an embedding-similarity top-k pool (proposed
   k=10–20, similarity floor ≈0.75, thresholds tuned empirically once real volume exists) over
   the `chunk_type: fact` rows of the **existing** D7 fact-embedding index — not a new index, not
   piggybacking `source_chunks` (different content, different lifecycle). Embedding-model choice
   deferred to whatever D22's fact-index benchmark (already scheduled at sweep-pipeline start,
   per D27) selects — this job just consumes it.
2. **Cadence (O2):** event-driven, triggered per commit/sweep-run that adds new fact anchors
   (mirroring D25's own event-driven re-verification philosophy) rather than a fixed nightly/
   weekly/monthly calendar cadence — the corpus's bursty onboarding-phase growth doesn't fit a
   flat calendar cadence well. A rare backstop full-corpus re-scan (proposed: annual, or tied to
   embedding-model swaps rather than a calendar interval) complements the event-driven trigger.
3. **Cost (O3):** university-API `deepseek` primary / `deepseek-thinking` escalation tier,
   identical to D24's own verifier tiering — this job's estimated volume (low hundreds to low
   thousands of comparison calls per onboarding-phase batch, near-zero during quiet research-phase
   stretches) stays a strict subset of D24's own verification volume, so no new cost-tiering
   decision is needed. No cross-family drift-sampling check proposed at v0 (lower stakes than
   admissibility gating).
4. **The comparison call (O4):** a distinct four-verdict vocabulary (`no-conflict |
   qualified-non-conflict | conflict | inconclusive`) over a claim-vs-claim relation, explicitly
   not reusing D24's six-verdict claim-vs-source vocabulary since both inputs here are already
   individually admissible facts. Folds the D45 since/version qualification check into the same
   call for this minting path specifically (cheaper than a separate mechanical pre-step given the
   model already has both facts in context), without changing brainstorm 37's separate-mechanical-
   step recommendation for its other two minting paths.
5. **Where findings land (O5):** zero new schema — writes directly into D45's existing
   `contradictions.yaml` (`opened.mechanism: contradiction-scan`, already anticipated by
   brainstorm 37's own worked example). Developer-facing triage rides D41's existing `report.py`
   pattern as one new subcommand, `report.py cross-fact-scan`. Orchestration rides D43's existing
   `driver.py` job-kind pattern, triggered by O2b's event rather than a bespoke scheduler.

The overall shape deliberately adds **no new infrastructure category** to the project — every
piece (fact-embedding index, university-API entailment-style call, `contradictions.yaml`,
`report.py`, `driver.py`) is a new *use* of something D7/D24/D26/D41/D43/D45 already committed to
building, consistent with CLAUDE.md's "boring, solo-maintainable technology" posture and D30's
own "reuse, don't rebuild" precedent for observability tooling.

## Open questions for the developer

1. **Embedding index reuse (O1b)** — confirm that a fact-claim embedding index is a separate table
   from `source_chunks` (as D7 already implies) rather than an attempt to piggyback the source
   corpus's embeddings, and that this job should simply wait on / consume whichever model D22's
   fact-index benchmark ultimately selects rather than making its own model choice now?
2. **Similarity floor and top-k (O1b)** — are the proposed starting values (k=10–20, cosine floor
   ≈0.75) reasonable defaults to tune empirically once real fact volume exists, or does the
   developer want a more conservative (lower-recall, cheaper) or more liberal (higher-recall,
   pricier) starting point given no real data exists yet to calibrate against?
3. **Cadence (O2)** — confirm event-driven-per-commit as the primary trigger over a fixed
   calendar cadence, and confirm the proposed annual/embedding-model-swap-triggered backstop
   re-scan (O2c) as an acceptable low-frequency complement rather than either dropping the
   backstop entirely or giving it its own fixed interval (e.g. matching D25's 18-month fact
   re-verification window instead of a shorter/longer one)?
4. **No drift-sampling check at v0 (O3)** — accept the recommendation to skip D24-style
   cross-family drift sampling for this job's comparison calls at v0, revisiting only if the O2c
   backstop's re-scan results suggest a meaningful false-negative rate, or would the developer
   rather build the drift check in from day one given how cheap it is relative to D24's own
   volume?
5. **Four-verdict comparison vocabulary (O4)** — does `no-conflict | qualified-non-conflict |
   conflict | inconclusive` read as the right shape, or should `qualified-non-conflict` be split
   further (e.g. distinguishing "ranges don't overlap" from "different dialect/edition" the way
   brainstorm 37's own open question 5 flagged as a possible v1 extension to the since/status-only
   qualification check)?
6. **Folding the qualification check into this job's LLM call (O4)** — acceptable to have this
   minting path's qualification check run *inside* the comparison call (asymmetric with the
   reconciler/human-challenge paths, which keep it as a separate mechanical step per D45), or
   does the asymmetry across minting paths bother the developer enough to prefer a uniform
   separate-step check everywhere, at the cost of a second pass for this job specifically?

## New brainstorm topics surfaced

- **Fact-embedding index build-out** — D7 already names a fact-embedding index as a planned
  artifact, and D22 already schedules its model-benchmark subphase, but no brainstorm has
  concretely designed the index's schema, refresh cadence, or its shared use across this job, the
  site's search box, and D8's `search_knowledge` MCP tool in one place. This topic's O1b treats
  it as a given; if the developer wants it designed before this job is built, that deserves its
  own pass rather than being derived piecemeal across three different topics' assumptions about
  it.
- **Comparison-call golden set for the contradiction-scan job** — mirroring D24's own calibrated
  golden set and brainstorm 36's golden-set authoring methodology, this job's four-verdict
  comparison call would benefit from its own small calibration set (deliberately-conflicting fact
  pairs, deliberately-qualified-non-conflicting pairs, genuine edge cases) once real cross-fact
  candidates start accumulating — flagged here rather than designed, since brainstorm 36 already
  claims the project's golden-set authoring methodology as its own scope and this should route
  through it rather than forking a parallel authoring effort.
