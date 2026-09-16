"""The carve plan: R4's spine, `research/drafts/<cycle>-<theme>.yaml`.

Every R4 step reads this file and writes it back — the ontologist fills it, the debate
machinery annotates it, the gate stamps verdicts on it, the mint step marks what landed. It
exists so no step has to re-run a Claude session to learn what the previous one decided, and
so the developer has one diffable surface between "what a model proposed" and "what git holds".

A plan entry is a plain dict, not a dataclass: it is written, validated and re-read as YAML
far more often than it is constructed, and the schema — not a Python class — is the contract."""
import io
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.cycle import Cycle
from langatlas_research.errors import DraftMissing, DraftOutputInvalid
from langatlas_research.paths import drafts_dir
from langatlas_research.schema import validate_research_record

PLAN_STATUSES = ("proposed", "waived", "debated", "verified", "minted", "dropped")

# The plan's four entry lists, in **mint order**: a dimension must be committed before a
# layer-3 feature names it, a quality before an affects-quality edge points at it, a concept
# before a feature `realizes` it, and both endpoints before any edge. `minting.py` relies on
# this ordering; `references.validate_references` is what punishes getting it wrong.
ENTRY_LISTS = ("dimensions", "qualities", "nodes", "edges", "quality_edges")

_yaml = YAML(typ="safe")


def plan_path(cycle_slug: str, repo_root: Path | None = None) -> Path:
    return drafts_dir(repo_root) / f"{cycle_slug}.yaml"


def build_plan_record(*, cycle: Cycle, ontologist_run_id: str, generated_at: str) -> dict:
    """A plan with every list present and empty. The theme digest is copied from the
    sign-off, not from the theme file: a plan describes the scope the developer signed."""
    return {"cycle": cycle.number, "theme": cycle.theme,
            "theme_digest": cycle.signed_off["theme_digest"],
            "generated_at": generated_at,
            "survey": f"research/surveys/{cycle.slug}.yaml",
            "runs": {"ontologist": ontologist_run_id},
            "dimensions": [], "qualities": [], "nodes": [], "edges": [],
            "quality_edges": [], "findings": []}


def render_plan(data: dict) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def save_plan(data: dict, *, repo_root: Path | None = None) -> Path:
    """@raises DraftOutputInvalid: when the record does not satisfy draft.schema.json."""
    errors = validate_research_record(data, "draft", repo_root=repo_root)
    if errors:
        raise DraftOutputInvalid("carve plan is invalid: " + "; ".join(errors))
    path = plan_path(f"{data['cycle']:02d}-{data['theme']}", repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_plan(data))
    return path


def load_plan(cycle_slug: str, *, repo_root: Path | None = None) -> dict:
    """@raises DraftMissing: no carve plan for this cycle yet."""
    path = plan_path(cycle_slug, repo_root)
    if not path.exists():
        raise DraftMissing(f"no carve plan at {path} — run `langatlas-research draft atomize`"
                           f" first")
    return _yaml.load(path.read_text())


def entries(plan: dict):
    """@returns: `(list_name, entry)` for every entry in every list, in `ENTRY_LISTS` order."""
    for name in ENTRY_LISTS:
        for entry in plan.get(name) or []:
            yield name, entry


def find_entry(plan: dict, key: str) -> tuple[str, dict]:
    """@raises KeyError: no entry with this key."""
    for name, entry in entries(plan):
        if entry["key"] == key:
            return name, entry
    raise KeyError(f"no plan entry with key {key!r}")


def set_entry(plan: dict, key: str, **fields) -> dict:
    """Returns a copy of `plan` with `key`'s entry updated. Pure: callers decide when to
    save, so a failed provider call cannot half-write a plan.

    @raises KeyError: no entry with this key.
    @raises ValueError: an unknown `status`."""
    if "status" in fields and fields["status"] not in PLAN_STATUSES:
        raise ValueError(f"unknown plan status: {fields['status']!r}")
    find_entry(plan, key)                       # raises KeyError before anything is copied
    updated = dict(plan)
    for name in ENTRY_LISTS:
        updated[name] = [{**entry, **fields} if entry["key"] == key else entry
                         for entry in plan.get(name) or []]
    return updated
