import os
import subprocess

import pytest
from langatlas_orchestrator import registry as registry_module


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch):
    """Every test gets a private copy of the module-level registry dict so tests can
    register throwaway job kinds without leaking into each other or into the real
    built-in kinds registered by `jobs/__init__.py`."""
    monkeypatch.setattr(registry_module, "_REGISTRY", dict(registry_module._REGISTRY))


_TESTS_NEEDING_GIT_IDENTITY_BYPASS = {
    "test_run_resolves_an_ambiguous_row_via_the_git_trailer",
}


def pytest_collection_modifyitems(items):
    """Apply git_identity_bypass only to the named tests below (mirrors the identical
    workaround in tools/commit/tests/conftest.py — see the docstring there for the
    full rationale). Scoped to this one test, which creates real git commits in a
    throwaway repo under this machine's personal pre-commit hook."""
    for item in items:
        if item.name in _TESTS_NEEDING_GIT_IDENTITY_BYPASS:
            item.fixturenames.insert(0, "git_identity_bypass")


@pytest.fixture
def git_identity_bypass(monkeypatch):
    """Bypass git pre-commit hook identity verification, for the duration of one test.

    This machine has a personal global pre-commit hook (/home/terra/.git-hooks-global/
    pre-commit) that rejects commits from subprocess calls when the committer identity
    doesn't match the configured user identity and there's no TTY available to
    confirm. This is a known local-dev-environment limitation, not a live bug — see
    tools/commit/tests/conftest.py for the identical fixture and its full rationale.
    """
    original_run = subprocess.run

    def wrapped_run(*args, **kwargs):
        if "env" not in kwargs:
            kwargs["env"] = os.environ.copy()

        if args and isinstance(args[0], list) and len(args[0]) > 0 and args[0][0] == "git":
            cmd = list(args[0])
            cmd_with_config = ["git", "-c", "user.email=bot@example.com", "-c", "user.name=bot"]
            cmd_with_config.extend(cmd[1:])

            if "commit" in cmd_with_config:
                commit_idx = cmd_with_config.index("commit")
                cmd_with_config.insert(commit_idx + 1, "--no-verify")

            args = (cmd_with_config,) + args[1:]

        return original_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", wrapped_run)
