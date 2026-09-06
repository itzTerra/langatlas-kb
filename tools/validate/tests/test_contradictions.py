import pytest
from ruamel.yaml import YAML
from langatlas_validate.ids import contradiction_key
from langatlas_validate.schema import validate_record
from langatlas_validate.store import validate_contradictions

_yaml = YAML()


def record(**kw):
    participants = kw.pop("participants",
                          ["f-000000000001", "citation:scott-plp:p. 12"])
    base = {"id": contradiction_key(participants), "type": "verification",
            "participants": participants, "status": "open", "mechanism": "verifier",
            "minted": "2026-09-06"}
    base.update(kw)
    return base


def write(tmp_path, records):
    path = tmp_path / "contradictions.yaml"
    with path.open("w") as fh:
        _yaml.dump({"contradictions": records}, fh)
    return tmp_path


def test_the_id_is_content_keyed_over_sorted_participants():
    # Sorted, so two processes minting the same conflict from opposite directions dedup
    # automatically instead of racing to create two records.
    assert contradiction_key(["b", "a"]) == contradiction_key(["a", "b"])
    assert contradiction_key(["a", "b"]).startswith("ctr-")
    assert len(contradiction_key(["a", "b"])) == len("ctr-") + 12


def test_a_well_formed_record_validates():
    assert validate_record(record(), "contradiction") == []


def test_both_record_types_are_accepted():
    assert validate_record(record(type="cross-fact"), "contradiction") == []


def test_an_unknown_type_is_rejected():
    assert validate_record(record(type="vibes"), "contradiction")


def test_an_unknown_status_is_rejected():
    assert validate_record(record(status="maybe"), "contradiction")


def test_a_malformed_id_is_rejected():
    assert validate_record(record(id="ctr-nothex"), "contradiction")


def test_fewer_than_two_participants_is_rejected():
    assert validate_record(record(participants=["f-000000000001"]), "contradiction")


def test_an_unknown_mechanism_is_rejected():
    assert validate_record(record(mechanism="a-hunch"), "contradiction")


def test_the_empty_ledger_validates(tmp_path):
    assert validate_contradictions(write(tmp_path, [])) == []


def test_an_id_that_does_not_match_its_participants_is_an_error(tmp_path):
    bad = record()
    bad["id"] = "ctr-000000000000"
    errors = validate_contradictions(write(tmp_path, [bad]))
    assert any("content key" in e for e in errors)


def test_a_duplicate_id_is_an_error(tmp_path):
    errors = validate_contradictions(write(tmp_path, [record(), record()]))
    assert any("duplicate" in e for e in errors)


def test_a_missing_file_is_not_an_error(tmp_path):
    # A repo that has never minted a contradiction is a valid repo.
    assert validate_contradictions(tmp_path) == []
