from pathlib import Path

import pytest
from ruamel.yaml import YAML

from langatlas_validate.store import iter_store_records, validate_store
from langatlas_validate.normalize import normalize_record

_yaml = YAML()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _feature_instance_yaml() -> str:
    raw = (
        "feature: pattern-matching\nlanguage: rust\nstatus: present\n"
        "since:\n  value: \"1.0\"\n  sources:\n    - source: rust-reference\n      locator: p. 1\n"
        "provenance:\n  claim_origin: source-derived\n"
    )
    return normalize_record(raw, "feature-instance")


@pytest.fixture
def store(tmp_path):
    root = tmp_path
    (root / "concepts" / ".gitkeep").parent.mkdir(parents=True, exist_ok=True)
    (root / "concepts" / ".gitkeep").write_text("")

    # Create the feature that the instance references
    _write(root / "features" / "pattern-matching.yaml",
          normalize_record(
              "id: pattern-matching\nslug: pattern-matching\nname: Pattern Matching\n"
              "layer: 2\nsummary:\n  text: X.\n  sources:\n    - source: s\n      locator: p. 1\n"
              "provenance:\n  claim_origin: source-derived\n", "feature"))

    # Create the language registry
    _write(root / "languages" / "_registry.yaml", "languages:\n  rust:\n    name: Rust\n")

    # Create the feature instance
    _write(root / "languages" / "rust" / "instances" / "pattern-matching.yaml",
          _feature_instance_yaml())

    (root / "sources" / "_tombstones.yaml").parent.mkdir(parents=True, exist_ok=True)
    (root / "sources" / "_tombstones.yaml").write_text("[]\n")
    return root


def test_iter_store_records_finds_the_instance_and_skips_ledgers(store):
    found = list(iter_store_records(store))
    kinds = {kind for _path, kind, _text, _data in found}
    assert kinds == {"feature", "feature-instance", "language-registry"}
    assert len(found) == 3


def test_iter_store_records_skips_gitkeep_and_tombstones(store):
    paths = {str(path) for path, _kind, _text, _data in iter_store_records(store)}
    assert not any("gitkeep" in p for p in paths)
    assert not any("_tombstones" in p for p in paths)


def test_validate_store_clean_repo_has_no_errors(store):
    assert validate_store(store) == []


def test_validate_store_flags_normalization_drift(store):
    bad_path = store / "languages" / "rust" / "instances" / "drifted.yaml"
    # deliberately unnormalized: wrong key order relative to the schema
    bad_path.write_text("language: rust\nfeature: pattern-matching\nstatus: present\n"
                        "since:\n  value: \"1.0\"\n  sources:\n    - source: rust-reference\n      locator: p. 1\n"
                        "provenance:\n  claim_origin: source-derived\n")
    errors = validate_store(store)
    assert any("not normalized" in e for e in errors)


def test_validate_store_flags_schema_violation(store):
    bad_path = store / "languages" / "rust" / "instances" / "invalid.yaml"
    bad_path.write_text("feature: pattern-matching\nlanguage: rust\nstatus: absent\n"
                        "provenance:\n  claim_origin: source-derived\n")   # missing absence_scope
    errors = validate_store(store)
    assert any("invalid.yaml" in e for e in errors)


def _source_yaml(*, canonical: bool | None, note: str | None) -> str:
    custom_lines = ["  tier: B", "  grounding: third-party-reference"]
    if canonical is not None:
        custom_lines.append(f"  canonical_source: {str(canonical).lower()}")
    if note is not None:
        custom_lines.append(f"  acquisition_note: {note}")
    raw = ("id: test-source-2026\ntype: book\ntitle: Test Source\ncustom:\n"
          + "\n".join(custom_lines) + "\n")
    return normalize_record(raw, "source")


def test_validate_store_flags_missing_acquisition_note_on_noncanonical_source(store):
    path = store / "sources" / "mirror-2026.yaml"
    path.write_text(_source_yaml(canonical=False, note=None))
    errors = validate_store(store)
    assert any("acquisition_note" in e for e in errors)


def test_validate_store_allows_canonical_source_without_a_note(store):
    path = store / "sources" / "official-2026.yaml"
    path.write_text(_source_yaml(canonical=True, note=None))
    assert validate_store(store) == []


def test_validate_store_allows_noncanonical_source_with_a_note(store):
    path = store / "sources" / "mirror-2026.yaml"
    path.write_text(_source_yaml(canonical=False, note="mirrored from libgen; original OOP"))
    assert validate_store(store) == []
