"""Stage 3D's exit condition, end to end against a real git repo and the real commit protocol.

No provider: the assessor and the escalation are injected. What this proves is the part that has
to be true whatever any model says — that a level reaches the canonical store only as a
schema-valid, signal-justified block, in one commit per record, without moving `ontology/VERSION`
and without ever minting a contradiction record."""
import subprocess

import pytest
from ruamel.yaml import YAML

from langatlas_research.controversy.assessor import Assessment
from langatlas_research.controversy.ledger import AssessmentLedger
from langatlas_research.controversy.run import Deps, assess_record, default_land
from langatlas_validate.store import validate_store

_yaml = YAML(typ="safe")

pytestmark = pytest.mark.git

FEATURE = """\
id: structural-typing
slug: structural-typing
name: Structural typing
layer: 2
summary:
  text: A type system in which type compatibility is determined by structure.
  sources:
    - source: pierce-tapl-2002
      locator: 'p. 251'
provenance:
  claim_origin: source-derived
"""


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


def test_a_contested_fact_lands_as_a_block_and_nothing_else_moves(store_repo, fake_ctx, tmp_path):
    repo = store_repo
    (repo / "features" / "structural-typing.yaml").write_text(FEATURE)
    (repo / "sources" / "pierce-tapl-2002.yaml").write_text(
        "id: pierce-tapl-2002\ntype: book\ntitle: Types and Programming Languages\n"
        "custom:\n  tier: A\n  grounding: third-party-reference\n  locator_kinds: [page]\n"
        "  acquisition_note: library copy\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "seed the feature"], repo)
    _git(["push", "-q", "origin", "HEAD:main"], repo)
    version_before = (repo / "ontology" / "VERSION").read_text()
    head_before = _git(["rev-parse", "HEAD"], repo).strip()

    def _assess(ctx, fact_id, inputs, *, alias, prompt=None):
        return Assessment(fact_id=fact_id, level=3, signals=("verdict:contradicted:base",),
                          model="deepseek-v4-pro-thinking",
                          prompt="controversy-assessor@v-1a2b3c4d", run_id="r-1")

    def _escalate(assessment, inputs):
        return Assessment(fact_id=assessment.fact_id, level=2, signals=assessment.signals,
                          model=assessment.model, prompt=assessment.prompt,
                          run_id=assessment.run_id, escalated_to="claude")

    class _Verdicts:
        def latest_for(self, fact_id):
            from langatlas_ingest.verify.verdicts import PairVerdict
            return [PairVerdict(fact_id=fact_id, source_id="pierce-tapl-2002",
                                locator="p. 251", verdict="contradicted")]

    with AssessmentLedger(tmp_path / "assessments.sqlite") as ledger:
        deps = Deps(assess=_assess, escalate=_escalate, ledger=ledger,
                    land=default_land(repo, "r-1"), alias="thinker", today="2026-09-17",
                    source_facts={}, contradictions=[], debates={},
                    verdict_ledger=_Verdicts())
        outcome = assess_record(fake_ctx, "features/structural-typing.yaml", repo_root=repo,
                                deps=deps)

    assert outcome.changed is True
    assert outcome.escalated == 1

    # 1. The block is in the committed record, at level 2, with a machine signal and no prose.
    data = _yaml.load((repo / "features" / "structural-typing.yaml").read_text())
    entry, = data["controversy"]
    assert (entry["key"], entry["level"]) == ("summary", 2)
    assert entry["signals"] == ["verdict:contradicted:base"]
    assert entry["assessed"]["escalated_to"] == "claude"
    assert "rationale" not in entry

    # 2. The store still validates, block and all.
    assert validate_store(repo) == []

    # 3. Exactly one commit, and it touched exactly one file (D36).
    log = _git(["log", "--oneline", f"{head_before}..HEAD"], repo).splitlines()
    assert len(log) == 1
    assert _git(["show", "--name-only", "--format=", "HEAD"], repo).split() == \
        ["features/structural-typing.yaml"]

    # 4. A machine annotation is not an ontology change (§5.1).
    assert (repo / "ontology" / "VERSION").read_text() == version_before

    # 5. The assessor never mints a contradiction record (§6.4).
    assert _yaml.load((repo / "contradictions.yaml").read_text())["contradictions"] == []


def test_a_second_run_over_unchanged_inputs_is_free_and_silent(store_repo, fake_ctx, tmp_path):
    """§6.4's "unchanged inputs => unchanged level, so a re-run is free" — measured as: no
    model call, and no second commit."""
    repo = store_repo
    (repo / "features" / "structural-typing.yaml").write_text(FEATURE)
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "seed"], repo)
    _git(["push", "-q", "origin", "HEAD:main"], repo)

    calls = []

    def _assess(ctx, fact_id, inputs, *, alias, prompt=None):
        calls.append(fact_id)
        return Assessment(fact_id=fact_id, level=1, signals=(), run_id="r-1")

    class _Verdicts:
        def latest_for(self, fact_id):
            return []

    with AssessmentLedger(tmp_path / "assessments.sqlite") as ledger:
        deps = Deps(assess=_assess, escalate=None, ledger=ledger,
                    land=default_land(repo, "r-1"), alias="thinker", today="2026-09-17",
                    source_facts={}, contradictions=[], debates={}, verdict_ledger=_Verdicts())
        assess_record(fake_ctx, "features/structural-typing.yaml", repo_root=repo, deps=deps)
        head = _git(["rev-parse", "HEAD"], repo).strip()
        second = assess_record(fake_ctx, "features/structural-typing.yaml", repo_root=repo,
                               deps=deps)

    assert len(calls) == 1
    assert second.skipped == 1
    assert second.changed is False
    assert _git(["rev-parse", "HEAD"], repo).strip() == head
