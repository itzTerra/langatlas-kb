from langatlas_ingest.verify.inputs import CitationInput, ClaimInput
from langatlas_validate.claims import fact_id as _fact_id


def work_for_fact(fact: dict):
    """Turn one derived fact into its (claim, citation) pairs — the verifiable unit.

    A field with three sources yields three pairs (Section 6.2), judged independently:
    the verifier never sees another citation's verdict.

    @param fact - one entry from `langatlas_validate.compile.derive_facts`

    @returns a list of (ClaimInput, CitationInput)
    """
    claim = ClaimInput(fact_id=fact.get("fact_id") or _fact_id(fact["claim"]),
                       claim=fact["claim"], since=fact.get("since"),
                       status=fact.get("status"),
                       absence_scope=fact.get("absence_scope"),
                       feature_aliases=tuple(fact.get("feature_aliases") or ()))
    return [(claim, CitationInput(entry["source"], entry["locator"],
                                  entry.get("quote")))
            for entry in fact.get("sources") or []]
