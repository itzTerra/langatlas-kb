# langatlas_finding_aids (D53)

PLDB, Wikidata, Hyperpolyglot and Wikipedia as **finding aids** — leads about what to
investigate and where. Nothing here is citable (D29/D3): results come back in a
`FindingAidResult` envelope the fact schema has no slot for, the tool description restates
the policy once per session, and every externally-derived string passes D31's scan.

    langatlas-finding-aids mirror-refresh                 # monthly job does this too
    langatlas-finding-aids checklist --theme type-systems # R3 batch-survey input
    langatlas-finding-aids lookup "rust macros"           # ad hoc

Reads are served from the monthly mirrors (PLDB: a git clone; Hyperpolyglot: a scoped
scrape) so a checklist is reproducible and two small community sites are hit once a month,
not once a query. Wikidata and Wikipedia are queried live under a conservative throttle.

`mint_identification_source` is the one path that produces a real `sources/` record — a
tier-D attribution citation for D29's identification-metadata carve-out (file extensions,
first-appeared years), which is ungated registry data, not a gated fact.

Never registered on the public MCP (D8/D60).
