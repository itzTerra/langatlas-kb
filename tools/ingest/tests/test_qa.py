from langatlas_ingest.chunker import chunk_document
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.extract import Block, ExtractedDocument
from langatlas_ingest.qa import run_qa

CONFIG = IngestConfig.load(overrides={"chunk_target_tokens": 40, "chunk_max_tokens": 60,
                                      "chunk_overlap_tokens": 8})

# "cafe" with an acute accent, encoded UTF-8 and read back as latin-1 — the canonical
# mojibake signature. Written with escapes so the fixture cannot itself be re-mangled.
MOJIBAKE_WORD = "cafÃ©"

# "Doesn't" with a curly apostrophe, encoded UTF-8 and read back as cp1252 -- the
# *dominant* real-world mojibake signature (curly quotes/dashes, not just accented
# Latin-1 letters). Written with escapes so the fixture cannot itself be re-mangled.
MOJIBAKE_CP1252_WORD = "Doesnâ€™t"


def make_doc(blocks, outline=(), page_count=2):
    return ExtractedDocument(source_id="s", media_type="application/pdf", backend="f",
                             backend_version="0", page_count=page_count,
                             blocks=list(blocks), outline=list(outline))


def clean_doc():
    return make_doc([
        Block(text="1 Introduction", page=1, heading_level=1),
        Block(text=("Lazy evaluation defers a computation until its value is demanded by "
                    "the surrounding program, which changes the cost model. ") * 4, page=1),
        Block(text="2 Types", page=2, heading_level=1),
        Block(text=("A type system assigns types to terms and rejects programs whose terms "
                    "cannot be assigned any type at all. ") * 4, page=2),
    ], outline=["1 Introduction", "2 Types"])


def qa_for(doc):
    return run_qa(doc, chunk_document(doc, config=CONFIG, locator_kinds=["book-page"]))


def test_a_clean_document_passes_everything():
    report = qa_for(clean_doc())
    assert report.hard_failures == []
    assert all(check.passed for check in report.checks)
    assert report.outline_coverage == 1.0
    assert report.status == "pass"


def test_mojibake_is_a_hard_failure():
    doc = clean_doc()
    doc.blocks.append(Block(text=(MOJIBAKE_WORD + " ") * 40, page=2))
    report = qa_for(doc)
    assert [c.check_id for c in report.hard_failures] == ["encoding"]
    assert report.to_dict()["qa_status"] == "fail"


def test_cp1252_mojibake_is_a_hard_failure():
    """UTF-8 curly quotes/dashes misread as cp1252 (â€™, â€œ, â€"...) is the dominant
    real-world mojibake signature -- more common than the accented-Latin-1 case above."""
    doc = clean_doc()
    doc.blocks.append(Block(text=(MOJIBAKE_CP1252_WORD + " ") * 40, page=2))
    report = qa_for(doc)
    assert [c.check_id for c in report.hard_failures] == ["encoding"]
    assert report.to_dict()["qa_status"] == "fail"


def test_extraction_collapse_is_a_hard_failure():
    """A PDF that extracts to a handful of characters per page did not really extract."""
    doc = make_doc([Block(text="A", page=1, heading_level=1), Block(text="b c", page=1)])
    report = qa_for(doc)
    assert "extraction-collapse" in [c.check_id for c in report.hard_failures]


def test_extraction_collapse_counts_non_whitespace_characters():
    """Layout whitespace (justified-text padding, table-cell gaps) can pad a near-empty
    extraction past both length thresholds on raw length alone; only non-whitespace
    characters count as evidence the extractor actually found text."""
    doc = make_doc([Block(text="A", page=1, heading_level=1),
                    Block(text=" " * 3000, page=1), Block(text=" " * 3000, page=2)])
    report = qa_for(doc)
    assert "extraction-collapse" in [c.check_id for c in report.hard_failures]


def test_ocr_noise_is_soft():
    doc = clean_doc()
    doc.blocks.append(Block(text=("rn0dern pr0grarnrn1ng l4ngu4ges 0ffer p4ttern m4tch1ng "
                                  "1n rn0st 0f the1r rn41n d14lects t0d4y. ") * 6, page=2))
    report = qa_for(doc)
    ocr = next(c for c in report.checks if c.check_id == "ocr-noise")
    assert not ocr.passed and ocr.severity == "soft"
    assert report.hard_failures == []
    assert report.status == "warn"


def test_length_outliers_are_soft():
    doc = clean_doc()
    doc.blocks.append(Block(text="x " * 4000, page=2))
    report = qa_for(doc)
    outlier = next(c for c in report.checks if c.check_id == "length-outliers")
    assert outlier.severity == "soft"
    assert not outlier.passed


def test_outline_gaps_are_reported_but_soft():
    doc = clean_doc()
    doc.outline.append("3 Concurrency")           # in the ToC, never reached by the chunker
    report = qa_for(doc)
    coverage = next(c for c in report.checks if c.check_id == "outline-coverage")
    assert coverage.severity == "soft" and not coverage.passed
    assert report.missing_sections == ["3 Concurrency"]
    assert report.outline_coverage == 2 / 3
    assert report.hard_failures == []


def test_a_document_without_an_outline_is_a_silent_no_op():
    """Section 4.4: sources with no machine-readable outline get no finding at all."""
    doc = clean_doc()
    doc.outline = []
    report = qa_for(doc)
    assert [c.check_id for c in report.checks if c.check_id == "outline-coverage"] == []
    assert report.outline_coverage is None
    assert report.status == "pass"


def test_outline_diff_tolerates_numbering_punctuation_drift():
    """A PDF's bookmark title (doc.get_toc()) and its in-body heading text come from
    different code paths and routinely disagree on numbering punctuation alone -- e.g.
    a bookmark titled "1 Introduction" for a heading rendered "1. Introduction". That
    is not a real extraction gap and must not be reported as one."""
    doc = make_doc([
        Block(text="1. Introduction", page=1, heading_level=1),
        Block(text=("Lazy evaluation defers a computation until its value is demanded by "
                    "the surrounding program, which changes the cost model. ") * 4, page=1),
    ], outline=["1 Introduction"], page_count=1)
    report = qa_for(doc)
    assert report.outline_coverage == 1.0
    assert report.missing_sections == []


def test_outline_diff_keeps_same_titled_sections_under_different_numbers_distinct():
    """Language references repeat subsection titles ("Syntax", "Semantics", ...) under
    every chapter. Normalizing away the numbering *separator* must not also discard the
    number itself -- "3.1 Syntax" and "4.2 Syntax" are different sections, and a real gap
    in one must not be hidden by the other's chunk."""
    doc = make_doc([
        Block(text="3 Expressions", page=1, heading_level=1),
        Block(text="3.1 Syntax", page=1, heading_level=2),
        Block(text=("The grammar for an expression is given by this production rule "
                    "and its accompanying precedence table below. ") * 4, page=1),
        # Note: no "4.2 Syntax" section is ever chunked.
    ], outline=["3.1 Syntax", "4.2 Syntax"], page_count=1)
    report = qa_for(doc)
    assert report.missing_sections == ["4.2 Syntax"]
    assert report.outline_coverage == 0.5


def test_markdown_report_names_every_failing_check():
    doc = clean_doc()
    doc.outline.append("3 Concurrency")
    markdown = qa_for(doc).to_markdown()
    assert markdown.startswith("# Extraction QA")
    assert "outline-coverage" in markdown and "3 Concurrency" in markdown
