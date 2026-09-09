from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_finding_aids.paths import FINDING_AIDS_CONFIG_PATH

_yaml = YAML(typ="safe")

# D53 §O2's honest asymmetry: two backends offer no API and are mirrored monthly; two
# offer real APIs and are queried live under a conservative throttle.
MIRRORED_SOURCES = ("pldb", "hyperpolyglot")
LIVE_SOURCES = ("wikidata", "wikipedia")
ALL_SOURCES = MIRRORED_SOURCES + LIVE_SOURCES


class UnknownFindingAidSource(ValueError):
    """A caller named a source that is not one of D53's four."""


class UnknownTheme(KeyError):
    """`checklist --theme` named a theme `config/finding-aids.yaml` does not define."""


@dataclass(frozen=True)
class FindingAidsConfig:
    sources: tuple[str, ...]
    user_agent: str
    pldb: dict
    hyperpolyglot: dict
    wikidata: dict
    wikipedia: dict
    themes: dict

    @classmethod
    def load(cls, path: Path | None = None) -> "FindingAidsConfig":
        raw = _yaml.load((path or FINDING_AIDS_CONFIG_PATH).read_text()) or {}
        enabled = tuple(raw.get("sources") or ALL_SOURCES)
        unknown = set(enabled) - set(ALL_SOURCES)
        if unknown:
            raise UnknownFindingAidSource(
                f"config/finding-aids.yaml enables unknown sources: {sorted(unknown)}")
        return cls(sources=enabled,
                   user_agent=raw["user_agent"],
                   pldb=dict(raw.get("pldb") or {}),
                   hyperpolyglot=dict(raw.get("hyperpolyglot") or {}),
                   wikidata=dict(raw.get("wikidata") or {}),
                   wikipedia=dict(raw.get("wikipedia") or {}),
                   themes=dict(raw.get("themes") or {}))

    def settings(self, source: str) -> dict:
        if source not in ALL_SOURCES:
            raise UnknownFindingAidSource(source)
        return getattr(self, source)

    def min_interval(self, source: str) -> float:
        """Seconds between calls. A mirrored source reads a local file, so its interval
        is 0 by construction — the *refresh* job throttles, the read does not."""
        if source in MIRRORED_SOURCES:
            return 0.0
        return float(self.settings(source).get("min_interval_seconds", 2.0))

    def theme(self, slug: str) -> dict:
        try:
            return self.themes[slug]
        except KeyError:
            raise UnknownTheme(
                f"no theme {slug!r} in config/finding-aids.yaml"
                f" (have: {', '.join(sorted(self.themes)) or 'none'})") from None
