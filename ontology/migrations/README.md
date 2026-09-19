# ontology/migrations/

One directory per ontology migration, `<NNNN>-<slug>/manifest.yaml`: D38's disposition DSL
(`op: split | merge | move | remove`, each with a `fact_remap` of anchor matchers →
`remap | requeue | tombstone | untouched`). Validated by `ontology/schema/migration-manifest.schema.json`.

A manifest is never applied by hand. `langatlas-research consolidate draft-migration` drafts one
from the casebook defaults (§5.2); `langatlas-research consolidate migrate` plans it with the
shared interpreter (`langatlas_validate.migrate`), re-runs the D24 gate on every rewritten edge
and rule, and lands the manifest and the migrated corpus diff as **one** commit. CI replays that
commit against its parent (`langatlas-validate migrations replay`) and fails on any byte of
difference.

During `0.x` a manifest is *required* only for a restructure touching a **settled** theme
(§7.4); it is available — and writes the tombstone and redirect lines for free — for any theme.
At `1.0.0` the RFC-gated D16 process (Stage 4) adds an `impact.md` beside each manifest.
