import json
from datetime import date
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_pipeline.injection import UNTRUSTED_CLOSE, delimit_untrusted
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


# ---- fix wave 2: surgical truncation of composite prompts ---------------------------

_BEFORE = "Evaluate the claim below against the following evidence, then answer yes or no."
_AFTER = "Now answer with exactly one word, and cite the source id you were given."


def test_a_composite_prompt_keeps_its_instructions_and_clips_only_the_evidence(tmp_path: Path):
    """Fix C: whole-message truncation clipped the task instructions along with the
    copyrighted body — and dropped them entirely when the block came first."""
    writer = _writer(tmp_path)
    block = delimit_untrusted("COPYRIGHTED " * 300, source_id="src-vanroy-2003",
                              kind="web-fetch")
    event = writer.append(role="user", content=f"{_BEFORE}\n{block}\n{_AFTER}")

    assert _BEFORE in event.content, "instructions before the evidence survive verbatim"
    assert _AFTER in event.content, "instructions after the evidence survive verbatim"
    assert event.tool_result_ref["truncated"] is True
    assert "truncated" in event.flags
    assert "delimited-untrusted" in event.flags
    assert event.content.count("COPYRIGHTED") < 300, "the evidence body was clipped"
    assert event.content.rstrip().endswith(_AFTER)
    assert UNTRUSTED_CLOSE in event.content, "the block still closes"


def test_the_span_ref_carries_the_real_source_id(tmp_path: Path):
    """Fix D: the ref's source_id was always null on a carried message, so the claimed
    correlation with the tool-role event only worked by substring accident."""
    writer = _writer(tmp_path)
    block = delimit_untrusted("COPYRIGHTED " * 300, source_id="src-vanroy-2003",
                              kind="web-fetch")
    event = writer.append(role="user", content=f"{_BEFORE}\n{block}")
    assert event.tool_result_ref["source_id"] == "src-vanroy-2003"
    assert event.tool_result_ref["spans"][0]["source_id"] == "src-vanroy-2003"


def test_two_evidence_blocks_are_each_clipped_and_each_reported(tmp_path: Path):
    writer = _writer(tmp_path)
    first = delimit_untrusted("AAAA " * 800, source_id="src-a", kind="web-fetch")
    second = delimit_untrusted("BBBB " * 800, source_id="src-b", kind="web-fetch")
    event = writer.append(role="user", content=f"{_BEFORE}\n{first}\nand also\n{second}\n{_AFTER}")

    refs = event.tool_result_ref["spans"]
    assert [ref["source_id"] for ref in refs] == ["src-a", "src-b"]
    assert all(ref["truncated"] for ref in refs)
    assert event.tool_result_ref["truncated"] is True
    assert "and also" in event.content and _BEFORE in event.content and _AFTER in event.content
    assert event.content.count("AAAA") < 800 and event.content.count("BBBB") < 800


def test_a_bare_oversized_block_is_still_truncated(tmp_path: Path):
    """Regression guard for finding 1: no surrounding text, so the whole message is
    evidence and must still shrink."""
    writer = _writer(tmp_path)
    block = delimit_untrusted("COPYRIGHTED " * 300, source_id="src-1", kind="web-fetch")
    event = writer.append(role="user", content=block)
    assert event.tool_result_ref["truncated"] is True
    assert len(event.content) < len(block)
    assert event.content.count("COPYRIGHTED") < 300


def test_a_raw_tool_result_is_still_truncated_wholesale(tmp_path: Path):
    writer = _writer(tmp_path)
    event = writer.append(role="tool", content="B" * 5000, tool_name="WebFetch",
                          source_id="src-1")
    assert event.tool_result_ref["truncated"] is True
    assert "spans" not in event.tool_result_ref, "no per-span shape for a raw tool result"
