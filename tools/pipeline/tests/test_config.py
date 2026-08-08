import shutil
from pathlib import Path

import pytest
from langatlas_pipeline.config import ProviderConfig
from langatlas_pipeline.errors import UnknownAlias
from langatlas_pipeline.paths import CONFIG_DIR

# Snapshot of the alias table's shape as Task 1 first shipped it (commit 869084d), before
# the capability probe (Task 14) ever ran. The live config/provider_capabilities.yaml is
# real, probed data now, so "unprobed" tests must not read it off disk (D41) — this
# fixture is the frozen "not probed yet" shape instead.
_UNPROBED_CAPABILITIES_YAML = """\
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
"""


def test_loads_every_d6_alias():
    cfg = ProviderConfig.load()
    for alias in ("glm", "kimi", "deepseek", "deepseek-thinking", "mini", "coder"):
        assert cfg.alias(alias).max_input_tokens > 0


def test_unprobed_alias_is_not_assumed_to_support_json_schema(tmp_path: Path):
    shutil.copy(CONFIG_DIR / "providers.yaml", tmp_path / "providers.yaml")
    (tmp_path / "provider_capabilities.yaml").write_text(_UNPROBED_CAPABILITIES_YAML)
    cfg = ProviderConfig.load(config_dir=tmp_path)
    cap = cfg.alias("glm")
    assert cap.supports_json_schema is None
    assert cap.structured_mode() == "prompt"


def test_probed_capabilities_pick_the_strongest_mode():
    from langatlas_pipeline.config import AliasCapability

    schema = AliasCapability("x", "m", True, True, None, 1000, {})
    obj = AliasCapability("x", "m", False, True, None, 1000, {})
    none = AliasCapability("x", "m", False, False, None, 1000, {})
    assert schema.structured_mode() == "json_schema"
    assert obj.structured_mode() == "json_object"
    assert none.structured_mode() == "prompt"


def test_unknown_alias_raises():
    with pytest.raises(UnknownAlias):
        ProviderConfig.load().alias("gpt-9")


def test_budget_defaults_come_from_providers_yaml():
    budget = ProviderConfig.load().budget_defaults()
    assert budget.max_calls == 500
    assert budget.max_claude_messages == 400


def test_reasoning_alias_declares_its_reasoning_field():
    assert ProviderConfig.load().alias("deepseek-thinking").reasoning_field == "inline-think"
