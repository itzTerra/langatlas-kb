from ruamel.yaml import YAML
from langatlas_ingest.scaffold import render_source_yaml
from langatlas_validate.schema import validate_record
from langatlas_validate.normalize import normalize_record

_yaml = YAML(typ="safe")


def test_render_source_yaml_validates_and_is_normalized():
    text = render_source_yaml(
        "vanroy-haridi-2003", "book", "Concepts, Techniques, and Models of Computer Programming",
        author=[{"family": "Van Roy", "given": "Peter"}, {"family": "Haridi", "given": "Seif"}],
        issued={"date-parts": [[2003]]}, tier="B", grounding="third-party-reference",
        canonical_source=False, acquisition_note="developer's personal library copy")
    data = _yaml.load(text)
    assert validate_record(data, "source") == []
    assert normalize_record(text, "source") == text


def test_render_source_yaml_omits_unset_optional_fields():
    text = render_source_yaml("kaijanaho-2015", "thesis", "Empirical Evaluation in PL Design",
                              tier="B", grounding="third-party-reference",
                              canonical_source=True)
    data = _yaml.load(text)
    assert "author" not in data and "URL" not in data and "DOI" not in data
    assert "acquisition_note" not in data["custom"]


def test_render_source_yaml_carries_edition_and_locator_kinds():
    text = render_source_yaml(
        "haskell-2010-report", "report", "Haskell 2010 Language Report",
        tier="A", grounding="formal-spec", canonical_source=True,
        edition="2010", edition_check_url="https://www.haskell.org/onlinereport/haskell2010/",
        locator_kinds=["numbered-section"])
    data = _yaml.load(text)
    assert data["custom"]["edition"] == "2010"
    assert data["custom"]["locator_kinds"] == ["numbered-section"]
    assert validate_record(data, "source") == []
