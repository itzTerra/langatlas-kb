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
        "provenance:\n  claim_origin: source-derived\n"
    )
    return normalize_record(raw, "feature-instance")


@pytest.fixture
def store(tmp_path):
    root = tmp_path
    (root / "concepts" / ".gitkeep").parent.mkdir(parents=True, exist_ok=True)
    (root / "concepts" / ".gitkeep").write_text("")
    _write(root / "languages" / "rust" / "instances" / "pattern-matching.yaml",
          _feature_instance_yaml())
    (root / "sources" / "_tombstones.yaml").parent.mkdir(parents=True, exist_ok=True)
    (root / "sources" / "_tombstones.yaml").write_text("[]\n")
    return root


def test_iter_store_records_finds_the_instance_and_skips_ledgers(store):
    found = list(iter_store_records(store))
    kinds = {kind for _path, kind, _text, _data in found}
    assert kinds == {"feature-instance"}
    assert len(found) == 1


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
                        "provenance:\n  claim_origin: source-derived\n")
    errors = validate_store(store)
    assert any("not normalized" in e for e in errors)


def test_validate_store_flags_schema_violation(store):
    bad_path = store / "languages" / "rust" / "instances" / "invalid.yaml"
    bad_path.write_text("feature: pattern-matching\nlanguage: rust\nstatus: absent\n"
                        "provenance:\n  claim_origin: source-derived\n")   # missing absence_scope
    errors = validate_store(store)
    assert any("invalid.yaml" in e for e in errors)
