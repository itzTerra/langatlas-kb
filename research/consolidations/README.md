R6 consolidation records (`<cycle>-<theme>.yaml`): whether the cross-theme
edge pass ran (its edges live in the cycle's carve plan, marked
`pass: r6`), the developer's rulings on dedup/alias candidates, and the
migrations this consolidation landed. Written by `langatlas-research
consolidate` (Stage 3F); read by later cycles' dedup audits (a `distinct`
ruling is never re-raised) and by `coverage report.py dossier`.
