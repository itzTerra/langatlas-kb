import time
from langatlas_pipeline.cache import cache_key
from langatlas_pipeline.errors import ContextTooLarge
from langatlas_pipeline.providers.completion import build_client, estimate_tokens, truncate_to_tokens
from langatlas_pipeline.providers.throttle import Throttle


class EmbeddingClient:
    """Batch embeddings through the same policy core. Logged as tool-class events —
    token counts, no message bodies — so transcripts stay readable (D18)."""

    def __init__(self, ctx, *, client=None, batch_size: int = 32,
                 throttle: Throttle | None = None):
        self.ctx = ctx
        self._client = client
        self.batch_size = batch_size
        self.truncated = 0
        self.cache_hits = 0
        settings = ctx.config.completion_settings()
        self.throttle = throttle or Throttle(
            min_interval=(settings.get("min_interval_seconds") or {}).get("embedding", 0.1),
            max_attempts=settings.get("max_attempts", 5))

    @property
    def client(self):
        if self._client is None:
            self._client = build_client(self.ctx.config)
        return self._client

    def embed(self, texts: list[str], *, model: str, truncate: bool = False,
              max_input_tokens: int | None = None) -> list[list[float]]:
        """`truncate` is off by default: the wrapper never silently shortens production
        text, because a claim verified against a half-read chunk is worse than a refused
        call. §8.6's benchmark turns it on deliberately, so a 512-token candidate is
        measured on exactly the input production would give it — and `self.truncated`
        makes the cost of that visible in the arm's result rather than invisible.

        `max_input_tokens` overrides the capability table for a model the table does not
        list yet (Task 1's probe). Nothing in the benchmark passes it.
        """
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
            # One aggregate record for the whole embed() call's cache hits, mirroring
            # how the miss-path below logs one record_call per provider batch rather
            # than one per text — total silence otherwise (a fully-cached call wrote
            # zero transcript/cost-log rows before this fix).
            self.ctx.recorder.record_call(
                endpoint="embeddings", alias=model, resolved_model=model, messages=[],
                response_text=None, tokens_in=0, tokens_out=0,
                latency_ms=0, cache_hit=True, outcome="ok",
                tool_call={"name": "embed", "args": {"n": cache_hits, "model": model}})

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
