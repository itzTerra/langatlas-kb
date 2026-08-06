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
    assert report.ran == (report.passed + len(report.failures) + len(report.warnings)
                          + len(report.skipped))


def _write(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body)
    return path


def test_soft_failures_warn_but_do_not_fail(tmp_path, monkeypatch):
    from langatlas_validate import regression

    monkeypatch.setitem(regression.CHECKERS, "questionnaire-shape",
                        lambda fixture: "soft problem")
    _write(tmp_path, "soft.yaml",
           "fixture_id: s\nkind: questionnaire-shape\nmode: soft\n")
    report = run_regression(tmp_path)
    assert report.failures == []
    assert report.warnings == ["soft problem"]


def test_hard_failures_still_fail(tmp_path, monkeypatch):
    from langatlas_validate import regression

    monkeypatch.setitem(regression.CHECKERS, "questionnaire-shape",
                        lambda fixture: "hard problem")
    _write(tmp_path, "hard.yaml",
           "fixture_id: h\nkind: questionnaire-shape\nmode: hard\n")
    report = run_regression(tmp_path)
    assert report.failures == ["hard problem"]
    assert report.warnings == []


def test_a_fixture_whose_checker_is_unavailable_is_skipped_not_failed(tmp_path):
    _write(tmp_path, "future.yaml",
           "fixture_id: f\nkind: not-yet-implemented\nmode: hard\n")
    report = run_regression(tmp_path)
    assert report.failures == []
    assert len(report.skipped) == 1


def test_pipeline_checkers_are_discovered_when_installed(tmp_path):
    import importlib.util

    if importlib.util.find_spec("langatlas_pipeline") is None:
        return
    from langatlas_validate.regression import available_checkers

    assert "provider-record-replay" in available_checkers()
