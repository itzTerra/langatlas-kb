from langatlas_research.config import ResearchConfig
from langatlas_research.paths import REPO_ROOT, research_config_path
from langatlas_research.schema import validate_research_record

VALID_SURVEY = {
    "cycle": 1, "theme": "typing", "theme_digest": "0123456789abcdef",
    "generated_at": "2026-09-20T10:00:00Z",
    "runs": {"surveyor": "2026-09-20-r3-survey-01-typing-01"},
    "tagging": {"prompt": "r3-tagger@v-00000000", "models": ["deepseek-v4-pro"],
                "chunks_tagged": 2, "chunks_relevant": 1},
    "pool": {"digest": "fedcba9876543210", "chunk_count": 2, "queries": ["Typing"]},
    "checklist": {"mirror_versions": {"pldb": "abc1234"}, "gap_terms": ["generics"]},
    "candidates": [{
        "key": "type-inference", "name": "Type inference",
        "gloss": "Reconstructing types without annotations.", "kind_hint": "feature",
        "origin": "corpus",
        "evidence": [{"chunk_id": "tapl#c00012", "source_id": "tapl", "locator": "p. 317"}],
        "aliases": [{"label": "type reconstruction", "chunk_id": "tapl#c00013"}],
    }],
    "unevidenced": [{"key": "gradual-typing", "name": "Gradual typing",
                     "gloss": "Mixing static and dynamic checking.", "origin": "prior",
                     "search_hint": "Siek and Taha 2006", "disposition": "scouted"}],
    "theme_amendments": [{"op": "edit", "slug": "typing", "seed_terms": ["gradual typing"],
                          "rationale": "Post-2006 literature treats it as core.",
                          "status": "proposed"}],
    "scouting": [{"source_id": "siek-taha-2006", "title": "Gradual Typing for Functional"
                  " Languages", "csl_type": "paper-conference", "tier": "A",
                  "grounding": "third-party-reference", "access": "open",
                  "url": "http://scheme2006.cs.uchicago.edu/13-siek.pdf",
                  "candidate_keys": ["gradual-typing"], "rationale": "Origin paper.",
                  "status": "filed", "queue_entry_id": 7}],
}


def test_the_committed_research_config_loads():
    config = ResearchConfig.load(research_config_path(REPO_ROOT))
    assert config.pool.k_per_query > 0 and config.pool.max_chunks > 0
    assert config.tagger.alias and config.tagger.batch_size >= 1
    assert 0 <= config.tagger.min_relevance <= 3
    assert config.surveyor.max_turns > 0 and config.scout.max_turns > 0


def test_a_complete_survey_validates():
    assert validate_research_record(VALID_SURVEY, "survey", repo_root=REPO_ROOT) == []


def test_a_candidate_needs_one_to_three_evidence_chunks():
    for evidence in ([], [VALID_SURVEY["candidates"][0]["evidence"][0]] * 4):
        bad = {**VALID_SURVEY,
               "candidates": [{**VALID_SURVEY["candidates"][0], "evidence": evidence}]}
        assert validate_research_record(bad, "survey", repo_root=REPO_ROOT)


def test_a_candidate_may_not_carry_a_citation_shape():
    bad = {**VALID_SURVEY, "candidates": [{**VALID_SURVEY["candidates"][0],
                                           "sources": [{"source": "tapl"}]}]}
    assert validate_research_record(bad, "survey", repo_root=REPO_ROOT)
