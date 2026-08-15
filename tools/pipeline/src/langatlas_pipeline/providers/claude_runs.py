import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
from claude_agent_sdk import (
    AssistantMessage, ClaudeAgentOptions, RateLimitEvent, ResultMessage, ServerToolUseBlock,
    TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock, UserMessage, query as sdk_query,
)
from langatlas_pipeline.errors import BudgetExceeded, ClaudeLimitSignal
from langatlas_pipeline.injection import scan_for_instructions
from langatlas_pipeline.transcripts.writer import utc_now

_LIMIT_ERRORS = {"rate_limit": "rate_limited", "authentication_failed": "auth",
                 "billing_error": "usage_limit"}


@dataclass
class ClaudeRunOptions:
    """The subset of ClaudeAgentOptions LangAtlas actually sets. Kept as our own
    dataclass so call sites don't import the SDK and so the mapping is one auditable
    function."""

    system_prompt: str | None = None
    tools: list[str] | None = None
    mcp_servers: dict | None = None     # in-process SDK servers (1C's source tools)
    allowed_tools: Sequence[str] = ()
    cwd: Path | str | None = None
    max_turns: int | None = None
    model: str | None = None
    permission_mode: str = "dontAsk"
    output_format: Any = None
    add_dirs: Sequence[Path | str] = ()
    setting_sources: Any = None


@dataclass
class AgentRunResult:
    session_id: str | None
    result_text: str | None
    structured_output: Any
    num_turns: int
    is_error: bool
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    terminal_reason: str | None = None
    flags: list[str] = field(default_factory=list)


def build_agent_options(options: ClaudeRunOptions) -> ClaudeAgentOptions:
    kwargs: dict[str, Any] = {
        "system_prompt": options.system_prompt,
        "allowed_tools": list(options.allowed_tools),
        "permission_mode": options.permission_mode,
    }
    if options.tools is not None:
        kwargs["tools"] = options.tools
    if options.mcp_servers is not None:
        kwargs["mcp_servers"] = options.mcp_servers
    for name in ("cwd", "max_turns", "model", "output_format", "setting_sources"):
        value = getattr(options, name)
        if value is not None:
            kwargs[name] = value
    if options.add_dirs:
        kwargs["add_dirs"] = list(options.add_dirs)
    return ClaudeAgentOptions(**kwargs)


class ClaudeRunner:
    """The Claude channel (D26): agentic by nature, never flattened into chat(). The
    message stream is written into the same transcript and cost log as every completion
    call, so 'every agent chat is logged' holds across both channels."""

    def __init__(self, ctx, *, query_fn=None):
        self.ctx = ctx
        self.query_fn = query_fn or sdk_query

    def run(self, prompt: str, *, options: ClaudeRunOptions) -> AgentRunResult:
        return asyncio.run(self._run(prompt, options))

    async def _run(self, prompt: str, options: ClaudeRunOptions) -> AgentRunResult:
        started = time.monotonic()
        # One claude_run() invocation is one logical unit of work from the caller's
        # perspective (like one complete() call) — count it toward max_calls before
        # the run starts, distinct from the per-message max_claude_messages check
        # inside _handle_assistant which caps message volume mid-stream.
        self.ctx.check_budget(calls=1)
        self.ctx.writer.append(role="user", content=prompt, agent="claude")
        result = AgentRunResult(session_id=None, result_text=None, structured_output=None,
                                num_turns=0, is_error=False, tokens_in=0, tokens_out=0,
                                cost_usd=None)
        stream = self.query_fn(prompt=prompt, options=build_agent_options(options))
        outcome = "ok"
        try:
            try:
                async for message in stream:
                    self._handle(message, result)
            finally:
                aclose = getattr(stream, "aclose", None)
                if aclose is not None:
                    await aclose()
            outcome = "error" if result.is_error else "ok"
        except ClaudeLimitSignal:
            outcome = "claude_limit"
            raise
        except BudgetExceeded:
            outcome = "budget_stop"
            raise
        finally:
            # D26: log whatever usage was accumulated so far even when the loop was
            # interrupted partway through — a real API call already happened and
            # must not be invisible in the cost log just because it didn't finish.
            self._record(result, int((time.monotonic() - started) * 1000),
                         outcome=outcome)
        return result

    def _handle(self, message, result: AgentRunResult) -> None:
        if isinstance(message, AssistantMessage):
            self._handle_assistant(message, result)
        elif isinstance(message, UserMessage):
            self._handle_user(message)
        elif isinstance(message, RateLimitEvent):
            self._handle_rate_limit(message)
        elif isinstance(message, ResultMessage):
            usage = message.usage or {}
            result.session_id = message.session_id
            result.result_text = message.result
            result.structured_output = message.structured_output
            result.num_turns = message.num_turns
            result.is_error = message.is_error
            result.cost_usd = message.total_cost_usd
            result.terminal_reason = message.terminal_reason
            result.tokens_in = usage.get("input_tokens", result.tokens_in)
            result.tokens_out = usage.get("output_tokens", result.tokens_out)

    def _handle_assistant(self, message: AssistantMessage, result: AgentRunResult) -> None:
        if message.error in _LIMIT_ERRORS:
            raise ClaudeLimitSignal(detected_at=utc_now(),
                                    signal_type=_LIMIT_ERRORS[message.error],
                                    raw_message=f"assistant error: {message.error}",
                                    run_id=self.ctx.run_id)
        self.ctx.check_budget(calls=0, claude_messages=1)
        self.ctx.note_usage(claude_messages=1)
        usage = message.usage or {}
        result.tokens_in += usage.get("input_tokens", 0)
        result.tokens_out += usage.get("output_tokens", 0)
        for block in message.content:
            if isinstance(block, TextBlock):
                self.ctx.writer.append(role="assistant", content=block.text, agent="claude",
                                       model=message.model)
            elif isinstance(block, ThinkingBlock):
                self.ctx.writer.append(role="assistant", content=block.thinking,
                                       agent="claude", model=message.model,
                                       flags=["thinking"])
            elif isinstance(block, (ToolUseBlock, ServerToolUseBlock)):
                self.ctx.writer.append(role="assistant", content="", agent="claude",
                                       model=message.model, tool_name=block.name,
                                       tool_args=dict(block.input))

    def _handle_user(self, message: UserMessage) -> None:
        content = message.content
        if isinstance(content, str):
            self.ctx.writer.append(role="user", content=content, agent="claude")
            return
        for block in content:
            if isinstance(block, ToolResultBlock):
                body = block.content
                text = body if isinstance(body, str) else str(body)
                # D31 applies to this channel too: a WebFetch result here is exactly the
                # untrusted external text `ctx.tool_result()` scans on the completion
                # side. Same flag naming, same log-and-continue posture.
                flags = [f"injection:{flag.pattern_id}"
                         for flag in scan_for_instructions(text)]
                if block.is_error:
                    flags.append("tool-error")
                self.ctx.writer.append(role="tool", content=text,
                                       tool_name="tool_result",
                                       tool_args={"tool_use_id": block.tool_use_id},
                                       flags=flags)
            elif isinstance(block, TextBlock):
                self.ctx.writer.append(role="user", content=block.text, agent="claude")

    def _handle_rate_limit(self, message: RateLimitEvent) -> None:
        info = message.rate_limit_info
        if info.status == "rejected":
            self.ctx.writer.append(role="system", content=f"rate limit rejected: {info.raw}",
                                   flags=["claude-limit-rejected"])
            raise ClaudeLimitSignal(detected_at=utc_now(), signal_type="rate_limited",
                                    raw_message=f"{info.rate_limit_type}: {info.status}",
                                    run_id=self.ctx.run_id, resets_at=info.resets_at)
        self.ctx.writer.append(
            role="system",
            content=f"rate limit {info.status} (utilization={info.utilization})",
            flags=["claude-limit-warning"])

    def _record(self, result: AgentRunResult, latency_ms: int, *, outcome: str) -> None:
        self.ctx.note_usage(calls=1, tokens=result.tokens_in + result.tokens_out)
        self.ctx.recorder.record_call(
            endpoint="claude", alias="claude", resolved_model="claude-agent-sdk",
            messages=[], response_text=result.result_text, tokens_in=result.tokens_in,
            tokens_out=result.tokens_out, latency_ms=latency_ms, cache_hit=False,
            outcome=outcome, cost_usd=result.cost_usd, agent="claude",
            tool_call={"name": "claude_run",
                       "args": {"session_id": result.session_id,
                                "turns": result.num_turns}})
