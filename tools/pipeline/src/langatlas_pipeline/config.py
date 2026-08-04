from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from ruamel.yaml import YAML
from langatlas_pipeline.errors import UnknownAlias
from langatlas_pipeline.paths import CONFIG_DIR

_yaml = YAML(typ="safe")


@dataclass(frozen=True)
class AliasCapability:
    alias: str
    resolved_model: str | None
    supports_json_schema: bool | None
    supports_json_object: bool | None
    reasoning_field: str | None
    max_input_tokens: int
    default_sampling: dict[str, Any] = field(default_factory=dict)

    def structured_mode(self) -> Literal["json_schema", "json_object", "prompt"]:
        """Strongest structured-output mode this alias is *proven* to support.
        An unprobed (None) capability is never assumed — D41's table is evidence."""
        if self.supports_json_schema is True:
            return "json_schema"
        if self.supports_json_object is True:
            return "json_object"
        return "prompt"


@dataclass(frozen=True)
class EmbeddingCapability:
    model: str
    dimensions: int
    max_input_tokens: int


@dataclass(frozen=True)
class ProviderConfig:
    providers: dict[str, Any]
    capabilities: dict[str, Any]
    config_dir: Path

    @classmethod
    def load(cls, config_dir: Path | None = None) -> "ProviderConfig":
        config_dir = config_dir or CONFIG_DIR
        providers = _yaml.load((config_dir / "providers.yaml").read_text())
        capabilities = _yaml.load((config_dir / "provider_capabilities.yaml").read_text())
        return cls(providers=providers, capabilities=capabilities, config_dir=config_dir)

    def alias(self, name: str) -> AliasCapability:
        entry = self.capabilities.get("aliases", {}).get(name)
        if entry is None:
            raise UnknownAlias(f"unknown completion alias: {name!r}")
        return AliasCapability(
            alias=name,
            resolved_model=entry.get("resolved_model"),
            supports_json_schema=entry.get("supports_json_schema"),
            supports_json_object=entry.get("supports_json_object"),
            reasoning_field=entry.get("reasoning_field"),
            max_input_tokens=int(entry["max_input_tokens"]),
            default_sampling=dict(entry.get("default_sampling") or {}),
        )

    def embedding(self, model: str) -> EmbeddingCapability:
        entry = self.capabilities.get("embeddings", {}).get(model)
        if entry is None:
            raise UnknownAlias(f"unknown embedding model: {model!r}")
        return EmbeddingCapability(model, int(entry["dimensions"]),
                                   int(entry["max_input_tokens"]))

    def budget_defaults(self):
        from langatlas_pipeline.providers.core import Budget

        return Budget(**(self.providers.get("budget_defaults") or {}))

    def completion_settings(self) -> dict[str, Any]:
        return dict(self.providers.get("completion") or {})
