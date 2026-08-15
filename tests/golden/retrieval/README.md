<!-- tests/golden/retrieval/README.md -->
# Retrieval golden set

Committed queries with expected results, scored by `langatlas-sources eval`
(Recall@5, MRR, nDCG@10). Distinct from `tests/fixtures/providers/` — that is D48's
pass/fail regression-fixture suite; this one is a **scored** harness with thresholds,
and it is never a CI blocker on its own.

**Status: empty by design.** Stage 1C ships the harness; Stage 2 (R1/R2) authors the
40–60 queries during the corpus QA skims and uses them for D22's embedding benchmark.
`queries.example.yaml` documents the format and is ignored by the runner.

Add one file per batch (`queries-<theme>.yaml`). Every entry needs `id`, `band`,
`query`, and exactly one of `expected_chunks` / `expected_sources` (both scores
recall@5/nDCG@10 against different denominators — `run_eval` rejects an entry that sets
both, since the two are not composable into one score).
