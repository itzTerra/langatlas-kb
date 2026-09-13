import pytest
from langatlas_commit.land import BlockedRedMain, Landed

from langatlas_research.cycle import load_cycle
from langatlas_research.errors import R3Incomplete
from langatlas_research.survey.chunks import ChunkRef
from langatlas_research.survey.finalize import finalize_r3, r3_blockers
from langatlas_research.survey.inventory import save_survey

REF = ChunkRef(chunk_id="tapl#c00012", source_id="tapl", locator="p. 317",
               breadcrumb="Ch 22", content_hash="h", text="...")


def _survey(cycle, **overrides):
    data = {"cycle": 1, "theme": "typing", "theme_digest": cycle.signed_off["theme_digest"],
            "generated_at": "2026-09-20T10:00:00Z",
            "runs": {"surveyor": "2026-09-20-r3-survey-01-typing-01"},
            "tagging": {"prompt": "r3-tagger@v-00000001", "models": ["m"],
                        "chunks_tagged": 1, "chunks_relevant": 1},
            "pool": {"digest": "0123456789abcdef", "chunk_count": 1, "queries": ["Typing"]},
            "checklist": {"mirror_versions": {}, "gap_terms": []},
            "candidates": [{"key": "type-inference", "name": "Type inference", "gloss": "g",
                            "kind_hint": "feature", "origin": "corpus",
                            "evidence": [REF.as_evidence()], "aliases": []}],
            "unevidenced": [], "theme_amendments": [], "scouting": []}
    return {**data, **overrides}


class RecordingLander:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def __call__(self, repo_root, path, content, *, chat_run_id, validator,
                 status_checker=None):
        self.calls.append((path, content, chat_run_id))
        return self._results.pop(0) if self._results else Landed(commit_sha="abc1234")


def test_a_clean_survey_has_no_blockers(research_repo, signed_cycle):
    assert r3_blockers(signed_cycle, _survey(signed_cycle), repo_root=research_repo,
                       lookup={REF.chunk_id: REF}.get) == []


def test_every_blocker_is_reported_at_once(research_repo, signed_cycle):
    survey = _survey(
        signed_cycle, theme_digest="f" * 16,
        unevidenced=[{"key": "gradual-typing", "name": "G", "gloss": "g", "origin": "prior",
                      "search_hint": "h", "disposition": "open"}],
        theme_amendments=[{"op": "edit", "slug": "typing", "rationale": "r",
                           "status": "proposed"}])
    blockers = r3_blockers(signed_cycle, survey, repo_root=research_repo,
                           lookup=lambda cid: None)
    text = " | ".join(blockers)
    assert len(blockers) == 4
    assert "sign-off" in text and "gradual-typing" in text
    assert "amendment" in text and "tapl#c00012" in text


def test_finalize_lands_survey_then_cycle_and_advances(research_repo, signed_cycle):
    save_survey(_survey(signed_cycle), repo_root=research_repo)
    lander = RecordingLander()

    cycle, results = finalize_r3(1, repo_root=research_repo, lookup={REF.chunk_id: REF}.get,
                                 lander=lander)

    assert [call[0] for call in lander.calls] == ["research/surveys/01-typing.yaml",
                                                  "research/cycles/01-typing.yaml"]
    assert {call[2] for call in lander.calls} == {"2026-09-20-r3-survey-01-typing-01"}
    assert "status: r3-done" in lander.calls[1][1]
    assert cycle.status == "r3-done"
    assert cycle.artifacts["survey"] == "research/surveys/01-typing.yaml"
    assert all(isinstance(result, Landed) for result in results)


def test_finalize_refuses_open_work(research_repo, signed_cycle):
    save_survey(_survey(signed_cycle, candidates=[]), repo_root=research_repo)
    with pytest.raises(R3Incomplete, match="no evidenced candidates"):
        finalize_r3(1, repo_root=research_repo, lookup=lambda cid: None,
                    lander=RecordingLander())


def test_a_blocked_survey_landing_leaves_the_cycle_untouched(research_repo, signed_cycle):
    save_survey(_survey(signed_cycle), repo_root=research_repo)
    lander = RecordingLander([BlockedRedMain(since=0.0, last_checked=0.0)])

    cycle, results = finalize_r3(1, repo_root=research_repo,
                                 lookup={REF.chunk_id: REF}.get, lander=lander)

    assert len(lander.calls) == 1 and isinstance(results[0], BlockedRedMain)
    assert cycle.status == "signed-off"
    assert load_cycle(1, repo_root=research_repo).status == "signed-off"
