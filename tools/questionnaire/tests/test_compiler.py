"""D46's six mechanical steps, one behaviour per test."""
import pytest

from conftest import typing_store
from langatlas_questionnaire.compiler import LANG_PLACEHOLDER, CompileError, compile_spec
from langatlas_questionnaire.fields import FACT_FIELDS
from langatlas_validate.ids import compose_instance_id


def _items(spec):
    for group in spec["groups"]:
        if group["kind"] == "dimension":
            yield from group["items"]
        else:
            yield group


def test_member_features_group_under_their_dimension_with_its_context_once(mini_store):
    spec = compile_spec(typing_store(mini_store).root)
    group = spec["groups"][0]
    assert group["kind"] == "dimension"
    assert group["dimension"] == "type-checking-discipline"
    assert group["label"] == "Type checking discipline"
    assert group["exclusivity"] == "exclusive"
    assert group["applies_to"] == ["general-purpose"]
    assert "values" not in group                  # D67: the items are the values
    assert [item["feature"] for item in group["items"]] == ["dynamic-typing", "static-typing"]
    assert "exclusivity" not in group["items"][0]


def test_features_outside_a_dimension_are_standalone_items_ordered_by_layer(mini_store):
    spec = compile_spec(typing_store(mini_store).root)
    standalone = [g for g in spec["groups"] if g["kind"] == "standalone"]
    assert [(g["layer"], g["feature"]) for g in standalone] == [(1, "type-annotation"),
                                                               (2, "type-inference")]


def test_every_item_asks_exactly_the_four_fact_bearing_fields(mini_store):
    spec = compile_spec(typing_store(mini_store).root)
    assert tuple(FACT_FIELDS) == ("exists", "since", "characteristics", "syntax")
    assert {tuple(item["fields"]) for item in _items(spec)} == {tuple(FACT_FIELDS)}


def test_items_carry_ontology_context_and_nothing_ontology_authored(mini_store):
    spec = compile_spec(typing_store(mini_store).root)
    item = next(i for i in _items(spec) if i["feature"] == "dynamic-typing")
    assert set(item) == {"feature", "name", "layer", "summary", "aliases", "anchor_prefix",
                         "fields"}
    assert item["aliases"] == ["dynamic type checking"]
    assert item["summary"] == "dynamic-typing summary."


def test_anchor_prefix_instantiates_to_the_instance_anchor_scheme(mini_store):
    spec = compile_spec(typing_store(mini_store).root)
    item = next(i for i in _items(spec) if i["feature"] == "dynamic-typing")
    assert item["anchor_prefix"] == f"fi.{LANG_PLACEHOLDER}.dynamic-typing"
    assert item["anchor_prefix"].replace(LANG_PLACEHOLDER, "python") == compose_instance_id(
        "python", "dynamic-typing")


def test_hard_edges_and_rules_compile_to_constraints_never_to_items(mini_store):
    store = typing_store(mini_store)
    store.edge("requires", "type-inference", "static-typing")
    store.edge("conflicts-with", "dynamic-typing", "static-typing")
    store.rule("annotated-inference", ["type-annotation", "type-inference"], "requires",
               ["static-typing"])
    spec = compile_spec(store.root)
    assert spec["constraints"] == [
        {"kind": "conflicts-with", "id": "edge.conflicts-with.dynamic-typing.static-typing",
         "features": ["dynamic-typing", "static-typing"]},
        {"kind": "requires", "id": "edge.requires.type-inference.static-typing",
         "if_present": "type-inference", "then_present": "static-typing"},
        {"kind": "rule", "id": "rule-annotated-inference",
         "when_all": ["type-annotation", "type-inference"], "effect": "requires",
         "then": ["static-typing"]},
    ]
    assert len(list(_items(spec))) == 4


def test_soft_edges_compile_to_nothing(mini_store):
    store = typing_store(mini_store)
    store.edge("influences", "type-inference", "static-typing")
    store.edge("enables", "type-annotation", "type-inference")
    store.edge("alternative-to", "dynamic-typing", "static-typing")
    assert compile_spec(store.root)["constraints"] == []


def test_an_empty_or_single_member_dimension_is_a_diagnostic(mini_store):
    """D67: a dimension with fewer than two member features is not an axis yet. Reported, not
    refused — the ontologist is asked for >= 2 members, and R6 decides what to do."""
    store = typing_store(mini_store)
    store.dimension("inference-scope")
    store.dimension("memory-reclamation")
    store.feature("tracing-gc", layer=3, dimension="memory-reclamation")
    spec = compile_spec(store.root)
    assert spec["diagnostics"] == [
        {"kind": "dimension-without-features", "dimension": "inference-scope"},
        {"kind": "dimension-with-one-feature", "dimension": "memory-reclamation"}]
    assert all(g.get("dimension") != "inference-scope" for g in spec["groups"])
    assert any(g.get("dimension") == "memory-reclamation" for g in spec["groups"])


def test_the_spec_is_stamped_and_compiling_twice_gives_the_same_spec(mini_store):
    root = typing_store(mini_store).root
    first, second = compile_spec(root), compile_spec(root)
    assert first == second
    assert first["ontology_version"] == "0.4.0"
    assert first["compiler_version"] == "0.1.0"
    assert first["fields"] == {name: list(members) for name, members in FACT_FIELDS.items()}


def test_an_invalid_store_refuses_to_compile(mini_store):
    mini_store.feature("static-typing", layer=3, dimension="undeclared")
    with pytest.raises(CompileError, match="undeclared"):
        compile_spec(mini_store.root)
