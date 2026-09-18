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

## The assessor is live (Stage 3D)

`goldens.controversy_assessor_entry_point` points at
`langatlas_research.controversy.assessor:golden_assessor`, which lives in the **research**
package. Score it from there — `tools/ingest`'s environment cannot import it:

    uv --directory tools/research run langatlas-sources golden-score \
      --controversy-assessor langatlas_research.controversy.assessor:golden_assessor

A scored run costs university-API calls *and* Claude messages (every level-3 assignment
escalates, §6.4). `langatlas_research.controversy.assessor:golden_assessor_thinker_only` scores
the first pass alone when you want to know how much of level-3 recall the escalation step is
carrying.

The run is a **measurement, not a CI gate** (§8.6): CI shape-checks these cases and never scores
them. New cases arrive from `candidates/` — see that directory's README.
