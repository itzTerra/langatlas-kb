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


_BENCH_SOURCE_BODY = ("A match expression compares a scrutinee against a sequence of "
                     "patterns and evaluates the arm of the first pattern that matches "
                     "it. ") * 6
_BENCH_SOURCE_HTML = (f"<html><body><h1 id='expressions'>Expressions</h1>"
                     f"<p>{_BENCH_SOURCE_BODY}</p>"
                     f"<h2 id='match-expressions'>Match expressions</h2>"
                     f"<p>{_BENCH_SOURCE_BODY}</p></body></html>")


@pytest.fixture
def bench_target(dsn):
    """A distinctly-named throwaway database, mirroring `test_benchmark_corpus.py`'s
    fixture of the same name — never `langatlas_bench` and never production."""
    import uuid
    import psycopg

    name = f"langatlas_bench_test_{uuid.uuid4().hex[:8]}"
    yield dsn, name
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _build_real_bench_corpus(bench_target, snapshot_root, tmp_path, *, target_tokens,
                             max_tokens):
    """Builds a real (small) bench corpus at a known chunk size, using the same
    `create_bench_db` / `build_bench_corpus` path the CLI uses — so `run_arm`'s guard is
    exercised against a genuinely recorded chunking, not a hand-built fixture row."""
    import psycopg
    from langatlas_ingest.benchmark.corpus import build_bench_corpus, create_bench_db
    from langatlas_ingest.config import IngestConfig
    from langatlas_ingest.snapshot import SnapshotStore

    base_dsn, name = bench_target
    target = create_bench_db(base_dsn, name=name)
    path = tmp_path / "ref.html"
    path.write_text(_BENCH_SOURCE_HTML)
    snapshots = SnapshotStore(snapshot_root)
    snapshots.put("bench-src", path, media_type="text/html",
                 source_url="https://example.org/ref", locator_kinds=["web-fragment"])
    config = IngestConfig.load(overrides={"chunk_target_tokens": target_tokens,
                                          "chunk_max_tokens": max_tokens,
                                          "chunk_overlap_tokens": 8})
    conn = psycopg.connect(target, autocommit=True)
    build_bench_corpus(conn, sources=["bench-src"], config=config, snapshots=snapshots)
    return conn, config


@pytest.mark.db
def test_run_arm_refuses_to_score_against_a_differently_chunked_bench_corpus(
        bench_target, snapshot_root, tmp_path, monkeypatch):
    # Finding I4: the bench corpus was built at 40/60, but the arm below declares
    # 999/1200. `run_arm` must catch this itself — the CLI-level guard that already
    # exists for `--chunk-size-for` does not cover the primary-matrix path at all.
    from langatlas_ingest.benchmark import runner as runner_mod
    from langatlas_ingest.errors import BenchCorpusChunkSizeMismatch

    conn, config = _build_real_bench_corpus(bench_target, snapshot_root, tmp_path,
                                            target_tokens=40, max_tokens=60)
    mismatched_arm = Arm(embedding_model="m", mode="vector", rerank=False,
                         chunk_target_tokens=999, chunk_max_tokens=1200, truncate=False)
    matrix = type("M", (), {"pilot_sources": ("bench-src",), "golden_dir": tmp_path})()

    embed_calls = []
    monkeypatch.setattr(runner_mod, "embed_and_measure",
                        lambda *a, **k: embed_calls.append(1))

    with pytest.raises(BenchCorpusChunkSizeMismatch) as exc_info:
        runner_mod.run_arm(conn, mismatched_arm, matrix=matrix, config=config)
    assert "999/1200" in str(exc_info.value) and "40/60" in str(exc_info.value)
    assert embed_calls == []          # never even attempted embedding work
    conn.close()


@pytest.mark.db
def test_run_arm_proceeds_past_the_guard_when_chunk_sizes_match(
        bench_target, snapshot_root, tmp_path, monkeypatch):
    # The mirror case: a correctly-sized arm must not be blocked by the new guard. A
    # sentinel raised from the next step (`RunContext.start`) proves execution passed
    # the chunk-size check without needing a real embedding/search pipeline.
    from langatlas_ingest.benchmark import runner as runner_mod

    conn, config = _build_real_bench_corpus(bench_target, snapshot_root, tmp_path,
                                            target_tokens=40, max_tokens=60)
    matching_arm = Arm(embedding_model="m", mode="vector", rerank=False,
                       chunk_target_tokens=40, chunk_max_tokens=60, truncate=False)
    matrix = type("M", (), {"pilot_sources": ("bench-src",), "golden_dir": tmp_path})()

    class _PastTheGuard(Exception):
        pass

    def _boom(*a, **k):
        raise _PastTheGuard

    monkeypatch.setattr(runner_mod.RunContext, "start", staticmethod(_boom))

    with pytest.raises(_PastTheGuard):
        runner_mod.run_arm(conn, matching_arm, matrix=matrix, config=config)
    conn.close()
