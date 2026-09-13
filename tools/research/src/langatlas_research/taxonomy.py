"""The three shared-list files: layer-3 dimensions, the controlled quality vocabulary, and
the language-id mint authority.

Entries are kept slug-sorted so two agents adding different entries produce a diff git can
merge, and the same entry produces the identical file regardless of who wrote it first."""
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.mint import MintedRecord, content_digest, dump_yaml
from langatlas_validate.ids import is_valid_slug

_yaml = YAML(typ="safe")

DIMENSIONS_PATH = "ontology/taxonomy/dimensions.yaml"
QUALITIES_PATH = "ontology/taxonomy/qualities.yaml"
REGISTRY_PATH = "languages/_registry.yaml"


def _read(repo_root: Path | None, rel: str) -> tuple[dict, str]:
    path = (Path(repo_root) if repo_root else Path(".")) / rel
    text = path.read_text()
    return _yaml.load(text) or {}, content_digest(text)


def _require_slug(value: str) -> str:
    if not is_valid_slug(value):
        raise ValueError(f"invalid slug: {value!r} (§3.5)")
    return value


def mint_dimension(slug: str, *, label: str, values, exclusivity: str = "exclusive",
                   applies_to=("general-purpose",),
                   repo_root: Path | None = None) -> MintedRecord:
    """Adds one layer-3 dimension. `exclusivity` (D39) and `applies_to` (D50) are written
    pre-emptively on every dimension — they are not fields a later feature turns on.

    @raises ValueError: for an invalid slug or a dimension that already exists (changing
        an existing dimension is a restructure, not a mint — 3F's ceremony owns it)."""
    _require_slug(slug)
    data, digest = _read(repo_root, DIMENSIONS_PATH)
    entries = list(data.get("dimensions") or [])
    if any(entry["slug"] == slug for entry in entries):
        raise ValueError(f"dimension {slug!r} already exists")
    entries.append({"slug": slug, "label": label,
                    "values": [_require_slug(v) for v in values],
                    "exclusivity": exclusivity, "applies_to": list(applies_to)})
    entries.sort(key=lambda entry: entry["slug"])
    return MintedRecord(path=DIMENSIONS_PATH, text=dump_yaml({"dimensions": entries}),
                        kind="taxonomy", node_ids=(slug,), base_digest=digest)


def mint_quality(slug: str, *, label: str, summary: str,
                 repo_root: Path | None = None) -> MintedRecord:
    """Adds one entry to the controlled quality vocabulary (§3.1).
    @raises ValueError: invalid slug, or the quality already exists."""
    _require_slug(slug)
    data, digest = _read(repo_root, QUALITIES_PATH)
    entries = list(data.get("qualities") or [])
    if any(entry["slug"] == slug for entry in entries):
        raise ValueError(f"quality {slug!r} already exists")
    entries.append({"slug": slug, "label": label, "summary": summary})
    entries.sort(key=lambda entry: entry["slug"])
    return MintedRecord(path=QUALITIES_PATH, text=dump_yaml({"qualities": entries}),
                        kind="taxonomy", node_ids=(slug,), base_digest=digest)


def register_language(language_id: str, *, name: str,
                      repo_root: Path | None = None) -> MintedRecord:
    """§3.3: `languages/_registry.yaml` is the language-id mint authority. A Language
    record and its instances may only use an id this file already carries.
    @raises ValueError: invalid id, or the language is already registered."""
    _require_slug(language_id)
    data, digest = _read(repo_root, REGISTRY_PATH)
    languages = dict(data.get("languages") or {})
    if language_id in languages:
        raise ValueError(f"language {language_id!r} is already registered")
    languages[language_id] = {"name": name}
    ordered = {key: languages[key] for key in sorted(languages)}
    return MintedRecord(path=REGISTRY_PATH, text=dump_yaml({"languages": ordered}),
                       kind="language-registry", node_ids=(language_id,),
                       base_digest=digest)
