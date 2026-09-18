"""The store gate's rules for a machine-written block: it may say a level and name machine
references, and it may say nothing else."""
import pytest

from langatlas_validate.schema import validate_record
from langatlas_validate.store import validate_controversy_blocks
from langatlas_validate.version import classify_change

GOOD = {"key": "summary", "fact_id": "f-aaaaaaaaaaaa", "level": 2,
        "signals": ["debate:d-01-typing-003:standing-dissent", "verdict:partial:since"],
        "assessed": {"date": "2026-09-17", "model": "deepseek-v4-pro-thinking",
                     "prompt": "controversy-assessor@v-1a2b3c4d", "run_id": "r-1",
                     "escalated_to": "claude"}}


def _feature(**overrides):
    data = {"id": "structural-typing", "slug": "structural-typing", "name": "Structural typing",
            "layer": 2, "summary": {"text": "t", "sources": [{"source": "s", "locator": "p. 1"}]},
            "provenance": {"claim_origin": "source-derived"}}
    data.update(overrides)
    return data


def test_a_well_formed_block_validates():
    assert validate_record(_feature(controversy=[GOOD]), "feature") == []


def test_a_free_prose_rationale_is_rejected_by_the_schema():
    """§6.4: the signals list *is* the justification. A rationale field would be an
    agent-written explanation nobody can check."""
    bad = {**GOOD, "rationale": "the sources plainly disagree"}
    assert validate_record(_feature(controversy=[bad]), "feature") != []


def test_level_4_is_rejected():
    assert validate_record(_feature(controversy=[{**GOOD, "level": 4}]), "feature") != []


def test_a_level_0_entry_is_refused_by_the_store_gate():
    """An absent block means level 0 (§6.4), so a stored 0 is a second way to say the same
    thing — and two encodings of "settled" is how a site ends up rendering one of them wrong."""
    errors = validate_controversy_blocks(
        [("features/structural-typing.yaml", "feature", _feature(controversy=[{**GOOD, "level": 0}]),
          ["f-aaaaaaaaaaaa"])])
    assert any("level 0" in e for e in errors)


def test_a_signal_outside_the_grammar_is_refused():
    bad = {**GOOD, "signals": ["the type theorist objected"]}
    errors = validate_controversy_blocks(
        [("features/structural-typing.yaml", "feature", _feature(controversy=[bad]),
          ["f-aaaaaaaaaaaa"])])
    assert any("not a machine reference" in e for e in errors)


def test_a_block_naming_a_fact_the_record_does_not_derive_is_refused():
    errors = validate_controversy_blocks(
        [("features/structural-typing.yaml", "feature", _feature(controversy=[GOOD]),
          ["f-999999999999"])])
    assert any("does not derive" in e for e in errors)


def test_a_controversy_only_edit_is_not_an_ontology_change():
    """The nightly batch must not bump `ontology/VERSION`. A machine annotation is not an
    ontology change; classifying it as `additive` would bump MINOR every night."""
    before = {"features/structural-typing.yaml": _feature()}
    after = {"features/structural-typing.yaml": _feature(controversy=[GOOD])}
    assert classify_change(before, after) == "none"


def test_a_real_edit_alongside_a_block_is_still_classified():
    before = {"features/structural-typing.yaml": _feature()}
    after = {"features/structural-typing.yaml": _feature(controversy=[GOOD], layer=3,
                                                         dimension="typing-discipline")}
    assert classify_change(before, after) == "restructuring"
