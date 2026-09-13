import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.paths import themes_path
from langatlas_research.schema import validate_research_record
from langatlas_validate.normalize import normalize_value

_yaml = YAML(typ="safe")
DIGEST_HEX_LEN = 16


@dataclass(frozen=True)
class Theme:
    slug: str
    label: str
    summary: str
    seed_terms: tuple[str, ...] = ()
    note: str = ""


def theme_digest(theme: Theme) -> str:
    """Content key over the parts of a theme a sign-off is an opinion *about*.

    Whitespace-insensitive (§3.5's normalization rules), so reflowing a summary does not
    re-open the gate, while changing what the theme covers does.

    @returns: 16 lowercase hex chars."""
    body = json.dumps({
        "slug": theme.slug,
        "label": normalize_value(theme.label),
        "summary": normalize_value(theme.summary),
        "seed_terms": sorted(normalize_value(t) for t in theme.seed_terms),
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:DIGEST_HEX_LEN]


def load_themes(repo_root: Path | None = None) -> dict[str, Theme]:
    """@returns: themes keyed by slug, in file order.
    @raises ValueError: when the registry does not satisfy its schema."""
    data = _yaml.load(themes_path(repo_root).read_text()) or {}
    errors = validate_research_record(data, "theme-registry", repo_root=repo_root)
    if errors:
        raise ValueError("research/themes.yaml is invalid: " + "; ".join(errors))
    return {
        entry["slug"]: Theme(
            slug=entry["slug"], label=entry["label"], summary=entry["summary"],
            seed_terms=tuple(entry.get("seed_terms", ())), note=entry.get("note", ""))
        for entry in data["themes"]
    }
