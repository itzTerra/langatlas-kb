# langatlas-questionnaire

D46's questionnaire compiler (context/spec.md §7.3): a deterministic function from the canonical
store to the sweep questionnaire. Six mechanical steps, zero judgment calls, no model.

```bash
uv --directory tools/questionnaire run langatlas-questionnaire compile          # write questionnaire/spec-<v>.yaml
uv --directory tools/questionnaire run langatlas-questionnaire compile --check  # does the committed spec match?
uv --directory tools/questionnaire run langatlas-questionnaire diff OLD NEW     # the delta questionnaire
uv --directory tools/questionnaire run langatlas-questionnaire validate         # schema-check committed specs
python tools/questionnaire/compile.py compile                                   # the spec-path shim, same CLI
```

- **Only the four fact-bearing FeatureInstance fields are asked** (`exists` / `since` /
  `characteristics` / `syntax`, `fields.FACT_FIELDS`). Hard `requires` / `conflicts-with` edges and
  Rules compile to `constraints:` for the Stage 5 reconciler; everything else ontology-authored
  compiles to nothing.
- **A dimension group's items are its values** (D67). A dimension with fewer than two member
  features is reported as a diagnostic.
- **Language-agnostic.** `instantiate(spec, language, language_kind=…)` fills in the anchors and
  applies D50's `applies_to` mask — the only filter there is.
- **Committed** at `questionnaire/spec-<ontology_version>.yaml`, stamped with nothing else that
  changes between runs, so a recompile at the same version is byte-identical.
- **The field map is drift-guarded** by `tests/fixtures/providers/questionnaire-shape/`
  (D48, `mode: soft`).
