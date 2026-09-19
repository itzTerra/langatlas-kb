from langatlas_ingest.verify.verdicts import PairVerdict
from langatlas_coverage.metrics import (
    dimension_members, fact_verification, feature_degrees, instance_counts, load_store,
)


def _typing_store(store):
    store.feature("static-typing", layer=3, dimension="typing-discipline")
    store.feature("dynamic-typing", layer=3, dimension="typing-discipline")
    store.feature("type-inference")
    store.concept("type-system")
    store.edge("requires", "type-inference", "static-typing")
    store.instance("haskell", "static-typing")
    store.instance("python", "static-typing", status="absent")
    store.instance("python", "dynamic-typing")
    return load_store(store.root)


def test_the_store_is_read_once_and_keyed_by_id(coverage_store):
    store = _typing_store(coverage_store)

    assert set(store.features) == {"static-typing", "dynamic-typing", "type-inference"}
    assert set(store.concepts) == {"type-system"}
    assert set(store.edges) == {"edge.requires.type-inference.static-typing"}
    assert set(store.instances) == {"fi.haskell.static-typing", "fi.python.static-typing",
                                    "fi.python.dynamic-typing"}
    assert set(store.nodes) == {"static-typing", "dynamic-typing", "type-inference",
                                "type-system"}


def test_instance_counts_cover_every_feature(coverage_store):
    counts = instance_counts(_typing_store(coverage_store))

    assert counts["static-typing"] == {"present": 1, "partial": 0, "absent": 1}
    assert counts["type-inference"] == {"present": 0, "partial": 0, "absent": 0}


def test_a_dimensions_values_are_its_member_features(coverage_store):
    members = dimension_members(_typing_store(coverage_store))

    assert members == {"typing-discipline": ["dynamic-typing", "static-typing"],
                       "evaluation-strategy": []}


def test_degrees_count_feature_edges(coverage_store):
    degrees = feature_degrees(_typing_store(coverage_store))

    assert degrees == {"static-typing": 1, "dynamic-typing": 0, "type-inference": 1}


class _Ledger:
    def __init__(self, verdicts):
        self.verdicts = verdicts

    def latest_for(self, fact_id):
        return self.verdicts.get(fact_id, [])


def test_fact_verification_folds_the_ledger(coverage_store):
    store = _typing_store(coverage_store)
    fact = next(f for f in store.facts if f["anchor"] == "static-typing#summary")
    source = type("S", (), {"tier": "A"})()
    ledger = _Ledger({fact["fact_id"]: [PairVerdict(fact_id=fact["fact_id"], source_id="s",
                                                    locator="p. 1", verdict="supported")]})

    verification = fact_verification(store.facts, ledger=ledger, source_facts={"s": source})

    assert verification[fact["fact_id"]] == "verified"
    other = next(f for f in store.facts if f["anchor"] == "dynamic-typing#summary")
    assert verification[other["fact_id"]] == "unverified"
