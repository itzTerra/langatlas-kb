"""D53's finding-aid tooling: PLDB, Wikidata, Hyperpolyglot and Wikipedia as *leads*.

Nothing this package returns is citable (D29/D3). Its results are wrapped in a
`FindingAidResult` envelope the fact schema has no slot for, its tool description restates
that policy once per session, and every externally-derived string reaches a model through
the D31 door. The one exception is `identification.mint_identification_source`, which is a
separate, explicit path for D29's narrow identification-metadata carve-out."""

__version__ = "0.1.0"
