import pytest
from pathlib import Path
from langatlas_ingest.benchmark.arms import Arm, Matrix, load_matrix, slug

MATRIX = """
pilot_sources: [scott-plp, sebesta-copl]
golden_dir: tests/golden/retrieval
results_dir: benchmarks/d22-source-corpus/results
incumbent: model-a
candidates:
  - model: model-a
  - model: model-b
    truncate: true
  - model: 'local:Vendor/tiny-v1.5'
    truncate: true
    local: true
modes: [vector, hybrid]
chunk_sizes:
  primary: {target_tokens: 600, max_tokens: 800}
  secondary:
    - {target_tokens: 400, max_tokens: 550}
    - {target_tokens: 800, max_tokens: 1050}
margins:
  beat_incumbent_recall5_pts: 5.0
  local_match_recall5_pts: 2.0
  rerank_min_ndcg_pts: 2.0
  hybrid_min_recall5_pts: 2.0
  chunk_size_min_recall5_pts: 2.0
"""


@pytest.fixture
def matrix_path(tmp_path: Path) -> Path:
    path = tmp_path / "d22.yaml"
    path.write_text(MATRIX)
    return path


def test_slug_is_filename_safe():
    assert slug("local:Vendor/tiny-v1.5") == "local-vendor-tiny-v1-5"
    assert slug("qwen3-embedding-4b") == "qwen3-embedding-4b"


def test_arm_id_is_deterministic_and_readable():
    arm = Arm(embedding_model="qwen3-embedding-4b", mode="hybrid", rerank=True,
              chunk_target_tokens=600, chunk_max_tokens=800, truncate=False)
    assert arm.arm_id == "qwen3-embedding-4b__hybrid-rerank__c600"
    assert Arm(embedding_model="m", mode="vector", rerank=False,
               chunk_target_tokens=400, chunk_max_tokens=550,
               truncate=True).arm_id == "m__vector__c400"


def test_result_path_is_the_arm_id(tmp_path: Path):
    arm = Arm(embedding_model="m", mode="hybrid", rerank=False,
              chunk_target_tokens=600, chunk_max_tokens=800, truncate=False)
    assert arm.result_path(tmp_path).name == "m__hybrid__c600.json"


def test_matrix_expands_three_arms_per_model(matrix_path: Path):
    matrix = load_matrix(matrix_path)
    assert len(matrix.primary) == 9        # 3 models x {vector, hybrid, hybrid+rerank}
    per_model = {}
    for arm in matrix.primary:
        per_model.setdefault(arm.embedding_model, []).append((arm.mode, arm.rerank))
    assert per_model["model-a"] == [("vector", False), ("hybrid", False),
                                    ("hybrid", True)]


def test_vector_arms_are_never_reranked(matrix_path: Path):
    matrix = load_matrix(matrix_path)
    assert not any(arm.rerank for arm in matrix.primary if arm.mode == "vector")


def test_truncate_rides_the_candidate_not_the_mode(matrix_path: Path):
    matrix = load_matrix(matrix_path)
    truncating = {arm.embedding_model for arm in matrix.primary if arm.truncate}
    assert truncating == {"model-b", "local:Vendor/tiny-v1.5"}


def test_local_models_are_declared_for_the_verdict_rule(matrix_path: Path):
    assert load_matrix(matrix_path).local_models == ("local:Vendor/tiny-v1.5",)


def test_primary_arms_all_use_the_primary_chunk_size(matrix_path: Path):
    matrix = load_matrix(matrix_path)
    assert {(a.chunk_target_tokens, a.chunk_max_tokens) for a in matrix.primary} \
        == {(600, 800)}


def test_chunk_size_arms_are_hybrid_rerank_only(matrix_path: Path):
    matrix = load_matrix(matrix_path)
    arms = matrix.chunk_size_arms("model-a", truncate=False)
    assert [(a.chunk_target_tokens, a.mode, a.rerank, a.axis) for a in arms] == [
        (400, "hybrid", True, "chunk-size"), (800, "hybrid", True, "chunk-size")]


def test_margins_load_from_the_file(matrix_path: Path):
    assert load_matrix(matrix_path).margins.beat_incumbent_recall5_pts == 5.0


def test_paths_are_resolved_against_the_repo_root(matrix_path: Path):
    matrix = load_matrix(matrix_path)
    assert matrix.golden_dir.is_absolute() and matrix.results_dir.is_absolute()
    assert matrix.golden_dir.name == "retrieval"


def test_the_committed_matrix_loads_and_is_shaped_as_ratified():
    matrix = load_matrix()
    assert matrix.incumbent == "qwen3-embedding-4b"
    assert len(matrix.pilot_sources) == 4
    assert len(matrix.primary) == 18       # 6 candidates x 3 arms
    assert matrix.chunk_sizes == ((400, 550), (800, 1050))
