from langatlas_coverage.dossier import reality_checks, render_dossier, sourcing_integrity
from langatlas_coverage.metrics import load_store


def _gated(key, admissible):
    return {"key": key, "status": "minted" if admissible else "proposed",
            "verification": {"fact_id": "f", "verdict": "v", "admissible": admissible}}


def _reality(cells, unmappable, violations=(), shakedown=()):
    return {"summary": {"cells": cells, "unmappable": unmappable, "admitted": cells - unmappable,
                        "refused": 0, "unsourced": 0},
            "findings": {"unmappable": [], "uninhabited_values": [], "unfittable": [],
                         "exclusivity_violations": list(violations)},
            "shakedown": list(shakedown)}


def test_sourcing_integrity_needs_a_ledger(make_inputs):
    assert sourcing_integrity(make_inputs()).status == "no-data"


def test_sourcing_integrity_counts_verified_definitions(coverage_store, make_inputs,
                                                         make_cycle):
    coverage_store.feature("static-typing")
    coverage_store.feature("dynamic-typing")
    coverage_store.edge("alternative-to", "dynamic-typing", "static-typing")
    store = load_store(coverage_store.root)
    ids = {fact["anchor"]: fact["fact_id"] for fact in store.facts}
    verification = {ids["static-typing#summary"]: "verified",
                    ids["dynamic-typing#summary"]: "failed",
                    ids["edge.alternative-to.dynamic-typing.static-typing#exists"]: "verified"}
    plan = {"nodes": [_gated("static-typing", True), _gated("dynamic-typing", False)],
            "edges": [], "quality_edges": [], "dimensions": [], "qualities": []}

    item = sourcing_integrity(make_inputs(store=store, verification=verification,
                                          cycles=(make_cycle(1, "typing"),),
                                          plans={"01-typing": plan},
                                          reality={"01-typing": _reality(10, 1)}))

    assert item.status == "not-met"
    assert "Nodes verified: 1/2 (50.0%)" in item.lines
    assert "Not yet verified: dynamic-typing" in item.lines
    assert "Edges verified: 1/1 (100.0%)" in item.lines
    assert "  01-typing: R4/R6 gate 1/2 (50.0%); R5 9/9 (100.0%)" in item.lines


def test_all_verified_meets_the_bar(coverage_store, make_inputs):
    coverage_store.feature("static-typing")
    store = load_store(coverage_store.root)

    item = sourcing_integrity(make_inputs(
        store=store, verification={store.facts[0]["fact_id"]: "verified"}))

    assert item.status == "met"


def test_reality_checks_read_the_final_cycle(make_inputs, make_cycle):
    violation = {"language": "python", "dimension": "typing-discipline",
                 "members": ["dynamic-typing", "static-typing"]}
    inputs = make_inputs(cycles=(make_cycle(1, "typing"), make_cycle(2, "memory-management")),
                         reality={"01-typing": _reality(20, 5, [violation]),
                                  "02-memory-management": _reality(40, 1)})

    item = reality_checks(inputs)

    assert item.status == "met"                    # 2.5% and no violation in the final cycle
    assert any(line.startswith("01-typing: 5/20 unmappable (25.0%)") for line in item.lines)
    assert reality_checks(make_inputs(
        cycles=(make_cycle(1, "typing"),),
        reality={"01-typing": _reality(20, 0, [violation])})).status == "not-met"
    assert reality_checks(make_inputs()).status == "no-data"


def test_the_dossier_renders_a_summary_table_and_the_advisory_note(make_inputs):
    text = render_dossier([sourcing_integrity(make_inputs()), reality_checks(make_inputs())])

    assert "All bars are advisory" in text
    assert "| Sourcing integrity | no-data |" in text
    assert "## Reality-check results — no-data" in text


def test_unmappable_bar_boundaries_are_strict(make_inputs, make_cycle):
    def status(cells, unmappable):
        return reality_checks(make_inputs(
            cycles=(make_cycle(1, "typing"),),
            reality={"01-typing": _reality(cells, unmappable)})).status

    assert status(1000, 49) == "met"       # 4.9%
    assert status(100, 5) == "not-met"     # exactly 5.0% is not "<5%"
    assert status(100, 6) == "not-met"
    assert status(100, 0) == "met"
    assert status(0, 0) == "no-data"       # nothing to measure is not a pass


def test_reality_checks_never_raise_on_malformed_records(make_inputs, make_cycle):
    cycles = (make_cycle(1, "typing"),)
    for record in ({}, {"summary": None}, {"summary": {"cells": "x"}},
                   {"summary": {"cells": 10, "unmappable": 1}}, "text", []):
        item = reality_checks(make_inputs(cycles=cycles, reality={"01-typing": record}))
        assert item.status == "no-data", record
        assert item.lines


def test_sourcing_integrity_empty_store_is_no_data(make_inputs):
    assert sourcing_integrity(make_inputs(verification={})).status == "no-data"


def test_unledgered_nodes_are_not_met(coverage_store, make_inputs):
    coverage_store.feature("static-typing")
    store = load_store(coverage_store.root)

    item = sourcing_integrity(make_inputs(store=store, verification={}))

    assert item.status == "not-met"
    assert "Nodes verified: 0/1 (0.0%)" in item.lines


def test_sourcing_integrity_tolerates_malformed_plans(coverage_store, make_inputs, make_cycle):
    coverage_store.feature("static-typing")
    store = load_store(coverage_store.root)
    verification = {store.facts[0]["fact_id"]: "verified"}
    for plan in ({}, {"nodes": None}, {"nodes": ["x"]}, {"nodes": [{"verification": 3}]}, "x"):
        item = sourcing_integrity(make_inputs(
            store=store, verification=verification, cycles=(make_cycle(1, "typing"),),
            plans={"01-typing": plan}, reality={"01-typing": {"summary": "bad"}}))
        assert item.status == "met", plan


def test_a_final_cycle_without_a_record_is_not_read_from_an_earlier_one(make_inputs, make_cycle):
    item = reality_checks(make_inputs(
        cycles=(make_cycle(1, "typing"), make_cycle(2, "memory-management")),
        reality={"01-typing": _reality(20, 0)}))

    assert item.status == "no-data"
