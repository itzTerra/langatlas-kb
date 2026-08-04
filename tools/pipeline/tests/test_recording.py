import json
from datetime import date
from pathlib import Path
from langatlas_pipeline.costlog import read_cost_rows
from langatlas_pipeline.recording import CallRecorder
from langatlas_pipeline.transcripts.events import RunManifest
from langatlas_pipeline.transcripts.writer import TranscriptWriter, mint_run_id, run_dir_for


def _recorder(tmp_path: Path) -> tuple[CallRecorder, Path, TranscriptWriter]:
    run_id = mint_run_id("sweep", "rust", root=tmp_path, today=date(2026, 8, 2))
    writer = TranscriptWriter(run_dir_for(run_id, root=tmp_path),
                              RunManifest(run_id=run_id, kind="sweep", started="t0"))
    cost_path = tmp_path / "cost-log.jsonl"
    return CallRecorder(writer, cost_path, run_id), cost_path, writer


def test_one_call_writes_one_cost_row_and_one_event_per_message(tmp_path: Path):
    recorder, cost_path, writer = _recorder(tmp_path)
    recorder.record_call(
        endpoint="chat", alias="glm", resolved_model="glm-5.2",
        messages=[{"role": "system", "content": "judge"}, {"role": "user", "content": "claim"}],
        response_text="supported", tokens_in=40, tokens_out=2, latency_ms=700,
        cache_hit=False, outcome="ok", prompt_id="verifier", prompt_version="v-0a1b2c3d",
    )
    events = [json.loads(line)
              for line in (writer.run_dir / "transcript.jsonl").read_text().splitlines()]
    assert [e["role"] for e in events] == ["system", "user", "assistant"]
    rows = read_cost_rows(cost_path)
    assert len(rows) == 1
    assert rows[0].tokens_in == 40 and rows[0].outcome == "ok"


def test_cache_hits_cost_nothing_marginal_but_keep_the_counterfactual(tmp_path: Path):
    recorder, cost_path, writer = _recorder(tmp_path)
    recorder.record_call(endpoint="chat", alias="glm", resolved_model="glm-5.2",
                         messages=[{"role": "user", "content": "q"}],
                         response_text="a", tokens_in=0, tokens_out=0, latency_ms=1,
                         cache_hit=True, outcome="ok", tokens_if_uncached=512)
    row = read_cost_rows(cost_path)[0]
    assert row.cache_hit is True
    assert row.tokens_in == 0 and row.tokens_out == 0
    assert row.tokens_if_uncached == 512
    events = [json.loads(line)
              for line in (writer.run_dir / "transcript.jsonl").read_text().splitlines()]
    assert events[-1]["cache_hit"] is True


def test_a_failed_call_still_costs_and_still_logs(tmp_path: Path):
    recorder, cost_path, writer = _recorder(tmp_path)
    recorder.record_call(endpoint="chat", alias="mini", resolved_model="gpt-oss-120b",
                         messages=[{"role": "user", "content": "q"}], response_text="{oops",
                         tokens_in=10, tokens_out=5, latency_ms=300, cache_hit=False,
                         outcome="parse_failure")
    assert read_cost_rows(cost_path)[0].outcome == "parse_failure"
    assert (writer.run_dir / "transcript.jsonl").read_text().count("\n") == 2


def test_tool_class_calls_log_counts_not_message_bodies(tmp_path: Path):
    recorder, cost_path, writer = _recorder(tmp_path)
    recorder.record_call(endpoint="embeddings", alias="qwen3-embedding-4b",
                         resolved_model="qwen3-embedding-4b", messages=[],
                         response_text=None, tokens_in=1200, tokens_out=0, latency_ms=90,
                         cache_hit=False, outcome="ok",
                         tool_call={"name": "embed", "args": {"n": 32}})
    events = [json.loads(line)
              for line in (writer.run_dir / "transcript.jsonl").read_text().splitlines()]
    assert len(events) == 1
    assert events[0]["tool_call"]["name"] == "embed"
    assert events[0]["content"] == ""
    assert read_cost_rows(cost_path)[0].endpoint == "embeddings"
