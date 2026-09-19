"""The R6 consolidation record: `research/consolidations/<cycle>-<theme>.yaml`.

R6's bookkeeping, as the carve plan is R4's and the reality check R5's. It records whether the
cross-theme pass ran (or why it was skipped), how the developer ruled on each dedup candidate,
and which migrations this consolidation landed. The edges live in the carve plan and the
migrations in `ontology/migrations/`; the rulings live only here, and a `distinct` ruling is
what stops the same pair being re-raised every cycle.

Pure: callers decide when to save."""
import io
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from langatlas_research.cycle import Cycle
from langatlas_research.errors import ConsolidationInvalid, ConsolidationMissing
from langatlas_research.paths import consolidations_dir
from langatlas_research.schema import validate_research_record

DEDUP_DISPOSITIONS = ("distinct", "merge", "drop-alias")

_yaml = YAML(typ="safe")


def consolidation_rel(cycle_slug: str) -> str:
    return f"research/consolidations/{cycle_slug}.yaml"


def consolidation_path(cycle_slug: str, repo_root: Path | None = None) -> Path:
    return consolidations_dir(repo_root) / f"{cycle_slug}.yaml"


def build_record(*, cycle: Cycle, opened_at: str) -> dict:
    """The theme digest is the sign-off's, like the carve plan's and the reality check's."""
    return {"cycle": cycle.number, "theme": cycle.theme,
            "theme_digest": cycle.signed_off["theme_digest"], "opened_at": opened_at,
            "cross_theme": {"run": None, "skipped": None, "edges": []},
            "dedup": [], "migrations": []}


def render_record(record: dict) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    buf = io.StringIO()
    yaml.dump(record, buf)
    return buf.getvalue()


def save_record(record: dict, *, repo_root: Path | None = None) -> Path:
    """@raises ConsolidationInvalid: the record fails its schema."""
    errors = validate_research_record(record, "consolidation", repo_root=repo_root)
    if errors:
        raise ConsolidationInvalid("consolidation record is invalid: " + "; ".join(errors))
    path = consolidation_path(f"{record['cycle']:02d}-{record['theme']}", repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_record(record))
    return path


def _read(path: Path) -> dict:
    """@raises ConsolidationInvalid: the file is not YAML, or not a mapping."""
    try:
        data = _yaml.load(path.read_text())
    except YAMLError as exc:
        raise ConsolidationInvalid(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConsolidationInvalid(f"{path} must hold a YAML mapping")
    return data


def load_record(cycle_slug: str, *, repo_root: Path | None = None) -> dict:
    """@raises ConsolidationMissing: no record for this cycle yet.
    @raises ConsolidationInvalid: the file is malformed."""
    path = consolidation_path(cycle_slug, repo_root)
    if not path.exists():
        raise ConsolidationMissing(f"no consolidation record at {path} — run"
                                   f" `langatlas-research consolidate open"
                                   f" {int(cycle_slug[:2])}` first")
    return _read(path)


def iter_records(repo_root: Path | None = None) -> list[dict]:
    directory = consolidations_dir(repo_root)
    if not directory.exists():
        return []
    return [_read(path) for path in sorted(directory.glob("*.yaml"))]


def add_migration(record: dict, migration_id: str) -> dict:
    return {**record, "migrations": sorted({*record["migrations"], migration_id})}


def add_ruling(record: dict, ruling: dict) -> dict:
    """A later ruling on the same pair replaces the earlier one: the developer changed their
    mind, and the record says what they think now (git keeps the history)."""
    kept = [entry for entry in record["dedup"] if entry["key"] != ruling["key"]]
    return {**record, "dedup": sorted([*kept, ruling], key=lambda entry: entry["key"])}
