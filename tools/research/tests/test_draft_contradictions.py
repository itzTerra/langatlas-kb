import pytest
from ruamel.yaml import YAML

from langatlas_research.draft.contradictions import (
    EMPTY_LEDGER, contradictions_mint, contradictions_pending, mint_debate_contradiction,
)
from langatlas_research.draft.debate_record import load_debate, save_debate
from langatlas_validate.ids import contradiction_key
from langatlas_validate.store import validate_contradictions

_yaml = YAML(typ="safe")


def _debate(debate_id="d-01-typing-001", **resolution):
    base = {"outcome": "resolved", "disposition": "keep", "standing_dissent": True,
            "rounds": 2, "upheld_challenges": [], "rationale": "sources disagree"}
    base.update(resolution)
    return {"id": debate_id, "cycle": 1, "theme": "typing",
            "target": {"list": "nodes", "key": "static-typing"}, "opened": "2026-09-20",
            "runs": {"debate": "run-1", "moderator": "run-2"}, "triggers": ["single-source"],
            "personas": {"proposer": "p", "moderator": "m"},
            "pre_challenge": {"key": "static-typing"},
            "messages": [{"seq": 1, "role": "proposer", "persona": "p", "text": "x"}],
            "resolution": base}


@pytest.fixture
def repo(research_repo):
    (research_repo / "contradictions.yaml").write_text("contradictions: []\n")
    return research_repo


def test_a_resolution_without_a_contradiction_mints_nothing(repo):
    debate = _debate()
    save_debate(debate, repo_root=repo)
    assert mint_debate_contradiction(debate, repo_root=repo) is None
    assert _yaml.load((repo / "contradictions.yaml").read_text())["contradictions"] == []


def test_a_sourced_disagreement_mints_a_reconciler_record(repo):
    participants = ["citation:pierce-tapl-2002:§1.1", "citation:scott-plp:§7.2"]
    debate = _debate(contradiction={"participants": participants,
                                    "detail": "the two texts disagree about gradual typing"})
    save_debate(debate, repo_root=repo)

    record_id = mint_debate_contradiction(debate, repo_root=repo, today="2026-09-20")

    assert record_id == contradiction_key(participants)
    records = _yaml.load((repo / "contradictions.yaml").read_text())["contradictions"]
    assert records[0]["mechanism"] == "reconciler"
    assert records[0]["type"] == "verification"
    assert records[0]["status"] == "open"
    assert records[0]["participants"] == sorted(participants)
    assert records[0]["chat_run_id"] == "run-2"
    assert validate_contradictions(repo) == []


def test_the_id_is_stamped_back_onto_the_saved_debate(repo):
    debate = _debate(contradiction={"participants": ["citation:a:§1", "citation:b:§2"],
                                    "detail": "d"})
    save_debate(debate, repo_root=repo)
    record_id = mint_debate_contradiction(debate, repo_root=repo)
    assert load_debate(debate["id"], repo_root=repo)["resolution"]["contradiction_id"] == \
        record_id


def test_minting_the_same_disagreement_twice_is_a_no_op(repo):
    participants = ["citation:a:§1", "citation:b:§2"]
    for debate_id in ("d-01-typing-001", "d-01-typing-002"):
        debate = _debate(debate_id, contradiction={"participants": participants,
                                                   "detail": "d"})
        save_debate(debate, repo_root=repo)
        mint_debate_contradiction(debate, repo_root=repo)
    records = _yaml.load((repo / "contradictions.yaml").read_text())["contradictions"]
    assert len(records) == 1


def test_a_disagreement_between_the_agents_rather_than_the_sources_is_refused(repo):
    debate = _debate(contradiction={"participants": ["the type theorist", "the proposer"],
                                    "detail": "they disagreed"})
    save_debate(debate, repo_root=repo)
    with pytest.raises(ValueError):
        mint_debate_contradiction(debate, repo_root=repo)


def test_an_escalated_debate_never_mints(repo):
    debate = _debate(outcome="escalated", disposition="escalate",
                     contradiction={"participants": ["citation:a:§1", "citation:b:§2"],
                                    "detail": "d"})
    save_debate(debate, repo_root=repo)
    assert mint_debate_contradiction(debate, repo_root=repo) is None


def test_the_ledger_renders_as_a_landable_shared_file_mint(repo):
    debate = _debate(contradiction={"participants": ["citation:a:§1", "citation:b:§2"],
                                    "detail": "d"})
    save_debate(debate, repo_root=repo)
    mint_debate_contradiction(debate, repo_root=repo)

    minted = contradictions_mint(repo)
    assert minted.path == "contradictions.yaml"
    assert minted.base_digest is not None
    assert minted.text == (repo / "contradictions.yaml").read_text()


def test_a_repo_with_no_ledger_yet_mints_the_committed_empty_state(research_repo):
    assert contradictions_mint(research_repo).text == EMPTY_LEDGER


def test_nothing_is_pending_without_a_ledger_or_a_work_tree(research_repo):
    assert contradictions_pending(research_repo) is False
    (research_repo / "contradictions.yaml").write_text(EMPTY_LEDGER)
    assert contradictions_pending(research_repo) is False
