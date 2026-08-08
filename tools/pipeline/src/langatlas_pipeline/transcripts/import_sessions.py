import json
from collections import Counter
from pathlib import Path
from langatlas_pipeline.paths import TRANSCRIPTS_ROOT
from langatlas_pipeline.transcripts.events import RunManifest
from langatlas_pipeline.transcripts.writer import (
    TranscriptWriter, mint_run_id, run_dir_for, utc_now,
)

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


def find_session_files(root: Path | None = None) -> list[Path]:
    """Claude Code writes one JSONL per session under ~/.claude/projects/<dir>/."""
    root = root or CLAUDE_PROJECTS
    return sorted(root.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime)


def _content_blocks(content) -> list[dict]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [block for block in (content or []) if isinstance(block, dict)]


def import_session(jsonl_path: Path, *, kind: str = "interactive", slug: str | None = None,
                   transcripts_root: Path | None = None) -> Path:
    """Tap B (D18): normalize a Claude Code session file into the same run format the
    wrapper writes. Parsing is deliberately defensive — the CLI's on-disk shape is not
    a contract we control, and a new line type must never lose the rest of a session."""
    transcripts_root = transcripts_root or TRANSCRIPTS_ROOT
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()

    session_id = None
    unparsable = 0
    parsed: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            unparsable += 1
            continue
        session_id = session_id or record.get("sessionId")
        parsed.append(record)

    slug = slug or (session_id or jsonl_path.stem)
    run_id = mint_run_id(kind, slug, root=transcripts_root)
    run_dir = run_dir_for(run_id, root=transcripts_root)
    writer = TranscriptWriter(run_dir, RunManifest(run_id=run_id, kind=kind,
                                                   started=utc_now()))

    skipped: Counter[str] = Counter()
    for record in parsed:
        line_type = record.get("type")
        message = record.get("message") or {}
        if line_type not in ("user", "assistant"):
            skipped[str(line_type)] += 1
            continue
        model = message.get("model")
        usage = message.get("usage") or {}
        for block in _content_blocks(message.get("content")):
            block_type = block.get("type")
            if block_type == "text":
                writer.append(role=line_type, content=block.get("text", ""),
                              agent="claude", model=model,
                              tokens_in=usage.get("input_tokens", 0),
                              tokens_out=usage.get("output_tokens", 0))
            elif block_type == "thinking":
                writer.append(role=line_type, content=block.get("thinking", ""),
                              agent="claude", model=model, flags=["thinking"])
            elif block_type == "tool_use":
                writer.append(role=line_type, content="", agent="claude", model=model,
                              tool_name=block.get("name"),
                              tool_args=block.get("input") or {})
            elif block_type == "tool_result":
                content = block.get("content")
                writer.append(role="tool",
                              content=content if isinstance(content, str) else str(content),
                              tool_name="tool_result",
                              tool_args={"tool_use_id": block.get("tool_use_id")})
            else:
                skipped[f"block:{block_type}"] += 1

    writer.manifest.stats = {"source_session_id": session_id,
                             "source_file": jsonl_path.name,
                             "skipped_line_types": dict(skipped),
                             "unparsable_lines": unparsable}
    writer.finalize()
    return run_dir
