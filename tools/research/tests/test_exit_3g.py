"""Stage 3G's exit: a draft-only cycle keeps a structural misfit, closes without minting, is
held at the gate, shows up in the review's agenda, and mints only once the review is recorded —
and even then never mints the blocked carve."""
import pytest

from langatlas_commit.land import Landed
from langatlas_research.cycle import advance, load_cycle, save_cycle
from langatlas_research.draft.finalize import finalize_r4_draft, r4_blockers
from langatlas_research.draft.findings import friction_entry
from langatlas_research.draft.minting import mint_items, mint_plan
from langatlas_research.draft.plan import build_plan_record, save_plan
from langatlas_research.errors import MintHeld
from langatlas_research.paths import structure_review_path
from langatlas_research.structure_review import (
    collect_friction, mint_open, release_structure_review, render_report,
)


def _concept():
    return {"key": "type-system", "from_candidates": ["type-system"], "kind": "concept",
            "id": "type-system", "name": "Type system", "summary": "s",
            "evidence": [{"source": "pierce-tapl-2002", "locator": "§1.1"},
                         {"source": "scott-plp", "locator": "§7.2"}],
            "contested": [], "debate_id": None, "status": "verified",
            "verification": {"fact_id": "f-1", "verdict": "verified", "admissible": True,
                             "pairs": 2}, "note": ""}


def _blocked_feature():
    return {"key": "type-classes", "from_candidates": ["type-classes"], "kind": "feature",
            "id": "type-classes", "name": "Type classes", "summary": "s", "layer": 2,
            "dimension": None, "cross_cutting": False, "aliases": [],
            "realizes": ["ad-hoc-polymorphism"],
            "evidence": [{"source": "scott-plp", "locator": "§7.2"}],
            "contested": [], "debate_id": None, "status": "proposed", "verification": None,
            "note": "", "blocked": "structure",
            "block_reason": "realizes 'ad-hoc-polymorphism', which is a feature"}


def test_the_draft_only_path_end_to_end(research_repo, signed_cycle):
    structure_review_path(research_repo).unlink()             # a fresh, unreviewed repo
    cycle = advance(signed_cycle, "r3-done")
    save_cycle(cycle, repo_root=research_repo)
    plan = build_plan_record(cycle=cycle, ontologist_run_id="run-1",
                             generated_at="2026-09-20T10:00:00Z")
    plan["nodes"] = [_concept(), _blocked_feature()]
    plan["findings"] = [friction_entry("a feature refines a feature; realizes cannot say so",
                                       keys=["type-classes"], element="realizes")]
    save_plan(plan, repo_root=research_repo)

    # 1. the draft closes without minting: the blocked carve is the point, not a blocker
    closed, _ = finalize_r4_draft(cycle.number, repo_root=research_repo,
                                  lander=lambda *a, **k: Landed(commit_sha="abc1234"))
    assert closed.status == "r4-drafted"
    assert load_cycle(cycle.number, repo_root=research_repo).nodes_minted == ()

    # 2. the gate holds
    assert mint_open(research_repo) is False
    with pytest.raises(MintHeld):
        mint_plan(plan, repo_root=research_repo, cycle=closed, chat_run_id="r",
                  prompt_version="v")

    # 3. the review's agenda shows the finding
    report = render_report(collect_friction(research_repo))
    assert "realizes: 1 finding(s) across 1 theme(s)" in report
    assert "[01 typing] type-classes" in report

    # 4. release opens the gate for the batch...
    release_structure_review(by="Michal", date="2026-09-25",
                             summary="kept the seed structure", repo_root=research_repo)
    assert mint_open(research_repo) is True

    # 5. ...but a blocked carve still never mints, and still blocks the mint-mode finalize
    items = mint_items(plan, repo_root=research_repo, ctx_run_id="r", prompt_version="v")
    assert len(items) == 1                                     # only the admitted concept
    assert any("blocked" in b for b in r4_blockers(closed, plan, repo_root=research_repo))
