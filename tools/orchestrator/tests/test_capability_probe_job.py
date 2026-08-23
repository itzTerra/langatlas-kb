from pathlib import Path

from langatlas_orchestrator.jobs.capability_probe import _enumerate, _run_item
from langatlas_orchestrator.registry import get_job_kind


class _FakeCtx:
    def __init__(self):
        self.run_id = "run-1"


def test_capability_probe_is_registered_on_import():
    import langatlas_orchestrator.jobs  # noqa: F401
    enumerator, item_runner = get_job_kind("monthly-capability-probe")
    assert enumerator is _enumerate
    assert item_runner is _run_item


def test_enumerate_returns_one_static_item(tmp_path):
    assert _enumerate({}, tmp_path) == ["probe-all-aliases"]


def test_run_item_calls_probe_all_and_applies_it(tmp_path, monkeypatch):
    calls = {}

    def _fake_probe_all(ctx):
        calls["probed"] = True
        return {"claude-completion": {"resolved_model": "claude-x"}}

    def _fake_apply_probe(path, probed):
        calls["applied"] = (path, probed)

    monkeypatch.setattr(
        "langatlas_orchestrator.jobs.capability_probe.probe_all", _fake_probe_all)
    monkeypatch.setattr(
        "langatlas_orchestrator.jobs.capability_probe.apply_probe", _fake_apply_probe)

    outcome = _run_item(_FakeCtx(), "probe-all-aliases", {}, tmp_path)

    assert outcome.status == "done"
    assert calls["probed"] is True
    assert "probed 1 alias" in outcome.detail
    assert calls["applied"][1] == {"claude-completion": {"resolved_model": "claude-x"}}
