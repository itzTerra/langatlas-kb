import pytest
from langatlas_ingest.goldens.items import (
    ADMITTING_VERDICTS, ANNOTATIONS, MAX_QUOTE_WORDS, STRATA, STRATUM_VERDICTS, VERDICTS,
    Citation, Claim, VerifierItem,
)


def item(**overrides) -> VerifierItem:
    defaults = dict(
        id="v-typing-0001", stratum="correct", expected_verdict="supported",
        claim=Claim(kind="instance-exists",
                    text="instance-exists(i-haskell-lazy-evaluation, status=present)",
                    status="present"),
        citation=Citation(source="vanroy-haridi-2003", locator="§4.5"),
    )
    return VerifierItem(**{**defaults, **overrides})


def test_the_thirteen_strata_are_frozen():
    assert len(STRATA) == 13
    assert STRATA[0] == "correct" and "overstated-claim" in STRATA
    assert set(STRATUM_VERDICTS) == set(STRATA)


def test_the_verdict_vocabulary_is_the_six_of_section_6_2():
    assert VERDICTS == ("source-unavailable", "locator-not-found", "supported", "partial",
                        "unsupported", "contradicted")
    assert ANNOTATIONS == ("quote-mismatch", "quote-found-elsewhere")


def test_only_supported_admits():
    # The admissibility rule (Section 6.2) is ">=1 citation is `supported`" — `partial`
    # bounces for narrowing, so it must never count as an accept.
    assert ADMITTING_VERDICTS == frozenset({"supported"})


def test_overstated_claim_is_the_partial_stratum():
    assert STRATUM_VERDICTS["overstated-claim"] == frozenset({"partial"})


def test_the_fact_id_is_derived_from_the_canonical_claim_text_not_stored():
    got = item()
    assert got.claim.fact_id.startswith("f-") and len(got.claim.fact_id) == 14


def test_the_verifier_input_is_the_whitelist_of_section_6_2():
    got = item(citation=Citation(source="ctm", locator="p. 12", quote="a short quote"))
    assert set(got.verifier_input()) == {"fact_id", "claim", "since", "source_id",
                                         "locator", "quote"}


def test_an_absent_claim_also_carries_its_absence_argument():
    # D49's inverted framing verifies the agent's own `absence_scope`, so the whitelist
    # widens by exactly those two keys for absent claims — and for no others.
    got = item(claim=Claim(kind="instance-exists",
                           text="instance-exists(i-c-pattern-matching, status=absent)",
                           status="absent", absence_scope="C23, whole language",
                           feature_aliases=("pattern matching", "destructuring")))
    assert set(got.verifier_input()) == {"fact_id", "claim", "since", "source_id",
                                         "locator", "quote", "absence_scope",
                                         "feature_aliases"}


def test_the_quote_cap_constant_is_d14s_fifty_words():
    assert MAX_QUOTE_WORDS == 50


def test_items_are_immutable():
    with pytest.raises(Exception):
        item().id = "v-other-0001"
