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
ratified decisions D44–D46. Batch 39, 40, and 41 questions were answered by the developer later on
2026-07-19 and promoted to ratified decisions D47–D49. Batch 42/43/44 questions were answered by
the developer later on 2026-07-19 and promoted to ratified decisions D50–D52; the one remaining
item (external-checklist transcription) was resolved later the same day — the developer decided
to drop external-checklist coverage from the exit dossier entirely (amendments to D27/D52), since
the brief and its R0/R1 seed sources are only seed context for the research phase, not something
worth coverage-reporting.
Move answered questions into decisions.md with their answer rather than deleting them.
Batch 45/46/47/48/49 questions (filed 2026-07-19 from brainstorms 45–49) were answered by the
developer later the same day and promoted to ratified decisions D53–D57.
Batch 53/56/57/59 questions (filed 2026-07-19 from brainstorms 53, 56, 57, 59) were answered by
the developer on 2026-07-20 and promoted to ratified decisions D58–D61.
Batch 61 questions (filed 2026-07-20 from brainstorm 61) were answered by the developer later the
same day and promoted to ratified decision D62.
The 2026-07-20 spec-consolidation pass (`context/spec.md` §14) filed the four open items below
(U1/U2/U5/U6); its fifth item (U4, human-challenge hard-override mechanics) became backlog
brainstorm topic 62, and its sixth (U3, the stale Elixir line in D28's deferred list) was fixed
in place the same day.

## Open Questions

Filed 2026-07-20 from the spec-consolidation pass (`context/spec.md` §14). Items 1–2 must be
resolved during the R0 schema-authoring work (spec §15 Stage 1) — they are design gaps, not
waiting on any external trigger; items 3–4 are implementation-note clarifications owed before
the code they touch is written.

1. **U1 — Concrete schema of the consolidated `affects-quality` edge.** D23 merged the two
   quality edge types into one signed `affects-quality` edge "carrying polarity + strength",
   but no document specifies the post-consolidation record shape; brainstorms 09 and 12 still
   show two conflicting pre-consolidation sketches. To decide: the record-id pattern
   (`edge.affects-quality.<feature>.<quality>`?); whether polarity lives per-assessment (the
   recorded-spread model implies yes) or on the edge; and whether brainstorm 12's
   `mixed`/`negligible` values survive in the polarity vocabulary alongside `improves`/`hurts`.
2. **U2 — Shape of the typed notes on `status: partial` instances.** D23 keeps `partial`
   "carrying associated notes typed `limitation | extra | alternative`", but the instance
   schema only has free-text `notes:`. To decide: keyed list or not, whether each typed note is
   fact-bearing (own `sources:` and derived fact), and its sub-key grammar.
3. **U5 — Retrieval-tool mediation split for university-API agents.** D26 excludes tool loops
   from the completion channel, yet D53's `search_finding_aids` is "available to every agent
   session type" and sweep drafting needs `search_sources` lookups. The implied resolution —
   the runner mediates all retrieval for university-API roles (as the D24 verifier already
   does), while only Claude-channel sessions call tools directly — is stated nowhere. Confirm
   and write it into the D26/D53 implementation notes before the sweep drafting role is built.
4. **U6 — Authoritative verdict-fold table.** D24 says `partial`-only facts bounce and never
   enter; D25 defines fact-level `partially-verified` as "best verdict is partial support". The
   reconciliation is implied (entry via one `supported` citation while other citations returned
   `partial`, or via the `since` as-of split) but never spelled out. Write the single
   authoritative fold table from per-(claim, citation) verdicts to the fact-level
   `verification` axis (brainstorm 12 §O6's sketch predates D24's final vocabulary) as part of
   the verifier's implementation.

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
