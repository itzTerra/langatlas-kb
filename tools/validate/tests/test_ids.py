# tools/validate/tests/test_ids.py
from langatlas_validate.ids import (
    is_valid_slug, compose_instance_id, compose_edge_id,
    canonical_endpoints, canonical_when_all, compose_rule_id, compose_syntax_id,
)


def test_valid_slugs():
    assert is_valid_slug("pattern-matching")
    assert is_valid_slug("cpp")
    assert is_valid_slug("a")


def test_invalid_slugs():
    assert not is_valid_slug("Pattern-Matching")     # uppercase
    assert not is_valid_slug("2fa")                   # leading digit
    assert not is_valid_slug("-lead")                 # leading hyphen
    assert not is_valid_slug("double--hyphen")        # empty segment
    assert not is_valid_slug("trailing-")             # trailing hyphen
    assert not is_valid_slug("under_score")           # non [a-z0-9-]
    assert not is_valid_slug("x" * 49)                # over 48 chars
    assert is_valid_slug("x" * 48)                    # exactly 48 ok


def test_composed_ids():
    assert compose_instance_id("rust", "pattern-matching") == "fi.rust.pattern-matching"
    assert compose_edge_id("requires", "ownership", "move-semantics") == \
        "edge.requires.ownership.move-semantics"
    assert compose_rule_id("laziness-needs-purity") == "rule-laziness-needs-purity"
    assert compose_syntax_id("fi.rust.pattern-matching", "basic-match") == \
        "fi.rust.pattern-matching.sx.basic-match"


def test_canonical_ordering():
    # alternative-to endpoints stored lexicographically (§3.3)
    assert canonical_endpoints("zeta", "alpha") == ("alpha", "zeta")
    assert canonical_endpoints("alpha", "zeta") == ("alpha", "zeta")
    # when_all sorted before hashing (D64)
    assert canonical_when_all(["side-effects-allowed", "lazy-evaluation"]) == \
        ["lazy-evaluation", "side-effects-allowed"]


def test_composers_reject_bad_slugs():
    import pytest
    with pytest.raises(ValueError):
        compose_instance_id("Rust", "pattern-matching")
