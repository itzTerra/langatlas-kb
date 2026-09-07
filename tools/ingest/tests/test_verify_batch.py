import pytest
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.errors import CanaryPassed
from langatlas_ingest.verify.batch import BatchResult, load_canary_ids, verify_batch
from langatlas_ingest.verify.inputs import CitationInput, ClaimInput
from langatlas_ingest.verify.verdicts import PairVerdict

CONFIG = IngestConfig.load()


def work(n):
    return [(ClaimInput(fact_id=f"f-{i:012d}", claim=f"instance-exists(fi.x.y{i})"),
             CitationInput("s", "p. 1")) for i in range(n)]


class FakeWriter:
    def __init__(self):
        self.events = []
        self.seq = 0

    def append(self, *, role, content, **kw):
        self.seq += 1
        self.events.append((role, content))
        return type("E", (), {"seq": self.seq})()


class FakeManifest:
    def __init__(self):
        self.msg_anchors = {}


class FakeCtx:
    def __init__(self):
        self.run_id = "2026-09-06-verify-batch-01"
        self.writer = FakeWriter()
        self.manifest = FakeManifest()


def verdict_for(claim, citation, name="supported"):
    return PairVerdict(fact_id=claim.fact_id, source_id=citation.source_id,
                       locator=citation.locator, verdict=name)


def test_every_pair_gets_a_verdict(monkeypatch):
    monkeypatch.setattr("langatlas_ingest.verify.batch.verify_pair",
                        lambda ctx, conn, **kw: verdict_for(kw["claim"], kw["citation"]))
    got = verify_batch(FakeCtx(), None, work(3), config=CONFIG, deps=object(),
                       canary_ids=[])
    assert isinstance(got, BatchResult)
    assert len(got.verdicts) == 3
    assert got.halted is False


def test_each_pair_gets_its_own_transcript_anchor(monkeypatch):
    seen = []

    def fake(ctx, conn, **kw):
        seen.append(kw["anchor"])
        return verdict_for(kw["claim"], kw["citation"])

    monkeypatch.setattr("langatlas_ingest.verify.batch.verify_pair", fake)
    ctx = FakeCtx()
    verify_batch(ctx, None, work(2), config=CONFIG, deps=object(), canary_ids=[])
    assert all(a and a.startswith(ctx.run_id + "#msg-") for a in seen)
    assert len(set(seen)) == 2
    # Section 7.10: the manifest carries per-claim anchors so each fact's "AI chat" link
    # lands on its own exchange, not on the top of a 4,000-pair batch.
    assert set(ctx.manifest.msg_anchors) == {"f-000000000000", "f-000000000001"}


def test_a_pair_that_raises_is_recorded_as_source_unavailable(monkeypatch):
    def fake(ctx, conn, **kw):
        if kw["claim"].fact_id.endswith("0001"):
            raise RuntimeError("provider outage")
        return verdict_for(kw["claim"], kw["citation"])

    monkeypatch.setattr("langatlas_ingest.verify.batch.verify_pair", fake)
    got = verify_batch(FakeCtx(), None, work(3), config=CONFIG, deps=object(),
                       canary_ids=[])
    # A mid-batch outage must produce a legible partial result, not lose every verdict
    # computed so far.
    assert len(got.verdicts) == 3
    assert got.verdicts[1].verdict == "source-unavailable"


def test_a_canary_that_passes_halts_the_batch(monkeypatch):
    calls = []

    def fake(ctx, conn, **kw):
        calls.append(kw["claim"].fact_id)
        return verdict_for(kw["claim"], kw["citation"])

    monkeypatch.setattr("langatlas_ingest.verify.batch.verify_pair", fake)
    monkeypatch.setattr("langatlas_ingest.verify.batch.run_canaries",
                        lambda *a, **k: ["v-fabricated-0001"])
    got = verify_batch(FakeCtx(), None, work(3), config=CONFIG, deps=object(),
                       canary_ids=["v-fabricated-0001"])
    assert got.halted is True
    assert "v-fabricated-0001" in got.halt_reason
    assert got.verdicts == ()
    assert calls == []           # no real pair ran after a canary passed


def test_a_clean_canary_run_lets_the_batch_proceed(monkeypatch):
    monkeypatch.setattr("langatlas_ingest.verify.batch.verify_pair",
                        lambda ctx, conn, **kw: verdict_for(kw["claim"], kw["citation"]))
    monkeypatch.setattr("langatlas_ingest.verify.batch.run_canaries",
                        lambda *a, **k: [])
    got = verify_batch(FakeCtx(), None, work(2), config=CONFIG, deps=object(),
                       canary_ids=["v-fabricated-0001"])
    assert got.halted is False
    assert got.canaries_run == 1


def test_an_empty_canary_list_skips_the_canary_stage(monkeypatch):
    monkeypatch.setattr("langatlas_ingest.verify.batch.verify_pair",
                        lambda ctx, conn, **kw: verdict_for(kw["claim"], kw["citation"]))
    got = verify_batch(FakeCtx(), None, work(1), config=CONFIG, deps=object(),
                       canary_ids=[])
    assert got.canaries_run == 0


def test_the_committed_canary_file_loads():
    # Empty until Task 18; the loader must handle that without an exception.
    assert isinstance(load_canary_ids(), list)


def test_a_batch_summary_reaches_the_transcript(monkeypatch):
    monkeypatch.setattr("langatlas_ingest.verify.batch.verify_pair",
                        lambda ctx, conn, **kw: verdict_for(kw["claim"], kw["citation"]))
    ctx = FakeCtx()
    verify_batch(ctx, None, work(2), config=CONFIG, deps=object(), canary_ids=[])
    assert any("verification batch" in content.lower()
               for _role, content in ctx.writer.events)
