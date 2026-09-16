"""Turning an admitted carve plan into committed records. Task 10 fills this in; the one
function here is what the ontologist needs to know which dimensions already exist."""
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.taxonomy import DIMENSIONS_PATH, QUALITIES_PATH

_yaml = YAML(typ="safe")


def _slugs(repo_root: Path | None, rel: str, key: str) -> set[str]:
    path = (Path(repo_root) if repo_root else Path(".")) / rel
    if not path.exists():
        return set()
    data = _yaml.load(path.read_text()) or {}
    return {entry["slug"] for entry in (data.get(key) or [])}


def committed_dimensions(repo_root: Path | None = None) -> set[str]:
    return _slugs(repo_root, DIMENSIONS_PATH, "dimensions")


def committed_qualities(repo_root: Path | None = None) -> set[str]:
    return _slugs(repo_root, QUALITIES_PATH, "qualities")
