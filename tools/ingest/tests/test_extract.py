import pytest
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.errors import ExtractionFailed
from langatlas_ingest.extract import Block, ExtractedDocument, extract_document

# Wrapped in <article>: verified directly against the installed trafilatura that its
# structural "<head rend=hN>" output — which extract_html depends on — only appears once
# a document is substantial enough and (typically) sits inside a landmark element; the
# identical prose in a bare <body> flattens to plain paragraphs with no heading structure
# at all. A too-small or wrapper-less fixture would silently exercise the degenerate,
# headingless path instead of the real one.
HTML = """
<html><body>
  <nav>skip me</nav>
  <article>
  <h1 id="expressions">Expressions</h1>
  <p>An expression evaluates to a value. Every expression has a type, and the type is
  determined statically before the program runs, which is what makes the checker sound.</p>
  <h2 id="match-expressions">Match expressions</h2>
  <p>A match expression compares a scrutinee against a sequence of patterns and evaluates
  the arm belonging to the first pattern that matches the scrutinee successfully.</p>
  </article>
</body></html>
"""


# Real prose, repeated to a realistic section length. Thin fixtures fall into
# trafilatura's degenerate single-paragraph collapse, where no <head> is emitted at all —
# which is exactly how an earlier misdiagnosis of this backend survived two rounds of
# green tests. Anything asserting on heading structure has to clear that bar first.
PROSE = ("This section explains the material in enough depth that the extractor treats it "
         "as genuine article prose rather than incidental page furniture, which matters "
         "because a thin fixture collapses into the degenerate path instead. ") * 2


@pytest.fixture
def pdf(tmp_path):
    """Generated, not committed: a two-page PDF with a real outline entry per page."""
    import fitz

    doc = fitz.open()
    for index, (title, body) in enumerate(
            [("Chapter 1 Introduction", "Lazy evaluation defers a computation until its "
                                        "value is demanded by the surrounding program."),
             ("Chapter 2 Types", "A type system assigns types to terms and rejects the "
                                 "programs whose terms cannot be assigned any type.")]):
        page = doc.new_page()
        page.insert_text((72, 90), title, fontsize=20)
        page.insert_text((72, 130), body, fontsize=11)
    doc.set_toc([[1, "Chapter 1 Introduction", 1], [1, "Chapter 2 Types", 2]])
    path = tmp_path / "book.pdf"
    doc.save(path)
    return path


def test_pdf_extraction_keeps_pages_and_outline(pdf):
    doc = extract_document(pdf, source_id="book", media_type="application/pdf",
                           config=IngestConfig.load())

    assert doc.backend == "pymupdf"
    assert doc.page_count == 2
    assert doc.outline == ["Chapter 1 Introduction", "Chapter 2 Types"]
    assert {block.page for block in doc.blocks} == {1, 2}
    assert any(block.heading_level == 1 and "Introduction" in block.text
               for block in doc.blocks)
    assert any("Lazy evaluation" in block.text and block.heading_level == 0
               for block in doc.blocks)


def test_html_extraction_keeps_heading_anchors(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(HTML)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load(),
                           source_url="https://example.org/ref")

    headings = [(b.text, b.anchor) for b in doc.blocks if b.heading_level]
    assert headings == [("Expressions", "expressions"),
                        ("Match expressions", "match-expressions")]
    assert doc.outline == ["Expressions", "Match expressions"]
    assert "skip me" not in " ".join(b.text for b in doc.blocks)   # boilerplate removed
    assert all(block.page is None for block in doc.blocks)         # HTML has no pages


def test_html_heading_text_repeated_in_body_does_not_steal_the_anchor(tmp_path):
    """A body paragraph that happens to repeat an earlier heading's text verbatim (e.g. a
    one-word recap) must never be promoted into a heading, and must never carry that
    heading's anchor — the anchor is a citation locator, so a wrong one is worse than
    none."""
    html = """
    <html><body>
      <article>
      <h1 id="top">Guide</h1>
      <p>Intro paragraph with enough words to survive extraction and set the stage for
      what comes next in this reference document.</p>
      <h2 id="overview">Overview</h2>
      <p>This section explains the overview of the system in enough detail to survive
      extraction as its own paragraph.</p>
      <h2 id="details">Details</h2>
      <p>This section goes into details with plenty of words so it is not treated as
      boilerplate either by the extractor.</p>
      <p>Overview</p>
      <p>That one-word recap paragraph should not be mistaken for the heading above it,
      since it repeats a heading's exact text.</p>
      </article>
    </body></html>
    """
    path = tmp_path / "page.html"
    path.write_text(html)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load())

    overview_blocks = [b for b in doc.blocks if b.text == "Overview"]
    # exactly one "Overview" block is a heading (the real <h2>); any other block with the
    # same text must be plain body with no anchor
    heading_overviews = [b for b in overview_blocks if b.heading_level]
    assert len(heading_overviews) == 1
    assert heading_overviews[0].anchor == "overview"
    non_heading_overviews = [b for b in overview_blocks if not b.heading_level]
    assert all(b.anchor is None for b in non_heading_overviews)
    assert doc.outline.count("Overview") == 1


def test_html_body_paragraph_never_matches_a_later_heading(tmp_path):
    """A block's identity as a heading is a structural fact from trafilatura, not a text
    match, so a plain body paragraph that happens to spell out a heading's text further
    down the page must never be promoted, and must never steal that later heading's
    anchor or displace whatever real heading sits between them."""
    html = """
    <html><body>
      <article>
      <h1 id="top">Guide</h1>
      <p>Overview</p>
      <p>This intervening paragraph exists only to separate the misleading body text
      above from the real heading that shares its wording further down the page.</p>
      <h2 id="section-a">Section A</h2>
      <p>Section A covers the first real topic in enough depth to survive extraction as
      a distinct paragraph of prose in its own right.</p>
      <h2 id="overview">Overview</h2>
      <p>The real overview section arrives here, after Section A, and must keep its own
      anchor rather than losing it to the misleading paragraph above.</p>
      </article>
    </body></html>
    """
    path = tmp_path / "page.html"
    path.write_text(html)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load())

    headings = [(b.text, b.anchor) for b in doc.blocks if b.heading_level]
    assert headings == [("Guide", "top"), ("Section A", "section-a"), ("Overview", "overview")]
    assert doc.outline == ["Guide", "Section A", "Overview"]
    early_overview = doc.blocks[1]
    assert early_overview.text == "Overview"
    assert early_overview.heading_level == 0
    assert early_overview.anchor is None


def test_html_duplicate_heading_text_keeps_each_anchor(tmp_path):
    """Two distinct sections sharing a heading's exact text must each keep their own
    anchor, matched positionally in document order."""
    html = """
    <html><body>
      <article>
      <h1 id="top">Guide</h1>
      <p>Intro paragraph with enough words to survive extraction and set the stage for
      what comes next in this reference document.</p>
      <h2 id="notes-a">Notes</h2>
      <p>The first notes section covers early concerns worth writing down for later
      reference material in this guide.</p>
      <h2 id="notes-b">Notes</h2>
      <p>The second notes section covers later concerns that also deserve their own
      place in the written record.</p>
      </article>
    </body></html>
    """
    path = tmp_path / "page.html"
    path.write_text(html)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load())

    notes = [(b.text, b.anchor) for b in doc.blocks if b.heading_level and b.text == "Notes"]
    assert notes == [("Notes", "notes-a"), ("Notes", "notes-b")]
    assert doc.outline.count("Notes") == 2


def test_html_boilerplate_heading_does_not_block_real_headings(tmp_path):
    """A <nav> heading that trafilatura strips as boilerplate must never sit unmatched at
    the front of the pending-heading queue and block every real heading behind it — that
    would silently empty the whole outline, which is worse than the anchor-collision bug
    it replaced, since nearly every real page has a nav or header heading."""
    html = """
    <html><body>
      <nav><h2 id="nav-heading">Site Navigation</h2>
      <p>links links links links links links links links</p></nav>
      <article>
      <h1 id="top">Guide</h1>
      <p>Intro paragraph with enough words to survive extraction and set the stage for
      what comes next in this reference document.</p>
      <h2 id="overview">Overview</h2>
      <p>This part explains the design of the system in enough detail to survive
      extraction nicely as its own paragraph of prose.</p>
      <h2 id="details">Details</h2>
      <p>This section goes into details with plenty of words so it is not treated as
      boilerplate either by the extractor here.</p>
      </article>
    </body></html>
    """
    path = tmp_path / "page.html"
    path.write_text(html)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load())

    assert doc.outline == ["Guide", "Overview", "Details"]
    headings = [(b.text, b.anchor) for b in doc.blocks if b.heading_level]
    assert headings == [("Guide", "top"), ("Overview", "overview"), ("Details", "details")]
    assert "Site Navigation" not in " ".join(b.text for b in doc.blocks)


def test_html_boilerplate_heading_text_collision_degrades_to_no_anchor(tmp_path):
    """A boilerplate heading sharing its exact text with a real content heading is an
    unresolvable collision: the raw parse sees two "Overview" headings, trafilatura emits
    one, and nothing structural says which survived.

    This test previously asserted the real section's id here, which the tag-list exclusion
    in `_AnchorParser` used to supply. That exclusion was removed as unsound (it broke the
    superset precondition `_anchors_by_key` relies on, letting parity certify a wrong
    anchor — see the round-5 note in the task report), so `None` is now the deliberate
    outcome, not a regression: the real section's id is unrecoverable *soundly*, and a
    missing anchor beats a wrong one."""
    html = """
    <html><body>
      <nav><h2 id="nav-overview">Overview</h2>
      <p>links links links links links links links links</p></nav>
      <article>
      <h1 id="top">Guide</h1>
      <p>Intro paragraph with enough words to survive extraction and set the stage for
      what comes next in this reference document.</p>
      <h2 id="overview">Overview</h2>
      <p>This part explains the design of the system in enough detail to survive
      extraction nicely as its own paragraph of prose.</p>
      </article>
    </body></html>
    """
    path = tmp_path / "page.html"
    path.write_text(html)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load())

    headings = [(b.text, b.anchor) for b in doc.blocks if b.heading_level]
    assert headings == [("Guide", "top"), ("Overview", None)]
    # the heading and the outline survive intact; only the ambiguous anchor is dropped,
    # and the unambiguous "Guide" beside it is untouched
    assert doc.outline == ["Guide", "Overview"]


def test_html_dropped_boilerplate_div_never_lends_its_anchor(tmp_path):
    """trafilatura drops boilerplate on content heuristics, not on tag names: a
    `<div class="related-links">` disappears from its output while the raw-HTML parse still
    sees the heading inside it. The two views then disagree about how many "Overview"
    headings exist, and there is no structural basis for deciding which one survived — so
    the real heading must come back with no anchor rather than the promo id. An anchor is a
    public citation locator; missing is tolerable, wrong is not."""
    html = f"""
    <html><body>
      <article>
      <h1 id="top">Guide</h1>
      <p>{PROSE}</p>
      <h2 id="section-a">Section A</h2>
      <p>{PROSE}</p>
      <div class="related-links">
        <h2 id="promo-overview">Overview</h2>
        <p>Related links and other promotional material that the extractor ought to drop.</p>
      </div>
      <h2 id="real-overview">Overview</h2>
      <p>{PROSE}</p>
      </article>
    </body></html>
    """
    path = tmp_path / "page.html"
    path.write_text(html)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load())

    headings = [(b.text, b.anchor) for b in doc.blocks if b.heading_level]
    assert headings == [("Guide", "top"), ("Section A", "section-a"), ("Overview", None)]
    # the heading itself is still found, and unambiguous neighbours keep their anchors —
    # only the ambiguous one degrades
    assert doc.outline == ["Guide", "Section A", "Overview"]
    assert all(b.anchor != "promo-overview" for b in doc.blocks)


def test_html_same_text_heading_in_dropped_boilerplate_yields_no_anchor(tmp_path):
    """The same collision with only one real heading: a dropped `<div class="sidebar">`
    holds a heading whose text matches the real section's. The surviving heading must not
    inherit the sidebar's id just because it is the only candidate left standing."""
    html = f"""
    <html><body>
      <article>
      <h1 id="top">Guide</h1>
      <p>{PROSE}</p>
      <div class="sidebar">
        <h2 id="sidebar-notes">Notes</h2>
        <p>Sidebar filler that the extractor ought to drop from the article body.</p>
      </div>
      <h2 id="notes">Notes</h2>
      <p>{PROSE}</p>
      </article>
    </body></html>
    """
    path = tmp_path / "page.html"
    path.write_text(html)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load())

    headings = [(b.text, b.anchor) for b in doc.blocks if b.heading_level]
    assert headings == [("Guide", "top"), ("Notes", None)]
    assert doc.outline == ["Guide", "Notes"]
    assert "Sidebar filler" not in " ".join(b.text for b in doc.blocks)


def test_html_ambiguous_heading_run_yields_no_anchor_rather_than_a_guess(tmp_path):
    """Three raw "Notes" headings, one of them inside boilerplate trafilatura drops, so
    only two come back. Nothing says which two — matching them off in order would pair the
    second real section with the sidebar's id, confidently and wrongly. Both must be
    `None`, while every unambiguous heading on the page is unaffected: ambiguity degrades
    only itself."""
    html = f"""
    <html><body>
      <article>
      <h1 id="top">Guide</h1>
      <p>{PROSE}</p>
      <h2 id="notes-a">Notes</h2>
      <p>{PROSE}</p>
      <div class="sidebar">
        <h2 id="sidebar-notes">Notes</h2>
        <p>Sidebar filler that the extractor ought to drop from the article body.</p>
      </div>
      <h2 id="notes-b">Notes</h2>
      <p>{PROSE}</p>
      </article>
    </body></html>
    """
    path = tmp_path / "page.html"
    path.write_text(html)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load())

    headings = [(b.text, b.anchor) for b in doc.blocks if b.heading_level]
    assert headings == [("Guide", "top"), ("Notes", None), ("Notes", None)]
    assert doc.outline == ["Guide", "Notes", "Notes"]


def test_html_heading_in_an_article_header_keeps_its_anchor(tmp_path):
    """`<article><header><h1 id="title">` is an extremely common real-world shape, and
    trafilatura keeps that heading. The raw parse must therefore record it too — an earlier
    version skipped headings inside `header`/`nav`/`footer`/`aside`, which silently threw
    away a perfectly good anchor that was sitting right there in the markup."""
    html = f"""
    <html><body>
      <article>
      <header><h1 id="title">Guide</h1></header>
      <p>{PROSE}</p>
      <h2 id="section-a">Section A</h2>
      <p>{PROSE}</p>
      </article>
    </body></html>
    """
    path = tmp_path / "page.html"
    path.write_text(html)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load())

    headings = [(b.text, b.anchor) for b in doc.blocks if b.heading_level]
    assert headings == [("Guide", "title"), ("Section A", "section-a")]
    assert doc.outline == ["Guide", "Section A"]


def test_html_landmark_and_dropped_container_collision_yields_no_anchor(tmp_path):
    """The asymmetry that made the tag-list exclusion unsound, pinned so it cannot return.

    Two headings share the text "Overview": one inside `<article><header>` (which
    trafilatura *keeps*) and one inside a `<div class="related-links">` (which trafilatura
    *drops*). When the raw parse filtered `header`, each view was missing a *different*
    heading, the counts coincided at one apiece, and count parity "confirmed" a pairing
    between two headings that do not correspond — handing the real, kept heading the id of
    the dropped promo block. With the raw parse recording every heading, the counts are 2
    vs 1 and the anchor correctly degrades to `None`."""
    html = f"""
    <html><body>
      <article>
      <header><h2 id="hdr-overview">Overview</h2></header>
      <p>{PROSE}</p>
      <div class="related-links">
        <h2 id="promo-overview">Overview</h2>
        <p>Related links and other promotional material that the extractor ought to drop.</p>
      </div>
      <h2 id="real-sec">Details</h2>
      <p>{PROSE}</p>
      </article>
    </body></html>
    """
    path = tmp_path / "page.html"
    path.write_text(html)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load())

    headings = [(b.text, b.anchor) for b in doc.blocks if b.heading_level]
    assert headings == [("Overview", None), ("Details", "real-sec")]
    assert all(b.anchor != "promo-overview" for b in doc.blocks)
    assert doc.outline == ["Overview", "Details"]


def test_html_summary_derived_heading_does_not_take_a_dropped_elements_anchor(tmp_path):
    """trafilatura synthesizes `<head>` elements from markup that is not an `hN` tag at
    all — `convert_details` turns a `<summary>` into one. If the raw parse only looked for
    `h1`-`h6`, that synthesized heading was invisible to it, the raw list stopped being a
    superset of trafilatura's headings, and count parity could pair the `<summary>` block
    with a completely unrelated heading inside a dropped `<div class="related-links">` —
    handing it the promo id. Both "Overview" elements must be recorded for the counts to
    come out 2-vs-1 and the anchor to degrade correctly."""
    html = f"""
    <html><body>
      <article>
      <h1 id="top">Guide</h1>
      <p>{PROSE}</p>
      <div class="related-links">
        <h2 id="promo-overview">Overview</h2>
        <p>Related links and other promotional material that the extractor ought to drop.</p>
      </div>
      <details><summary>Overview</summary><p>{PROSE}</p></details>
      <h2 id="real-sec">Details</h2>
      <p>{PROSE}</p>
      </article>
    </body></html>
    """
    path = tmp_path / "page.html"
    path.write_text(html)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load())

    headings = [(b.text, b.anchor) for b in doc.blocks if b.heading_level]
    assert headings == [("Guide", "top"), ("Overview", None), ("Details", "real-sec")]
    assert all(b.anchor != "promo-overview" for b in doc.blocks)


def test_html_faq_question_heading_does_not_take_a_dropped_elements_anchor(tmp_path):
    """The other promotion path found in trafilatura's `htmlprocessing`: a Yoast FAQ
    question, `<strong class="schema-faq-question">`, becomes `<head rend="h3">`. Same
    exploit shape as the `<summary>` one, same required outcome."""
    html = f"""
    <html><body>
      <article>
      <h1 id="top">Guide</h1>
      <p>{PROSE}</p>
      <div class="related-links">
        <h2 id="promo-faq">What is it</h2>
        <p>Related links and other promotional material that the extractor ought to drop.</p>
      </div>
      <div class="schema-faq"><strong class="schema-faq-question">What is it</strong>
      <p>{PROSE}</p></div>
      <h2 id="real-sec">Details</h2>
      <p>{PROSE}</p>
      </article>
    </body></html>
    """
    path = tmp_path / "page.html"
    path.write_text(html)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load())

    headings = [(b.text, b.heading_level, b.anchor) for b in doc.blocks if b.heading_level]
    assert headings == [("Guide", 1, "top"), ("What is it", 3, None),
                        ("Details", 2, "real-sec")]
    assert all(b.anchor != "promo-faq" for b in doc.blocks)


def test_html_heading_without_a_rend_is_nested_deepest_not_promoted_to_top(tmp_path):
    """A `<summary>`-derived `<head>` carries no `rend`, so its level is ours to choose.
    It must not default to 1: the outline feeds a QA diff against the chunker's section
    paths, and a mid-document disclosure widget claiming top level would open a phantom
    section and reparent everything after it. Deepest is the honest reading of "synthesized
    heading of unknown rank" — it nests under the real section it sits in.

    Its anchor is still recoverable here (unique text, so counts agree at one apiece),
    which also pins that `<summary>` elements are recorded by the raw parse at all."""
    html = f"""
    <html><body>
      <article>
      <h1 id="top">Guide</h1>
      <p>{PROSE}</p>
      <h2 id="section-a">Section A</h2>
      <p>{PROSE}</p>
      <details><summary id="faq">Frequently asked questions</summary><p>{PROSE}</p></details>
      </article>
    </body></html>
    """
    path = tmp_path / "page.html"
    path.write_text(html)

    doc = extract_document(path, source_id="ref", media_type="text/html",
                           config=IngestConfig.load())

    headings = [(b.text, b.heading_level, b.anchor) for b in doc.blocks if b.heading_level]
    assert headings == [("Guide", 1, "top"), ("Section A", 2, "section-a"),
                        ("Frequently asked questions", 6, "faq")]
    assert doc.outline == ["Guide", "Section A", "Frequently asked questions"]


def test_empty_extraction_raises(tmp_path):
    path = tmp_path / "empty.html"
    path.write_text("<html><body></body></html>")
    with pytest.raises(ExtractionFailed, match="no text"):
        extract_document(path, source_id="x", media_type="text/html",
                         config=IngestConfig.load())


def test_unknown_media_type_raises(tmp_path):
    path = tmp_path / "thing.epub"
    path.write_bytes(b"x")
    with pytest.raises(ExtractionFailed, match="media type"):
        extract_document(path, source_id="x", media_type="application/epub+zip",
                         config=IngestConfig.load())


def test_char_count_is_derived():
    doc = ExtractedDocument(source_id="s", media_type="text/plain", backend="fake",
                            backend_version="0", page_count=0,
                            blocks=[Block(text="abcd"), Block(text="ef")], outline=[])
    assert doc.char_count == 6


def test_a_custom_backend_can_be_injected(tmp_path):
    class FakeBackend:
        name = "fake"
        version = "9"

        def extract(self, path, *, source_id):
            return ExtractedDocument(source_id=source_id, media_type="application/pdf",
                                     backend=self.name, backend_version=self.version,
                                     page_count=1, blocks=[Block(text="hi", page=1)],
                                     outline=[])

    path = tmp_path / "x.pdf"
    path.write_bytes(b"%PDF-")
    doc = extract_document(path, source_id="s", media_type="application/pdf",
                           config=IngestConfig.load(), backend=FakeBackend())
    assert doc.backend == "fake"


def test_nul_bytes_are_stripped_at_the_extraction_boundary(tmp_path):
    """A PDF with an unmapped embedded font makes PyMuPDF emit U+0000 runs; Postgres
    `text` cannot store one, so it must not survive extraction (real case: Van Roy &
    Haridi 2003, 22 blocks near p. 685)."""
    class NulBackend:
        name = "fake"
        version = "9"

        def extract(self, path, *, source_id):
            return ExtractedDocument(source_id=source_id, media_type="application/pdf",
                                     backend=self.name, backend_version=self.version,
                                     page_count=1,
                                     blocks=[Block(text="lazy\x00 evaluation", page=1)],
                                     outline=["Chapter\x00 4"])

    path = tmp_path / "x.pdf"
    path.write_bytes(b"%PDF-")
    doc = extract_document(path, source_id="s", media_type="application/pdf",
                           config=IngestConfig.load(), backend=NulBackend())
    assert doc.blocks[0].text == "lazy evaluation"
    assert doc.outline == ["Chapter 4"]
