import pytest
from ruamel.yaml import YAML

from langatlas_validate.compile import derive_facts
from langatlas_validate.migrate import MigrationError, apply_plan, plan_migration
from langatlas_validate.redirects import load_redirects, parse_redirects
from langatlas_validate.store import iter_store_records, validate_store

_safe = YAML(typ="safe")


def _manifest(*dispositions):
    return {"migration_id": "0001-test", "date": "2026-10-01", "cycle": 2,
            "ontology_version_before": "0.4.0", "rationale": "test",
            "dispositions": list(dispositions)}


def _entry(anchor, action, **extra):
    return {"match": {"anchor": anchor}, "action": action, **extra}


def _fact_ids(root):
    return {fact["anchor"]: fact["fact_id"]
            for fact in derive_facts(list(iter_store_records(root)))}


def _load(root, rel):
    return _safe.load((root / rel).read_text())


@pytest.fixture
def pair(mini_store):
    mini_store.feature("alpha", name="Alpha", aliases=("first letter",))
    mini_store.feature("gamma", name="Gamma", aliases=("Alpha",))
    mini_store.feature("beta")
    mini_store.edge("requires", "alpha", "beta")
    return mini_store


def _merge(*remap, frm=("alpha",), to="gamma"):
    return {"op": "merge", "from": list(frm), "to": to, "fact_remap": list(remap)}


def test_a_merge_folds_names_into_aliases_redirects_and_remaps(pair):
    before = _fact_ids(pair.root)

    plan = plan_migration(pair.root, _manifest(_merge(
        _entry("alpha#summary", "remap", target="gamma"),
        _entry("edge.requires.alpha.beta#*", "remap", target="gamma", reverify="fast-path"))))
    apply_plan(pair.root, plan)

    after = _fact_ids(pair.root)
    assert _load(pair.root, "features/gamma.yaml")["aliases"] == ["Alpha", "first letter"]
    assert load_redirects(pair.root) == {"alpha": "gamma"}
    assert not (pair.root / "features" / "alpha.yaml").exists()
    assert (pair.root / "edges" / "gamma" / "requires--beta.yaml").exists()
    dead = {entry["anchor"]: entry for entry in plan.tombstones}
    assert dead["alpha#summary"]["fact_id"] == before["alpha#summary"]
    assert dead["alpha#summary"]["superseded_by"] == [after["gamma#summary"]]
    assert dead["edge.requires.alpha.beta#exists"]["superseded_by"] == [
        after["edge.requires.gamma.beta#exists"]]
    assert all(entry["reason"] == "merge" for entry in plan.tombstones)
    assert validate_store(pair.root) == []


def test_a_remapped_edge_that_already_exists_dedupes_into_it(pair):
    pair.edge("requires", "gamma", "beta")
    existing = _fact_ids(pair.root)["edge.requires.gamma.beta#exists"]

    plan = plan_migration(pair.root, _manifest(_merge(
        _entry("edge.requires.alpha.beta#*", "remap", target="gamma"))))

    assert plan.changes["edges/alpha/requires--beta.yaml"] is None
    assert "edges/gamma/requires--beta.yaml" not in plan.changes
    moved = next(e for e in plan.tombstones if e["anchor"] == "edge.requires.alpha.beta#exists")
    assert moved["superseded_by"] == [existing]
    assert plan.gated == ()


def test_a_merge_whose_remap_flips_an_existing_edges_polarity_is_refused(pair):
    pair.feature("delta")
    pair.edge("influences", "delta", "alpha", polarity="+")
    pair.edge("influences", "delta", "gamma", polarity="-")

    with pytest.raises(MigrationError, match="polarity"):
        plan_migration(pair.root, _manifest(_merge(
            _entry("edge.influences.delta.alpha#*", "remap", target="gamma"),
            _entry("edge.requires.alpha.beta#*", "remap", target="gamma"))))


def test_a_merge_that_would_loop_an_edge_onto_itself_is_refused(pair):
    pair.edge("requires", "alpha", "gamma")

    with pytest.raises(MigrationError, match="itself"):
        plan_migration(pair.root, _manifest(_merge(
            _entry("edge.requires.alpha.*#*", "remap", target="gamma"))))


def test_redirects_that_pointed_at_a_merged_node_follow_it(pair):
    pair.write("ontology/redirects.yaml", "redirects:\n  old-alpha: alpha\n")

    plan = plan_migration(pair.root, _manifest(_merge(
        _entry("edge.requires.alpha.beta#*", "remap", target="gamma"))))

    assert parse_redirects(plan.changes["ontology/redirects.yaml"]) == {
        "alpha": "gamma", "old-alpha": "gamma"}


def test_a_concept_merge_repoints_realizes(mini_store):
    mini_store.concept("c-one")
    mini_store.concept("c-two")
    mini_store.feature("alpha", realizes=("c-one",))

    plan = plan_migration(mini_store.root, _manifest(_merge(
        _entry("c-one#summary", "remap", target="c-two"), frm=("c-one",), to="c-two")))
    apply_plan(mini_store.root, plan)

    assert _load(mini_store.root, "features/alpha.yaml")["realizes"] == ["c-two"]
    assert load_redirects(mini_store.root) == {"c-one": "c-two"}
    assert validate_store(mini_store.root) == []


def test_a_merge_across_kinds_is_refused(pair):
    pair.concept("c-one")

    with pytest.raises(MigrationError, match="not a concept"):
        plan_migration(pair.root, _manifest(_merge(frm=("alpha",), to="c-one")))


@pytest.fixture
def splittable(mini_store):
    for node_id in ("pattern-matching", "destructuring", "guards", "ownership"):
        mini_store.feature(node_id)
    mini_store.edge("enables", "ownership", "pattern-matching")
    return mini_store


def _split(*remap, old_node=None):
    disposition = {"op": "split", "from": "pattern-matching", "to": ["destructuring", "guards"],
                   "fact_remap": list(remap)}
    if old_node:
        disposition["old_node"] = old_node
    return disposition


_REQUEUE_EDGE = _entry("edge.enables.ownership.pattern-matching#*", "requeue",
                       reason="ambiguous-subject")


def test_a_split_demotes_the_node_to_a_concept_its_children_realize(splittable):
    before = _fact_ids(splittable.root)

    plan = plan_migration(splittable.root, _manifest(_split(_REQUEUE_EDGE)))
    apply_plan(splittable.root, plan)

    after = _fact_ids(splittable.root)
    root = splittable.root
    assert (root / "concepts" / "pattern-matching.yaml").exists()
    assert not (root / "features" / "pattern-matching.yaml").exists()
    assert after["pattern-matching#summary"] == before["pattern-matching#summary"]
    for child in ("destructuring", "guards"):
        assert _load(root, f"features/{child}.yaml")["realizes"] == ["pattern-matching"]
    assert [(e["anchor"], e["action"], e["reason"]) for e in plan.tombstones] == [
        ("edge.enables.ownership.pattern-matching#exists", "requeue", "split")]
    assert validate_store(root) == []


def test_a_tombstoning_split_remaps_its_definition_to_a_child(splittable):
    plan = plan_migration(splittable.root, _manifest(_split(
        _entry("pattern-matching#summary", "remap", target="guards"),
        _entry("edge.enables.ownership.pattern-matching#*", "remap", target="destructuring"),
        old_node="tombstone")))
    apply_plan(splittable.root, plan)

    after = _fact_ids(splittable.root)
    dead = {entry["anchor"]: entry for entry in plan.tombstones}
    assert dead["pattern-matching#summary"]["superseded_by"] == [after["guards#summary"]]
    assert (splittable.root / "edges" / "ownership" / "enables--destructuring.yaml").exists()
    assert not (splittable.root / "concepts" / "pattern-matching.yaml").exists()
    assert validate_store(splittable.root) == []


def test_a_demoting_split_keeps_its_definition(splittable):
    with pytest.raises(MigrationError, match="keeps its definition"):
        plan_migration(splittable.root, _manifest(_split(
            _entry("pattern-matching#summary", "tombstone"), _REQUEUE_EDGE)))


def test_a_split_child_must_be_a_committed_feature(splittable):
    splittable.concept("guard-concept")
    disposition = {**_split(_REQUEUE_EDGE), "to": ["destructuring", "guard-concept"]}

    with pytest.raises(MigrationError, match="not a feature"):
        plan_migration(splittable.root, _manifest(disposition))


def test_dispositions_apply_in_order(splittable):
    plan = plan_migration(splittable.root, _manifest(
        _split(_REQUEUE_EDGE),
        {"op": "move", "node": "guards", "to_layer": 1, "fact_remap": []}))

    assert _safe.load(plan.changes["features/guards.yaml"])["layer"] == 1
    assert _safe.load(plan.changes["features/guards.yaml"])["realizes"] == ["pattern-matching"]
