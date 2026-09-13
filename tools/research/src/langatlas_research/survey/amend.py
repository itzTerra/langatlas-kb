"""Theme-list amendments (§7.4: the final theme list is itself an R3 deliverable).

The surveyor proposes; the developer applies, through the CLI, one amendment at a time. No
new gate logic is needed: an applied edit changes the theme's digest, and 3A's
`require_sign_off` already refuses any cycle signed against the old text. Slugs are immutable
once a cycle names them — a cycle file points at its theme by slug, so removing one would
orphan the cycle's bookkeeping."""
import io
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.cycle import Cycle, load_cycle
from langatlas_research.errors import AmendmentRefused
from langatlas_research.paths import cycles_dir, themes_path
from langatlas_research.schema import validate_research_record
from langatlas_research.themes import load_themes, theme_digest

_FIELDS = ("label", "summary", "seed_terms")


def _cycles(repo_root: Path | None) -> list[Cycle]:
    return [load_cycle(int(path.name[:2]), repo_root=repo_root)
            for path in sorted(cycles_dir(repo_root).glob("*.yaml"))]


def stale_cycles(repo_root: Path | None = None) -> list[Cycle]:
    themes = load_themes(repo_root)
    return [cycle for cycle in _cycles(repo_root)
            if cycle.signed_off and cycle.theme in themes
            and cycle.signed_off["theme_digest"] != theme_digest(themes[cycle.theme])]


def _roundtrip() -> YAML:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    yaml.preserve_quotes = True
    return yaml


def apply_amendment(amendment: dict, *, repo_root: Path | None = None) -> list[str]:
    """@raises AmendmentRefused: see the Interfaces block; nothing is written on refusal.
    @returns: slugs of cycles whose sign-off this amendment made stale."""
    if amendment.get("status") != "proposed":
        raise AmendmentRefused(f"only a proposed amendment can be applied, this one is"
                               f" {amendment.get('status')!r}")
    yaml = _roundtrip()
    path = themes_path(repo_root)
    registry = yaml.load(path.read_text())
    entries = registry["themes"]
    slug, op = amendment["slug"], amendment["op"]
    position = next((i for i, entry in enumerate(entries) if entry["slug"] == slug), None)

    if op == "add":
        if position is not None:
            raise AmendmentRefused(f"theme {slug!r} already exists")
        if not amendment.get("label") or not amendment.get("summary"):
            raise AmendmentRefused(f"adding {slug!r} needs both a label and a summary")
        entries.append({"slug": slug, **{f: amendment[f] for f in _FIELDS if f in amendment}})
    elif position is None:
        raise AmendmentRefused(f"no theme {slug!r} to {op}")
    elif op == "edit":
        for field in _FIELDS:
            if field in amendment:
                entries[position][field] = amendment[field]
    elif op == "remove":
        users = [cycle.slug for cycle in _cycles(repo_root) if cycle.theme == slug]
        if users:
            raise AmendmentRefused(f"theme {slug!r} is referenced by cycle(s)"
                                   f" {', '.join(users)}; slugs are immutable once used")
        del entries[position]
    else:
        raise AmendmentRefused(f"unknown amendment op {op!r}")

    errors = validate_research_record(YAML(typ="safe").load(_dump(yaml, registry)),
                                      "theme-registry", repo_root=repo_root)
    if errors:
        raise AmendmentRefused("the amended theme list is invalid: " + "; ".join(errors))
    path.write_text(_dump(yaml, registry))
    return [cycle.slug for cycle in stale_cycles(repo_root)]


def _dump(yaml: YAML, data) -> str:
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def mark_amendment(survey: dict, index: int, status: str) -> dict:
    amendments = [dict(item) for item in survey["theme_amendments"]]
    amendments[index]["status"] = status
    return {**survey, "theme_amendments": amendments}
