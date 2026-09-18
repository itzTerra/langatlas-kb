"""The compiled spec as a committed artifact, and the three ways a consumer reads it."""
from conftest import typing_store
from langatlas_questionnaire.compiler import compile_spec
from langatlas_questionnaire.spec import (
    diff_specs, instantiate, load_spec, render_spec, select, spec_rel, validate_spec,
    write_spec,
)


def test_a_compiled_spec_validates_and_round_trips(mini_store):
    root = typing_store(mini_store).root
    spec = compile_spec(root)
    assert validate_spec(spec) == []
    path = write_spec(spec, root)
    assert path == root / spec_rel("0.4.0") == root / "questionnaire" / "spec-0.4.0.yaml"
    assert load_spec(path) == spec
    assert path.read_text() == render_spec(spec)


def test_validate_spec_rejects_a_field_outside_the_fact_bearing_four(mini_store):
    spec = compile_spec(typing_store(mini_store).root)
    spec["groups"][0]["items"][0]["fields"] = ["exists", "since", "characteristics", "layer"]
    assert validate_spec(spec) != []


def test_select_keeps_only_the_theme_slice_and_the_constraints_that_touch_it(mini_store):
    store = typing_store(mini_store)
    store.edge("requires", "type-inference", "static-typing")
    store.edge("enables", "type-annotation", "type-inference")
    store.rule("annotated", ["type-annotation", "type-inference"], "warn", [])
    spec = select(compile_spec(store.root), {"static-typing"})
    assert [g["kind"] for g in spec["groups"]] == ["dimension"]
    assert [i["feature"] for i in spec["groups"][0]["items"]] == ["static-typing"]
    assert [c["id"] for c in spec["constraints"]] == [
        "edge.requires.type-inference.static-typing"]


def test_instantiate_substitutes_the_language_into_every_anchor(mini_store):
    items = instantiate(compile_spec(typing_store(mini_store).root), "python")
    assert {i["anchor_prefix"] for i in items} == {
        "fi.python.dynamic-typing", "fi.python.static-typing",
        "fi.python.type-annotation", "fi.python.type-inference"}
    dimensioned = next(i for i in items if i["feature"] == "static-typing")
    assert dimensioned["dimension"] == "type-checking-discipline"
    assert next(i for i in items if i["feature"] == "type-inference")["dimension"] is None


def test_instantiate_applies_the_d50_mask_and_nothing_else(mini_store):
    items = instantiate(compile_spec(typing_store(mini_store).root), "sql",
                        language_kind="domain-specific")
    assert sorted(i["feature"] for i in items) == ["type-annotation", "type-inference"]


def test_diff_reports_added_removed_and_changed_anchors_but_not_wording(mini_store):
    store = typing_store(mini_store)
    old = compile_spec(store.root)

    store.version("0.5.0")
    store.drop_feature("type-annotation")
    store.feature("gradual-typing", layer=3, dimension="type-checking-discipline")
    store.dimension("type-checking-discipline", exclusivity="multi",
                    label="Type checking discipline")
    store.feature("type-inference", layer=2, summary="Reworded: types are deduced.")
    store.edge("requires", "type-inference", "static-typing")
    new = compile_spec(store.root)

    diff = diff_specs(old, new)
    assert diff["from"] == "0.4.0" and diff["to"] == "0.5.0"
    assert diff["added"] == ["fi.<lang>.gradual-typing"]
    assert diff["removed"] == ["fi.<lang>.type-annotation"]
    assert diff["changed"] == ["fi.<lang>.dynamic-typing", "fi.<lang>.static-typing"]
    assert diff["constraints_added"] == ["edge.requires.type-inference.static-typing"]
    assert diff["constraints_removed"] == [] and diff["constraints_changed"] == []
