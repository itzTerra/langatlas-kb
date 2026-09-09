from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from langatlas_ingest.currency.links import FetchedPage
from langatlas_orchestrator.jobs.edition_check import _enumerate, _run_item
from langatlas_orchestrator.registry import get_job_kind


class _FakeWriter:
    """Mirrors test_link_checker_job.py's FakeWriter — `_run_item` logs its conclusion
    through `ctx.writer.append` the same way `verification.py` and `link_checker.py` do."""

    def __init__(self):
        self.events = []

    def append(self, *, role, content, **kw):
        self.events.append((role, content))
        return type("E", (), {"seq": len(self.events)})()


class _FakeCtx:
    def __init__(self):
        self.run_id = "run-1"
        self.writer = _FakeWriter()


def _write_sources(root: Path):
    (root / "sources").mkdir(parents=True)
    (root / "sources" / "spec.yaml").write_text(
        "id: spec\ntype: report\ntitle: S\nURL: https://example.test/spec\n"
        "custom:\n  tier: A\n  grounding: formal-spec\n  edition: N3220\n")
    (root / "sources" / "docs.yaml").write_text(
        "id: docs\ntype: book\ntitle: D\nURL: https://example.test/docs\n"
        "custom:\n  tier: B\n  grounding: reference-implementation-docs\n"
        "  edition: 3.14.7\n  edition_check_url: https://example.test/whatsnew\n")
    (root / "sources" / "no-edition.yaml").write_text(
        "id: no-edition\ntype: book\ntitle: N\nURL: https://example.test/n\n"
        "custom:\n  tier: B\n  grounding: third-party-reference\n")


def test_registered_on_import():
    import langatlas_orchestrator.jobs  # noqa: F401
    enumerator, item_runner = get_job_kind("quarterly-edition-check")
    assert enumerator is _enumerate and item_runner is _run_item


@pytest.mark.db
def test_enumerate_skips_sources_with_no_pinned_edition(tmp_path, monkeypatch, dsn):
    from langatlas_ingest.db import connect, migrate

    _write_sources(tmp_path)
    monkeypatch.setenv("LANGATLAS_DSN", dsn)
    with connect(dsn) as conn:
        migrate(conn)
    assert _enumerate({}, tmp_path) == ["docs", "spec"]


@pytest.mark.db
def test_enumerate_skips_sources_not_yet_due(tmp_path, monkeypatch, dsn):
    """The job runs monthly (plan decision 2); a formal-spec source checked 40 days ago
    is not due for another 50, so it must not be re-fetched."""
    from langatlas_ingest.currency.editions import EditionCheckResult
    from langatlas_ingest.currency.store import record_edition_check
    from langatlas_ingest.db import connect, migrate

    _write_sources(tmp_path)
    monkeypatch.setenv("LANGATLAS_DSN", dsn)
    with connect(dsn) as conn:
        migrate(conn)
        record_edition_check(conn, EditionCheckResult(
            source_id="spec", edition="N3220", url=None, matched=True, detail="",
            fetched=True))
        with conn.cursor() as cur:
            cur.execute("UPDATE source_edition_checks SET checked_at = %s"
                        " WHERE source_id = 'spec'",
                        (datetime.now(timezone.utc) - timedelta(days=40),))
    assert _enumerate({}, tmp_path) == ["docs"]


@pytest.mark.db
def test_a_match_files_nothing_and_records_the_check(tmp_path, monkeypatch, dsn):
    # Runs before the mismatch test below: both share the session-scoped `dsn` database
    # (no per-test schema reset, matching test_link_checker_job.py's identical fixture
    # use), so this test's "queue stays empty" assertion needs to see the source before
    # the mismatch test files a triage entry against it.
    from langatlas_ingest.currency.store import last_edition_check
    from langatlas_ingest.db import connect, migrate
    from langatlas_ingest.store import SourcingQueue

    _write_sources(tmp_path)
    monkeypatch.setenv("LANGATLAS_DSN", dsn)
    with connect(dsn) as conn:
        migrate(conn)
    monkeypatch.setattr("langatlas_orchestrator.jobs.edition_check._http_fetch",
                        lambda ctx: (lambda url: FetchedPage(200, "3.14.7 docs")))

    assert _run_item(_FakeCtx(), "docs", {}, tmp_path).detail == "ok"
    with connect(dsn) as conn:
        assert SourcingQueue(conn).open_entries(kind="edition-check") == []
        assert last_edition_check(conn, "docs") is not None


@pytest.mark.db
def test_a_mismatch_opens_a_triage_entry_and_never_reingests(tmp_path, monkeypatch, dsn):
    from langatlas_ingest.db import connect, migrate
    from langatlas_ingest.store import SourcingQueue

    _write_sources(tmp_path)
    monkeypatch.setenv("LANGATLAS_DSN", dsn)
    with connect(dsn) as conn:
        migrate(conn)
    monkeypatch.setattr("langatlas_orchestrator.jobs.edition_check._http_fetch",
                        lambda ctx: (lambda url: FetchedPage(200, "now shipping 3.15.0")))

    outcome = _run_item(_FakeCtx(), "docs", {}, tmp_path)

    assert outcome.status == "done" and "edition-mismatch" in outcome.detail
    with connect(dsn) as conn:
        entries = SourcingQueue(conn).open_entries(kind="edition-check")
    assert [e["reason"] for e in entries] == ["edition-mismatch"]
    assert "supersede" in entries[0]["detail"]
