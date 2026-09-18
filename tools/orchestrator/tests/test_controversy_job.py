"""The job kind's contract with the driver: what it enumerates, and how it classifies failure."""
import psycopg
import pytest

from langatlas_orchestrator.jobs import controversy as job
from langatlas_orchestrator.registry import get_job_kind
from langatlas_pipeline.errors import CircuitOpen, ProviderTransportError


def test_the_kind_is_registered():
    enumerate_fn, run_fn = get_job_kind("nightly-controversy")
    assert callable(enumerate_fn) and callable(run_fn)


def test_it_enumerates_one_item_per_record(tmp_path, monkeypatch):
    monkeypatch.setattr(job, "store_record_paths",
                        lambda root: ["features/a.yaml", "concepts/b.yaml"])
    assert job._enumerate({}, tmp_path) == ["concepts/b.yaml", "features/a.yaml"]


def test_records_can_be_narrowed_from_the_spec(tmp_path, monkeypatch):
    monkeypatch.setattr(job, "store_record_paths", lambda root: ["features/a.yaml"])
    assert job._enumerate({"records": ["concepts/b.yaml"]}, tmp_path) == ["concepts/b.yaml"]


def test_a_provider_outage_blocks_the_item_rather_than_crashing(tmp_path, monkeypatch):
    monkeypatch.setattr(job, "_assess",
                        lambda *a, **k: (_ for _ in ()).throw(ProviderTransportError("down")))
    outcome = job._run_item(object(), "features/a.yaml", {}, tmp_path)
    assert outcome.status == "blocked"
    assert "provider unavailable" in outcome.detail


def test_a_database_outage_blocks_the_item(tmp_path, monkeypatch):
    monkeypatch.setattr(job, "_assess",
                        lambda *a, **k: (_ for _ in ()).throw(psycopg.OperationalError("no db")))
    assert job._run_item(object(), "features/a.yaml", {}, tmp_path).status == "blocked"


def test_a_record_that_vanished_is_done_not_blocked(tmp_path, monkeypatch):
    """The store moves under a nightly batch all the time — a record tombstoned since the
    enumerator ran is finished work, not a failure to retry forever."""
    monkeypatch.setattr(job, "_assess",
                        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("gone")))
    outcome = job._run_item(object(), "features/a.yaml", {}, tmp_path)
    assert outcome.status == "done"
    assert "no longer in the store" in outcome.detail
