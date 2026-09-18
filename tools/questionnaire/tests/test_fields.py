from pathlib import Path

from ruamel.yaml import YAML

from langatlas_questionnaire.fields import FACT_FIELDS

FIXTURE = (Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "providers"
           / "questionnaire-shape" / "feature-instance-fact-fields.yaml")


def test_the_compilers_field_map_is_the_one_the_drift_fixture_pins():
    fixture = YAML(typ="safe").load(FIXTURE.read_text())
    assert fixture["mode"] == "soft"
    assert {name: list(members) for name, members in FACT_FIELDS.items()} == fixture["fields"]
