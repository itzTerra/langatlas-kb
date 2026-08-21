import subprocess
from pathlib import Path

import pytest

from langatlas_commit.revert import (
    evaluate_revert_safety, auto_revert, RevertBudget, RevertCircuitBroken,
)
from langatlas_commit.land import Landed


def _git(args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


def test_evaluate_revert_safety_all_conditions_hold():
    ok, reason = evaluate_revert_safety(
        is_tip=True, author_is_bot=True, deterministic_failure=True, revert_applies_cleanly=True,
    )
    assert ok is True


@pytest.mark.parametrize("field", ["is_tip", "author_is_bot", "deterministic_failure",
                                   "revert_applies_cleanly"])
def test_evaluate_revert_safety_fails_if_any_condition_false(field):
    conditions = dict(is_tip=True, author_is_bot=True, deterministic_failure=True,
                      revert_applies_cleanly=True)
    conditions[field] = False
    ok, reason = evaluate_revert_safety(**conditions)
    assert ok is False
    assert field in reason


def test_revert_budget_allows_two_then_breaks():
    budget = RevertBudget()
    budget.record_revert()
    budget.record_revert()
    with pytest.raises(RevertCircuitBroken):
        budget.record_revert()


@pytest.fixture
def bare_and_clone(tmp_path):
    bare = tmp_path / "bare.git"
    _git(["init", "-q", "--bare", "-b", "main", str(bare)], tmp_path)
    clone = tmp_path / "clone"
    _git(["clone", "-q", str(bare), str(clone)], tmp_path)
    _git(["config", "user.email", "bot@example.com"], clone)
    _git(["config", "user.name", "bot"], clone)
    (clone / "README.md").write_text("seed\n")
    _git(["add", "README.md"], clone)
    _git(["commit", "-q", "-m", "seed"], clone)
    (clone / "bad.yaml").write_text("broken: true\n")
    _git(["add", "bad.yaml"], clone)
    _git(["commit", "-q", "-m", "bad commit"], clone)
    _git(["push", "-q", "origin", "main"], clone)
    return bare, clone


def test_auto_revert_pushes_a_clean_revert(bare_and_clone):
    bare, clone = bare_and_clone
    tip = _git(["rev-parse", "HEAD"], clone).stdout.strip()
    result = auto_revert(clone, tip)
    assert isinstance(result, Landed)
    log = _git(["log", "-1", "--format=%s", "origin/main"], clone)
    assert "Revert" in log.stdout
