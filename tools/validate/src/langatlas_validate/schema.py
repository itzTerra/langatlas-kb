import json
from functools import lru_cache
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from langatlas_validate.ids import is_valid_slug
from langatlas_validate.paths import SCHEMA_DIR as _SCHEMA_DIR

RECORD_KINDS = (
    "feature", "feature-instance", "edge", "affects-quality-edge",
    "rule", "language", "language-registry", "concept", "source",
)


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
    errors = [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(_validator(kind).iter_errors(data), key=str)
    ]
    errors.extend(_slug_errors(data, kind))
    return errors


def _slug_errors(data: dict, kind: str) -> list[str]:
    errors: list[str] = []
    if kind in ("feature", "concept"):
        slug = data.get("slug")
        if isinstance(slug, str) and not is_valid_slug(slug):
            errors.append(f"slug: invalid slug format: {slug!r}")
    elif kind in ("edge", "affects-quality-edge"):
        for field in ("from", "to"):
            value = data.get(field)
            if isinstance(value, str) and not is_valid_slug(value):
                errors.append(f"{field}: invalid slug format: {value!r}")
    return errors
