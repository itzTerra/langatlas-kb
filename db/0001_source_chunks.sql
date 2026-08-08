-- 0001_source_chunks.sql — D15's second table plus its ingestion bookkeeping.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS source_chunks (
    chunk_id          text PRIMARY KEY,          -- "<source_id>#c00042"
    source_id         text NOT NULL,
    ordinal           int  NOT NULL,
    parent_section_id text,                      -- D15 small-to-big expansion
    section_path      text[] NOT NULL DEFAULT '{}',
    breadcrumb        text NOT NULL,             -- prefixed into the embedded text
    locator           text NOT NULL,             -- §4.3 grammar, machine-produced
    locator_kind      text NOT NULL,
    page_start        int,
    page_end          int,
    section_number    text,                      -- "13.2.1" for §-overlap joins
    anchor            text,                      -- url fragment / repo path
    line_start        int,
    line_end          int,
    text              text NOT NULL,
    token_count       int  NOT NULL,
    content_hash      text NOT NULL,
    ingested_at       timestamptz NOT NULL DEFAULT now(),
    tsv               tsvector GENERATED ALWAYS AS
                          (to_tsvector('english', text)) STORED,
    UNIQUE (source_id, ordinal)
);

-- One row per source per ingestion run: what backend produced it, what the QA harness
-- said, and whether it was promoted. A source that fails the D37 hard gate is recorded
-- with promoted = false and has no rows in source_chunks.
CREATE TABLE IF NOT EXISTS source_ingestions (
    source_id       text PRIMARY KEY,
    content_hash    text NOT NULL,
    backend         text NOT NULL,
    backend_version text NOT NULL,
    chunk_count     int  NOT NULL,
    qa_status       text NOT NULL CHECK (qa_status IN ('pass', 'warn', 'fail')),
    qa_report       jsonb NOT NULL,
    promoted        boolean NOT NULL,
    ingested_at     timestamptz NOT NULL DEFAULT now()
);

-- D37/D41: one private queue with a kind discriminator. bounce_count rides D24's
-- 2-bounce budget; age_days is derived from opened_at by the reporting side.
CREATE TABLE IF NOT EXISTS sourcing_queue (
    id           bigserial PRIMARY KEY,
    kind         text NOT NULL CHECK (kind IN
                     ('pending-source', 'link-checker', 'edition-check')),
    source_id    text NOT NULL,
    reason       text NOT NULL CHECK (reason IN
                     ('not-ingested', 'partially-ingested', 'paywalled',
                      'access-pending', 'acquisition-failed')),
    detail       text NOT NULL DEFAULT '',
    bounce_count int NOT NULL DEFAULT 0,
    opened_at    timestamptz NOT NULL DEFAULT now(),
    resolved_at  timestamptz
);
