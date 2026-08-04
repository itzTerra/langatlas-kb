import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from langatlas_pipeline.cache import CallCache
from langatlas_pipeline.config import ProviderConfig
from langatlas_pipeline.errors import AliasDrift, BudgetExceeded
from langatlas_pipeline.injection import delimit_untrusted, scan_for_instructions
from langatlas_pipeline.paths import PRIVATE_DIR, TRANSCRIPTS_ROOT
from langatlas_pipeline.recording import CallRecorder
from langatlas_pipeline.transcripts.events import RunManifest
from langatlas_pipeline.transcripts.writer import (
    TranscriptWriter, mint_run_id, run_dir_for, utc_now,
)


@dataclass
class Budget:
    """Per-run caps declared in the run manifest (D26/D43). None == uncapped."""

    max_calls: int | None = None
    max_total_tokens: int | None = None
    max_wall_seconds: int | None = None
    max_claude_messages: int | None = None

    def as_dict(self) -> dict[str, int | None]:
        return {
            "max_calls": self.max_calls,
            "max_total_tokens": self.max_total_tokens,
            "max_wall_seconds": self.max_wall_seconds,
            "max_claude_messages": self.max_claude_messages,
        }


class RunContext:
    """The policy core (D26). Owns the transcript writer, the cost log, budget
    enforcement, the cache handle, and the D31 untrusted-content door. Every provider
    client takes one of these as its first argument — there is deliberately no way to
    reach a provider without it."""

    def __init__(self, *, run_id: str, kind: str, budget: Budget, config: ProviderConfig,
                 run_dir: Path, private_dir: Path, manifest: RunManifest,
                 no_cache: bool = False):
        self.run_id = run_id
        self.kind = kind
        self.budget = budget
        self.config = config
        self.run_dir = run_dir
        self.private_dir = private_dir
        self.manifest = manifest
        self.writer = TranscriptWriter(run_dir, manifest)
        self.recorder = CallRecorder(self.writer, private_dir / "cost-log.jsonl", run_id)
        self.cache = None if no_cache else CallCache(private_dir / "call-cache.sqlite")
        self.closed = False
        self._started_monotonic = time.monotonic()
        self._calls = 0
        self._tokens = 0
        self._claude_messages = 0
        self._pinned: dict[str, str] = {}
        self._stopped_by: str | None = None
        self._completion = None
        self._embedding = None
        self._rerank = None

    @classmethod
    def start(cls, *, kind: str, slug: str, budget: Budget | None = None,
              config: ProviderConfig | None = None, transcripts_root: Path | None = None,
              private_dir: Path | None = None, no_cache: bool = False,
              agents: Sequence[dict] = (), debate_id: str | None = None) -> "RunContext":
        config = config or ProviderConfig.load()
        budget = budget or config.budget_defaults()
        transcripts_root = transcripts_root or TRANSCRIPTS_ROOT
        private_dir = private_dir or PRIVATE_DIR
        run_id = mint_run_id(kind, slug, root=transcripts_root)
        manifest = RunManifest(run_id=run_id, kind=kind, started=utc_now(),
                               agents=list(agents), debate_id=debate_id,
                               budget=budget.as_dict())
        return cls(run_id=run_id, kind=kind, budget=budget, config=config,
                   run_dir=run_dir_for(run_id, root=transcripts_root),
                   private_dir=private_dir, manifest=manifest, no_cache=no_cache)

    # ---- budget -----------------------------------------------------------------

    def check_budget(self, *, calls: int = 1, tokens: int = 0,
                     claude_messages: int = 0) -> None:
        """Raise *before* crossing a cap (D43), so the in-flight item is still
        re-attemptable and the run resumes by plain re-invocation."""
        checks = [
            ("max_calls", self._calls + calls, self.budget.max_calls),
            ("max_total_tokens", self._tokens + tokens, self.budget.max_total_tokens),
            ("max_claude_messages", self._claude_messages + claude_messages,
             self.budget.max_claude_messages),
        ]
        for kind, projected, limit in checks:
            if limit is not None and projected > limit:
                self._stopped_by = "BudgetExceeded"
                raise BudgetExceeded(kind, projected, limit)
        if self.budget.max_wall_seconds is not None:
            elapsed = int(time.monotonic() - self._started_monotonic)
            if elapsed > self.budget.max_wall_seconds:
                self._stopped_by = "BudgetExceeded"
                raise BudgetExceeded("max_wall_seconds", elapsed,
                                     self.budget.max_wall_seconds)

    def note_usage(self, *, calls: int = 0, tokens: int = 0,
                   claude_messages: int = 0) -> None:
        self._calls += calls
        self._tokens += tokens
        self._claude_messages += claude_messages

    def pin_alias(self, alias: str, resolved_model: str) -> None:
        """D26: pin the resolved model at first use and abort on mid-run drift — a
        different model answering is a provenance change, not a retry."""
        pinned = self._pinned.setdefault(alias, resolved_model)
        if pinned != resolved_model:
            raise AliasDrift(alias, pinned, resolved_model)

    def pinned_model(self, alias: str) -> str | None:
        return self._pinned.get(alias)

    # ---- D31 door ---------------------------------------------------------------

    def tool_result(self, *, tool: str, text: str, source_id: str | None = None,
                    kind: str = "source-chunk") -> str:
        """The only supported way untrusted text enters a model's context. Scans, logs,
        delimits — and always returns the content (log-and-continue, never block)."""
        flags = [f"injection:{flag.pattern_id}" for flag in scan_for_instructions(text)]
        self.writer.append(role="tool", content=text, tool_name=tool,
                           tool_args={"source_id": source_id, "kind": kind},
                           source_id=source_id, flags=flags)
        return delimit_untrusted(text, source_id=source_id, kind=kind)

    # ---- channels (delegations; implemented in Tasks 8-11) ----------------------

    def complete(self, alias: str, messages: list[dict], *, prompt, schema=None,
                 sampling=None):
        from langatlas_pipeline.providers.completion import CompletionClient

        if self._completion is None:
            self._completion = CompletionClient(self)
        return self._completion.complete(alias, messages, prompt=prompt, schema=schema,
                                         sampling=sampling)

    def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        from langatlas_pipeline.providers.embedding import EmbeddingClient

        if self._embedding is None:
            self._embedding = EmbeddingClient(self)
        return self._embedding.embed(texts, model=model)

    def rerank(self, query: str, docs: list[str], *, model: str) -> list[float]:
        from langatlas_pipeline.providers.rerank import RerankClient

        if self._rerank is None:
            self._rerank = RerankClient(self)
        return self._rerank.rerank(query, docs, model=model)

    # ---- lifecycle --------------------------------------------------------------

    def close(self, *, resulting_fact_ids: Sequence[str] = (),
              publish: bool | None = None) -> Path:
        if self.closed:
            return self.run_dir / "manifest.yaml"
        self.manifest.stats = {
            **self.manifest.stats,
            "calls": self._calls,
            "tokens": self._tokens,
            "claude_messages": self._claude_messages,
            "stopped_by": self._stopped_by,
        }
        path = self.writer.finalize(resulting_fact_ids=list(resulting_fact_ids),
                                    prompts=sorted(set(self.manifest.prompts)))
        if self.cache is not None:
            self.cache.close()
        self.closed = True
        return path

    def __enter__(self) -> "RunContext":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None and self._stopped_by is None:
            self._stopped_by = exc_type.__name__
        self.close()
