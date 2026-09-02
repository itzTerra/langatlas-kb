from pydantic import BaseModel
from langatlas_pipeline.prompts import load_prompt


class RerankScores(BaseModel):
    scores: list[float]


class RerankClient:
    """D26 (ratified): no /v1/rerank route is documented on the gateway, so reranking is
    completion-driven like every other call. Documents are delimited as untrusted —
    a reranker reads adversarial text by definition."""

    def __init__(self, ctx, *, completer=None, batch_size: int | None = None,
                 alias: str = "mini"):
        self.ctx = ctx
        self._completer = completer
        settings = ctx.config.providers.get("rerank", {})
        self.batch_size = batch_size or settings.get("batch_size", 8)
        self.prompt = load_prompt(settings.get("prompt_id", "rerank-score"))
        self.alias = alias

    @property
    def completer(self):
        if self._completer is None:
            from langatlas_pipeline.providers.completion import CompletionClient

            self._completer = CompletionClient(self.ctx)
        return self._completer

    def rerank(self, query: str, docs: list[str], *, model: str) -> list[float]:
        # `model` names the reranker (e.g. "qwen3-reranker-4b") per the
        # provider_capabilities.yaml `rerankers:` table; it must be a known entry
        # even though every reranker currently dispatches through the constructor's
        # completion `alias` (D26: no /v1/rerank route, so this is completion-driven).
        self.ctx.config.reranker(model)
        scores: list[float] = []
        for start in range(0, len(docs), self.batch_size):
            batch = docs[start:start + self.batch_size]
            # Through the D31 door, not around it: a rerank candidate is untrusted
            # external text like any other fetched chunk, so it gets the same lexical
            # instruction scan and the same logged flags, not just the delimiters.
            rendered = "\n\n".join(
                f"{i + 1}. " + self.ctx.tool_result(
                    tool="rerank-candidate", text=doc, source_id=None,
                    kind="rerank-candidate")
                for i, doc in enumerate(batch))
            messages = self.prompt.render(query=query, documents=rendered,
                                          count=str(len(batch)))
            # A schema-valid `{"scores": [...]}` array can still carry the wrong number
            # of entries — pydantic has no way to encode "exactly len(batch)" in a
            # static JSON schema, so a miscount is a content error the completion
            # client's own JSON-validity repair loop never sees. Observed live: at
            # sampling temperature 0, a blind identical-prompt retry reproduces the same
            # wrong count byte-for-byte, so the retry has to hand the model its own wrong
            # answer and the actual/expected counts — the same repair shape
            # CompletionClient already uses for invalid JSON — rather than resending an
            # unchanged prompt and hoping for a different sample.
            conversation = list(messages)
            batch_scores = None
            for attempt in range(2):
                result = self.completer.complete(self.alias, conversation, prompt=self.prompt,
                                                  schema=RerankScores)
                if len(result.parsed.scores) == len(batch):
                    batch_scores = result.parsed.scores
                    break
                if attempt == 0:
                    conversation = conversation + [
                        {"role": "assistant", "content": result.text},
                        {"role": "user",
                         "content": f"That was {len(result.parsed.scores)} scores; there"
                                    f" are exactly {len(batch)} documents. Reply again"
                                    f" with exactly {len(batch)} scores, one per"
                                    " document, no extra entries."},
                    ]
            if batch_scores is None:
                raise ValueError(f"reranker returned {len(result.parsed.scores)} scores"
                                 f" for {len(batch)} documents (after one repair turn)")
            scores.extend(batch_scores)
        return scores
