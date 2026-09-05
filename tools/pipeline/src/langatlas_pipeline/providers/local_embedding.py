import time
from langatlas_pipeline.cache import cache_key
from langatlas_pipeline.errors import ContextTooLarge
from langatlas_pipeline.providers.completion import estimate_tokens, truncate_to_tokens

# `local:` rather than a separate config key, so a local model id stays an ordinary
# string everywhere else: config/ingest.yaml's `models.embedding`, the per-model
# embedding table name, an arm id, a verdict record. One namespace, one lookup.
LOCAL_PREFIX = "local:"


def is_local(model: str) -> bool:
    return model.startswith(LOCAL_PREFIX)


def local_model_name(model: str) -> str:
    return model[len(LOCAL_PREFIX):]


def build_encoder(name: str):
    """Imported lazily and behind an optional extra: `fastembed` pulls onnxruntime and a
    model download, and nothing outside §8.6's local-floor arm needs either. A developer
    who never runs that arm should never have to install it."""
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:        # pragma: no cover - exercised by the install path
        raise ImportError(
            "the local embedding arm needs the `local-embed` extra:"
            " `uv --directory tools/pipeline sync --extra local-embed`") from exc
    return TextEmbedding(model_name=name)


class LocalEmbeddingClient:
    """§8.6's free-and-local floor. Deliberately the same shape as `EmbeddingClient`:
    same cache keys, same recorder events, same truncation contract, same counters — so
    a benchmark arm cannot accidentally measure a local model on a different code path
    than a remote one, and D18's "every call is logged" holds for calls that cost
    nothing.

    Budget: a local batch is counted as a call. It buys no API quota, but the budget is
    also a runaway-loop stop-loss, and a run that embeds the corpus twice by mistake
    should hit a cap whichever backend it used.
    """

    def __init__(self, ctx, *, encoder=None, batch_size: int = 64):
        self.ctx = ctx
        self._encoder = encoder
        self._encoder_name: str | None = None
        self.batch_size = batch_size
        self.truncated = 0
        self.cache_hits = 0

    def encoder(self, model: str):
        name = local_model_name(model)
        if self._encoder is None:
            self._encoder = build_encoder(name)
            self._encoder_name = name
        elif self._encoder_name is not None and self._encoder_name != name:
            # Mirrors D26's alias pinning: one client, one model, for the life of a run.
            raise ValueError(f"local encoder pinned to {self._encoder_name!r},"
                             f" refusing to serve {name!r}")
        return self._encoder

    def embed(self, texts: list[str], *, model: str, truncate: bool = False,
              max_input_tokens: int | None = None) -> list[list[float]]:
        window = max_input_tokens
        if window is None:
            window = self.ctx.config.embedding(model).max_input_tokens
        vectors: dict[int, list[float]] = {}
        pending: list[tuple[int, str, str]] = []
        cache_hits = 0

        for index, text in enumerate(texts):
            if estimate_tokens([{"content": text}]) > window:
                if not truncate:
                    raise ContextTooLarge(model, estimate_tokens([{"content": text}]),
                                          window)
                text = truncate_to_tokens(text, window)
                self.truncated += 1
            key = cache_key(endpoint="embeddings", resolved_model=model,
                            messages=[{"role": "user", "content": text}], sampling={},
                            schema_name=None, prompt_ref=None)
            hit = self.ctx.cache.get(key) if self.ctx.cache is not None else None
            if hit is not None:
                vectors[index] = hit["vector"]
                cache_hits += 1
            else:
                pending.append((index, text, key))

        self.cache_hits += cache_hits
        if cache_hits:
            self.ctx.recorder.record_call(
                endpoint="embeddings", alias=model, resolved_model=model, messages=[],
                response_text=None, tokens_in=0, tokens_out=0, latency_ms=0,
                cache_hit=True, outcome="ok",
                tool_call={"name": "embed-local",
                           "args": {"n": cache_hits, "model": model}})

        encoder = self.encoder(model) if pending else None
        for start in range(0, len(pending), self.batch_size):
            batch = pending[start:start + self.batch_size]
            self.ctx.check_budget(calls=1)
            began = time.monotonic()
            produced = list(encoder.embed([text for _, text, _ in batch]))
            latency_ms = int((time.monotonic() - began) * 1000)
            tokens_in = estimate_tokens([{"content": text} for _, text, _ in batch])
            for (index, _, key), vector in zip(batch, produced, strict=True):
                vectors[index] = [float(value) for value in vector]
                if self.ctx.cache is not None:
                    self.ctx.cache.put(key, {"vector": vectors[index]})
            self.ctx.note_usage(calls=1, tokens=tokens_in)
            self.ctx.recorder.record_call(
                endpoint="embeddings", alias=model, resolved_model=model, messages=[],
                response_text=None, tokens_in=tokens_in, tokens_out=0,
                latency_ms=latency_ms, cache_hit=False, outcome="ok",
                tool_call={"name": "embed-local",
                           "args": {"n": len(batch), "model": model}})

        return [vectors[index] for index in range(len(texts))]
