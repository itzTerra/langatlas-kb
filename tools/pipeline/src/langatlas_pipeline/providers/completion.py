import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Any
from pydantic import BaseModel, ValidationError
from langatlas_pipeline.cache import cache_key
from langatlas_pipeline.errors import (
    ContextTooLarge, StructuredOutputError, UntrustedContentInSystemRole,
)
from langatlas_pipeline.injection import is_delimited
from langatlas_pipeline.providers.throttle import Throttle

_THINK = re.compile(r"<think>(.*?)</think>", re.S)
_CHARS_PER_TOKEN = 4
_ESTIMATE_MARGIN = 1.1


@dataclass(frozen=True)
class Sampling:
    """Temperature 0 by default, precisely so the cache is meaningful."""

    temperature: float = 0.0
    top_p: float | None = None
    seed: int | None = None
    max_tokens: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Completion:
    text: str
    parsed: BaseModel | None
    alias: str
    resolved_model: str
    tokens_in: int
    tokens_out: int
    cache_hit: bool
    latency_ms: int
    finish_reason: str | None
    reasoning: str | None = None


def estimate_tokens(messages: list[dict]) -> int:
    """Conservative chars/4 bound with a 10% margin. Deliberately approximate — the only
    decision it drives is 'refuse or proceed', and exact tokenization is out of scope."""
    chars = sum(len(str(m.get("content", ""))) for m in messages)
    return int(chars / _CHARS_PER_TOKEN * _ESTIMATE_MARGIN) + 1


def split_reasoning(text: str, reasoning_field: str | None) -> tuple[str, str | None]:
    """Reasoning models emit traces that must not reach the JSON parser — but D18 logs
    what the model actually said, so the trace is returned, not discarded."""
    if reasoning_field != "inline-think":
        return text, None
    match = _THINK.search(text)
    if not match:
        return text, None
    return _THINK.sub("", text, count=1), match.group(1).strip()


def build_client(config):
    """The whole 'provider abstraction' for transport: one openai SDK client with the
    base_url swapped and the gateway's non-standard auth header (D26)."""
    from openai import OpenAI

    settings = config.completion_settings()
    token = os.environ.get(settings["token_env"], "")
    return OpenAI(
        base_url=os.environ[settings["base_url_env"]],
        api_key=token or "unused",
        default_headers={settings["auth_header"]:
                         f"{settings['auth_scheme']} {token}"},
        timeout=settings.get("timeout_seconds", 900),
        max_retries=0,          # retries are the Throttle's job, so they get logged
    )


class CompletionClient:
    """University-API channel. No tool loop, ever (D26): retrieval reaches this channel
    only as runner-mediated results already injected into the messages."""

    def __init__(self, ctx, *, client=None, throttle: Throttle | None = None):
        self.ctx = ctx
        self._client = client
        settings = ctx.config.completion_settings()
        self.throttle = throttle or Throttle(
            min_interval=(settings.get("min_interval_seconds") or {}).get("chat", 0.5),
            max_attempts=settings.get("max_attempts", 5),
            circuit_breaker_failures=settings.get("circuit_breaker_failures", 5),
        )

    @property
    def client(self):
        if self._client is None:
            self._client = build_client(self.ctx.config)
        return self._client

    def complete(self, alias: str, messages: list[dict], *, prompt,
                 schema: type[BaseModel] | None = None,
                 sampling: Sampling | None = None) -> Completion:
        for message in messages:
            if message["role"] in ("system", "developer") and is_delimited(
                    str(message.get("content", ""))):
                raise UntrustedContentInSystemRole(
                    "fetched content may not occupy a system-role message (D31)")

        cap = self.ctx.config.alias(alias)
        sampling = sampling or Sampling(**cap.default_sampling)
        estimated = estimate_tokens(messages)
        if estimated > cap.max_input_tokens:
            raise ContextTooLarge(alias, estimated, cap.max_input_tokens)
        self.ctx.check_budget(calls=1, tokens=estimated)

        resolved_hint = cap.resolved_model or alias
        key = cache_key(endpoint="chat", resolved_model=resolved_hint, messages=messages,
                        sampling=sampling.as_dict(),
                        schema_name=schema.__name__ if schema else None,
                        prompt_ref=prompt.ref())
        if self.ctx.cache is not None:
            hit = self.ctx.cache.get(key)
            if hit is not None:
                return self._from_cache(hit, alias, prompt, messages, schema)

        mode = cap.structured_mode() if schema else None
        attempts = 0
        conversation = list(messages)
        last_text = ""
        while attempts < 3:
            attempts += 1
            started = time.monotonic()
            response = self.throttle.run(
                lambda: self.client.chat.completions.create(
                    model=alias, messages=conversation,
                    **self._structured_kwargs(mode, schema), **sampling.as_dict()))
            latency_ms = int((time.monotonic() - started) * 1000)
            resolved = getattr(response, "model", None) or resolved_hint
            self.ctx.pin_alias(alias, resolved)
            choice = response.choices[0]
            raw = choice.message.content or ""
            body, reasoning = split_reasoning(raw, cap.reasoning_field)
            last_text = body
            tokens_in = getattr(response.usage, "prompt_tokens", 0)
            tokens_out = getattr(response.usage, "completion_tokens", 0)
            self.ctx.note_usage(calls=1, tokens=tokens_in + tokens_out)

            parsed = None
            outcome = "ok"
            if schema is not None:
                try:
                    parsed = schema.model_validate_json(body.strip())
                except (ValidationError, ValueError) as exc:
                    outcome = "parse_failure"
                    self.ctx.recorder.record_call(
                        endpoint="chat", alias=alias, resolved_model=resolved,
                        messages=conversation, response_text=raw, tokens_in=tokens_in,
                        tokens_out=tokens_out, latency_ms=latency_ms, cache_hit=False,
                        outcome=outcome, prompt_id=prompt.prompt_id,
                        prompt_version=prompt.version)
                    if attempts == 1:
                        # one repair turn: hand the model its own error back
                        conversation = conversation + [
                            {"role": "assistant", "content": raw},
                            {"role": "user",
                             "content": f"That was not valid JSON for the required schema. "
                                        f"Repair it. Error: {exc}. Reply with JSON only."},
                        ]
                        continue
                    if attempts == 2:
                        conversation = list(messages)      # one clean retry
                        continue
                    break
                outcome = "repaired" if attempts > 1 else "ok"

            self.ctx.recorder.record_call(
                endpoint="chat", alias=alias, resolved_model=resolved,
                messages=conversation, response_text=raw, tokens_in=tokens_in,
                tokens_out=tokens_out, latency_ms=latency_ms, cache_hit=False,
                outcome=outcome, prompt_id=prompt.prompt_id,
                prompt_version=prompt.version)

            result = Completion(text=body, parsed=parsed, alias=alias,
                                resolved_model=resolved, tokens_in=tokens_in,
                                tokens_out=tokens_out, cache_hit=False,
                                latency_ms=latency_ms,
                                finish_reason=getattr(choice, "finish_reason", None),
                                reasoning=reasoning)
            if self.ctx.cache is not None:
                self.ctx.cache.put(key, {"text": body, "resolved_model": resolved,
                                         "tokens_in": tokens_in, "tokens_out": tokens_out,
                                         "reasoning": reasoning,
                                         "finish_reason": result.finish_reason})
            return result

        raise StructuredOutputError(alias, last_text, attempts)

    def _structured_kwargs(self, mode: str | None, schema) -> dict:
        if mode == "json_schema":
            return {"response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "strict": True,
                                "schema": schema.model_json_schema()}}}
        if mode == "json_object":
            return {"response_format": {"type": "json_object"}}
        return {}

    def _from_cache(self, hit: dict, alias, prompt, messages, schema) -> Completion:
        parsed = schema.model_validate_json(hit["text"]) if schema else None
        uncached = hit.get("tokens_in", 0) + hit.get("tokens_out", 0)
        self.ctx.recorder.record_call(
            endpoint="chat", alias=alias, resolved_model=hit["resolved_model"],
            messages=messages, response_text=hit["text"], tokens_in=0, tokens_out=0,
            latency_ms=0, cache_hit=True, outcome="ok", prompt_id=prompt.prompt_id,
            prompt_version=prompt.version, tokens_if_uncached=uncached)
        self.ctx.note_usage(calls=1)
        return Completion(text=hit["text"], parsed=parsed, alias=alias,
                          resolved_model=hit["resolved_model"], tokens_in=0, tokens_out=0,
                          cache_hit=True, latency_ms=0,
                          finish_reason=hit.get("finish_reason"),
                          reasoning=hit.get("reasoning"))
