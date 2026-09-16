<!-- tests/golden/debates/README.md -->
# Debate golden set (D5/D30 — §7.2, §7.4)

**R4 schema-dispute debates.** Each case in `cases-r4.yaml` is a complete debate record plus
the outcome, round count and controversy projection it must produce.

What these guard is a boundary, not a model. The moderator's judgment is not scored here —
D44 owns scored fact-debate golden sets, and §7.13 defers them until phase-1 volume. What is
scored is the deterministic layer between a moderator's decision and what Stage 3D reads:
the `disposition -> outcome` mapping, the `rounds` count, and the `debate:<id>:<signal>`
format. A change to any of those breaks a committed case here instead of silently re-scoring
the controversy golden set, whose `debates:` inputs use exactly this shape.

Run: `uv --directory tools/research run pytest tests/test_debate_goldens.py`

**Growing the set.** The three committed cases are synthetic, one per outcome. Add real
records from cycle 1 onward: copy `research/debates/<id>.yaml` into a new `cases:` entry,
fill in `expect` by hand, and keep the `notes` line saying what the case is *for*. A case
that duplicates an existing one's shape adds nothing.
