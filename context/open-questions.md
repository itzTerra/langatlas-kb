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
U1/U2/U5/U6 were answered by the developer on 2026-07-24 and folded in as dated amendment notes
on D23 (U1/U2), D53 (U5), and D25 (U6), with the resolved shapes written into `spec.md` §§3.4,
6.2, 7.6.
Batch 62 questions (filed 2026-07-24 from brainstorm 62) were answered by the developer the same
day and promoted to ratified decision D63.
Batch 63 questions (filed 2026-07-25 from brainstorm 63) were answered by the developer the same
day and promoted to ratified decision D64.
Stage 3E planning questions (raised 2026-09-18 while validating the 3E plan against the ratified
decisions: `since` as part of the existence claim, as-of in YAML and the too-early-`since` gap,
dimension values vs features, whether R5 mints, spec location, job-entry timing, sweep
independence from reality checks) were answered by the developer the same day and promoted to
ratified decisions D65–D68; the one deferred item became backlog topic 64.

## Open Questions

1. `text/plain` ingestion is non-functional for any headerless plain-text document (the
   extractor never assigns `heading_level` to any block for this media type, so the
   `named-section` locator — the only kind a plain-text document could ever satisfy — never
   becomes admissible, and `chunk_document` always raises `ExtractionFailed`). Worth a fix
   (e.g. synthesizing a heading from the first line or filename) before `text/plain` is usable
   for any future ad hoc source, or should it just stay an unsupported media type?
2. `langatlas-sources new-source` has no way to record a source's editor role separately from
   authorship (CSL-JSON supports a distinct `editor` field, but the CLI only exposes
   `--author`). Two records in the R1 corpus (`pierce-attapl-2004`, edited by Pierce;
   `haskell-2010-report`, edited by Marlow) currently list their editor as an author instead.
   Worth adding an `--editor` flag to `new-source`/`render_source_yaml` before the corpus grows
   further, or is author-as-editor an acceptable simplification long-term?
3. `render_source_yaml`/`new-source` expose no flags for several CSL-JSON bibliographic fields
   that later ingestion has needed in practice: `container-title`, `volume`, `page` (for
   journal articles — three R1 records needed these added by direct YAML edit after the fact),
   `publisher`, and `accessed` (for webpages, though the schema already defines
   `custom.accessed`). Should Stage 3 add these flags to the scaffold tooling before the corpus
   multiplies further, given every future journal-article or webpage source will hit the same
   gap?
4. Stage 2B's Task 10 (the fully developer-authored, no-agent-assisted held-out audit slice,
   `tests/golden/verifier/held-out/items-audit.yaml`) was skipped on the developer's own
   instruction after being told what depends on it: nothing in CI, but `golden-validate
   --complete` will keep reporting one expected error (`held-out slice has 0 items`) until it
   exists, and 2D will have no independent, never-tuned-against audit slice at calibration time.
   Author it before or during 2D's calibration pass, or accept permanently skipping the audit
   entirely (in which case `validate_set`'s held-out invariant check should be relaxed to allow
   zero, rather than left as a standing, silently-ignored error)?
5. `langatlas_ingest.goldens.authoring.generate_candidates`'s locator-matching (fixed in
   `#stage-2b` for a source-id-prefix mismatch, see `git log --grep normalize.*candidate.*locator`)
   still misses candidates whose locator comes back bracket-wrapped (e.g. `[p. 125]`,
   `[§22.1]`) or otherwise punctuated differently from the bare `source_chunks.locator` format —
   observed repeatedly while authoring Task 9's batches. In every observed case the underlying
   citation was correct once the brackets were manually stripped during curation, so no bad data
   reached the committed set, but every future `golden-candidates` run will keep silently
   producing empty `evidence_chunk_ids` for otherwise-good candidates until the matcher is
   widened. Worth a follow-up normalization pass before Stage 3 leans on this tool more heavily,
   or is manual curation an acceptable permanent mitigation?
6. `langatlas-sources golden-derive-queries --out <path>` (and every other CLI command taking a
   relative `--out`/`--verifier-dir` path) resolves that path against the process's current
   working directory, which is `tools/ingest` when invoked via `uv --directory tools/ingest run
   ...` — the form every command in this plan uses. Every batch in Stage 2B that used
   `golden-derive-queries` had to move the written file from `tools/ingest/tests/golden/...` to
   the real repo-root `tests/golden/...` afterward. Worth defaulting relative `--out` paths to
   resolve against `REPO_ROOT` instead of the CWD, or documenting the gotcha directly in the
   command's `--help` text?

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
