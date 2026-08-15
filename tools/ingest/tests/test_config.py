from langatlas_ingest.config import IngestConfig


def test_load_reads_repo_defaults():
    config = IngestConfig.load()
    assert 400 <= config.chunk_target_tokens <= 800
    assert config.chunk_max_tokens >= config.chunk_target_tokens
    assert config.embedding_model == "qwen3-embedding-4b"     # D15 incumbent until D22
    assert config.reranker_model == "qwen3-reranker-4b"
    assert config.rerank_default_on is True                   # D15: reranker default-on
    assert config.retrieval_k == 5                             # §8.1
    assert config.pdf_backend == "pymupdf"


def test_overrides_win_over_file(tmp_path):
    config = IngestConfig.load(overrides={"retrieval_k": 12, "pdf_backend": "docling"})
    assert config.retrieval_k == 12
    assert config.pdf_backend == "docling"


def test_dsn_env_wins(monkeypatch):
    monkeypatch.setenv("LANGATLAS_DSN", "postgresql://example/db")
    assert IngestConfig.load().dsn == "postgresql://example/db"


def test_the_provider_cost_knobs_load():
    """`rerank_candidates` is deliberately not `retrieval_candidates`: RRF fuses the wide
    pool in one SQL statement, but reranking spends one completion round-trip per 8
    documents on a slow API. `max_section_tokens` bounds the one path that injects text
    into a session without any budget accounting (`get_source_section`)."""
    config = IngestConfig.load()
    assert config.rerank_candidates <= config.retrieval_candidates
    assert config.rerank_candidates >= config.retrieval_k
    assert config.max_section_tokens > config.chunk_max_tokens
