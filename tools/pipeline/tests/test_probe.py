import json
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_pipeline.observability.probe import (
    apply_probe, diff_capabilities, probe_alias, probe_all,
)

_yaml = YAML(typ="safe")


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
    source = Path("config/provider_capabilities.yaml").read_text()
    target = tmp_path / "provider_capabilities.yaml"
    target.write_text(source)
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
