# langatlas-ingest

D15's ingestion pipeline and the pipeline-only retrieval tools.

```
snapshot store -> extract -> chunk -> QA gate -> source_chunks -> embed -> search
```

## Quick start

```bash
docker compose up -d db          # from the repo root
cd tools/ingest && uv sync --extra dev
uv run langatlas-sources db      # apply db/*.sql
uv run langatlas-sources ingest vanroy-haridi-2003 --file /path/to/book.pdf \
    --media-type application/pdf --locator-kinds book-page
uv run langatlas-sources ingest some-web-spec --url https://example.org/spec  # fetch + archive first
uv run langatlas-sources qa vanroy-haridi-2003
uv run langatlas-sources embed vanroy-haridi-2003
uv run langatlas-sources search "call-by-need memoization"
uv run langatlas-sources eval             # score tests/golden/retrieval/*.yaml (D22/§8.6)
uv run langatlas-sources queue            # list open sourcing-queue entries
uv run langatlas-sources reingest         # re-ingest every stored snapshot (D1)
```

`--locator-kinds` is stored on the snapshot and reused by every later run for that
source, so a re-ingest reproduces the locators already published rather than silently
falling back to a different preference order. Pass it again to change it. `--min-chars`
works the same way: it is the extraction-collapse floor the QA hard gate applies to this
one source, for a legitimately tiny standalone source (a one-page errata note, a short
RFC) that fails the default floor on its honest length. Omitting it reuses the stored
value, or QA's own default — never zero. A re-ingest whose content hash, backend version,
locator kinds, and chunking config/version/floor all match the recorded run is skipped:
rewriting the chunks would cascade away every embedding for that source and cost a full
re-embed on the paid provider to reach byte-identical rows.

## Where things live

Nothing this package extracts is ever committed (D13/D15). The private tier is
`$LANGATLAS_PRIVATE_DIR` (default `~/.local/share/langatlas`), shared with 1B's call
cache and cost log so one tarball backs up the whole private side:

```
snapshots/<source_id>/original/…        the acquired PDF/HTML, byte-for-byte
snapshots/<source_id>/snapshot.yaml     content hash, retrieval date, archive_url,
                                        locator_kinds, min_chars
snapshots/<source_id>/extracted/…       extracted blocks (JSON)
snapshots/<source_id>/qa/report.{md,json}
```

Postgres holds `source_chunks`, `source_ingestions`, `sourcing_queue`, and one
`source_chunk_emb_<model>` table per embedding model. `source_chunks` and the other
tables are regenerable for free: drop the database, `langatlas-sources db`, re-ingest
from the snapshot store. The `source_chunk_emb_<model>` tables are not — dropping them
means a fresh `langatlas-sources embed` run, a paid provider round-trip over the whole
corpus, not something the snapshot store alone reproduces.

## Extraction backends

`pymupdf` (default) or `docling` (`uv sync --extra docling`, then
`extraction.pdf_backend: docling` in `config/ingest.yaml`). The QA report is what tells
you a source needs the heavier backend — read it before switching.

## Tests

```bash
uv run pytest                    # offline unit tests
uv run pytest -m db              # needs `docker compose up -d db`
```

## Not public

`search_sources` and `get_source_section` are pipeline-only (Section 9/D60): every return
is raw pre-verification source text. Stage 6's public MCP server exposes a different seven
tools and must never list these.
