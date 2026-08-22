import pytest
from langatlas_orchestrator.registry import (
    ItemOutcome, UnknownJobKind, get_job_kind, register_job_kind, registered_kinds,
)


def _enumerate(extra, repo_root):
    return ["a", "b"]


def _run_item(ctx, item_key, extra, repo_root):
    return ItemOutcome(status="done")


def test_register_then_get_round_trips():
    register_job_kind("test-kind-1", _enumerate, _run_item)
    enumerator, item_runner = get_job_kind("test-kind-1")
    assert enumerator is _enumerate
    assert item_runner is _run_item


def test_get_unknown_kind_raises():
    with pytest.raises(UnknownJobKind):
        get_job_kind("no-such-kind")


def test_registered_kinds_lists_registrations_sorted():
    register_job_kind("test-kind-z", _enumerate, _run_item)
    register_job_kind("test-kind-a", _enumerate, _run_item)
    kinds = registered_kinds()
    assert kinds.index("test-kind-a") < kinds.index("test-kind-z")


def test_item_outcome_defaults():
    outcome = ItemOutcome(status="done")
    assert outcome.record_key is None
    assert outcome.detail == ""
