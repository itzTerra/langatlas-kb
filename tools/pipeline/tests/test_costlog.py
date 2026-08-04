from pathlib import Path
from langatlas_pipeline.costlog import CostRow, append_cost_row, read_cost_rows


def test_rows_round_trip_as_jsonl(tmp_path: Path):
    path = tmp_path / "cost-log.jsonl"
    row = CostRow(ts="2026-08-02T10:00:00Z", run_id="r1", seq=3, endpoint="chat",
                  alias="glm", resolved_model="glm-5.2", prompt_id="verifier",
                  prompt_version="v-0a1b2c3d", tokens_in=100, tokens_out=20,
                  tokens_if_uncached=120, latency_ms=850, cache_hit=False, outcome="ok")
    append_cost_row(path, row)
    append_cost_row(path, row)
    rows = read_cost_rows(path)
    assert len(rows) == 2
    assert rows[0].alias == "glm"
    assert rows[0].tokens_if_uncached == 120


def test_reading_a_missing_log_returns_empty(tmp_path: Path):
    assert read_cost_rows(tmp_path / "nope.jsonl") == []
