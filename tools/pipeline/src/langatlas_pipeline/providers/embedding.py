import time
from langatlas_pipeline.cache import cache_key
from langatlas_pipeline.errors import ContextTooLarge
from langatlas_pipeline.providers.completion import build_client, estimate_tokens
from langatlas_pipeline.providers.throttle import Throttle


class EmbeddingClient:
    """Batch embeddings through the same policy core. Logged as tool-class events —
    token counts, no message bodies — so transcripts stay readable (D18)."""

    def __init__(self, ctx, *, client=None, batch_size: int = 32,
                 throttle: Throttle | None = None):
        self.ctx = ctx
        self._client = client
        self.batch_size = batch_size
        settings = ctx.config.completion_settings()
        self.throttle = throttle or Throttle(
            min_interval=(settings.get("min_interval_seconds") or {}).get("embedding", 0.1),
            max_attempts=settings.get("max_attempts", 5))

    @property
    def client(self):
        if self._client is None:
            self._client = build_client(self.ctx.config)
        return self._client

    def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        cap = self.ctx.config.embedding(model)
        vectors: dict[int, list[float]] = {}
        pending: list[tuple[int, str, str]] = []

        for index, text in enumerate(texts):
            estimated = estimate_tokens([{"content": text}])
            if estimated > cap.max_input_tokens:
                raise ContextTooLarge(model, estimated, cap.max_input_tokens)
            key = cache_key(endpoint="embeddings", resolved_model=model,
                            messages=[{"role": "user", "content": text}], sampling={},
                            schema_name=None, prompt_ref=None)
            hit = self.ctx.cache.get(key) if self.ctx.cache is not None else None
            if hit is not None:
                vectors[index] = hit["vector"]
            else:
                pending.append((index, text, key))

        for start in range(0, len(pending), self.batch_size):
            batch = pending[start:start + self.batch_size]
            self.ctx.check_budget(calls=1)
            began = time.monotonic()
            response = self.throttle.run(
                lambda: self.client.embeddings.create(model=model,
                                                      input=[text for _, text, _ in batch]))
            latency_ms = int((time.monotonic() - began) * 1000)
            tokens_in = getattr(getattr(response, "usage", None), "prompt_tokens", 0)
            for (index, _, key), item in zip(batch, response.data):
                vectors[index] = list(item.embedding)
                if self.ctx.cache is not None:
                    self.ctx.cache.put(key, {"vector": vectors[index]})
            self.ctx.note_usage(calls=1, tokens=tokens_in)
            self.ctx.recorder.record_call(
                endpoint="embeddings", alias=model, resolved_model=model, messages=[],
                response_text=None, tokens_in=tokens_in, tokens_out=0,
                latency_ms=latency_ms, cache_hit=False, outcome="ok",
                tool_call={"name": "embed", "args": {"n": len(batch), "model": model}})

        return [vectors[index] for index in range(len(texts))]
