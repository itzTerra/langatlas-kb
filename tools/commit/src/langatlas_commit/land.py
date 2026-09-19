import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from langatlas_commit.trailers import changeset_key, find_record_key_in_history, format_trailers, record_key

Validator = Callable[[Path], list[str]]
StatusChecker = Callable[[Path, str], Literal["green", "red", "unknown"]]


@dataclass(frozen=True)
class Landed:
    commit_sha: str


@dataclass(frozen=True)
class BlockedRedMain:
    since: float
    last_checked: float


@dataclass(frozen=True)
class ContentionExhausted:
    retries: int
    last_conflict_summary: str


@dataclass(frozen=True)
class Reverted:
    commit_sha: str
    reason: str


@dataclass(frozen=True)
class UnsafeHalt:
    commit_sha: str | None
    diagnostic: str


LandResult = Landed | BlockedRedMain | ContentionExhausted | Reverted | UnsafeHalt


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


def _integrate(repo_root: Path, *, started: float, validator: Validator, retries: int,
               timeout_seconds: int, remote: str, branch: str,
               status_checker: StatusChecker | None) -> LandResult:
    """D36 §2.4: fetch-rebase-validate-push, retried under contention, gated on is-main-green
    immediately before the push. Shared by `land_record` and `land_changeset`, so a migration
    lands under exactly the same rules as a single record."""
    last_conflict = ""
    for attempt in range(1, retries + 1):
        if time.monotonic() - started > timeout_seconds:
            return ContentionExhausted(retries=attempt - 1, last_conflict_summary=last_conflict)

        _git(["fetch", "-q", remote], repo_root)
        rebase = _git(["rebase", f"{remote}/{branch}"], repo_root, check=False)
        if rebase.returncode != 0:
            _git(["rebase", "--abort"], repo_root, check=False)
            return UnsafeHalt(commit_sha=None,
                              diagnostic=f"rebase conflict: {rebase.stdout}\n{rebase.stderr}")

        errors = validator(repo_root)
        if errors:
            last_conflict = "; ".join(errors)
            return ContentionExhausted(retries=attempt, last_conflict_summary=last_conflict)

        if status_checker is not None:
            head_sha = _git(["rev-parse", f"{remote}/{branch}"], repo_root).stdout.strip()
            status = status_checker(repo_root, head_sha)
            if status != "green":
                now = time.monotonic()
                return BlockedRedMain(since=started, last_checked=now)

        push = _git(["push", remote, f"HEAD:{branch}"], repo_root, check=False)
        if push.returncode == 0:
            sha = _git(["rev-parse", "HEAD"], repo_root).stdout.strip()
            return Landed(commit_sha=sha)
        last_conflict = push.stderr.strip()

    return ContentionExhausted(retries=retries, last_conflict_summary=last_conflict)


def land_record(
    repo_root: Path, record_path: str, content: str, *, chat_run_id: str,
    validator: Validator, retries: int = 5, timeout_seconds: int = 180,
    remote: str = "origin", branch: str = "main",
    status_checker: StatusChecker | None = None, challenge_id: str | None = None,
) -> LandResult:
    """D36 §2.1/§2.3/§2.4/§2.6: one commit per record file, fetch-rebase-retry against
    `origin/<branch>`, gated on is-main-green immediately before push. Idempotent:
    safe to call again for the same (path, content) without double-committing."""
    key = record_key(record_path, content)
    existing = find_record_key_in_history(repo_root, key)
    if existing is not None:
        return Landed(commit_sha=existing)

    started = time.monotonic()
    path = repo_root / record_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    _git(["add", "--", record_path], repo_root)
    message = f"land {record_path}\n\n" + format_trailers(key, chat_run_id, challenge_id=challenge_id)
    _git(["commit", "-q", "-m", message], repo_root)
    return _integrate(repo_root, started=started, validator=validator, retries=retries,
                      timeout_seconds=timeout_seconds, remote=remote, branch=branch,
                      status_checker=status_checker)


def land_changeset(
    repo_root: Path, changes: dict[str, str | None], *, message: str, chat_run_id: str,
    validator: Validator, retries: int = 5, timeout_seconds: int = 180,
    remote: str = "origin", branch: str = "main",
    status_checker: StatusChecker | None = None,
) -> LandResult:
    """One commit for a set of files that must change together: a migration's manifest plus
    the corpus diff it produces (§5.2). The only multi-file commit in the project, because the
    intermediate states of a split or a merge are not valid stores.

    @param changes: repo-relative path -> new text, or None to delete that path.
    @raises ValueError: an empty changeset, or a deletion of a path that does not exist."""
    if not changes:
        raise ValueError("an empty changeset has nothing to land")
    for rel, content in changes.items():
        if content is None and not (repo_root / rel).exists():
            raise ValueError(f"{rel}: cannot delete a file that does not exist")
    key = changeset_key(changes)
    existing = find_record_key_in_history(repo_root, key)
    if existing is not None:
        return Landed(commit_sha=existing)

    started = time.monotonic()
    for rel, content in sorted(changes.items()):
        path = repo_root / rel
        if content is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    _git(["add", "-A", "--", *sorted(changes)], repo_root)
    _git(["commit", "-q", "-m", f"{message}\n\n" + format_trailers(key, chat_run_id)], repo_root)
    return _integrate(repo_root, started=started, validator=validator, retries=retries,
                      timeout_seconds=timeout_seconds, remote=remote, branch=branch,
                      status_checker=status_checker)
