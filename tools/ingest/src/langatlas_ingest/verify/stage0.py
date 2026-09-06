from dataclasses import dataclass
from langatlas_ingest.verify.inputs import CitationInput, ClaimInput
from langatlas_validate.locators import validate_locator_shape


@dataclass(frozen=True)
class Stage0Result:
    """Stage 0's outcome. `ok` means "keep going"; otherwise `verdict` is final for this
    pair and no provider call is made. The registry-existence escape hatch is the one case
    where a *terminal* result is a pass (`supported`) rather than a failure."""

    ok: bool
    verdict: str | None = None
    detail: str = ""
    locator_kind: str | None = None


def run_stage0(claim: ClaimInput, citation: CitationInput,
               source_facts: dict) -> Stage0Result:
    """Section 6.2's stage 0: schema + referential checks, in plain code.

    The cheapest filter in the pipeline and the only one that can reject a pair without
    reading a single chunk. Everything here is a property of the citation as written, not
    of what the source says.

    @param source_facts - source_id -> SourceFacts, from `load_source_facts`

    @returns a `Stage0Result`; `ok=False` carries the terminal verdict
    """
    facts = source_facts.get(citation.source_id)
    if facts is None:
        return Stage0Result(False, "source-unavailable",
                            f"no source record for {citation.source_id!r}")
    if claim.registry_existence:
        # Section 6.2's escape hatch: identification metadata (Section 3.4) is ungated,
        # and a claim whose whole content is "this source exists" is answered by the
        # record's existence. There is nothing for the entailment stage to read.
        return Stage0Result(False, "supported",
                            "registry-existence check: the source record exists")

    kind = validate_locator_shape(citation.locator)
    if kind is None:
        return Stage0Result(False, "locator-not-found",
                            f"locator {citation.locator!r} matches no Section 4.3 grammar")
    if facts.locator_kinds and kind not in facts.locator_kinds:
        # An empty list means the source never declared its kinds, which is a gap in the
        # record rather than a licence to reject — so only a *declared* list constrains.
        return Stage0Result(False, "locator-not-found",
                            f"{citation.source_id!r} declares locator kinds"
                            f" {list(facts.locator_kinds)}, not {kind!r}")
    return Stage0Result(True, locator_kind=kind)
