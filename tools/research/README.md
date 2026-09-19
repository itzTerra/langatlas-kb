# langatlas-research

Stage 3's research spine: theme cycles, the developer sign-off gate, and the node-minting path.

## What this package is for

Every Stage 3 agent role — surveyor (3B), ontologist and edge drafter (3C), reality checker
(3E) — ends by handing a **draft** to this package. Drafts are dumb data; this package turns
one into a validated, normalized record at its `context/spec.md` §3.3 path and lands it through
the D36 commit protocol, one commit per record.

No model is called anywhere in this package. That is deliberate: the minting rules are the part
of Stage 3 that must be deterministic and testable without a provider.

## The gate

`require_sign_off(cycle)` is D27's hard checkpoint — the developer signs off a cycle's theme
before anything runs. The sign-off is bound to a digest of the theme text, so editing the theme
afterwards re-opens the gate rather than silently inheriting it. Nothing technically prevents an
agent from writing a sign-off block; the gate is a checkpoint artifact the developer reads in a
diff, not an ACL.

## Commands

```
langatlas-research init                       # create research/
langatlas-research themes list
langatlas-research cycle new 1 typing         # draft cycle 1, plan its R5 language sample
langatlas-research cycle sign-off 1           # the developer checkpoint
langatlas-research cycle status
langatlas-research cycle advance 1 --to r3-done
langatlas-research validate                   # every research artifact against its schema

# R3 — one signed-off cycle, in order (each step refuses an unsigned or stale cycle):
langatlas-research survey pool 1              # freeze the candidate-chunk pool (private tier)
langatlas-orchestrator run config/jobs/r3-corpus-tagging.yaml --set cycle=1   # bulk tagging
langatlas-research survey run 1               # checklist + surveyor -> research/surveys/01-typing.yaml
langatlas-research themes amend 1 0 [--reject]   # decide each proposed theme amendment
langatlas-research survey scout 1             # file unevidenced gaps into sourcing_queue
langatlas-research survey drop-gap 1 KEY --reason "..."  # developer escape hatch, see below
langatlas-research survey finalize 1          # land survey + cycle, status r3-done
```

## R3: the survey

Candidates in `research/surveys/*.yaml` are **leads, never facts** — nothing there is citable,
and nothing there is a node. Evidence is bound by chunk id; source ids and locators are copied
from `source_chunks`, never from a model. The tagger (university API) grounds every term against
its chunk text in code; the surveyor and scout (Claude) are separate roles on purpose (§7.4).

Scouted sources are only *filed*: ingest one with the printed `langatlas-sources new-source …`
line plus `langatlas-sources ingest`, then re-run `survey pool` → tagging → `survey run` to let the
surveyor evidence what used to be a gap. Re-running `survey run` replaces the survey, so re-run
`survey scout` after it.

Applying a theme amendment edits `research/themes.yaml`, which re-opens the sign-off gate for any
cycle signed against the old text (`cycle status` shows `STALE`). **Amending the cycle's own
theme is expensive**: the pool, the tags, and the survey all answer the old theme text, so `survey
scout`/`survey finalize` refuse (`PoolStale`/`R3Incomplete`) until you rebuild the pool, re-run
the tagging job, and re-run `survey run` — which also rebuilds `theme_amendments` from scratch, so
the applied amendment's status is only recoverable from git history, not the working survey file.
Prefer amending a *different* theme (or waiting until the next cycle) over editing the one you are
mid-survey on, unless the theme text is actually wrong.

`survey drop-gap` is a **developer-only** escape hatch for a gap the scout could never close (its
proposals kept getting screened out, or the model never volunteered a `dropped` entry) — it marks
that one `unevidenced` entry `dropped` by hand so `survey finalize` can proceed. It is never called
by an agent.

## R4: drafting, debates and minting

```bash
# R4 — after `survey finalize` put the cycle at r3-done. Each step refuses an unsigned or
# stale cycle, and every provider step opens its own logged run.
uv run --package langatlas-research langatlas-research draft atomize 1    # the ontologist
uv run --package langatlas-research langatlas-research draft contested 1  # what must be debated
uv run --package langatlas-research langatlas-research draft debate 1 --all
uv run --package langatlas-research langatlas-research draft verify 1     # the D24 gate
uv run --package langatlas-research langatlas-research draft mint 1       # one commit per record
uv run --package langatlas-research langatlas-research draft edges 1      # the edge drafter
uv run --package langatlas-research langatlas-research draft debate 1 --all
uv run --package langatlas-research langatlas-research draft verify 1
uv run --package langatlas-research langatlas-research draft mint 1
uv run --package langatlas-research langatlas-research draft finalize 1   # -> r4-done
```

The carve plan (`research/drafts/<cycle>-<theme>.yaml`) is the spine: every step reads it and
writes it back, so any step can be re-run without re-running the ones before it. `draft status`
prints it.

**Nothing reaches the store except through the gate.** `draft mint` refuses an entry the D24
verifier did not admit, and refuses a contested carve that has neither a debate nor a waiver.
The developer's escape hatch is `draft waive <n> <key> --reason "…"` — never an agent's.

**Debates are for contested carves only** (§7.2). `draft contested` lists the triggers;
`draft debate` runs proposer + two challengers + a **fresh-context** moderator in its own run.
A moderator that asks for a revision or a split has it applied mechanically — its prose changes
nothing.

**Instrumentation** (D30, ephemeral, reads existing logs):

```bash
uv run --package langatlas-research langatlas-research instrument replay 1  # did debates matter?
uv run --package langatlas-research langatlas-research instrument cost 1    # what did they cost?
```

## R5: reality checks

```bash
# R5 — after `draft finalize` put the cycle at r4-done. Each step refuses an unsigned or stale
# cycle, and every provider step opens its own logged run.
uv run --package langatlas-research langatlas-research reality compile 1    # compile + commit the questionnaire
uv run --package langatlas-research langatlas-research reality classify 1   # one Claude session per sampled language
uv run --package langatlas-research langatlas-research reality verify 1     # the D24 gate; verdicts to the ledger
uv run --package langatlas-research langatlas-research reality status 1     # cells, findings, open shakedown entries
uv run --package langatlas-research langatlas-research reality finalize 1   # -> r5-done
```

The reality check (`research/reality-checks/<cycle>-<theme>.yaml`) is the spine, like R4's carve
plan: every step reads it and writes it back, and `reality classify --language <l> --redo`
re-runs a single language.

**R5 is a shakedown, not a sweep, and it mints nothing (D68).** The cycle's rotating
4–5-language sample answers the theme's slice of the compiled questionnaire (D46). Every answer
passes through the real D24 gate, with `since` verified inside the existence claim (D65). An
as-of `since` is accepted only when it is the version its citation documents (D66). The cells
are recorded, never landed in `languages/`.

**The shakedown log is R5's second output.** Friction in the compiler, the questionnaire format,
the verifier or the sources is filed automatically. The developer adds and closes entries by
hand:

```bash
uv run --package langatlas-research langatlas-research reality shakedown 1 --add sources --detail "…"
uv run --package langatlas-research langatlas-research reality shakedown 1 --close s-sources-1a2b3c4d --resolution "…"
```

A dimension's values are its member features (D67), so every finding is read from the cells, and
only verified answers count.

## Tests

```
uv --directory tools/research sync --extra dev
uv --directory tools/research run pytest -m ''   # `git`-marked tests build throwaway repos
```
