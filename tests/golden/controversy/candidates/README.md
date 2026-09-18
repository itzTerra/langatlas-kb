<!-- tests/golden/controversy/candidates/README.md -->
# Controversy golden candidates (uncurated)

§6.4's **opportunistic lane**. Every Claude escalation review the assessor runs is appended here
as a case with `curated: false` and `expected_level` seeded from Claude's answer.

Nothing in this directory is scored. `load_controversy_cases` globs
`tests/golden/controversy/*.yaml` non-recursively, so a subdirectory is invisible to it — and an
uncurated case it *could* see would be rejected outright.

To promote a case: read its `inputs`, decide the level yourself, set `expected_level` to your
label, set `curated: true`, give it a stable id (`c-escalated-NNNN`), and move it into
`tests/golden/controversy/cases-escalated.yaml`. The bootstrap lane is ~15-20 cases; the target
is ~50.
