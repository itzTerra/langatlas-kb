import pytest
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_ingest.benchmark.report import matrix_markdown, pin_config, write_verdict
from langatlas_ingest.benchmark.verdict import Verdict

VERDICT = Verdict(table="source-corpus", incumbent="inc", model="cha", dimensions=1024,
                  index_type="hnsw-halfvec-cosine", mode="vector", rerank=False,
                  chunk_target_tokens=400, chunk_max_tokens=550,
                  pilot_sources=("s1",), queries_scored=30, moved=True,
                  rationale=("because",))

CONFIG = """chunking:
  target_tokens: 600
  max_tokens: 800
  overlap_tokens: 60
models:
  embedding: inc
  embedding_dimensions: 2560
  index_type: hnsw-halfvec-cosine
  reranker: r
  rerank_default_on: true
retrieval:
  mode: hybrid
  k: 5
"""


class _FakeProviderConfig:
    def __init__(self, dimensions):
        self.dimensions = dimensions

    def embedding(self, model):
        return type("Cap", (), {"model": model, "dimensions": self.dimensions,
                                "max_input_tokens": 512})()


def test_pin_config_writes_every_decided_value(tmp_path: Path):
    path = tmp_path / "ingest.yaml"
    path.write_text(CONFIG)
    changed = pin_config(VERDICT, config_path=path,
                         provider_config=_FakeProviderConfig(1024))
    data = YAML(typ="safe").load(path.read_text())
    assert data["models"]["embedding"] == "cha"
    assert data["models"]["embedding_dimensions"] == 1024
    assert data["models"]["rerank_default_on"] is False
    assert data["retrieval"]["mode"] == "vector"
    assert data["chunking"]["target_tokens"] == 400
    assert data["chunking"]["max_tokens"] == 550
    assert len(changed) == 6


def test_pin_config_preserves_the_files_comments(tmp_path: Path):
    path = tmp_path / "ingest.yaml"
    path.write_text("# load-bearing comment\n" + CONFIG)
    pin_config(VERDICT, config_path=path, provider_config=_FakeProviderConfig(1024))
    assert "# load-bearing comment" in path.read_text()


def test_pin_config_refuses_a_dimension_the_capability_table_disagrees_with(
        tmp_path: Path):
    path = tmp_path / "ingest.yaml"
    path.write_text(CONFIG)
    with pytest.raises(ValueError) as caught:
        pin_config(VERDICT, config_path=path,
                   provider_config=_FakeProviderConfig(768))
    assert "768" in str(caught.value)
    assert YAML(typ="safe").load(path.read_text())["models"]["embedding"] == "inc"


def test_pin_config_reports_no_changes_for_an_unmoved_verdict(tmp_path: Path):
    path = tmp_path / "ingest.yaml"
    path.write_text(CONFIG)
    unmoved = Verdict(table="source-corpus", incumbent="inc", model="inc",
                      dimensions=2560, index_type="hnsw-halfvec-cosine", mode="hybrid",
                      rerank=True, chunk_target_tokens=600, chunk_max_tokens=800,
                      pilot_sources=("s1",), queries_scored=30, moved=False,
                      rationale=())
    assert pin_config(unmoved, config_path=path,
                      provider_config=_FakeProviderConfig(2560)) == []


def test_write_verdict_emits_both_forms(tmp_path: Path):
    matrix = type("M", (), {"primary": (), "incumbent": "inc",
                            "pilot_sources": ("s1",)})()
    json_path, md_path = write_verdict(VERDICT, {}, matrix=matrix, root=tmp_path)
    assert json_path.name == "verdict.json" and md_path.name == "verdict.md"
    assert "cha" in md_path.read_text()
    assert json_path.read_text().endswith("\n")


def test_matrix_markdown_has_a_row_per_result_and_marks_dishonest_throughput():
    from langatlas_ingest.benchmark.arms import Arm
    from langatlas_ingest.benchmark.metrics import IndexStats
    from langatlas_ingest.benchmark.runner import ArmResult

    arm = Arm(embedding_model="m", mode="hybrid", rerank=True, chunk_target_tokens=600,
              chunk_max_tokens=800, truncate=True)
    result = ArmResult(
        arm=arm,
        index=IndexStats(model="m", chunks=10, tokens=100, embed_seconds=1.0,
                         chunks_per_second=10.0, tokens_per_second=100.0,
                         truncated_chunks=9, cached_vectors=5, throughput_honest=False,
                         table_bytes=80, bytes_per_chunk=8.0, dimensions=4),
        metrics={"queries": 30, "recall_at_5": 0.8, "recall_at_50": 0.9, "mrr": 0.5,
                 "ndcg_at_10": 0.6, "latency_p50_ms": 10.0, "skipped_queries": 7,
                 "per_query": []},
        pilot_sources=("s1",), run_id="r", finished="2026-09-05T00:00:00Z")
    matrix = type("M", (), {"primary": (arm,), "incumbent": "m",
                            "pilot_sources": ("s1",)})()
    text = matrix_markdown({arm.arm_id: result}, matrix=matrix)
    assert arm.arm_id in text
    assert "90%" in text          # truncated share, visible in the table
    assert "cache-warm" in text   # the throughput caveat, not silently omitted
