import json
from functools import lru_cache
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

RECORD_KINDS = (
    "feature", "feature-instance", "edge", "affects-quality-edge",
    "rule", "language", "language-registry", "concept", "source",
)

# src layout: .../tools/validate/src/langatlas_validate/schema.py -> parents[4] == repo root
_SCHEMA_DIR = Path(__file__).resolve().parents[4] / "ontology" / "schema"


@lru_cache(maxsize=None)
def _registry() -> Registry:
    reg = Registry()
    for path in _SCHEMA_DIR.glob("*.schema.json"):
        contents = json.loads(path.read_text())
        resource = Resource.from_contents(contents)
        reg = reg.with_resource(path.name, resource)
        # Each schema declares its own absolute "$id" (e.g.
        # "https://langatlas.dev/schema/rule"), which jsonschema uses as the
        # resolution *base URI* for that document's own "$ref"s. A relative
        # ref like "defs.schema.json#/$defs/provenance" therefore resolves
        # per RFC 3986 against that base, not against the bare filename key
        # registered above -- it joins to
        # "https://langatlas.dev/schema/defs.schema.json". Register every
        # resource under that joined form too so cross-file "$ref"s resolve
        # regardless of which schema is doing the referencing.
        reg = reg.with_resource(
            f"https://langatlas.dev/schema/{path.name}", resource
        )
    return reg


@lru_cache(maxsize=None)
def _validator(kind: str) -> Draft202012Validator:
    if kind not in RECORD_KINDS:
        raise ValueError(f"unknown record kind: {kind!r}")
    schema = json.loads((_SCHEMA_DIR / f"{kind}.schema.json").read_text())
    return Draft202012Validator(schema, registry=_registry())


def validate_record(data: dict, kind: str) -> list[str]:
    if kind not in RECORD_KINDS:
        raise ValueError(f"unknown record kind: {kind!r}")
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(_validator(kind).iter_errors(data), key=str)
    ]
