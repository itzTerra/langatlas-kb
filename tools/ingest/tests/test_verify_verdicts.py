import pytest
from langatlas_ingest.verify.inputs import ClaimInput, CitationInput, whitelist_payload
from langatlas_ingest.verify.verdicts import (
    ADMITTING_VERDICTS, LOAD_BEARING_FIELDS, PairVerdict, VERDICTS, fold_verification,
)

TIERS = {"a-src": "A", "b-src": "B", "c-src": "C", "d-src": "D"}


def tier_of(source_id):
    return TIERS[source_id]


def pair(source_id="a-src", verdict="supported", since_status=None):
    return PairVerdict(fact_id="f-000000000001", source_id=source_id, locator="p. 1",
                       verdict=verdict, since_status=since_status)


def test_vocabulary_is_the_six_verdicts_in_spec_order():
    assert VERDICTS == ("source-unavailable", "locator-not-found", "supported", "partial",
                        "unsupported", "contradicted")
    # `partial` bounces for claim narrowing and never admits: the whole false-accept
    # measurement hangs off this set being exactly {"supported"}.
    assert ADMITTING_VERDICTS == frozenset({"supported"})
    assert LOAD_BEARING_FIELDS == ("base", "since")


def test_no_pairs_is_unverified():
    assert fold_verification([], tier_of=tier_of, has_since=False) == "unverified"


def test_supported_on_tier_c_only_is_failed():
    # Admissibility is >=1 `supported` from tier A/B. C/D corroborate only.
    got = fold_verification([pair("c-src")], tier_of=tier_of, has_since=False)
    assert got == "failed"


def test_supported_on_tier_a_with_no_since_is_verified():
    assert fold_verification([pair()], tier_of=tier_of, has_since=False) == "verified"


def test_since_supported_clears_the_since_field():
    got = fold_verification([pair(since_status="since-supported")],
                            tier_of=tier_of, has_since=True)
    assert got == "verified"


def test_as_of_supported_tops_out_at_partially_verified():
    got = fold_verification([pair(since_status="as-of-supported")],
                            tier_of=tier_of, has_since=True)
    assert got == "partially-verified"


def test_a_second_citation_can_clear_a_field_the_first_left_partial():
    pairs = [pair("a-src", since_status="as-of-supported"),
             pair("b-src", since_status="since-supported")]
    assert fold_verification(pairs, tier_of=tier_of, has_since=True) == "verified"


def test_a_partial_citation_never_demotes_a_field_another_citation_cleared():
    pairs = [pair("a-src"), pair("c-src", verdict="partial")]
    assert fold_verification(pairs, tier_of=tier_of, has_since=False) == "verified"


def test_contradicted_never_feeds_the_table():
    # A fact can be `verified` and `contradicted` at once: contradiction routes to the
    # register and the separate `dispute` axis, never to `verification`.
    pairs = [pair("a-src"), pair("b-src", verdict="contradicted")]
    assert fold_verification(pairs, tier_of=tier_of, has_since=False) == "verified"


def test_locator_not_found_is_not_support():
    got = fold_verification([pair("a-src", verdict="locator-not-found")],
                            tier_of=tier_of, has_since=False)
    assert got == "failed"


def test_has_since_with_no_pair_addressing_it_is_partially_verified():
    assert fold_verification([pair()], tier_of=tier_of, has_since=True) == "partially-verified"


def test_whitelist_payload_carries_only_the_six_allowed_keys():
    claim = ClaimInput(fact_id="f-000000000001", claim="instance-exists(fi.python.x)",
                       since="3.10")
    citation = CitationInput(source_id="a-src", locator="p. 1", quote="hello")
    assert set(whitelist_payload(claim, citation)) == {
        "fact_id", "claim", "since", "source_id", "locator", "quote"}


def test_absent_claims_widen_the_whitelist_by_exactly_two_keys():
    claim = ClaimInput(fact_id="f-000000000002", claim="instance-exists(fi.c.x, status=absent)",
                       status="absent", absence_scope="the whole standard",
                       feature_aliases=("generics", "templates"))
    citation = CitationInput(source_id="a-src", locator="§6.7")
    payload = whitelist_payload(claim, citation)
    assert set(payload) == {"fact_id", "claim", "since", "source_id", "locator", "quote",
                            "absence_scope", "feature_aliases"}


def test_whitelist_payload_refuses_to_carry_notes_or_provenance():
    claim = ClaimInput(fact_id="f-000000000003", claim="instance-exists(fi.python.x)")
    citation = CitationInput(source_id="a-src", locator="p. 1")
    payload = whitelist_payload(claim, citation)
    for forbidden in ("notes", "claim_origin", "proposer", "debate_id", "stratum",
                      "expected_verdict", "chat_run_id"):
        assert forbidden not in payload
