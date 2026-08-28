import json
import pytest
from langatlas_ingest.chunker import Chunk
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.goldens.authoring import generate_candidates, write_candidate_file
from langatlas_ingest.goldens.loader import load_verifier_items
from langatlas_ingest.errors import GoldenItemInvalid

CONFIG = IngestConfig.load()


class FakeCompletionCtx:
    """A RunContext stand-in that records the D31 door and returns a fixed batch."""

    def __init__(self, payload):
        self.payload = payload
        self.completions = []
        self.tool_results = []

    def tool_result(self, *, tool, text, source_id=None, kind="source-chunk"):
        self.tool_results.append((tool, source_id, text))
        return f"<untrusted source={source_id}>\n{text}\n</untrusted>"

    def complete(self, alias, messages, *, prompt, schema=None, sampling=None):
        self.completions.append((alias, messages, prompt.ref()))

        class Result:
            parsed = schema.model_validate(self.payload) if schema else None
            text = json.dumps(self.payload)

        return Result()


PAYLOAD = {"candidates": [{
    "stratum": "overstated-claim",
    "claim_kind": "instance-exists",
    "claim_text": "instance-exists(i-ctm-lazy-evaluation, status=present)",
    "rendered": "Oz evaluates every expression lazily.",
    "expected_verdict": "partial",
    "locator": "p. 1",
    "quote": "Lazy evaluation defers a computation until its value is demanded.",
    "expected_annotations": [],
    "rationale": "generalises a scoped statement to the whole language",
}]}


def chunks():
    return [Chunk(chunk_id="ctm#c00001", source_id="ctm", ordinal=1,
                  parent_section_id="ctm#s0001", section_path=["Ch"], breadcrumb="Ch",
                  locator="p. 1", locator_kind="book-page", token_count=12,
                  content_hash="h1", page_start=1, page_end=1,
                  text="Lazy evaluation defers a computation until its value is demanded.")]


def test_chunk_text_reaches_the_model_only_through_the_d31_door():
    ctx = FakeCompletionCtx(PAYLOAD)
    generate_candidates(ctx, conn=None, source_id="ctm", stratum="overstated-claim",
                        count=1, config=CONFIG, chunks=chunks())
    assert ctx.tool_results and ctx.tool_results[0][1] == "ctm"
    _, messages, _ = ctx.completions[0]
    assert all(m["role"] != "system" or "untrusted" not in m["content"]
               for m in messages)


def test_generation_uses_the_configured_decorrelated_alias():
    ctx = FakeCompletionCtx(PAYLOAD)
    generate_candidates(ctx, conn=None, source_id="ctm", stratum="overstated-claim",
                        count=1, config=CONFIG, chunks=chunks())
    alias = ctx.completions[0][0]
    assert alias == CONFIG.golden_candidate_model
    assert alias not in ("deepseek", "deepseek-thinking", "mini")


def test_candidates_are_written_uncurated_and_refuse_to_load(tmp_path):
    ctx = FakeCompletionCtx(PAYLOAD)
    candidates = generate_candidates(ctx, conn=None, source_id="ctm",
                                     stratum="overstated-claim", count=1, config=CONFIG,
                                     chunks=chunks())
    assert all(c["curated"] is False for c in candidates)
    write_candidate_file(candidates, tmp_path / "candidates-ctm.yaml")
    with pytest.raises(GoldenItemInvalid, match="uncurated"):
        load_verifier_items(tmp_path)


def test_the_generated_locator_and_chunk_id_come_from_the_real_chunk(tmp_path):
    ctx = FakeCompletionCtx(PAYLOAD)
    candidate = generate_candidates(ctx, conn=None, source_id="ctm",
                                    stratum="overstated-claim", count=1, config=CONFIG,
                                    chunks=chunks())[0]
    assert candidate["evidence_chunk_ids"] == ["ctm#c00001"]
    assert candidate["citation"]["locator"] == "p. 1"


def test_a_source_prefixed_locator_still_resolves_to_the_real_chunk():
    """Observed live against a real model: the locator came back re-contextualized as
    `"vanroy-haridi-2003 §8.4.3"` for a chunk stored bare as `"§8.4.3"`. A genuinely
    grounded citation must not be indistinguishable from a fabricated one just because
    the model dressed the locator up."""
    ctx = FakeCompletionCtx({"candidates": [dict(PAYLOAD["candidates"][0],
                                                 locator="ctm p. 1")]})
    candidate = generate_candidates(ctx, conn=None, source_id="ctm",
                                    stratum="overstated-claim", count=1, config=CONFIG,
                                    chunks=chunks())[0]
    assert candidate["evidence_chunk_ids"] == ["ctm#c00001"]
    # The citation records what the model actually said, not the normalized form —
    # normalization is a matching aid, not a rewrite of the drafted citation.
    assert candidate["citation"]["locator"] == "ctm p. 1"


def test_a_fabricated_locator_stratum_does_not_inherit_the_real_locator():
    ctx = FakeCompletionCtx({"candidates": [dict(PAYLOAD["candidates"][0],
                                                 stratum="fabricated-locator",
                                                 expected_verdict="locator-not-found",
                                                 locator="p. 9999")]})
    candidate = generate_candidates(ctx, conn=None, source_id="ctm",
                                    stratum="fabricated-locator", count=1, config=CONFIG,
                                    chunks=chunks())[0]
    assert candidate["citation"]["locator"] == "p. 9999"
    assert candidate["evidence_chunk_ids"] == []
