from langatlas_research.cli import main
from langatlas_research.cycle import load_cycle
from langatlas_research.paths import REPO_ROOT, ensure_layout, themes_path


def _research_repo(tmp_path):
    ensure_layout(tmp_path)
    for name in ("theme-registry", "cycle"):
        (tmp_path / "research" / "schema" / f"{name}.schema.json").write_text(
            (REPO_ROOT / "research" / "schema" / f"{name}.schema.json").read_text())
    themes_path(tmp_path).write_text(themes_path(REPO_ROOT).read_text())
    return tmp_path


def test_cycle_new_then_sign_off(tmp_path, capsys):
    repo = _research_repo(tmp_path)

    assert main(["--repo-root", str(repo), "cycle", "new", "1", "typing"]) == 0
    assert main(["--repo-root", str(repo), "cycle", "sign-off", "1",
                 "--by", "Michal Dolezel", "--date", "2026-09-20"]) == 0

    cycle = load_cycle(1, repo_root=repo)
    assert cycle.status == "signed-off"
    assert cycle.signed_off["by"] == "Michal Dolezel"
    assert len(cycle.languages) == 5


def test_validate_reports_a_broken_artifact(tmp_path):
    repo = _research_repo(tmp_path)
    (repo / "research" / "cycles" / "09-broken.yaml").write_text("cycle: nine\n")

    assert main(["--repo-root", str(repo), "validate"]) == 1


def test_themes_list_prints_every_theme(tmp_path, capsys):
    repo = _research_repo(tmp_path)

    assert main(["--repo-root", str(repo), "themes", "list"]) == 0

    out = capsys.readouterr().out
    assert "typing" in out and "qualities-vocabulary" in out
