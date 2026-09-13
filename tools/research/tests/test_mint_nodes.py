import pytest
from ruamel.yaml import YAML

from langatlas_research.drafts import ConceptDraft, Evidence, FeatureDraft, Proposer
from langatlas_research.errors import InvalidDraft, UnsourcedNode
from langatlas_research.mint import render_draft

yaml = YAML(typ="safe")

PROPOSER = Proposer(agent="ontologist", model="claude-opus-5", prompt_version="v1")
EVIDENCE = (Evidence(source="vanroy-haridi-2003", locator="p. 142",
                     quote="Pattern matching selects a clause by the shape of a value."),)


def _feature(**overrides) -> FeatureDraft:
    base = dict(id="pattern-matching", name="Pattern matching", layer=2,
                summary="Selection of a branch by the structural shape of a value.",
                evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0001")
    return FeatureDraft(**(base | overrides))


def test_a_feature_renders_to_its_spec_path_and_validates():
    minted = render_draft(_feature())

    assert minted.path == "features/pattern-matching.yaml"
    assert minted.kind == "feature"
    assert minted.node_ids == ("pattern-matching",)
    data = yaml.load(minted.text)
    assert data["slug"] == "pattern-matching"
    assert data["summary"]["sources"][0]["source"] == "vanroy-haridi-2003"
    assert data["provenance"]["claim_origin"] == "source-derived"
    assert data["provenance"]["chat_run_id"] == "r4-typing-0001"


def test_the_rendered_text_is_already_normalized():
    from langatlas_validate.normalize import normalize_record

    minted = render_draft(_feature())

    assert normalize_record(minted.text, "feature") == minted.text


def test_an_unsourced_node_is_refused():
    with pytest.raises(UnsourcedNode, match="pattern-matching"):
        render_draft(_feature(evidence=()))


def test_a_layer_three_feature_without_a_dimension_is_refused():
    with pytest.raises(InvalidDraft, match="dimension"):
        render_draft(_feature(layer=3))


def test_a_layer_three_feature_with_a_dimension_validates():
    minted = render_draft(_feature(layer=3, dimension="typing-discipline"))

    assert yaml.load(minted.text)["dimension"] == "typing-discipline"


def test_an_invalid_id_is_refused_before_the_schema_sees_it():
    with pytest.raises(InvalidDraft, match="slug"):
        render_draft(_feature(id="Pattern Matching"))


def test_a_concept_renders_with_its_excluded_rationale():
    minted = render_draft(ConceptDraft(
        id="scope", name="Scope", summary="The region of a program where a binding is visible.",
        evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0002",
        excluded_rationale="Staged as a Concept; atomizes into features through an ordinary split."))

    assert minted.path == "concepts/scope.yaml"
    assert "excluded_rationale" in yaml.load(minted.text)
