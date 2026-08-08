from pathlib import Path
from langatlas_ingest.extract import Block, ExtractedDocument


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
            text = (getattr(item, "text", "") or "").strip()
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
