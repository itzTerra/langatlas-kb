import pytest
from langatlas_ingest.chunker import chunk_document, count_tokens
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.errors import ExtractionFailed
from langatlas_ingest.extract import Block, ExtractedDocument
from langatlas_validate.locators import validate_locator_shape

CONFIG = IngestConfig.load(overrides={"chunk_target_tokens": 40, "chunk_max_tokens": 60,
                                      "chunk_overlap_tokens": 8})


def body(words: int, word: str = "evaluation") -> str:
    return " ".join([word] * words)


def pdf_doc() -> ExtractedDocument:
    return ExtractedDocument(
        source_id="ctm", media_type="application/pdf", backend="fake", backend_version="0",
        page_count=3, outline=["1 Introduction", "2 Declarative programming"],
        blocks=[
            Block(text="1 Introduction", page=1, heading_level=1),
            Block(text=body(60), page=1),
            Block(text=body(60), page=2),
            Block(text="2 Declarative programming", page=3, heading_level=1),
            Block(text=body(20), page=3),
        ])


def html_doc() -> ExtractedDocument:
    return ExtractedDocument(
        source_id="rust-ref", media_type="text/html", backend="fake", backend_version="0",
        page_count=0, outline=["Expressions", "Match expressions"],
        blocks=[
            Block(text="Expressions", heading_level=1, anchor="expressions"),
            Block(text=body(30)),
            Block(text="Match expressions", heading_level=2, anchor="match-expressions"),
            Block(text=body(30)),
        ])


def test_chunks_stay_inside_the_size_band():
    chunks = chunk_document(pdf_doc(), config=CONFIG, locator_kinds=["book-page"])
    assert chunks
    assert all(c.token_count <= CONFIG.chunk_max_tokens for c in chunks)


def test_every_emitted_locator_satisfies_1as_grammar():
    for doc, kinds in [(pdf_doc(), ["book-page"]), (html_doc(), ["web-fragment"])]:
        for chunk in chunk_document(doc, config=CONFIG, locator_kinds=kinds):
            assert validate_locator_shape(chunk.locator) == chunk.locator_kind


def test_page_locators_span_the_pages_the_chunk_actually_covers():
    chunks = chunk_document(pdf_doc(), config=CONFIG, locator_kinds=["book-page"])
    spanning = [c for c in chunks if c.page_start != c.page_end]
    assert all(c.locator == f"pp. {c.page_start}–{c.page_end}" for c in spanning)
    assert all(c.locator == f"p. {c.page_start}"
               for c in chunks if c.page_start == c.page_end)


def test_breadcrumbs_and_section_paths_follow_the_heading_stack():
    chunks = chunk_document(html_doc(), config=CONFIG, locator_kinds=["web-fragment"])
    last = chunks[-1]
    assert last.section_path == ["Expressions", "Match expressions"]
    assert last.breadcrumb == "Expressions > Match expressions"
    assert last.text.startswith("Expressions > Match expressions\n\n")   # embedded prefix


def test_html_locators_use_the_nearest_heading_anchor():
    chunks = chunk_document(html_doc(), config=CONFIG, locator_kinds=["web-fragment"])
    assert chunks[0].locator == "#expressions"
    assert chunks[-1].locator == "#match-expressions"


def test_chunks_in_one_section_share_a_parent_section_id():
    chunks = chunk_document(pdf_doc(), config=CONFIG, locator_kinds=["book-page"])
    first_section = [c for c in chunks if c.section_path == ["1 Introduction"]]
    assert len({c.parent_section_id for c in first_section}) == 1
    assert first_section[0].parent_section_id.startswith("ctm#s")


def test_numbered_headings_prefer_the_section_grammar():
    chunks = chunk_document(pdf_doc(), config=CONFIG,
                            locator_kinds=["numbered-section", "book-page"])
    assert chunks[0].locator == "§1"
    assert chunks[0].locator_kind == "numbered-section"
    assert chunks[0].section_number == "1"


def test_ids_are_stable_and_ordered():
    chunks = chunk_document(pdf_doc(), config=CONFIG, locator_kinds=["book-page"])
    assert [c.chunk_id for c in chunks] == [f"ctm#c{i:05d}" for i in range(len(chunks))]
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    again = chunk_document(pdf_doc(), config=CONFIG, locator_kinds=["book-page"])
    assert [c.content_hash for c in again] == [c.content_hash for c in chunks]


def test_consecutive_chunks_in_a_section_overlap():
    chunks = chunk_document(pdf_doc(), config=CONFIG, locator_kinds=["book-page"])
    intro = [c for c in chunks if c.section_path == ["1 Introduction"]]
    assert len(intro) > 1
    tail = " ".join(intro[0].text.split()[-4:])
    assert tail in intro[1].text


def test_an_oversized_single_block_is_split_not_dropped():
    doc = ExtractedDocument(source_id="s", media_type="application/pdf", backend="f",
                            backend_version="0", page_count=1, outline=[],
                            blocks=[Block(text="A", page=1, heading_level=1),
                                    Block(text=body(500), page=1)])
    chunks = chunk_document(doc, config=CONFIG, locator_kinds=["book-page"])
    assert len(chunks) > 5
    assert all(c.token_count <= CONFIG.chunk_max_tokens for c in chunks)


def test_no_admissible_locator_kind_is_a_hard_failure():
    doc = ExtractedDocument(source_id="s", media_type="text/plain", backend="f",
                            backend_version="0", page_count=0, outline=[],
                            blocks=[Block(text=body(30))])
    with pytest.raises(ExtractionFailed, match="locator"):
        chunk_document(doc, config=CONFIG, locator_kinds=["book-page"])


def test_count_tokens_is_the_documented_chars_over_four_rule():
    assert count_tokens("abcd" * 10) == 10


def test_an_oversized_block_with_no_word_boundaries_is_not_silently_dropped():
    # A block that exceeds chunk_max_tokens but has no spaces to split on (one long
    # whitespace run, or in practice a giant unbroken token) must still surface in a
    # chunk -- word-boundary splitting has nowhere to cut, but the content still has
    # to be reachable by a locator rather than vanishing without a trace.
    doc = ExtractedDocument(source_id="w", media_type="application/pdf", backend="f",
                            backend_version="0", page_count=1, outline=[],
                            blocks=[Block(text="1", page=1, heading_level=1),
                                    Block(text=" " * 1000, page=1)])
    chunks = chunk_document(doc, config=CONFIG, locator_kinds=["book-page"])
    assert chunks
    assert sum(len(c.text) for c in chunks) > len("1\n\n")


def test_a_skipped_heading_level_still_nests_correctly():
    # Real documents jump straight from h1 to h3 with no h2 in between. The section
    # stack must nest the h3 under the h1 rather than dropping or misplacing it.
    doc = ExtractedDocument(
        source_id="skip", media_type="text/html", backend="fake", backend_version="0",
        page_count=0, outline=[],
        blocks=[
            Block(text="Top", heading_level=1, anchor="top"),
            Block(text=body(10)),
            Block(text="Deep", heading_level=3, anchor="deep"),
            Block(text=body(10)),
        ])
    chunks = chunk_document(doc, config=CONFIG, locator_kinds=["web-fragment"])
    assert [c.section_path for c in chunks] == [["Top"], ["Top", "Deep"]]
    assert chunks[1].breadcrumb == "Top > Deep"
    assert chunks[0].parent_section_id != chunks[1].parent_section_id


def test_no_two_chunks_share_a_content_hash_and_none_is_pure_overlap():
    # At production-scale config (600/800/60), a carry that still doesn't fit against
    # a fresh piece must be discarded, never flushed as its own chunk -- flushing it
    # emits a contentless, byte-identical duplicate of the chunk it was carried from.
    words = " ".join(f"word{i}" for i in range(4000))
    doc = ExtractedDocument(source_id="s", media_type="application/pdf", backend="f",
                            backend_version="0", page_count=1, outline=[],
                            blocks=[Block(text="1 A", page=1, heading_level=1),
                                    Block(text=words, page=1)])
    config = IngestConfig.load()  # real 600/800/60 band, not the test's shrunk one
    chunks = chunk_document(doc, config=config, locator_kinds=["book-page"])
    assert len(chunks) > 1

    hashes = [c.content_hash for c in chunks]
    assert len(hashes) == len(set(hashes)), "two chunks share a content_hash"

    for prev, cur in zip(chunks, chunks[1:]):
        if cur.section_path != prev.section_path:
            continue
        prev_words = set(prev.text.split("\n\n", 1)[-1].split())
        cur_words = set(cur.text.split("\n\n", 1)[-1].split())
        assert not cur_words <= prev_words, \
            "chunk contributes no content beyond what it carried from its predecessor"


def test_page_range_reflects_only_the_blocks_that_contributed_text():
    # A section with no body of its own (heading immediately followed by another
    # heading) must not leak its heading's page into the next section's citation.
    doc = ExtractedDocument(source_id="pl", media_type="application/pdf", backend="f",
                            backend_version="0", page_count=5, outline=[],
                            blocks=[Block(text="1 A", page=1, heading_level=1),
                                    Block(text="2 B", page=5, heading_level=1),
                                    Block(text="some body text here", page=5)])
    chunks = chunk_document(doc, config=CONFIG, locator_kinds=["book-page"])
    assert len(chunks) == 1
    assert chunks[0].page_start == 5
    assert chunks[0].page_end == 5
    assert chunks[0].locator == "p. 5"


def test_a_single_unbreakable_oversized_word_is_hard_cut_within_budget():
    # A "word" (no internal whitespace) wider than chunk_max_tokens can't be reduced
    # by joining -- it has to be hard-cut, and the resulting pieces (even if visually
    # identical, e.g. a run of the same character) must each fit the budget rather
    # than being emitted whole and over-limit.
    doc = ExtractedDocument(source_id="gw", media_type="application/pdf", backend="f",
                            backend_version="0", page_count=1, outline=[],
                            blocks=[Block(text="1", page=1, heading_level=1),
                                    Block(text="x" * 1000, page=1)])
    chunks = chunk_document(doc, config=CONFIG, locator_kinds=["book-page"])
    assert chunks
    assert all(c.token_count <= CONFIG.chunk_max_tokens for c in chunks)
