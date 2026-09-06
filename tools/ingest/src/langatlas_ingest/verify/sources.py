from dataclasses import dataclass
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_validate.paths import REPO_ROOT

_yaml = YAML(typ="safe")

# CSL fields that identify a publishing body. Two sources sharing any of them are not
# independent (Section 6.3) — a book and its own chapter reprint corroborate nothing.
_VENUE_FIELDS = ("publisher", "container-title", "collection-title")


@dataclass(frozen=True)
class SourceFacts:
    """What the verifier needs from a committed `sources/*.yaml` record: the tier the
    admissibility rule reads, the grounding and locator kinds stage 0 checks against, and
    the CSL body the independence check runs on."""

    id: str
    tier: str
    grounding: str
    locator_kinds: tuple[str, ...]
    csl: dict


def load_source_facts(sources_dir: Path | None = None) -> dict[str, SourceFacts]:
    """Load every committed source record's verification-relevant fields.

    Read from git, not Postgres: tier is canonical data (D1), and a verifier that read it
    from a derived table could admit a fact on a tier the store does not actually claim.

    @param sources_dir - defaults to `<repo>/sources`

    @returns source_id -> SourceFacts, ledgers (`_`-prefixed files) excluded
    """
    directory = Path(sources_dir or REPO_ROOT / "sources")
    loaded: dict[str, SourceFacts] = {}
    for path in sorted(directory.glob("*.yaml")):
        if path.stem.startswith("_"):
            continue
        data = _yaml.load(path.read_text()) or {}
        custom = data.get("custom") or {}
        loaded[data.get("id", path.stem)] = SourceFacts(
            id=data.get("id", path.stem), tier=custom.get("tier", ""),
            grounding=custom.get("grounding", ""),
            locator_kinds=tuple(custom.get("locator_kinds") or ()), csl=data)
    return loaded


def _authors(csl: dict) -> set[str]:
    return {f"{a.get('family', '')}|{a.get('given', '')}".strip().lower()
            for a in csl.get("author") or [] if isinstance(a, dict)}


def _venues(csl: dict) -> set[str]:
    return {str(csl[field]).strip().lower() for field in _VENUE_FIELDS if csl.get(field)}


def are_independent(a: SourceFacts, b: SourceFacts) -> bool:
    """Section 6.3's mechanical independence check: no shared author, no shared
    publisher/venue.

    Missing metadata on either side is *borderline*, and Section 6.3 fixes borderline as
    **not independent** — the conservative direction, since the only thing independence
    can do is raise a confidence level.

    @returns True only when both records carry enough CSL to prove independence
    """
    if a.id == b.id:
        return False
    authors_a, authors_b = _authors(a.csl), _authors(b.csl)
    if not authors_a or not authors_b or (authors_a & authors_b):
        return False
    venues_a, venues_b = _venues(a.csl), _venues(b.csl)
    if not venues_a or not venues_b:
        return False
    return not (venues_a & venues_b)
