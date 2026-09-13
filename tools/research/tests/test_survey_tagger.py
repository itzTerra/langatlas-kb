from types import SimpleNamespace

import pytest

from langatlas_research.errors import TaggerOutputInvalid
from langatlas_research.survey.chunks import ChunkRef
from langatlas_research.survey.tagger import (
    TagBatchOut, ground_terms, normalize_term, tag_batch,
)
from langatlas_research.survey.tags import TagStore
from langatlas_research.themes import load_themes
from langatlas_pipeline.injection import is_delimited

TEXT = {"tapl#c1": "Type  inference reconstructs types. Hindley-Milner is one algorithm.",
        "tapl#c2": "Subtyping lets a value of one type stand for another."}


def _ref(chunk_id, text=True, content_hash=None):
    return ChunkRef(chunk_id=chunk_id, source_id="tapl", locator="p. 1", breadcrumb="Ch",
                    content_hash=content_hash or f"h-{chunk_id}",
                    text=TEXT.get(chunk_id, "") if text else "")


def _responder(chunks):
    def respond(alias, messages, schema):
        return SimpleNamespace(parsed=TagBatchOut(chunks=chunks),
                               resolved_model="deepseek-v4-pro")
    return respond


@pytest.fixture
def theme(research_repo):
    return load_themes(research_repo)["typing"]


@pytest.fixture
def store(tmp_path):
    with TagStore(tmp_path / "tags.sqlite") as tag_store:
        yield tag_store


def test_terms_are_grounded_against_the_passage_text():
    kept, dropped = ground_terms(["Type inference", "HINDLEY-MILNER", "dependent types",
                                  "type inference"], TEXT["tapl#c1"])
    assert kept == ("type inference", "hindley-milner")
    assert dropped == 1
    assert normalize_term("  Type\n Inference ") == "type inference"


def test_a_batch_is_tagged_stored_and_delimited(fake_ctx, theme, store):
    fake_ctx.completions.append(_responder([
        {"chunk_id": "tapl#c1", "relevance": 3, "defined_terms": ["Type inference"],
         "mentioned_terms": ["Hindley-Milner", "effect system"]},
        {"chunk_id": "tapl#c2", "relevance": 2, "defined_terms": ["Subtyping"],
         "mentioned_terms": []},
    ]))
    batch = (_ref("tapl#c1", text=False), _ref("tapl#c2", text=False))

    result = tag_batch(fake_ctx, theme, "01-typing", batch, lookup=_ref, store=store,
                       alias="deepseek")

    assert (result.tagged, result.skipped, result.dropped_terms) == (2, 0, 1)
    row = store.get("01-typing", "tapl#c1")
    assert row.status == "tagged" and row.relevance == 3
    assert row.defined_terms == ("type inference",)
    assert row.mentioned_terms == ("hindley-milner",)
    assert row.resolved_model == "deepseek-v4-pro" and row.prompt_ref.startswith("r3-tagger@")
    messages = fake_ctx.complete_calls[0]["messages"]
    assert not any(is_delimited(m["content"]) for m in messages if m["role"] == "system")
    assert is_delimited(next(m for m in messages if m["role"] == "user")["content"])
    assert fake_ctx.complete_calls[0]["alias"] == "deepseek"


def test_missing_and_stale_chunks_never_reach_the_model(fake_ctx, theme, store):
    fake_ctx.completions.append(_responder([
        {"chunk_id": "tapl#c1", "relevance": 1, "defined_terms": [], "mentioned_terms": []}]))
    batch = (_ref("tapl#c1", text=False), _ref("gone#c9", text=False),
             _ref("tapl#c2", text=False, content_hash="old-hash"))

    result = tag_batch(fake_ctx, theme, "01-typing", batch,
                       lookup=lambda cid: None if cid.startswith("gone") else _ref(cid),
                       store=store, alias="deepseek")

    assert (result.tagged, result.missing, result.stale) == (1, 1, 1)
    user = next(m for m in fake_ctx.complete_calls[0]["messages"] if m["role"] == "user")
    assert "gone#c9" not in user["content"] and "tapl#c2" not in user["content"]
    assert store.get("01-typing", "tapl#c2").status == "stale"


def test_an_omitted_chunk_is_skipped_and_foreign_ids_are_ignored(fake_ctx, theme, store):
    fake_ctx.completions.append(_responder([
        {"chunk_id": "tapl#c1", "relevance": 2, "defined_terms": [], "mentioned_terms": []},
        {"chunk_id": "invented#c7", "relevance": 3, "defined_terms": [],
         "mentioned_terms": []}]))
    batch = (_ref("tapl#c1", text=False), _ref("tapl#c2", text=False))

    result = tag_batch(fake_ctx, theme, "01-typing", batch, lookup=_ref, store=store,
                       alias="deepseek")

    assert (result.tagged, result.skipped) == (1, 1)
    assert store.get("01-typing", "invented#c7") is None
    assert [t.chunk_id for t in store.for_cycle("01-typing")] == ["tapl#c1", "tapl#c2"]


def test_a_response_naming_none_of_its_batch_is_refused(fake_ctx, theme, store):
    fake_ctx.completions.append(_responder([
        {"chunk_id": "invented#c7", "relevance": 3, "defined_terms": [],
         "mentioned_terms": []}]))
    with pytest.raises(TaggerOutputInvalid):
        tag_batch(fake_ctx, theme, "01-typing", (_ref("tapl#c1", text=False),),
                  lookup=_ref, store=store, alias="deepseek")
