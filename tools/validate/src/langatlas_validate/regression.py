from dataclasses import dataclass, field
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_validate.schema import validate_record

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


def _questionnaire_shape_stub(fixture: dict) -> str | None:
    return None   # owned by 1C; a bare stub never fails the suite


CHECKERS = {
    "schema-shape": _schema_shape_checker,
    "questionnaire-shape": _questionnaire_shape_stub,
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
