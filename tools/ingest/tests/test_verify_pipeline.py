import pytest
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.store import SourceChunk
from langatlas_ingest.verify.entailment import AssertionOut, EntailmentOut
from langatlas_ingest.verify.inputs import CitationInput, ClaimInput
from langatlas_ingest.verify.pipeline import VerifyDeps, verify_pair
from langatlas_ingest.verify.sources import SourceFacts

CONFIG = IngestConfig.load()
PASSAGE = ("Pattern matching destructures a value against a sequence of patterns, "
           "binding names in the matched arm.")

SF = {"s": SourceFacts("s", "A", "formal-spec", ("book-page",), {})}


def chunk(chunk_id="s#c00001", text=PASSAGE, locator="p. 1", tokens=1000):
    return SourceChunk(chunk_id=chunk_id, source_id="s", ordinal=1,
                       parent_section_id=None, section_path=[], breadcrumb="",
                       locator=locator, locator_kind="book-page", page_start=1, page_end=1,
                       section_number=None, anchor=None, line_start=None, line_end=None,
                       text=text, token_count=tokens, content_hash="h")


class FakeIndex:
    def __init__(self, ids=("s#c00001",)):
        self.ids = list(ids)

    def resolve(self, source_id, locator):
        return list(self.ids)


class FakeStore:
    def __init__(self, chunks=None, ingested=True):
        self._chunks = list(chunks or [chunk()])
        self._ingested = ingested

    def get(self, chunk_id):
        return next((c for c in self._chunks if c.chunk_id == chunk_id), None)

    def by_source(self, source_id):
        return list(self._chunks)

    def ingestion(self, source_id):
        return {"source_id": source_id} if self._ingested else None


class FakeSearch:
    def search(self, query, *, k=None, source_ids=None):
        return []

    def get_section(self, chunk_id, expand="parent"):
        return []


class FakeQueue:
    def __init__(self):
        self.filed = []

    def file(self, *, kind, source_id, reason, detail=""):
        self.filed.append((kind, source_id, reason))
        return 1

    def open_entries(self, *, kind=None):
        return []

    def bounce(self, entry_id):
        return 1


class FakeCompletion:
    def __init__(self, parsed, resolved_model="deepseek-v4"):
        self.parsed = parsed
        self.resolved_model = resolved_model


class ScriptedCtx:
    """Returns each scripted parse in turn; records the aliases and rendered messages
    it was called with. An output is either a bare parsed object (defaults its
    `resolved_model` to "deepseek-v4") or a `(parsed, resolved_model)` tuple, so a test
    can tell which underlying call actually produced the recorded model id."""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.aliases = []
        self.messages = []
        self.run_id = "2026-09-06-verify-test-01"

    def tool_result(self, *, tool, text, source_id=None, kind="source-chunk"):
        from langatlas_pipeline.injection import delimit_untrusted
        return delimit_untrusted(text, source_id=source_id, kind=kind)

    def complete(self, alias, messages, *, prompt, schema=None, sampling=None):
        self.aliases.append(alias)
        self.messages.append(messages)
        item = self.outputs.pop(0)
        parsed, resolved_model = item if isinstance(item, tuple) else (item, "deepseek-v4")
        return FakeCompletion(parsed, resolved_model)


def ent(*statuses, since_status=None, kinds=None):
    kinds = kinds or ["presence"] * len(statuses)
    return EntailmentOut(
        assertions=[AssertionOut(kind=k, text="t", status=s)
                    for k, s in zip(kinds, statuses)],
        since_status=since_status)


def deps(**kw):
    base = dict(source_facts=SF, index=FakeIndex(), store=FakeStore(),
                search=FakeSearch(), ledger=None)
    base.update(kw)
    return VerifyDeps(**base)


CLAIM = ClaimInput(fact_id="f-000000000001",
                   claim="instance-exists(fi.rust.pattern-matching, status=present)")
CITATION = CitationInput("s", "p. 1")


def test_a_supported_pair_records_its_provenance():
    ctx = ScriptedCtx(ent("supported"))
    got = verify_pair(ctx, None, claim=CLAIM, citation=CITATION, config=CONFIG,
                      deps=deps(), anchor="run#msg-4")
    assert got.verdict == "supported"
    assert got.model == "deepseek-v4"
    assert got.prompt_version
    assert got.run_id == ctx.run_id
    assert got.anchor == "run#msg-4"
    assert got.date
    assert got.evidence_chunk_ids == ("s#c00001",)


def test_stage_zero_rejects_before_any_provider_call():
    ctx = ScriptedCtx()
    got = verify_pair(ctx, None, claim=CLAIM, citation=CitationInput("s", "page four"),
                      config=CONFIG, deps=deps())
    assert got.verdict == "locator-not-found"
    assert ctx.aliases == []


def test_an_uningested_source_parks_the_claim_and_never_calls_a_model():
    ctx = ScriptedCtx()
    queue = FakeQueue()
    got = verify_pair(ctx, None, claim=CLAIM, citation=CITATION, config=CONFIG,
                      deps=deps(store=FakeStore(ingested=False)), queue=queue)
    assert got.verdict == "source-unavailable"
    assert queue.filed == [("pending-source", "s", "not-ingested")]
    assert ctx.aliases == []


def test_an_unresolvable_locator_is_locator_not_found_with_the_hint_preserved():
    ctx = ScriptedCtx()
    got = verify_pair(ctx, None, claim=CLAIM, citation=CITATION, config=CONFIG,
                      deps=deps(index=FakeIndex([])))
    assert got.verdict == "locator-not-found"
    assert ctx.aliases == []


def test_a_matched_quote_never_waives_entailment():
    # Section 6.2's core K1 defense: quote-real-but-overstated must still come back
    # `partial`, not `supported`. A `partial` verdict always escalates to the reasoning
    # model (Task 8's `ESCALATING_VERDICTS`), so the escalation pass is scripted too —
    # it confirms the same partial rather than reversing it.
    ctx = ScriptedCtx(ent("supported", "not-supported", kinds=["presence", "qualifier"]),
                      ent("supported", "not-supported", kinds=["presence", "qualifier"]))
    citation = CitationInput("s", "p. 1", quote="destructures a value against a sequence")
    got = verify_pair(ctx, None, claim=CLAIM, citation=citation, config=CONFIG,
                      deps=deps())
    assert len(ctx.aliases) >= 1          # entailment ran despite the clean quote match
    assert got.verdict == "partial"


def test_a_fabricated_quote_short_circuits_to_unsupported_with_the_annotation():
    ctx = ScriptedCtx()
    citation = CitationInput("s", "p. 1",
                             quote="monads are monoids in the category of endofunctors")
    got = verify_pair(ctx, None, claim=CLAIM, citation=citation, config=CONFIG,
                      deps=deps())
    assert got.verdict == "unsupported"
    assert "quote-mismatch" in got.annotations


def test_a_quote_found_elsewhere_is_annotated_and_still_entailed():
    other = chunk("s#c00002", text=PASSAGE, locator="p. 400")
    here = chunk("s#c00001", text="an unrelated paragraph about lexing", locator="p. 1")
    ctx = ScriptedCtx(ent("supported"))
    citation = CitationInput("s", "p. 1", quote="destructures a value against a sequence")
    got = verify_pair(ctx, None, claim=CLAIM, citation=citation, config=CONFIG,
                      deps=deps(store=FakeStore([here, other])))
    assert "quote-found-elsewhere" in got.annotations
    assert got.verdict in ("supported", "partial")


def test_an_over_cap_quote_is_rejected_before_the_model_sees_it():
    # D14's 50-word cap binds the verifier's own inputs too: a 200-word "quote" is a
    # licensing problem, not a citation.
    ctx = ScriptedCtx()
    citation = CitationInput("s", "p. 1", quote=" ".join(["word"] * 60))
    got = verify_pair(ctx, None, claim=CLAIM, citation=citation, config=CONFIG,
                      deps=deps())
    assert got.verdict == "unsupported"
    assert "quote cap" in got.detail
    assert ctx.aliases == []


def test_a_partial_verdict_escalates_to_the_reasoning_model():
    ctx = ScriptedCtx(ent("supported", "not-supported", kinds=["presence", "qualifier"]),
                      ent("supported", "not-supported", kinds=["presence", "qualifier"]))
    got = verify_pair(ctx, None, claim=CLAIM, citation=CITATION, config=CONFIG,
                      deps=deps())
    assert ctx.aliases[:2] == ["deepseek", "deepseek-thinking"]
    assert got.verdict == "partial"


def test_an_escalation_that_reverses_the_verdict_wins():
    ctx = ScriptedCtx(ent("supported", "not-supported", kinds=["presence", "qualifier"]),
                      ent("supported"))
    got = verify_pair(ctx, None, claim=CLAIM, citation=CITATION, config=CONFIG,
                      deps=deps())
    assert got.verdict == "supported"


def test_the_second_opinion_disagreement_is_recorded_not_acted_on():
    # The `mini` sample is a drift gauge, not a vote (until the hardening flag flips).
    config = IngestConfig.load(overrides={"second_opinion_rate": 1.0})
    ctx = ScriptedCtx(ent("supported"), ent("supported", "not-supported",
                                            kinds=["presence", "qualifier"]))
    got = verify_pair(ctx, None, claim=CLAIM, citation=CITATION, config=config,
                      deps=deps())
    assert ctx.aliases == ["deepseek", "mini"]
    assert got.verdict == "supported"
    assert "second-opinion-disagreement" in got.detail


def test_a_mandatory_second_vote_downgrades_a_disputed_supported():
    # When the second opinion's verdict is the one that gets recorded, its resolved
    # model id must travel with it — otherwise the ledger row is not re-derivable: it
    # would claim the primary model produced a verdict it never actually returned.
    config = IngestConfig.load(overrides={"second_opinion_rate": 1.0,
                                          "mandatory_second_opinion": True})
    ctx = ScriptedCtx((ent("supported"), "primary-model"),
                      (ent("supported", "not-supported", kinds=["presence", "qualifier"]),
                       "second-opinion-model"))
    got = verify_pair(ctx, None, claim=CLAIM, citation=CITATION, config=config,
                      deps=deps())
    assert got.verdict == "partial"
    assert got.model == "second-opinion-model"


def test_a_registry_existence_claim_needs_no_evidence():
    ctx = ScriptedCtx()
    claim = ClaimInput(fact_id="f-000000000002", claim="source-exists(s)",
                       registry_existence=True)
    got = verify_pair(ctx, None, claim=claim, citation=CITATION, config=CONFIG,
                      deps=deps(index=FakeIndex([])))
    assert got.verdict == "supported"
    assert ctx.aliases == []


def test_an_absent_claim_routes_through_the_d49_ladder():
    ctx = ScriptedCtx(ent("supported"))
    claim = ClaimInput(fact_id="f-000000000003",
                       claim="instance-exists(fi.c.generics, status=absent)",
                       status="absent", absence_scope="the type chapter",
                       feature_aliases=("generics",))
    got = verify_pair(ctx, None, claim=claim, citation=CITATION, config=CONFIG,
                      deps=deps(), grep_chunk_ids=())
    assert got.verdict == "supported"


def test_an_escalating_absent_claim_stays_on_the_inverted_absence_prompt():
    # Finding 1: an `absent` claim that escalates must be re-run through `run_absence`
    # (the inverted-framing prompt), never through `run_entailment` (the presence
    # prompt) -- otherwise the model is asked the wrong question and the recorded
    # prompt_version misattributes which prompt actually produced the verdict.
    ctx = ScriptedCtx(ent("supported", "not-supported", kinds=["presence", "qualifier"]),
                      ent("supported"))
    claim = ClaimInput(fact_id="f-000000000004",
                       claim="instance-exists(fi.c.generics, status=absent)",
                       status="absent", absence_scope="the type chapter",
                       feature_aliases=("generics",))
    got = verify_pair(ctx, None, claim=claim, citation=CITATION, config=CONFIG,
                      deps=deps(), grep_chunk_ids=())
    assert ctx.aliases == ["deepseek", "deepseek-thinking"]
    assert got.verdict == "supported"

    from langatlas_pipeline.prompts import load_prompt
    assert got.prompt_version == load_prompt("verify-absence").version
    # Both calls' rendered messages must carry the absence prompt's own wording, never
    # entailment's -- a wrong-prompt escalation would not raise (run_entailment happily
    # ignores payload keys it doesn't render), so message content is what catches it.
    for messages in ctx.messages:
        user_text = messages[-1]["content"]
        assert "Absence scope argued by the claimant" in user_text
        assert "Version claimed" not in user_text


def test_the_verdict_is_written_to_the_ledger_when_one_is_supplied(tmp_path):
    from langatlas_ingest.verify.ledger import VerdictLedger
    ctx = ScriptedCtx(ent("supported"))
    with VerdictLedger(tmp_path / "v.sqlite") as ledger:
        verify_pair(ctx, None, claim=CLAIM, citation=CITATION, config=CONFIG,
                    deps=deps(ledger=ledger))
        assert len(ledger.all_for("f-000000000001")) == 1
