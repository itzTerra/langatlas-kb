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


def test_the_other_five_stubs_are_still_deferred():
    from langatlas_orchestrator.registry import get_job_kind
    from pathlib import Path
    for kind in ("monthly-link-checker", "quarterly-edition-check",
                 "monthly-finding-aid-mirror-refresh", "monthly-demand-export",
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


def test_a_bounced_fact_is_blocked_not_halted(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job
    from langatlas_ingest.verify.admissibility import FactOutcome
    from langatlas_ingest.verify.batch import BatchResult

    monkeypatch.setattr(job, "_verify_fact", lambda *a, **k: (
        BatchResult(verdicts=()),
        FactOutcome(fact_id="f-1", admissible=False, verification="failed",
                    confidence=None, bounced=True, bounce_reason="narrow the claim")))
    outcome = job._run_item(object(), "f-1", {}, tmp_path)
    # A bounce is a re-attemptable outcome in the driver's own model, not a human-needed
    # halt: the proposer gets another try within the budget.
    assert outcome.status == "blocked"


def test_an_exhausted_bounce_budget_halts(tmp_path, monkeypatch):
    import langatlas_orchestrator.jobs.verification as job
    from langatlas_ingest.verify.admissibility import FactOutcome
    from langatlas_ingest.verify.batch import BatchResult

    monkeypatch.setattr(job, "_verify_fact", lambda *a, **k: (
        BatchResult(verdicts=()),
        FactOutcome(fact_id="f-1", admissible=False, verification="failed",
                    confidence=None, exhausted=True,
                    bounce_reason="no citation supports the claim")))
    outcome = job._run_item(object(), "f-1", {}, tmp_path)
    assert outcome.status == "halted"


def test_the_job_spec_still_loads():
    from pathlib import Path
    from langatlas_orchestrator.spec import load_batch_spec
    spec = load_batch_spec(Path("../../config/jobs/nightly-verification.yaml").resolve())
    assert spec.kind == "nightly-verification"
    assert spec.budget.max_calls
