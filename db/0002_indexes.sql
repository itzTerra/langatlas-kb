-- 0002_indexes.sql — the FTS half of D15's hybrid retrieval, plus the filter-first paths.
CREATE INDEX IF NOT EXISTS source_chunks_tsv_idx     ON source_chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS source_chunks_source_idx  ON source_chunks (source_id, ordinal);
CREATE INDEX IF NOT EXISTS source_chunks_parent_idx  ON source_chunks (parent_section_id);
CREATE INDEX IF NOT EXISTS source_chunks_section_idx ON source_chunks (source_id, section_number);
CREATE INDEX IF NOT EXISTS source_chunks_pages_idx   ON source_chunks (source_id, page_start, page_end);
CREATE INDEX IF NOT EXISTS source_chunks_path_idx    ON source_chunks USING gin (section_path);
CREATE INDEX IF NOT EXISTS sourcing_queue_open_idx   ON sourcing_queue (kind, source_id)
    WHERE resolved_at IS NULL;
