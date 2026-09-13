from langatlas_pipeline.injection import is_delimited
from langatlas_research.survey.chunks import ChunkRef
from langatlas_research.survey.index import (
    build_term_index, render_term_index, tagging_summary,
)
from langatlas_research.survey.pool import Pool
from langatlas_research.survey.tags import ChunkTags


def _tags(chunk_id, relevance, defined=(), mentioned=(), status="tagged"):
    return ChunkTags(chunk_id=chunk_id, content_hash="h", status=status, relevance=relevance,
                     defined_terms=tuple(defined), mentioned_terms=tuple(mentioned),
                     dropped_terms=0, prompt_ref="r3-tagger@v-00000001",
                     resolved_model="deepseek-v4-pro" if status == "tagged" else "")


def _pool(*chunk_ids):
    return Pool(cycle_slug="01-typing", theme_digest="0" * 16, queries=("Typing",),
                entries=tuple(ChunkRef(chunk_id=c, source_id=c.split("#")[0],
                                       locator="p. 9", breadcrumb="Ch", content_hash="h")
                              for c in chunk_ids))


POOL = _pool("tapl#c1", "tapl#c2", "pierce#c1", "ctm#c1", "ctm#c2", "ctm#c3", "ctm#c4")


def test_terms_defined_across_more_sources_rank_first():
    tags = [_tags("tapl#c1", 3, defined=["subtyping"]),
            _tags("tapl#c2", 3, defined=["type inference"]),
            _tags("ctm#c1", 2, defined=["type inference"]),
            _tags("pierce#c1", 2, mentioned=["subtyping", "type inference"])]
    index = build_term_index(tags, POOL, min_relevance=2, seed_terms=())
    assert [e.term for e in index] == ["type inference", "subtyping"]
    assert index[0].defining_sources == ("ctm", "tapl")
    assert index[1].mention_count == 1 and index[1].source_count == 2


def test_low_relevance_and_untagged_rows_are_ignored():
    tags = [_tags("tapl#c1", 1, defined=["closure"]),
            _tags("tapl#c2", 0, status="skipped")]
    assert build_term_index(tags, POOL, min_relevance=2, seed_terms=()) == []


def test_evidence_is_capped_at_three_highest_relevance_chunks():
    tags = [_tags(c, r, defined=["generics"]) for c, r in
            (("ctm#c1", 2), ("ctm#c2", 3), ("ctm#c3", 3), ("ctm#c4", 2))]
    entry = build_term_index(tags, POOL, min_relevance=2, seed_terms=())[0]
    assert [ref.chunk_id for ref in entry.evidence] == ["ctm#c2", "ctm#c3", "ctm#c1"]


def test_a_seed_term_with_no_hits_is_still_listed_last():
    tags = [_tags("tapl#c1", 3, defined=["subtyping"])]
    index = build_term_index(tags, POOL, min_relevance=2, seed_terms=("Region Inference",))
    assert [(e.term, e.seed) for e in index] == [("subtyping", False),
                                                  ("region inference", True)]
    assert index[1].evidence == ()


def test_the_rendered_index_is_one_delimited_block_respecting_the_limit(fake_ctx):
    tags = [_tags("tapl#c1", 3, defined=["subtyping"]),
            _tags("tapl#c2", 3, defined=["type inference"])]
    index = build_term_index(tags, POOL, min_relevance=2, seed_terms=())
    rendered = render_term_index(fake_ctx, index, limit=1)
    assert is_delimited(rendered)
    assert "tapl#c1" in rendered or "tapl#c2" in rendered
    assert rendered.count("evidence:") == 1
    assert render_term_index(fake_ctx, [], limit=5) == ""


def test_the_tagging_summary_counts_only_tagged_rows():
    tags = [_tags("tapl#c1", 3), _tags("tapl#c2", 1), _tags("ctm#c1", 0, status="stale")]
    assert tagging_summary(tags, min_relevance=2) == {
        "prompt": "r3-tagger@v-00000001", "models": ["deepseek-v4-pro"],
        "chunks_tagged": 2, "chunks_relevant": 1}
