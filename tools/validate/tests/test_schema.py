import pytest
from langatlas_validate.schema import RECORD_KINDS, validate_record


def test_record_kinds_complete():
    assert set(RECORD_KINDS) == {
        "feature", "feature-instance", "edge", "affects-quality-edge",
        "rule", "language", "language-registry", "concept", "source",
        "contradiction",
    }


REF = [{"source": "rust-fls", "locator": "§6.18"}]
PROVENANCE = {"claim_origin": "source-derived"}


def test_valid_feature_instance():
    rec = {"feature": "pattern-matching", "language": "rust", "status": "present",
           "since": {"value": "1.0", "sources": REF}, "provenance": PROVENANCE}
    assert validate_record(rec, "feature-instance") == []


def test_a_present_or_partial_instance_needs_a_since():
    """D65: without a `since`, a present instance has no version and no existence citation."""
    for status in ("present", "partial"):
        rec = {"feature": "x", "language": "rust", "status": status, "provenance": PROVENANCE}
        assert any("since" in e for e in validate_record(rec, "feature-instance"))


def test_a_present_instance_cites_through_since_not_at_status_level():
    rec = {"feature": "x", "language": "rust", "status": "present",
           "since": {"value": "1.0", "sources": REF}, "sources": REF,
           "provenance": PROVENANCE}
    assert validate_record(rec, "feature-instance") != []


def test_an_absent_instance_cites_at_status_level_and_has_no_since():
    ok = {"feature": "x", "language": "rust", "status": "absent", "absence_scope": "s",
          "sources": REF, "provenance": PROVENANCE}
    assert validate_record(ok, "feature-instance") == []
    assert validate_record({**ok, "sources": []}, "feature-instance") != []
    assert any("sources" in e for e in validate_record(
        {k: v for k, v in ok.items() if k != "sources"}, "feature-instance"))
    assert validate_record({**ok, "since": {"value": "1.0", "sources": REF}},
                           "feature-instance") != []


def test_as_of_is_never_a_since_status():
    """D66: as-of is a verdict, held in the private ledger — never written into YAML (D23)."""
    rec = {"feature": "x", "language": "rust", "status": "present",
           "since": {"value": "1.0", "sources": REF, "since_status": "as-of"},
           "provenance": PROVENANCE}
    assert validate_record(rec, "feature-instance") != []


def test_absent_requires_absence_scope():
    rec = {"feature": "x", "language": "rust", "status": "absent",
           "provenance": {"claim_origin": "source-derived"}}
    errors = validate_record(rec, "feature-instance")
    assert any("absence_scope" in e for e in errors)


def test_rule_arity_floor():
    rec = {"id": "rule-x", "when_all": ["a"], "effect": "warn", "then": [],
           "message": "m", "sources": [], "provenance": {}}
    errors = validate_record(rec, "rule")
    assert errors  # 1-antecedent rule rejected (min 2)


def test_source_requires_grounding_and_tier():
    rec = {"id": "s", "type": "book", "title": "T", "custom": {"tier": "A"}}
    errors = validate_record(rec, "source")
    assert any("grounding" in e for e in errors)


def test_valid_feature_with_populated_summary_and_sources():
    rec = {
        "id": "feature-pattern-matching",
        "slug": "pattern-matching",
        "name": "Pattern matching",
        "layer": 1,
        "summary": {
            "text": "Destructures values against structural patterns.",
            "sources": [{"source": "s1", "locator": "p. 1"}],
        },
        "provenance": {"claim_origin": "source-derived"},
    }
    assert validate_record(rec, "feature") == []


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        validate_record({}, "not-a-kind")


def test_feature_invalid_slug_rejected():
    rec = {
        "id": "feature-pattern-matching",
        "slug": "Pattern_Matching",
        "name": "Pattern matching",
        "layer": 1,
        "summary": {
            "text": "Destructures values against structural patterns.",
            "sources": [{"source": "s1", "locator": "p. 1"}],
        },
        "provenance": {"claim_origin": "source-derived"},
    }
    errors = validate_record(rec, "feature")
    assert any("slug" in e for e in errors)


def test_feature_valid_slug_passes():
    rec = {
        "id": "feature-pattern-matching",
        "slug": "pattern-matching",
        "name": "Pattern matching",
        "layer": 1,
        "summary": {
            "text": "Destructures values against structural patterns.",
            "sources": [{"source": "s1", "locator": "p. 1"}],
        },
        "provenance": {"claim_origin": "source-derived"},
    }
    assert validate_record(rec, "feature") == []


def test_edge_invalid_from_id_rejected():
    rec = {
        "id": "edge.requires.Bad_Id.pattern-matching",
        "type": "requires",
        "from": "Bad_Id",
        "to": "pattern-matching",
        "provenance": {"claim_origin": "source-derived"},
    }
    errors = validate_record(rec, "edge")
    assert any("from" in e and "slug" in e for e in errors)
