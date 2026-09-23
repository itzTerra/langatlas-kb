import pytest
from langatlas_ingest.backends.markdown import extract_markdown
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.errors import ExtractionFailed
from langatlas_ingest.extract import extract_document

MD = """# Structured concurrency

* Proposal: SE-0304
* Status: **Implemented**

## Motivation

An asynchronous function that spawns child tasks needs a way to wait for them.

### Detached tasks

A detached task carries no parent, so cancellation does not propagate to it.
"""


def test_atx_headings_become_the_outline(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text(MD)
    doc = extract_markdown(path, source_id="se-0304")
    assert doc.outline == ["Structured concurrency", "Motivation", "Detached tasks"]


def test_heading_levels_follow_the_number_of_hashes(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text(MD)
    doc = extract_markdown(path, source_id="se-0304")
    levels = {b.text: b.heading_level for b in doc.blocks if b.heading_level}
    assert levels == {"Structured concurrency": 1, "Motivation": 2, "Detached tasks": 3}


def test_content_before_the_first_heading_stays_a_plain_block(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("Front matter line.\n\n# Title\n\nBody.\n")
    doc = extract_markdown(path, source_id="x")
    assert doc.blocks[0].text == "Front matter line." and doc.blocks[0].heading_level == 0


def test_anchors_follow_githubs_slug_rule(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("# Detached Tasks!\n\nbody\n")
    doc = extract_markdown(path, source_id="x")
    heading = next(b for b in doc.blocks if b.heading_level)
    assert heading.anchor == "detached-tasks"


def test_a_hash_inside_a_fenced_code_block_is_not_a_heading(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("# Real heading\n\n```python\n# not a heading\nx = 1\n```\n\nafter.\n")
    doc = extract_markdown(path, source_id="x")
    assert doc.outline == ["Real heading"]
    assert any("# not a heading" in b.text for b in doc.blocks)


def test_a_bare_hash_with_no_space_is_not_a_heading(tmp_path):
    """`#include`, `#!/usr/bin/env`-style lines are not ATX headings (CommonMark
    requires a space, or end-of-line, after the leading `#`s)."""
    path = tmp_path / "doc.md"
    path.write_text("#no-space-here\n\nbody.\n")
    doc = extract_markdown(path, source_id="x")
    assert doc.outline == []


def test_extract_document_dispatches_text_markdown_to_the_markdown_backend(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text(MD)
    doc = extract_document(path, source_id="se-0304", media_type="text/markdown",
                           config=IngestConfig.load())
    assert doc.outline == ["Structured concurrency", "Motivation", "Detached tasks"]
    assert doc.backend == "markdown-atx"


def test_a_headingless_markdown_file_still_extracts_as_plain_body(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("Just a paragraph, no headings at all.\n")
    doc = extract_document(path, source_id="x", media_type="text/markdown",
                           config=IngestConfig.load())
    assert doc.char_count > 0


def test_empty_markdown_still_raises(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("")
    with pytest.raises(ExtractionFailed, match="no text"):
        extract_document(path, source_id="x", media_type="text/markdown",
                         config=IngestConfig.load())
