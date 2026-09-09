import pytest
from langatlas_orchestrator.registry import get_job_kind, registered_kinds

# A top-level (collection-time) import, matching test_capability_probe_job.py's and
# test_deferred_jobs.py's established pattern: this runs every jobs/*.py module's
# register_job_kind() once against the *real* global registry, before any per-test
# `_isolated_registry` fixture takes its snapshot copy. Without it, a test-body-only
# `import langatlas_orchestrator.jobs...` is a no-op on every test after the first (the
# module is already in sys.modules) and the isolated copy each test starts from would
# never see any job kind when this file runs alone.
import langatlas_orchestrator.jobs  # noqa: E402,F401


def test_nightly_verification_is_registered_for_real():
    import langatlas_orchestrator.jobs  # noqa: F401 — registration is an import side effect
    assert "nightly-verification" in registered_kinds()


def test_it_is_no_longer_a_deferred_stub():
    import langatlas_orchestrator.jobs.verification  # noqa: F401
    enumerate_fn, _run = get_job_kind("nightly-verification")
    # The stub raised NotImplementedError from `enumerate`; the real one returns a list.
    from pathlib import Path
    assert isinstance(enumerate_fn({}, Path(".")), list)


def test_the_other_three_stubs_are_still_deferred():
    from langatlas_orchestrator.registry import get_job_kind
    from pathlib import Path
    for kind in ("monthly-finding-aid-mirror-refresh", "monthly-demand-export",
                 "backstop-sweep-18mo"):
        enumerate_fn, _ = get_job_kind(kind)
        with pytest.raises(NotImplementedError):
            enumerate_fn({}, Path("."))


def test_enumeration_lists_facts_with_citations(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job

    monkeypatch.setattr(job, "_derived_facts", lambda repo_root: [
        {"fact_id": "f-000000000001", "claim": "c1",
         "sources": [{"source": "s", "locator": "p. 1"}]},
        {"fact_id": "f-000000000002", "claim": "c2", "sources": []},
    ])
    keys = job._enumerate({}, tmp_path)
    # A fact with no citations has nothing to verify; enumerating it would burn a
    # checkpoint row per night forever.
    assert keys == ["f-000000000001"]


def test_a_fact_id_filter_narrows_enumeration(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job

    monkeypatch.setattr(job, "_derived_facts", lambda repo_root: [
        {"fact_id": "f-1", "claim": "c1", "sources": [{"source": "s", "locator": "p. 1"}]},
        {"fact_id": "f-2", "claim": "c2", "sources": [{"source": "s", "locator": "p. 2"}]},
    ])
    assert job._enumerate({"fact_ids": ["f-2"]}, tmp_path) == ["f-2"]


def test_a_halted_batch_halts_the_item(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job
    from langatlas_ingest.verify.batch import BatchResult

    monkeypatch.setattr(job, "_verify_fact",
                        lambda *a, **k: (BatchResult(halted=True,
                                                     halt_reason="canaries passed: v-1"),
                                         None))
    outcome = job._run_item(object(), "f-1", {}, tmp_path)
    assert outcome.status == "halted"
    assert "canaries passed" in outcome.detail


def test_an_admitted_fact_is_done(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job
    from langatlas_ingest.verify.admissibility import FactOutcome
    from langatlas_ingest.verify.batch import BatchResult

    monkeypatch.setattr(job, "_verify_fact", lambda *a, **k: (
        BatchResult(verdicts=()),
        FactOutcome(fact_id="f-1", admissible=True, verification="verified",
                    confidence="high")))
    outcome = job._run_item(object(), "f-1", {}, tmp_path)
    assert outcome.status == "done"
    assert "verified" in outcome.detail


def test_a_bounced_fact_is_done_not_blocked(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job
    from langatlas_ingest.verify.admissibility import FactOutcome
    from langatlas_ingest.verify.batch import BatchResult

    monkeypatch.setattr(job, "_verify_fact", lambda *a, **k: (
        BatchResult(verdicts=()),
        FactOutcome(fact_id="f-1", admissible=False, verification="failed",
                    confidence=None, bounced=True, bounce_reason="narrow the claim")))
    outcome = job._run_item(object(), "f-1", {}, tmp_path)
    # A citation that did not check out is this gate's normal output, and the item is
    # finished: the bounce is filed. `blocked` would pause the whole night's run on the
    # first such fact.
    assert outcome.status == "done"
    assert "narrow the claim" in outcome.detail


def test_an_exhausted_bounce_budget_is_done_with_the_reason(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job
    from langatlas_ingest.verify.admissibility import FactOutcome
    from langatlas_ingest.verify.batch import BatchResult

    monkeypatch.setattr(job, "_verify_fact", lambda *a, **k: (
        BatchResult(verdicts=()),
        FactOutcome(fact_id="f-1", admissible=False, verification="failed",
                    confidence=None, exhausted=True,
                    bounce_reason="no citation supports the claim")))
    outcome = job._run_item(object(), "f-1", {}, tmp_path)
    # The queue entry stays open for a human, but this fact's verification is over —
    # the remaining 199 facts of the night still get verified.
    assert outcome.status == "done"
    assert "exhausted" in outcome.detail


def test_an_unreachable_database_is_blocked(tmp_path, monkeypatch):
    import psycopg
    import langatlas_orchestrator.jobs.verification as job

    def boom(*a, **k):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(job, "_verify_fact", boom)
    outcome = job._run_item(object(), "f-1", {}, tmp_path)
    # `blocked` is reserved for exactly this: infrastructure, retry the whole batch.
    assert outcome.status == "blocked"
    assert "database unavailable" in outcome.detail


class FakeWriter:
    def __init__(self):
        self.events = []
        self.seq = 0

    def append(self, *, role, content, **kw):
        self.seq += 1
        self.events.append((role, content))
        return type("E", (), {"seq": self.seq})()


class FakeCtx:
    def __init__(self, run_id="2026-09-07-nightly-verification-01"):
        self.run_id = run_id
        self.writer = FakeWriter()
        self.manifest = type("M", (), {"msg_anchors": {}})()


class FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeQueue:
    def __init__(self, *a, **k):
        self.filed = []

    def file(self, **kw):
        self.filed.append(kw)
        return len(self.filed)

    def open_entries(self, **kw):
        return []

    def bounce(self, entry_id):
        pass


class FakeSourceFacts:
    tier = "A"


class FakeDeps:
    source_facts = {"s": FakeSourceFacts()}


def _fake_session(monkeypatch, job, verdicts, *, canary_calls=None,
                  canary_ids=("v-fabricated-0001",)):
    """Replace everything `_verify_fact` reaches the world through, leaving the job's own
    composition (and the real `decide_fact`) running for real."""
    monkeypatch.setattr(job, "connect", lambda dsn=None: FakeConn())
    monkeypatch.setattr(job, "VerdictLedger", lambda *a, **k: FakeConn())
    monkeypatch.setattr(job.VerifyDeps, "build",
                        classmethod(lambda cls, conn, ctx, **kw: FakeDeps()))
    monkeypatch.setattr(job, "SourcingQueue", FakeQueue)
    monkeypatch.setattr(job, "load_canary_ids", lambda: list(canary_ids))

    def fake_canaries(ctx, conn, *, config, deps, canary_ids, items=None):
        if canary_calls is not None:
            canary_calls.append(list(canary_ids))
        return []

    monkeypatch.setattr(job, "run_canaries", fake_canaries)

    from langatlas_ingest.verify.batch import BatchResult

    monkeypatch.setattr(job, "verify_batch",
                        lambda ctx, conn, work, **kw: BatchResult(verdicts=verdicts))


def _seed(monkeypatch, job, tmp_path, facts):
    monkeypatch.setattr(job, "_derived_facts", lambda repo_root: facts)
    return job._enumerate({}, tmp_path)


def test_a_real_rejection_is_done_not_blocked(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job
    from langatlas_ingest.verify.verdicts import PairVerdict

    fact = {"fact_id": "f-1", "claim": "c",
            "sources": [{"source": "s", "locator": "p. 1"}]}
    assert _seed(monkeypatch, job, tmp_path, [fact]) == ["f-1"]
    _fake_session(monkeypatch, job, (PairVerdict(fact_id="f-1", source_id="s",
                                                 locator="p. 1",
                                                 verdict="unsupported"),))
    outcome = job._run_item(FakeCtx(), "f-1", {}, tmp_path)
    # The whole path from a real `unsupported` verdict through the real admissibility
    # rule: the fact does not enter, and the night's run keeps going.
    assert outcome.status == "done"


def test_the_canary_preflight_runs_once_per_run_not_once_per_fact(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job
    from langatlas_ingest.verify.verdicts import PairVerdict

    facts = [{"fact_id": f"f-{i}", "claim": "c",
              "sources": [{"source": "s", "locator": "p. 1"}]} for i in (1, 2, 3)]
    _seed(monkeypatch, job, tmp_path, facts)
    calls: list[list[str]] = []
    _fake_session(monkeypatch, job,
                  (PairVerdict(fact_id="f-1", source_id="s", locator="p. 1",
                               verdict="supported"),),
                  canary_calls=calls)
    ctx = FakeCtx()
    for fact in facts:
        job._run_item(ctx, fact["fact_id"], {}, tmp_path)
    # Section 6.2's canaries are a per-batch preflight. Once Task 18 fills the list in,
    # running them per fact would be a full provider pass over every canary ~200 times
    # a night.
    assert len(calls) == 1


def test_a_new_run_runs_the_canaries_again(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job
    from langatlas_ingest.verify.verdicts import PairVerdict

    facts = [{"fact_id": "f-1", "claim": "c",
              "sources": [{"source": "s", "locator": "p. 1"}]}]
    _seed(monkeypatch, job, tmp_path, facts)
    calls: list[list[str]] = []
    _fake_session(monkeypatch, job,
                  (PairVerdict(fact_id="f-1", source_id="s", locator="p. 1",
                               verdict="supported"),),
                  canary_calls=calls)
    job._run_item(FakeCtx("run-a"), "f-1", {}, tmp_path)
    job._run_item(FakeCtx("run-b"), "f-1", {}, tmp_path)
    assert len(calls) == 2


def test_a_passing_canary_halts_before_any_fact_is_verified(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job

    facts = [{"fact_id": "f-1", "claim": "c",
              "sources": [{"source": "s", "locator": "p. 1"}]}]
    _seed(monkeypatch, job, tmp_path, facts)
    _fake_session(monkeypatch, job, ())
    monkeypatch.setattr(job, "run_canaries",
                        lambda *a, **k: ["v-fabricated-0001"])

    def fail(*a, **k):
        raise AssertionError("no pair may be verified after a canary passed")

    monkeypatch.setattr(job, "verify_batch", fail)
    outcome = job._run_item(FakeCtx(), "f-1", {}, tmp_path)
    assert outcome.status == "halted"
    assert "v-fabricated-0001" in outcome.detail


def test_the_whole_store_is_derived_once_per_run(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job
    from langatlas_ingest.verify.verdicts import PairVerdict

    facts = [{"fact_id": f"f-{i}", "claim": "c",
              "sources": [{"source": "s", "locator": "p. 1"}]} for i in (1, 2, 3)]
    walks = []

    def counting(repo_root):
        walks.append(repo_root)
        return facts

    monkeypatch.setattr(job, "_derived_facts", counting)
    job._enumerate({}, tmp_path)
    _fake_session(monkeypatch, job,
                  (PairVerdict(fact_id="f-1", source_id="s", locator="p. 1",
                               verdict="supported"),))
    for fact in facts:
        job._run_item(FakeCtx(), fact["fact_id"], {}, tmp_path)
    # One `iter_store_records` + `derive_facts` walk for the run, not one per item.
    assert len(walks) == 1


def test_a_minted_contradiction_is_committed(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job
    from langatlas_commit.land import Landed
    from langatlas_ingest.verify.admissibility import FactOutcome
    from langatlas_ingest.verify.batch import BatchResult

    (tmp_path / job.CONTRADICTIONS_RECORD).write_text("contradictions: []\n")
    landed = []

    def fake_land(repo_root, record_path, content, **kw):
        landed.append((record_path, content, kw["chat_run_id"]))
        return Landed(commit_sha="abc1234")

    monkeypatch.setattr(job, "land_record", fake_land)
    monkeypatch.setattr(job, "_verify_fact", lambda *a, **k: (
        BatchResult(verdicts=()),
        FactOutcome(fact_id="f-1", admissible=True, verification="verified",
                    confidence="high", contradiction_ids=("c-0001",))))
    outcome = job._run_item(FakeCtx(), "f-1", {}, tmp_path)
    # D1: a canonical file the nightly run rewrites has to reach a commit, or the
    # unattended run just leaves a dirty working tree with no audit trail.
    assert outcome.status == "done"
    assert landed and landed[0][0] == job.CONTRADICTIONS_RECORD
    assert "abc1234" in outcome.detail


def test_a_register_that_will_not_land_is_not_reported_as_done(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job
    from langatlas_commit.land import UnsafeHalt
    from langatlas_ingest.verify.admissibility import FactOutcome
    from langatlas_ingest.verify.batch import BatchResult

    (tmp_path / job.CONTRADICTIONS_RECORD).write_text("contradictions: []\n")
    monkeypatch.setattr(job, "land_record",
                        lambda *a, **k: UnsafeHalt(commit_sha=None, diagnostic="conflict"))
    monkeypatch.setattr(job, "_verify_fact", lambda *a, **k: (
        BatchResult(verdicts=()),
        FactOutcome(fact_id="f-1", admissible=True, verification="verified",
                    confidence="high", contradiction_ids=("c-0001",))))
    assert job._run_item(FakeCtx(), "f-1", {}, tmp_path).status == "halted"


def test_a_fact_with_no_contradictions_never_touches_git(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job
    from langatlas_ingest.verify.admissibility import FactOutcome
    from langatlas_ingest.verify.batch import BatchResult

    def fail(*a, **k):
        raise AssertionError("nothing to land")

    monkeypatch.setattr(job, "land_record", fail)
    monkeypatch.setattr(job, "_verify_fact", lambda *a, **k: (
        BatchResult(verdicts=()),
        FactOutcome(fact_id="f-1", admissible=True, verification="verified",
                    confidence="high")))
    assert job._run_item(FakeCtx(), "f-1", {}, tmp_path).status == "done"


def test_the_job_spec_still_loads():
    from pathlib import Path
    from langatlas_orchestrator.spec import load_batch_spec
    spec = load_batch_spec(Path("../../config/jobs/nightly-verification.yaml").resolve())
    assert spec.kind == "nightly-verification"
    assert spec.budget.max_calls
