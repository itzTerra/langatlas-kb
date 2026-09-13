import json

import pytest

from langatlas_research.paths import cycles_dir, ensure_layout, research_schema_dir, surveys_dir
from langatlas_research.schema import validate_research_record, validate_research_tree

REPO = __import__("pathlib").Path(__file__).resolve().parents[3]


@pytest.fixture
def research_repo(tmp_path):
    ensure_layout(tmp_path)
    for name in ("theme-registry", "cycle"):
        (research_schema_dir(tmp_path) / f"{name}.schema.json").write_text(
            (REPO / "research" / "schema" / f"{name}.schema.json").read_text())
    return tmp_path


def test_a_valid_cycle_record_has_no_errors(research_repo):
    record = {"cycle": 1, "theme": "typing", "theme_digest": "0" * 16,
              "status": "drafted", "languages": ["python", "haskell"],
              "nodes_minted": [], "artifacts": {}}

    assert validate_research_record(record, "cycle", repo_root=research_repo) == []


def test_an_unknown_status_is_an_error(research_repo):
    record = {"cycle": 1, "theme": "typing", "theme_digest": "0" * 16,
              "status": "nearly-done", "languages": [], "nodes_minted": [], "artifacts": {}}

    errors = validate_research_record(record, "cycle", repo_root=research_repo)

    assert any("status" in e for e in errors), errors


def test_the_tree_walk_reports_the_offending_file(research_repo):
    (cycles_dir(research_repo) / "01-typing.yaml").write_text("cycle: 1\n")

    errors = validate_research_tree(research_repo)

    assert any("research/cycles/01-typing.yaml" in e for e in errors), errors


def test_a_populated_directory_with_no_schema_yet_is_a_loud_error(research_repo):
    (surveys_dir(research_repo) / "01-typing.yaml").write_text("candidates: []\n")

    errors = validate_research_tree(research_repo)

    assert any("survey.schema.json" in e for e in errors), errors
