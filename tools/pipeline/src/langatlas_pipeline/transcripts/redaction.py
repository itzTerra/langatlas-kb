import hashlib
import re
from langatlas_pipeline.injection import find_untrusted_spans

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


def truncate_untrusted_spans(text: str, *, source_id: str | None) -> tuple[str, dict]:
    """The copyright rule protects *fetched source text*, not the prompt that carries it.
    A composite message ("evaluate this claim against the following evidence: <block>,
    now answer yes/no") must keep its instructions verbatim, so only the body of each
    `<fetched-source>` block is clipped — everything outside every block is untouched.

    The returned ref keeps `truncate_tool_result`'s shape (`truncated`/`bytes`/`sha256`/
    `source_id`) and adds a per-span `spans` list. With a single block — the common case —
    the top-level fields describe that block, including its real `source_id` read off the
    block's own `id` attribute, so the tool-role and carrying-message records of the same
    chunk correlate on a field rather than on a substring."""
    spans = find_untrusted_spans(text)
    if not spans:
        # is_delimited() is a loose check; if no well-formed block is actually there, fall
        # back to the conservative whole-content rule rather than logging it verbatim.
        return truncate_tool_result(text, source_id=source_id)

    pieces: list[str] = []
    refs: list[dict] = []
    cursor = 0
    for span in spans:
        body = text[span.body_start:span.body_end]
        new_body, ref = truncate_tool_result(body, source_id=span.source_id or source_id)
        pieces.append(text[cursor:span.body_start])
        pieces.append(new_body)
        refs.append(ref)
        cursor = span.body_end
    pieces.append(text[cursor:])

    if len(refs) == 1:
        return "".join(pieces), {**refs[0], "spans": refs}
    return "".join(pieces), {
        "truncated": any(ref["truncated"] for ref in refs),
        "bytes": sum(ref["bytes"] for ref in refs),
        "sha256": None,                # no single body to hash; see `spans`
        "source_id": None,
        "spans": refs,
    }
