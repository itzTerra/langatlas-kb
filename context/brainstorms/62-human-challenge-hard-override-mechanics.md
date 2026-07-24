# 62 — Human-Challenge Hard-Override Mechanics

> Backlog brainstorm for LangAtlas. Topic (checklist item 62): design the concrete mechanism for
> D9's 2026-07-20 amendment — "an accepted human challenge is a hard override... no subsequent
> machine verdict can reinstate a value a human challenge overturned." Binding context: D9
> (challenge channel, GitHub-issue-form intake, resolution loop landing through the normal
> verification gate); D23 (content-keyed `f-<12-hex>` fact ids, anchor = `(record-id)#(field-path)`,
> append-only root `tombstones.yaml`, verifier verdicts live in a build-side ledger *not* written
> back into authored YAML); D24 (verifier — filter ladder, `since`/`as-of` back-dating split);
> D25 (three orthogonal status axes, event-driven re-verification with challenge resolutions as
> one of five named triggers, `dispute` axis derived from currently-open records only); D36
> (agent-runner commit protocol, `LangAtlas-Record-Key`/`LangAtlas-Chat-Run-Id` commit trailers,
> auto-revert's four-condition gate); D45 (`contradictions.yaml` — the precedent for a root ledger
> *sibling* to `tombstones.yaml` rather than an overloaded field, content-keyed id, mutable
> `status`, closed-not-deleted). This is a **Stage-6 hard gate** (spec.md §15): must land before
> the first `challenge-fact.yml` resolution, since the rule has no teeth without it. All proposals
> below are *proposed*, not ratified, per the project's decision-hygiene convention.

## Problem framing

D9's amendment is a one-sentence policy with no designed mechanism. Four consultation points were
named in spec.md §14 U4 as needing to respect it, and none of them currently has any way to know
a value was human-locked:

1. **Where is the override recorded** — a new field on the canonical fact/anchor, or a ledger
   record sibling to `tombstones.yaml` (matching D45's precedent for `contradictions.yaml`)?
2. **How does the D24 verifier consult it** — before admitting a machine-drafted correction to an
   anchor, how does it know that anchor is currently human-locked?
3. **How does the `since`/`as-of` back-dating pipeline (D24) consult it** — back-dating is
   monotone-earlier-only and source-first; does a lock block back-dating touching that anchor at
   all, or only block content-value changes?
4. **How does D36's auto-revert consult it** — auto-revert's four conditions (main's tip, bot
   author, deterministic validator failure, clean revert) don't currently exclude reverting a
   challenge-resolution commit that happens to trip an unrelated validator.
5. **How does this interact with D25's event-driven re-verification** — challenge resolutions are
   already one of D25's five re-verification triggers; what happens when a *later*, unrelated
   trigger (verifier version bump, migration) re-verifies a locked anchor and produces a `failed`
   verdict?

A fact making this concrete: fact ids are **content-keyed** (D23 — `f-<12-hex SHA-256 of the
canonical claim string>`). This means "reinstating an overturned value" isn't hypothetical drift —
it's a specific, mechanically exact event: some later process (debate re-run, back-dating,
independent re-sweep) computes the *same* claim string the human challenge overturned, which
hashes to the *same* fact id, and writes it back to the anchor. Content-addressing makes the
reinstatement check exact (a fact-id equality test) rather than fuzzy — the design should exploit
this rather than build something approximate.

**Scale grounding**: this is a low-volume, high-stakes path — human challenges are rare relative
to the sweep pipeline's fact volume (D9 assumes a handful of GitHub-literate domain experts, not a
crowd), so the mechanism can afford to be conservative (block first, ask later) without a
throughput concern anywhere in this design.

## Options with trade-offs

### O1 — Where the override lives

**O1a (recommended) — a new root ledger, `overrides.yaml`, sibling to `tombstones.yaml` and
`contradictions.yaml`.** Append-friendly, content-keyed like both siblings (`ovr-<12-hex SHA-256>`
over `anchor + challenge_issue_url`), one entry per anchor-lock event:

```yaml
- id: ovr-a1b2c3d4e5f6
  anchor: fi.rust.pattern-matching#characteristics[c-exhaustive]
  locked_value: f-9f8e7d6c5b4a      # the human-set fact id, now protected
  overturned_value: f-1a2b3c4d5e6f  # the fact id the challenge overturned
  challenge_issue_url: https://github.com/langatlas/kb/issues/482
  chat_run_id: run-2026-07-30-0007  # D18 link to the resolution transcript
  resolved_at: 2026-07-30T14:02:00Z
  status: locked                    # locked | superseded (see O5)
```

This mirrors D45's own reasoning for splitting `contradictions.yaml` out from `tombstones.yaml`
rather than overloading it: a tombstone records *that* content changed (any correction, agent- or
human-driven) and is consumed for chain-walking/superseding lookups; an override records *that a
human, specifically, is now the only party allowed to change this anchor* — a different question
with a different set of consumers (verifier admission gate, back-dating pipeline, auto-revert),
not the same "old id → new id" bookkeeping tombstones already do. Keeping them separate avoids
retrofitting a `hard_override: true` flag onto every tombstone-consuming code path that has no
reason to care about it.

**O1b — rejected: a field on `tombstones.yaml`'s existing entries.** Tombstones already fire on
every ordinary correction (agent-authored, verification-gated, no special status). Adding a
`hard_override` boolean to that shared schema means every consumer of `tombstones.yaml`
(chain-walking for `get_fact`'s tombstone-inlining per D35/D29, the `since` back-dating pipeline,
build tooling) now has to filter on a flag it previously had no reason to inspect, and a
tombstone's existing "closed, historical record" framing doesn't naturally carry "and also, block
all future writes here" — that's an active constraint on *future* commits, not a passive record of
a *past* one, which is why O1a's separate ledger with a `status: locked` field (mutable, unlike
`tombstones.yaml`'s append-only entries) is the better fit.

**O1c — rejected: a field on the canonical fact/anchor's own YAML.** D25 already ratified that
verifier verdicts "live in a build-side ledger... not written back into authored YAML" specifically
to keep authored content and machine-derived status separate; a `locked_by_human: true` field on
the record itself would blur that line the same way, and — more concretely — D23's anchors are
`(record-id)#(field-path)` pairs, many of which point at list-entry sub-keys
(`characteristics[c-exhaustive]`) with no natural place to hang a sibling boolean without changing
the list-entry schema itself. A root ledger keyed by anchor string sidesteps this entirely.

### O2 — Lock granularity: whole anchor, or specific overturned value only?

This is the sharpest reading question in D9's one-sentence amendment. "No subsequent machine
verdict can reinstate **a value a human challenge overturned**" is literally about one specific
overturned fact id, not a blanket freeze on the anchor.

**O2a (recommended) — lock the whole anchor, not just the overturned fact id.** Reasoning: the
narrow reading (block only the exact overturned content) is under-protective given content-keyed
ids. A machine process that disagrees with the human's correction wouldn't necessarily re-derive
the *exact same* overturned claim string — it might derive a *third* value, still wrong, still
against the human's judgment, and a narrow per-fact-id blocklist would wave it through because it's
neither the locked value nor the overturned one. The practical intent of "an accepted human
challenge is a hard override of anything machine-decided about the fact" (D9's own framing, not
just the reinstatement clause) reads as *anchor-level* authority transfer, not a one-value
denylist. Mechanically: any machine-authored commit that would change `overrides.yaml`'s
`locked_value` for a given anchor is refused outright, full stop, until a *new* human-challenge
resolution session updates the lock itself (O5).

**O2b — rejected: narrow per-fact-id blocklist only.** Technically satisfies the letter of D9's
sentence but not its evident spirit, and is strictly weaker for equivalent implementation cost —
the anchor-level lock is not more work to build (same ledger, same lookup key), it's just a
stricter equality check (`anchor` alone vs. `anchor` + `candidate_fact_id == overturned_value`).
Rejected as leaving a gap for no savings.

**Consequence for downstream field like `since`**: a locked anchor's `since` field is covered by
the same lock (O2a's "any machine-authored commit... refused outright") — the back-dating
pipeline (O4 below) cannot adjust a locked anchor's `since` independently of its content value,
even though back-dating is a narrower, more mechanical operation than a full content correction.
If a human-resolution session also needs to correct `since`, it does so as part of that same
challenge-resolution commit (O5), not as a separately-triggered back-dating run.

### O3 — Consultation point: the D24 verifier / D5 reconciler admission gate

**O3a (recommended) — a pre-commit lock check, ahead of the normal verification gate, on every
machine-authored write path that would touch an anchor's content.** Concretely: any commit
originating from the D5 debate/reconciler machinery, D24's verifier admitting a fresh claim, or the
D45-named contradiction-scan/dissolution paths, resolves the target anchor(s) first and looks them
up in `overrides.yaml`. A `status: locked` hit refuses the write outright — the draft correction
never enters the verification gate at all, reported with a new terminal status,
`blocked_by_human_override`, matching D36's existing vocabulary shape for other terminal halt
states (`contention_exhausted`, `blocked_red_main`). This is a gate *in front of* D24's verifier,
not a change to the verifier's own filter ladder — the verifier never even sees a blocked draft.

**Only a new human-challenge-resolution session (D9's own resolution loop) is exempt** — it is, by
construction, the one path allowed to update `overrides.yaml` itself (O5), so its own commit is
never checked against the lock it is simultaneously updating.

**O3b — rejected: teach the verifier's filter ladder a new stage.** Folding the lock check into
D24's filter ladder (alongside registry/schema checks, locator resolution, quote-fuzzy-match)
would conflate "is this citation good enough" with "are you even allowed to write here at all" —
two different questions with different failure semantics (the first is about evidence quality and
worth logging per-verdict per D24's existing six-verdict scheme; the second is a hard authorization
boundary that shouldn't consume a verifier verdict slot at all). Keeping it a pre-gate check that
runs before the verifier is invoked at all is simpler and cheaper (skips an entailment call
entirely for an anchor that's locked, rather than running verification and then discarding the
result).

### O4 — Consultation point: the `since`/back-dating pipeline

**O4a (recommended) — the back-dating pipeline resolves anchors the same way as O3a, before
computing any `since` adjustment, and skips locked anchors entirely (not a partial "only skip the
content, still back-date `since`" carve-out).** Per O2a's resolution, a lock covers the whole
anchor including `since`; the back-dating run's per-fact loop adds one lookup (identical
`overrides.yaml` anchor check) before it computes a `since_status` for a candidate fact, and simply
excludes locked anchors from that run's batch — no special-cased partial-write logic needed, since
"skip this fact entirely" is the same shape as any other exclusion the batch already has to handle
(e.g. facts with `source-unavailable` verdicts already don't get back-dated).

**O4b — rejected: let back-dating touch `since` on locked anchors since it's "just a timestamp,
not the claim content."** Rejected per O2a's anchor-level reasoning — `since` is part of what the
human's resolution session commits when relevant, and treating it as a carve-out reopens exactly
the narrow-reading gap O2a closed for the main content value.

### O5 — How a lock is updated or released

A lock can't be permanent-forever in a literal sense — a later human challenge might legitimately
re-open and re-correct the same anchor again (a second expert disagrees with the first, or new
information surfaces). D9's resolution loop already provides the only legitimate update path.

**O5a (recommended) — a new human-challenge resolution targeting an already-locked anchor updates
the existing `overrides.yaml` entry in place** (new `locked_value`, `overturned_value` set to the
*previous* `locked_value`, fresh `challenge_issue_url`/`chat_run_id`/`resolved_at`), rather than
appending a second entry. Anchors are 1:1 with at most one live lock, so update-in-place (mutable
`status`/value fields, matching `contradictions.yaml`'s own mutable-`status`-on-an-otherwise-stable
record precedent from D45) is simpler than chaining a list of historical lock entries — full
history of *why* the anchor changed is already in git log + the D18 chat-transcript link, so
`overrides.yaml` itself doesn't need to be its own audit trail of every past lock, just the current
one.

**O5b — mechanism for the resolution session itself to know it's allowed to write past a lock.**
The commit-time check (O3a) explicitly names "a new human-challenge-resolution session" as the one
exempt path — mechanically, this needs the same kind of provenance tag D36 already uses
elsewhere: a commit trailer, e.g. `LangAtlas-Challenge-Id: <issue-number>`, alongside D36's
existing `LangAtlas-Record-Key`/`LangAtlas-Chat-Run-Id` trailers. The pre-commit lock check (O3a)
permits a write to a locked anchor **only** when the commit carries this trailer *and* the
referenced GitHub issue is a legitimate `challenge-fact.yml`-sourced issue in a resolved state —
without this, "is this commit exempt" would otherwise have to infer intent from context, which is
exactly the kind of ambiguity a hard gate shouldn't have.

### O6 — Consultation point: D36's auto-revert

**O6a (recommended) — add a fifth condition to D36's existing four-condition auto-revert gate:
the failing commit must not carry a `LangAtlas-Challenge-Id` trailer (O5b).** D36's auto-revert
already fires only when all four of {main's tip, bot author, deterministic validator failure
reproduced once, clean revert} hold; a human-challenge-resolution commit is bot-authored (per D9's
resolution loop — an agent session re-argues and commits) so it can satisfy the first three
conditions by accident if it trips some unrelated deterministic validator (a schema lint, a
referential-integrity check unrelated to the override itself). Without this carve-out, auto-revert
could silently erase a just-landed human override the same run it was created, which would be
exactly the failure this whole brainstorm exists to prevent — and worse, silently, since D36's
auto-revert is designed to not require human involvement for the common case. Any unmet condition
already halts the runner and files an issue (D36) rather than reverting — the same fallback applies
here: a challenge-resolution commit that fails validation halts and gets a filed issue instead of
being auto-reverted, so a real validator problem in the human's own correction still surfaces, just
not through silent auto-revert.

### O7 — Consultation point: D25's event-driven re-verification

**O7a (recommended) — re-verification is not blocked from running on a locked anchor, but its
output cannot trigger any content-changing commit there; a `failed` verdict on a locked anchor
becomes a flagged status only, not a reversion.** This falls out mostly for free from D23's
already-ratified separation of verifier verdicts (build-side ledger) from authored content
(canonical YAML) — a re-verification run recomputes `verification` status for display, and that
status axis was never the thing that rewrites content in the first place; the actual risk surface
is narrower than "re-verification could revert the fact," it's specifically "a *reconciler* action
triggered in response to a `failed`/`contradicted` re-verification verdict could try to write a
correction," which is already covered by O3a's pre-commit gate on any content-changing write path.
Net effect: a locked anchor can display `verification: failed` (built honestly, per D24's published
error-rate philosophy) while its content stays exactly what the human set — status and content
diverging is an accepted, visible state, not a bug, and existing site chrome (D25's status
popover, D45's `caution` blocks) already has a slot for "verification and human correction
disagree" without new UI design being owed here.

**Consequence for D25's `dispute`/`controversy` axes**: a locked anchor that also has a `failed`
re-verification result should probably surface *something* distinguishing "human overrode the
machine, machine still disagrees" from an ordinary `disputed`/`unsettled-in-the-field` controversy
level — but per D45's 2026-07-20 withdrawal (no human-challenge-derived signal may feed the
controversy assessor), this can't flow into the ordinal controversy score itself. Filed as an open
question below rather than resolved here, since it's a presentation-layer decision (does the site
show a distinct "human-locked, machine disagrees" glyph, or does the existing verification-status
popover already say enough) more than a mechanics one.

## Recommendation

*Proposed* package:

1. **Storage (O1):** a new root ledger `overrides.yaml`, sibling to `tombstones.yaml` and
   `contradictions.yaml`, content-keyed id (`ovr-<12-hex>` over anchor + challenge issue),
   `status: locked | superseded`, holding `anchor`, `locked_value`, `overturned_value`,
   `challenge_issue_url`, `chat_run_id` (D18 link), `resolved_at`.
2. **Granularity (O2):** anchor-level lock, not a narrow single-fact-id blocklist — any
   machine-authored write to a locked anchor (content or `since`) is refused until a new
   human-challenge resolution updates the lock.
3. **Verifier/reconciler gate (O3):** a pre-commit lock check ahead of D24's verifier and D5's
   reconciler on every machine-authored write path; a hit refuses the write with a new terminal
   status `blocked_by_human_override`, mirroring D36's existing halt-state vocabulary. The check
   never touches the verifier's own filter ladder.
4. **Back-dating pipeline (O4):** the same anchor-lock check runs before any `since` computation;
   locked anchors are excluded from a back-dating batch entirely, no partial timestamp-only
   carve-out.
5. **Lock update path (O5):** a new human-challenge resolution updates the existing entry in
   place (mutable `status`/value fields); the resolution commit is marked exempt from the O3 gate
   via a new `LangAtlas-Challenge-Id` commit trailer (alongside D36's existing trailers),
   validated against a real resolved `challenge-fact.yml` issue.
6. **Auto-revert (O6):** add a fifth condition to D36's existing four — never auto-revert a commit
   carrying `LangAtlas-Challenge-Id`; such a failure halts the runner and files an issue instead,
   same as any other unmet auto-revert condition.
7. **Re-verification (O7):** re-verification keeps running on locked anchors and can produce a
   `failed`/`contradicted` display status, but no reconciler action may write a correction to a
   locked anchor (already covered by O3's gate) — status and content are allowed to visibly
   diverge; how (or whether) the site distinguishes this from ordinary disputed-status chrome is
   left as an open question, not resolved here.

This adds one new root ledger file (matching D45's own precedent for adding `contradictions.yaml`
alongside `tombstones.yaml` rather than overloading either), one new commit trailer, one new
terminal status name, and one new auto-revert condition — no new infrastructure category, and each
piece reuses a shape (ledger file, trailer, terminal-status vocabulary, four-condition gate) the
project already has multiple precedents for.

## Open questions for the developer

1. **Anchor-level lock granularity (O2)** — confirm the broader anchor-level reading (any machine
   write to the anchor is blocked, not just the exact overturned value) over the narrower literal
   reading of D9's sentence (block only that specific overturned fact id from being reinstated).
2. **`overrides.yaml` as a new root ledger vs. extending `tombstones.yaml` (O1)** — confirm the new
   sibling-ledger file over adding a `hard_override` flag to existing tombstone entries.
3. **`LangAtlas-Challenge-Id` commit trailer + auto-revert carve-out (O5/O6)** — confirm adding a
   fifth condition to D36's auto-revert gate (never revert a commit carrying this trailer) rather
   than leaving human-challenge-resolution commits to satisfy the existing four conditions like any
   other bot commit.
4. **Presentation of "locked but machine still disagrees" (O7)** — does a locked anchor with a
   `failed`/`contradicted` re-verification result need its own distinct site glyph/copy, or is the
   existing verification-status popover (D25) plus `caution` block (D45) sufficient as-is? This is
   a site-content decision, not a mechanics one, and wasn't resolved here.
5. **Does a lock ever expire or get periodically re-surfaced for review** — e.g. should a
   long-standing lock where the field has since moved on (new upstream language version, new
   sources) get flagged for a human to re-examine, or does it stay locked indefinitely until someone
   files a fresh challenge on their own initiative? No re-surfacing mechanism is proposed above;
   flagged in case the developer wants one designed.

## New brainstorm topics surfaced

None. This brainstorm resolves entirely within the mechanics named in spec.md §14 U4 and the
checklist's own framing — no sub-question here reads as large enough to warrant its own future
session; open questions 1–5 above are ordinary ratification-scale developer calls, not deferred
design work.
