# Open Questions

Updated 2026-07-18: round-3 questions (brainstorms 09, 11, 12, 13, 25, 34) were answered by the
developer and promoted to ratified decisions D23–D28 in `context/decisions.md`. Batch 14/16/17
questions were answered in a later pass the same day and promoted to D29–D31. Batch 18/19/20
questions were answered by the developer on 2026-07-19 and promoted to ratified decisions D32–D34.
Batch 26/27/28 questions were answered by the developer later on 2026-07-19 and promoted to
ratified decisions D35–D37. Batch 29/30/31 questions (filed 2026-07-19) were answered by the
developer later the same day and promoted to ratified decisions D38–D40. Batch 32/33/35 questions
were answered by the developer later the same day and promoted to ratified decisions D41–D43.
Batch 36, 37, and 38 questions were answered by the developer later on 2026-07-19 and promoted to
ratified decisions D44–D46.
Move answered questions into decisions.md with their answer rather than deleting them.

## Open Questions

None currently open.

## Deferred (waiting on a specific future trigger, no action needed yet)

- **Register `langatlas.dev` and confirm the `langatlas` GitHub org** (D17). The registrar
   check found `langatlas.dev` available (`langatlas.io` is taken; `lang-atlas.io` available
   defensively) — the actual registration and the GitHub-org name confirmation are still to do.
   Per D40, this is **not gated on topic 31's launch-readiness work or any other trigger** — it
   happens purely on the developer's own independent decision, whenever that comes.
- **Positioning paragraph wording** — drafted by topic 31/D40 (three nested lengths: hero
  paragraph, compressed derivative, D17's tagline); per D40, ship with the PLDB/Hyperpolyglot
  named-comparison sentence cut from the hero paragraph, rest of the wording as written.
- **Embedding-model choices** — D22's research-phase benchmark subphase decides per use case.
- **What threshold of "debate changed nothing" would justify simplifying the challenger round
  for some claim types?** Flagged in brainstorm 16 §2.1/open-question 2 but not resolved there
  either — needs a sharper framing before it's answerable: concretely, this is asking whether,
  once the verifier-replay counterfactual (D30) has run against enough R3/R4 schema-dispute
  debates and (later) phase-1 fact debates, a *rate* of "pre-challenge draft would have passed
  verification unchanged" — e.g. "if 90%+ of debates on quote-verified syntax claims show no
  detectable change" — should trigger auto-accepting that claim type without a challenger round
  at all (the brainstorm-04 §4 "auto-skip" idea D30 references). No such rate exists yet because
  the sweep pipeline hasn't run; revisit once D30's instrumentation has produced real numbers to
  look at, rather than trying to pick a threshold in the abstract now.
- Upvote/usage-rate rankings deferred with the Builder; votes' home and volatility decided
  then (05, 06).
- Whole-language comparison pages deferred until non-thin (06).
- `/concepts/` as separate pages vs grouping metadata — D16's Concept-first staging implies
  Concept pages will exist eventually (06, 22).
- Indexing user-generated `/library/` submissions — moot until the Builder (06).
- Challenge-resolution SLA statement — disputed badge immediate, resolution best-effort (05).
- Transcript corpus as a citable/publishable dataset — licensing + citation format decided
  with the dataset-export work (24, 15).
