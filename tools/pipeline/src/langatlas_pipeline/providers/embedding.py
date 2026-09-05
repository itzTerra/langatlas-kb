import time
from langatlas_pipeline.cache import cache_key
from langatlas_pipeline.errors import ContextTooLarge
from langatlas_pipeline.providers.completion import build_client, estimate_tokens, truncate_to_tokens
from langatlas_pipeline.providers.throttle import Throttle

# Live D22 benchmark evidence (2026-09-05): real gateway tokenizers vary in tokens-per-char
# far more than a fixed char ratio can bound — two ~1773-char chunks measured 396 and 509+
# real tokens against a 512-token model, and one chunk still overflowed after 4 linear
# +48-token retries (192 tokens of margin). `truncate_to_tokens`'s fixed safety margin
# narrows this but cannot eliminate it for arbitrarily dense content, so a truncated batch
# the provider still rejects is re-truncated with a multiplicative backoff and retried —
# each attempt targets a fraction of the window small enough that *some* fraction is
# guaranteed to converge quickly regardless of how token-dense the source text is, rather
# than failing the whole arm on content the char-based estimator misjudged.
_MAX_CONTEXT_RETRUNCATIONS = 5
_CONTEXT_RETRUNCATION_FACTORS = (0.85, 0.65, 0.45, 0.25, 0.1)


def _is_context_window_error(exc: Exception) -> bool:
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    return status == 400 and "contextwindowexceedederror" in str(exc).lower()


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
        # `original` is the untruncated source text whenever `truncate` is enabled for
        # this call — kept for every text, not only ones the char-based estimate flagged,
        # because a real tokenizer can reject text the estimate judged safe (dense
        # Unicode/notation tokenizes far richer than chars/4 predicts). That is exactly
        # what lets a provider-side context-window rejection re-truncate any text in the
        # batch, not only the ones pre-emptively shortened.
        pending: list[tuple[int, str, str, str | None]] = []
        cache_hits = 0
        counted_truncated: set[int] = set()

        for index, text in enumerate(texts):
            original = text if truncate else None
            if estimate_tokens([{"content": text}]) > window:
                if not truncate:
                    raise ContextTooLarge(model, estimate_tokens([{"content": text}]),
                                          window)
                text = truncate_to_tokens(text, window)
                self.truncated += 1
                counted_truncated.add(index)
            key = cache_key(endpoint="embeddings", resolved_model=model,
                            messages=[{"role": "user", "content": text}], sampling={},
                            schema_name=None, prompt_ref=None)
            hit = self.ctx.cache.get(key) if self.ctx.cache is not None else None
            if hit is not None:
                vectors[index] = hit["vector"]
                cache_hits += 1
            else:
                pending.append((index, text, key, original))

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
            for attempt in range(_MAX_CONTEXT_RETRUNCATIONS + 1):
                self.ctx.check_budget(calls=1)
                began = time.monotonic()
                try:
                    response = self.throttle.run(
                        lambda b=batch: self.client.embeddings.create(
                            model=model, input=[text for _, text, _, _ in b]))
                except Exception as exc:
                    retruncatable = any(original is not None for _, _, _, original in batch)
                    if (attempt == _MAX_CONTEXT_RETRUNCATIONS or not retruncatable
                            or not _is_context_window_error(exc)):
                        raise
                    target = max(1, int(window * _CONTEXT_RETRUNCATION_FACTORS[attempt]))
                    batch = [
                        (index, truncate_to_tokens(original, target), key, original)
                        if original is not None else (index, text, key, original)
                        for index, text, key, original in batch
                    ]
                    continue
                latency_ms = int((time.monotonic() - began) * 1000)
                tokens_in = getattr(getattr(response, "usage", None), "prompt_tokens", 0)
                for (index, sent_text, key, original), item in zip(batch, response.data):
                    if original is not None and sent_text != original:
                        if index not in counted_truncated:
                            self.truncated += 1
                            counted_truncated.add(index)
                        # The retry loop may have re-truncated `sent_text` past the key
                        # computed at the top of `embed` — cache under what was actually sent.
                        key = cache_key(endpoint="embeddings", resolved_model=model,
                                        messages=[{"role": "user", "content": sent_text}],
                                        sampling={}, schema_name=None, prompt_ref=None)
                    vectors[index] = list(item.embedding)
                    if self.ctx.cache is not None:
                        self.ctx.cache.put(key, {"vector": vectors[index]})
                self.ctx.note_usage(calls=1, tokens=tokens_in)
                self.ctx.recorder.record_call(
                    endpoint="embeddings", alias=model, resolved_model=model, messages=[],
                    response_text=None, tokens_in=tokens_in, tokens_out=0,
                    latency_ms=latency_ms, cache_hit=False, outcome="ok",
                    tool_call={"name": "embed", "args": {"n": len(batch), "model": model}})
                break

        return [vectors[index] for index in range(len(texts))]
