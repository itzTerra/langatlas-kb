import json

import pytest

from langatlas_pipeline.providers.claude_runs import AgentRunResult
from langatlas_research.config import ResearchConfig
from langatlas_research.cycle import new_cycle
from langatlas_research.errors import R3Incomplete, SignOffMissing, SurveyOutputInvalid
from langatlas_research.paths import research_config_path
from langatlas_research.schema import validate_research_record
from langatlas_research.survey.scout import (
    ProposalOut, file_proposals, new_source_command, run_scout, screen_proposals,
)


class FakeQueue:
    def __init__(self, open_ids=()):
        self.filed = []
        self._open = [{"source_id": sid} for sid in open_ids]

    def file(self, *, kind, source_id, reason, detail=""):
        self.filed.append({"kind": kind, "source_id": source_id, "reason": reason,
                           "detail": detail})
        return len(self.filed)

    def open_entries(self, *, kind=None):
        return self._open


def _proposal(**overrides):
    data = {"source_id": "siek-taha-2006", "title": "Gradual Typing for Functional Languages",
            "csl_type": "paper-conference", "url": "http://scheme2006.cs.uchicago.edu/13-siek.pdf",
            "doi": None, "issued_year": 2006, "authors": ["Siek, Jeremy", "Taha, Walid"],
            "tier": "A", "grounding": "third-party-reference", "access": "open",
            "candidate_keys": ["gradual-typing"], "rationale": "The origin paper."}
    return ProposalOut.model_validate({**data, **overrides})


def _survey(cycle, *, digest=None):
    return {"cycle": 1, "theme": "typing",
            "theme_digest": digest or cycle.signed_off["theme_digest"],
            "generated_at": "2026-09-20T10:00:00Z",
            "runs": {"surveyor": "2026-09-20-r3-survey-01-typing-01"},
            "tagging": {"prompt": "r3-tagger@v-00000001", "models": [], "chunks_tagged": 0,
                        "chunks_relevant": 0},
            "pool": {"digest": "0123456789abcdef", "chunk_count": 0, "queries": []},
            "checklist": {"mirror_versions": {}, "gap_terms": []},
            "candidates": [],
            "unevidenced": [
                {"key": "gradual-typing", "name": "Gradual typing", "gloss": "g",
                 "origin": "prior", "search_hint": "Siek & Taha 2006", "disposition": "open"},
                {"key": "soft-typing", "name": "Soft typing", "gloss": "s", "origin": "prior",
                 "search_hint": "Cartwright & Fagan 1991", "disposition": "open"}],
            "theme_amendments": [], "scouting": []}


@pytest.fixture
def sources_repo(research_repo):
    (research_repo / "sources").mkdir()
    (research_repo / "sources" / "pierce-tapl-2002.yaml").write_text(
        "id: pierce-tapl-2002\ntype: book\ntitle: Types and Programming Languages\n"
        "DOI: 10.5555/509043\nURL: https://www.cis.upenn.edu/~bcpierce/tapl/\n"
        "custom: {tier: A, grounding: third-party-reference}\n")
    return research_repo


def test_screening_rejects_finding_aids_and_identifierless_proposals(sources_repo):
    entries = screen_proposals(
        [_proposal(source_id="wiki-gradual", url="https://en.wikipedia.org/wiki/Gradual_typing"),
         _proposal(source_id="mystery", url=None, doi=None),
         _proposal(source_id="Bad_Id"),
         _proposal(source_id="elsewhere", candidate_keys=["not-a-gap"])],
        repo_root=sources_repo, open_queue_ids=set(), candidate_keys={"gradual-typing"},
        max_proposals=10)
    assert [e["status"] for e in entries] == ["rejected"] * 4
    assert "D29" in entries[0]["rejection"]


def test_screening_marks_committed_pending_and_repeated_sources_as_duplicates(sources_repo):
    entries = screen_proposals(
        [_proposal(source_id="tapl-again", doi="10.5555/509043", url=None),
         _proposal(source_id="tapl-url", url="http://cis.upenn.edu/~bcpierce/tapl"),
         _proposal(source_id="queued-already"),
         _proposal(),
         _proposal(source_id="siek-taha-2006-copy")],
        repo_root=sources_repo, open_queue_ids={"queued-already"},
        candidate_keys={"gradual-typing"}, max_proposals=10)
    assert [e["status"] for e in entries] == ["duplicate", "duplicate", "duplicate",
                                             "filed", "duplicate"]
    assert "pierce-tapl-2002" in entries[0]["rejection"]


def test_too_many_proposals_is_refused(sources_repo):
    with pytest.raises(SurveyOutputInvalid):
        screen_proposals([_proposal()] * 3, repo_root=sources_repo, open_queue_ids=set(),
                         candidate_keys={"gradual-typing"}, max_proposals=2)


def test_filing_maps_access_to_queue_reasons_and_skips_non_filed(sources_repo):
    queue = FakeQueue()
    entries = screen_proposals(
        [_proposal(), _proposal(source_id="acm-paper", access="paywalled",
                                url="https://dl.acm.org/x"),
         _proposal(source_id="wiki", url="https://en.wikipedia.org/wiki/X")],
        repo_root=sources_repo, open_queue_ids=set(), candidate_keys={"gradual-typing"},
        max_proposals=10)
    filed = file_proposals(entries, queue=queue, cycle_slug="01-typing")
    assert [(f["source_id"], f["reason"]) for f in queue.filed] == [
        ("siek-taha-2006", "not-ingested"), ("acm-paper", "paywalled")]
    assert json.loads(queue.filed[0]["detail"])["cycle"] == "01-typing"
    assert [e.get("queue_entry_id") for e in filed] == [1, 2, None]


def test_a_scout_run_files_gaps_and_updates_the_survey(fake_ctx, sources_repo, signed_cycle):
    config = ResearchConfig.load(research_config_path(sources_repo))
    fake_ctx.claude_results.append(AgentRunResult(
        session_id="s", result_text="", num_turns=20, is_error=False, tokens_in=1,
        tokens_out=1, cost_usd=None, terminal_reason="completed",
        structured_output={"proposals": [_proposal().model_dump()],
                           "dropped": [{"key": "soft-typing",
                                        "reason": "Subsumed by gradual typing."}]}))
    queue = FakeQueue()

    updated = run_scout(fake_ctx, signed_cycle, _survey(signed_cycle), repo_root=sources_repo,
                        config=config, queue=queue)

    assert validate_research_record(updated, "survey", repo_root=sources_repo) == []
    assert updated["runs"]["scout"] == fake_ctx.run_id
    assert {u["key"]: u["disposition"] for u in updated["unevidenced"]} == {
        "gradual-typing": "scouted", "soft-typing": "dropped"}
    assert updated["scouting"][0]["queue_entry_id"] == 1
    _, options = fake_ctx.claude_calls[0]
    assert set(options.tools) == {"WebSearch", "WebFetch"}
    assert "pierce-tapl-2002" in fake_ctx.claude_calls[0][0]


def test_the_scout_is_gated_and_refuses_a_survey_from_an_older_sign_off(
        fake_ctx, sources_repo, signed_cycle):
    config = ResearchConfig.load(research_config_path(sources_repo))
    unsigned = new_cycle(2, "modules", repo_root=sources_repo, languages=("c",))
    with pytest.raises(SignOffMissing):
        run_scout(fake_ctx, unsigned, _survey(signed_cycle), repo_root=sources_repo,
                  config=config, queue=FakeQueue())
    with pytest.raises(R3Incomplete):
        run_scout(fake_ctx, signed_cycle, _survey(signed_cycle, digest="f" * 16),
                  repo_root=sources_repo, config=config, queue=FakeQueue())
    assert fake_ctx.claude_calls == []


def test_a_survey_with_no_open_gaps_costs_no_claude_run(fake_ctx, sources_repo,
                                                        signed_cycle):
    config = ResearchConfig.load(research_config_path(sources_repo))
    survey = _survey(signed_cycle)
    survey["unevidenced"] = []
    assert run_scout(fake_ctx, signed_cycle, survey, repo_root=sources_repo, config=config,
                     queue=FakeQueue()) == survey
    assert fake_ctx.claude_calls == []


def test_the_new_source_command_carries_the_bibliographic_identity():
    entry = screen_proposals([_proposal()], repo_root=None, open_queue_ids=set(),
                             candidate_keys={"gradual-typing"}, max_proposals=5)[0]
    command = new_source_command(entry)
    assert command.startswith("uv --directory tools/ingest run langatlas-sources new-source"
                              " siek-taha-2006 paper-conference")
    assert "--tier A" in command and "--grounding third-party-reference" in command
    assert "--author 'Siek, Jeremy' 'Taha, Walid'" in command
    assert "--issued-year 2006" in command
