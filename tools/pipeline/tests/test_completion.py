import json
import time
import pytest
from pydantic import BaseModel
from langatlas_pipeline.errors import (
    ContextTooLarge, ProviderTransportError, StructuredOutputError,
    UntrustedContentInSystemRole,
)
from langatlas_pipeline.injection import delimit_untrusted
from langatlas_pipeline.prompts import load_prompt
from langatlas_pipeline.providers.completion import (
    CompletionClient, Sampling, call_with_hard_timeout, estimate_tokens, split_reasoning,
)


class Verdict(BaseModel):
    verdict: str
    confidence: float


class FakeResponses:
    """Stands in for openai.OpenAI().chat.completions — records requests, replays
    scripted responses, and can raise to exercise backoff."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, script):
        self.responses = FakeResponses(script)
        self.chat = type("Chat", (), {"completions": self.responses})()


def _response(content, *, model="glm-5.2", tokens_in=10, tokens_out=5):
    return type("R", (), {
        "model": model,
        "choices": [type("C", (), {
            "message": type("M", (), {"content": content})(),
            "finish_reason": "stop",
        })()],
        "usage": type("U", (), {"prompt_tokens": tokens_in,
                                "completion_tokens": tokens_out})(),
    })()


PROMPT = None  # set in each test via load_prompt("capability-probe")


def test_estimate_tokens_is_a_conservative_char_bound():
    assert estimate_tokens([{"role": "user", "content": "a" * 400}]) >= 110


def test_oversized_call_is_refused_not_truncated(ctx):
    prompt = load_prompt("capability-probe")
    client = CompletionClient(ctx, client=FakeClient([]))
    huge = [{"role": "user", "content": "x" * 4_000_000}]
    with pytest.raises(ContextTooLarge) as excinfo:
        client.complete("mini", huge, prompt=prompt)
    assert excinfo.value.alias == "mini"
    assert ctx.recorder.writer.seq == 0, "a refused call makes no provider contact"


def test_plain_completion_records_transcript_and_cost(ctx, workspace):
    prompt = load_prompt("capability-probe")
    client = CompletionClient(ctx, client=FakeClient([_response("pong")]))
    result = client.complete("glm", prompt.render(), prompt=prompt)
    assert result.text == "pong"
    assert result.resolved_model == "glm-5.2"
    assert result.cache_hit is False
    rows = (workspace["private"] / "cost-log.jsonl").read_text().strip().splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["prompt_id"] == "capability-probe"


def test_second_identical_call_is_a_cache_hit(ctx):
    prompt = load_prompt("capability-probe")
    fake = FakeClient([_response("pong")])
    client = CompletionClient(ctx, client=fake)
    client.complete("glm", prompt.render(), prompt=prompt)
    again = client.complete("glm", prompt.render(), prompt=prompt)
    assert again.cache_hit is True
    assert len(fake.responses.requests) == 1


def test_json_schema_mode_is_used_only_when_probed(ctx, monkeypatch):
    prompt = load_prompt("capability-probe")
    payload = json.dumps({"verdict": "supported", "confidence": 0.9})
    fake = FakeClient([_response(payload)])
    client = CompletionClient(ctx, client=fake)

    cap = ctx.config.alias("glm")
    monkeypatch.setattr(type(ctx.config), "alias",
                        lambda self, name: type(cap)(**{**cap.__dict__,
                                                        "supports_json_schema": True}))
    result = client.complete("glm", prompt.render(), prompt=prompt, schema=Verdict)
    assert result.parsed.verdict == "supported"
    assert fake.responses.requests[0]["response_format"]["type"] == "json_schema"


def test_json_object_fallback_repairs_once_then_succeeds(ctx, monkeypatch):
    prompt = load_prompt("capability-probe")
    good = json.dumps({"verdict": "supported", "confidence": 0.9})
    fake = FakeClient([_response("not json at all"), _response(good)])
    client = CompletionClient(ctx, client=fake)
    cap = ctx.config.alias("glm")
    monkeypatch.setattr(type(ctx.config), "alias",
                        lambda self, name: type(cap)(**{**cap.__dict__,
                                                        "supports_json_object": True}))
    result = client.complete("glm", prompt.render(), prompt=prompt, schema=Verdict)
    assert result.parsed.confidence == 0.9
    assert len(fake.responses.requests) == 2
    assert "repair" in fake.responses.requests[1]["messages"][-1]["content"].lower()


def test_structured_output_gives_up_after_repair_and_one_retry(ctx):
    prompt = load_prompt("capability-probe")
    fake = FakeClient([_response("nope"), _response("still nope"), _response("nope again")])
    client = CompletionClient(ctx, client=fake)
    with pytest.raises(StructuredOutputError) as excinfo:
        client.complete("glm", prompt.render(), prompt=prompt, schema=Verdict)
    assert excinfo.value.attempts == 3
    assert len(fake.responses.requests) == 3


def test_reasoning_traces_are_stripped_before_parsing_but_kept(ctx):
    body, reasoning = split_reasoning("<think>hmm</think>{\"verdict\": \"x\"}",
                                      "inline-think")
    assert body.strip().startswith("{")
    assert reasoning == "hmm"


def test_transport_failures_back_off_then_raise(ctx, monkeypatch):
    prompt = load_prompt("capability-probe")
    monkeypatch.setattr("time.sleep", lambda _: None)
    fake = FakeClient([ProviderTransportError("503", status=503)] * 5)
    client = CompletionClient(ctx, client=fake)
    with pytest.raises(ProviderTransportError):
        client.complete("glm", prompt.render(), prompt=prompt)
    assert len(fake.responses.requests) == 5


def test_call_with_hard_timeout_bounds_a_stuck_call():
    # Real time.sleep, deliberately not monkeypatched: the point is that a call which
    # never returns is still bounded by the wall clock, not by cooperative timing.
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        call_with_hard_timeout(lambda: time.sleep(5), 0.05)
    assert time.monotonic() - started < 1.0


def test_call_with_hard_timeout_returns_the_fast_result():
    assert call_with_hard_timeout(lambda: 42, 5) == 42


def test_call_with_hard_timeout_reraises_the_call_s_own_exception():
    def boom():
        raise ValueError("real failure")

    with pytest.raises(ValueError, match="real failure"):
        call_with_hard_timeout(boom, 5)


def test_a_stuck_provider_call_is_bounded_not_left_to_hang(ctx):
    # Live evidence (2026-09-11): a real call sat on an open socket for ~9 hours because
    # httpx's `timeout=` bounds each response chunk, not the call's total duration. This
    # is the regression test for the fix: `complete()` must not block past its own
    # configured hard timeout even when the transport itself never gives up.
    prompt = load_prompt("capability-probe")

    class HangingResponses:
        def __init__(self):
            self.requests = []

        def create(self, **kwargs):
            self.requests.append(kwargs)
            time.sleep(5)                   # far longer than the hard timeout below
            return _response("too late")    # pragma: no cover - never reached in time

    class HangingClient:
        def __init__(self):
            self.responses = HangingResponses()
            self.chat = type("Chat", (), {"completions": self.responses})()

    client = CompletionClient(ctx, client=HangingClient())
    client._hard_timeout_seconds = 0.05
    client.throttle.max_attempts = 1

    started = time.monotonic()
    with pytest.raises(ProviderTransportError):
        client.complete("glm", prompt.render(), prompt=prompt)
    assert time.monotonic() - started < 2.0, \
        "a stuck call must be bounded by the hard timeout, not left to hang"


def test_delimited_content_may_not_sit_in_a_system_message(ctx):
    prompt = load_prompt("capability-probe")
    client = CompletionClient(ctx, client=FakeClient([_response("pong")]))
    poisoned = [{"role": "system",
                 "content": delimit_untrusted("body", source_id="s", kind="web-fetch")}]
    with pytest.raises(UntrustedContentInSystemRole):
        client.complete("glm", poisoned, prompt=prompt)


def test_sampling_defaults_to_temperature_zero(ctx):
    prompt = load_prompt("capability-probe")
    fake = FakeClient([_response("pong")])
    CompletionClient(ctx, client=fake).complete("glm", prompt.render(), prompt=prompt)
    assert fake.responses.requests[0]["temperature"] == 0.0
    assert Sampling().temperature == 0.0


# ---- whole-branch review fixes ------------------------------------------------------

def _events(ctx):
    return [json.loads(line)
            for line in (ctx.run_dir / "transcript.jsonl").read_text().splitlines()]


def test_truncation_survives_into_the_prompt_message_that_carries_it(ctx):
    """Finding 1: ctx.tool_result() truncates the tool-role event but returns the full
    delimited text, which the caller then puts into a user message. That message must be
    truncated too, or the copyright control is undone one event later."""
    prompt = load_prompt("capability-probe")
    body = "COPYRIGHTED " * 220          # comfortably over TOOL_RESULT_MAX_BYTES
    delimited = ctx.tool_result(tool="WebFetch", text=body, source_id="src-1",
                                kind="web-fetch")
    assert "COPYRIGHTED COPYRIGHTED" in delimited, "the model still gets the full text"

    client = CompletionClient(ctx, client=FakeClient([_response("pong")]))
    client.complete("glm", [{"role": "user", "content": delimited}], prompt=prompt)

    events = _events(ctx)
    tool_event = [e for e in events if e["role"] == "tool"][0]
    assert tool_event["tool_result_ref"]["truncated"] is True
    assert "truncated" in tool_event["flags"]

    user_event = [e for e in events if e["role"] == "user"][0]
    assert user_event["tool_result_ref"] is not None, \
        "a truncated user message still needs its hash/excerpt record"
    assert user_event["tool_result_ref"]["truncated"] is True
    assert "truncated" in user_event["flags"]
    assert "delimited-untrusted" in user_event["flags"]
    assert len(user_event["content"]) < len(delimited)
    assert user_event["content"].count("COPYRIGHTED") < 200


def test_short_delimited_content_is_recorded_but_not_mangled(ctx):
    ctx.writer.append(role="user",
                      content=delimit_untrusted("short body", source_id="s",
                                                kind="web-fetch"))
    event = _events(ctx)[-1]
    assert "short body" in event["content"]
    assert event["tool_result_ref"]["truncated"] is False
    assert "truncated" not in event["flags"]


def test_a_cache_hit_still_registers_the_prompt_in_the_manifest(ctx):
    """Finding 4: manifest.prompts was appended only on the live-call path."""
    prompt = load_prompt("capability-probe")
    fake = FakeClient([_response("pong")])
    client = CompletionClient(ctx, client=fake)
    client.complete("glm", prompt.render(), prompt=prompt)
    ctx.manifest.prompts.clear()

    again = client.complete("glm", prompt.render(), prompt=prompt)
    assert again.cache_hit is True
    assert ctx.manifest.prompts == [prompt.ref()]


def test_the_manifest_prompt_list_does_not_duplicate(ctx):
    prompt = load_prompt("capability-probe")
    client = CompletionClient(ctx, client=FakeClient([_response("a"), _response("b")]))
    client.complete("glm", [{"role": "user", "content": "one"}], prompt=prompt)
    client.complete("glm", [{"role": "user", "content": "two"}], prompt=prompt)
    assert ctx.manifest.prompts == [prompt.ref()]


def test_cache_key_follows_the_run_pin_not_the_configured_model(ctx):
    """Finding 5: the config says glm resolves to 'glm', but the gateway answers as
    'glm-5.2'. Once the run has pinned the observed id, the key must follow the pin."""
    from langatlas_pipeline.cache import cache_key

    prompt = load_prompt("capability-probe")
    messages = prompt.render()
    assert ctx.config.alias("glm").resolved_model == "glm"

    def key_under(model):
        return cache_key(endpoint="chat", resolved_model=model, messages=messages,
                         sampling={"temperature": 0.0}, schema_name=None,
                         prompt_ref=prompt.ref())

    fake = FakeClient([_response("pong")])
    client = CompletionClient(ctx, client=fake)
    client.complete("glm", messages, prompt=prompt)

    assert ctx.pinned_model("glm") == "glm-5.2"
    assert key_under("glm") != key_under("glm-5.2"), "sanity: the two ids key differently"
    assert ctx.cache.get(key_under("glm-5.2")) is not None, \
        "the entry is stored under the observed model id"
    assert ctx.cache.get(key_under("glm")) is None, \
        "nothing is stored under the (stale) configured id"

    again = client.complete("glm", messages, prompt=prompt)
    assert again.cache_hit is True, "the second read follows the pin and hits"
    assert len(fake.responses.requests) == 1


def test_a_stale_entry_under_the_configured_id_is_not_served_after_pinning(ctx):
    from langatlas_pipeline.cache import cache_key

    prompt = load_prompt("capability-probe")
    messages = prompt.render()
    stale_key = cache_key(endpoint="chat", resolved_model="glm", messages=messages,
                          sampling={"temperature": 0.0}, schema_name=None,
                          prompt_ref=prompt.ref())
    ctx.cache.put(stale_key, {"text": "STALE", "resolved_model": "glm",
                              "tokens_in": 1, "tokens_out": 1})
    ctx.pin_alias("glm", "glm-5.2")

    fake = FakeClient([_response("fresh")])
    result = CompletionClient(ctx, client=fake).complete("glm", messages, prompt=prompt)
    assert result.text == "fresh"
    assert result.cache_hit is False
