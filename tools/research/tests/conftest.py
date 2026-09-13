import subprocess

import pytest

from langatlas_research.paths import REPO_ROOT, ensure_layout


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture
def store_repo(tmp_path):
    """A throwaway origin + clone carrying just enough canonical store to validate.

    `core.hooksPath` is pointed at an empty directory so this machine's global pre-commit
    hook does not reject the commits `land_record` makes from a subprocess."""
    origin = tmp_path / "origin.git"
    clone = tmp_path / "clone"
    hooks = tmp_path / "no-hooks"
    hooks.mkdir()
    _git(["init", "--bare", "-b", "main", str(origin)], tmp_path)
    _git(["clone", str(origin), str(clone)], tmp_path)
    for key, value in (("user.email", "bot@example.com"), ("user.name", "bot"),
                       ("core.hooksPath", str(hooks)), ("commit.gpgsign", "false")):
        _git(["config", key, value], clone)

    for directory in ("concepts", "features", "edges", "rules", "sources",
                      "ontology/taxonomy", "languages"):
        (clone / directory).mkdir(parents=True, exist_ok=True)
        (clone / directory / ".gitkeep").touch()
    for rel in ("ontology/taxonomy/dimensions.yaml", "ontology/taxonomy/qualities.yaml",
                "ontology/taxonomy/layers.yaml", "ontology/taxonomy/edge-types.yaml",
                "languages/_registry.yaml"):
        (clone / rel).write_text((REPO_ROOT / rel).read_text())
    (clone / "contradictions.yaml").write_text("contradictions: []\n")
    (clone / "ontology").mkdir(exist_ok=True)
    (clone / "ontology" / "VERSION").write_text((REPO_ROOT / "ontology" / "VERSION").read_text())
    (clone / "ontology" / "CHANGELOG.md").write_text("# Ontology changelog\n")

    ensure_layout(clone)
    for name in ("theme-registry", "cycle"):
        (clone / "research" / "schema" / f"{name}.schema.json").write_text(
            (REPO_ROOT / "research" / "schema" / f"{name}.schema.json").read_text())
    (clone / "research" / "themes.yaml").write_text(
        (REPO_ROOT / "research" / "themes.yaml").read_text())

    _git(["add", "-A"], clone)
    _git(["commit", "-q", "-m", "seed"], clone)
    _git(["push", "-q", "origin", "HEAD:main"], clone)
    return clone
