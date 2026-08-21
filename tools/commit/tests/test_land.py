import subprocess
import time
from pathlib import Path

import pytest

from langatlas_commit.land import land_record, Landed, ContentionExhausted
from langatlas_commit.trailers import record_key


def _git(args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


@pytest.fixture
def bare_and_clone(tmp_path):
    bare = tmp_path / "bare.git"
    _git(["init", "-q", "--bare", "-b", "main", str(bare)], tmp_path)
    clone = tmp_path / "clone"
    _git(["clone", "-q", str(bare), str(clone)], tmp_path)
    _git(["config", "user.email", "bot@example.com"], clone)
    _git(["config", "user.name", "bot"], clone)
    # seed main so `git rebase origin/main` has something to rebase onto
    (clone / "README.md").write_text("seed\n")
    _git(["add", "README.md"], clone)
    _git(["commit", "-q", "-m", "seed"], clone)
    _git(["push", "-q", "origin", "main"], clone)
    return bare, clone


def _always_pass_validator(worktree: Path) -> list[str]:
    return []   # no errors


def test_land_record_happy_path(bare_and_clone):
    bare, clone = bare_and_clone
    content = "feature: pattern-matching\n"
    result = land_record(clone, "features/pattern-matching.yaml", content,
                         chat_run_id="run-1#msg-1", validator=_always_pass_validator)
    assert isinstance(result, Landed)
    log = _git(["log", "-1", "--format=%B", "origin/main"], clone)
    assert "LangAtlas-Record-Key" in log.stdout


def test_land_record_idempotent_resume(bare_and_clone):
    bare, clone = bare_and_clone
    content = "feature: pattern-matching\n"
    first = land_record(clone, "features/pattern-matching.yaml", content,
                        chat_run_id="run-1#msg-1", validator=_always_pass_validator)
    second = land_record(clone, "features/pattern-matching.yaml", content,
                         chat_run_id="run-1#msg-1", validator=_always_pass_validator)
    assert isinstance(second, Landed)
    assert second.commit_sha == first.commit_sha   # short-circuited, no re-push


def test_land_record_retries_through_concurrent_push(bare_and_clone, tmp_path):
    bare, clone = bare_and_clone
    # A second clone lands first, moving origin/main out from under our clone's fetch.
    other = tmp_path / "other"
    _git(["clone", "-q", str(bare), str(other)], tmp_path)
    _git(["config", "user.email", "other@example.com"], other)
    _git(["config", "user.name", "other"], other)
    (other / "features").mkdir()
    (other / "features" / "unrelated.yaml").write_text("feature: unrelated\n")
    _git(["add", "features/unrelated.yaml"], other)
    _git(["commit", "-q", "-m", "unrelated"], other)
    _git(["push", "-q", "origin", "main"], other)

    result = land_record(clone, "features/pattern-matching.yaml", "feature: pattern-matching\n",
                         chat_run_id="run-1#msg-1", validator=_always_pass_validator)
    assert isinstance(result, Landed)
    log = _git(["log", "--oneline", "origin/main"], clone)
    assert "unrelated" in log.stdout   # both commits landed, no data lost


def test_land_record_reports_contention_exhausted_when_validator_never_passes(bare_and_clone):
    bare, clone = bare_and_clone

    def _always_fail(worktree: Path) -> list[str]:
        return ["schema: always broken in this test"]

    result = land_record(clone, "features/broken.yaml", "feature: broken\n",
                         chat_run_id="run-1#msg-1", validator=_always_fail,
                         retries=1, timeout_seconds=5)
    assert isinstance(result, ContentionExhausted)
