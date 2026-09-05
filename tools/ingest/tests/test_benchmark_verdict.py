import pytest
from pathlib import Path
from langatlas_ingest.benchmark.arms import Arm, Margins, Matrix
from langatlas_ingest.benchmark.metrics import IndexStats
from langatlas_ingest.benchmark.runner import ArmResult
from langatlas_ingest.benchmark.verdict import decide
from langatlas_ingest.errors import IncompleteMatrix

INCUMBENT, CHALLENGER, LOCAL = "inc", "cha", "local:tiny"


def _matrix(**overrides) -> Matrix:
    arms = []
    for model in (INCUMBENT, CHALLENGER, LOCAL):
        for mode, rerank in (("vector", False), ("hybrid", False), ("hybrid", True)):
            arms.append(Arm(embedding_model=model, mode=mode, rerank=rerank,
                            chunk_target_tokens=600, chunk_max_tokens=800,
                            truncate=False))
    defaults = dict(pilot_sources=("s1",), golden_dir=Path("g"),
                    results_dir=Path("r"), incumbent=INCUMBENT,
                    local_models=(LOCAL,), margins=Margins(), primary=tuple(arms),
                    primary_chunk_size=(600, 800),
                    chunk_sizes=((400, 550), (800, 1050)))
    defaults.update(overrides)
    return Matrix(**defaults)


def _result(arm: Arm, *, recall5: float, ndcg: float = 0.5,
            dimensions: int = 8) -> ArmResult:
    return ArmResult(
        arm=arm,
        index=IndexStats(model=arm.embedding_model, chunks=10, tokens=100,
                         embed_seconds=1.0, chunks_per_second=10.0,
                         tokens_per_second=100.0, truncated_chunks=0, cached_vectors=0,
                         throughput_honest=True, table_bytes=80, bytes_per_chunk=8.0,
                         dimensions=dimensions),
        metrics={"queries": 30, "recall_at_5": recall5, "recall_at_50": 0.9, "mrr": 0.5,
                 "ndcg_at_10": ndcg, "latency_p50_ms": 10.0, "skipped_queries": 0,
                 "per_query": []},
        pilot_sources=("s1",), run_id="r", finished="2026-09-05T00:00:00Z")


def _results(matrix: Matrix, table: dict) -> dict:
    """`table` maps (model, mode, rerank) -> (recall5, ndcg)."""
    out = {}
    for arm in matrix.primary:
        recall5, ndcg = table[(arm.embedding_model, arm.mode, arm.rerank)]
        out[arm.arm_id] = _result(arm, recall5=recall5, ndcg=ndcg)
    return out


BASE = {
    (INCUMBENT, "vector", False): (0.60, 0.50),
    (INCUMBENT, "hybrid", False): (0.70, 0.55),
    (INCUMBENT, "hybrid", True): (0.75, 0.65),
    (CHALLENGER, "vector", False): (0.58, 0.48),
    (CHALLENGER, "hybrid", False): (0.68, 0.53),
    (CHALLENGER, "hybrid", True): (0.72, 0.62),
    (LOCAL, "vector", False): (0.40, 0.35),
    (LOCAL, "hybrid", False): (0.50, 0.42),
    (LOCAL, "hybrid", True): (0.55, 0.48),
}


def test_incumbent_stays_when_nobody_clears_the_margin():
    matrix = _matrix()
    verdict = decide(_results(matrix, BASE), matrix=matrix)
    assert verdict.model == INCUMBENT
    assert verdict.moved is False
    assert any("stays" in line for line in verdict.rationale)


def test_a_challenger_needs_five_points_not_four():
    matrix = _matrix()
    near = {**BASE, (CHALLENGER, "hybrid", True): (0.79, 0.68)}   # +4 pts
    assert decide(_results(matrix, near), matrix=matrix).model == INCUMBENT
    far = {**BASE, (CHALLENGER, "hybrid", True): (0.80, 0.68)}    # +5 pts exactly
    assert decide(_results(matrix, far), matrix=matrix).model == CHALLENGER


def test_a_local_model_within_two_points_wins_outright():
    matrix = _matrix()
    close = {**BASE, (LOCAL, "hybrid", True): (0.73, 0.63)}       # -2 pts exactly
    verdict = decide(_results(matrix, close), matrix=matrix)
    assert verdict.model == LOCAL
    assert verdict.moved is True
    assert any("local" in line for line in verdict.rationale)


def test_a_local_model_three_points_behind_does_not_win():
    matrix = _matrix()
    far = {**BASE, (LOCAL, "hybrid", True): (0.72, 0.62)}         # -3 pts
    assert decide(_results(matrix, far), matrix=matrix).model == INCUMBENT


def test_the_local_rule_is_checked_before_the_beat_by_five_rule():
    matrix = _matrix()
    both = {**BASE, (CHALLENGER, "hybrid", True): (0.85, 0.70),
            (LOCAL, "hybrid", True): (0.74, 0.64)}
    # The challenger beats the incumbent by 10 pts; the local model matches within 1.
    assert decide(_results(matrix, both), matrix=matrix).model == LOCAL


def test_the_reranker_is_turned_off_when_it_adds_under_two_ndcg_points():
    matrix = _matrix()
    weak = {**BASE, (INCUMBENT, "hybrid", True): (0.75, 0.56)}    # +1 pt over 0.55
    verdict = decide(_results(matrix, weak), matrix=matrix)
    assert verdict.rerank is False
    assert verdict.moved is True


def test_the_reranker_stays_on_at_exactly_two_points():
    matrix = _matrix()
    exact = {**BASE, (INCUMBENT, "hybrid", True): (0.75, 0.57)}   # +2 pts
    assert decide(_results(matrix, exact), matrix=matrix).rerank is True


def test_vector_only_wins_when_hybrid_adds_under_two_points():
    matrix = _matrix()
    flat = {**BASE, (INCUMBENT, "hybrid", False): (0.61, 0.55)}   # +1 pt over 0.60
    verdict = decide(_results(matrix, flat), matrix=matrix)
    assert verdict.mode == "vector"


def test_a_missing_arm_raises_instead_of_deciding():
    matrix = _matrix()
    results = _results(matrix, BASE)
    results.pop(matrix.primary[0].arm_id)
    with pytest.raises(IncompleteMatrix) as caught:
        decide(results, matrix=matrix)
    assert matrix.primary[0].arm_id in str(caught.value)


def test_a_chunk_size_arm_moves_the_chunking_only_past_the_margin():
    matrix = _matrix()
    results = _results(matrix, BASE)
    for arm in matrix.chunk_size_arms(INCUMBENT, truncate=False):
        gain = 0.02 if arm.chunk_target_tokens == 400 else 0.00
        results[arm.arm_id] = _result(arm, recall5=0.75 + gain, ndcg=0.65)
    verdict = decide(results, matrix=matrix)
    assert verdict.chunk_target_tokens == 400
    assert verdict.chunk_max_tokens == 550


def test_chunk_size_arms_are_optional():
    matrix = _matrix()
    verdict = decide(_results(matrix, BASE), matrix=matrix)
    assert (verdict.chunk_target_tokens, verdict.chunk_max_tokens) == (600, 800)


def test_the_verdict_carries_the_pinned_index_identity():
    matrix = _matrix()
    verdict = decide(_results(matrix, BASE), matrix=matrix)
    assert verdict.dimensions == 8
    assert verdict.index_type == "hnsw-halfvec-cosine"
    assert verdict.table == "source-corpus"
    assert "queries scored" in verdict.to_markdown()
