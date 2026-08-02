import pytest
from langatlas_validate.schema import RECORD_KINDS, validate_record


def test_record_kinds_complete():
    assert set(RECORD_KINDS) == {
        "feature", "feature-instance", "edge", "affects-quality-edge",
        "rule", "language", "language-registry", "concept", "source",
    }


def test_valid_feature_instance():
    rec = {
        "feature": "pattern-matching", "language": "rust", "status": "present",
        "provenance": {"claim_origin": "source-derived"},
    }
    assert validate_record(rec, "feature-instance") == []


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
