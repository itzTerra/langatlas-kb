import pytest
from langatlas_ingest.store import SourceChunk, SourceChunksStore
from langatlas_ingest.verify.absence import (
    NEGATIVE_GREP_LIMIT, negative_grep, run_absence,
)
from langatlas_ingest.verify.entailment import AssertionOut, EntailmentOut
from langatlas_ingest.verify.evidence import Evidence
from langatlas_ingest.verify.inputs import CitationInput, ClaimInput


def chunk(chunk_id, text, ordinal=1):
    return SourceChunk(chunk_id=chunk_id, source_id="s", ordinal=ordinal,
                       parent_section_id=None, section_path=[], breadcrumb="",
                       locator=f"p. {ordinal}", locator_kind="book-page",
                       page_start=ordinal, page_end=ordinal, section_number=None,
                       anchor=None, line_start=None, line_end=None, text=text,
                       token_count=10, content_hash="h")


CLAIM = ClaimInput(fact_id="f-1", claim="instance-exists(fi.c.generics, status=absent)",
                   status="absent", absence_scope="the whole C23 standard's type chapter",
                   feature_aliases=("generics", "parametric polymorphism"))
CITATION = CitationInput(source_id="s", locator="§6.7")


class FakeCompletion:
    def __init__(self, parsed):
        self.parsed = parsed
        self.resolved_model = "deepseek-v4"


class RecordingCtx:
    def __init__(self, out):
        self.out = out
        self.messages = None

    def tool_result(self, *, tool, text, source_id=None, kind="source-chunk"):
        from langatlas_pipeline.injection import delimit_untrusted
        return delimit_untrusted(text, source_id=source_id, kind=kind)

    def complete(self, alias, messages, *, prompt, schema=None, sampling=None):
        self.messages = messages
        return FakeCompletion(self.out)


class FakeStore:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def by_source(self, source_id):
        return list(self._chunks)

    def get(self, chunk_id):
        return next((c for c in self._chunks if c.chunk_id == chunk_id), None)


def out(status, kind="presence"):
    return EntailmentOut(assertions=[AssertionOut(kind=kind, text="t", status=status)])


@pytest.mark.db
def test_negative_grep_finds_word_boundary_matches_only(db_conn):
    from langatlas_ingest.db import migrate
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("s", [
        chunk("s#c00001", "The language has no generics.", 1),
        chunk("s#c00002", "Degenericized names are unrelated.", 2),
    ])
    hits = negative_grep(db_conn, "s", ("generics",))
    assert hits == ["s#c00001"]


@pytest.mark.db
def test_negative_grep_is_capped_per_alias(db_conn):
    from langatlas_ingest.db import migrate
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("s", [
        chunk(f"s#c{i:05d}", "generics appear here", i)
        for i in range(1, NEGATIVE_GREP_LIMIT + 5)])
    assert len(negative_grep(db_conn, "s", ("generics",))) == NEGATIVE_GREP_LIMIT


@pytest.mark.db
def test_run_absence_drives_real_negative_grep_end_to_end(searchable):
    # Every other run_absence test pre-supplies grep_chunk_ids, bypassing negative_grep
    # entirely. This is the one test that lets run_absence call the real, tsv-backed
    # negative_grep against a live Postgres connection and checks its hits actually reach
    # the rendered prompt — the FTS-deviation's interaction with the prompt-assembly path.
    SourceChunksStore(searchable).replace_source("s", [
        chunk("s#c00001", "Generics are declared with _Generic.", 1),
    ])
    ctx = RecordingCtx(out("contradicted"))
    got = run_absence(ctx, searchable, claim=CLAIM, citation=CITATION,
                      evidence=Evidence(chunk_ids=("s#c00001",), text="the cited passage"),
                      alias="deepseek")
    assert got.grep_chunk_ids == ("s#c00001",)
    rendered = "\n".join(m["content"] for m in ctx.messages)
    assert "_Generic" in rendered
    assert "the cited passage" in rendered


def test_a_source_that_documents_the_feature_yields_contradicted():
    # D49's inverse-K1 guard: false-absence laundering must not admit.
    ctx = RecordingCtx(out("contradicted"))
    store = FakeStore([chunk("s#c00007", "Generics are declared with _Generic.", 7)])
    got = run_absence(ctx, None, claim=CLAIM, citation=CITATION,
                      evidence=Evidence(chunk_ids=("s#c00001",), text="body"),
                      alias="deepseek", store=store, grep_chunk_ids=("s#c00007",))
    assert got.verdict == "contradicted"
    assert got.grep_chunk_ids == ("s#c00007",)


def test_a_silent_source_with_a_sound_scope_argument_is_supported():
    ctx = RecordingCtx(out("supported"))
    got = run_absence(ctx, None, claim=CLAIM, citation=CITATION,
                      evidence=Evidence(chunk_ids=("s#c00001",), text="body"),
                      alias="deepseek", store=FakeStore([]), grep_chunk_ids=())
    assert got.verdict == "supported"


def test_a_weak_scope_argument_is_unsupported():
    ctx = RecordingCtx(out("not-supported"))
    got = run_absence(ctx, None, claim=CLAIM, citation=CITATION,
                      evidence=Evidence(chunk_ids=("s#c00001",), text="body"),
                      alias="deepseek", store=FakeStore([]), grep_chunk_ids=())
    assert got.verdict == "unsupported"


def test_grep_hit_text_is_added_to_the_evidence_the_model_reads():
    ctx = RecordingCtx(out("contradicted"))
    store = FakeStore([chunk("s#c00007", "Generics are declared with _Generic.", 7)])
    run_absence(ctx, None, claim=CLAIM, citation=CITATION,
                evidence=Evidence(chunk_ids=("s#c00001",), text="the cited passage"),
                alias="deepseek", store=store, grep_chunk_ids=("s#c00007",))
    rendered = "\n".join(m["content"] for m in ctx.messages)
    assert "the cited passage" in rendered
    assert "_Generic" in rendered


def test_the_aliases_reach_the_prompt():
    ctx = RecordingCtx(out("supported"))
    run_absence(ctx, None, claim=CLAIM, citation=CITATION,
                evidence=Evidence(chunk_ids=("s#c00001",), text="body"),
                alias="deepseek", store=FakeStore([]), grep_chunk_ids=())
    rendered = "\n".join(m["content"] for m in ctx.messages)
    assert "parametric polymorphism" in rendered
