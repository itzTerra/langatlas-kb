import pytest
from ruamel.yaml import YAML

from langatlas_ingest.currency.supersede import supersede_source

yaml = YAML(typ="safe")


def _repo(tmp_path):
    (tmp_path / "sources").mkdir(parents=True)
    (tmp_path / "sources" / "docs-3-14.yaml").write_text(
        "id: docs-3-14\ntype: book\ntitle: D\nURL: https://example.test/docs\n"
        "custom:\n  tier: B\n  grounding: reference-implementation-docs\n"
        "  edition: 3.14.7\n")
    (tmp_path / "sources" / "docs-3-15.yaml").write_text(
        "id: docs-3-15\ntype: book\ntitle: D\nURL: https://example.test/docs\n"
        "custom:\n  tier: B\n  grounding: reference-implementation-docs\n"
        "  edition: 3.15.0\n")
    (tmp_path / "sources" / "_tombstones.yaml").write_text("tombstones: []\n")
    return tmp_path


def test_the_old_record_gains_superseded_by(tmp_path):
    root = _repo(tmp_path)
    supersede_source(root, old_id="docs-3-14", new_id="docs-3-15")
    old = yaml.load((root / "sources" / "docs-3-14.yaml").read_text())
    assert old["custom"]["superseded_by"] == "docs-3-15"


def test_a_tombstone_entry_is_appended(tmp_path):
    root = _repo(tmp_path)
    supersede_source(root, old_id="docs-3-14", new_id="docs-3-15", note="3.15 shipped")
    ledger = yaml.load((root / "sources" / "_tombstones.yaml").read_text())
    assert ledger["tombstones"] == [
        {"id": "docs-3-14", "superseded_by": "docs-3-15", "reason": "edition-superseded",
         "note": "3.15 shipped"}]


def test_superseding_twice_does_not_duplicate_the_tombstone(tmp_path):
    root = _repo(tmp_path)
    supersede_source(root, old_id="docs-3-14", new_id="docs-3-15")
    supersede_source(root, old_id="docs-3-14", new_id="docs-3-15")
    ledger = yaml.load((root / "sources" / "_tombstones.yaml").read_text())
    assert len(ledger["tombstones"]) == 1


def test_an_unknown_new_id_is_refused(tmp_path):
    """The replacement must already be ingested and committed: tombstoning toward a
    record that does not exist points every reader of the old source at nothing."""
    root = _repo(tmp_path)
    with pytest.raises(ValueError, match="docs-9-99"):
        supersede_source(root, old_id="docs-3-14", new_id="docs-9-99")


def test_superseding_a_record_by_itself_is_refused(tmp_path):
    root = _repo(tmp_path)
    with pytest.raises(ValueError, match="itself"):
        supersede_source(root, old_id="docs-3-14", new_id="docs-3-14")


def test_the_rewritten_record_stays_schema_valid_and_normalized(tmp_path):
    from langatlas_validate.normalize import normalize_record
    from langatlas_validate.schema import validate_record

    root = _repo(tmp_path)
    supersede_source(root, old_id="docs-3-14", new_id="docs-3-15")
    text = (root / "sources" / "docs-3-14.yaml").read_text()
    assert validate_record(yaml.load(text), "source") == []
    assert normalize_record(text, "source") == text


@pytest.mark.db
def test_the_staleness_trigger_is_filed(db_conn):
    from langatlas_ingest.db import migrate
    from langatlas_ingest.store import SourcingQueue
    import tempfile
    from pathlib import Path

    migrate(db_conn)
    queue = SourcingQueue(db_conn)
    with tempfile.TemporaryDirectory() as tmp:
        supersede_source(_repo(Path(tmp)), old_id="docs-3-14", new_id="docs-3-15",
                         queue=queue)
    entries = queue.open_entries(kind="edition-check")
    assert [(e["source_id"], e["reason"]) for e in entries] == \
        [("docs-3-14", "edition-superseded")]
