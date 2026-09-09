import json

import pytest

from langatlas_finding_aids.checklist import (
    build_checklist, store_coverage, write_checklist,
)
from langatlas_finding_aids.config import FindingAidsConfig, UnknownTheme
from langatlas_finding_aids.results import FindingAidResult


class _Ctx:
    def __init__(self):
        self.run_id = "run-1"
        self.events = []

    class _W:
        def __init__(self, outer):
            self.outer = outer

        def append(self, **event):
            self.outer.events.append(event)

    @property
    def writer(self):
        return self._W(self)

    def tool_result(self, *, tool, text, source_id=None, kind="source-chunk"):
        return text


@pytest.fixture
def config():
    return FindingAidsConfig.load()


@pytest.fixture
def theme(config):
    return next(iter(config.themes))


@pytest.fixture
def stub_search(monkeypatch):
    def _search(ctx, query, *, sources=None, limit=10, config=None, channel=None,
                root=None):
        return [FindingAidResult(source="pldb", item_id="rust", label="Rust",
                                 fields={"paradigms": "functional"},
                                 url="https://pldb.io/concepts/rust.html",
                                 retrieved_at="2026-09-08T00:00:00Z",
                                 mirror_version="abc1234")]

    monkeypatch.setattr("langatlas_finding_aids.checklist.search_finding_aids", _search)


def _store(tmp_path, *, feature=None):
    for directory in ("concepts", "features", "languages", "edges", "rules", "sources"):
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    (tmp_path / "languages" / "_registry.yaml").write_text("languages: {}\n")
    if feature:
        (tmp_path / "features" / "f.yaml").write_text(feature)
    return tmp_path


def test_an_empty_store_covers_nothing(tmp_path):
    assert store_coverage(_store(tmp_path)) == {}


def test_coverage_indexes_a_feature_by_name_and_alias(tmp_path):
    root = _store(tmp_path, feature=(
        "id: f.type-inference\nname: Type inference\naliases: [Hindley-Milner]\n"))
    coverage = store_coverage(root)
    assert coverage["type inference"] == {"f.type-inference"}
    assert coverage["hindley-milner"] == {"f.type-inference"}


def test_a_checklist_has_one_row_per_theme_term_and_language(config, theme, tmp_path,
                                                             stub_search):
    checklist = build_checklist(_Ctx(), theme, config=config, repo_root=_store(tmp_path))
    entry = config.theme(theme)
    assert len(checklist.rows) == len(entry["terms"]) * len(entry["languages"])


def test_rows_report_store_coverage_when_the_feature_exists(config, theme, tmp_path,
                                                            stub_search):
    term = config.theme(theme)["terms"][0]
    root = _store(tmp_path, feature=f"id: f.covered\nname: {term}\n")
    checklist = build_checklist(_Ctx(), theme, config=config, repo_root=root)
    covered = [row for row in checklist.rows if row.term == term]
    assert covered and all(row.covered_by == ("f.covered",) for row in covered)


def test_uncovered_rows_are_the_point_of_the_artifact(config, theme, tmp_path,
                                                      stub_search):
    checklist = build_checklist(_Ctx(), theme, config=config, repo_root=_store(tmp_path))
    assert all(row.covered_by == () for row in checklist.rows)
    assert "GAP" in checklist.to_markdown()


def test_the_checklist_header_pins_the_mirror_versions(config, theme, tmp_path,
                                                       stub_search):
    """Plan decision 4: the artifact is not committed, so it has to say what it was built
    from or an R3 survey citing it is irreproducible."""
    checklist = build_checklist(_Ctx(), theme, config=config, repo_root=_store(tmp_path))
    assert "abc1234" in checklist.to_markdown()
    assert checklist.mirror_versions["pldb"] == "abc1234"


def test_an_unknown_theme_is_refused_before_any_query(config, tmp_path, stub_search):
    with pytest.raises(UnknownTheme):
        build_checklist(_Ctx(), "no-such-theme", config=config,
                        repo_root=_store(tmp_path))


def test_writing_produces_a_markdown_and_a_json_sibling(config, theme, tmp_path,
                                                        stub_search):
    checklist = build_checklist(_Ctx(), theme, config=config, repo_root=_store(tmp_path))
    md, js = write_checklist(checklist, out_dir=tmp_path / "out")
    assert md.suffix == ".md" and js.suffix == ".json"
    assert json.loads(js.read_text())["theme"] == theme


def test_the_written_artifact_never_lands_in_the_repo(config, theme, tmp_path,
                                                      stub_search):
    from langatlas_finding_aids import paths

    assert paths.REPO_ROOT not in paths.CHECKLIST_DIR.parents
