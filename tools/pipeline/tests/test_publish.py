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


def test_a_failing_commit_is_reported_as_commit_failed(tmp_path: Path):
    """Fix E: a rejected commit used to be reported as `push_failed`, which sent an
    operator looking at the network for a purely local problem."""
    repo = _repo(tmp_path)
    run_dir = _run_dir(repo)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'refusing this commit' >&2\nexit 1\n")
    hook.chmod(0o755)

    result = publish_run(run_dir, repo_root=repo, push=False)
    assert result.status == "commit_failed"
    assert result.detail
    log = subprocess.run(["git", "log", "--oneline"], cwd=repo, capture_output=True,
                         text=True).stdout
    assert log.strip() == "", "nothing was committed"


# ---- fix wave 2: close() can publish without pushing ---------------------------------

def _fake_publish(calls):
    from langatlas_pipeline.transcripts.publish import PublishResult

    def fake_publish(run_dir, **kwargs):
        calls.append((run_dir, kwargs))
        return PublishResult("published")

    return fake_publish


def _config_with_transcripts(**transcripts):
    import dataclasses
    from langatlas_pipeline.config import ProviderConfig

    config = ProviderConfig.load()
    providers = {**config.providers, "transcripts": transcripts}
    return dataclasses.replace(config, providers=providers)


def test_close_can_publish_without_pushing(workspace, monkeypatch):
    """Fix A: publishing (a local commit) and pushing are separate decisions; before this
    the only way to commit a run without touching the remote was to monkeypatch."""
    from langatlas_pipeline.providers.core import RunContext

    calls = []
    monkeypatch.setattr("langatlas_pipeline.transcripts.publish.publish_run",
                        _fake_publish(calls))
    run = RunContext.start(kind="sweep", slug="nopush",
                           transcripts_root=workspace["transcripts"],
                           private_dir=workspace["private"])
    run.close(publish=True, push=False)
    assert len(calls) == 1
    assert calls[0][1]["push"] is False


def test_close_honors_the_configured_push_setting(workspace, monkeypatch):
    from langatlas_pipeline.providers.core import RunContext

    calls = []
    monkeypatch.setattr("langatlas_pipeline.transcripts.publish.publish_run",
                        _fake_publish(calls))
    run = RunContext.start(kind="sweep", slug="cfgnopush",
                           config=_config_with_transcripts(publish=True, push=False),
                           transcripts_root=workspace["transcripts"],
                           private_dir=workspace["private"])
    run.close()                       # no explicit publish/push: config decides both
    assert len(calls) == 1
    assert calls[0][1]["push"] is False


def test_close_still_pushes_by_default(workspace, monkeypatch):
    """The new knob must not change behaviour for anyone who does not set it."""
    from langatlas_pipeline.providers.core import RunContext

    calls = []
    monkeypatch.setattr("langatlas_pipeline.transcripts.publish.publish_run",
                        _fake_publish(calls))
    run = RunContext.start(kind="sweep", slug="defaultpush",
                           config=_config_with_transcripts(),   # neither key present
                           transcripts_root=workspace["transcripts"],
                           private_dir=workspace["private"])
    run.close(publish=True)
    assert len(calls) == 1
    assert calls[0][1]["push"] is True
