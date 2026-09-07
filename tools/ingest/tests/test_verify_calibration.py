import pytest
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.goldens.items import Citation, Claim, VerifierItem
from langatlas_ingest.goldens.score import VerdictOutcome
from langatlas_ingest.verify.calibration import GoldenVerifier
from langatlas_ingest.verify.verdicts import Assertion, PairVerdict


def item(**kw):
    claim = kw.pop("claim", Claim(kind="instance-exists",
                                  text="instance-exists(fi.rust.pattern-matching, status=present)"))
    base = dict(id="v-test-0001", stratum="correct", expected_verdict="supported",
                claim=claim, citation=Citation(source="s", locator="p. 1"))
    base.update(kw)
    return VerifierItem(**base)


class FakeDeps:
    pass


def test_the_verifier_returns_a_verdict_outcome(monkeypatch):
    monkeypatch.setattr(
        "langatlas_ingest.verify.calibration.verify_pair",
        lambda ctx, conn, **kw: PairVerdict(
            fact_id=kw["claim"].fact_id, source_id="s", locator="p. 1",
            verdict="supported",
            per_assertion=(Assertion("presence", "t", "supported", "g"),),
            annotations=("quote-found-elsewhere",), model="deepseek-v4"))
    verifier = GoldenVerifier(config=IngestConfig.load(), deps=FakeDeps(), conn=None,
                              ctx=object())
    got = verifier(item())
    assert isinstance(got, VerdictOutcome)
    assert got.verdict == "supported"
    assert got.annotations == ("quote-found-elsewhere",)
    assert got.model == "deepseek-v4"
    assert got.per_assertion[0]["kind"] == "presence"


def test_the_golden_items_own_whitelist_is_what_reaches_the_verifier(monkeypatch):
    seen = {}

    def fake(ctx, conn, **kw):
        seen["claim"] = kw["claim"]
        seen["citation"] = kw["citation"]
        return PairVerdict(fact_id=kw["claim"].fact_id, source_id="s", locator="p. 1",
                           verdict="supported")

    monkeypatch.setattr("langatlas_ingest.verify.calibration.verify_pair", fake)
    golden = item(claim=Claim(kind="instance-exists",
                              text="instance-exists(fi.c.generics, status=absent)",
                              status="absent", absence_scope="the type chapter",
                              feature_aliases=("generics",)))
    GoldenVerifier(config=IngestConfig.load(), deps=FakeDeps(), conn=None,
                   ctx=object())(golden)
    # The claim's fact_id is derived from its text, never carried separately: an item
    # whose stored id disagreed with its claim would be a silently wrong test.
    assert seen["claim"].fact_id == golden.claim.fact_id
    assert seen["claim"].status == "absent"
    assert seen["claim"].feature_aliases == ("generics",)


def test_the_stratum_and_expected_verdict_never_reach_the_verifier(monkeypatch):
    seen = {}

    def fake(ctx, conn, **kw):
        seen.update(kw)
        return PairVerdict(fact_id=kw["claim"].fact_id, source_id="s", locator="p. 1",
                           verdict="supported")

    monkeypatch.setattr("langatlas_ingest.verify.calibration.verify_pair", fake)
    GoldenVerifier(config=IngestConfig.load(), deps=FakeDeps(), conn=None,
                   ctx=object())(item(stratum="overstated-claim",
                                      expected_verdict="partial"))
    rendered = repr(seen)
    assert "overstated-claim" not in rendered
    assert "v-test-0001" not in rendered


class FakeConn:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeRunContext:
    """Stands in for the real `RunContext`, whose `close()` is what finalizes the
    transcript and writes the run's `manifest.yaml`."""

    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _fake_session(monkeypatch):
    conn, ctx = FakeConn(), FakeRunContext()
    monkeypatch.setattr("langatlas_ingest.db.connect", lambda dsn=None: conn)
    monkeypatch.setattr("langatlas_pipeline.providers.core.RunContext.start",
                        classmethod(lambda cls, **kw: ctx))
    monkeypatch.setattr("langatlas_ingest.verify.pipeline.VerifyDeps.build",
                        classmethod(lambda cls, conn, ctx, **kw: FakeDeps()))
    monkeypatch.setattr(
        "langatlas_ingest.verify.calibration.verify_pair",
        lambda ctx, conn, **kw: PairVerdict(fact_id=kw["claim"].fact_id, source_id="s",
                                            locator="p. 1", verdict="supported"))
    return conn, ctx


def test_closing_releases_the_session_it_opened(monkeypatch):
    conn, ctx = _fake_session(monkeypatch)
    verifier = GoldenVerifier()
    verifier(item())
    assert (conn.closed, ctx.closed) == (False, False)
    verifier.close()
    assert conn.closed is True
    assert ctx.closed is True


def test_a_golden_scoring_run_closes_the_verifiers_session(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from langatlas_ingest import cli

    conn, ctx = _fake_session(monkeypatch)
    verifier = GoldenVerifier()
    monkeypatch.setattr("langatlas_ingest.goldens.runner.load_entry_point",
                        lambda dotted: verifier)
    verifier(item())               # the session is open before the run finishes

    cli._cmd_golden_score(SimpleNamespace(
        verifier="x:y", controversy_assessor=None, verifier_dir=str(tmp_path),
        controversy_dir=None, include_held_out=False, json=None))
    # `RunContext.close()` writes manifest.yaml with the run's stats; a calibration run
    # whose whole point is a published, audited number cannot leave it unwritten.
    assert ctx.closed is True
    assert conn.closed is True


def test_the_session_is_closed_even_when_the_run_raises(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from langatlas_ingest import cli

    conn, ctx = _fake_session(monkeypatch)
    verifier = GoldenVerifier()
    verifier(item())
    monkeypatch.setattr("langatlas_ingest.goldens.runner.load_entry_point",
                        lambda dotted: verifier)

    def boom(*a, **k):
        raise RuntimeError("scoring blew up")

    monkeypatch.setattr("langatlas_ingest.goldens.runner.run_verifier_goldens", boom)
    with pytest.raises(RuntimeError):
        cli._cmd_golden_score(SimpleNamespace(
            verifier="x:y", controversy_assessor=None, verifier_dir=str(tmp_path),
            controversy_dir=None, include_held_out=False, json=None))
    assert ctx.closed is True


def test_an_injected_session_is_never_closed_by_the_verifier():
    # Closing collaborators this instance never opened would break the caller that still
    # owns them (tests, and any harness building its own session).
    conn, ctx = FakeConn(), FakeRunContext()
    GoldenVerifier(config=IngestConfig.load(), deps=FakeDeps(), conn=conn,
                   ctx=ctx).close()
    assert (conn.closed, ctx.closed) == (False, False)


def test_the_config_names_this_entry_point():
    # `golden-score` resolves this dotted path; if it drifts, 2B's harness reports
    # "no verifier registered" instead of scoring 2D's work.
    assert IngestConfig.load().verifier_entry_point == \
        "langatlas_ingest.verify.calibration:verify_golden_item"


def test_the_entry_point_resolves():
    from langatlas_ingest.goldens.runner import load_entry_point
    assert callable(load_entry_point(
        "langatlas_ingest.verify.calibration:verify_golden_item"))
