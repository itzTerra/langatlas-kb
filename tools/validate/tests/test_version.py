import subprocess
from pathlib import Path

import pytest

from langatlas_validate.normalize import normalize_record
from langatlas_validate.version import (
    MajorRequiresGovernance, bump, classify_change, snapshot_at, store_snapshot,
)


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def git_store(tmp_path):
    """A tiny real git repo carrying one of every kind `iter_store_records` walks,
    including a ledger under `sources/` and `languages/_registry.yaml` — exactly the mix
    `snapshot_at` must agree with `store_snapshot` about (Finding 1)."""
    _write(tmp_path / "features" / "pattern-matching.yaml", normalize_record(
        "id: pattern-matching\nslug: pattern-matching\nname: Pattern Matching\n"
        "layer: 2\nsummary:\n  text: X.\n  sources:\n    - source: s\n      locator: p. 1\n"
        "provenance:\n  claim_origin: source-derived\n", "feature"))
    _write(tmp_path / "languages" / "_registry.yaml", "languages:\n  rust:\n    name: Rust\n")
    _write(tmp_path / "sources" / "_tombstones.yaml", "[]\n")
    (tmp_path / "concepts" / ".gitkeep").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "concepts" / ".gitkeep").write_text("")

    hooks = tmp_path.parent / f"{tmp_path.name}-no-hooks"
    hooks.mkdir()
    _git(["init", "-q", "-b", "main"], tmp_path)
    for key, value in (("user.email", "bot@example.com"), ("user.name", "bot"),
                       ("commit.gpgsign", "false"), ("core.hooksPath", str(hooks))):
        _git(["config", key, value], tmp_path)
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-q", "-m", "seed"], tmp_path)
    return tmp_path


def test_snapshot_at_agrees_with_store_snapshot_on_an_unmodified_repo(git_store):
    """The regression test for Finding 1: `snapshot_at` and `store_snapshot` must walk
    exactly the same files, or a completely unchanged repo classifies as "additive"
    forever instead of "none"."""
    assert classify_change(snapshot_at(git_store, "HEAD"), store_snapshot(git_store)) == "none"

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
             BEFORE["features/pattern-matching.yaml"] | {"realizes": ["matching"]}}

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


from langatlas_validate.version import diff_class


def test_an_aliases_only_edit_is_cosmetic_even_when_it_drops_one():
    record = BEFORE["features/pattern-matching.yaml"]
    two = {"features/x.yaml": record | {"aliases": ["a", "b"]}}

    assert classify_change(two, {"features/x.yaml": record | {"aliases": ["a"]}}) == "cosmetic"
    assert classify_change(two, {"features/x.yaml": dict(record)}) == "cosmetic"
    assert classify_change({"features/x.yaml": dict(record)}, two) == "cosmetic"


def test_an_alias_change_does_not_hide_a_restructure():
    record = BEFORE["features/pattern-matching.yaml"]

    assert diff_class(record | {"aliases": ["a"]}, record | {"layer": 3}) == "restructuring"
