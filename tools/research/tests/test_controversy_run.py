"""The per-record loop: what gets a model call, what gets a commit, and what neither."""
import pytest

from langatlas_research.controversy.assessor import Assessment
from langatlas_research.controversy.inputs import ControversyInputs, inputs_digest
from langatlas_research.controversy.ledger import AssessmentLedger
from langatlas_research.controversy.run import Deps, anchor_key, assess_record

FEATURE_YAML = """\
id: structural-typing
slug: structural-typing
name: Structural typing
layer: 2
summary:
  text: A type system in which compatibility is determined by structure.
  sources:
    - source: pierce-tapl-2002
      locator: p. 251
provenance:
  claim_origin: source-derived
"""


@pytest.fixture
def feature_repo(tmp_path):
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "structural-typing.yaml").write_text(FEATURE_YAML)
    return tmp_path


def _deps(monkeypatch, level=2, signals=("verdict:partial:base",), calls=None):
    """An assessor stub standing in for the university API; assembly is real."""
    def _assess(ctx, fact_id, inputs, *, alias, prompt=None):
        if calls is not None:
            calls.append(fact_id)
        return Assessment(fact_id=fact_id, level=level, signals=tuple(signals),
                          model="deepseek-v4-pro-thinking",
                          prompt="controversy-assessor@v-1a2b3c4d", run_id="r-1")
    return _assess


def test_anchor_key_recovers_the_field_path():
    assert anchor_key("node-definition(structural-typing, sha256-16=ab)") == "summary"
    assert anchor_key("characteristic(fi.rust.pattern-matching, c-exhaustive, sha256-16=ab)") \
        == "characteristics[c-exhaustive]"
    assert anchor_key("instance-exists(fi.rust.pattern-matching, present)") == "exists"


def test_a_contested_fact_gets_a_block_and_a_landed_commit(feature_repo, fake_ctx, monkeypatch):
    landed = []
    outcome = assess_record(
        fake_ctx, "features/structural-typing.yaml", repo_root=feature_repo,
        deps=Deps(assess=_deps(monkeypatch), escalate=None,
                  ledger=AssessmentLedger(feature_repo / "l.sqlite"),
                  land=lambda minted: landed.append(minted) or True,
                  alias="thinker", today="2026-09-17",
                  source_facts={}, contradictions=[], debates={},
                  verdict_ledger=type("L", (), {"latest_for": lambda self, f: []})()))
    assert outcome.assessed == 1
    assert outcome.changed is True
    assert "controversy:" in landed[0].text


def test_a_settled_fact_writes_nothing_and_lands_nothing(feature_repo, fake_ctx, monkeypatch):
    landed = []
    outcome = assess_record(
        fake_ctx, "features/structural-typing.yaml", repo_root=feature_repo,
        deps=Deps(assess=_deps(monkeypatch, level=0, signals=()), escalate=None,
                  ledger=AssessmentLedger(feature_repo / "l.sqlite"),
                  land=lambda minted: landed.append(minted) or True,
                  alias="thinker", today="2026-09-17", source_facts={}, contradictions=[],
                  debates={}, verdict_ledger=type("L", (), {"latest_for": lambda self, f: []})()))
    assert outcome.assessed == 1
    assert outcome.changed is False
    assert landed == []


def test_an_unchanged_digest_skips_the_model_entirely(feature_repo, fake_ctx, monkeypatch):
    """§6.4's free re-run. This is the property the nightly cadence depends on — without it a
    nightly batch re-pays for the whole store every night."""
    calls = []
    ledger = AssessmentLedger(feature_repo / "l.sqlite")
    deps = Deps(assess=_deps(monkeypatch, calls=calls), escalate=None, ledger=ledger,
                land=lambda minted: True, alias="thinker", today="2026-09-17",
                source_facts={}, contradictions=[], debates={},
                verdict_ledger=type("L", (), {"latest_for": lambda self, f: []})())
    assess_record(fake_ctx, "features/structural-typing.yaml", repo_root=feature_repo, deps=deps)
    second = assess_record(fake_ctx, "features/structural-typing.yaml", repo_root=feature_repo,
                           deps=deps)
    assert len(calls) == 1
    assert second.skipped == 1
    assert second.changed is False


def test_a_failed_land_leaves_no_ledger_row(feature_repo, fake_ctx, monkeypatch):
    """Finding 1: a row must not outlive the commit it describes. `land` returning falsy (red
    main, a validator error, push contention, a rebase conflict — `default_land` collapses all
    of those to `False`) must not leave the fact looking already-assessed, or the next run
    would skip it forever while the record itself never picked up the assessment."""
    ledger = AssessmentLedger(feature_repo / "l.sqlite")
    outcome = assess_record(
        fake_ctx, "features/structural-typing.yaml", repo_root=feature_repo,
        deps=Deps(assess=_deps(monkeypatch), escalate=None, ledger=ledger,
                  land=lambda minted: False,
                  alias="thinker", today="2026-09-17",
                  source_facts={}, contradictions=[], debates={},
                  verdict_ledger=type("L", (), {"latest_for": lambda self, f: []})()))
    assert outcome.changed is False
    assert ledger.levels() == {}


def test_a_budget_stop_mid_record_leaves_no_ledger_row(feature_repo, fake_ctx, monkeypatch):
    """A `BudgetExceeded` raised for a later fact in the same record must not leave earlier
    facts in this record recorded — the record's block never landed, so nothing about it may
    look done."""
    from langatlas_pipeline.errors import BudgetExceeded

    calls = []

    def _assess(ctx, fact_id, inputs, *, alias, prompt=None):
        calls.append(fact_id)
        raise BudgetExceeded("completions", used=200, limit=200)

    ledger = AssessmentLedger(feature_repo / "l.sqlite")
    with pytest.raises(BudgetExceeded):
        assess_record(
            fake_ctx, "features/structural-typing.yaml", repo_root=feature_repo,
            deps=Deps(assess=_assess, escalate=None, ledger=ledger,
                      land=lambda minted: (_ for _ in ()).throw(
                          AssertionError("land must not be reached")),
                      alias="thinker", today="2026-09-17",
                      source_facts={}, contradictions=[], debates={},
                      verdict_ledger=type("L", (), {"latest_for": lambda self, f: []})()))
    assert len(calls) == 1
    assert ledger.levels() == {}


def test_a_level_3_assessment_is_escalated(feature_repo, fake_ctx, monkeypatch):
    escalated = []

    def _escalate(assessment, inputs):
        escalated.append(assessment.fact_id)
        return Assessment(fact_id=assessment.fact_id, level=2, signals=assessment.signals,
                          model=assessment.model, prompt=assessment.prompt,
                          run_id=assessment.run_id, escalated_to="claude")

    outcome = assess_record(
        fake_ctx, "features/structural-typing.yaml", repo_root=feature_repo,
        deps=Deps(assess=_deps(monkeypatch, level=3, signals=("verdict:contradicted:base",)),
                  escalate=_escalate, ledger=AssessmentLedger(feature_repo / "l.sqlite"),
                  land=lambda minted: True, alias="thinker", today="2026-09-17",
                  source_facts={}, contradictions=[], debates={},
                  verdict_ledger=type("L", (), {"latest_for": lambda self, f: []})()))
    assert escalated == list(outcome.levels)
    assert outcome.escalated == 1
    assert set(outcome.levels.values()) == {2}
