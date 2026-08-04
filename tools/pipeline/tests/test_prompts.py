import pytest
from pathlib import Path
from langatlas_pipeline.prompts import (
    PromptRef, list_versions, load_prompt, mint_prompt_version, version_hash,
)

BODY = """---
prompt_id: demo
variables: [claim, evidence]
---
# system
You judge entailment. Answer only "supported" or "unsupported".

# user
Claim: {{claim}}

Evidence:
{{evidence}}
"""


def test_version_hash_is_stable_8_hex():
    assert version_hash("abc") == version_hash("abc")
    assert version_hash("abc").startswith("v-")
    assert len(version_hash("abc")) == 10
    assert version_hash("abc") != version_hash("abd")


def test_mint_writes_a_content_addressed_file_and_changelog(tmp_path: Path):
    ref = mint_prompt_version("demo", BODY, note="first cut", root=tmp_path)
    assert ref.path == tmp_path / "demo" / f"{ref.version}.md"
    assert ref.path.exists()
    changelog = (tmp_path / "demo" / "CHANGELOG.md").read_text()
    assert ref.version in changelog
    assert "v1" in changelog
    assert "first cut" in changelog


def test_minting_identical_text_is_a_no_op(tmp_path: Path):
    first = mint_prompt_version("demo", BODY, root=tmp_path)
    second = mint_prompt_version("demo", BODY, root=tmp_path)
    assert first.version == second.version
    assert (tmp_path / "demo" / "CHANGELOG.md").read_text().count(first.version) == 1
    assert list_versions("demo", root=tmp_path) == [first.version]


def test_minting_new_text_adds_a_second_alias(tmp_path: Path):
    mint_prompt_version("demo", BODY, root=tmp_path)
    second = mint_prompt_version("demo", BODY + "\nBe terse.\n", note="terser", root=tmp_path)
    changelog = (tmp_path / "demo" / "CHANGELOG.md").read_text()
    assert "v2" in changelog
    assert load_prompt("demo", "latest", root=tmp_path).version == second.version
    assert load_prompt("demo", "v2", root=tmp_path).version == second.version
    assert load_prompt("demo", second.version, root=tmp_path).version == second.version


def test_render_produces_messages_in_declared_order(tmp_path: Path):
    ref = mint_prompt_version("demo", BODY, root=tmp_path)
    messages = ref.render(claim="Rust has ADTs", evidence="<fetched-source …>")
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "Rust has ADTs" in messages[1]["content"]
    assert "{{claim}}" not in messages[1]["content"]


def test_missing_or_unknown_variables_are_errors(tmp_path: Path):
    ref = mint_prompt_version("demo", BODY, root=tmp_path)
    with pytest.raises(KeyError):
        ref.render(claim="only one")
    with pytest.raises(KeyError):
        ref.render(claim="a", evidence="b", extra="c")


def test_ref_string_is_prompt_id_at_version(tmp_path: Path):
    ref = mint_prompt_version("demo", BODY, root=tmp_path)
    assert ref.ref() == f"demo@{ref.version}"


def test_shipped_prompts_load_and_declare_their_variables():
    probe = load_prompt("capability-probe")
    assert isinstance(probe, PromptRef)
    assert probe.render()[0]["role"] == "system"
    scorer = load_prompt("rerank-score")
    messages = scorer.render(query="ownership", documents="1. some text")
    assert "ownership" in messages[-1]["content"]
