import pytest

from langatlas_finding_aids.checklist import Checklist, ChecklistRow
from langatlas_pipeline.injection import is_delimited
from langatlas_pipeline.providers.claude_runs import AgentRunResult
from langatlas_research.config import ResearchConfig
from langatlas_research.cycle import new_cycle
from langatlas_research.errors import PoolStale, SignOffMissing
from langatlas_research.paths import research_config_path
from langatlas_research.schema import validate_research_record
from langatlas_research.survey.chunks import ChunkRef
from langatlas_research.survey.pool import Pool
from langatlas_research.survey.surveyor import SurveyInputs, run_surveyor
from langatlas_research.survey.tags import ChunkTags

REF = ChunkRef(chunk_id="tapl#c00012", source_id="tapl", locator="p. 317",
               breadcrumb="Ch 22", content_hash="h", text="Type inference ...")
TAGS = [ChunkTags(chunk_id="tapl#c00012", content_hash="h", status="tagged", relevance=3,
                  defined_terms=("type inference",), mentioned_terms=(), dropped_terms=0,
                  prompt_ref="r3-tagger@v-00000001", resolved_model="deepseek-v4-pro")]
CHECKLIST = Checklist(theme="typing", label="Typing", generated_at="2026-09-20T00:00:00Z",
                      mirror_versions={"pldb": "abc1234"},
                      rows=(ChecklistRow(term="generics", language="python", aids=(),
                                         leads=(), covered_by=()),))
STRUCTURED = {
    "candidates": [{"key": "type-inference", "name": "Type inference",
                    "gloss": "Reconstructing types without annotations.",
                    "kind_hint": "feature", "origin": "corpus",
                    "evidence_chunk_ids": ["tapl#c00012", "made#up"], "aliases": []}],
    "unevidenced": [{"key": "gradual-typing", "name": "Gradual typing",
                     "gloss": "Mixing static and dynamic checking in one program.",
                     "origin": "prior", "search_hint": "Siek & Taha 2006"}],
    "theme_amendments": [],
}


def _pool(cycle, digest=None):
    return Pool(cycle_slug=cycle.slug,
                theme_digest=digest or cycle.signed_off["theme_digest"],
                queries=("Typing",), entries=(REF,))


def _result():
    return AgentRunResult(session_id="s", result_text="", structured_output=STRUCTURED,
                          num_turns=9, is_error=False, tokens_in=1, tokens_out=1,
                          cost_usd=None, terminal_reason="completed")


@pytest.fixture
def config(research_repo):
    return ResearchConfig.load(research_config_path(research_repo))


def test_a_survey_run_produces_a_schema_valid_record(fake_ctx, research_repo, signed_cycle,
                                                     config):
    fake_ctx.claude_results.append(_result())
    lookup = {REF.chunk_id: REF}.get

    data, report = run_surveyor(
        fake_ctx, signed_cycle, repo_root=research_repo,
        inputs=SurveyInputs(pool=_pool(signed_cycle), tags=TAGS, checklist=CHECKLIST),
        lookup=lookup, config=config, mcp_servers={"srv": object()},
        allowed_tools=("mcp__srv__search_sources",), now="2026-09-20T10:00:00Z")

    assert validate_research_record(data, "survey", repo_root=research_repo) == []
    assert data["runs"] == {"surveyor": fake_ctx.run_id}
    assert data["candidates"][0]["evidence"] == [REF.as_evidence()]
    assert data["unevidenced"][0]["key"] == "gradual-typing"
    assert data["checklist"] == {"mirror_versions": {"pldb": "abc1234"},
                                 "gap_terms": ["generics"]}
    assert data["tagging"]["chunks_relevant"] == 1
    assert any("made#up" in w for w in report.warnings)
    assert any("r3:survey-warning" in (e.get("flags") or []) for e in fake_ctx.events)

    user, options = fake_ctx.claude_calls[0]
    assert is_delimited(user) and "type inference" in user
    assert not is_delimited(options.system_prompt)
    assert options.tools == [] and list(options.allowed_tools) == ["mcp__srv__search_sources"]


def test_stale_out_of_pool_tags_are_not_counted_in_the_tagging_summary(fake_ctx, research_repo,
                                                                       signed_cycle, config):
    """TagStore rows accumulate across every tagging pass ever run for a cycle slug; after a
    pool rebuild, a row tagged for a chunk that is no longer in the CURRENT pool must not
    inflate `tagging.chunks_tagged` / `chunks_relevant` in the survey header."""
    fake_ctx.claude_results.append(_result())
    lookup = {REF.chunk_id: REF}.get
    stale_row = ChunkTags(chunk_id="stale#c99999", content_hash="h", status="tagged",
                          relevance=3, defined_terms=("obsolete term",), mentioned_terms=(),
                          dropped_terms=0, prompt_ref="r3-tagger@v-00000001",
                          resolved_model="deepseek-v4-pro")

    data, _ = run_surveyor(
        fake_ctx, signed_cycle, repo_root=research_repo,
        inputs=SurveyInputs(pool=_pool(signed_cycle), tags=[*TAGS, stale_row],
                            checklist=CHECKLIST),
        lookup=lookup, config=config, mcp_servers={"srv": object()},
        allowed_tools=("mcp__srv__search_sources",), now="2026-09-20T10:00:00Z")

    # Only REF's row (in the current pool) counts; the stale row is excluded.
    assert data["tagging"]["chunks_tagged"] == 1
    assert data["tagging"]["chunks_relevant"] == 1


def test_the_surveyor_refuses_an_unsigned_cycle(fake_ctx, research_repo, config):
    cycle = new_cycle(2, "modules", repo_root=research_repo, languages=("c",))
    with pytest.raises(SignOffMissing):
        run_surveyor(fake_ctx, cycle, repo_root=research_repo,
                     inputs=SurveyInputs(pool=None, tags=[], checklist=CHECKLIST),
                     lookup=lambda cid: None, config=config)
    assert fake_ctx.claude_calls == []


def test_the_surveyor_refuses_a_pool_built_for_another_theme_text(fake_ctx, research_repo,
                                                                  signed_cycle, config):
    with pytest.raises(PoolStale):
        run_surveyor(fake_ctx, signed_cycle, repo_root=research_repo,
                     inputs=SurveyInputs(pool=_pool(signed_cycle, digest="f" * 16),
                                         tags=TAGS, checklist=CHECKLIST),
                     lookup=lambda cid: None, config=config)
    assert fake_ctx.claude_calls == []
