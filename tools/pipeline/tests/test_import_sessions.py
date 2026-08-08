import json
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_pipeline.transcripts.import_sessions import find_session_files, import_session

_yaml = YAML(typ="safe")

SESSION = [
    {"type": "user", "timestamp": "2026-08-02T09:00:00Z", "sessionId": "abc123",
     "message": {"role": "user", "content": "design the schema"}},
    {"type": "assistant", "timestamp": "2026-08-02T09:00:05Z", "sessionId": "abc123",
     "message": {"role": "assistant",
                 "content": [{"type": "text", "text": "Here is a sketch."},
                             {"type": "tool_use", "id": "t1", "name": "Read",
                              "input": {"file_path": "/x"}}],
                 "model": "claude-opus-5",
                 "usage": {"input_tokens": 500, "output_tokens": 40}}},
    {"type": "user", "timestamp": "2026-08-02T09:00:06Z", "sessionId": "abc123",
     "message": {"role": "user",
                 "content": [{"type": "tool_result", "tool_use_id": "t1",
                              "content": "Q" * 4000}]}},
    {"type": "summary", "summary": "ignored kind"},
]


def _session_file(tmp_path: Path) -> Path:
    path = tmp_path / "abc123.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in SESSION) + "\n")
    return path


def test_import_produces_a_normalized_run(tmp_path: Path, workspace):
    run_dir = import_session(_session_file(tmp_path), kind="interactive",
                             slug="schema-design",
                             transcripts_root=workspace["transcripts"])
    events = [json.loads(line)
              for line in (run_dir / "transcript.jsonl").read_text().splitlines()]
    assert [e["role"] for e in events] == ["user", "assistant", "assistant", "tool"]
    assert events[1]["model"] == "claude-opus-5"
    assert events[2]["tool_call"]["name"] == "Read"
    assert events[3]["tool_result_ref"]["truncated"] is True


def test_import_records_the_source_session_in_the_manifest(tmp_path: Path, workspace):
    run_dir = import_session(_session_file(tmp_path), kind="interactive",
                             transcripts_root=workspace["transcripts"])
    manifest = _yaml.load((run_dir / "manifest.yaml").read_text())
    assert manifest["kind"] == "interactive"
    assert manifest["stats"]["source_session_id"] == "abc123"
    assert manifest["stats"]["skipped_line_types"] == {"summary": 1}


def test_slug_defaults_to_the_session_id(tmp_path: Path, workspace):
    run_dir = import_session(_session_file(tmp_path),
                             transcripts_root=workspace["transcripts"])
    assert "abc123" in run_dir.name


def test_malformed_lines_are_skipped_not_fatal(tmp_path: Path, workspace):
    path = tmp_path / "broken.jsonl"
    path.write_text('{"type": "user", "message": {"role": "user", "content": "ok"}}\n'
                    "not json at all\n")
    run_dir = import_session(path, transcripts_root=workspace["transcripts"])
    manifest = _yaml.load((run_dir / "manifest.yaml").read_text())
    assert manifest["stats"]["unparsable_lines"] == 1


def test_find_session_files_sorts_newest_last(tmp_path: Path):
    (tmp_path / "p1").mkdir()
    older = tmp_path / "p1" / "a.jsonl"
    newer = tmp_path / "p1" / "b.jsonl"
    older.write_text("{}\n")
    newer.write_text("{}\n")
    import os, time
    os.utime(older, (time.time() - 100, time.time() - 100))
    assert find_session_files(tmp_path)[-1] == newer
