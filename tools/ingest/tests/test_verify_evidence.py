import pytest
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.store import SourceChunk
from langatlas_ingest.verify.evidence import (
    BOUNCE_HINT_K, Evidence, SMALL_CHUNK_TOKENS, resolve_evidence,
)

CONFIG = IngestConfig.load(overrides={"max_section_tokens": 5000, "relevance_floor": 0.0})


def chunk(chunk_id, *, locator="p. 1", text="body", tokens=1000, parent="s#s0001"):
    return SourceChunk(chunk_id=chunk_id, source_id="s", ordinal=1, parent_section_id=parent,
                       section_path=["Ch"], breadcrumb="Ch", locator=locator,
                       locator_kind="book-page", page_start=1, page_end=1,
                       section_number=None, anchor=None, line_start=None, line_end=None,
                       text=text, token_count=tokens, content_hash="h")


class FakeIndex:
    def __init__(self, ids):
        self.ids = ids

    def resolve(self, source_id, locator):
        return list(self.ids)


class FakeStore:
    def __init__(self, chunks):
        self.chunks = {c.chunk_id: c for c in chunks}

    def get(self, chunk_id):
        return self.chunks.get(chunk_id)


class FakeSearch:
    def __init__(self, hits=(), section=()):
        self.hits = list(hits)
        self.section = list(section)
        self.searched = []

    def search(self, query, *, k=None, source_ids=None):
        self.searched.append((query, k, source_ids))
        return self.hits

    def get_section(self, chunk_id, expand="parent"):
        return self.section


class Hit:
    def __init__(self, c, score):
        self.chunk = c
        self.score = score


def test_an_exact_locator_string_match_reports_exact():
    c = chunk("s#c00001", locator="p. 11")
    got = resolve_evidence(None, None, source_id="s", locator="p. 11", claim_text="x",
                           config=CONFIG, index=FakeIndex(["s#c00001"]),
                           store=FakeStore([c]), search=FakeSearch())
    assert got.resolution == "exact"
    assert got.chunk_ids == ("s#c00001",)
    assert got.text == "body"


def test_an_overlap_only_match_reports_containment():
    # Section 4.3's join is *overlap*: a citation to `p. 11` is backed by a chunk
    # covering pages 10-12, whose own display locator reads `pp. 10-12`.
    c = chunk("s#c00001", locator="pp. 10–12")
    got = resolve_evidence(None, None, source_id="s", locator="p. 11", claim_text="x",
                           config=CONFIG, index=FakeIndex(["s#c00001"]),
                           store=FakeStore([c]), search=FakeSearch())
    assert got.resolution == "containment"


def test_a_short_chunk_is_expanded_to_its_parent_section():
    small = chunk("s#c00001", tokens=SMALL_CHUNK_TOKENS - 1, text="short")
    sibling = chunk("s#c00002", tokens=200, text="sibling")
    search = FakeSearch(section=[small, sibling])
    got = resolve_evidence(None, None, source_id="s", locator="p. 1", claim_text="x",
                           config=CONFIG, index=FakeIndex(["s#c00001"]),
                           store=FakeStore([small]), search=search)
    assert got.expanded is True
    assert got.chunk_ids == ("s#c00001", "s#c00002")
    assert "sibling" in got.text


def test_expansion_is_skipped_when_the_section_exceeds_the_token_ceiling():
    small = chunk("s#c00001", tokens=SMALL_CHUNK_TOKENS - 1, text="short")
    huge = chunk("s#c00002", tokens=CONFIG.max_section_tokens + 1, text="huge")
    got = resolve_evidence(None, None, source_id="s", locator="p. 1", claim_text="x",
                           config=CONFIG, index=FakeIndex(["s#c00001"]),
                           store=FakeStore([small]), search=FakeSearch(section=[small, huge]))
    assert got.expanded is False
    assert got.chunk_ids == ("s#c00001",)


def test_a_long_chunk_is_not_expanded():
    big = chunk("s#c00001", tokens=SMALL_CHUNK_TOKENS + 1)
    search = FakeSearch(section=[big, chunk("s#c00002")])
    resolve_evidence(None, None, source_id="s", locator="p. 1", claim_text="x",
                     config=CONFIG, index=FakeIndex(["s#c00001"]),
                     store=FakeStore([big]), search=search)
    assert search.section  # unused: get_section was never consulted
    assert search.searched == []


def test_an_unresolvable_locator_yields_no_chunks_and_a_bounce_hint():
    elsewhere = chunk("s#c00099", locator="p. 400", text="the real passage")
    search = FakeSearch(hits=[Hit(elsewhere, 0.9)])
    got = resolve_evidence(None, None, source_id="s", locator="p. 1",
                           claim_text="pattern matching", config=CONFIG,
                           index=FakeIndex([]), store=FakeStore([elsewhere]), search=search)
    assert got.chunk_ids == ()
    assert got.resolution == "none"
    # The rescue is a HINT. It must never become evidence — a strong hit far from the
    # claimed locator is `locator-not-found` plus a pointer, not a silent pass.
    assert got.text == ""
    assert "p. 400" in got.hint
    assert search.searched == [("pattern matching", BOUNCE_HINT_K, ["s"])]


def test_a_rescue_below_the_relevance_floor_produces_no_hint():
    config = IngestConfig.load(overrides={"relevance_floor": 0.5})
    search = FakeSearch(hits=[Hit(chunk("s#c00099"), 0.1)])
    got = resolve_evidence(None, None, source_id="s", locator="p. 1", claim_text="x",
                           config=config, index=FakeIndex([]), store=FakeStore([]),
                           search=search)
    assert got.hint == ""


@pytest.mark.db
def test_resolution_against_the_real_index(searchable, fake_ctx):
    got = resolve_evidence(searchable, fake_ctx, source_id="s", locator="p. 1",
                           claim_text="lazy", config=CONFIG)
    assert got.chunk_ids
    assert isinstance(got, Evidence)
