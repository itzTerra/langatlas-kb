import hashlib
import re

# D18: the wrapper logs message content only — auth headers and endpoint config never
# enter a transcript by construction. These patterns are the belt-and-suspenders layer
# for secrets that arrive *inside* content (pasted config, a tool result, a stack trace).
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("bearer", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9._\-]{16,}")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}")),
    ("assignment", re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password)\b\s*[:=]\s*[\"']?[A-Za-z0-9._\-]{16,}[\"']?")),
]

TOOL_RESULT_MAX_BYTES = 2048
TOOL_RESULT_EXCERPT_CHARS = 1024


def scrub_secrets(text: str) -> tuple[str, list[str]]:
    """Return (scrubbed_text, kinds_found). A leak in a public immutable log is the one
    unrecoverable failure mode here, so this runs on every event before it is written."""
    kinds: list[str] = []
    for kind, pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            kinds.append(kind)
            text = pattern.sub(f"[REDACTED:{kind}]", text)
    return text, kinds


def truncate_tool_result(text: str, *, source_id: str | None) -> tuple[str, dict]:
    """D18: large fetched-source tool results are truncated in the *published* transcript
    to excerpt + hash. The full text lives only in the private snapshot store (D4/D15).
    This is a copyright control, not a noise control."""
    raw = text.encode("utf-8")
    ref = {
        "truncated": False,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "source_id": source_id,
    }
    if len(raw) <= TOOL_RESULT_MAX_BYTES:
        return text, ref
    ref["truncated"] = True
    return text[:TOOL_RESULT_EXCERPT_CHARS] + "\n…[truncated]", ref
