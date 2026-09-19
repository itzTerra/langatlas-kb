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
