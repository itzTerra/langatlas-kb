"""The R5 reality check: `research/reality-checks/<cycle>-<theme>.yaml`.

One file per cycle, doing three jobs: R5's working state (every step reads it and writes it
back, as 3C's carve plan is for R4), D52's named authored artifact (the structured findings 3F's
`dossier` reads), and the shakedown issue log Stage 4's pipeline-readiness item counts.

It is research bookkeeping, not canonical store: R5 mints nothing (D68), so a cell's proposal is
what a sweep *would* commit, and its verdicts are the D24 gate's on exactly that record. Stage 5
sweep agents never read this directory — their answers must stay independent (D5/D34).

A cell and an uncovered construct are keyed `<language>--<subject>`. Slugs cannot contain `--`
(§3.5), so a key splits unambiguously and never collides.

Everything here is pure: callers decide when to save, so a failed provider call cannot
half-write the file."""
import hashlib
import io
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_questionnaire.spec import iter_items, select
from langatlas_research.cycle import Cycle
from langatlas_research.errors import RealityCheckMissing, RealityOutputInvalid
from langatlas_research.paths import reality_checks_dir
from langatlas_research.schema import validate_research_record

CELL_STATUSES = ("proposed", "admitted", "refused", "unmappable", "unsourced")
SHAKEDOWN_COMPONENTS = ("compiler", "questionnaire", "classifier", "verifier", "commit",
                        "sources")
FINDING_KEYS = ("unmappable", "uninhabited_values", "unfittable", "exclusivity_violations")
SUMMARY_KEYS = ("languages", "cells", "mappable", "unmappable", "admitted", "refused",
                "unsourced", "uncovered")

_yaml = YAML(typ="safe")


def reality_rel(cycle_slug: str) -> str:
    return f"research/reality-checks/{cycle_slug}.yaml"


def reality_path(cycle_slug: str, repo_root: Path | None = None) -> Path:
    return reality_checks_dir(repo_root) / f"{cycle_slug}.yaml"


def cell_key(language: str, subject: str) -> str:
    return f"{language}--{subject}"


def build_record(*, cycle: Cycle, spec_rel: str, spec: dict, scope_features,
                 generated_at: str) -> dict:
    """A reality check with no answers yet, scoped to the theme's features.

    The scope's dimensions are read off the compiled spec: the spec is what the classifier is
    shown, so it is also what the findings are computed against. The theme digest is the
    sign-off's, like the carve plan's — this file describes the scope the developer signed."""
    scoped = select(spec, scope_features)
    dimensions = sorted({group["dimension"] for group, _item in iter_items(scoped)
                         if group["kind"] == "dimension"})
    return {"cycle": cycle.number, "theme": cycle.theme,
            "theme_digest": cycle.signed_off["theme_digest"],
            "ontology_version": spec["ontology_version"], "questionnaire": spec_rel,
            "generated_at": generated_at,
            "runs": {"classify": {}, "verify": None},
            "scope": {"features": sorted(scope_features), "dimensions": dimensions},
            "cells": [], "uncovered": [],
            "findings": {key: [] for key in FINDING_KEYS},
            "summary": {key: 0 for key in SUMMARY_KEYS}, "shakedown": []}


def render_record(record: dict) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    buf = io.StringIO()
    yaml.dump(record, buf)
    return buf.getvalue()


def save_record(record: dict, *, repo_root: Path | None = None) -> Path:
    """@raises RealityOutputInvalid: the record does not satisfy reality-check.schema.json."""
    errors = validate_research_record(record, "reality-check", repo_root=repo_root)
    if errors:
        raise RealityOutputInvalid("reality check is invalid: " + "; ".join(errors))
    path = reality_path(f"{record['cycle']:02d}-{record['theme']}", repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_record(record))
    return path


def load_record(cycle_slug: str, *, repo_root: Path | None = None) -> dict:
    """@raises RealityCheckMissing: `reality compile` has not opened this cycle yet."""
    path = reality_path(cycle_slug, repo_root)
    if not path.exists():
        raise RealityCheckMissing(f"no reality check at {path} — run `langatlas-research"
                                  f" reality compile` first")
    return _yaml.load(path.read_text())


def find_cell(record: dict, key: str) -> dict:
    """@raises KeyError: no cell with this key."""
    for cell in record["cells"]:
        if cell["key"] == key:
            return cell
    raise KeyError(f"no cell {key!r}")


def set_cell(record: dict, key: str, **fields) -> dict:
    """@raises KeyError: no such cell. @raises ValueError: an unknown `status`."""
    if "status" in fields and fields["status"] not in CELL_STATUSES:
        raise ValueError(f"unknown cell status {fields['status']!r} (not one of"
                         f" {list(CELL_STATUSES)}; R5 mints nothing, D68)")
    find_cell(record, key)
    return {**record, "cells": [{**cell, **fields} if cell["key"] == key else cell
                                for cell in record["cells"]]}


def replace_language(record: dict, language: str, *, cells, uncovered, run: dict) -> dict:
    """Swap one language's answers wholesale. A re-run replaces and never merges: two sessions'
    partial answers stitched together are an answer nobody gave."""
    def keep(entries):
        return [entry for entry in entries if entry["language"] != language]

    def by_key(entry):
        return entry["key"]

    return {**record,
            "runs": {**record["runs"],
                     "classify": {**record["runs"]["classify"], language: dict(run)}},
            "cells": sorted(keep(record["cells"]) + list(cells), key=by_key),
            "uncovered": sorted(keep(record["uncovered"]) + list(uncovered), key=by_key)}


def shakedown_key(component: str, detail: str) -> str:
    return f"s-{component}-{hashlib.sha256(detail.encode('utf-8')).hexdigest()[:8]}"


def add_shakedown(record: dict, *, component: str, detail: str) -> dict:
    """Log one friction. Keyed by content, so a detector that fires on every re-run files it
    once — and an entry the developer already closed stays closed.

    @raises ValueError: an unknown component."""
    if component not in SHAKEDOWN_COMPONENTS:
        raise ValueError(f"unknown shakedown component {component!r}"
                         f" (not one of {list(SHAKEDOWN_COMPONENTS)})")
    key = shakedown_key(component, detail)
    if any(entry["key"] == key for entry in record["shakedown"]):
        return record
    entry = {"key": key, "component": component, "status": "open", "detail": detail}
    return {**record, "shakedown": sorted(record["shakedown"] + [entry],
                                          key=lambda e: e["key"])}


def close_shakedown(record: dict, key: str, *, resolution: str) -> dict:
    """@raises KeyError: no such entry. @raises ValueError: an empty resolution."""
    if not resolution.strip():
        raise ValueError("closing a shakedown entry needs a resolution saying what was done")
    if not any(entry["key"] == key for entry in record["shakedown"]):
        raise KeyError(f"no shakedown entry {key!r}")
    return {**record, "shakedown": [
        {**entry, "status": "closed", "resolution": resolution.strip()}
        if entry["key"] == key else entry for entry in record["shakedown"]]}


def open_shakedown(record: dict) -> list[dict]:
    return [entry for entry in record["shakedown"] if entry["status"] == "open"]
