<!-- tests/golden/controversy/README.md -->
# Controversy golden cases (D21/D25 — §6.4)

The **bootstrap lane**: 15–20 synthetic structured-input cases seeding the ~50-case
target that Stage 3's opportunistic lane grows from real Claude-escalation reviews.

Each case is structured inputs in, ordinal level out (`0 settled | 1 noted-variance |
2 contested | 3 disputed`). Permitted inputs are exactly `debates`,
`contradiction_records`, `verdicts`, `source_strength`, `assessment_spread`.
Human-challenge-derived inputs — GitHub activity, challenge counts, and (per the
2026-07-20 withdrawal) `closure_attempt.outcome` — are **rejected by the validator**:
the assessor never sees them, so calibrating against them would calibrate a fiction.

The assessor itself is Stage 3. These cases exist so it has a calibration set the day it
is written; `golden-score --controversy-assessor <dotted.path>` scores it.
