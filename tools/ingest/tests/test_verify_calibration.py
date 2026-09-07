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


def test_the_config_names_this_entry_point():
    # `golden-score` resolves this dotted path; if it drifts, 2B's harness reports
    # "no verifier registered" instead of scoring 2D's work.
    assert IngestConfig.load().verifier_entry_point == \
        "langatlas_ingest.verify.calibration:verify_golden_item"


def test_the_entry_point_resolves():
    from langatlas_ingest.goldens.runner import load_entry_point
    assert callable(load_entry_point(
        "langatlas_ingest.verify.calibration:verify_golden_item"))
