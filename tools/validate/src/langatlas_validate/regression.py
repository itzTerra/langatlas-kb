import json
from dataclasses import dataclass, field
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_validate.schema import validate_record
from langatlas_validate.paths import SCHEMA_DIR as _SCHEMA_DIR

_yaml = YAML(typ="safe")


@dataclass
class RegressionReport:
    ran: int = 0
    passed: int = 0
    failures: list[str] = field(default_factory=list)   # mode: hard -> non-zero exit
    warnings: list[str] = field(default_factory=list)   # mode: soft -> log only (D41)
    skipped: list[str] = field(default_factory=list)    # checker not installed here


def _schema_shape_checker(fixture: dict) -> str | None:
    """Return None on success, else an error message."""
    errors = validate_record(fixture["record"], fixture["record_kind"])
    valid = errors == []
    expected_pass = fixture["expect"] == "pass"
    if valid != expected_pass:
        return (f"{fixture['fixture_id']}: expected {fixture['expect']}, "
                f"got {'pass' if valid else 'fail'} (errors={errors})")
    return None


def _carries_sources(name: str, subschema: dict) -> bool:
    """A property is fact-bearing iff it holds citations: `sources` itself, or anything whose
    schema reaches a `sourcesList` (directly, or through its list items)."""
    return name == "sources" or "sourcesList" in json.dumps(subschema)


def _questionnaire_shape_checker(fixture: dict) -> str | None:
    """D46/D48: does the questionnaire compiler's fact-bearing field map still cover the record
    schema it compiles questions for? Two drifts, both silent otherwise: the schema grows a
    sourced property no questionnaire field asks for (sweeps would never produce it), or a field
    names a property the schema no longer has (sweeps would answer into nothing)."""
    schema = json.loads((_SCHEMA_DIR / f"{fixture['record_kind']}.schema.json").read_text())
    properties = schema.get("properties", {})
    named = {member for members in fixture["fields"].values() for member in members}
    problems = []
    unknown = sorted(named - set(properties))
    if unknown:
        problems.append(f"fields name properties the schema no longer has: {unknown}")
    unasked = sorted(name for name, sub in properties.items()
                     if _carries_sources(name, sub) and name not in named)
    if unasked:
        problems.append(f"sourced properties no questionnaire field asks for: {unasked}")
    return f"{fixture['fixture_id']}: " + "; ".join(problems) if problems else None


CHECKERS = {
    "schema-shape": _schema_shape_checker,
    "questionnaire-shape": _questionnaire_shape_checker,
}


def available_checkers() -> dict:
    """Checkers registered here plus any contributed by langatlas_pipeline (1B), which
    is soft-imported so this package stays installable — and fast — on its own as the
    pre-commit gate."""
    checkers = dict(CHECKERS)
    try:
        from langatlas_pipeline.regression_checkers import CHECKERS as pipeline_checkers
    except ImportError:
        return checkers
    return {**checkers, **pipeline_checkers}


def run_regression(fixtures_dir: Path) -> RegressionReport:
    report = RegressionReport()
    checkers = available_checkers()
    for path in sorted(fixtures_dir.rglob("*.yaml")):
        fixture = _yaml.load(path.read_text())
        kind = fixture.get("kind")
        soft = fixture.get("mode") == "soft"
        report.ran += 1
        checker = checkers.get(kind)
        if checker is None:
            report.skipped.append(f"{path}: no checker available for kind {kind!r}")
            continue
        err = checker(fixture)
        if err is None:
            report.passed += 1
        elif soft:
            report.warnings.append(err)
        else:
            report.failures.append(err)
    return report
