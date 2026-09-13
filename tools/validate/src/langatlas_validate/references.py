"""Referential integrity across the canonical store (§3.3).

Separate from `schema.py` because JSON Schema can validate a record in isolation and
nothing more: that an edge's endpoint names a feature that actually exists is a property of
the *store*, not of the record. Stage 3 is the first stage that mints nodes, so it is the
first stage where any of this can fail."""
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_validate.ids import compose_edge_id, compose_instance_id
from langatlas_validate.store import iter_store_records

_yaml = YAML(typ="safe")


def _taxonomy_slugs(repo_root: Path, rel: str, key: str) -> set[str]:
    path = repo_root / rel
    if not path.exists():
        return set()
    data = _yaml.load(path.read_text()) or {}
    return {entry["slug"] for entry in (data.get(key) or [])}


def _registry_ids(repo_root: Path) -> set[str]:
    path = repo_root / "languages" / "_registry.yaml"
    if not path.exists():
        return set()
    data = _yaml.load(path.read_text()) or {}
    return set((data.get("languages") or {}).keys())


def validate_references(repo_root: Path) -> list[str]:
    """@returns: one error string per violation, each prefixed with the offending path."""
    records = list(iter_store_records(repo_root))
    features = {data["id"] for _, kind, _, data in records if kind == "feature"}
    concepts = {data["id"] for _, kind, _, data in records if kind == "concept"}
    dimensions = _taxonomy_slugs(repo_root, "ontology/taxonomy/dimensions.yaml", "dimensions")
    qualities = _taxonomy_slugs(repo_root, "ontology/taxonomy/qualities.yaml", "qualities")
    languages = _registry_ids(repo_root)

    errors: list[str] = []

    def require(condition: bool, path: Path, message: str) -> None:
        if not condition:
            errors.append(f"{path.relative_to(repo_root)}: {message}")

    for path, kind, _text, data in records:
        record_id = data.get("id")

        if kind in ("feature", "concept", "rule"):
            require(path.stem == record_id, path,
                    f"filename does not match id {record_id!r} (§3.3)")
        if kind == "feature":
            dimension = data.get("dimension")
            if dimension is not None:
                require(dimension in dimensions, path,
                        f"dimension {dimension!r}: not declared in"
                        f" ontology/taxonomy/dimensions.yaml")
            for concept_id in data.get("realizes", []):
                require(concept_id in concepts, path,
                        f"realizes {concept_id!r}: no such concept")
        if kind in ("edge", "affects-quality-edge"):
            frm, to = data.get("from"), data.get("to")
            expected_id = compose_edge_id(data["type"], frm, to)
            require(record_id == expected_id, path,
                    f"id {record_id!r} is not the composition of its type and endpoints"
                    f" (expected {expected_id!r})")
            require(path.name == f"{data['type']}--{to}.yaml" and path.parent.name == frm,
                    path, f"filename must be edges/{frm}/{data['type']}--{to}.yaml (§3.3)")
            require(frm in features, path, f"from {frm!r}: no such feature")
            if kind == "edge":
                require(to in features, path, f"to {to!r}: no such feature")
            else:
                require(to in qualities, path,
                        f"to {to!r}: not in ontology/taxonomy/qualities.yaml")
        if kind == "rule":
            for feature_id in list(data.get("when_all", [])) + list(data.get("then", [])):
                require(feature_id in features, path,
                        f"{feature_id!r}: no such feature")
        if kind == "feature-instance":
            language, feature = data.get("language"), data.get("feature")
            if record_id is not None:
                require(record_id == compose_instance_id(language, feature), path,
                        f"id {record_id!r} is not fi.<language>.<feature>")
            require(path.stem == feature, path,
                    f"filename must be languages/{language}/instances/{feature}.yaml (§3.3)")
            require(language in languages, path,
                    f"language {language!r}: not in languages/_registry.yaml")
            require(feature in features, path, f"feature {feature!r}: no such feature")
        if kind == "language":
            require(record_id in languages, path,
                    f"language {record_id!r}: not in languages/_registry.yaml")

    return errors
