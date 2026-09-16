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


from langatlas_validate.claims import FREETEXT_KINDS, build_claim, fact_id


def test_node_definition_is_a_freetext_claim_kind():
    assert "node-definition" in FREETEXT_KINDS


def test_node_definition_renders_id_and_a_hash_of_the_summary():
    claim = build_claim("node-definition", node_id="static-typing",
                        text="Type checking happens before the program runs.")
    assert claim.startswith("node-definition(static-typing, sha256-16=")
    assert claim.endswith(")")
    assert len(claim.split("sha256-16=")[1].rstrip(")")) == 16


def test_node_definition_is_insensitive_to_case_whitespace_and_final_period():
    a = build_claim("node-definition", node_id="x", text="Type checking  happens early.")
    b = build_claim("node-definition", node_id="x", text="type checking happens early")
    assert a == b and fact_id(a) == fact_id(b)


def test_a_different_node_with_the_same_summary_is_a_different_fact():
    text = "Type checking happens before the program runs."
    assert (build_claim("node-definition", node_id="a", text=text)
            != build_claim("node-definition", node_id="b", text=text))
