from pathlib import Path

import pytest

from langatlas_ingest.currency.links import FetchedPage
from langatlas_orchestrator.jobs.link_checker import _enumerate, _run_item
from langatlas_orchestrator.registry import get_job_kind


class _FakeWriter:
    """Mirrors test_verification_job.py's FakeWriter — `_run_item` logs its conclusion
    through `ctx.writer.append` the same way `verification.py` does."""

    def __init__(self):
        self.events = []

    def append(self, *, role, content, **kw):
        self.events.append((role, content))
        return type("E", (), {"seq": len(self.events)})()


class _FakeCtx:
    def __init__(self):
        self.run_id = "run-1"
        self.tool_results = []
        self.writer = _FakeWriter()

    def tool_result(self, *, tool, text, source_id=None, kind="source-chunk"):
        self.tool_results.append((tool, source_id))
        return text


def _write_sources(root: Path):
    (root / "sources").mkdir(parents=True)
    (root / "sources" / "with-url.yaml").write_text(
        "id: with-url\ntype: book\ntitle: T\nURL: https://example.test/ref#lexical\n"
        "custom:\n  tier: B\n  grounding: reference-implementation-docs\n")
    (root / "sources" / "doi-only.yaml").write_text(
        "id: doi-only\ntype: article-journal\ntitle: T2\nDOI: 10.1000/x\n"
        "custom:\n  tier: A\n  grounding: third-party-reference\n")
    (root / "sources" / "_tombstones.yaml").write_text("tombstones: []\n")


def test_registered_on_import():
    import langatlas_orchestrator.jobs  # noqa: F401
    enumerator, item_runner = get_job_kind("monthly-link-checker")
    assert enumerator is _enumerate and item_runner is _run_item


def test_enumerate_takes_only_url_bearing_sources(tmp_path):
    """§4.4 scopes the link-checker to URL-locator sources; a DOI-only record has no
    live link to check and would be a permanent no-op checkpoint row."""
    _write_sources(tmp_path)
    assert _enumerate({}, tmp_path) == ["with-url"]


def test_enumerate_honours_an_explicit_subset(tmp_path):
    _write_sources(tmp_path)
    assert _enumerate({"source_ids": ["doi-only"]}, tmp_path) == []


@pytest.mark.db
def test_run_item_records_the_check_and_files_findings(tmp_path, monkeypatch, dsn):
    from langatlas_ingest.db import connect, migrate
    from langatlas_ingest.store import SourcingQueue

    _write_sources(tmp_path)
    monkeypatch.setenv("LANGATLAS_DSN", dsn)
    with connect(dsn) as conn:
        migrate(conn)

    page = FetchedPage(status=200, text="<p>no anchor here</p>")
    monkeypatch.setattr("langatlas_orchestrator.jobs.link_checker._http_fetch",
                        lambda ctx: (lambda url: page))

    outcome = _run_item(_FakeCtx(), "with-url", {}, tmp_path)

    assert outcome.status == "done"
    assert "anchor-missing" in outcome.detail
    with connect(dsn) as conn:
        assert [e["reason"] for e in SourcingQueue(conn).open_entries(
            kind="link-checker")] == ["anchor-missing"]


@pytest.mark.db
def test_a_dead_link_is_a_finding_not_a_halt(tmp_path, monkeypatch, dsn):
    """A dead link is exactly what this job exists to find. Halting on one would stop
    the run at the first bad URL and never check the rest of the corpus."""
    from langatlas_ingest.db import connect, migrate

    _write_sources(tmp_path)
    monkeypatch.setenv("LANGATLAS_DSN", dsn)
    with connect(dsn) as conn:
        migrate(conn)

    def _boom(url):
        raise ConnectionError("gone")

    monkeypatch.setattr("langatlas_orchestrator.jobs.link_checker._http_fetch",
                        lambda ctx: _boom)
    outcome = _run_item(_FakeCtx(), "with-url", {}, tmp_path)
    assert outcome.status == "done" and "link-dead" in outcome.detail


@pytest.mark.db
def test_an_unreachable_database_blocks_rather_than_completing(tmp_path, monkeypatch):
    _write_sources(tmp_path)
    monkeypatch.setenv("LANGATLAS_DSN",
                       "postgresql://nobody@127.0.0.1:1/none?connect_timeout=1")
    outcome = _run_item(_FakeCtx(), "with-url", {}, tmp_path)
    assert outcome.status == "blocked" and "database" in outcome.detail
