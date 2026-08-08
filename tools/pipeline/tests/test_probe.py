import json
import pytest
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_pipeline.observability.probe import (
    apply_probe, diff_capabilities, probe_alias, probe_all,
)

_yaml = YAML(typ="safe")

# Snapshot of config/provider_capabilities.yaml's unprobed shape as Task 1 first shipped it
# (commit 869084d), before the capability probe (Task 14) ever ran against it. Reading the
# live repo file here would be both semantically wrong (it's genuinely probed now, D41) and
# cwd-sensitive (a relative "config/..." path only resolves when pytest is invoked from the
# tools/pipeline directory) — so this test carries its own fixed starting-point content.
_UNPROBED_CAPABILITIES_SOURCE = """\
# Per-alias capability table (D41). NEVER hand-edited from guesses and never
# auto-committed: run `langatlas-probe` and commit its reviewed diff.
# `null` means "not probed yet" and is treated as unsupported until proven.
version: 1
probed_at: null
aliases:
  glm:
    resolved_model: null
    supports_json_schema: null
    supports_json_object: null
    reasoning_field: null
    max_input_tokens: 131072
    default_sampling: {temperature: 0.0}
  kimi:
    resolved_model: null
    supports_json_schema: null
    supports_json_object: null
    reasoning_field: null
    max_input_tokens: 131072
    default_sampling: {temperature: 0.0}
  deepseek:
    resolved_model: null
    supports_json_schema: null
    supports_json_object: null
    reasoning_field: null
    max_input_tokens: 131072
    default_sampling: {temperature: 0.0}
  deepseek-thinking:
    resolved_model: null
    supports_json_schema: null
    supports_json_object: null
    reasoning_field: inline-think     # <think>...</think> arrives in-band
    max_input_tokens: 131072
    default_sampling: {temperature: 0.0}
  mini:
    resolved_model: null
    supports_json_schema: null
    supports_json_object: null
    reasoning_field: null
    max_input_tokens: 32768
    default_sampling: {temperature: 0.0}
  coder:
    resolved_model: null
    supports_json_schema: null
    supports_json_object: null
    reasoning_field: null
    max_input_tokens: 131072
    default_sampling: {temperature: 0.0}
embeddings:
  qwen3-embedding-4b: {dimensions: 2560, max_input_tokens: 40960}
  nomic-embed-text-v1.5: {dimensions: 768, max_input_tokens: 8192}
  mxbai-embed-large: {dimensions: 1024, max_input_tokens: 512}
  multilingual-e5-large-instruct: {dimensions: 1024, max_input_tokens: 512}
rerankers:
  qwen3-reranker-4b: {mode: completion}
"""


class FakeGateway:
    """json_schema is rejected the way a gateway without guided decoding rejects it;
    json_object works."""

    def __init__(self, *, schema_ok: bool, model="glm-5.2"):
        self.schema_ok = schema_ok
        self.model = model
        self.chat = type("Chat", (), {"completions": self})()
        self.seen = []

    def create(self, **kwargs):
        self.seen.append(kwargs)
        fmt = (kwargs.get("response_format") or {}).get("type")
        if fmt == "json_schema" and not self.schema_ok:
            raise ValueError("response_format json_schema is not supported")
        return type("R", (), {
            "model": self.model,
            "choices": [type("C", (), {
                "message": type("M", (), {"content": json.dumps({"ok": True,
                                                                 "answer": "pong"})})(),
                "finish_reason": "stop"})()],
            "usage": type("U", (), {"prompt_tokens": 12, "completion_tokens": 8})(),
        })()


def test_probe_records_the_strongest_working_mode(ctx):
    result = probe_alias(ctx, "glm", client=FakeGateway(schema_ok=True))
    assert result["supports_json_schema"] is True
    assert result["supports_json_object"] is True
    assert result["resolved_model"] == "glm-5.2"


def test_probe_falls_back_when_json_schema_is_rejected(ctx):
    result = probe_alias(ctx, "glm", client=FakeGateway(schema_ok=False))
    assert result["supports_json_schema"] is False
    assert result["supports_json_object"] is True


def test_probe_all_covers_every_configured_alias(ctx):
    probed = probe_all(ctx, client=FakeGateway(schema_ok=True))
    assert set(probed["aliases"]) == set(ctx.config.capabilities["aliases"])
    assert probed["probed_at"]


def test_diff_reports_drift_and_silence_when_unchanged():
    current = {"aliases": {"glm": {"resolved_model": "glm-5.2",
                                   "supports_json_schema": True}}}
    same = {"aliases": {"glm": {"resolved_model": "glm-5.2",
                                "supports_json_schema": True}}}
    drifted = {"aliases": {"glm": {"resolved_model": "glm-5.3",
                                   "supports_json_schema": True}}}
    assert diff_capabilities(current, same) == []
    lines = diff_capabilities(current, drifted)
    assert len(lines) == 1
    assert "glm-5.2" in lines[0] and "glm-5.3" in lines[0]


def test_apply_probe_writes_the_table_and_preserves_comments(tmp_path: Path):
    target = tmp_path / "provider_capabilities.yaml"
    target.write_text(_UNPROBED_CAPABILITIES_SOURCE)
    apply_probe(target, {"probed_at": "2026-08-02T10:00:00Z",
                         "aliases": {"glm": {"resolved_model": "glm-5.2",
                                             "supports_json_schema": False,
                                             "supports_json_object": True,
                                             "reasoning_field": None,
                                             "max_input_tokens": 131072,
                                             "default_sampling": {"temperature": 0.0}}}})
    written = target.read_text()
    assert "NEVER hand-edited" in written, "ruamel round-trip keeps the warning comment"
    reloaded = _yaml.load(written)
    assert reloaded["aliases"]["glm"]["supports_json_object"] is True
    assert reloaded["probed_at"] == "2026-08-02T10:00:00Z"
    assert reloaded["aliases"]["kimi"]["resolved_model"] is None, "unprobed aliases survive"


def test_the_probe_is_budget_gated_and_counted(ctx):
    """Finding 3: complete_with_mode called the throttle directly, so the probe's own
    Budget(max_calls=...) was unenforceable and the run's stats reported zero calls."""
    from langatlas_pipeline.observability.probe import ProbeAnswer, _ProbeClient
    from langatlas_pipeline.prompts import load_prompt

    prompt = load_prompt("capability-probe")
    wrapper = _ProbeClient(ctx, client=FakeGateway(schema_ok=True))
    wrapper.complete_with_mode("glm", prompt.render(), prompt=prompt, schema=ProbeAnswer,
                               mode="json_object")
    assert ctx._calls == 1
    assert ctx._tokens == 20, "12 prompt + 8 completion tokens from the fake gateway"


def test_probe_alias_stops_at_the_budget_cap(workspace):
    from langatlas_pipeline.config import ProviderConfig
    from langatlas_pipeline.errors import BudgetExceeded
    from langatlas_pipeline.providers.core import Budget, RunContext

    run = RunContext.start(kind="probe", slug="budget", budget=Budget(max_calls=2),
                           config=ProviderConfig.load(),
                           transcripts_root=workspace["transcripts"],
                           private_dir=workspace["private"], no_cache=True)
    gateway = FakeGateway(schema_ok=True)
    try:
        # One call per alias (json_schema succeeding short-circuits the json_object
        # confirmation), so the third alias is the one that crosses the cap.
        with pytest.raises(BudgetExceeded) as excinfo:
            probe_all(run, client=gateway)
        assert excinfo.value.kind == "max_calls"
        assert len(gateway.seen) == 2, "the refused call never reached the gateway"
    finally:
        run.close()
