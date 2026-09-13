import pytest

from langatlas_validate.version import (
    MajorRequiresGovernance, bump, classify_change,
)

BEFORE = {"features/pattern-matching.yaml": {
    "id": "pattern-matching", "slug": "pattern-matching", "name": "Pattern matching",
    "layer": 2, "summary": {"text": "A.", "sources": [{"source": "s", "locator": "p. 1"}]}}}


def test_no_change_is_none():
    assert classify_change(BEFORE, BEFORE) == "none"


def test_a_new_record_is_additive():
    after = BEFORE | {"features/ownership.yaml": {"id": "ownership", "layer": 2}}

    assert classify_change(BEFORE, after) == "additive"


def test_a_new_field_is_additive():
    after = {"features/pattern-matching.yaml":
             BEFORE["features/pattern-matching.yaml"] | {"aliases": ["destructuring"]}}

    assert classify_change(BEFORE, after) == "additive"


def test_a_text_only_edit_is_cosmetic():
    record = dict(BEFORE["features/pattern-matching.yaml"])
    record["summary"] = {"text": "A better sentence.",
                         "sources": [{"source": "s", "locator": "p. 1"}]}

    assert classify_change(BEFORE, {"features/pattern-matching.yaml": record}) == "cosmetic"


def test_a_removed_record_is_restructuring():
    assert classify_change(BEFORE, {}) == "restructuring"


def test_a_layer_move_is_restructuring():
    record = dict(BEFORE["features/pattern-matching.yaml"]) | {"layer": 3,
                                                               "dimension": "d"}

    assert classify_change(BEFORE, {"features/pattern-matching.yaml": record}) == "restructuring"


@pytest.mark.parametrize("change,expected", [
    ("none", (0, 2, 0)), ("cosmetic", (0, 2, 1)), ("additive", (0, 3, 0)),
    ("restructuring", (0, 3, 0)),
])
def test_zero_x_bumps(change, expected):
    assert bump((0, 2, 0), change) == expected


def test_after_one_zero_a_restructure_needs_governance():
    with pytest.raises(MajorRequiresGovernance):
        bump((1, 4, 0), "restructuring")


def test_after_one_zero_additive_is_still_minor():
    assert bump((1, 4, 0), "additive") == (1, 5, 0)
