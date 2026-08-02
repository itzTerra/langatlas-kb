from dataclasses import dataclass


class PipelineError(Exception):
    """Base for every typed failure the provider layer raises."""


class UnknownAlias(PipelineError):
    pass


class BudgetExceeded(PipelineError):
    """Raised *before* a call would cross a declared cap; the run stays resumable."""

    def __init__(self, kind: str, used: int, limit: int):
        super().__init__(f"budget exceeded: {kind} used={used} limit={limit}")
        self.kind, self.used, self.limit = kind, used, limit


class ContextTooLarge(PipelineError):
    """The wrapper never auto-truncates; the call site decides how to shrink."""

    def __init__(self, alias: str, estimated_tokens: int, max_input_tokens: int):
        super().__init__(f"{alias}: ~{estimated_tokens} tokens > window {max_input_tokens}")
        self.alias = alias
        self.estimated_tokens = estimated_tokens
        self.max_input_tokens = max_input_tokens


class StructuredOutputError(PipelineError):
    def __init__(self, alias: str, raw_text: str, attempts: int):
        super().__init__(f"{alias}: structured output failed after {attempts} attempts")
        self.alias, self.raw_text, self.attempts = alias, raw_text, attempts


class ProviderTransportError(PipelineError):
    def __init__(self, message: str, status: int | None = None, attempts: int = 0):
        super().__init__(message)
        self.status, self.attempts = status, attempts


class CircuitOpen(PipelineError):
    """N consecutive transport failures: pause the run rather than hammer a down service."""


class AliasDrift(PipelineError):
    """The gateway resolved an alias to a different model mid-run (D26: pin and abort)."""

    def __init__(self, alias: str, pinned: str, observed: str):
        super().__init__(f"{alias}: pinned {pinned}, gateway returned {observed}")
        self.alias, self.pinned, self.observed = alias, pinned, observed


class UntrustedContentInSystemRole(PipelineError):
    """D31: fetched content is never allowed to occupy a system/developer message."""


@dataclass
class ClaudeLimitSignal(PipelineError):
    """D41: reactive Claude usage-limit telemetry — distinct from a self-imposed
    BudgetExceeded. No proactive quota API exists on Pro, so this is raised from
    whatever the Claude channel actually observes."""

    detected_at: str
    signal_type: str          # "rate_limited" | "usage_limit" | "auth"
    raw_message: str
    run_id: str
    resets_at: int | None = None

    def __str__(self) -> str:
        return f"claude limit ({self.signal_type}) during {self.run_id}: {self.raw_message}"
