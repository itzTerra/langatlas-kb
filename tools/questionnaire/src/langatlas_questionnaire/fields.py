"""D46's fact-bearing / structural line, as data.

The keys are what a sweep agent is asked, per (language, feature): the four D23 FeatureInstance
fields that carry citations. The values are the record-schema properties each is answered in.
`exists` is answered by the status and — for an absence — the status-level citations and scope
argument, or — for a partial — the typed notes. `since` is answered by `since`, whose citations
are also the existence citations of a present or partial instance (D65).

This map is the one piece of the compiler that can silently drift from the record schema, so it
is what `tests/fixtures/providers/questionnaire-shape/` guards (D48)."""

FACT_FIELDS: dict[str, tuple[str, ...]] = {
    "exists": ("status", "sources", "absence_scope", "notes"),
    "since": ("since",),
    "characteristics": ("characteristics",),
    "syntax": ("syntax",),
}
