import subprocess
from pathlib import Path
from langatlas_pipeline.transcripts.publish import publish_run


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "transcripts"
    (repo / "2026" / "08" / "2026-08-02-sweep-rust-01").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "bot@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "bot"], cwd=repo, check=True)
    return repo


def _run_dir(repo: Path) -> Path:
    run_dir = repo / "2026" / "08" / "2026-08-02-sweep-rust-01"
    (run_dir / "transcript.jsonl").write_text('{"seq": 1}\n')
    (run_dir / "manifest.yaml").write_text("run_id: 2026-08-02-sweep-rust-01\n")
    return run_dir


def test_publish_commits_one_commit_per_run(tmp_path: Path):
    repo = _repo(tmp_path)
    run_dir = _run_dir(repo)
    result = publish_run(run_dir, repo_root=repo, push=False)
    assert result.status == "published"
    log = subprocess.run(["git", "log", "--oneline"], cwd=repo, capture_output=True,
                         text=True).stdout
    assert log.count("\n") == 1
    assert "2026-08-02-sweep-rust-01" in log


def test_republishing_an_unchanged_run_is_a_noop(tmp_path: Path):
    repo = _repo(tmp_path)
    run_dir = _run_dir(repo)
    publish_run(run_dir, repo_root=repo, push=False)
    assert publish_run(run_dir, repo_root=repo, push=False).status == "noop"


def test_a_failing_push_still_leaves_the_commit_and_never_raises(tmp_path: Path):
    repo = _repo(tmp_path)
    run_dir = _run_dir(repo)
    result = publish_run(run_dir, repo_root=repo, push=True)   # no remote configured
    assert result.status == "push_failed"
    assert result.detail
    log = subprocess.run(["git", "log", "--oneline"], cwd=repo, capture_output=True,
                         text=True).stdout
    assert "2026-08-02-sweep-rust-01" in log


def test_a_missing_repo_is_reported_not_raised(tmp_path: Path):
    result = publish_run(tmp_path / "nowhere" / "run", repo_root=tmp_path / "nowhere",
                         push=False)
    assert result.status == "no_repo"


def test_ctx_close_publishes_only_when_asked(workspace, monkeypatch):
    from langatlas_pipeline.providers.core import RunContext
    from langatlas_pipeline.transcripts.publish import PublishResult

    calls = []

    def fake_publish(run_dir, **kwargs):
        calls.append(run_dir)
        return PublishResult("published")

    monkeypatch.setattr("langatlas_pipeline.transcripts.publish.publish_run", fake_publish)
    run = RunContext.start(kind="sweep", slug="p", transcripts_root=workspace["transcripts"],
                           private_dir=workspace["private"])
    run.close(publish=False)
    assert calls == []

    run2 = RunContext.start(kind="sweep", slug="q", transcripts_root=workspace["transcripts"],
                            private_dir=workspace["private"])
    run2.close(publish=True)
    assert calls == [run2.run_dir]
