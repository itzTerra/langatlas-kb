"""One file per theme cycle. The cycle record is the only place that knows which nodes a
theme minted: node schemas have no `theme` field (and `additionalProperties: false` means
they cannot grow one casually), so theme membership lives here, where 3F's settled-theme
ceremony and `coverage report.py dossier` read it."""
import io
from dataclasses import dataclass, replace
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from langatlas_research.errors import (
    InvalidTransition, ResearchError, SignOffMissing, SignOffStale, UnknownTheme,
)
from langatlas_research.paths import cycles_dir
from langatlas_research.schema import validate_research_record
from langatlas_research.themes import load_themes, theme_digest

CYCLE_STATUSES = ("drafted", "signed-off", "r3-done", "r4-done", "r5-done", "settled")

_yaml = YAML(typ="safe")


def _dumper() -> YAML:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    return yaml


@dataclass(frozen=True)
class Cycle:
    number: int
    theme: str
    theme_digest: str
    status: str
    languages: tuple[str, ...]
    nodes_minted: tuple[str, ...] = ()
    artifacts: dict | None = None
    signed_off: dict | None = None
    settled: dict | None = None

    @property
    def slug(self) -> str:
        return f"{self.number:02d}-{self.theme}"

    def as_dict(self) -> dict:
        data = {"cycle": self.number, "theme": self.theme,
                "theme_digest": self.theme_digest, "status": self.status,
                "languages": list(self.languages),
                "nodes_minted": list(self.nodes_minted),
                "artifacts": dict(self.artifacts or {})}
        if self.signed_off is not None:
            data["signed_off"] = dict(self.signed_off)
        if self.settled is not None:
            data["settled"] = dict(self.settled)
        return data


def cycle_path(number: int, theme: str, repo_root: Path | None = None) -> Path:
    return cycles_dir(repo_root) / f"{number:02d}-{theme}.yaml"


def _current_digest(theme: str, repo_root: Path | None) -> str:
    themes = load_themes(repo_root)
    if theme not in themes:
        raise UnknownTheme(f"{theme!r} is not in research/themes.yaml")
    return theme_digest(themes[theme])


def new_cycle(number: int, theme: str, *, repo_root: Path | None = None,
              languages: tuple[str, ...] | None = None) -> Cycle:
    """Drafts cycle `number` for `theme`. @raises UnknownTheme: unknown theme slug."""
    if languages is None:
        from langatlas_research.rotation import plan_languages
        languages = plan_languages(number)
    cycle = Cycle(number=number, theme=theme,
                  theme_digest=_current_digest(theme, repo_root), status="drafted",
                  languages=tuple(languages), nodes_minted=(), artifacts={})
    save_cycle(cycle, repo_root=repo_root)
    return cycle


def save_cycle(cycle: Cycle, *, repo_root: Path | None = None) -> Path:
    """@raises ValueError: when the record does not satisfy cycle.schema.json."""
    data = cycle.as_dict()
    errors = validate_research_record(data, "cycle", repo_root=repo_root)
    if errors:
        raise ValueError(f"cycle {cycle.slug} is invalid: " + "; ".join(errors))
    path = cycle_path(cycle.number, cycle.theme, repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    _dumper().dump(data, buf)
    path.write_text(buf.getvalue())
    return path


def load_cycle(number: int, *, repo_root: Path | None = None) -> Cycle:
    """@raises FileNotFoundError: when no cycle with that number is committed."""
    matches = sorted(cycles_dir(repo_root).glob(f"{number:02d}-*.yaml"))
    if not matches:
        raise FileNotFoundError(f"no cycle {number:02d} in research/cycles/")
    data = _yaml.load(matches[0].read_text())
    return Cycle(number=data["cycle"], theme=data["theme"],
                 theme_digest=data["theme_digest"], status=data["status"],
                 languages=tuple(data["languages"]),
                 nodes_minted=tuple(data["nodes_minted"]),
                 artifacts=dict(data.get("artifacts") or {}),
                 signed_off=data.get("signed_off"),
                 settled=data.get("settled"))


def sign_off(cycle: Cycle, *, by: str, date: str, repo_root: Path | None = None) -> Cycle:
    """D27's hard checkpoint. Re-stamps the digest from the current theme text, so a
    sign-off always describes the theme as it stands at the moment of signing."""
    digest = _current_digest(cycle.theme, repo_root)
    signed = replace(cycle, theme_digest=digest, status="signed-off",
                     signed_off={"by": by, "date": date, "theme_digest": digest})
    save_cycle(signed, repo_root=repo_root)
    return signed


def require_sign_off(cycle: Cycle, *, repo_root: Path | None = None) -> None:
    """The gate every R3-R6 runner calls first.

    @raises SignOffMissing: no sign-off block.
    @raises SignOffStale: the theme changed after it was signed — the developer signed a
        different scope than the one that would now run."""
    if not cycle.signed_off:
        raise SignOffMissing(
            f"cycle {cycle.slug} has no developer sign-off (D27): run"
            f" `langatlas-research cycle sign-off {cycle.number}` first")
    current = _current_digest(cycle.theme, repo_root)
    if cycle.signed_off.get("theme_digest") != current:
        raise SignOffStale(
            f"cycle {cycle.slug} was signed off against theme digest"
            f" {cycle.signed_off.get('theme_digest')}, but research/themes.yaml now reads"
            f" {current} — re-sign the cycle before running it")


def advance(cycle: Cycle, status: str) -> Cycle:
    """@raises InvalidTransition: for an unknown status or a backward move. Returns the
    updated cycle; the caller saves it (so a runner can advance only after its own work
    actually landed)."""
    if status not in CYCLE_STATUSES:
        raise InvalidTransition(f"unknown cycle status: {status!r}")
    if CYCLE_STATUSES.index(status) <= CYCLE_STATUSES.index(cycle.status):
        raise InvalidTransition(
            f"cycle {cycle.slug} is already at {cycle.status!r}; cannot move to {status!r}")
    return replace(cycle, status=status)


def record_minted(cycle: Cycle, node_ids, *, repo_root: Path | None = None) -> Cycle:
    """Append-only, sorted, deduped — the theme-membership list 3F's settled-theme
    ceremony reads."""
    merged = tuple(sorted(set(cycle.nodes_minted) | set(node_ids)))
    updated = replace(cycle, nodes_minted=merged)
    save_cycle(updated, repo_root=repo_root)
    return updated


def settle_cycle(cycle: Cycle, *, by: str, date: str) -> Cycle:
    """§7.4's settled state: once a theme passes R5 and its R6 consolidation closes, a
    restructure of its records needs a migration manifest. Settling is the developer's act —
    like sign-off, it names who and when. Pure: `consolidate settle` saves and lands it.

    @raises InvalidTransition: the cycle is not at `r5-done`."""
    if cycle.status != "r5-done":
        raise InvalidTransition(f"cycle {cycle.slug} is at {cycle.status!r}; only an r5-done"
                                f" cycle can be settled")
    return replace(advance(cycle, "settled"), settled={"by": by, "date": date})


def settled_themes_by_record(cycle_dicts) -> dict[str, str]:
    """@param cycle_dicts: parsed cycle records (as `load_cycle` reads them, or as git holds
        them at some ref — the settled-theme guard reads history).
    @raises ResearchError: a settled cycle has no theme (fail loud, never fail open).
    @returns: record id -> theme, for every id a settled cycle minted. Theme membership lives
        on the cycle (3A): node schemas have no theme field."""
    membership: dict[str, str] = {}
    for data in cycle_dicts:
        if isinstance(data, dict) and data.get("status") == "settled":
            theme = data.get("theme")
            if not theme:
                raise ResearchError(f"settled cycle {data.get('cycle')!r} has no theme: "
                                    f"malformed, so its records cannot be protected")
            for record_id in data.get("nodes_minted") or []:
                membership.setdefault(record_id, theme)
    return membership


def settled_record_ids(repo_root: Path | None = None) -> dict[str, str]:
    """@raises ResearchError: a cycle file is not parseable YAML."""
    loaded = []
    for path in sorted(cycles_dir(repo_root).glob("*.yaml")):
        try:
            loaded.append(_yaml.load(path.read_text()))
        except YAMLError as exc:
            raise ResearchError(f"{path.name}: malformed cycle file: {exc}") from exc
    return settled_themes_by_record(loaded)
