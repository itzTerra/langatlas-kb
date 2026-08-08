import json
import pytest
from claude_agent_sdk import (
    AssistantMessage, RateLimitEvent, RateLimitInfo, ResultMessage, TextBlock,
    ToolResultBlock, ToolUseBlock, UserMessage,
)
from langatlas_pipeline.errors import BudgetExceeded, ClaudeLimitSignal
from langatlas_pipeline.providers.claude_runs import (
    ClaudeRunner, ClaudeRunOptions, build_agent_options,
)


def scripted(messages):
    """Stands in for claude_agent_sdk.query — same async-iterator contract."""

    async def _query(*, prompt, options, transport=None):
        for message in messages:
            yield message

    return _query


def _assistant(text, **kwargs):
    return AssistantMessage(content=[TextBlock(text=text)], model="claude-opus-5",
                            usage={"input_tokens": 100, "output_tokens": 20}, **kwargs)


def _result(**kwargs):
    defaults = dict(subtype="success", duration_ms=1200, duration_api_ms=900,
                    is_error=False, num_turns=1, session_id="sess-1",
                    total_cost_usd=0.03, usage={"input_tokens": 100, "output_tokens": 20},
                    result="done", terminal_reason="completed")
    return ResultMessage(**{**defaults, **kwargs})


def test_a_simple_run_returns_the_result_and_logs_it(ctx, workspace):
    runner = ClaudeRunner(ctx, query_fn=scripted([_assistant("hello"), _result()]))
    result = runner.run("say hello", options=ClaudeRunOptions())
    assert result.result_text == "done"
    assert result.session_id == "sess-1"
    assert result.cost_usd == 0.03
    events = [json.loads(line)
              for line in (ctx.run_dir / "transcript.jsonl").read_text().splitlines()]
    assert any(e["role"] == "assistant" and e["content"] == "hello" for e in events)
    row = json.loads((workspace["private"] / "cost-log.jsonl").read_text().splitlines()[-1])
    assert row["endpoint"] == "claude"
    assert row["cost_usd"] == 0.03


def test_tool_use_and_tool_results_are_logged(ctx):
    messages = [
        AssistantMessage(content=[ToolUseBlock(id="t1", name="Read",
                                               input={"file_path": "/x"})],
                         model="claude-opus-5"),
        UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="file body")]),
        _assistant("summarized"), _result(),
    ]
    ClaudeRunner(ctx, query_fn=scripted(messages)).run("read it",
                                                       options=ClaudeRunOptions())
    events = [json.loads(line)
              for line in (ctx.run_dir / "transcript.jsonl").read_text().splitlines()]
    assert any(e["tool_call"] and e["tool_call"]["name"] == "Read" for e in events)
    assert any(e["role"] == "tool" and "file body" in e["content"] for e in events)


def test_large_tool_results_are_truncated_in_the_transcript(ctx):
    messages = [UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="Z" * 6000)]),
                _result()]
    ClaudeRunner(ctx, query_fn=scripted(messages)).run("x", options=ClaudeRunOptions())
    events = [json.loads(line)
              for line in (ctx.run_dir / "transcript.jsonl").read_text().splitlines()]
    tool_event = [e for e in events if e["role"] == "tool"][0]
    assert tool_event["tool_result_ref"]["truncated"] is True


def test_a_rejected_rate_limit_raises_a_typed_claude_limit_signal(ctx):
    messages = [
        _assistant("working"),
        RateLimitEvent(rate_limit_info=RateLimitInfo(status="rejected", resets_at=1780000000,
                                                     rate_limit_type="five_hour"),
                       uuid="u1", session_id="sess-1"),
    ]
    with pytest.raises(ClaudeLimitSignal) as excinfo:
        ClaudeRunner(ctx, query_fn=scripted(messages)).run("x", options=ClaudeRunOptions())
    assert excinfo.value.signal_type == "rate_limited"
    assert excinfo.value.resets_at == 1780000000
    assert excinfo.value.run_id == ctx.run_id


def test_a_warning_rate_limit_only_flags_the_transcript(ctx):
    messages = [
        RateLimitEvent(rate_limit_info=RateLimitInfo(status="allowed_warning",
                                                     utilization=0.85),
                       uuid="u1", session_id="sess-1"),
        _assistant("still fine"), _result(),
    ]
    result = ClaudeRunner(ctx, query_fn=scripted(messages)).run("x",
                                                                options=ClaudeRunOptions())
    assert result.is_error is False
    events = [json.loads(line)
              for line in (ctx.run_dir / "transcript.jsonl").read_text().splitlines()]
    assert any("claude-limit-warning" in e["flags"] for e in events)


def test_an_assistant_rate_limit_error_also_raises_the_signal(ctx):
    with pytest.raises(ClaudeLimitSignal):
        ClaudeRunner(ctx, query_fn=scripted([_assistant("x", error="rate_limit")])).run(
            "x", options=ClaudeRunOptions())


def test_claude_message_budget_stops_the_run(workspace):
    from langatlas_pipeline.providers.core import Budget, RunContext

    run = RunContext.start(kind="research", slug="cap", budget=Budget(max_claude_messages=1),
                           transcripts_root=workspace["transcripts"],
                           private_dir=workspace["private"])
    messages = [_assistant("one"), _assistant("two"), _result()]
    with pytest.raises(BudgetExceeded) as excinfo:
        ClaudeRunner(run, query_fn=scripted(messages)).run("x", options=ClaudeRunOptions())
    assert excinfo.value.kind == "max_claude_messages"
    run.close()


def test_a_single_claude_run_counts_as_exactly_one_call(ctx):
    messages = [_assistant("one"), _assistant("two"), _assistant("three"), _result()]
    ClaudeRunner(ctx, query_fn=scripted(messages)).run("x", options=ClaudeRunOptions())
    assert ctx._calls == 1


def test_a_max_calls_budget_is_tripped_by_a_claude_run(workspace):
    """Unlike message volume, one claude_run() invocation must count toward
    max_calls the same way one complete() call does — this could not happen at
    all before the fix."""
    from langatlas_pipeline.providers.core import Budget, RunContext

    run = RunContext.start(kind="research", slug="cap", budget=Budget(max_calls=0),
                           transcripts_root=workspace["transcripts"],
                           private_dir=workspace["private"])
    messages = [_assistant("one"), _result()]
    with pytest.raises(BudgetExceeded) as excinfo:
        ClaudeRunner(run, query_fn=scripted(messages)).run("x", options=ClaudeRunOptions())
    assert excinfo.value.kind == "max_calls"
    run.close()


def test_a_claude_limit_signal_mid_stream_still_logs_a_cost_row(ctx, workspace):
    messages = [
        _assistant("working"),
        RateLimitEvent(rate_limit_info=RateLimitInfo(status="rejected", resets_at=1780000000,
                                                     rate_limit_type="five_hour"),
                       uuid="u1", session_id="sess-1"),
    ]
    with pytest.raises(ClaudeLimitSignal):
        ClaudeRunner(ctx, query_fn=scripted(messages)).run("x", options=ClaudeRunOptions())
    row = json.loads((workspace["private"] / "cost-log.jsonl").read_text().splitlines()[-1])
    assert row["endpoint"] == "claude"
    assert row["outcome"] == "claude_limit"
    assert row["tokens_in"] == 100
    assert row["tokens_out"] == 20


def test_a_budget_stop_mid_stream_still_logs_a_cost_row(workspace):
    from langatlas_pipeline.providers.core import Budget, RunContext

    run = RunContext.start(kind="research", slug="cap", budget=Budget(max_claude_messages=1),
                           transcripts_root=workspace["transcripts"],
                           private_dir=workspace["private"])
    messages = [_assistant("one"), _assistant("two"), _result()]
    with pytest.raises(BudgetExceeded):
        ClaudeRunner(run, query_fn=scripted(messages)).run("x", options=ClaudeRunOptions())
    row = json.loads((workspace["private"] / "cost-log.jsonl").read_text().splitlines()[-1])
    assert row["endpoint"] == "claude"
    assert row["outcome"] == "budget_stop"
    assert row["tokens_in"] == 100
    assert row["tokens_out"] == 20
    run.close()


def test_a_budget_stop_is_not_a_limit_signal(workspace):
    """D41: the two must stay distinguishable — one is ours, one is Anthropic's."""
    assert not issubclass(BudgetExceeded, ClaudeLimitSignal)
    assert not issubclass(ClaudeLimitSignal, BudgetExceeded)


def test_options_map_onto_the_sdk_dataclass():
    options = build_agent_options(ClaudeRunOptions(system_prompt="be terse",
                                                   allowed_tools=["Read"],
                                                   max_turns=3, model="claude-opus-5"))
    assert options.system_prompt == "be terse"
    assert options.allowed_tools == ["Read"]
    assert options.max_turns == 3


@pytest.mark.live
def test_live_smoke(ctx):
    result = ctx.claude_run("Reply with the single word: ok",
                            options=ClaudeRunOptions(tools=[], max_turns=1))
    assert "ok" in (result.result_text or "").lower()
