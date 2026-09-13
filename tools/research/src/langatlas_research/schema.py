"""Research artifacts validate against their own schemas, not against the canonical
store's `RECORD_KINDS`. `validate_research_tree` maps a directory to a kind and validates
every file in it — a later sub-plan adds `survey.schema.json` or `debate.schema.json` and
this module picks it up with no code change. A directory that holds files but has no schema
yet is a hard error rather than a silent skip: an unvalidated artifact directory is exactly
how a format drifts."""
import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from ruamel.yaml import YAML

from langatlas_research.paths import research_root, research_schema_dir

DIR_KINDS = {"cycles": "cycle", "surveys": "survey", "debates": "debate",
             "reality-checks": "reality-check"}

_yaml = YAML(typ="safe")


@lru_cache(maxsize=None)
def _validator(schema_path: str, mtime: float) -> Draft202012Validator:
    return Draft202012Validator(json.loads(Path(schema_path).read_text()))


def _load_validator(kind: str, repo_root: Path | None) -> Draft202012Validator | None:
    path = research_schema_dir(repo_root) / f"{kind}.schema.json"
    if not path.exists():
        return None
    return _validator(str(path), path.stat().st_mtime)


def validate_research_record(data: dict, kind: str, *,
                             repo_root: Path | None = None) -> list[str]:
    """@returns: error strings, one per violation, empty when the record is valid.
    @raises FileNotFoundError: when no schema for `kind` is committed yet."""
    validator = _load_validator(kind, repo_root)
    if validator is None:
        raise FileNotFoundError(
            f"research/schema/{kind}.schema.json is missing — the sub-plan that writes"
            f" {kind} records must ship its schema")
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in sorted(validator.iter_errors(data), key=str)]


def validate_research_tree(repo_root: Path | None = None) -> list[str]:
    """Validates `research/themes.yaml` and every artifact directory. @returns: error
    strings prefixed with the offending repo-relative path."""
    errors: list[str] = []
    root = research_root(repo_root)
    if not root.exists():
        return errors

    registry = root / "themes.yaml"
    if registry.exists():
        if _load_validator("theme-registry", repo_root) is None:
            errors.append("research/themes.yaml: no schema"
                          " (research/schema/theme-registry.schema.json) — the sub-plan"
                          " that writes this file must ship one")
        else:
            errors.extend(f"research/themes.yaml: {e}" for e in validate_research_record(
                _yaml.load(registry.read_text()) or {}, "theme-registry", repo_root=repo_root))

    for name, kind in DIR_KINDS.items():
        directory = root / name
        files = sorted(directory.glob("*.yaml")) if directory.exists() else []
        if not files:
            continue
        if _load_validator(kind, repo_root) is None:
            errors.append(f"research/{name}: no schema (research/schema/{kind}.schema.json)"
                          f" — the sub-plan that writes this directory must ship one")
            continue
        for path in files:
            data = _yaml.load(path.read_text()) or {}
            errors.extend(f"research/{name}/{path.name}: {e}"
                          for e in validate_research_record(data, kind, repo_root=repo_root))
    return errors
