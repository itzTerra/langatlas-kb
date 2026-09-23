import re
from pathlib import Path
from langatlas_ingest.extract import Block, ExtractedDocument
from langatlas_ingest.locators import canonical_text

# CommonMark's ATX rule: 1-6 `#`s, then either end-of-line or whitespace before the
# heading text; a trailing run of `#`s is decorative and stripped. `#include`,
# `#!/usr/bin/env` and similar have no separating whitespace and are not headings.
_ATX_HEADING = re.compile(r"^(#{1,6})(?:\s+(.*?))?\s*#*\s*$")
_FENCE = re.compile(r"^(```|~~~)")
# GitHub's own heading-to-anchor rule (github/markup, `Markup::extensions::toc`):
# lowercase, drop anything that isn't a word char/space/hyphen, spaces to hyphens.
_ANCHOR_STRIP = re.compile(r"[^\w\s-]")


def _slugify(text: str) -> str:
    slug = _ANCHOR_STRIP.sub("", text.lower()).strip()
    return re.sub(r"\s+", "-", slug)


def extract_markdown(path: Path, *, source_id: str) -> ExtractedDocument:
    """ATX headings (`#` through `######`) become structure, GitHub-slugged so the same
    proposal's own cross-references resolve; everything else — including a `#` that
    opens no heading, inside a fenced code block or without the separating whitespace
    CommonMark requires — is body text, verbatim. No setext (`===`/`---`-underlined)
    headings: every source this backend has seen (RFCs, Swift evolution proposals) uses
    ATX exclusively, and guessing at a bare underline risks promoting a table divider or
    a horizontal rule."""
    blocks: list[Block] = []
    outline: list[str] = []
    paragraph: list[str] = []
    in_fence = False

    def flush_paragraph():
        if paragraph:
            blocks.append(Block(text=canonical_text("\n".join(paragraph))))
            paragraph.clear()

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if _FENCE.match(line.strip()):
            in_fence = not in_fence
            paragraph.append(line)
            continue
        if not in_fence:
            heading = _ATX_HEADING.match(line)
            if heading:
                flush_paragraph()
                text = canonical_text(heading.group(2) or "")
                if text:
                    level = len(heading.group(1))
                    outline.append(text)
                    blocks.append(Block(text=text, heading_level=level,
                                        anchor=_slugify(text)))
                continue
            if not line.strip():
                flush_paragraph()
                continue
        paragraph.append(line)
    flush_paragraph()

    return ExtractedDocument(source_id=source_id, media_type="text/markdown",
                             backend="markdown-atx", backend_version="1", page_count=0,
                             blocks=blocks, outline=outline)
