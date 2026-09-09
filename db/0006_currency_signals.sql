-- 0006_currency_signals.sql — what the D37 standing jobs need in order to say
-- anything at all.
--
-- 0001 put 'link-checker' and 'edition-check' in `sourcing_queue.kind`'s CHECK but left
-- `reason` listing only the five *pending-source* reasons ('not-ingested' ...
-- 'acquisition-failed'), none of which describes a dead URL or a moved edition. So the
-- two jobs the queue was widened for could not file a single row. The five reasons added
-- below are the complete outcome vocabulary of §4.4's two checks, plus the one act a
-- developer performs by hand ('edition-superseded', filed by `langatlas-sources
-- supersede` so the re-verification trigger has a carrier until D25's own queue exists).
--
-- The two tables are the *previous observation* each check compares against — content
-- drift is not a property of one fetch, and "is this source due" is not a property of
-- the calendar alone (§4.2's flat shorter interval for non-formal-spec grounding). They
-- are private/derived in D1's sense: dropping them costs one no-op check cycle, never a
-- fact.
ALTER TABLE sourcing_queue DROP CONSTRAINT IF EXISTS sourcing_queue_reason_check;
ALTER TABLE sourcing_queue ADD CONSTRAINT sourcing_queue_reason_check CHECK (reason IN
    ('not-ingested', 'partially-ingested', 'paywalled', 'access-pending',
     'acquisition-failed',
     'link-dead', 'anchor-missing', 'content-drift',
     'edition-mismatch', 'edition-superseded'));

-- One row per source, replaced on every check: this is a *state*, like the queue itself,
-- not a history. A trend over time would be a different table with a different key, and
-- nothing in §4.4 asks for one.
CREATE TABLE IF NOT EXISTS source_link_checks (
    source_id      text PRIMARY KEY,
    url            text NOT NULL,
    checked_at     timestamptz NOT NULL DEFAULT now(),
    resolves       boolean NOT NULL,
    http_status    int,
    anchor         text,               -- NULL when the URL carries no fragment
    anchor_present boolean,            -- NULL means "not applicable", never "missing"
    content_hash   text,               -- NULL when the fetch failed
    drifted        boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS source_edition_checks (
    source_id  text PRIMARY KEY,
    checked_at timestamptz NOT NULL DEFAULT now(),
    edition    text NOT NULL,          -- the record's `custom.edition` at check time
    matched    boolean NOT NULL,
    detail     text NOT NULL DEFAULT ''
);
