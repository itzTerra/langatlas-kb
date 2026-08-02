import json
from datetime import date
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_pipeline.transcripts.events import RunManifest
from langatlas_pipeline.transcripts.writer import (
    REDACTION_RULES_VERSION, TranscriptWriter, mint_run_id, run_dir_for,
)

_yaml = YAML(typ="safe")


def test_run_id_shape_and_sequence(tmp_path: Path):
    day = date(2026, 8, 2)
    first = mint_run_id("debate", "rust-ownership", root=tmp_path, today=day)
    assert first == "2026-08-02-debate-rust-ownership-01"
    run_dir_for(first, root=tmp_path).mkdir(parents=True)
    second = mint_run_id("debate", "rust-ownership", root=tmp_path, today=day)
    assert second == "2026-08-02-debate-rust-ownership-02"


def test_run_dir_is_sharded_by_year_and_month(tmp_path: Path):
    assert run_dir_for("2026-08-02-debate-x-01", root=tmp_path) == tmp_path / "2026" / "08" / "2026-08-02-debate-x-01"


def _writer(tmp_path: Path) -> TranscriptWriter:
    run_id = mint_run_id("verification", "batch", root=tmp_path, today=date(2026, 8, 2))
    manifest = RunManifest(run_id=run_id, kind="verification", started="2026-08-02T10:00:00Z")
    return TranscriptWriter(run_dir_for(run_id, root=tmp_path), manifest)


def test_events_are_jsonl_with_monotonic_seq(tmp_path: Path):
    writer = _writer(tmp_path)
    writer.append(role="system", content="You judge entailment.")
    writer.append(role="user", content="Claim: Rust has pattern matching.")
    writer.append(role="assistant", content="supported", model="glm-5.2", tokens_out=3)
    lines = (writer.run_dir / "transcript.jsonl").read_text().splitlines()
    events = [json.loads(line) for line in lines]
    assert [e["seq"] for e in events] == [1, 2, 3]
    assert events[2]["model"] == "glm-5.2"
    assert all(e["ts"].endswith("Z") for e in events)


def test_secrets_are_scrubbed_before_the_line_is_written(tmp_path: Path):
    writer = _writer(tmp_path)
    event = writer.append(role="user", content="key: Bearer sk-abcdefghijklmnopqrstuvwx")
    written = (writer.run_dir / "transcript.jsonl").read_text()
    assert "sk-abcdefghijklmnopqrstuvwx" not in written
    assert "secret-scrubbed" in event.flags


def test_tool_results_are_truncated_and_referenced(tmp_path: Path):
    writer = _writer(tmp_path)
    event = writer.append(role="tool", content="B" * 5000, tool_name="search_sources",
                          source_id="src-vanroy-2003")
    assert event.tool_result_ref["truncated"] is True
    assert len(event.content) < 5000


def test_finalize_writes_the_manifest(tmp_path: Path):
    writer = _writer(tmp_path)
    writer.append(role="assistant", content="done")
    path = writer.finalize(ended="2026-08-02T10:05:00Z", resulting_fact_ids=["f-0123456789ab"])
    manifest = _yaml.load(path.read_text())
    assert manifest["run_id"].endswith("-01")
    assert manifest["kind"] == "verification"
    assert manifest["resulting_fact_ids"] == ["f-0123456789ab"]
    assert manifest["redaction"]["rules_version"] == REDACTION_RULES_VERSION
    assert manifest["files"] == ["transcript.jsonl"]
    assert manifest["wrapper_version"]
