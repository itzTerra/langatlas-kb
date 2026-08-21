from pathlib import Path

from langatlas_validate.compile import derive_facts, check_fact_collisions, compile_bundle
from langatlas_validate.normalize import normalize_record


def _write_instance(root: Path) -> None:
    raw = (
        "feature: pattern-matching\nlanguage: rust\nstatus: present\n"
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
