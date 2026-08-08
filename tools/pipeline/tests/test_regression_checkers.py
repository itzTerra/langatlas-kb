from pathlib import Path
from langatlas_pipeline.regression_checkers import CHECKERS

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_registry_owns_exactly_the_two_1b_checkers():
    assert set(CHECKERS) == {"provider-record-replay", "prompt-version-rerun"}


def test_record_replay_checker_passes_on_the_shipped_fixture():
    from ruamel.yaml import YAML

    fixture = YAML(typ="safe").load(
        (REPO_ROOT / "tests/fixtures/providers/provider-record-replay/"
                     "verifier-supported.yaml").read_text())
    assert CHECKERS["provider-record-replay"](fixture) is None


def test_record_replay_checker_reports_a_changed_response():
    fixture = {"fixture_id": "x", "kind": "provider-record-replay", "mode": "hard",
               "request": {"model": "glm", "messages": [{"role": "user", "content": "ping"}],
                           "temperature": 0.0},
               "expect": {"text": "definitely-not-what-was-recorded"}}
    assert "definitely-not" in (CHECKERS["provider-record-replay"](fixture) or "")


def test_prompt_version_checker_finds_the_shipped_coverage_record():
    """Finding 6: the checker looked under tests/fixtures/providers/prompt-rerun/, a
    directory that does not exist, so the soft warning was permanently unclearable."""
    fixture = {"fixture_id": "y", "kind": "prompt-version-rerun", "mode": "soft",
               "prompt_id": "capability-probe"}
    assert CHECKERS["prompt-version-rerun"](fixture) is None


def test_prompt_version_checker_warns_when_coverage_is_missing(monkeypatch):
    import langatlas_pipeline.regression_checkers as checkers

    monkeypatch.setattr(checkers, "RERUN_DIR", REPO_ROOT / "tests/fixtures/does-not-exist")
    fixture = {"fixture_id": "y", "kind": "prompt-version-rerun", "mode": "soft",
               "prompt_id": "capability-probe"}
    result = CHECKERS["prompt-version-rerun"](fixture)
    assert result is not None
    assert "capability-probe" in result
    assert "prompt-version-rerun" in result, "the warning names the real fixture directory"


def test_prompt_version_checker_names_the_file_a_developer_should_add(monkeypatch):
    import langatlas_pipeline.regression_checkers as checkers
    from langatlas_pipeline.prompts import list_versions

    monkeypatch.setattr(checkers, "RERUN_DIR", REPO_ROOT / "tests/fixtures/does-not-exist")
    latest = list_versions("capability-probe")[-1]
    result = CHECKERS["prompt-version-rerun"](
        {"fixture_id": "y", "kind": "prompt-version-rerun", "mode": "soft",
         "prompt_id": "capability-probe"})
    assert f"capability-probe-{latest}.yaml" in result


def test_a_coverage_record_passes_and_a_stale_one_warns():
    from ruamel.yaml import YAML
    from langatlas_pipeline.prompts import list_versions

    latest = list_versions("capability-probe")[-1]
    shipped = YAML(typ="safe").load(
        (REPO_ROOT / "tests/fixtures/providers/prompt-version-rerun/"
                     f"capability-probe-{latest}.yaml").read_text())
    assert CHECKERS["prompt-version-rerun"](shipped) is None

    stale = {**shipped, "version": "v-deadbeef"}
    assert "not a registered version" in (CHECKERS["prompt-version-rerun"](stale) or "")
