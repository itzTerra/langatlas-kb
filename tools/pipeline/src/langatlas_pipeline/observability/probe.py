import argparse
from pathlib import Path
from typing import Any
from pydantic import BaseModel
from ruamel.yaml import YAML
from langatlas_pipeline.paths import CONFIG_DIR
from langatlas_pipeline.prompts import load_prompt
from langatlas_pipeline.providers.completion import CompletionClient
from langatlas_pipeline.providers.core import Budget, RunContext
from langatlas_pipeline.transcripts.writer import utc_now

_yaml = YAML()          # round-trip: the file's comments are load-bearing documentation
_yaml.preserve_quotes = True


class ProbeAnswer(BaseModel):
    ok: bool
    answer: str


def _try_mode(client_wrapper, alias: str, prompt, schema, mode: str) -> bool:
    """Force one structured-output mode and report whether the gateway honored it."""
    try:
        client_wrapper.complete_with_mode(alias, prompt.render(), prompt=prompt,
                                          schema=schema, mode=mode)
    except Exception:
        return False
    return True


def probe_alias(ctx: RunContext, alias: str, *, client=None) -> dict[str, Any]:
    """Probe one alias empirically (D26 ratified: json_schema support is undocumented,
    so it must be measured, per alias, against the running gateway)."""
    prompt = load_prompt("capability-probe")
    wrapper = _ProbeClient(ctx, client=client)
    cap = ctx.config.alias(alias)

    schema_ok = _try_mode(wrapper, alias, prompt, ProbeAnswer, "json_schema")
    object_ok = schema_ok or _try_mode(wrapper, alias, prompt, ProbeAnswer, "json_object")
    return {
        "resolved_model": wrapper.last_resolved_model or cap.resolved_model,
        "supports_json_schema": schema_ok,
        "supports_json_object": object_ok,
        "reasoning_field": cap.reasoning_field,
        "max_input_tokens": cap.max_input_tokens,
        "default_sampling": cap.default_sampling or {"temperature": 0.0},
    }


def probe_all(ctx: RunContext, *, client=None) -> dict[str, Any]:
    aliases = ctx.config.capabilities.get("aliases", {})
    return {"version": ctx.config.capabilities.get("version", 1),
            "probed_at": utc_now(),
            "aliases": {name: probe_alias(ctx, name, client=client) for name in aliases}}


def diff_capabilities(current: dict, probed: dict) -> list[str]:
    """Drift lines for developer review. Never applied automatically (D41)."""
    lines: list[str] = []
    for alias, probed_entry in probed.get("aliases", {}).items():
        current_entry = current.get("aliases", {}).get(alias, {})
        for key, value in probed_entry.items():
            if key in current_entry and current_entry[key] != value:
                lines.append(f"{alias}.{key}: {current_entry[key]!r} -> {value!r}")
    return lines


def apply_probe(path: Path, probed: dict) -> None:
    data = _yaml.load(path.read_text())
    data["probed_at"] = probed["probed_at"]
    for alias, entry in probed.get("aliases", {}).items():
        data.setdefault("aliases", {}).setdefault(alias, {}).update(entry)
    with path.open("w", encoding="utf-8") as fh:
        _yaml.dump(data, fh)


class _ProbeClient(CompletionClient):
    """CompletionClient that can be told which structured mode to use, instead of
    reading it from the (as yet unprobed) table."""

    last_resolved_model: str | None = None

    def complete_with_mode(self, alias, messages, *, prompt, schema, mode):
        response = self.throttle.run(
            lambda: self.client.chat.completions.create(
                model=alias, messages=messages, temperature=0.0,
                **self._structured_kwargs(mode, schema)))
        self.last_resolved_model = getattr(response, "model", None)
        schema.model_validate_json(response.choices[0].message.content)
        self.ctx.recorder.record_call(
            endpoint="chat", alias=alias, resolved_model=self.last_resolved_model,
            messages=messages, response_text=response.choices[0].message.content,
            tokens_in=getattr(response.usage, "prompt_tokens", 0),
            tokens_out=getattr(response.usage, "completion_tokens", 0),
            latency_ms=0, cache_hit=False, outcome="ok", prompt_id=prompt.prompt_id,
            prompt_version=prompt.version)
        return response


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-probe")
    parser.add_argument("--write", action="store_true",
                       help="apply the probe result to config/provider_capabilities.yaml")
    parser.add_argument("--config-dir", type=Path, default=CONFIG_DIR)
    args = parser.parse_args(argv)

    with RunContext.start(kind="probe", slug="capabilities",
                          budget=Budget(max_calls=50), no_cache=True) as ctx:
        probed = probe_all(ctx)
        drift = diff_capabilities(ctx.config.capabilities, probed)

    path = args.config_dir / "provider_capabilities.yaml"
    if not drift:
        print("no capability drift")
    for line in drift:
        print(f"drift: {line}")
    if args.write:
        apply_probe(path, probed)
        print(f"wrote {path} — review the diff and commit it deliberately")
        return 0
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
