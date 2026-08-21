import subprocess
from pathlib import Path

from langatlas_commit.trailers import (
    record_key, format_trailers, find_record_key_in_history,
)


def test_record_key_deterministic_on_content_and_path():
    k1 = record_key("features/pattern-matching.yaml", "feature: pattern-matching\n")
    k2 = record_key("features/pattern-matching.yaml", "feature: pattern-matching\n")
    k3 = record_key("features/other.yaml", "feature: pattern-matching\n")
    assert k1 == k2
    assert k1 != k3


def test_format_trailers_without_challenge():
    text = format_trailers("abc123", "2026-08-21-sweep-rust-01#msg-7")
    assert "LangAtlas-Record-Key: abc123" in text
    assert "LangAtlas-Chat-Run-Id: 2026-08-21-sweep-rust-01#msg-7" in text
    assert "LangAtlas-Challenge-Id" not in text


def test_format_trailers_with_challenge():
    text = format_trailers("abc123", "run-1#msg-1", challenge_id="ch-42")
    assert "LangAtlas-Challenge-Id: ch-42" in text


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def test_find_record_key_in_history(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "bot@example.com"], repo)
    _git(["config", "user.name", "bot"], repo)
    (repo / "f.yaml").write_text("x: 1\n")
    _git(["add", "f.yaml"], repo)
    msg = "add f\n\n" + format_trailers("deadbeef", "run-1#msg-1")
    _git(["commit", "-q", "-m", msg], repo)

    sha = find_record_key_in_history(repo, "deadbeef")
    assert sha is not None
    assert find_record_key_in_history(repo, "not-there") is None
