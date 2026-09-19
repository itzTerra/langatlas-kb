from langatlas_validate.redirects import (
    load_redirects, parse_redirects, render_redirects, validate_redirects,
)
from langatlas_validate.store import validate_store

NODES = {"static-typing": "static-typing", "type-inference": "type-inference"}


def test_render_sorts_and_round_trips():
    text = render_redirects({"zeta": "static-typing", "alpha": "type-inference"})

    assert text.index("alpha") < text.index("zeta")
    assert parse_redirects(text) == {"alpha": "type-inference", "zeta": "static-typing"}
    assert render_redirects({}) == "redirects: {}\n"


def test_a_redirect_must_target_a_live_node():
    assert validate_redirects({"old-name": "static-typing"}, nodes=NODES) == []
    assert any("no such" in e for e in validate_redirects({"old-name": "gone"}, nodes=NODES))


def test_a_live_slug_cannot_also_be_a_redirect():
    errors = validate_redirects({"type-inference": "static-typing"}, nodes=NODES)

    assert any("current slug" in e for e in errors)


def test_an_invalid_redirect_key_is_refused():
    assert any("slug" in e for e in validate_redirects({"Bad Key": "static-typing"},
                                                       nodes=NODES))


def test_validate_store_checks_both_ledgers(mini_store):
    mini_store.feature("alpha")
    mini_store.write("ontology/redirects.yaml", "redirects:\n  old-alpha: nowhere\n")
    mini_store.write("tombstones.yaml",
                     "tombstones:\n  - fact_id: f-000000000001\n    anchor: a#summary\n"
                     "    action: remap\n    reason: merge\n"
                     "    superseded_by: [f-000000000002]\n    migration_id: 0001-x\n"
                     "    date: '2026-10-01'\n")

    errors = validate_store(mini_store.root)

    assert load_redirects(mini_store.root) == {"old-alpha": "nowhere"}
    assert any(e.startswith("ontology/redirects.yaml") for e in errors)
    assert any(e.startswith("tombstones.yaml") and "neither" in e for e in errors)
