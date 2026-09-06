"""D24's verification gate (context/spec.md Section 6.2).

Four stages of increasingly expensive filters, not one LLM call. Import the composed
entry points from here; the per-stage modules are importable directly for testing."""
from langatlas_ingest.verify.inputs import CitationInput, ClaimInput, whitelist_payload
from langatlas_ingest.verify.verdicts import (
    ADMITTING_VERDICTS, ANNOTATIONS, Assertion, PairVerdict, SINCE_STATUSES, VERDICTS,
    fold_verification,
)

__all__ = ["ADMITTING_VERDICTS", "ANNOTATIONS", "Assertion", "CitationInput", "ClaimInput",
           "PairVerdict", "SINCE_STATUSES", "VERDICTS", "fold_verification",
           "whitelist_payload"]
