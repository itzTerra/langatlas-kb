import pytest

from langatlas_finding_aids.config import FindingAidsConfig
from langatlas_finding_aids.query import render_for_prompt, search_finding_aids
from langatlas_finding_aids.results import FindingAidResult


class _Ctx:
    def __init__(self):
        self.run_id = "run-1"
        self.tool_results = []
        self.events = []

    class _W:
        def __init__(self, outer):
            self.outer = outer

        def append(self, **event):
            self.outer.events.append(event)

    @property
    def writer(self):
        return self._W(self)

    def tool_result(self, *, tool, text, source_id=None, kind="source-chunk"):
        self.tool_results.append((tool, source_id, text))
        return f"<delimited kind={kind}>{text}</delimited>"


def _result(source) -> FindingAidResult:
    return FindingAidResult(source=source, item_id="x", label="X", fields={"a": "b"},
                            url=f"https://{source}.test/x",
                            retrieved_at="2026-09-08T00:00:00Z")


@pytest.fixture
def config():
    return FindingAidsConfig.load()


@pytest.fixture
def patched(monkeypatch):
    calls = []

    def _make(source, *, fail=False):
        def _query(*args, **kwargs):
            calls.append(source)
            if fail:
                raise RuntimeError(f"{source} is down")
            return [_result(source)]
        return _query

    return _make, calls


def test_it_fans_out_over_every_enabled_source(monkeypatch, config, patched):
    make, calls = patched
    for source in ("pldb", "hyperpolyglot"):
        monkeypatch.setattr(f"langatlas_finding_aids.query.query_{source}", make(source))
    for source in ("wikidata", "wikipedia"):
        monkeypatch.setattr(f"langatlas_finding_aids.query.query_{source}", make(source))
    results = search_finding_aids(_Ctx(), "rust", config=config)
    assert sorted(calls) == ["hyperpolyglot", "pldb", "wikidata", "wikipedia"]
    assert len(results) == 4


def test_an_explicit_source_list_narrows_the_fan_out(monkeypatch, config, patched):
    make, calls = patched
    monkeypatch.setattr("langatlas_finding_aids.query.query_pldb", make("pldb"))
    search_finding_aids(_Ctx(), "rust", sources=["pldb"], config=config)
    assert calls == ["pldb"]


def test_one_failing_adapter_never_sinks_the_others(monkeypatch, config, patched):
    """A missing mirror or a Wikidata outage must degrade to fewer leads, not to no
    survey: this tool is never load-bearing for correctness, so a partial answer is
    strictly better than an exception in an agent's tool loop."""
    make, _ = patched
    monkeypatch.setattr("langatlas_finding_aids.query.query_pldb", make("pldb"))
    monkeypatch.setattr("langatlas_finding_aids.query.query_wikidata",
                        make("wikidata", fail=True))
    ctx = _Ctx()
    results = search_finding_aids(ctx, "rust", sources=["pldb", "wikidata"],
                                  config=config)
    assert [r.source for r in results] == ["pldb"]
    assert any("wikidata" in str(event.get("content", "")) for event in ctx.events)


def test_rendering_opens_with_the_non_citability_caveat(config):
    from langatlas_finding_aids.results import NON_CITABLE_CAVEAT

    rendered = render_for_prompt(_Ctx(), [_result("pldb")])
    assert rendered.startswith(NON_CITABLE_CAVEAT)


def test_every_rendered_result_goes_through_the_d31_door(config):
    ctx = _Ctx()
    render_for_prompt(ctx, [_result("pldb"), _result("wikidata")])
    assert len(ctx.tool_results) == 2
    assert {call[0] for call in ctx.tool_results} == {"search_finding_aids"}


def test_no_results_renders_to_an_empty_string(config):
    """Distinguishable from 'leads found but blank' — the caveat alone would read as a
    result block with nothing in it."""
    assert render_for_prompt(_Ctx(), []) == ""


def test_the_rendered_block_carries_the_advisory_candidate_source(config):
    rendered = render_for_prompt(_Ctx(), [_result("hyperpolyglot")])
    assert "candidate_source: hyperpolyglot" in rendered
