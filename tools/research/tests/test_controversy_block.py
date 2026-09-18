"""The writer side: merging assessments into a record without disturbing anything else."""
import pytest
from ruamel.yaml import YAML

from langatlas_research.controversy.assessor import Assessment
from langatlas_research.controversy.block import block_entries, controversy_mint, merge_block

_yaml = YAML(typ="safe")

FEATURE = {"id": "structural-typing", "slug": "structural-typing",
           "name": "Structural typing", "layer": 2,
           "summary": {"text": "t", "sources": [{"source": "pierce-tapl-2002",
                                                 "locator": "p. 251"}]},
           "provenance": {"claim_origin": "source-derived"}}


def _assessment(level, signals=(), fact_id="f-aaaaaaaaaaaa"):
    return Assessment(fact_id=fact_id, level=level, signals=tuple(signals),
                      model="deepseek-v4-pro-thinking", prompt="controversy-assessor@v-1a2b3c4d",
                      run_id="r-1")


def test_a_level_0_assessment_writes_no_entry():
    merged = merge_block(FEATURE, {"summary": _assessment(0)}, date="2026-09-17")
    assert "controversy" not in merged


def test_a_level_0_assessment_removes_a_stale_entry():
    """A fact that stopped being contested must lose its block, or the site keeps rendering a
    dispute that resolved."""
    existing = {**FEATURE, "controversy": [{"key": "summary", "fact_id": "f-aaaaaaaaaaaa",
                                            "level": 2, "signals": [], "assessed": {}}]}
    merged = merge_block(existing, {"summary": _assessment(0)}, date="2026-09-17")
    assert "controversy" not in merged


def test_an_entry_carries_the_signals_and_the_assessed_stamp():
    merged = merge_block(FEATURE, {"summary": _assessment(2, ["verdict:partial:since"])},
                         date="2026-09-17")
    entry, = merged["controversy"]
    assert entry["key"] == "summary"
    assert entry["level"] == 2
    assert entry["signals"] == ["verdict:partial:since"]
    assert entry["assessed"]["date"] == "2026-09-17"
    assert entry["assessed"]["prompt"] == "controversy-assessor@v-1a2b3c4d"


def test_entries_for_other_facts_are_left_alone():
    """A record's facts are assessed together, but a budget stop can still leave one
    unassessed — and an untouched fact must keep the level it already had."""
    existing = {**FEATURE, "controversy": [
        {"key": "characteristics[c-width]", "fact_id": "f-bbbbbbbbbbbb", "level": 3,
         "signals": ["verdict:contradicted:base"], "assessed": {"date": "2026-09-01",
                                                                "model": "m", "prompt": "p",
                                                                "run_id": "r"}}]}
    merged = merge_block(existing, {"summary": _assessment(1, ["debate:d-01-typing-003:resolved"])},
                         date="2026-09-17")
    assert [e["key"] for e in merged["controversy"]] == ["characteristics[c-width]", "summary"]


def test_the_mint_renders_normalized_yaml_with_the_block_at_the_tail(tmp_path):
    minted = controversy_mint("features/structural-typing.yaml",
                              merge_block(FEATURE, {"summary": _assessment(2, [])},
                                          date="2026-09-17"),
                              kind="feature", base_text="")
    assert minted.path == "features/structural-typing.yaml"
    assert minted.text.rstrip().endswith("run_id: r-1")
    assert list(_yaml.load(minted.text)) [-1] == "controversy"
