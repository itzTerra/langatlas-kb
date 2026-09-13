"""One way every Stage 3 Claude role runs: a registered prompt, rendered and split into a
system prompt and a user prompt, executed on the Claude channel with a JSON-schema output
format, and parsed into a pydantic model — or refused with a typed error.

No repair turn: a Claude-channel session is expensive and agentic, and its full transcript is
already logged (D18), so a malformed result is something the developer reads and re-runs, not
something to paper over with a second, unlogged-in-spirit attempt."""
from typing import Sequence

from pydantic import BaseModel, ValidationError

from langatlas_pipeline.errors import UntrustedContentInSystemRole
from langatlas_pipeline.injection import is_delimited
from langatlas_pipeline.prompts import PromptRef
from langatlas_pipeline.providers.claude_runs import AgentRunResult, ClaudeRunOptions
from langatlas_pipeline.providers.core import Budget
from langatlas_research.config import ClaudeRoleConfig
from langatlas_research.errors import SurveyOutputInvalid


def split_for_claude(messages: list[dict]) -> tuple[str, str]:
    """@raises UntrustedContentInSystemRole: D31's role separation, enforced here because
        the Claude channel has no equivalent of `CompletionClient`'s check.
    @raises ValueError: no user message, or an assistant turn (not expressible as one
        Claude-channel prompt)."""
    system, user = [], []
    for message in messages:
        if message["role"] == "system":
            if is_delimited(message["content"]):
                raise UntrustedContentInSystemRole(
                    "fetched content may not occupy a system-role message (D31)")
            system.append(message["content"])
        elif message["role"] == "user":
            user.append(message["content"])
        else:
            raise ValueError(f"unsupported role for a Claude-channel prompt: {message['role']}")
    if not user:
        raise ValueError("a Claude-channel prompt needs a # user section")
    return "\n\n".join(system), "\n\n".join(user)


def role_budget(config: ClaudeRoleConfig) -> Budget:
    return Budget(max_claude_messages=config.max_claude_messages)


def run_structured(ctx, prompt: PromptRef, variables: dict, *, output_model: type[BaseModel],
                   role_config: ClaudeRoleConfig, mcp_servers: dict | None = None,
                   allowed_tools: Sequence[str] = (),
                   builtin_tools: Sequence[str] = ()) -> tuple[BaseModel, AgentRunResult]:
    """@param builtin_tools: Claude Code built-ins this role may use; empty disables all of
        them (no filesystem, no shell, no web) — the default for every role but the scout.
    @raises SurveyOutputInvalid: errored run, no structured output, or output the model
        class rejects.
    @raises ClaudeLimitSignal / BudgetExceeded: unchanged from the channel."""
    system, user = split_for_claude(prompt.render(**variables))
    manifest = getattr(ctx, "manifest", None)
    if manifest is not None and prompt.ref() not in manifest.prompts:
        manifest.prompts.append(prompt.ref())
    options = ClaudeRunOptions(
        system_prompt=system, tools=list(builtin_tools), mcp_servers=mcp_servers,
        allowed_tools=list(allowed_tools), max_turns=role_config.max_turns,
        model=role_config.model,
        output_format={"type": "json_schema", "schema": output_model.model_json_schema()})
    result = ctx.claude_run(user, options=options)
    if result.is_error or result.structured_output is None:
        raise SurveyOutputInvalid(
            f"{prompt.ref()}: no usable structured output (is_error={result.is_error},"
            f" terminal_reason={result.terminal_reason})")
    try:
        parsed = output_model.model_validate(result.structured_output)
    except ValidationError as exc:
        raise SurveyOutputInvalid(f"{prompt.ref()}: output failed its schema: {exc}") from exc
    return parsed, result
