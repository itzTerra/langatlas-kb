import pytest
from langatlas_ingest.chunker import Chunk
from langatlas_ingest.db import migrate
from langatlas_ingest.goldens.items import Citation, Claim, VerifierItem
from langatlas_ingest.goldens.staleness import check_staleness
from langatlas_ingest.store import SourceChunksStore

pytestmark = pytest.mark.db


@pytest.fixture
def corpus(db_conn):
    migrate(db_conn)
    SourceChunksStore(db_conn).replace_source("ctm", [
        Chunk(chunk_id="ctm#c00001", source_id="ctm", ordinal=1,
              parent_section_id="ctm#s0001", section_path=["Ch"], breadcrumb="Ch",
              locator="p. 1", locator_kind="book-page", token_count=8, content_hash="h1",
              page_start=1, page_end=1, text="Lazy evaluation defers a computation.")])
    return db_conn


def item(item_id, chunks, locator="p. 1"):
    return VerifierItem(id=item_id, stratum="correct", expected_verdict="supported",
                        claim=Claim(kind="instance-exists",
                                    text="instance-exists(i-oz-lazy, status=present)"),
                        citation=Citation(source="ctm", locator=locator),
                        evidence_chunk_ids=chunks)


def test_a_live_item_is_not_stale(corpus):
    assert check_staleness(corpus, [item("a", ("ctm#c00001",))]) == []


def test_a_vanished_evidence_chunk_is_reported(corpus):
    stale = check_staleness(corpus, [item("a", ("ctm#c09999",))])
    assert [s.item_id for s in stale] == ["a"]
    assert "ctm#c09999" in stale[0].reason


def test_an_unresolvable_locator_is_reported(corpus):
    stale = check_staleness(corpus, [item("a", ("ctm#c00001",), locator="p. 4242")])
    assert "locator" in stale[0].reason


def test_a_fabricated_locator_item_is_never_reported_stale(corpus):
    fabricated = VerifierItem(
        id="a", stratum="fabricated-locator", expected_verdict="locator-not-found",
        claim=Claim(kind="instance-exists", text="instance-exists(i-oz-lazy, status=present)"),
        citation=Citation(source="ctm", locator="p. 4242"))
    assert check_staleness(corpus, [fabricated]) == []
