import dataclasses

import pytest

from langatlas_finding_aids.results import (
    NON_CITABLE_CAVEAT, FindingAidResult, candidate_source_for,
)


def _result(source="pldb", **overrides) -> FindingAidResult:
    base = dict(source=source, item_id="rust", label="Rust",
                fields={"appeared": "2010"}, url="https://pldb.io/concepts/rust.html",
                retrieved_at="2026-09-08T00:00:00Z", mirror_version="abc1234")
    return FindingAidResult(**{**base, **overrides})


def test_a_result_carries_no_citation_shaped_field():
    """The structural half of D53's non-citability: there is no `source_id`, no
    `locator`, and no `quote` on this type, so no code path can move one into a
    `sources:` entry without inventing all three by hand."""
    names = {field.name for field in dataclasses.fields(FindingAidResult)}
    assert names & {"source_id", "locator", "quote", "tier"} == set()


def test_non_citable_is_true_and_frozen():
    result = _result()
    assert result.non_citable is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.non_citable = False


def test_the_dict_form_is_rejected_by_the_source_schema():
    """The other half: even someone who dumps a result straight into `sources/` gets a
    schema failure rather than a quietly-admitted tier-less record."""
    from langatlas_validate.schema import validate_record

    assert validate_record(_result().as_dict(), "source") != []


def test_candidate_source_maps_onto_the_provenance_enum():
    """D29 fixed the enum; a finding-aid source that does not map onto it would make
    `provenance.candidate_source` unwritable for that source."""
    assert candidate_source_for(_result("pldb")) == "pldb"
    assert candidate_source_for(_result("wikidata")) == "wikidata"
    assert candidate_source_for(_result("hyperpolyglot")) == "hyperpolyglot"


def test_wikipedia_maps_to_internal_survey():
    """D29's enum has no `wikipedia` member. Rather than widen a ratified enum, a
    Wikipedia lead is bookkept as `internal-survey` — an honest 'the pipeline found this
    itself' — and the transcript retains which tool actually answered."""
    assert candidate_source_for(_result("wikipedia")) == "internal-survey"


def test_the_caveat_names_the_policy_not_just_a_warning():
    assert "never" in NON_CITABLE_CAVEAT.lower()
    assert "sources:" in NON_CITABLE_CAVEAT
