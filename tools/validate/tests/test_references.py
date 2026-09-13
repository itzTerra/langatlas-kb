import pytest

from langatlas_validate.references import validate_references


@pytest.fixture
def store(tmp_path):
    for directory in ("concepts", "features", "rules", "sources", "ontology/taxonomy",
                      "languages"):
        (tmp_path / directory).mkdir(parents=True)
    (tmp_path / "ontology/taxonomy/dimensions.yaml").write_text(
        "dimensions:\n  - slug: typing-discipline\n    label: Typing discipline\n"
        "    values: [static, dynamic]\n    exclusivity: exclusive\n"
        "    applies_to: [general-purpose]\n")
    (tmp_path / "ontology/taxonomy/qualities.yaml").write_text(
        "qualities:\n  - slug: learnability\n    label: Learnability\n    summary: x\n")
    (tmp_path / "languages/_registry.yaml").write_text("languages: {}\n")
    return tmp_path


def _feature(store, node_id, *, layer=2, dimension=None):
    body = [f"id: {node_id}", f"slug: {node_id}", "name: X", f"layer: {layer}"]
    if dimension:
        body.append(f"dimension: {dimension}")
    body += ["summary:", "  text: X.", "  sources:",
             "    - source: s", "      locator: p. 1",
             "provenance:", "  claim_origin: source-derived"]
    (store / "features" / f"{node_id}.yaml").write_text("\n".join(body) + "\n")


def test_a_clean_store_has_no_reference_errors(store):
    _feature(store, "pattern-matching")

    assert validate_references(store) == []


def test_a_filename_that_disagrees_with_its_id_is_an_error(store):
    _feature(store, "pattern-matching")
    (store / "features" / "pattern-matching.yaml").rename(store / "features" / "patmat.yaml")

    assert any("filename" in e for e in validate_references(store))


def test_a_dangling_edge_endpoint_is_an_error(store):
    _feature(store, "pattern-matching")
    (store / "edges" / "pattern-matching").mkdir(parents=True)
    (store / "edges" / "pattern-matching" / "requires--ownership.yaml").write_text(
        "id: edge.requires.pattern-matching.ownership\ntype: requires\n"
        "from: pattern-matching\nto: ownership\n"
        "statement:\n  text: X.\n  sources:\n    - source: s\n      locator: p. 1\n"
        "provenance:\n  claim_origin: source-derived\n")

    assert any("ownership" in e and "no such feature" in e for e in validate_references(store))


def test_an_undeclared_dimension_is_an_error(store):
    _feature(store, "typing-x", layer=3, dimension="nominality")

    assert any("nominality" in e for e in validate_references(store))


def test_a_declared_dimension_on_a_layer_three_feature_is_fine(store):
    _feature(store, "static-typing", layer=3, dimension="typing-discipline")

    assert validate_references(store) == []


def test_a_rule_antecedent_must_name_a_committed_feature(store):
    _feature(store, "lazy-evaluation")
    (store / "rules" / "rule-x.yaml").write_text(
        "id: rule-x\nwhen_all: [lazy-evaluation, purity]\neffect: requires\n"
        "then: [purity]\nmessage: X.\nsources:\n  - source: s\n    locator: p. 1\n"
        "provenance:\n  claim_origin: source-derived\n")

    assert any("purity" in e for e in validate_references(store))
