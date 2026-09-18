from pathlib import Path

from langatlas_validate.compile import derive_facts, check_fact_collisions, compile_bundle
from langatlas_validate.normalize import normalize_record


def _write_instance(root: Path) -> None:
    raw = (
        "feature: pattern-matching\nlanguage: rust\nstatus: present\n"
        "since:\n  value: \"1.0\"\n  sources:\n    - source: rust-reference\n      locator: p. 1\n"
        "characteristics:\n"
        "  - key: c-exhaustive\n"
        "    text: match arms must be exhaustive\n"
        "    sources:\n"
        "      - source: nystrom-2021\n        locator: \"p. 42\"\n"
        "provenance:\n  claim_origin: source-derived\n"
    )
    path = root / "languages" / "rust" / "instances" / "pattern-matching.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalize_record(raw, "feature-instance"))


def test_derive_facts_yields_instance_exists_and_characteristic(tmp_path):
    _write_instance(tmp_path)
    from langatlas_validate.store import iter_store_records
    records = list(iter_store_records(tmp_path))
    facts = derive_facts(records)
    kinds = {f["claim"].split("(")[0] for f in facts}
    assert "instance-exists" in kinds
    assert "characteristic" in kinds
    for f in facts:
        assert f["fact_id"].startswith("f-")
        assert f["record_path"] is not None


def test_check_fact_collisions_flags_same_fact_id_from_two_records():
    facts = [
        {"fact_id": "f-abc", "claim": "instance-exists(fi.rust.x, status=present)",
        "record_path": "a.yaml"},
        {"fact_id": "f-abc", "claim": "instance-exists(fi.rust.x, status=present)",
        "record_path": "b.yaml"},
    ]
    errors = check_fact_collisions(facts)
    assert len(errors) == 1
    assert "a.yaml" in errors[0] and "b.yaml" in errors[0]


def test_check_fact_collisions_allows_unique_facts():
    facts = [
        {"fact_id": "f-abc", "claim": "instance-exists(fi.rust.x, status=present)",
        "record_path": "a.yaml"},
        {"fact_id": "f-def", "claim": "instance-exists(fi.rust.y, status=present)",
        "record_path": "b.yaml"},
    ]
    assert check_fact_collisions(facts) == []


def test_compile_bundle_shape(tmp_path):
    _write_instance(tmp_path)
    (tmp_path / "ontology").mkdir()
    (tmp_path / "ontology" / "VERSION").write_text("0.1.0\n")
    bundle = compile_bundle(tmp_path)
    assert bundle["schema_version"] == "0.1.0"
    assert isinstance(bundle["facts"], list) and len(bundle["facts"]) > 0


from pathlib import Path

from langatlas_validate.compile import derive_facts


def _concept(**over):
    return {"id": "type-system", "slug": "type-system", "name": "Type system",
            "summary": {"text": "What types exist and what counts as a type error.",
                        "sources": [{"source": "pierce-tapl-2002", "locator": "§1.1"}]},
            "provenance": {}, **over}


def _edge(**over):
    return {"id": "edge.requires.static-typing.type-system", "type": "requires",
            "from": "static-typing", "to": "type-system",
            "statement": {"text": "Static typing requires a type system.",
                          "sources": [{"source": "scott-plp", "locator": "§7.2"}]},
            "provenance": {}, **over}


def test_a_concept_summary_derives_one_node_definition_fact():
    facts = derive_facts([(Path("concepts/type-system.yaml"), "concept", "", _concept())])
    assert len(facts) == 1
    assert facts[0]["claim"].startswith("node-definition(type-system, sha256-16=")
    assert facts[0]["sources"] == [{"source": "pierce-tapl-2002", "locator": "§1.1"}]


def test_a_feature_summary_derives_a_node_definition_fact_too():
    feature = {**_concept(), "id": "static-typing", "slug": "static-typing", "layer": 3,
               "dimension": "type-checking-discipline"}
    facts = derive_facts([(Path("features/static-typing.yaml"), "feature", "", feature)])
    assert [f["claim"].split("(")[0] for f in facts] == ["node-definition"]


def test_a_node_without_a_summary_derives_no_fact():
    data = {"id": "x", "slug": "x", "name": "X", "provenance": {}}
    assert derive_facts([(Path("concepts/x.yaml"), "concept", "", data)]) == []


def test_edge_exists_carries_the_edges_own_citations():
    facts = derive_facts([(Path("edges/static-typing/requires--type-system.yaml"),
                           "edge", "", _edge())])
    exists = next(f for f in facts if f["claim"].startswith("edge-exists("))
    assert exists["sources"] == [{"source": "scott-plp", "locator": "§7.2"}]


def test_edge_polarity_still_derives_without_its_own_citations():
    influences = _edge(id="edge.influences.static-typing.type-system", type="influences",
                       polarity="+")
    kinds = [f["claim"].split("(")[0] for f in
             derive_facts([(Path("edges/static-typing/influences--type-system.yaml"),
                            "edge", "", influences)])]
    assert kinds == ["edge-exists", "edge-polarity"]


INSTANCE_PATH = Path("languages/rust/instances/pattern-matching.yaml")
REF = [{"source": "rust-fls", "locator": "§6.18"}]
FEATURE = {"id": "pattern-matching", "slug": "pattern-matching", "name": "Pattern matching",
           "layer": 2, "aliases": ["match expression", "Pattern matching"],
           "summary": {"text": "Branch selection by the shape of a value.",
                       "sources": [{"source": "scott-plp", "locator": "§6.1"}]},
           "provenance": {}}


def _present(**over):
    return {"feature": "pattern-matching", "language": "rust", "status": "present",
            "since": {"value": "1.0", "sources": REF}, "provenance": {}, **over}


def _absent(**over):
    return {"feature": "pattern-matching", "language": "rust", "status": "absent",
            "absence_scope": "Chapter 6 lists every expression form.", "sources": REF,
            "provenance": {}, **over}


def _anchored(instance, *context):
    facts = derive_facts([(INSTANCE_PATH, "feature-instance", "", instance), *context])
    return {fact["anchor"]: fact for fact in facts if "anchor" in fact}


def test_a_present_instance_is_cited_through_its_since():
    """D65: `since` is a load-bearing field of the existence claim (D25's fold table), so the
    #exists fact carries it and is verified against `since.sources`."""
    exists = _anchored(_present())["fi.rust.pattern-matching#exists"]
    assert exists["claim"] == "instance-exists(fi.rust.pattern-matching, status=present)"
    assert exists["sources"] == REF
    assert exists["since"] == "1.0"
    assert exists["status"] == "present"


def test_since_is_an_identity_fact_verified_through_exists():
    since = _anchored(_present())["fi.rust.pattern-matching#since"]
    assert since["claim"] == 'instance-field(fi.rust.pattern-matching, since, "1.0")'
    assert since["sources"] == []
    assert since["verified_with"] == "fi.rust.pattern-matching#exists"


def test_correcting_since_changes_one_fact_id_and_keeps_the_existence_id():
    """§3.4: correcting `since` changes one fact id and leaves the others untouched."""
    old = _anchored(_present())
    new = _anchored(_present(since={"value": "1.2", "sources": REF}))
    assert (old["fi.rust.pattern-matching#exists"]["fact_id"]
            == new["fi.rust.pattern-matching#exists"]["fact_id"])
    assert (old["fi.rust.pattern-matching#since"]["fact_id"]
            != new["fi.rust.pattern-matching#since"]["fact_id"])


def test_an_absent_instance_cites_at_status_level_with_its_scope_and_the_features_names():
    feature = (Path("features/pattern-matching.yaml"), "feature", "", FEATURE)
    facts = _anchored(_absent(), feature)
    exists = facts["fi.rust.pattern-matching#exists"]
    assert exists["sources"] == REF
    assert exists["absence_scope"] == "Chapter 6 lists every expression form."
    assert exists["feature_aliases"] == ["Pattern matching", "match expression"]
    assert "since" not in exists
    assert "fi.rust.pattern-matching#since" not in facts


def test_an_absent_instance_without_its_feature_record_has_no_grep_vocabulary():
    exists = _anchored(_absent())["fi.rust.pattern-matching#exists"]
    assert exists["feature_aliases"] == []


def test_typed_notes_are_independently_verifiable_facts():
    note = {"key": "n-no-guards", "type": "limitation", "text": "Guards are not supported.",
            "sources": REF}
    fact = _anchored(_present(status="partial", notes=[note]))[
        "fi.rust.pattern-matching#notes[n-no-guards]"]
    assert fact["claim"].startswith(
        "instance-note(fi.rust.pattern-matching, n-no-guards, type=limitation, sha256-16=")
    assert fact["sources"] == REF


def test_a_copyedit_to_a_note_keeps_its_fact_id():
    def note_fact_id(text):
        note = {"key": "n-a", "type": "extra", "text": text, "sources": REF}
        return _anchored(_present(status="partial", notes=[note]))[
            "fi.rust.pattern-matching#notes[n-a]"]["fact_id"]

    assert note_fact_id("Guards are  supported.") == note_fact_id("guards are supported")
    assert note_fact_id("Guards are supported.") != note_fact_id("Guards are not supported.")


def test_characteristics_and_syntax_carry_their_anchors():
    facts = _anchored(_present(
        characteristics=[{"key": "c-exhaustive", "text": "Matches must be exhaustive.",
                          "sources": REF}],
        syntax=[{"key": "basic-match", "title": "Basic", "origin": "original",
                 "code": "match x { _ => () }", "sources": REF}]))
    assert facts["fi.rust.pattern-matching#characteristics[c-exhaustive]"][
        "claim"].startswith("characteristic(fi.rust.pattern-matching, c-exhaustive,")
    assert facts["fi.rust.pattern-matching#syntax[basic-match]"]["claim"].startswith(
        "syntax-valid(fi.rust.pattern-matching.sx.basic-match,")
