"""Stage 3B's exit condition, end to end with scripted models and an in-memory corpus: a
signed-off cycle freezes a pool, tags it, surveys it, scouts its one gap, and finalizes —
landing the survey and the cycle through the real commit protocol."""
import subprocess
from types import SimpleNamespace

import pytest
from langatlas_commit.land import Landed

from langatlas_finding_aids.checklist import Checklist, ChecklistRow
from langatlas_pipeline.providers.claude_runs import AgentRunResult
from langatlas_research.config import PoolConfig, ResearchConfig
from langatlas_research.cycle import load_cycle, new_cycle, sign_off
from langatlas_research.paths import research_config_path
from langatlas_research.schema import validate_research_tree
from langatlas_research.survey.chunks import ChunkRef
from langatlas_research.survey.finalize import finalize_r3
from langatlas_research.survey.inventory import load_survey, save_survey
from langatlas_research.survey.pool import batches, build_pool, require_current_pool, save_pool
from langatlas_research.survey.scout import run_scout
from langatlas_research.survey.surveyor import SurveyInputs, run_surveyor
from langatlas_research.survey.tagger import TagBatchOut, tag_batch
from langatlas_research.survey.tags import TagStore
from langatlas_research.themes import load_themes

pytestmark = pytest.mark.git

CORPUS = {
    "tapl#c00012": ChunkRef(chunk_id="tapl#c00012", source_id="tapl", locator="p. 317",
                            breadcrumb="Ch 22", content_hash="h1",
                            text="Type inference reconstructs the types of terms."),
    "ctm#c00400": ChunkRef(chunk_id="ctm#c00400", source_id="vanroy-haridi-2003",
                           locator="p. 104", breadcrumb="Ch 3", content_hash="h2",
                           text="Static typing checks types before a program runs."),
}


class FakeQueue:
    def __init__(self):
        self.filed = []

    def file(self, *, kind, source_id, reason, detail=""):
        self.filed.append((kind, source_id, reason))
        return len(self.filed)

    def open_entries(self, *, kind=None):
        return []


def _claude(structured):
    return AgentRunResult(session_id="s", result_text="", structured_output=structured,
                          num_turns=5, is_error=False, tokens_in=1, tokens_out=1,
                          cost_usd=None, terminal_reason="completed")


def _search(query, k):
    return [{"chunk_id": cid, "source_id": ref.source_id, "locator": ref.locator,
             "breadcrumb": ref.breadcrumb, "text": ref.text, "score": 0.5}
            for cid, ref in CORPUS.items()][:k]


def test_a_signed_off_cycle_closes_r3_with_a_landed_inventory(store_repo, fake_ctx,
                                                              private_dir):
    (store_repo / "config").mkdir(exist_ok=True)
    (store_repo / "config" / "research.yaml").write_text(
        research_config_path().read_text())
    config = ResearchConfig.load(research_config_path(store_repo))
    cycle = sign_off(new_cycle(1, "typing", repo_root=store_repo, languages=("python",)),
                     by="Michal Dolezel", date="2026-09-20", repo_root=store_repo)

    # R3 step 1: pool
    save_pool(build_pool(fake_ctx, cycle, repo_root=store_repo, search_fn=_search,
                         lookup=CORPUS.get, config=PoolConfig(k_per_query=5, max_chunks=10)))
    pool = require_current_pool(cycle, repo_root=store_repo)

    # R3 step 2: tagging (what the orchestrator job does per item)
    theme = load_themes(store_repo)["typing"]
    fake_ctx.completions.append(lambda alias, messages, schema: SimpleNamespace(
        resolved_model="deepseek-v4-pro", parsed=TagBatchOut(chunks=[
            {"chunk_id": "ctm#c00400", "relevance": 3, "defined_terms": ["static typing"],
             "mentioned_terms": []},
            {"chunk_id": "tapl#c00012", "relevance": 3, "defined_terms": ["type inference"],
             "mentioned_terms": []}])))
    with TagStore(private_dir / "tags.sqlite") as store:
        for batch in batches(pool, 6):
            tag_batch(fake_ctx, theme, cycle.slug, batch, lookup=CORPUS.get, store=store,
                      alias=config.tagger.alias)
        tags = store.for_cycle(cycle.slug)

    # R3 step 3: survey
    checklist = Checklist(theme="typing", label="Typing", generated_at="2026-09-20T00:00:00Z",
                          mirror_versions={}, rows=(ChecklistRow(
                              term="gradual typing", language="python", aids=(), leads=(),
                              covered_by=()),))
    fake_ctx.claude_results.append(_claude({
        "candidates": [
            {"key": "type-inference", "name": "Type inference", "gloss": "Reconstructing"
             " types without annotations.", "kind_hint": "feature", "origin": "corpus",
             "evidence_chunk_ids": ["tapl#c00012"], "aliases": []},
            {"key": "static-typing", "name": "Static typing", "gloss": "Checking types"
             " before execution.", "kind_hint": "feature", "origin": "corpus",
             "evidence_chunk_ids": ["ctm#c00400"], "aliases": []}],
        "unevidenced": [{"key": "gradual-typing", "name": "Gradual typing",
                         "gloss": "Mixing static and dynamic checking.",
                         "origin": "finding-aid-gap", "search_hint": "Siek & Taha 2006"}],
        "theme_amendments": []}))
    data, _ = run_surveyor(fake_ctx, cycle, repo_root=store_repo,
                           inputs=SurveyInputs(pool=pool, tags=tags, checklist=checklist),
                           lookup=CORPUS.get, config=config)
    save_survey(data, repo_root=store_repo)

    # R3 step 4: scout
    fake_ctx.claude_results.append(_claude({"proposals": [{
        "source_id": "siek-taha-2006", "title": "Gradual Typing for Functional Languages",
        "csl_type": "paper-conference", "url": "http://scheme2006.cs.uchicago.edu/13-siek.pdf",
        "issued_year": 2006, "authors": ["Siek, Jeremy", "Taha, Walid"], "tier": "A",
        "grounding": "third-party-reference", "access": "open",
        "candidate_keys": ["gradual-typing"], "rationale": "The origin paper."}],
        "dropped": []}))
    queue = FakeQueue()
    save_survey(run_scout(fake_ctx, cycle, load_survey(cycle.slug, repo_root=store_repo),
                          repo_root=store_repo, config=config, queue=queue),
                repo_root=store_repo)
    assert queue.filed == [("pending-source", "siek-taha-2006", "not-ingested")]

    # R3 step 5: finalize through the real commit protocol
    closed, results = finalize_r3(1, repo_root=store_repo, lookup=CORPUS.get)

    assert [type(result) for result in results] == [Landed, Landed]
    assert closed.status == "r3-done"
    assert load_cycle(1, repo_root=store_repo).artifacts["survey"] == \
        "research/surveys/01-typing.yaml"
    assert validate_research_tree(store_repo) == []
    log = subprocess.run(["git", "log", "--format=%B", "-2"], cwd=store_repo,
                         capture_output=True, text=True, check=True).stdout
    assert "research/cycles/01-typing.yaml" in log and "research/surveys/01-typing.yaml" in log
    assert data["runs"]["surveyor"] in log
    survey = load_survey(cycle.slug, repo_root=store_repo)
    assert {c["key"] for c in survey["candidates"]} == {"type-inference", "static-typing"}
    assert survey["unevidenced"][0]["disposition"] == "scouted"
