# 12 — Fact Confidence, Dissent & Staleness Model

> Brainstorm output for LangAtlas. Topic: the fact status lifecycle, confidence from source
> tier × corroboration, recorded-spread representation for quality judgments, re-verification
> cadence, the `since` back-dating pipeline, and the concrete D21 controversy-score design.
> Binding context: decisions D1–D22 (esp. D2, D3, D4, D9, D16, D20, D21) and brainstorms 04,
> 05, 08, 22. Topic 11 (claim↔source verification pipeline) runs in parallel — this document
> defines the interface it needs from topic 11 rather than duplicating that design.

## Problem framing

Every user-facing fact needs a trust story the reader can inspect: has a machine checked that
the cited source supports it (D4)? Do multiple independent sources back it? Do the sources —
or the agents — disagree? Has the ontology moved underneath it (D16)? Is a human currently
challenging it (D9)? These are **different questions with different sources of truth**, and
the round-1 sketches conflated them into single linear lifecycles (`draft → … → accepted` in
brainstorm 04; `proposed | verified | challenged | disputed` in brainstorm 05). A linear
lifecycle cannot express "verified but stale" or "verified, disputed between tier-A sources,
with one open challenge" — states that will genuinely co-occur.

Hard constraints shaping the design:

- **D9**: unchallenged facts count as **unverified by humans, not verified** — "verified" in
  this document always means *machine-verified against its cited sources*, never
  human-endorsed. There is no status that claims human endorsement, because no mechanism
  produces it (challenges correct facts; absence of challenges proves nothing).
- **D1/D13**: no human gate; every state transition must be producible by pipeline + CI alone.
  The canonical store is YAML in git (per-instance records with per-field sources, D20), so
  any state that needs to survive rebuilds must live in the record; anything whose source of
  truth is elsewhere (GitHub issues, migration manifests) must be *derived at build time*, not
  copied into canonical files where it would rot.
- **D16**: staleness is precise (migration manifests, per-fact dispositions) with the
  `ontology_version` stamp as coarse backstop, and is a *visible* fact status.
- **D2**: quality-impact judgments are attributed assessments with recorded spread, no forced
  consensus — the model must make dissent a first-class, structured, renderable thing rather
  than an error condition. Jordan et al. (2015) is the intellectual anchor: feature value is
  application-dependent, so a single consensus number would be wrong *by design*.
- **D21**: controversy is an ordinal score from a dedicated assessor agent; GitHub-challenge
  activity is explicitly a separate accompanying value. The developer wants this proposal
  sanity-checkable in concrete detail.
- **D3**: tiers A–D; community sources and tier-D are corroboration-only.
- **D6**: Claude does judgment, the university API does volume; the assessor and
  re-verification sweeps must respect that lane split.

## Options with trade-offs

### O1 — Status: one linear lifecycle vs orthogonal axes + derived display status

**Option 1a — single linear status enum** (`proposed → verified → challenged → disputed →
superseded/stale`). Simple to render, matches the round-1 sketches. But the states are not
mutually exclusive (verified+stale, verified+challenged are normal), so the enum forces
information loss and ad-hoc precedence hacks inside one field; every new orthogonal concern
(freshness, dispute) multiplies the enum.

**Option 1b — three orthogonal axes on each derived fact, plus one derived display status
(recommended).**

1. **`verification`** — owned by the topic-11 pipeline; fold over per-source verdicts (see
   the interface below): `unverified | verified | partially-verified | failed`.
   - `verified`: at least one admissible (A/B/C, non-community) source fully supports the
     claim, including its `since` value where present (D2/D4).
   - `partially-verified`: best verdict is partial support (e.g. claim supported but `since`
     unconfirmed, or hedged support).
   - `failed`: all verdicts unsupported/contradicted — such facts never enter the canonical
     store (D4), so `failed` exists only transiently in pipeline queues, never on the site.
   - `unverified`: not yet through the gate (also transient for new facts; becomes visible
     when re-verification is *pending* after a migration — see freshness).
2. **`freshness`** — owned by D16 machinery: `fresh | stale`. A fact is `stale` iff some
   migration manifest since its authored `ontology_version` touched its subject nodes with a
   disposition demanding re-verification that has not yet completed (D16 option 4b), or the
   coarse backstop trips. Staleness clears automatically when the re-verification batch lands.
3. **`dispute`** — owned by the contradiction register + supersession tombstones:
   `none | contradicted | superseded`. `contradicted`: a standing first-class contradiction
   record (D5) links this fact to a conflicting sourced fact. `superseded`: tombstone state
   (D16) — the fact carries `superseded_by` and renders only as a redirect/hub stub.

A single **display status** for site badges and MCP metadata is *derived* by precedence:
`superseded > stale > contradicted > partially-verified > verified > unverified`. The axes
travel with the fact everywhere (dataset bundle, MCP responses, JSON-LD); the display status
is a build-time convenience the site may override with its own thresholds.

Note what is *not* an axis: GitHub challenge state. An open challenge is real-time GitHub
data; baking it into canonical YAML creates a second master (the round-1 sync-back trap).
Build-time derivation handles it (see O6).

**Option 1c — axes plus a `human_endorsed` state** for facts a named expert has affirmed.
Rejected for now: D9 says no experts are lined up; an endorsement mechanism without endorsers
is dead schema, and it half-reintroduces the "unchallenged = verified" fallacy. Revisit if a
seeded expert-review program (brainstorm 08, risk P3) materializes — as provenance metadata
("reviewed-by"), not as a verification state.

### O2 — Confidence: numeric score vs ordinal lookup from tier × corroboration

**Option 2a — numeric formula** (e.g. weighted sum of tier values × log corroboration count).
Precise-looking, but the precision is fake: it invites cross-fact ranking arithmetic the
inputs cannot support, and every weight is an unarguable magic number. Also collides with the
project's stance against forced consensus.

**Option 2b — small ordinal confidence derived by lookup table (recommended).** Confidence is
a *derived, recomputed-at-build* value — never hand-edited — from exactly two inputs: the
strongest admissible backing tier and the count of *independent* corroborating sources.

| Level | Rule (evaluated top-down, first match) |
|---|---|
| `high` | verified; ≥1 tier-A or tier-B source fully supports; ≥1 additional *independent* source corroborates (any tier, community allowed) |
| `medium` | verified; exactly one tier-A/B source, no independent corroboration — **or** tier-C sole backing with ≥1 independent corroboration |
| `low` | verified; tier-C sole backing, uncorroborated — or `partially-verified` at any tier |
| (none) | `unverified` facts carry no confidence value at all |

Independence rule: two sources corroborate independently only if they share no author and no
publisher/venue (the CSL records make this checkable mechanically; borderline cases default
to *not* independent). Community sources and tier-D can only ever add corroboration — they
can lift `medium → high` and `low → medium`, but never establish `verified` (D3).

Deliberate properties: confidence never decreases because of challenges or controversy —
those are the other axes; mixing them would double-count dissent and make confidence
unexplainable. Confidence is explainable in one rendered sentence ("backed by the Rust
Reference (tier B), corroborated by PLDB"), which is the actual point.

**Option 2c — add human-confirmation as a confidence booster** (brainstorm 04's
"human-confirmed" tier). Rejected with 1c, same reason.

### O3 — Recorded spread for quality judgments

Quality-impact facts (feature→quality edges, D2) are where "no forced consensus" bites.

**Option 3a — one edge with a consensus polarity + dissent footnote.** Loses information and
forces the reconciler to pick winners — exactly what D2 forbids.

**Option 3b — assessment list on the edge record, with a derived distribution
(recommended).** The quality-edge record carries an `assessments:` list; each assessment is
one attributed, independently challengeable claim (so per D20 each derives its own fact ID):

```yaml
# inside a feature record: qualities: [...]
- quality: learnability
  assessments:
    - polarity: hurts            # improves | hurts | mixed | negligible
      source: klabnik-nichols-2023
      locator: "ch. 4"
      note: "ownership described as the steepest initial hurdle"   # ≤1 sentence, optional
    - polarity: improves
      source: some-tier-a-study-2021
      locator: "§5.2"
      note: "after the initial period, fewer memory-bug debugging sessions"
```

At build time the pipeline derives a **distribution summary** per (feature, quality) pair —
counts per polarity, strongest tier per side, e.g. `{improves: 1 (A), hurts: 1 (B)}` — which
is what the site renders ("sources disagree: 1 says improves, 1 says hurts", each linked with
its citation popover). No averaged score, no majority vote, ever. Each assessment goes
through the topic-11 gate like any fact; the *spread itself* is an input to the controversy
assessor (O5). Scope qualifiers (e.g. "hurts learnability *for beginners*") stay inside the
assessment's claim text/note rather than becoming schema — revisit if a pattern hardens.

**Option 3c — polarity plus magnitude scale per assessment.** Rejected: D2 already ratified
polarity-only for `influences`; magnitudes from heterogeneous sources are not commensurable,
and Jordan et al. (2015) warns feature value is application-dependent. `mixed` and
`negligible` polarities absorb most of what magnitude would have expressed.

### O4 — Re-verification cadence: calendar sweeps vs event triggers vs hybrid

**Option 4a — pure calendar** ("re-verify everything every N months"). Wasteful at corpus
scale, blind between sweeps.

**Option 4b — pure event-driven.** Precise but misses slow rot (source content drift under a
live URL, verifier prompt improvements).

**Option 4c — event-driven primary + slow rolling sweep backstop (recommended).**
Re-verification (always the cheap topic-11 fast path on the university API, overnight batch)
is *triggered* by:

1. **Migration manifests** (D16) — the disposition says fast-path or full re-verify; this is
   the primary staleness clearer.
2. **Source-snapshot change** — the topic-28 link-checker/freshness pass detects that a
   source's live content no longer matches its snapshot hash: re-verify every fact citing it
   (against the *new* snapshot; if support is lost, the fact keeps its verified state against
   the archived snapshot but gets flagged for the contradiction/refresh queue — sources are
   allowed to have said something at retrieval time).
3. **Challenge resolution** (D9) — the correcting commit re-runs the gate by construction.
4. **Verifier MAJOR change** — when topic 11's verifier prompt/model version bumps
   incompatibly, previously-passed verdicts are suspect; re-verify oldest-verdicts-first
   under a per-week budget rather than all at once.
5. **`since` back-dating runs** (see O4½ below).

Backstop sweep: a low-priority rolling queue re-verifies facts whose newest verdict is older
than **18 months**, ordered oldest-first with tier-C-backed and single-source facts
prioritized. Budgeted (e.g. ≤N facts/night) so it never competes with pipeline work; the
university API's latency-blindness makes this effectively free (D6). Every verdict carries
`verified_at` + verifier version, so "how old is this fact's check" is always renderable.

### O4½ — The `since` back-dating pipeline (D2)

A dedicated, later, wholly mechanical-plus-cheap-LLM pipeline; design *proposed* here:

- **Invariant:** `since` only ever moves *earlier*, and only to a value the gate has verified
  against a source. A claim that the current `since` is too *late*-stated-as-wrong arrives
  via the normal contradiction/challenge machinery, not this pipeline.
- **Mechanics:** per feature instance, a university-API agent queries the source-corpus RAG
  (D15 `search_sources`) with the feature + language + release-history vocabulary; candidate
  earlier versions become ordinary source-first claims (`source_id` + locator) that the
  topic-11 gate must verify *specifically supporting the earlier version value*. On pass, the
  record's `since` is updated and stamped `since_status: back-dated` (vs `as-cited` for the
  original sweep value). Claude is consulted only for ambiguous cases (e.g. feature existed
  earlier in a restricted form — which is usually a *new, distinct* fact, not a back-date).
- **Cadence:** batch-run per language after that language's sweep stabilizes, then re-run
  only when new sources for that language enter the corpus. It also naturally piggybacks on
  O4c trigger 2.
- `since_status: earliest-known` is deliberately *not* claimable — the pipeline can never
  prove it found the earliest; it only records the earliest *supported so far*.

### O5 — The controversy score (D21) — concrete design

This is the section the developer explicitly wants to sanity-check. All *proposed*.

#### 5.1 The ordinal scale

Five levels, 0–4. Ordinal only — levels are ranks, never arithmetic operands; the level names
are pipeline vocabulary (the site chooses its own user-facing wording and badge thresholds).

| Level | Name | Semantics |
|---|---|---|
| 0 | `settled` | No disagreement signal anywhere: verification clean, sources concordant, no debate was needed or the debate converged immediately with no standing dissent. |
| 1 | `noted-variance` | Weak, resolved signals: a debate converged only after revision (`accepted-as-revised`), or a minority assessment/partial verdict exists but is clearly outweighed (e.g. one tier-D dissent against tier-A support). |
| 2 | `contested` | Live disagreement inside the pipeline: reconciler conflicts that debate resolved with recorded standing dissent, a quality-judgment spread with credible sources on both sides but unequal strength, or partial verification verdicts on load-bearing fields. |
| 3 | `disputed` | Non-convergence: an escalated/unresolved debate, a standing first-class contradiction record, or verification verdicts that *conflict* across admissible sources (one supports, another contradicts). |
| 4 | `unsettled-in-the-field` | The disagreement is out in the literature, not an artifact of the pipeline: independent tier-A/B sources genuinely take opposing positions. Highest level ≠ "worst fact" — it marks a known open question, arguably the most interesting content on the site. |

Distinguishing 3 from 4 is the assessor's one genuinely judgment-heavy call: 3 says "the
pipeline could not settle this," 4 says "the field has not settled this." The rubric's
tiebreaker: level 4 requires opposing verdicts/assessments each backed by independent
tier-A/B sources; anything less caps at 3.

#### 5.2 The assessor agent

- **Inputs (all structured — the assessor never re-reads sources or transcripts):**
  1. Debate records (D5): outcome, round count, challenge types, standing-dissent blocks,
     escalation flag; non-convergence is the strongest single signal.
  2. Reconciler conflict records and the contradiction register (open/closed, and what closed
     them — version-qualification closures drop the signal to ≤1).
  3. Per-source verification verdicts from topic 11 (see interface): partial verdicts,
     and especially *conflicting* verdicts across sources.
  4. Source-strength context: tier and independence of each side's backing (computed
     mechanically and handed in — the assessor does not re-derive tiers).
  5. The O3 assessment spread for quality-judgment facts.
  - **Explicitly excluded:** GitHub-challenge activity (D21), page traffic, and any agent
    free text outside structured records.
- **Model & lane (D6):** the assessor is bounded classification over structured inputs — a
  volume job. Default: university API `thinker` (deepseek-v4-pro-thinking) with a fixed
  rubric prompt and a JSON output schema. **Claude is the calibrator, not the assessor**: a
  committed golden set of ~50 hand-labeled cases regression-tests the rubric (the topic-16
  harness), and two guardrails escalate individual cases to Claude: (a) the rubric's own
  self-reported ambiguity between adjacent levels, and (b) any assignment of level 3–4, which
  is rare, site-prominent, and worth judgment-tier review.
- **When it runs:** event-driven, batched nightly — re-assess a fact whenever an input
  changed since its last assessment (fact accepted/revised, debate resolved, contradiction
  opened/closed, new corroborating source verified, re-verification verdict landed). No
  calendar re-assessment: unchanged inputs give an unchanged level by construction.
- **Where the output lives:** a machine-written block in the canonical record (git is the
  database, D1), one per derived fact where signals exist (absent block = level 0):

```yaml
controversy:
  level: 3
  name: disputed
  assessed_at: 2026-09-14
  assessor: {model: deepseek-v4-pro-thinking, prompt_version: cv-1.2, escalated_to: claude}
  signals: [debate:2026-09-12-typing-gradual-07:escalated, contradiction:CTR-0142]
```

  The `signals` list is the explanation — machine references to the records that justify the
  level, renderable as links (including transcript links via D18). No free-prose rationale
  field: agent prose is not citable (D4), and the signals are the auditable justification.

#### 5.3 GitHub-challenge activity — the separate accompanying value

Computed **at build time** from the GitHub Issues API (challenge-labeled issues carry fact
IDs per D9), never stored in canonical YAML — GitHub is its source of truth and the value
must not rot in git:

```yaml
challenge_activity:            # build-artifact field, per fact
  open: 1
  resolved: 4
  last_activity: 2026-09-10
```

It ships in the dataset bundle next to `controversy` and the status axes. The site defines
its own presentation thresholds on both values independently (D21) — e.g. it may badge
`controversy ≥ 2` as "contested" and show open-challenge counts separately; that mapping is a
site concern this document deliberately does not fix. MCP responses carry both values raw so
agent consumers can apply their own caution policy.

### O6 — Interface required from topic 11 (defined here, designed there)

Topic 12 needs, per (fact, source) check, a **verdict record** with at least:

```
verdict:        supported | partially-supported | unsupported | contradicted | unretrievable
fields_checked: [presence, since, syntax, ...]        # which derived-fact fields the verdict covers
since_check:    supported | unsupported | n/a          # D2/D4: explicit since verdict
snapshot_hash:  <hash of source text the check ran against>
verifier:       {model, prompt_version}
checked_at:     <date>
```

Folding rules (owned by topic 12, applied at build): `verification: verified` iff ≥1
admissible source's verdict is `supported` covering all load-bearing fields;
`partially-verified` iff the best verdict is `partially-supported` (or `supported` with
`since_check: unsupported`); `contradicted` verdicts feed the contradiction register and the
controversy assessor rather than silently blocking. `unretrievable` triggers the O4c
snapshot-change path, and never counts as support. Whatever internal machinery topic 11
chooses (entailment prompts, quote fast paths, thresholds) is invisible here as long as this
record shape holds.

## Recommendation

*Proposed* (developer ratifies):

1. **Orthogonal status axes, not a linear lifecycle** (O1b): `verification`
   (unverified/verified/partially-verified/failed), `freshness` (fresh/stale, driven by D16
   manifests), `dispute` (none/contradicted/superseded) — plus a derived display status with
   precedence `superseded > stale > contradicted > partially-verified > verified >
   unverified`. No human-endorsement state (D9). GitHub challenge state is never a canonical
   axis; it is build-time derived (O5.3).
2. **Ordinal confidence by lookup** (O2b): `high/medium/low` from strongest admissible tier ×
   independent corroboration; community/tier-D lift but never establish; confidence is
   derived, explainable in one sentence, and never dented by controversy or challenges.
3. **Recorded spread as assessment lists** (O3b): quality edges carry attributed
   `assessments` (polarity + source + locator), each an independently challengeable derived
   fact; the site renders the derived distribution, never a vote or average.
4. **Hybrid re-verification** (O4c): event triggers (migrations, snapshot drift, challenge
   resolutions, verifier MAJORs, back-dating runs) + an 18-month budgeted rolling backstop
   sweep on the university API, oldest/weakest-backed first.
5. **`since` back-dating** (O4½): monotone earlier-only, source-first through the normal
   gate, `since_status: as-cited | back-dated`, no "earliest-known" claim, batch per language
   after sweep stabilization.
6. **Controversy** (O5): the 0–4 ordinal scale
   (`settled / noted-variance / contested / disputed / unsettled-in-the-field`), assessed by
   a rubric-driven university-API `thinker` agent over structured inputs only, with Claude as
   golden-set calibrator and escalation target for adjacent-level ambiguity and all level-3/4
   assignments; event-driven nightly batches; output committed to the canonical record as a
   machine-written block whose `signals` list is the whole justification; GitHub-challenge
   activity as a separate build-time value; presentation thresholds left to the site (D21).
7. **Topic-11 interface** (O6): per-(fact, source) verdict records with the field shape
   above; topic 12 owns the fold to fact-level `verification` and feeds `contradicted`
   verdicts to the contradiction register and the assessor.

Schema-touching consequences hand off to topic 09 (fact schema): the status axes,
`assessments`, `controversy`, `since_status`, and verdict-record shapes all need concrete
YAML schema + derived-ID treatment there.

## Open questions for the developer

1. **Controversy scale shape** (the D21 sanity check): are five levels right, and is the
   3-vs-4 distinction ("pipeline couldn't settle it" vs "the field hasn't settled it") worth
   carrying, or should 4 fold into 3 until real tier-A-vs-tier-A cases appear?
2. **Assessor lane**: is university-API-with-Claude-calibration acceptable for the assessor
   (O5.2), or do you consider controversy assessment judgment work that belongs to Claude
   outright (D6)? The proposal leans on the escalation guardrails to square it.
3. **Level-3/4 escalation cost**: auto-escalating every level-3/4 assignment to Claude is the
   conservative default; accept, or reserve Claude review for level 4 only?
4. **Backstop sweep window**: is 18 months the right rolling re-verification age, and is a
   fixed nightly budget (say, 200 facts) acceptable as the initial cap?
5. **`partially-verified` on the public site**: may partially-verified facts render publicly
   (badged), or should the site suppress them until fully verified? The proposal assumes
   render-with-badge, matching the transparency posture.
6. **Confidence vocabulary**: `high/medium/low` is deliberately plain; any preference for
   different user-facing names (the site can relabel regardless)?
7. **Snapshot-drift policy** (O4c trigger 2): confirm that a fact whose live source changed
   keeps `verified` against the archived snapshot while queued for refresh, rather than
   dropping to unverified immediately.

## New brainstorm topics surfaced

- **Contradiction-register lifecycle** — brainstorm 04 created standing contradiction
  records and this document leans on them (dispute axis, controversy signals), but nobody has
  designed their schema, closure semantics (version-qualification, supersession, agreement),
  or site rendering; candidate for folding into topic 09 or a small dedicated topic.
- **Golden set for the controversy assessor** — sourcing ~50 hand-labelable cases (including
  genuine field disputes: gradual-typing efficacy, checked exceptions, GC-vs-ownership
  learnability) before the assessor first runs; naturally joins the topic-16 harness.
- **Trust-signal UX** — the site now has up to five signals per fact (display status,
  confidence, controversy, challenge activity, verdict age); how a typography-first page
  shows them without turning into a dashboard is a real design problem (feeds topic 19 and
  the D10 badge-threshold decision).
- **MCP caution contract** — whether/how the read-only MCP surface should recommend
  agent-side handling of low-confidence/high-controversy facts (e.g. a documented convention
  in tool descriptions), so downstream agents don't treat every returned fact as equally
  settled (feeds the D8 surface and topic 26's bundle contract).
