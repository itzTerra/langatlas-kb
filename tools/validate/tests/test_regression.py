from pathlib import Path
from langatlas_validate.regression import run_regression, CHECKERS

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "providers"


def test_schema_shape_checker_registered():
    assert "schema-shape" in CHECKERS


def test_all_fixtures_pass_their_expectation():
    report = run_regression(FIXTURES)
    assert report.failures == [], report.failures
    assert report.ran >= 2


def test_report_counts():
    report = run_regression(FIXTURES)
    assert report.ran == report.passed + len(report.failures)
