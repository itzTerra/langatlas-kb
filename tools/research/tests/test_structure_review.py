import pytest

from langatlas_research.cycle import advance, save_cycle
from langatlas_research.errors import MintHeld, StructureReviewRefused
from langatlas_research.paths import structure_review_path
from langatlas_research.schema import validate_research_record
from langatlas_research.structure_review import (
    drafted_cycles, mint_open, release_structure_review, require_mint_open,
)


@pytest.fixture
def closed_repo(research_repo):
    structure_review_path(research_repo).unlink()
    return research_repo


def test_the_gate_is_closed_until_a_review_is_recorded(closed_repo):
    assert mint_open(closed_repo) is False
    with pytest.raises(MintHeld, match="structure review"):
        require_mint_open(closed_repo)


def test_release_needs_at_least_one_drafted_cycle(closed_repo, signed_cycle):
    with pytest.raises(StructureReviewRefused, match="no cycle is at r4-drafted"):
        release_structure_review(by="Michal", date="2026-09-25", summary="s",
                                 repo_root=closed_repo)


def test_release_records_the_batch_and_opens_the_gate(closed_repo, signed_cycle):
    cycle = advance(advance(signed_cycle, "r3-done"), "r4-drafted")
    save_cycle(cycle, repo_root=closed_repo)
    assert drafted_cycles(closed_repo) == [1]
    path = release_structure_review(by="Michal", date="2026-09-25",
                                    summary="added a specialises edge type",
                                    repo_root=closed_repo)
    assert mint_open(closed_repo) is True
    from ruamel.yaml import YAML

    data = YAML(typ="safe").load(path.read_text())
    assert data["batch"] == [1] and data["reviewed_by"] == "Michal"
    assert validate_research_record(data, "structure-review", repo_root=closed_repo) == []


def test_a_review_is_recorded_once(closed_repo, signed_cycle):
    save_cycle(advance(advance(signed_cycle, "r3-done"), "r4-drafted"),
               repo_root=closed_repo)
    release_structure_review(by="M", date="d", summary="s", repo_root=closed_repo)
    with pytest.raises(StructureReviewRefused, match="already recorded"):
        release_structure_review(by="M", date="d", summary="s", repo_root=closed_repo)


def test_a_blank_summary_is_refused(closed_repo, signed_cycle):
    save_cycle(advance(advance(signed_cycle, "r3-done"), "r4-drafted"),
               repo_root=closed_repo)
    with pytest.raises(StructureReviewRefused, match="summary"):
        release_structure_review(by="M", date=" ", summary=" ", repo_root=closed_repo)


from langatlas_research.draft.findings import friction_entry
from langatlas_research.draft.plan import build_plan_record, save_plan
from langatlas_research.structure_review import collect_friction, render_report


def _plan_with(cycle, repo, *findings):
    plan = build_plan_record(cycle=cycle, ontologist_run_id="r", generated_at="t")
    plan["findings"] = list(findings)
    save_plan(plan, repo_root=repo)


def test_collect_friction_reads_every_plans_friction_findings(research_repo, signed_cycle):
    _plan_with(signed_cycle, research_repo,
               friction_entry("no refinement relation", keys=["gadt", "adts"],
                              element="edge-types"),
               {"kind": "rule-candidate", "detail": "x", "keys": []},
               friction_entry("provenance has no slot for a chat link", keys=["a"],
                              element="other", area="adjacent"))
    rows = collect_friction(research_repo)
    assert [(r.cycle, r.theme, r.area, r.element) for r in rows] == [
        (1, "typing", "ontology", "edge-types"), (1, "typing", "adjacent", "other")]
    assert rows[0].keys == ("gadt", "adts")


def test_the_report_groups_by_area_then_element_and_says_how_widespread(
        research_repo, signed_cycle):
    _plan_with(signed_cycle, research_repo,
               friction_entry("a", keys=["k1"], element="realizes"),
               friction_entry("b", keys=["k2"], element="realizes"),
               friction_entry("c", keys=["k3"], element="other", area="adjacent"))
    text = render_report(collect_friction(research_repo))
    assert text.index("== ontology ==") < text.index("== adjacent ==")
    assert "realizes: 2 finding(s) across 1 theme(s)" in text
    assert "[01 typing] k1: a" in text


def test_an_empty_report_says_so():
    assert render_report([]) == "no structure-friction findings"
