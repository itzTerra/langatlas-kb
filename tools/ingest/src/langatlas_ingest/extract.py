from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.errors import ExtractionFailed


@dataclass
class Block:
    """One extracted run of text. `heading_level` 0 means body text; 1..6 mirror h1..h6
    (PDF backends map outline depth onto the same scale)."""

    text: str
    page: int | None = None
    heading_level: int = 0
    anchor: str | None = None
    line_start: int | None = None
    line_end: int | None = None


@dataclass
class ExtractedDocument:
    source_id: str
    media_type: str
    backend: str
    backend_version: str
    page_count: int
    blocks: list[Block] = field(default_factory=list)
    outline: list[str] = field(default_factory=list)   # the source's own ToC, D37 §4.4
    source_url: str | None = None

    @property
    def char_count(self) -> int:
        return sum(len(block.text) for block in self.blocks)


class PdfBackend(Protocol):
    name: str
    version: str

    def extract(self, path: Path, *, source_id: str) -> ExtractedDocument: ...


def _pdf_backend(name: str) -> PdfBackend:
    if name == "pymupdf":
        from langatlas_ingest.backends.pymupdf_backend import PyMuPdfBackend

        return PyMuPdfBackend()
    if name == "docling":
        # Imported lazily: the docling extra is not installed by default (see the plan's
        # stated assumption), so naming it in config is what pulls it in.
        from langatlas_ingest.backends.docling_backend import DoclingBackend

        return DoclingBackend()
    raise ExtractionFailed("-", f"unknown pdf_backend {name!r}")


def extract_document(path: Path, *, source_id: str, media_type: str,
                     config: IngestConfig, backend: PdfBackend | None = None,
                     source_url: str | None = None) -> ExtractedDocument:
    """The one entry point. Dispatches on media type, then hands off to a backend that
    knows nothing about LangAtlas beyond `ExtractedDocument`."""
    if media_type == "application/pdf":
        doc = (backend or _pdf_backend(config.pdf_backend)).extract(Path(path),
                                                                    source_id=source_id)
    elif media_type in ("text/html", "application/xhtml+xml"):
        from langatlas_ingest.backends.html import extract_html

        doc = extract_html(Path(path), source_id=source_id)
    elif media_type == "text/plain":
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        doc = ExtractedDocument(source_id=source_id, media_type=media_type,
                                backend="plaintext", backend_version="1", page_count=0,
                                blocks=[Block(text=paragraph.strip())
                                        for paragraph in text.split("\n\n")
                                        if paragraph.strip()])
    else:
        raise ExtractionFailed(source_id, f"unsupported media type {media_type!r}")

    doc.source_url = source_url
    _strip_nuls(doc)
    if doc.char_count == 0:
        raise ExtractionFailed(source_id, "extractor returned no text")
    return doc


def _strip_nuls(doc: ExtractedDocument) -> None:
    """A PDF whose embedded font carries no unicode mapping makes PyMuPDF emit runs of
    U+0000 for the affected glyphs (Van Roy & Haridi 2003 does this on 22 blocks around
    p. 685). Postgres `text` cannot store a NUL at all, so an unstripped one aborts the
    whole `replace_source` write with `DataError` — and the character carries no
    information to lose. Stripped here, at the one entry point every backend passes
    through, so no downstream stage has to know about it and the stored text always
    matches the extracted text on disk.

    `block.anchor` is deliberately not stripped: today anchors come only from HTML `id`
    attributes, which cannot carry a NUL. A backend that ever synthesizes an anchor from
    extracted glyphs must add it here — `anchor` lands in a Postgres `text` column too."""
    for block in doc.blocks:
        if "\x00" in block.text:
            block.text = block.text.replace("\x00", "")
    doc.outline = [entry.replace("\x00", "") for entry in doc.outline]
