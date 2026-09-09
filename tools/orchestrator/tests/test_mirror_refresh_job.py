import pytest

from langatlas_finding_aids.mirror import MirrorRefusedByRobots, MirrorState
from langatlas_orchestrator.jobs.mirror_refresh import _enumerate, _run_item
from langatlas_orchestrator.registry import get_job_kind


class _FakeCtx:
    def __init__(self):
        self.run_id = "run-1"

    class _W:
        def append(self, **event):
            pass

    writer = _W()


def test_registered_on_import():
    import langatlas_orchestrator.jobs  # noqa: F401
    enumerator, item_runner = get_job_kind("monthly-finding-aid-mirror-refresh")
    assert enumerator is _enumerate and item_runner is _run_item


def test_one_item_per_mirrored_source(tmp_path):
    assert _enumerate({}, tmp_path) == ["hyperpolyglot", "pldb"]


def test_a_refresh_reports_the_new_version(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "langatlas_orchestrator.jobs.mirror_refresh.refresh",
        lambda source, ctx, **kw: MirrorState(source=source, version="abc1234",
                                              refreshed_at="2026-09-08T00:00:00Z",
                                              item_count=7))
    outcome = _run_item(_FakeCtx(), "pldb", {}, tmp_path)
    assert outcome.status == "done" and "abc1234" in outcome.detail


def test_a_robots_refusal_halts_rather_than_retrying(tmp_path, monkeypatch):
    """A publisher's opt-out is not a transient failure. `blocked` would have the job
    re-attempt it next month and every month after; `halted` puts it in front of a human,
    which is the only correct response to 'you may not fetch this'."""
    def _refuse(source, ctx, **kw):
        raise MirrorRefusedByRobots("robots.txt disallows /c")

    monkeypatch.setattr("langatlas_orchestrator.jobs.mirror_refresh.refresh", _refuse)
    outcome = _run_item(_FakeCtx(), "hyperpolyglot", {}, tmp_path)
    assert outcome.status == "halted" and "robots" in outcome.detail


def test_a_transport_failure_is_blocked_not_halted(tmp_path, monkeypatch):
    def _boom(source, ctx, **kw):
        raise ConnectionError("network down")

    monkeypatch.setattr("langatlas_orchestrator.jobs.mirror_refresh.refresh", _boom)
    outcome = _run_item(_FakeCtx(), "pldb", {}, tmp_path)
    assert outcome.status == "blocked"


def test_only_the_two_non_stage_2_stubs_remain():
    """The final state of jobs/deferred.py after Stage 2E: the Umami export (Stage 6) and
    the 18-month backstop sweep (Stage 5)."""
    from langatlas_orchestrator.registry import registered_kinds

    import langatlas_orchestrator.jobs  # noqa: F401
    for kind in ("monthly-link-checker", "quarterly-edition-check",
                 "monthly-finding-aid-mirror-refresh", "nightly-verification"):
        assert kind in registered_kinds()
    with pytest.raises(NotImplementedError):
        get_job_kind("monthly-demand-export")[0]({}, None)
    with pytest.raises(NotImplementedError):
        get_job_kind("backstop-sweep-18mo")[0]({}, None)
