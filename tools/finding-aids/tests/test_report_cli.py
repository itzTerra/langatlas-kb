import pytest

from langatlas_finding_aids.report import main


def test_no_subcommand_is_an_error_not_a_silent_zero(capsys):
    with pytest.raises(SystemExit):
        main([])


def test_lookup_prints_the_caveat_first(monkeypatch, capsys):
    from langatlas_finding_aids.results import FindingAidResult

    monkeypatch.setattr(
        "langatlas_finding_aids.report.search_finding_aids",
        lambda ctx, query, **kw: [FindingAidResult(
            source="pldb", item_id="rust", label="Rust", fields={},
            url="https://pldb.io/concepts/rust.html",
            retrieved_at="2026-09-08T00:00:00Z", mirror_version="abc")])
    monkeypatch.setattr("langatlas_finding_aids.report._run_context", _FakeRun)

    assert main(["lookup", "rust"]) == 0
    out = capsys.readouterr().out
    assert out.lstrip().startswith("Finding-aid results are LEADS")


class _FakeRun:
    """Stands in for `RunContext.start(...)` as a context manager, so the CLI tests never
    mint a transcript or touch the private tier."""

    def __init__(self, *args, **kwargs):
        self.run_id = "run-1"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    class _W:
        def append(self, **event):
            pass

    writer = _W()

    def tool_result(self, *, tool, text, source_id=None, kind="source-chunk"):
        return text

    def close(self, **kwargs):
        pass
