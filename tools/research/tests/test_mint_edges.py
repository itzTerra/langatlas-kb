import pytest
from ruamel.yaml import YAML

from langatlas_research.drafts import Assessment, EdgeDraft, Evidence, Proposer, QualityEdgeDraft, RuleDraft
from langatlas_research.errors import DegenerateRule, InvalidDraft, UnsourcedNode
from langatlas_research.mint import render_draft

yaml = YAML(typ="safe")

PROPOSER = Proposer(agent="edge-drafter", model="claude-opus-5", prompt_version="v1")
EVIDENCE = (Evidence(source="pierce-2002", locator="ch. 11"),)


def test_an_influences_edge_renders_to_its_sharded_path():
    minted = render_draft(EdgeDraft(
        type="influences", frm="algebraic-data-types", to="pattern-matching", polarity="+",
        statement="Algebraic data types make pattern matching worth having.",
        evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-adt-0001"))

    assert minted.path == "edges/algebraic-data-types/influences--pattern-matching.yaml"
    data = yaml.load(minted.text)
    assert data["id"] == "edge.influences.algebraic-data-types.pattern-matching"
    assert data["polarity"] == "+"
    assert minted.node_ids == ("edge.influences.algebraic-data-types.pattern-matching",)


def test_an_influences_edge_without_polarity_is_refused():
    with pytest.raises(InvalidDraft, match="polarity"):
        render_draft(EdgeDraft(
            type="influences", frm="a-feature", to="b-feature", statement="x.",
            evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r"))


def test_alternative_to_endpoints_are_canonically_ordered():
    minted = render_draft(EdgeDraft(
        type="alternative-to", frm="pattern-matching", to="algebraic-data-types",
        statement="Two ways of expressing the same selection.",
        evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r"))

    assert minted.path == "edges/algebraic-data-types/alternative-to--pattern-matching.yaml"
    assert yaml.load(minted.text)["from"] == "algebraic-data-types"


def test_a_quality_edge_carries_its_assessments():
    minted = render_draft(QualityEdgeDraft(
        frm="ownership", to="learnability", proposer=PROPOSER, chat_run_id="r",
        assessments=(Assessment(key="a-steep-onboarding", assessor=PROPOSER, polarity="hurts",
                                strength="moderate",
                                statement="Ownership raises the initial learning cost.",
                                evidence=EVIDENCE),)))

    assert minted.path == "edges/ownership/affects-quality--learnability.yaml"
    data = yaml.load(minted.text)
    assert data["type"] == "affects-quality"
    assert data["assessments"][0]["polarity"] == "hurts"


def test_a_rule_sorts_its_antecedents_and_keeps_then_in_authored_order():
    minted = render_draft(RuleDraft(
        slug="laziness-needs-purity", when_all=("lazy-evaluation", "algebraic-data-types"),
        effect="requires", then=("purity", "referential-transparency"),
        message="Lazy evaluation is only predictable under purity.",
        evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r"))

    data = yaml.load(minted.text)
    assert minted.path == "rules/rule-laziness-needs-purity.yaml"
    assert data["when_all"] == ["algebraic-data-types", "lazy-evaluation"]
    assert data["then"] == ["purity", "referential-transparency"]


def test_a_one_antecedent_rule_names_the_edge_type_it_belongs_in():
    with pytest.raises(DegenerateRule, match="requires"):
        render_draft(RuleDraft(
            slug="degenerate", when_all=("lazy-evaluation",), effect="requires",
            then=("purity",), message="x.", evidence=EVIDENCE, proposer=PROPOSER,
            chat_run_id="r"))


def test_an_unsourced_edge_is_refused():
    with pytest.raises(UnsourcedNode):
        render_draft(EdgeDraft(
            type="requires", frm="a-feature", to="b-feature", statement="x.",
            evidence=(), proposer=PROPOSER, chat_run_id="r"))
