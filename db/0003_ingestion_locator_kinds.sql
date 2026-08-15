-- 0003_ingestion_locator_kinds.sql — D1: the database is a derived artifact, so every
-- input that determines its contents has to be recorded beside the run that used it.
-- `locator_kinds` (the source record's `custom.locator_kinds`, §4.1) picks which locator
-- each chunk emits — the public citation surface — and lived only in an ad-hoc CLI flag.
-- Stored here it is also what lets `ingest_source` tell a genuinely unchanged re-ingest
-- (skippable: the chunks and their paid embeddings are already correct) from one whose
-- locator preference changed (must re-run).
ALTER TABLE source_ingestions
    ADD COLUMN IF NOT EXISTS locator_kinds text[] NOT NULL DEFAULT '{}';
