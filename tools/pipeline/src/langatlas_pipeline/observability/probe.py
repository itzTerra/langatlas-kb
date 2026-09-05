import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from pydantic import BaseModel
from ruamel.yaml import YAML
from langatlas_pipeline.paths import CONFIG_DIR
from langatlas_pipeline.prompts import load_prompt
from langatlas_pipeline.errors import BudgetExceeded
from langatlas_pipeline.providers.completion import CompletionClient, estimate_tokens
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
    except BudgetExceeded:
        # A budget stop is a decision about the run, not evidence about the gateway —
        # swallowing it here would silently record "mode unsupported" for a call that
        # was never made.
        raise
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

    def _record_rejection(self, alias, messages, prompt, mode, detail, *,
                          tokens_in: int = 0, tokens_out: int = 0,
                          response_text: str | None = None) -> None:
        """A refused mode is still a call the gateway served and billed. Logging it under
        its own outcome keeps the run's budget and the public transcript honest about how
        many calls a probe made, and leaves the evidence for *why* a mode was recorded as
        unsupported in the transcript rather than only in the capability table."""
        self.ctx.recorder.record_call(
            endpoint="chat", alias=alias, resolved_model=self.last_resolved_model,
            messages=messages,
            response_text=response_text if response_text is not None
            else f"[{mode} rejected] {type(detail).__name__}: {detail}",
            tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=0, cache_hit=False,
            outcome="mode_rejected", prompt_id=prompt.prompt_id,
            prompt_version=prompt.version)

    def complete_with_mode(self, alias, messages, *, prompt, schema, mode):
        # The probe is a provider call like any other: it goes through the same budget
        # gate and the same usage accounting as CompletionClient.complete, otherwise the
        # probe run's own Budget(max_calls=...) is unenforceable and its manifest stats
        # report zero calls for a run that hit the gateway repeatedly.
        self.ctx.check_budget(calls=1, tokens=estimate_tokens(messages))
        try:
            response = self.throttle.run(
                lambda: self.client.chat.completions.create(
                    model=alias, messages=messages, temperature=0.0,
                    **self._structured_kwargs(mode, schema)))
        except BudgetExceeded:
            # Not a call: nothing was sent, so nothing is counted or logged.
            raise
        except Exception as exc:
            # Token counts are unknowable for a call that never returned a usage block;
            # the call itself is not, so it is counted.
            self.ctx.note_usage(calls=1)
            self._record_rejection(alias, messages, prompt, mode, exc)
            raise
        self.last_resolved_model = getattr(response, "model", None)
        tokens_in = getattr(response.usage, "prompt_tokens", 0)
        tokens_out = getattr(response.usage, "completion_tokens", 0)
        self.ctx.note_usage(calls=1, tokens=tokens_in + tokens_out)
        raw = response.choices[0].message.content
        try:
            schema.model_validate_json(raw)
        except Exception as exc:
            # The gateway accepted the mode and then ignored it — for probe purposes that
            # is the same verdict as an outright refusal, and just as much a real call.
            self._record_rejection(alias, messages, prompt, mode, exc, tokens_in=tokens_in,
                                   tokens_out=tokens_out, response_text=raw)
            raise
        self.ctx.recorder.record_call(
            endpoint="chat", alias=alias, resolved_model=self.last_resolved_model,
            messages=messages, response_text=raw,
            tokens_in=tokens_in, tokens_out=tokens_out,
            latency_ms=0, cache_hit=False, outcome="ok", prompt_id=prompt.prompt_id,
            prompt_version=prompt.version)
        return response


# A one-word input is enough to learn a vector's length, and keeps the probe's cost at
# a rounding error. It is deliberately not domain text: nothing about this call should
# depend on the corpus.
_PROBE_INPUT = "probe"
# The window the probe declares when the table has none. A model nobody has recorded yet
# is exactly the case the probe exists for, so the embed call must not route through the
# capability lookup and fail with UnknownAlias — which would be reported as "unreachable"
# and hide a perfectly working model.
_UNBOUNDED_WINDOW = 10 ** 9


@dataclass(frozen=True)
class EmbeddingProbe:
    """What one embedding model answered. `dimensions` is *measured* from the returned
    vector — the one fact a call can establish for free. `max_input_tokens` is never
    guessed: the gateway's model-info route, else the existing recorded entry, else
    None, which `apply_embedding_probe` refuses to write."""

    model: str
    dimensions: int | None
    max_input_tokens: int | None
    reachable: bool
    error: str | None = None

    def as_entry(self) -> dict:
        return {"dimensions": self.dimensions,
                "max_input_tokens": self.max_input_tokens}

    def complete(self) -> bool:
        return (self.reachable and self.dimensions is not None
                and self.max_input_tokens is not None)


def _recorded_window(ctx, model: str) -> int | None:
    entry = ctx.config.capabilities.get("embeddings", {}).get(model) or {}
    value = entry.get("max_input_tokens")
    return int(value) if value else None


def probe_embedding(ctx, model: str, *, client=None) -> EmbeddingProbe:
    """One embeddings call per model. Routed through `EmbeddingClient` so the probe is
    budgeted, throttled and logged exactly like production embedding traffic (D26/D18) —
    a probe that bypassed the policy core would be measuring a path nothing else uses."""
    from langatlas_pipeline.providers.embedding import EmbeddingClient

    window = _recorded_window(ctx, model)
    embedder = EmbeddingClient(ctx, client=client)
    try:
        vectors = embedder.embed([_PROBE_INPUT], model=model, truncate=True,
                                 max_input_tokens=window or _UNBOUNDED_WINDOW)
    except Exception as exc:                      # noqa: BLE001 - any failure is a verdict
        return EmbeddingProbe(model, None, window, False, f"{type(exc).__name__}: {exc}")
    return EmbeddingProbe(model, len(vectors[0]), window, True)


def probe_embeddings(ctx, models: Sequence[str] | None = None, *,
                     client=None) -> dict[str, EmbeddingProbe]:
    names = list(models) if models else list(ctx.config.capabilities.get("embeddings", {}))
    return {name: probe_embedding(ctx, name, client=client) for name in names}


def diff_embeddings(current: dict, probed: dict[str, EmbeddingProbe]) -> list[str]:
    """Drift lines for developer review, mirroring `diff_capabilities`. Never applied
    automatically (D41)."""
    lines: list[str] = []
    for model, probe in probed.items():
        entry = current.get("embeddings", {}).get(model)
        if entry is None:
            lines.append(f"{model}: new model, dimensions={probe.dimensions}"
                         f" max_input_tokens={probe.max_input_tokens}")
            continue
        for key, value in probe.as_entry().items():
            if value is not None and entry.get(key) != value:
                lines.append(f"{model}.{key}: {entry.get(key)!r} -> {value!r}")
    return lines


def apply_embedding_probe(path: Path, probed: dict[str, EmbeddingProbe]) -> list[str]:
    """Write only *complete* measurements. A model whose context window nobody has
    established is refused rather than defaulted: §8.6's honest-truncation clause is
    built on that number, so an invented one would corrupt the benchmark quietly."""
    data = _yaml.load(path.read_text())
    refused = [model for model, probe in probed.items() if not probe.complete()]
    for model, probe in probed.items():
        if probe.complete():
            data.setdefault("embeddings", {})[model] = probe.as_entry()
    with path.open("w", encoding="utf-8") as fh:
        _yaml.dump(data, fh)
    return sorted(refused)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-probe")
    parser.add_argument("--write", action="store_true",
                       help="apply the probe result to config/provider_capabilities.yaml")
    parser.add_argument("--embeddings", action="store_true",
                        help="probe the embedding roster (dimensions) instead of the"
                             " chat aliases")
    parser.add_argument("--model", action="append", default=[],
                        help="with --embeddings: probe this model (repeatable). Use it to"
                             " measure a candidate the table does not list yet.")
    parser.add_argument("--config-dir", type=Path, default=CONFIG_DIR)
    args = parser.parse_args(argv)
    path = args.config_dir / "provider_capabilities.yaml"

    if args.embeddings:
        with RunContext.start(kind="probe", slug="embeddings",
                              budget=Budget(max_calls=50), no_cache=True) as ctx:
            probed = probe_embeddings(ctx, args.model or None)
            drift = diff_embeddings(ctx.config.capabilities, probed)
        for line in drift or ["no embedding capability drift"]:
            print(f"drift: {line}" if drift else line)
        if args.write:
            refused = apply_embedding_probe(path, probed)
            print(f"wrote {path} — review the diff and commit it deliberately")
            for model in refused:
                probe = probed[model]
                print(f"REFUSED {model}: reachable={probe.reachable}"
                      f" max_input_tokens={probe.max_input_tokens};"
                      " add max_input_tokens from the model card and commit it by hand")
            return 0
        return 1 if drift else 0

    with RunContext.start(kind="probe", slug="capabilities",
                          budget=Budget(max_calls=50), no_cache=True) as ctx:
        probed_aliases = probe_all(ctx)
        drift = diff_capabilities(ctx.config.capabilities, probed_aliases)
    if not drift:
        print("no capability drift")
    for line in drift:
        print(f"drift: {line}")
    if args.write:
        apply_probe(path, probed_aliases)
        print(f"wrote {path} — review the diff and commit it deliberately")
        return 0
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
