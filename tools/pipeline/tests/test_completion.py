import json
import pytest
from pydantic import BaseModel
from langatlas_pipeline.errors import (
    ContextTooLarge, ProviderTransportError, StructuredOutputError,
    UntrustedContentInSystemRole,
)
from langatlas_pipeline.injection import delimit_untrusted
from langatlas_pipeline.prompts import load_prompt
from langatlas_pipeline.providers.completion import (
    CompletionClient, Sampling, estimate_tokens, split_reasoning,
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
    monkeypatch.setattr(ctx.config, "alias",
                        lambda name: type(cap)(**{**cap.__dict__,
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
    monkeypatch.setattr(ctx.config, "alias",
                        lambda name: type(cap)(**{**cap.__dict__,
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
