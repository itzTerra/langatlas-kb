-- 0004_ingestion_currency.sql — the rest of what decides whether a recorded ingestion is
-- still current. `source_ingestions` already carried the content hash, the extraction
-- backend and its version, and the locator kinds (0003); it did not carry the chunking
-- knobs (`config/ingest.yaml`: target/max/overlap tokens) or any marker for the
-- chunker/QA code itself. So tuning chunk size and re-running a source silently no-opped:
-- `ingest_source` saw every recorded input match, skipped the run, and left the old
-- chunks in place with no error and no warning.
--
-- One jsonb column rather than four scalars: it is a single opaque comparand that
-- `chunker.chunking_fingerprint` owns end to end, so a future knob or a version bump is
-- a change in one Python function instead of another migration plus another column list.
-- The `'{}'` default follows 0003's locator_kinds: a row written before this migration
-- has an empty fingerprint, which can never equal a real one (always version + three
-- knobs), so pre-existing rows read as "unknown, therefore not current" and re-ingest
-- once — never as "matches by default", which would pin the corpus to stale chunks.
ALTER TABLE source_ingestions
    ADD COLUMN IF NOT EXISTS chunking jsonb NOT NULL DEFAULT '{}'::jsonb;
