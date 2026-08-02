import pytest
from langatlas_validate.claims import (
    build_claim, fact_id, render_claim, load_claim_template, validate_claim_template,
)


def test_build_instance_exists():
    assert build_claim("instance-exists", instance_id="fi.rust.pattern-matching",
                       status="present") == \
        "instance-exists(fi.rust.pattern-matching, status=present)"


def test_build_instance_field_quotes_value():
    assert build_claim("instance-field", instance_id="fi.rust.pattern-matching",
                       field="since", value="1.0") == \
        'instance-field(fi.rust.pattern-matching, since, "1.0")'


def test_build_freetext_kind_hashes_normalized_text():
    c1 = build_claim("characteristic", instance_id="fi.rust.pattern-matching",
                     key="c-exhaustive", text="The compiler rejects it.")
    c2 = build_claim("characteristic", instance_id="fi.rust.pattern-matching",
                     key="c-exhaustive", text="the compiler rejects it")  # copyedit
    assert c1 == c2                      # copyedit-tolerant
    assert "sha256-16=" in c1


def test_fact_id_shape_and_stability():
    fid = fact_id("instance-exists(fi.rust.pattern-matching, status=present)")
    assert fid.startswith("f-")
    assert len(fid) == 2 + 12
    assert all(ch in "0123456789abcdef" for ch in fid[2:])


def test_fact_id_changes_with_claim():
    a = fact_id("instance-exists(fi.rust.x, status=present)")
    b = fact_id("instance-exists(fi.rust.x, status=absent)")
    assert a != b


def test_render_uses_template():
    out = render_claim("instance-exists", {
        "language": "Rust", "feature_verb": "supports",
        "feature": "pattern matching", "status": "present"})
    assert out == "Rust supports pattern matching (present)."


def test_template_pattern_matches_grammar():
    assert validate_claim_template("instance-exists") == []


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        build_claim("nope")
