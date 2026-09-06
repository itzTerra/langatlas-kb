from langatlas_ingest.verify.inputs import CitationInput, ClaimInput
from langatlas_ingest.verify.sources import SourceFacts
from langatlas_ingest.verify.stage0 import run_stage0

SF = {"scott-plp": SourceFacts(id="scott-plp", tier="B",
                               grounding="third-party-reference",
                               locator_kinds=("book-page",), csl={}),
      "loose": SourceFacts(id="loose", tier="A", grounding="formal-spec",
                           locator_kinds=(), csl={})}


def claim(**kw):
    return ClaimInput(fact_id="f-1", claim="instance-exists(fi.python.x)", **kw)


def test_unknown_source_is_source_unavailable():
    got = run_stage0(claim(), CitationInput("no-such-source", "p. 1"), SF)
    assert got.ok is False
    assert got.verdict == "source-unavailable"


def test_malformed_locator_is_locator_not_found():
    got = run_stage0(claim(), CitationInput("scott-plp", "page four"), SF)
    assert got.ok is False
    assert got.verdict == "locator-not-found"


def test_a_well_shaped_locator_passes_and_reports_its_kind():
    got = run_stage0(claim(), CitationInput("scott-plp", "pp. 492–495"), SF)
    assert got.ok is True
    assert got.locator_kind == "book-page"


def test_a_kind_the_source_does_not_declare_is_locator_not_found():
    # `custom.locator_kinds` is the source's own statement about what a citation to it
    # may look like; a section citation into a page-only PDF is a referential error, not
    # something to hand to an LLM.
    got = run_stage0(claim(), CitationInput("scott-plp", "§13.2.1"), SF)
    assert got.ok is False
    assert got.verdict == "locator-not-found"


def test_an_empty_locator_kinds_list_permits_any_shape():
    got = run_stage0(claim(), CitationInput("loose", "§13.2.1"), SF)
    assert got.ok is True


def test_registry_existence_claims_short_circuit_to_supported():
    # Section 6.2's one escape hatch: the claim *is* the source's existence.
    got = run_stage0(claim(registry_existence=True), CitationInput("scott-plp", "p. 1"), SF)
    assert got.ok is False
    assert got.verdict == "supported"
    assert "registry-existence" in got.detail


def test_registry_existence_still_requires_the_source_to_exist():
    got = run_stage0(claim(registry_existence=True), CitationInput("nope", "p. 1"), SF)
    assert got.verdict == "source-unavailable"
