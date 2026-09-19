# langatlas_coverage (D52)

Coverage analytics for the research phase and after: one CLI, one metrics core ("instance
count per node, keyed by immutable id"), recomputed from the store on every run — no cache.

    langatlas-coverage dossier [--ledger PATH] [--cost-log PATH] [--snapshot]
    langatlas-coverage gaps [--min-instances 2] [--snapshot]

- **`dossier`** — the five-item R6 exit dossier (§7.4): sourcing integrity, reality-check
  results, churn trend, graph health, pipeline readiness. Every bar is **advisory** (D27): the
  `1.0.0` declaration is the developer's judgment. Reads the canonical store, the private
  verdict ledger, `research/` (cycles, carve plans, reality checks), `ontology/migrations/`,
  `benchmarks/d24-verifier/calibration.json` and the cost log.
- **`gaps`** — `<dimension, value>` corroborating-instance counts against `--min-instances`.
  Report-only; near-meaningless before D28 phase 1 completes (there are no instances before
  Stage 5).
- **`demand`** — Stage 6 (the site's search export).

Output is ephemeral: stdout, plus `--snapshot` to `reports/` (gitignored). Never committed.
