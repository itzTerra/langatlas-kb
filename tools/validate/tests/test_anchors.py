from langatlas_validate.compile import anchor_record_id, derive_facts
from langatlas_validate.store import iter_store_records


def _facts(root):
    return derive_facts(list(iter_store_records(root)))


def test_every_node_edge_and_rule_fact_carries_its_anchor(mini_store):
    mini_store.feature("alpha")
    mini_store.feature("beta")
    mini_store.concept("gamma")
    mini_store.edge("influences", "alpha", "beta", polarity="+")
    mini_store.quality_edge("alpha", "learnability", keys=("a-1", "a-2"))
    mini_store.rule("x", ["alpha", "beta"], then=["beta"])

    anchors = {fact["anchor"] for fact in _facts(mini_store.root)}

    assert anchors == {
        "alpha#summary", "beta#summary", "gamma#summary",
        "edge.influences.alpha.beta#exists", "edge.influences.alpha.beta#polarity",
        "edge.affects-quality.alpha.learnability#assessments[a-1]",
        "edge.affects-quality.alpha.learnability#assessments[a-2]",
        "rule-x#exists",
    }


def test_an_anchor_names_the_record_that_owns_the_fact(mini_store):
    mini_store.feature("alpha")
    mini_store.feature("beta")
    mini_store.edge("requires", "alpha", "beta")

    for fact in _facts(mini_store.root):
        record_id = anchor_record_id(fact["anchor"])
        assert record_id in fact["record_path"] or record_id.startswith("edge.")
    assert anchor_record_id("fi.rust.pattern-matching#characteristics[c-a]") == \
        "fi.rust.pattern-matching"
    assert anchor_record_id("edge.requires.alpha.beta#exists") == "edge.requires.alpha.beta"


def test_anchors_are_unique_across_the_store(mini_store):
    for node_id in ("alpha", "beta", "delta"):
        mini_store.feature(node_id)
    mini_store.edge("requires", "alpha", "beta")
    mini_store.edge("requires", "beta", "delta")

    anchors = [fact["anchor"] for fact in _facts(mini_store.root)]

    assert len(anchors) == len(set(anchors))
