import pytest
from ruamel.yaml import YAML

from langatlas_validate.compile import derive_facts
from langatlas_validate.migrate import (
    MigrationError, apply_plan, check_plan, iter_manifests, manifest_rel, match_anchor,
    plan_migration, render_manifest, validate_manifests,
)
from langatlas_validate.normalize import normalize_record
from langatlas_validate.schema import validate_record
from langatlas_validate.store import iter_store_records, validate_store
from langatlas_validate.tombstones import parse_tombstones

_safe = YAML(typ="safe")


def _manifest(*dispositions, migration_id="0001-test"):
    return {"migration_id": migration_id, "date": "2026-10-01", "cycle": 2,
            "ontology_version_before": "0.4.0", "rationale": "test",
            "dispositions": list(dispositions)}


def _entry(anchor, action, **extra):
    return {"match": {"anchor": anchor}, "action": action, **extra}


def _fact_ids(root):
    return {fact["anchor"]: fact["fact_id"]
            for fact in derive_facts(list(iter_store_records(root)))}


@pytest.fixture
def graph(mini_store):
    """alpha is referenced by one edge each way, a quality edge and a rule."""
    for node_id in ("alpha", "beta", "gamma"):
        mini_store.feature(node_id)
    mini_store.edge("requires", "alpha", "beta")
    mini_store.edge("influences", "gamma", "alpha", polarity="-")
    mini_store.quality_edge("alpha", "learnability")
    mini_store.rule("x", ["alpha", "gamma"], then=["gamma"])
    return mini_store


def _remove_alpha(overrides=None):
    """`remove alpha` with every dependent record tombstoned; `overrides` (anchor pattern ->
    entry, or None to drop that entry) adjusts one disposition at a time."""
    entries = {pattern: _entry(pattern, "tombstone") for pattern in (
        "edge.requires.alpha.beta#*", "edge.influences.gamma.alpha#*",
        "edge.affects-quality.alpha.learnability#*", "rule-x#exists")}
    entries.update(overrides or {})
    return _manifest({"op": "remove", "node": "alpha",
                      "fact_remap": [entry for entry in entries.values() if entry is not None]})


def test_the_schema_closes_the_action_vocabulary_and_requires_remap_targets():
    assert validate_record(_remove_alpha(), "migration-manifest") == []
    assert validate_record(_remove_alpha({"alpha#*": _entry("alpha#*", "vanish")}),
                           "migration-manifest")
    assert validate_record(_remove_alpha({"alpha#*": _entry("alpha#*", "remap")}),
                           "migration-manifest")


def test_render_orders_keys_and_validate_manifests_checks_the_directory(mini_store):
    text = render_manifest(_remove_alpha())
    mini_store.write(manifest_rel("0001-test"), text)
    mini_store.write("ontology/migrations/0002-wrong/manifest.yaml", text)

    errors = validate_manifests(mini_store.root)

    assert text.index("migration_id") < text.index("rationale") < text.index("dispositions")
    assert [rel for rel, _m in iter_manifests(mini_store.root)] == [
        "ontology/migrations/0001-test/manifest.yaml",
        "ontology/migrations/0002-wrong/manifest.yaml"]
    assert any("0002-wrong" in e and "directory name" in e for e in errors)
    assert any("duplicate" in e for e in errors)


def test_validate_store_schema_checks_committed_manifests(mini_store):
    mini_store.write(manifest_rel("0001-test"),
                     render_manifest(_remove_alpha({"x": _entry("x", "vanish")})))

    assert any(e.startswith("ontology/migrations/0001-test") for e in validate_store(mini_store.root))


def test_matchers_glob_on_star_and_treat_brackets_literally():
    assert match_anchor("edge.affects-quality.alpha.learnability#assessments[*]",
                        "edge.affects-quality.alpha.learnability#assessments[a-1]")
    assert match_anchor("alpha#*", "alpha#summary")
    assert not match_anchor("alpha#summary", "alphabet#summary")
    assert not match_anchor("edge.*.alpha.beta#[e]xists", "edge.requires.alpha.beta#exists")


def test_removing_a_node_disposes_of_every_record_that_points_at_it(graph):
    before = _fact_ids(graph.root)
    manifest = _remove_alpha({"edge.influences.gamma.alpha#*":
                              _entry("edge.influences.gamma.alpha#*", "requeue")})

    plan = plan_migration(graph.root, manifest)

    for rel in ("features/alpha.yaml", "edges/alpha/requires--beta.yaml",
                "edges/gamma/influences--alpha.yaml", "edges/alpha/affects-quality--learnability.yaml",
                "rules/rule-x.yaml"):
        assert plan.changes[rel] is None
    dead = {entry["anchor"]: entry for entry in plan.tombstones}
    assert set(dead) == {
        "alpha#summary", "edge.requires.alpha.beta#exists", "edge.influences.gamma.alpha#exists",
        "edge.influences.gamma.alpha#polarity",
        "edge.affects-quality.alpha.learnability#assessments[a-1]", "rule-x#exists"}
    assert dead["alpha#summary"]["action"] == "tombstone"   # implicit: the node is gone
    assert dead["edge.influences.gamma.alpha#polarity"]["action"] == "requeue"
    assert all(entry["reason"] == "removal" and entry["superseded_by"] == []
               for entry in plan.tombstones)
    assert all(entry["fact_id"] == before[entry["anchor"]] for entry in plan.tombstones)
    assert all(entry["migration_id"] == "0001-test" and entry["date"] == "2026-10-01"
               for entry in plan.tombstones)
    assert parse_tombstones(plan.changes["tombstones.yaml"]) == list(plan.tombstones)
    assert check_plan(graph.root, plan) == []


def test_planning_writes_nothing(graph):
    text = (graph.root / "features" / "alpha.yaml").read_text()

    plan_migration(graph.root, _remove_alpha())

    assert (graph.root / "features" / "alpha.yaml").read_text() == text


def test_a_remapped_edge_moves_and_its_old_facts_point_at_the_new_ones(graph):
    plan = plan_migration(graph.root, _remove_alpha({
        "alpha#summary": _entry("alpha#summary", "remap", target="beta"),
        "edge.requires.alpha.beta#*": _entry("edge.requires.alpha.beta#*", "remap",
                                             target="gamma", reverify="full")}))
    apply_plan(graph.root, plan)

    after = _fact_ids(graph.root)
    dead = {entry["anchor"]: entry for entry in plan.tombstones}
    assert dead["edge.requires.alpha.beta#exists"]["superseded_by"] == [
        after["edge.requires.gamma.beta#exists"]]
    assert dead["alpha#summary"]["superseded_by"] == [after["beta#summary"]]
    assert plan.gated == ("edges/gamma/requires--beta.yaml",)
    assert {"alpha", "edge.requires.alpha.beta", "edge.requires.gamma.beta"} <= set(plan.touched)
    assert validate_store(graph.root) == []


def test_a_rule_remap_keeps_its_fact_identity_and_is_still_gated(graph):
    graph.feature("delta")

    plan = plan_migration(graph.root, _remove_alpha(
        {"rule-x#exists": _entry("rule-x#exists", "remap", target="delta")}))

    assert "rule-x#exists" not in {entry["anchor"] for entry in plan.tombstones}
    assert "rules/rule-x.yaml" in plan.gated and "rule-x" in plan.touched
    assert _safe.load(plan.changes["rules/rule-x.yaml"])["when_all"] == ["delta", "gamma"]


@pytest.mark.parametrize("overrides, message", [
    ({"nope#*": _entry("nope#*", "tombstone")}, "zero anchors"),
    ({"beta#summary": _entry("beta#summary", "tombstone")}, "does not touch"),
    ({"edge.requires.alpha.beta#*": None}, "still points at"),
    ({"alpha#summary": _entry("alpha#summary", "requeue")}, "remapped to a surviving node"),
    ({"alpha#summary": _entry("alpha#summary", "remap", target="nowhere")}, "not a surviving"),
    ({"rule-x#exists": _entry("rule-x#exists", "remap", target="gamma")}, "D64"),
    ({"edge.requires.alpha.beta#*": _entry("edge.requires.alpha.beta#*", "remap",
                                           target="learnability")}, "surviving committed feature"),
    ({"edge.influences.gamma.alpha#*": None,
      "edge.influences.gamma.alpha#exists": _entry("edge.influences.gamma.alpha#exists",
                                                   "tombstone"),
      "edge.influences.gamma.alpha#polarity": _entry("edge.influences.gamma.alpha#polarity",
                                                     "requeue")}, "different dispositions"),
])
def test_the_interpreter_refuses_with_a_message(graph, overrides, message):
    with pytest.raises(MigrationError, match=message):
        plan_migration(graph.root, _remove_alpha(overrides))


def test_a_feature_instance_blocks_the_migration(graph):
    graph.write("languages/_registry.yaml", "languages:\n  rust:\n    name: Rust\n")
    graph.write("languages/rust/instances/alpha.yaml", normalize_record(
        "feature: alpha\nlanguage: rust\nstatus: present\nsince:\n  value: '1.0'\n"
        "  sources:\n    - source: s\n      locator: p. 1\n"
        "provenance:\n  claim_origin: source-derived\n", "feature-instance"))

    with pytest.raises(MigrationError, match="FeatureInstance"):
        plan_migration(graph.root, _remove_alpha())


def test_a_move_rewrites_classification_and_retires_no_fact(graph):
    plan = plan_migration(graph.root, _manifest(
        {"op": "move", "node": "beta", "to_layer": 3, "to_dimension": "typing-discipline",
         "fact_remap": []}))

    assert set(plan.changes) == {"features/beta.yaml"}
    moved = _safe.load(plan.changes["features/beta.yaml"])
    assert (moved["layer"], moved["dimension"]) == (3, "typing-discipline")
    assert plan.tombstones == () and plan.gated == ()
    assert check_plan(graph.root, plan) == []


@pytest.mark.parametrize("move, message", [
    ({"to_layer": 3, "to_dimension": "nominality"}, "declared dimension"),
    ({"to_layer": 1, "to_dimension": "typing-discipline"}, "only a layer-3"),
    ({"to_layer": 3, "to_dimension": "typing-discipline",
      "fact_remap": [_entry("beta#summary", "untouched")]}, "must be empty"),
])
def test_a_malformed_move_is_refused(graph, move, message):
    disposition = {"op": "move", "node": "beta", "fact_remap": [], **move}

    with pytest.raises(MigrationError, match=message):
        plan_migration(graph.root, _manifest(disposition))


@pytest.mark.parametrize("text, message", [
    ("- a\n- b\n", "must be a mapping"),
    ("just a string\n", "must be a mapping"),
    ("a: [unclosed\n", "not valid YAML"),
    ("migration_id: [1, 2]\ndate: x\n", "migration_id"),
])
def test_malformed_manifest_files_are_error_strings_not_tracebacks(mini_store, text, message):
    mini_store.write("ontology/migrations/0001-bad/manifest.yaml", text)

    errors = validate_manifests(mini_store.root)

    assert any("0001-bad" in e and message in e for e in errors)
    assert any("0001-bad" in e for e in validate_store(mini_store.root))


def test_plan_migration_refuses_a_non_mapping_manifest(graph):
    with pytest.raises(MigrationError, match="must be a mapping"):
        plan_migration(graph.root, ["not", "a", "mapping"])


@pytest.mark.parametrize("bad", ["../evil", "0001-Test", "x", "0001-a/../b"])
def test_manifest_rel_rejects_ids_outside_the_schema_pattern(bad):
    with pytest.raises(MigrationError, match="schema pattern"):
        manifest_rel(bad)


def test_a_same_polarity_collision_dedupes_onto_the_survivors_facts(graph):
    graph.edge("requires", "gamma", "beta")

    plan = plan_migration(graph.root, _remove_alpha({
        "edge.requires.alpha.beta#*": _entry("edge.requires.alpha.beta#*", "remap",
                                             target="gamma")}))
    apply_plan(graph.root, plan)

    survivor = _fact_ids(graph.root)["edge.requires.gamma.beta#exists"]
    dead = {entry["anchor"]: entry for entry in plan.tombstones}
    assert dead["edge.requires.alpha.beta#exists"]["superseded_by"] == [survivor]
    assert plan.gated == ()
    assert validate_store(graph.root) == []


def test_a_polarity_conflicting_collision_is_refused(graph):
    graph.feature("delta")
    graph.edge("influences", "delta", "alpha", polarity="+")
    graph.edge("influences", "delta", "gamma", polarity="-")
    disposition = _remove_alpha({
        "edge.influences.gamma.alpha#*": _entry("edge.influences.gamma.alpha#*", "tombstone"),
        "edge.influences.delta.alpha#*": _entry("edge.influences.delta.alpha#*", "remap",
                                                target="gamma")})

    with pytest.raises(MigrationError, match="polarity"):
        plan_migration(graph.root, disposition)


def test_a_quality_edge_remaps_onto_the_surviving_feature(graph):
    plan = plan_migration(graph.root, _remove_alpha({
        "edge.affects-quality.alpha.learnability#*":
            _entry("edge.affects-quality.alpha.learnability#*", "remap", target="gamma")}))
    apply_plan(graph.root, plan)

    after = _fact_ids(graph.root)
    dead = {entry["anchor"]: entry for entry in plan.tombstones}
    assert dead["edge.affects-quality.alpha.learnability#assessments[a-1]"]["superseded_by"] == [
        after["edge.affects-quality.gamma.learnability#assessments[a-1]"]]
    assert "edges/gamma/affects-quality--learnability.yaml" in plan.gated
    assert validate_store(graph.root) == []
