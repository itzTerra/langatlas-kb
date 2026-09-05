import json
import pytest
from pathlib import Path
from langatlas_ingest.benchmark.arms import Arm
from langatlas_ingest.benchmark.metrics import IndexStats
from langatlas_ingest.benchmark.runner import (
    ArmResult, load_results, write_result,
)

ARM = Arm(embedding_model="m", mode="hybrid", rerank=True, chunk_target_tokens=600,
          chunk_max_tokens=800, truncate=False)
STATS = IndexStats(model="m", chunks=10, tokens=100, embed_seconds=2.0,
                   chunks_per_second=5.0, tokens_per_second=50.0, truncated_chunks=0,
                   cached_vectors=0, throughput_honest=True, table_bytes=80,
                   bytes_per_chunk=8.0, dimensions=4)


def _result(**overrides) -> ArmResult:
    payload = {"arm": ARM, "index": STATS,
               "metrics": {"queries": 5, "recall_at_5": 0.8, "recall_at_50": 0.95,
                           "mrr": 0.7, "ndcg_at_10": 0.6, "latency_p50_ms": 40.0,
                           "skipped_queries": 2, "per_query": []},
               "pilot_sources": ("s1",), "run_id": "r1", "finished": "2026-09-05T00:00:00Z"}
    payload.update(overrides)
    return ArmResult(**payload)


def test_points_properties_convert_fractions_once():
    result = _result()
    assert result.recall_at_5_pts == 80.0
    assert result.ndcg_at_10_pts == 60.0


def test_points_are_none_when_the_metric_is():
    result = _result(metrics={"recall_at_5": None, "ndcg_at_10": None})
    assert result.recall_at_5_pts is None and result.ndcg_at_10_pts is None


def test_result_round_trips_through_json(tmp_path: Path):
    path = write_result(_result(), tmp_path)
    assert path.name == f"{ARM.arm_id}.json"
    restored = ArmResult.from_dict(json.loads(path.read_text()))
    assert restored.arm == ARM
    assert restored.index.table_bytes == 80
    assert restored.metrics["recall_at_5"] == 0.8


def test_written_json_is_stable_and_readable(tmp_path: Path):
    first = write_result(_result(), tmp_path).read_text()
    second = write_result(_result(), tmp_path).read_text()
    assert first == second                # sorted keys, fixed indent: diffable
    assert first.endswith("\n")


def test_load_results_is_keyed_by_arm_id(tmp_path: Path):
    write_result(_result(), tmp_path)
    results = load_results(tmp_path)
    assert list(results) == [ARM.arm_id]


def test_load_results_ignores_non_json_files(tmp_path: Path):
    write_result(_result(), tmp_path)
    (tmp_path / "README.md").write_text("notes")
    assert list(load_results(tmp_path)) == [ARM.arm_id]


def test_run_matrix_skips_an_arm_that_already_has_a_result(tmp_path: Path,
                                                            monkeypatch):
    from langatlas_ingest.benchmark import runner

    write_result(_result(), tmp_path)
    calls = []
    monkeypatch.setattr(runner, "run_arm",
                        lambda *a, **k: calls.append(k) or _result())
    matrix = type("M", (), {"results_dir": tmp_path, "pilot_sources": ("s1",),
                            "golden_dir": tmp_path})()
    results = runner.run_matrix(None, [ARM], matrix=matrix, config=None, resume=True)
    assert calls == []                    # skipped
    assert len(results) == 1              # but still reported


def test_run_matrix_reruns_when_resume_is_off(tmp_path: Path, monkeypatch):
    from langatlas_ingest.benchmark import runner

    write_result(_result(), tmp_path)
    calls = []
    monkeypatch.setattr(runner, "run_arm",
                        lambda *a, **k: calls.append(k) or _result())
    matrix = type("M", (), {"results_dir": tmp_path, "pilot_sources": ("s1",),
                            "golden_dir": tmp_path})()
    runner.run_matrix(None, [ARM], matrix=matrix, config=None, resume=False)
    assert len(calls) == 1
