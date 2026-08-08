import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PublishResult:
    # published | noop | commit_failed | push_failed | no_repo. `commit_failed` and
    # `push_failed` are deliberately distinct: a rejected commit is a local problem
    # (hooks, identity, index), a rejected push is a remote one, and an orchestrator
    # retrying a publish needs to tell them apart.
    status: str
    detail: str | None = None


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def publish_run(run_dir: Path, *, repo_root: Path, push: bool = True,
                remote: str = "origin", branch: str = "main") -> PublishResult:
    """One commit per run (D18) — the transcripts repo's git history doubles as the run
    log. Never raises: a publishing problem is an operational nuisance, while losing a
    pipeline run to a network error would be a real loss. Failures are returned so the
    orchestrator can retry the publish alone."""
    if not (repo_root / ".git").exists():
        return PublishResult("no_repo", f"{repo_root} is not a git repository")

    relative = run_dir.relative_to(repo_root)
    _git(["add", "--", str(relative)], repo_root)
    staged = _git(["diff", "--cached", "--quiet"], repo_root)
    if staged.returncode == 0:
        return PublishResult("noop", "nothing to commit")

    commit = _git(["commit", "-q", "-m", run_dir.name], repo_root)
    if commit.returncode != 0:
        return PublishResult("commit_failed",
                             commit.stderr.strip() or commit.stdout.strip())

    if not push:
        return PublishResult("published")

    pushed = _git(["push", remote, branch], repo_root)
    if pushed.returncode != 0:
        return PublishResult("push_failed", pushed.stderr.strip())
    return PublishResult("published")
