from langatlas_validate.locators import (
    validate_locator_shape, validate_locator, LocatorResult,
)


def test_shape_matches_each_kind():
    assert validate_locator_shape("pp. 492–495") == "book-page"     # en dash
    assert validate_locator_shape("p. 492") == "book-page"
    assert validate_locator_shape("§13.2.1") == "numbered-section"
    assert validate_locator_shape("§ Match expressions") == "named-section"
    assert validate_locator_shape("#match-expressions") == "web-fragment"
    assert validate_locator_shape("reference/expr.html#match-guards") == "multipage-docs"
    assert validate_locator_shape("a1b2c3d:src/lib.rs#L10-L25") == "repo-file"
    assert validate_locator_shape("t=00:41:20") == "video"
    assert validate_locator_shape("PEP 634 §Overview") == "design-doc"


def test_shape_rejects_garbage():
    assert validate_locator_shape("just some text") is None
    assert validate_locator_shape("pp. 495-492") == "book-page"  # shape only; ordering not checked here


def test_shape_respects_allowed_kinds():
    assert validate_locator_shape("#frag", allowed_kinds=["book-page"]) is None
    assert validate_locator_shape("#frag", allowed_kinds=["web-fragment"]) == "web-fragment"


class _FakeIndex:
    def __init__(self, hits): self._hits = hits
    def resolve(self, source_id, locator): return self._hits


def test_resolution_bad_shape_short_circuits():
    res = validate_locator("garbage", "s1", _FakeIndex([]))
    assert isinstance(res, LocatorResult)
    assert res.shape_ok is False
    assert res.resolved is False


def test_resolution_hits():
    res = validate_locator("#frag", "s1", _FakeIndex(["chunk-1"]))
    assert res.shape_ok is True
    assert res.resolved is True
    assert res.chunk_ids == ["chunk-1"]
