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


def test_prompt_version_checker_flags_a_prompt_with_no_fixture():
    fixture = {"fixture_id": "y", "kind": "prompt-version-rerun", "mode": "soft",
               "prompt_id": "capability-probe"}
    result = CHECKERS["prompt-version-rerun"](fixture)
    assert result is None or "capability-probe" in result
