import subprocess
import time
from pathlib import Path

import pytest

from langatlas_orchestrator.checkpoint import CheckpointStore
from langatlas_orchestrator.driver import EXIT_HALTED, EXIT_OK, EXIT_PAUSED, run
from langatlas_orchestrator.registry import ItemOutcome, register_job_kind
from langatlas_orchestrator.status import read_status
from langatlas_pipeline.errors import BudgetExceeded, ClaudeLimitSignal


def _write_spec(tmp_path, kind, extra_yaml="") -> Path:
    path = tmp_path / "job.yaml"
    path.write_text(f"kind: {kind}\ncheckpoint_path: {tmp_path / 'ck.sqlite'}\n{extra_yaml}")
    return path


def test_run_happy_path_marks_every_item_done(tmp_path):
    calls = []

    def _enumerate(extra, repo_root):
        return ["item-1", "item-2"]

    def _run_item(ctx, item_key, extra, repo_root):
        calls.append(item_key)
        return ItemOutcome(status="done", detail=f"processed {item_key}")

    register_job_kind("test-happy-path", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-happy-path")

    rc = run(spec_path, repo_root=tmp_path, status_path=tmp_path / "status.json")

    assert rc == EXIT_OK
    assert calls == ["item-1", "item-2"]
    store = CheckpointStore(tmp_path / "ck.sqlite")
    assert store.get(spec_kind="test-happy-path", item_key="item-1").status == "done"
    assert store.get(spec_kind="test-happy-path", item_key="item-2").status == "done"
    assert read_status(tmp_path / "status.json")["test-happy-path"]["state"] == "done"


def test_run_skips_items_already_marked_done(tmp_path):
    calls = []

    def _enumerate(extra, repo_root):
        return ["item-1", "item-2"]

    def _run_item(ctx, item_key, extra, repo_root):
        calls.append(item_key)
        return ItemOutcome(status="done")

    register_job_kind("test-skip-done", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-skip-done")
    CheckpointStore(tmp_path / "ck.sqlite").upsert(
        run_id="earlier-run", spec_kind="test-skip-done", item_key="item-1", status="done")

    rc = run(spec_path, repo_root=tmp_path, status_path=tmp_path / "status.json")

    assert rc == EXIT_OK
    assert calls == ["item-2"]        # item-1 was never re-run


def test_run_pauses_on_budget_exceeded_and_checkpoints_blocked(tmp_path):
    def _enumerate(extra, repo_root):
        return ["item-1", "item-2"]

    def _run_item(ctx, item_key, extra, repo_root):
        raise BudgetExceeded("max_calls", 1, 0)

    register_job_kind("test-budget-pause", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-budget-pause", "budget:\n  max_calls: 0\n")

    rc = run(spec_path, repo_root=tmp_path, status_path=tmp_path / "status.json")

    assert rc == EXIT_PAUSED
    row = CheckpointStore(tmp_path / "ck.sqlite").get(spec_kind="test-budget-pause",
                                                      item_key="item-1")
    assert row.status == "blocked"
    status = read_status(tmp_path / "status.json")["test-budget-pause"]
    assert status["state"] == "paused"
    assert status["reason"] == "budget"


def test_run_pauses_on_claude_limit_and_sets_a_four_hour_cooldown(tmp_path):
    def _enumerate(extra, repo_root):
        return ["item-1"]

    def _run_item(ctx, item_key, extra, repo_root):
        raise ClaudeLimitSignal(detected_at="2026-08-22T00:00:00Z", signal_type="usage_limit",
                                raw_message="limit hit", run_id=ctx.run_id)

    register_job_kind("test-claude-limit-pause", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-claude-limit-pause")

    before = time.time()
    rc = run(spec_path, repo_root=tmp_path, status_path=tmp_path / "status.json")

    assert rc == EXIT_PAUSED
    status = read_status(tmp_path / "status.json")["test-claude-limit-pause"]
    assert status["reason"] == "claude_limit"
    assert status["paused_until"] - before == pytest.approx(4 * 60 * 60, abs=5)


def test_run_no_ops_before_claude_limit_cooldown_elapses(tmp_path):
    call_count = {"n": 0}

    def _enumerate(extra, repo_root):
        return ["item-1"]

    def _run_item(ctx, item_key, extra, repo_root):
        call_count["n"] += 1
        return ItemOutcome(status="done")

    register_job_kind("test-claude-limit-cooldown", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-claude-limit-cooldown")
    status_path = tmp_path / "status.json"
    from langatlas_orchestrator.status import write_status
    write_status("test-claude-limit-cooldown", state="paused", reason="claude_limit",
                paused_at=time.time(), paused_until=time.time() + 3600, path=status_path)

    rc = run(spec_path, repo_root=tmp_path, status_path=status_path)

    assert rc == EXIT_PAUSED
    assert call_count["n"] == 0        # the item runner was never invoked


def test_run_halts_and_stops_processing_further_items(tmp_path):
    calls = []

    def _enumerate(extra, repo_root):
        return ["item-1", "item-2"]

    def _run_item(ctx, item_key, extra, repo_root):
        calls.append(item_key)
        return ItemOutcome(status="halted", detail="unsafe_halt: needs a human")

    register_job_kind("test-halt", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-halt")

    rc = run(spec_path, repo_root=tmp_path, status_path=tmp_path / "status.json")

    assert rc == EXIT_HALTED
    assert calls == ["item-1"]         # item-2 never attempted
    status = read_status(tmp_path / "status.json")["test-halt"]
    assert status["state"] == "halted"


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def test_run_resolves_an_ambiguous_row_via_the_git_trailer(tmp_path):
    """Simulates a crash right after a commit landed but before the checkpoint row was
    marked `done` (D43 §2.2's crash-safety property): the row is stuck `in_progress`
    with a `record_key`, but the record actually landed. The driver must not re-run the
    item — it must resolve it via `find_record_key_in_history` and mark it `done`."""
    from langatlas_commit.trailers import format_trailers, record_key

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "bot@example.com"], repo)
    _git(["config", "user.name", "bot"], repo)
    key = record_key("features/thing.yaml", "feature: thing\n")
    (repo / "features").mkdir()
    (repo / "features" / "thing.yaml").write_text("feature: thing\n")
    _git(["add", "features/thing.yaml"], repo)
    _git(["commit", "-q", "-m", "land it\n\n" + format_trailers(key, "run-0#msg-1")], repo)

    CheckpointStore(tmp_path / "ck.sqlite").upsert(
        run_id="crashed-run", spec_kind="test-resume-ambiguous", item_key="item-1",
        status="in_progress", record_key=key)

    calls = []

    def _enumerate(extra, repo_root):
        return ["item-1"]

    def _run_item(ctx, item_key, extra, repo_root):
        calls.append(item_key)             # would double-commit if the driver got here
        return ItemOutcome(status="done")

    register_job_kind("test-resume-ambiguous", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-resume-ambiguous")

    rc = run(spec_path, repo_root=repo, status_path=tmp_path / "status.json")

    assert rc == EXIT_OK
    assert calls == []                     # never re-attempted
    row = CheckpointStore(tmp_path / "ck.sqlite").get(spec_kind="test-resume-ambiguous",
                                                      item_key="item-1")
    assert row.status == "done"
