"""`ontology/redirects.yaml` — every historical slug, mapped to the immutable node id it now
resolves to (D16/§5.1). A slug rename writes one line here, and so does a merge (both old URLs
301, §5.2). The site resolves a redirect's node id to that node's *current* slug, so a chain of
renames never needs chaining here."""
import io
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_validate.ids import is_valid_slug

REDIRECTS_REL = "ontology/redirects.yaml"

_safe = YAML(typ="safe")


def parse_redirects(text: str | None) -> dict[str, str]:
    if not text:
        return {}
    return dict((_safe.load(text) or {}).get("redirects") or {})


def load_redirects(repo_root: Path) -> dict[str, str]:
    path = Path(repo_root) / REDIRECTS_REL
    return parse_redirects(path.read_text() if path.exists() else None)


def render_redirects(mapping: dict[str, str]) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    buf = io.StringIO()
    yaml.dump({"redirects": dict(sorted(mapping.items()))}, buf)
    return buf.getvalue()


def validate_redirects(mapping: dict[str, str], *, nodes: dict[str, str]) -> list[str]:
    """@param nodes: live concept and feature ids -> their current slug.
    @returns one message per violation."""
    live_slugs = {slug: node_id for node_id, slug in nodes.items()}
    errors = []
    for old, target in sorted(mapping.items()):
        if not is_valid_slug(str(old)):
            errors.append(f"{old!r}: not a valid slug (§3.5)")
        if target not in nodes:
            errors.append(f"{old} -> {target}: no such concept or feature")
        if old in live_slugs:
            errors.append(f"{old}: is the current slug of {live_slugs[old]} — a live slug cannot"
                          f" also be a redirect")
    return errors
