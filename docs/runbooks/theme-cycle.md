# Theme cycle runbook (Stage 3, cycles 2–12)

The ordered sequence every research-phase theme cycle runs (context/spec.md §7.4). Cycle 1 was
the shakedown the Stage 3 sub-plans were built against; every later cycle executes this file.
**Cycles change data, not code** — if a step needs a code change, that is a defect in the
sub-plan that owns the step (3A–3F); re-open it rather than patching around it here.

Checkpoints marked **[developer]** are yours; everything else is a command.

## 0. Setup for this cycle

```bash
N=2                                  # cycle number
THEME=memory-management              # a slug from research/themes.yaml
R="uv --directory tools/research run langatlas-research"
V="uv --directory tools/validate run langatlas-validate"
COV="uv --directory tools/coverage run langatlas-coverage"
SRC="uv --directory tools/ingest run langatlas-sources"
ORCH="uv --directory tools/orchestrator run langatlas-orchestrator"
```

Postgres must be up (`docker compose up -d`) for every step that touches the corpus.

## 1. Sign off — the hard checkpoint (D27)

```bash
$R themes list
$R cycle new $N $THEME               # drafts the cycle and plans its R5 language sample
```

**[developer]** Read `research/themes.yaml`'s entry for `$THEME` and the sampled languages
in `research/cycles/<NN>-$THEME.yaml`. Nothing runs until you sign:

```bash
$R cycle sign-off $N
$R cycle status $N                   # signed, not STALE
```

Editing the theme later re-opens the gate (`STALE`); re-run `cycle sign-off`.

## 2. R3 — the survey (divergent)

```bash
$R survey pool $N
$ORCH run "$PWD/config/jobs/r3-corpus-tagging.yaml" --set cycle=$N   # university API, resumable
$R survey run $N                     # checklist + surveyor (Claude)
```

**[developer]** For each proposed theme amendment: `$R themes amend $N <index>` or
`--reject`. Prefer amending a *different* theme over this cycle's own.

```bash
$R survey scout $N                   # files unevidenced gaps into the sourcing queue
```

Ingest any filed source (`$SRC new-source …` as printed, then `$SRC ingest`), then re-run `survey pool` → tagging → `survey run` → `survey scout`.
**[developer]** A gap no source can close: `$R survey drop-gap $N KEY --reason "…"`.

```bash
$R survey finalize $N                # lands the survey; cycle -> r3-done
```

## 3. R4 — drafting and debates (convergent)

```bash
$R draft atomize $N                  # the ontologist (Claude)
$R draft contested $N
$R draft debate $N --all             # contested carves only (§7.2)
$R draft verify $N                   # the D24 gate
$R draft mint $N                     # one commit per record
$R draft edges $N                    # the edge drafter (Claude)
$R draft debate $N --all
$R draft verify $N
$R draft mint $N
$R draft status $N
$R draft finalize $N                 # cycle -> r4-done
```

**[developer]** A trigger you disagree with: `$R draft waive $N KEY --reason "…"`. An
escalated debate: read `research/debates/<id>.yaml` and rule on it.

Instrumentation (read-only): `$R instrument replay $N`, `$R instrument cost $N`.

## 4. R5 — reality checks (shakedown; mints nothing, D68)

```bash
$R reality compile $N                # compiles + commits questionnaire/spec-<version>.yaml
$R reality classify $N               # one Claude session per sampled language
$R reality verify $N                 # the D24 gate; verdicts to the private ledger
$R reality status $N
```

**[developer]** Close or accept each shakedown entry:
`$R reality shakedown $N --close KEY --resolution "…"` (or `--add COMPONENT --detail "…"`).

```bash
$R reality finalize $N               # cycle -> r5-done
```

## 5. R6 — consolidation

```bash
$R consolidate open $N
$R consolidate edges $N              # cross-theme edge pass (Claude); skipped if no other theme
$R draft debate $N --all             # the new `pass: r6` entries go through 3C's machinery
$R draft verify $N
$R draft mint $N
```

**Dedup/alias audit** — **[developer]** rule on every candidate:

```bash
$R consolidate dedup $N
$R consolidate rule $N KEY --distinct --reason "…"
$R consolidate rule $N KEY --merge-into NODE --reason "…"          # drafts a manifest
$R consolidate rule $N KEY --drop-alias "ALIAS" --node NODE --reason "…"
```

**Restructures** (merge / split / remove / move). Any theme may use them; a **settled** theme
*must* (CI's guard refuses a hand restructure):

```bash
$R consolidate draft-migration $N --op merge --from OLD --to SURVIVOR --rationale "…"
$R consolidate draft-migration $N --op split --from NODE --to CHILD1 --to CHILD2 --rationale "…"
$R consolidate draft-migration $N --op remove --node NODE --rationale "…"
$R consolidate draft-migration $N --op move --node NODE --layer 3 --dimension DIM --rationale "…"
```

**[developer]** Review the drafted `ontology/migrations/<id>/manifest.yaml` — the casebook
defaults are a starting point (split → requeue, merge → remap, remove → tombstone). Split
children must already be minted (through R4/R6's gate). Edit the manifest in place, but do **not**
commit it: `consolidate migrate` lands the manifest and the corpus diff together as one commit,
and a manifest committed by hand first makes CI's guard flag the migration (the manifest is no
longer part of the migration commit). Then:

```bash
$V migrations plan ontology/migrations/<id>/manifest.yaml   # dry run
$R consolidate migrate $N <id>       # plan, gate, land as one commit
git status --short research/consolidations   # the record is now a modified, uncommitted file
git add research/consolidations/$(printf %02d $N)-$THEME.yaml
git commit -m "record migration <id>" && git push
```

**[developer]** After **every** `consolidate migrate`, commit and push the consolidation record
(`research/consolidations/$(printf %02d $N)-$THEME.yaml`) *between* migrations, before doing
anything else that lands: the migration leaves it as an uncommitted modification, and the *next*
`consolidate migrate` rebases onto origin first, which git refuses on a dirty tree (see the
failure table). Do the same push-first check before a migration whenever origin may have
advanced. After the **last** migration do not commit the record: `consolidate settle` lands it
itself, from the loaded record (see step 6).

What a drafted manifest contains, so the review knows what to look at:

- A **move** touches no facts in Stage 3: its `fact_remap` is empty. Nothing to fill in.
- A **remove** seeds an explicit tombstone entry for every dependent (fact, edge, instance) — check
  each one is really meant to die.
- The v0 interpreter refuses (a manifest hitting one of these is a `MigrationRefused`):
  more than one action per record; remapping an affects-quality edge onto a node that already
  has one to that quality; any op touching a FeatureInstance (Stage 5); a move whose `fact_remap`
  is not empty; a split whose children do not already exist; an edge-remap collision with a
  differing polarity.

**Slug polish** — **[developer]** rename where the slug no longer fits the name:

```bash
$R consolidate slugs $N
$R consolidate rename-slug $N NODE NEW-SLUG
```

## 6. Settle — R6's exit (§7.4)

```bash
$R consolidate status $N
$COV dossier                         # read before settling
$R consolidate settle $N --by "Your Name"   # --by is REQUIRED (no git-config fallback); lists
                                     # every blocker at once, or lands plan, record, cycle
$COV dossier --snapshot              # the post-settle dossier, kept under reports/ (not committed)
```

**Do not commit the carve plan or the consolidation record yourself before settling** (no
`git add -A` / commit of `research/drafts/` or `research/consolidations/`): `settle` lands both
itself, and if they are already committed its own commit fails with "nothing to commit". (The
only time you commit the record by hand is *between* migrations, step 5.)

From here on, CI refuses any commit that restructures this theme's records without a manifest.
A settled cycle file **must** carry its `theme`; a settled cycle without one is a malformed cycle
and the guard reports errors loudly rather than skipping it. Renaming a settled record's file
while keeping the same `id` is free; a rename that also restructures its content is not.

## After the cycle

- The nightly jobs keep running: verification, controversy assessment (`$R controversy assess`
  or the `nightly-controversy` job).
- `$COV gaps` is advisory and near-meaningless before Stage 5.
- `$COV dossier`: the *pipeline readiness* item reads `not-met` for as long as
  `benchmarks/d24-verifier/calibration.json` has `thresholds_met: false` (a missing input reads
  `no-data`; a corrupt one exits 2 with a message, never a traceback).
- **Stage 3 exit:** stop calling cycles when the dossier's five items are good enough for you.
  No bar is binding (D27). `1.0.0` is Stage 4's declaration.

## When something fails

| Symptom | Meaning | Do |
|---|---|---|
| `SignOffMissing` / `SignOffStale` | the gate (D27) | `$R cycle sign-off $N` after reading the theme |
| `R4Incomplete` / `R5Incomplete` / `R6Incomplete` | open work, all listed | act on each listed blocker |
| `NotAdmissible` at mint | the gate refused a carve | fix the claim or citations, re-verify, or drop it |
| `MigrationRefused … still points at` | a record left dangling | give it a remap target, requeue or tombstone in the manifest |
| `MigrationRefused … D24 gate refused` | a remapped edge is not supported | requeue or tombstone it instead |
| CI `migrations replay` FAIL | the migration commit is not the manifest's output | re-run `consolidate migrate`; never edit the commit |
| CI `consolidate guard` SETTLED | a hand restructure of a settled theme | revert it; do it through `draft-migration` / `migrate` |
| CI `ledger-check` TOMBSTONES | a tombstone line was edited or removed | restore it; the ledger is append-only |
| `consolidate settle` says `pass --by` | settling is the developer's act | re-run with `--by "Your Name"` |
| `migrate` prints `UnsafeHalt(… diagnostic='rebase conflict: … error: cannot rebase: You have unstaged changes.')` | the previous migration left the consolidation record modified and uncommitted; the rebase onto origin refuses. The new `migrate <id>` commit exists locally but is **not pushed** | commit the record, then `git push` (do not re-run `migrate`: it finds its commit already in history and reports Landed without pushing) |
| `settle stopped at research/drafts/… (CalledProcessError: Command '['git', 'commit', …` | the plan or record was committed by hand first: "nothing to commit" | re-running fails the same way. Undo the hand commit (`git reset --mixed HEAD~1` if unpushed, else `git revert` it) so the file differs from history again, then re-run `consolidate settle $N --by …` |
| CI `consolidate guard` SETTLED on a migration you ran | the manifest was committed by hand before `consolidate migrate`, so it is not in the migration commit | do not commit a drafted manifest; `consolidate migrate` lands it with the corpus diff |
| migration refused: edge remap collision | two edges collapse onto one with differing polarity | resolve by hand in the manifest (requeue or tombstone one) |
| `consolidate guard` errors on a settled cycle | that cycle has no `theme` — malformed | restore the cycle's `theme` field |

**Known limit.** `consolidate edges` truncates the other-theme node list alphabetically at the
role's `max_packet_terms`. Nodes late in the alphabet stop being offered to the cross-theme pass
as the corpus grows — a blind spot that gets worse each cycle. Until the pass is paged, spot-check
`$COV dossier` graph-health (cross-theme edge coverage) after each cycle.
