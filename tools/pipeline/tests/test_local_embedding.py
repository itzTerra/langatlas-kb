import pytest
from langatlas_pipeline.config import ProviderConfig
from langatlas_pipeline.errors import UnknownAlias
from langatlas_pipeline.providers.local_embedding import (
    LOCAL_PREFIX, LocalEmbeddingClient, is_local, local_model_name,
)

MODEL = LOCAL_PREFIX + "BAAI/bge-small-en-v1.5"


class _FakeEncoder:
    """Stands in for fastembed's TextEmbedding: same duck type (`embed(iterable)` ->
    an iterable of vectors), so the tests never need the real package or its download."""

    def __init__(self, dimensions=4):
        self.dimensions = dimensions
        self.seen = []

    def embed(self, texts):
        texts = list(texts)
        self.seen.extend(texts)
        return [[float(len(text) % 10)] + [0.0] * (self.dimensions - 1) for text in texts]


def test_is_local_recognises_the_prefix():
    assert is_local(MODEL) is True
    assert is_local("qwen3-embedding-4b") is False
    assert local_model_name(MODEL) == "BAAI/bge-small-en-v1.5"


def test_config_resolves_a_local_model(tmp_path):
    config = ProviderConfig(
        providers={}, config_dir=tmp_path,
        capabilities={"embeddings": {"remote": {"dimensions": 8, "max_input_tokens": 99}},
                      "local_embeddings": {MODEL: {"dimensions": 384,
                                                   "max_input_tokens": 512}}})
    cap = config.embedding(MODEL)
    assert (cap.model, cap.dimensions, cap.max_input_tokens) == (MODEL, 384, 512)
    assert config.embedding("remote").dimensions == 8
    with pytest.raises(UnknownAlias):
        config.embedding("nope")


def test_local_client_embeds_and_logs(local_ctx):
    import json
    encoder = _FakeEncoder()
    client = LocalEmbeddingClient(local_ctx, encoder=encoder)
    vectors = client.embed(["alpha", "beta"], model=MODEL)
    assert len(vectors) == 2 and len(vectors[0]) == 4
    assert encoder.seen == ["alpha", "beta"]
    # D18: a local call costs nothing but is still a call the run made.
    rows = [json.loads(line)
            for line in (local_ctx.private_dir / "cost-log.jsonl").read_text().splitlines()]
    assert [r["endpoint"] for r in rows] == ["embeddings"]
    assert rows[0]["tokens_in"] > 0


def test_local_client_truncates_when_asked(local_ctx):
    encoder = _FakeEncoder()
    client = LocalEmbeddingClient(local_ctx, encoder=encoder)
    client.embed(["word " * 5000], model=MODEL, truncate=True)
    assert client.truncated == 1
    assert len(encoder.seen[0]) < len("word " * 5000)


def test_local_client_refuses_an_oversized_text_by_default(local_ctx):
    from langatlas_pipeline.errors import ContextTooLarge

    client = LocalEmbeddingClient(local_ctx, encoder=_FakeEncoder())
    with pytest.raises(ContextTooLarge):
        client.embed(["word " * 5000], model=MODEL)


def test_local_client_reuses_the_cache(local_ctx):
    encoder = _FakeEncoder()
    client = LocalEmbeddingClient(local_ctx, encoder=encoder)
    client.embed(["alpha"], model=MODEL)
    client.embed(["alpha"], model=MODEL)
    assert encoder.seen == ["alpha"]           # second call served from cache
    assert client.cache_hits == 1


def test_run_context_dispatches_local_models(local_ctx, monkeypatch):
    encoder = _FakeEncoder()
    monkeypatch.setattr(
        "langatlas_pipeline.providers.local_embedding.build_encoder",
        lambda name: encoder)
    vectors = local_ctx.embed(["alpha"], model=MODEL)
    assert len(vectors[0]) == 4
    assert encoder.seen == ["alpha"]
    assert local_ctx.embedding_cache_hits == 0


@pytest.fixture
def local_ctx(tmp_path):
    from langatlas_pipeline.providers.core import Budget, RunContext
    from langatlas_pipeline.transcripts.events import RunManifest

    config = ProviderConfig(
        providers={"completion": {"min_interval_seconds": {"embedding": 0.0},
                                  "max_attempts": 1},
                   "transcripts": {"publish": False, "push": False}},
        capabilities={"local_embeddings": {MODEL: {"dimensions": 4,
                                                   "max_input_tokens": 512}}},
        config_dir=tmp_path)
    manifest = RunManifest(run_id="r", kind="test", started="now", budget={})
    (tmp_path / "run").mkdir(parents=True, exist_ok=True)
    (tmp_path / "private").mkdir(parents=True, exist_ok=True)
    ctx = RunContext(run_id="r", kind="test", budget=Budget(), config=config,
                     run_dir=tmp_path / "run", private_dir=tmp_path / "private",
                     manifest=manifest)
    yield ctx
    ctx.close(publish=False)
