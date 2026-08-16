-- 0005_locator_identity_columns.sql — the columns that let a `design-doc` or
-- `multipage-docs` citation check *which document* it is citing, closing two
-- false-positive gaps in `index.PostgresSourceChunksIndex` (docstring gaps 3 and 4).
--
-- Both kinds share their SQL branch with a kind the chunker genuinely emits
-- (`named-section`, `web-fragment`), and neither had a column carrying the cited
-- document's own identity. So `RFC 2119 §Indentation` compiled to the same
-- `section_path` clause as `PEP 8 §Indentation` and resolved against a PEP 8 chunk, and
-- a `path#anchor` citation matched any chunk sharing the anchor whatever page it was on.
-- The D24 verifier trusts this join completely, so a false positive here attaches a fact
-- to a passage that does not support it.
--
-- Nullable with no default, unlike 0004's currency columns: there is no "was this row
-- processed before or after" question to backfill. NULL always correctly means "this
-- chunk carries no such identity", which is true of every existing row and of every
-- future one until a backend that produces design-doc/multipage-docs locators exists —
-- `chunker._locator_for` only ever emits numbered-section, web-fragment, book-page and
-- named-section. `column = %s` is false against NULL, so until then these citations
-- resolve to nothing, which is the correct, safe outcome rather than the over-matching
-- they got before.
--
-- `doc_number` is `int`, not `text` like `section_number`. `section_number` is text
-- because it is dotted ("13.2.1") and joins by component-prefix LIKE; a design-doc
-- number is a plain integer in the §4.3 grammar, `locators.parse_locator` already
-- returns it as an `int`, and `ranges_overlap` compares it as one — so an int column
-- keeps the SQL join and the in-memory join comparing the same values, and makes
-- "RFC 007" vs "RFC 7" impossible to get wrong. `doc_kind` stores the canonical
-- lowercase form `parse_locator` produces ("rfc", "pep"), so both sides of the join
-- agree without a case-folding wrapper that only one of them would apply.
ALTER TABLE source_chunks
    ADD COLUMN IF NOT EXISTS doc_kind   text,
    ADD COLUMN IF NOT EXISTS doc_number int,
    ADD COLUMN IF NOT EXISTS path       text;
