from pathlib import Path
from langatlas_ingest.extract import Block, ExtractedDocument
from langatlas_ingest.locators import canonical_text


class DoclingBackend:
    """Opt-in layout-model backend (`uv sync --extra docling`, `pdf_backend: docling`).
    Same protocol as PyMuPdfBackend, so switching is a config change."""

    name = "docling"

    def __init__(self):
        from docling.document_converter import DocumentConverter
        from docling import __version__

        self._converter = DocumentConverter()
        self.version = __version__

    def extract(self, path: Path, *, source_id: str) -> ExtractedDocument:
        result = self._converter.convert(path).document
        blocks: list[Block] = []
        outline: list[str] = []
        for item, _level in result.iterate_items():
            # `canonical_text`, not `.strip()`: the same NFC + whitespace-collapse rule
            # every other backend applies (`locators.canonical_text`), so a heading this
            # backend produces keys identically to the same heading via pymupdf or HTML.
            # Bare `.strip()` left both an unnormalized form and internal whitespace runs
            # in `section_path`, which the §4.3 named-section join compares.
            text = canonical_text(getattr(item, "text", "") or "")
            if not text:
                continue
            label = str(getattr(item, "label", ""))
            page = None
            provenance = getattr(item, "prov", None)
            if provenance:
                page = provenance[0].page_no
            is_heading = "section_header" in label or "title" in label
            if is_heading:
                outline.append(text)
            blocks.append(Block(text=text, page=page, heading_level=1 if is_heading else 0))
        return ExtractedDocument(source_id=source_id, media_type="application/pdf",
                                 backend=self.name, backend_version=str(self.version),
                                 page_count=result.num_pages(), blocks=blocks,
                                 outline=outline)
