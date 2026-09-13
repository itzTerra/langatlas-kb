from langatlas_research.paths import (
    cycles_dir, ensure_layout, research_root, surveys_dir, themes_path,
)


def test_paths_hang_off_the_given_repo_root(tmp_path):
    assert research_root(tmp_path) == tmp_path / "research"
    assert themes_path(tmp_path) == tmp_path / "research" / "themes.yaml"
    assert cycles_dir(tmp_path) == tmp_path / "research" / "cycles"


def test_ensure_layout_creates_every_directory_with_a_readme(tmp_path):
    created = ensure_layout(tmp_path)

    assert (tmp_path / "research" / "cycles" / "README.md").exists()
    assert (tmp_path / "research" / "surveys" / "README.md").exists()
    assert (tmp_path / "research" / "debates" / "README.md").exists()
    assert (tmp_path / "research" / "reality-checks" / "README.md").exists()
    assert (tmp_path / "research" / "schema").is_dir()
    assert created, "the first run reports what it created"


def test_ensure_layout_is_idempotent_and_never_rewrites_a_readme(tmp_path):
    ensure_layout(tmp_path)
    (surveys_dir(tmp_path) / "README.md").write_text("edited by hand\n")

    assert ensure_layout(tmp_path) == []
    assert (surveys_dir(tmp_path) / "README.md").read_text() == "edited by hand\n"
