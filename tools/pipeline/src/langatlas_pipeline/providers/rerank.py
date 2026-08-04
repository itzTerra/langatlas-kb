from pydantic import BaseModel
from langatlas_pipeline.injection import delimit_untrusted
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
            rendered = "\n\n".join(
                f"{i + 1}. {delimit_untrusted(doc, source_id=None, kind='rerank-candidate')}"
                for i, doc in enumerate(batch))
            messages = self.prompt.render(query=query, documents=rendered)
            result = self.completer.complete(self.alias, messages, prompt=self.prompt,
                                             schema=RerankScores)
            batch_scores = result.parsed.scores
            if len(batch_scores) != len(batch):
                raise ValueError(f"reranker returned {len(batch_scores)} scores for "
                                 f"{len(batch)} documents")
            scores.extend(batch_scores)
        return scores
