import hashlib
import subprocess
from pathlib import Path


def record_key(path: str, content: str) -> str:
    """D36 §2.3: content-derived idempotency key. Path is part of the hash input so
    the same content committed to two different paths never collides."""
    h = hashlib.sha256()
    h.update(path.encode("utf-8"))
    h.update(b"\0")
    h.update(content.encode("utf-8"))
    return h.hexdigest()


def format_trailers(record_key: str, chat_run_id: str, *, challenge_id: str | None = None) -> str:
    lines = [
        f"LangAtlas-Record-Key: {record_key}",
        f"LangAtlas-Chat-Run-Id: {chat_run_id}",
    ]
    if challenge_id is not None:
        lines.append(f"LangAtlas-Challenge-Id: {challenge_id}")
    return "\n".join(lines)


def find_record_key_in_history(repo: Path, record_key: str) -> str | None:
    """D36 §2.6: idempotent-resume ground truth — a cheap grep against main's
    reachable history, checked before any push attempt."""
    result = subprocess.run(
        ["git", "log", "--format=%H", f"--grep=LangAtlas-Record-Key: {record_key}$",
         "--fixed-strings" if False else f"--grep=LangAtlas-Record-Key: {record_key}"],
        cwd=repo, capture_output=True, text=True,
    )
    shas = [line for line in result.stdout.splitlines() if line]
    return shas[0] if shas else None


def changeset_key(changes: dict[str, str | None]) -> str:
    """`record_key` for a multi-file commit (a migration, §5.2): order-free over paths, and a
    deletion hashes differently from an empty file. Shares the Record-Key trailer, so
    `find_record_key_in_history` makes a re-landed migration idempotent exactly like a
    re-landed record."""
    digest = hashlib.sha256()
    for path in sorted(changes):
        content = changes[path]
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(b"\x01deleted" if content is None else content.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()
