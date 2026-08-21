import subprocess
from pathlib import Path

from langatlas_commit.land import Landed, UnsafeHalt, LandResult

# D36 §2.5: a run-level pattern can override an individually-safe per-event verdict.
_MAX_REVERTS_PER_RUN = 2


class RevertCircuitBroken(Exception):
    """More than _MAX_REVERTS_PER_RUN auto-reverts in one run — evidence something
    systemic is wrong (most plausibly: the runner's local validator has drifted from
    CI's copy). The caller must halt, not keep reverting one-by-one."""


class RevertBudget:
    def __init__(self) -> None:
        self._count = 0

    def record_revert(self) -> None:
        self._count += 1
        if self._count > _MAX_REVERTS_PER_RUN:
            raise RevertCircuitBroken(f"{self._count} reverts this run (max {_MAX_REVERTS_PER_RUN})")


def evaluate_revert_safety(
    *, is_tip: bool, author_is_bot: bool, deterministic_failure: bool,
    revert_applies_cleanly: bool,
) -> tuple[bool, str]:
    """D36 §2.5's four-condition checklist. All four must hold, or the failure bot
    does not touch main. Content disputes, D25 controversy flags, and anything the
    D24 verifier already gated are the caller's responsibility to exclude before
    calling this — this function only judges the four mechanical conditions."""
    if not is_tip:
        return False, "is_tip: failing commit is not main's current tip"
    if not author_is_bot:
        return False, "author_is_bot: commit was not authored by the bot identity"
    if not deterministic_failure:
        return False, "deterministic_failure: failure did not reproduce on rerun (flake)"
    if not revert_applies_cleanly:
        return False, "revert_applies_cleanly: git revert would conflict"
    return True, "all four conditions hold"


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


def auto_revert(repo_root: Path, sha: str, *, remote: str = "origin",
                branch: str = "main") -> LandResult:
    """Push a `git revert` of `sha`. Caller must have already confirmed
    `evaluate_revert_safety(...) == (True, ...)` and charged a `RevertBudget` — this
    function performs no safety checks of its own, matching the boundary that
    `revert.py`'s job is deciding-and-acting, split into a pure decision function and
    a thin git-mechanics function."""
    _git(["fetch", "-q", remote], repo_root)
    _git(["checkout", "-q", branch], repo_root)
    _git(["reset", "-q", "--hard", f"{remote}/{branch}"], repo_root)
    revert = _git(["revert", "--no-edit", sha], repo_root, check=False)
    if revert.returncode != 0:
        _git(["revert", "--abort"], repo_root, check=False)
        return UnsafeHalt(commit_sha=sha,
                          diagnostic=f"revert did not apply cleanly: {revert.stderr}")
    push = _git(["push", remote, f"HEAD:{branch}"], repo_root, check=False)
    if push.returncode != 0:
        return UnsafeHalt(commit_sha=sha, diagnostic=f"revert push failed: {push.stderr}")
    new_sha = _git(["rev-parse", "HEAD"], repo_root).stdout.strip()
    return Landed(commit_sha=new_sha)
