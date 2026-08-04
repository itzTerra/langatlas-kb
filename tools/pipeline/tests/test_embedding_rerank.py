import json
import pytest
from langatlas_pipeline.errors import ContextTooLarge, UnknownAlias
from langatlas_pipeline.providers.embedding import EmbeddingClient
from langatlas_pipeline.providers.rerank import RerankClient


class FakeEmbeddings:
    def __init__(self):
        self.calls = []

    def create(self, *, model, input):
        self.calls.append(list(input))
        return type("R", (), {
            "model": model,
            "data": [type("D", (), {"embedding": [float(len(text))] * 4})() for text in input],
            "usage": type("U", (), {"prompt_tokens": 7 * len(input)})(),
        })()


class FakeEmbeddingClient:
    def __init__(self):
        self.embeddings = FakeEmbeddings()


def test_embed_returns_one_vector_per_text(ctx):
    fake = FakeEmbeddingClient()
    vectors = EmbeddingClient(ctx, client=fake).embed(["alpha", "beta"],
                                                      model="qwen3-embedding-4b")
    assert len(vectors) == 2
    assert vectors[0][0] == 5.0


def test_embed_batches_and_caches_by_content(ctx):
    fake = FakeEmbeddingClient()
    client = EmbeddingClient(ctx, client=fake, batch_size=2)
    client.embed(["a", "b", "c"], model="qwen3-embedding-4b")
    assert [len(batch) for batch in fake.embeddings.calls] == [2, 1]
    client.embed(["a", "b"], model="qwen3-embedding-4b")
    assert len(fake.embeddings.calls) == 2, "cached texts are not re-sent"


def test_embed_logs_counts_not_bodies(ctx, workspace):
    EmbeddingClient(ctx, client=FakeEmbeddingClient()).embed(["alpha"],
                                                             model="qwen3-embedding-4b")
    events = [json.loads(line)
              for line in (ctx.run_dir / "transcript.jsonl").read_text().splitlines()]
    assert events[0]["tool_call"]["name"] == "embed"
    assert events[0]["content"] == ""
    row = json.loads((workspace["private"] / "cost-log.jsonl").read_text().splitlines()[0])
    assert row["endpoint"] == "embeddings"


def test_oversized_embedding_input_is_refused(ctx):
    with pytest.raises(ContextTooLarge):
        EmbeddingClient(ctx, client=FakeEmbeddingClient()).embed(
            ["x" * 5_000_000], model="mxbai-embed-large")


def test_embed_logs_cache_hits(ctx, workspace):
    fake = FakeEmbeddingClient()
    client = EmbeddingClient(ctx, client=fake)
    client.embed(["alpha", "beta"], model="qwen3-embedding-4b")
    assert len(fake.embeddings.calls) == 1, "sanity: both texts were misses first time"

    client.embed(["alpha", "beta"], model="qwen3-embedding-4b")
    assert len(fake.embeddings.calls) == 1, "fully-cached call must not re-hit the provider"

    events = [json.loads(line)
              for line in (ctx.run_dir / "transcript.jsonl").read_text().splitlines()]
    hit_events = [e for e in events if e.get("cache_hit") is True]
    assert hit_events, "a fully-cached embed() call must still write a transcript event"
    assert hit_events[-1]["tool_call"]["name"] == "embed"
    assert hit_events[-1]["tool_call"]["args"] == {"n": 2, "model": "qwen3-embedding-4b"}

    rows = [json.loads(line)
            for line in (workspace["private"] / "cost-log.jsonl").read_text().splitlines()]
    hit_rows = [r for r in rows if r["cache_hit"] is True]
    assert hit_rows, "a fully-cached embed() call must still write a cost-log row"
    assert hit_rows[-1]["endpoint"] == "embeddings"
    assert hit_rows[-1]["tokens_in"] == 0
    assert hit_rows[-1]["tokens_out"] == 0


class FakeCompleter:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def complete(self, alias, messages, *, prompt, schema=None, sampling=None):
        self.calls.append(messages)
        payload = self.payloads.pop(0)
        return type("C", (), {"text": payload,
                              "parsed": schema.model_validate_json(payload)})()


def test_rerank_scores_documents_in_order(ctx):
    completer = FakeCompleter([json.dumps({"scores": [0.9, 0.1]})])
    scores = RerankClient(ctx, completer=completer).rerank(
        "ownership", ["about ownership", "about lunch"], model="qwen3-reranker-4b")
    assert scores == [0.9, 0.1]


def test_rerank_batches_and_concatenates(ctx):
    completer = FakeCompleter([json.dumps({"scores": [0.5, 0.4]}),
                               json.dumps({"scores": [0.3]})])
    scores = RerankClient(ctx, completer=completer, batch_size=2).rerank(
        "q", ["a", "b", "c"], model="qwen3-reranker-4b")
    assert scores == [0.5, 0.4, 0.3]


def test_rerank_rejects_a_score_count_mismatch(ctx):
    completer = FakeCompleter([json.dumps({"scores": [0.5]})])
    with pytest.raises(ValueError):
        RerankClient(ctx, completer=completer).rerank("q", ["a", "b"],
                                                      model="qwen3-reranker-4b")


def test_rerank_documents_are_delimited_as_untrusted(ctx):
    completer = FakeCompleter([json.dumps({"scores": [0.5]})])
    RerankClient(ctx, completer=completer).rerank("q", ["some source text"],
                                                  model="qwen3-reranker-4b")
    sent = completer.calls[0][-1]["content"]
    assert "untrusted-external" in sent


def test_rerank_rejects_an_unknown_model(ctx):
    completer = FakeCompleter([])
    with pytest.raises(UnknownAlias):
        RerankClient(ctx, completer=completer).rerank("q", ["a"], model="not-a-reranker")
    assert completer.calls == [], "an unknown model must be rejected before any dispatch"
