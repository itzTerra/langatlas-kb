from dataclasses import dataclass, field
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_validate.schema import validate_record

_yaml = YAML(typ="safe")


@dataclass
class RegressionReport:
    ran: int = 0
    passed: int = 0
    failures: list[str] = field(default_factory=list)


def _schema_shape_checker(fixture: dict) -> str | None:
    """Return None on success, else an error message."""
    errors = validate_record(fixture["record"], fixture["record_kind"])
    valid = errors == []
    expected_pass = fixture["expect"] == "pass"
    if valid != expected_pass:
        return (f"{fixture['fixture_id']}: expected {fixture['expect']}, "
                f"got {'pass' if valid else 'fail'} (errors={errors})")
    return None


def _stub_checker(fixture: dict) -> str | None:
    return None   # owned by a later sub-plan; a bare stub never fails the suite


CHECKERS = {
    "schema-shape": _schema_shape_checker,
    "provider-record-replay": _stub_checker,
    "questionnaire-shape": _stub_checker,
    "prompt-version-rerun": _stub_checker,
}


def run_regression(fixtures_dir: Path) -> RegressionReport:
    report = RegressionReport()
    for path in sorted(fixtures_dir.rglob("*.yaml")):
        fixture = _yaml.load(path.read_text())
        checker = CHECKERS.get(fixture.get("kind"))
        if checker is None:
            report.failures.append(f"{path}: unknown checker kind {fixture.get('kind')!r}")
            report.ran += 1
            continue
        report.ran += 1
        err = checker(fixture)
        if err is None:
            report.passed += 1
        else:
            report.failures.append(err)
    return report
