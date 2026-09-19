"""R6's slug polish (§7.4, §5.1). A node's id never changes; its slug may, and every old slug
keeps resolving through `ontology/redirects.yaml` — so a rename is a PATCH, never a broken URL.
Candidates are mechanical; the rename is the developer's."""
import re
import unicodedata
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from langatlas_research.errors import SlugRefused
from langatlas_research.mint import dump_yaml
from langatlas_research.rotation import PARADIGM_FAMILIES
from langatlas_validate.ids import MAX_SLUG_LEN, is_valid_slug
from langatlas_validate.normalize import normalize_record
from langatlas_validate.redirects import REDIRECTS_REL, load_redirects, render_redirects

_safe = YAML(typ="safe")
_KINDS = (("concepts", "concept"), ("features", "feature"))


def slugify(name: str) -> str:
    """§3.5's grammar: ASCII, lowercase, hyphen-joined, no leading digit, at most 48 chars."""
    ascii_text = (unicodedata.normalize("NFKD", name).encode("ascii", "ignore")
                  .decode("ascii").lower())
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    slug = re.sub(r"^[0-9-]+", "", slug)
    return slug[:MAX_SLUG_LEN].rstrip("-")


def _nodes(repo_root: Path) -> dict[str, tuple[str, str, dict]]:
    """@raises SlugRefused: a concept or feature file that is not a YAML mapping with a string
        id, slug and name."""
    root = Path(repo_root)
    nodes = {}
    for directory, kind in _KINDS:
        for path in sorted((root / directory).glob("*.yaml")):
            rel = str(path.relative_to(root))
            try:
                data = _safe.load(path.read_text())
            except YAMLError as exc:
                raise SlugRefused(f"{rel} is not valid YAML: {exc}") from exc
            if not isinstance(data, dict) or not all(
                    isinstance(data.get(key), str) for key in ("id", "slug", "name")):
                raise SlugRefused(f"{rel} is not a record mapping with a string id, slug and name")
            nodes[data["id"]] = (rel, kind, data)
    return nodes


def _redirects(repo_root: Path) -> dict[str, str]:
    try:
        redirects = load_redirects(repo_root)
    except (YAMLError, AttributeError, TypeError, ValueError) as exc:
        raise SlugRefused(f"{REDIRECTS_REL} is malformed: {exc}") from exc
    if not all(isinstance(old, str) and isinstance(new, str) for old, new in redirects.items()):
        raise SlugRefused(f"{REDIRECTS_REL} is malformed: entries must map slug to node id")
    return redirects


def _language_ids(repo_root: Path) -> set[str]:
    """The D28 set plus anything registered since: a slug token equal to one of these names a
    language, which §3.5 keeps out of feature naming."""
    ids = set(PARADIGM_FAMILIES)
    registry = Path(repo_root) / "languages" / "_registry.yaml"
    if registry.exists():
        try:
            loaded = _safe.load(registry.read_text())
        except YAMLError as exc:
            raise SlugRefused(f"languages/_registry.yaml is not valid YAML: {exc}") from exc
        languages = loaded.get("languages") if isinstance(loaded, dict) else None
        if isinstance(languages, dict):
            ids |= set(languages)
    return ids


def slug_candidates(repo_root: Path) -> list[dict]:
    languages = _language_ids(repo_root)
    found = []
    for node_id, (_rel, _kind, data) in sorted(_nodes(repo_root).items()):
        signals = []
        suggested = slugify(data["name"])
        if suggested and suggested != data["slug"]:
            signals.append("slug-differs-from-name")
        if set(data["slug"].split("-")) & languages:
            signals.append("language-specific")
        if signals:
            found.append({"node": node_id, "slug": data["slug"], "suggested": suggested,
                          "signals": signals})
    return found


def rename_slug(repo_root: Path, node_id: str, new_slug: str) -> dict[str, str]:
    """@returns the changeset: the node's record and the redirect map, which must land together.
    @raises SlugRefused: an unknown node, an invalid or unchanged slug, a slug a live node owns,
        or one that already redirects to a different node."""
    root = Path(repo_root)
    nodes = _nodes(root)
    if node_id not in nodes:
        raise SlugRefused(f"{node_id!r} is not a committed concept or feature")
    if not is_valid_slug(new_slug):
        raise SlugRefused(f"{new_slug!r} is not a valid slug (§3.5)")
    rel, kind, data = nodes[node_id]
    old = data["slug"]
    if new_slug == old:
        raise SlugRefused(f"{node_id} already has slug {new_slug!r}")
    live = {entry["slug"]: other for other, (_r, _k, entry) in nodes.items()}
    if new_slug in live:
        raise SlugRefused(f"{new_slug!r} is already the slug of {live[new_slug]}")
    redirects = _redirects(root)
    if redirects.get(new_slug, node_id) != node_id:
        raise SlugRefused(f"{new_slug!r} already redirects to {redirects[new_slug]} — a published"
                          f" URL must keep pointing where it pointed")
    redirects.pop(new_slug, None)
    redirects[old] = node_id
    record = YAML().load((root / rel).read_text())
    record["slug"] = new_slug
    return {rel: normalize_record(dump_yaml(record), kind),
            REDIRECTS_REL: render_redirects(redirects)}
