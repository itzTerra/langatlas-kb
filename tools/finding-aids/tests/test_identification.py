import pytest
from ruamel.yaml import YAML

from langatlas_finding_aids.identification import (
    NotIdentificationMetadata, identification_source_id, mint_identification_source,
)
from langatlas_finding_aids.results import FindingAidResult

yaml = YAML(typ="safe")


def _result(source="wikidata") -> FindingAidResult:
    return FindingAidResult(source=source, item_id="Q575", label="Rust",
                            fields={"extension": "rs", "inception": "2010-07-07"},
                            url="https://www.wikidata.org/wiki/Q575",
                            retrieved_at="2026-09-08T00:00:00Z")


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "sources").mkdir()
    return tmp_path


def test_a_paradigm_claim_is_refused(repo):
    """The carve-out is *identification* metadata only. A paradigm or feature claim from
    a finding aid is exactly what D29 rejects, and this is the one code path that could
    smuggle one into `sources/`."""
    with pytest.raises(NotIdentificationMetadata, match="paradigm"):
        mint_identification_source(_result(), "paradigm", repo_root=repo)


def test_minting_writes_a_tier_d_attribution_record(repo):
    path = mint_identification_source(_result(), "file-extension", repo_root=repo)
    record = yaml.load(path.read_text())
    assert record["custom"]["tier"] == "D"
    assert record["custom"]["grounding"] == "third-party-reference"
    assert record["custom"]["canonical_source"] is False
    assert record["URL"] == "https://www.wikidata.org/wiki/Q575"


def test_the_record_is_schema_valid_and_normalized(repo):
    from langatlas_validate.normalize import normalize_record
    from langatlas_validate.schema import validate_record

    path = mint_identification_source(_result(), "first-appeared", repo_root=repo)
    text = path.read_text()
    assert validate_record(yaml.load(text), "source") == []
    assert normalize_record(text, "source") == text


def test_the_acquisition_note_says_what_this_record_is_for(repo):
    path = mint_identification_source(_result(), "file-extension", repo_root=repo)
    note = yaml.load(path.read_text())["custom"]["acquisition_note"]
    assert "identification metadata" in note and "ungated" in note


def test_ids_are_stable_and_readable(repo):
    assert identification_source_id(_result(), "file-extension") \
        == "wikidata-q575-file-extension"


def test_minting_twice_is_idempotent(repo):
    first = mint_identification_source(_result(), "file-extension", repo_root=repo)
    second = mint_identification_source(_result(), "file-extension", repo_root=repo)
    assert first == second
    assert len(list((repo / "sources").glob("*.yaml"))) == 1
