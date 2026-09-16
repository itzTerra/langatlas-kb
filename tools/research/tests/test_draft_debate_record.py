# tools/research/tests/test_draft_debate_record.py
import pytest

from langatlas_research.draft.debate_record import (
    DEBATE_OUTCOMES, DISPOSITIONS, as_controversy_input, debate_signals, iter_debates,
    load_debate, next_debate_id, resolution_outcome, rounds, save_debate,
)
from langatlas_research.schema import validate_research_record, validate_research_tree


def _debate(debate_id="d-01-typing-001", **over):
    record = {
        "id": debate_id, "cycle": 1, "theme": "typing",
        "target": {"list": "nodes", "key": "static-typing"},
        "opened": "2026-09-20", "runs": {"debate": "run-1", "moderator": "run-2"},
        "triggers": ["merged-candidates"],
        "personas": {"proposer": "the ontologist", "challenger_a": "the type theorist",
                     "challenger_b": "the working language implementer",
                     "moderator": "the moderator"},
        "pre_challenge": {"key": "static-typing", "summary": "checked before running"},
        "messages": [
            {"seq": 1, "role": "proposer", "persona": "the ontologist", "text": "I carve …"},
            {"seq": 2, "role": "challenger-a", "persona": "the type theorist",
             "text": "This merges two ideas.",
             "challenges": [{"type": "wrong-atomization", "text": "gradual typing is a"
                             " third value, not a blend",
                             "evidence": [{"source": "siek-taha", "locator": "§2"}]}]},
            {"seq": 3, "role": "challenger-b",
             "persona": "the working language implementer", "text": "Agreed in practice."},
            {"seq": 4, "role": "proposer", "persona": "the ontologist", "text": "Fair."},
            {"seq": 5, "role": "moderator", "persona": "the moderator", "text": "Revise."},
        ],
        "resolution": {"outcome": "converged-after-revision", "disposition": "revise",
                       "standing_dissent": False, "rounds": 1,
                       "upheld_challenges": ["wrong-atomization"],
                       "rationale": "the challenge is evidenced and the carve narrows"},
    }
    record.update(over)
    return record


def test_the_outcome_vocabulary_matches_2bs_committed_controversy_cases():
    assert DEBATE_OUTCOMES == ("resolved", "converged-after-revision", "escalated")


def test_every_disposition_maps_to_an_outcome():
    assert {resolution_outcome(d) for d in DISPOSITIONS} <= set(DEBATE_OUTCOMES)
    assert resolution_outcome("keep") == "resolved"
    assert resolution_outcome("revise") == "converged-after-revision"
    assert resolution_outcome("split") == "converged-after-revision"
    assert resolution_outcome("merge") == "converged-after-revision"
    assert resolution_outcome("drop") == "converged-after-revision"
    assert resolution_outcome("escalate") == "escalated"


def test_an_unknown_disposition_is_refused():
    with pytest.raises(ValueError):
        resolution_outcome("ignore-it")


def test_rounds_counts_challenge_messages_not_all_messages():
    assert rounds(_debate()) == 1
    both = _debate()
    both["messages"][2]["challenges"] = [{"type": "scope", "text": "too broad"}]
    assert rounds(both) == 2


def test_a_debate_record_is_schema_valid_and_round_trips(research_repo):
    record = _debate()
    assert validate_research_record(record, "debate", repo_root=research_repo) == []
    save_debate(record, repo_root=research_repo)
    assert load_debate(record["id"], repo_root=research_repo) == record
    assert validate_research_tree(research_repo) == []


def test_debate_ids_are_cycle_scoped_and_increment(research_repo):
    assert next_debate_id("01-typing", repo_root=research_repo) == "d-01-typing-001"
    save_debate(_debate("d-01-typing-001"), repo_root=research_repo)
    assert next_debate_id("01-typing", repo_root=research_repo) == "d-01-typing-002"
    save_debate(_debate("d-02-memory-001", cycle=2, theme="memory-management"),
                repo_root=research_repo)
    assert next_debate_id("01-typing", repo_root=research_repo) == "d-01-typing-002"


def test_iter_debates_yields_every_committed_record(research_repo):
    save_debate(_debate("d-01-typing-001"), repo_root=research_repo)
    save_debate(_debate("d-01-typing-002"), repo_root=research_repo)
    assert [d["id"] for d in iter_debates(research_repo)] == ["d-01-typing-001",
                                                              "d-01-typing-002"]


def test_the_controversy_projection_is_exactly_3ds_four_fields():
    assert as_controversy_input(_debate()) == {"id": "d-01-typing-001",
                                               "outcome": "converged-after-revision",
                                               "standing_dissent": False, "rounds": 1}


def test_a_debate_without_dissent_signals_its_outcome():
    assert debate_signals(_debate()) == ["debate:d-01-typing-001:converged-after-revision"]


def test_standing_dissent_outranks_the_outcome_in_the_signal():
    record = _debate()
    record["resolution"].update(outcome="resolved", disposition="keep",
                                standing_dissent=True)
    assert debate_signals(record) == ["debate:d-01-typing-001:standing-dissent"]
