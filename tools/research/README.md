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
cycle signed against the old text (`cycle status` shows `STALE`).

## Tests

```
uv --directory tools/research sync --extra dev
uv --directory tools/research run pytest -m ''   # `git`-marked tests build throwaway repos
```
