from langatlas_ingest.verify.confidence import derive_confidence
from langatlas_ingest.verify.sources import SourceFacts, are_independent, load_source_facts
from langatlas_ingest.verify.verdicts import PairVerdict


def facts(source_id, tier, *, authors=(), publisher=None, venue=None):
    csl = {"author": [{"family": a, "given": ""} for a in authors]}
    if publisher:
        csl["publisher"] = publisher
    if venue:
        csl["container-title"] = venue
    return SourceFacts(id=source_id, tier=tier, grounding="third-party-reference",
                       locator_kinds=(), csl=csl)


def pair(source_id, verdict="supported"):
    return PairVerdict(fact_id="f-1", source_id=source_id, locator="p. 1", verdict=verdict)


def test_shared_author_is_not_independent():
    a = facts("a", "A", authors=["Pierce"], publisher="MIT Press")
    b = facts("b", "B", authors=["Pierce"], publisher="Springer")
    assert are_independent(a, b) is False


def test_shared_publisher_is_not_independent():
    a = facts("a", "A", authors=["Pierce"], publisher="MIT Press")
    b = facts("b", "B", authors=["Scott"], publisher="MIT Press")
    assert are_independent(a, b) is False


def test_distinct_authors_and_publishers_are_independent():
    a = facts("a", "A", authors=["Pierce"], publisher="MIT Press")
    b = facts("b", "C", authors=["Scott"], publisher="Morgan Kaufmann")
    assert are_independent(a, b) is True


def test_missing_metadata_defaults_to_not_independent():
    # Section 6.3: borderline defaults to *not* independent.
    a = facts("a", "A", authors=["Pierce"], publisher="MIT Press")
    b = facts("b", "B")
    assert are_independent(a, b) is False


def test_a_source_is_never_independent_of_itself():
    a = facts("a", "A", authors=["Pierce"], publisher="MIT Press")
    assert are_independent(a, a) is False


def test_unverified_carries_no_confidence():
    assert derive_confidence("unverified", [], {}) is None
    assert derive_confidence("failed", [], {}) is None


def test_partially_verified_is_low_at_any_tier():
    sf = {"a": facts("a", "A", authors=["Pierce"], publisher="MIT Press")}
    assert derive_confidence("partially-verified", [pair("a")], sf) == "low"


def test_one_uncorroborated_tier_a_source_is_medium():
    sf = {"a": facts("a", "A", authors=["Pierce"], publisher="MIT Press")}
    assert derive_confidence("verified", [pair("a")], sf) == "medium"


def test_tier_a_plus_an_independent_corroborator_is_high():
    sf = {"a": facts("a", "A", authors=["Pierce"], publisher="MIT Press"),
          "c": facts("c", "C", authors=["Scott"], publisher="Morgan Kaufmann")}
    assert derive_confidence("verified", [pair("a"), pair("c")], sf) == "high"


def test_tier_a_plus_a_dependent_corroborator_stays_medium():
    sf = {"a": facts("a", "A", authors=["Pierce"], publisher="MIT Press"),
          "b": facts("b", "B", authors=["Pierce"], publisher="Springer")}
    assert derive_confidence("verified", [pair("a"), pair("b")], sf) == "medium"


def test_tier_c_sole_backing_uncorroborated_is_low():
    sf = {"c": facts("c", "C", authors=["Scott"], publisher="Morgan Kaufmann")}
    assert derive_confidence("verified", [pair("c")], sf) == "low"


def test_tier_c_with_an_independent_corroborator_is_medium():
    sf = {"c": facts("c", "C", authors=["Scott"], publisher="Morgan Kaufmann"),
          "d": facts("d", "D", authors=["Wiki"], publisher="Wikimedia")}
    assert derive_confidence("verified", [pair("c"), pair("d")], sf) == "medium"


def test_tier_d_alone_never_establishes_confidence():
    sf = {"d": facts("d", "D", authors=["Wiki"], publisher="Wikimedia")}
    assert derive_confidence("verified", [pair("d")], sf) is None


def test_absence_on_a_single_source_caps_at_medium():
    # D49: absence confidence caps at `medium` on a single source, even when the
    # corroboration rule would otherwise reach `high`.
    sf = {"a": facts("a", "A", authors=["Pierce"], publisher="MIT Press")}
    assert derive_confidence("verified", [pair("a")], sf, absent=True) == "medium"


def test_absence_on_two_independent_sources_is_not_capped():
    sf = {"a": facts("a", "A", authors=["Pierce"], publisher="MIT Press"),
          "c": facts("c", "C", authors=["Scott"], publisher="Morgan Kaufmann")}
    assert derive_confidence("verified", [pair("a"), pair("c")], sf, absent=True) == "high"


def test_only_supported_pairs_count_toward_confidence():
    sf = {"a": facts("a", "A", authors=["Pierce"], publisher="MIT Press"),
          "c": facts("c", "C", authors=["Scott"], publisher="Morgan Kaufmann")}
    pairs = [pair("a"), pair("c", verdict="partial")]
    assert derive_confidence("verified", pairs, sf) == "medium"


def test_load_source_facts_reads_the_real_store():
    loaded = load_source_facts()
    assert "scott-plp" in loaded
    assert loaded["scott-plp"].tier == "B"
    assert loaded["scott-plp"].csl["title"] == "Programming Language Pragmatics"
    # `_tombstones.yaml` is a ledger, not a source record.
    assert "_tombstones" not in loaded
