"""The handful of git reads 3F's history checks share (migration replay, the append-only
tombstone check, the settled-theme guard). Read-only: nothing here writes a ref or a file in the
repository, and every call runs with `cwd=repo_root`."""
import io
import re
import subprocess
import tarfile
from pathlib import Path

_ALL_ZERO = re.compile(r"^0+$")


def _git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True,
                          check=check)


def resolve_ref(repo_root: Path, ref: str | None) -> str | None:
    """@returns the commit sha, or None for an empty ref, GitHub's all-zero "no previous
        commit" sha, or a ref this clone does not have — callers treat None as "no base"."""
    if not ref or _ALL_ZERO.match(ref):
        return None
    result = _git(repo_root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}",
                  check=False)
    return result.stdout.strip() or None if result.returncode == 0 else None


def show(repo_root: Path, ref: str, rel: str) -> str | None:
    """@returns the file's text at `ref`, or None when `ref` does not have it."""
    result = _git(repo_root, "show", f"{ref}:{rel}", check=False)
    return result.stdout if result.returncode == 0 else None


def commits_since(repo_root: Path, since: str | None) -> list[str]:
    """@param since: a resolved base sha; None walks the whole history.
    @returns the commits after `since` up to HEAD, oldest first."""
    span = f"{since}..HEAD" if since else "HEAD"
    return _git(repo_root, "rev-list", "--reverse", span).stdout.split()


def changed_paths(repo_root: Path, commit: str) -> list[tuple[str, str]]:
    """@returns `(status, path)` for every file `commit` changed relative to its first parent,
        renames split into a delete and an add so a moved record is never mistaken for an
        edit."""
    output = _git(repo_root, "diff-tree", "--no-commit-id", "--no-renames", "--name-status",
                  "-r", "--root", commit).stdout
    return [tuple(line.split("\t", 1)) for line in output.splitlines() if line]


def list_files(repo_root: Path, ref: str, prefix: str) -> list[str]:
    output = _git(repo_root, "ls-tree", "-r", "--name-only", ref, "--", prefix,
                  check=False).stdout
    return sorted(line for line in output.splitlines() if line)


def extract_tree(repo_root: Path, ref: str, dest: Path) -> None:
    """Materializes `ref`'s tree under `dest` through `git archive` — no worktree and no
    checkout, so the caller's working copy is never touched."""
    archive = subprocess.run(["git", "archive", "--format=tar", ref], cwd=repo_root,
                             capture_output=True, check=True).stdout
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest, filter="data")
