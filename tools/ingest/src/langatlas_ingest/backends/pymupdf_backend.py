import statistics
from pathlib import Path
from langatlas_ingest.errors import ExtractionFailed
from langatlas_ingest.extract import Block, ExtractedDocument
from langatlas_ingest.locators import canonical_text

_HEADING_RATIO = 1.15      # a span this much larger than body text is a heading
_HEADING_MAX_CHARS = 120   # ...and headings are short; a big-font paragraph is not one

# NFC + strip *and* whitespace collapse — `locators.canonical_text`, not a local subset
# of it. `_collect` joins spans with " ", and PDF text extraction hands back spans that
# already carry leading/trailing spaces, so a heading routinely comes out as
# "7.7.2 Introduction   to   Java   programming". Uncollapsed, that run reached two
# places it must never reach: the `section_path` the §4.3 named-section join compares
# (975 of the real corpus's 1263 chunks carry one), and the emitted locator string
# itself — a public citation rendering its own triple spaces.
_normalize = canonical_text


class PyMuPdfBackend:
    """Structure from font size and the PDF's own outline. Deliberately dumb and fast:
    the D37 QA harness is what tells the developer when a book needs the heavier
    `docling` backend instead (see the plan's stated assumption)."""

    name = "pymupdf"

    def __init__(self):
        import fitz

        self._fitz = fitz
        self.version = fitz.__doc__.split()[1] if fitz.__doc__ else fitz.VersionBind

    def extract(self, path: Path, *, source_id: str) -> ExtractedDocument:
        doc = self._fitz.open(path)
        try:
            spans = self._collect(doc)
            if not spans:
                raise ExtractionFailed(source_id, "extractor returned no text")
            body_size = statistics.median(size for _, _, size in spans)
            blocks = [
                Block(text=text, page=page,
                      heading_level=1 if (size >= body_size * _HEADING_RATIO
                                          and len(text) <= _HEADING_MAX_CHARS) else 0)
                for page, text, size in spans
            ]
            outline = [_normalize(entry[1]) for entry in doc.get_toc()]
            return ExtractedDocument(source_id=source_id, media_type="application/pdf",
                                     backend=self.name, backend_version=str(self.version),
                                     page_count=doc.page_count, blocks=blocks,
                                     outline=outline)
        finally:
            doc.close()

    def _collect(self, doc) -> list[tuple[int, str, float]]:
        collected: list[tuple[int, str, float]] = []
        for index, page in enumerate(doc, start=1):
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:      # 0 == text; images carry no locatable text
                    continue
                text = _normalize(" ".join(span["text"] for line in block["lines"]
                                           for span in line["spans"]))
                if not text:
                    continue
                size = max(span["size"] for line in block["lines"] for span in line["spans"])
                collected.append((index, text, size))
        return collected
