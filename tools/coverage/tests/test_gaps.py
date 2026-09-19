from langatlas_coverage.gaps import gaps, render_gaps
from langatlas_coverage.metrics import load_store


def test_each_dimension_value_is_counted_and_thin_ones_flagged(coverage_store):
    coverage_store.feature("static-typing", layer=3, dimension="typing-discipline")
    coverage_store.feature("dynamic-typing", layer=3, dimension="typing-discipline")
    coverage_store.instance("haskell", "static-typing")
    coverage_store.instance("python", "static-typing")
    coverage_store.instance("python", "dynamic-typing", status="absent")

    rows = gaps(load_store(coverage_store.root), min_instances=2)

    assert rows == [
        {"dimension": "typing-discipline", "value": "dynamic-typing", "present": 0,
         "partial": 0, "corroborating": 0, "thin": True},
        {"dimension": "typing-discipline", "value": "static-typing", "present": 2,
         "partial": 0, "corroborating": 2, "thin": False},
    ]


def test_the_report_carries_its_caveat_and_says_when_nothing_is_swept(coverage_store):
    coverage_store.feature("static-typing", layer=3, dimension="typing-discipline")
    store = load_store(coverage_store.root)

    text = render_gaps(gaps(store), min_instances=2, instances_total=len(store.instances))

    assert "near-meaningless before D28 phase 1" in text
    assert "No FeatureInstance records yet" in text
    assert "| typing-discipline | static-typing | 0 | 0 | 0 | thin |" in text
