# tools/ingest/src/langatlas_ingest/index.py
from langatlas_ingest.locators import parse_locator

_SELECT = "SELECT chunk_id FROM source_chunks WHERE source_id = %s AND "
_ORDER = " ORDER BY ordinal"


class PostgresSourceChunksIndex:
    """The concrete `SourceChunksIndex` 1A's `validate_locator` takes by injection, and
    the same table the D24 verifier reads (D15: one index, two consumers).

    Section 4.3's join is *overlap*, not string equality — a citation to `p. 11` is backed
    by a chunk covering pages 10-12, and a citation to a whole section is backed by any
    chunk inside it. The overlap rules live in `locators.ranges_overlap` for the in-memory
    case; here the same rules are expressed as SQL against the indexed columns, so a
    resolution never scans chunk text. `test_sql_resolution_agrees_with_ranges_overlap`
    pins the two expressions of the rule together so they cannot drift apart.

    FOUR differences from `ranges_overlap`. The first two are deliberate and widen what
    resolves; the last two are gaps that let *too much* resolve, and the D24 verifier
    trusts this join completely — a false positive here attaches a fact to a passage that
    does not support it. `test_sql_resolution_agrees_with_ranges_overlap` pins the kinds
    that agree, and the `*_diverges_from_ranges_overlap` tests pin each gap below, so none
    of this is invisible.

    Deliberate (this side has the chunk's *columns*, not only its display locator):

    1. The comparable span comes from `page_start`/`page_end` (and `line_start`/`line_end`),
       not from parsing `locator` — a chunk labelled `p. 10` may genuinely cover pages
       10-12, and `ranges_overlap` reading its locator alone would miss that.
    2. `locator_kind` is not required to match the citation's kind. A chunk of a PDF
       carries pages whatever locator kind it prefers to display, and refusing to back
       `p. 11` with it would be a false negative — the failure mode that makes a true
       fact look unverifiable. `named-section` also resolves through `section_path`
       containment, a relation `ranges_overlap` cannot express at all.

    Known gaps (these resolve MORE than `ranges_overlap` would, in the false-positive
    direction — fix before Stage 2 leans on these kinds):

    3. `design-doc` never compares `doc_kind`/`doc_number`, so the cited document's own
       identity is never checked. This is NOT limited to whole-document citations:
       - `RFC 1` and `PEP 484` each become `TRUE` and resolve to *every* chunk of the
         cited source, even when that source is PEP 8;
       - a heading-qualified citation is equally blind — `RFC 2119 §Indentation` and
         `PEP 8 §Indentation` compile to the *same* `section_path` clause, so the former
         resolves against a PEP 8 chunk. A section-qualified citation looks precise and
         is not.
       Scoping by `source_id` is the only thing containing this today.
    4. `repo-file` ignores the `commit`, and `multipage-docs` ignores the `path` — both
       match on `anchor` alone. Two files sharing a fragment id, or the same path at a
       different commit, resolve to each other. Line numbers move between commits, so
       the `repo-file` case can genuinely cite the wrong lines.

    None of gaps 3 and 4 is one SQL clause away. `source_chunks` stores no `doc_kind`,
    `doc_number`, `commit`, or `path` column — only the raw `locator` string, `anchor`,
    and `section_path` (see `db/0001_source_chunks.sql`). Closing any of the three
    therefore costs the same thing: either a schema change adding the missing columns
    (and a chunker change to populate them), or re-parsing the stored `locator` text at
    query time — and the latter is exactly the "stop comparing indexed columns" tension
    that justified expressing these rules in SQL in the first place. All three are
    carried forward as one Stage 2 developer decision, not as cheap follow-ups."""

    def __init__(self, conn):
        self.conn = conn

    def resolve(self, source_id: str, locator: str) -> list[str]:
        try:
            parsed = parse_locator(locator)
        except ValueError:
            return []       # shape errors are validate_locator_shape's to report, not ours
        query = self._query(parsed)
        if query is None:
            return []
        clause, params = query
        with self.conn.cursor() as cur:
            cur.execute(_SELECT + clause + _ORDER, (source_id, *params))
            return [row[0] for row in cur.fetchall()]

    def _query(self, parsed) -> tuple[str, tuple] | None:
        if parsed.kind == "book-page":
            start, end = parsed.pages
            # COALESCE, not a bare `page_end`: a single-page chunk that recorded only
            # `page_start` would otherwise compare NULL and drop out silently.
            return ("page_start IS NOT NULL AND page_start <= %s"
                    " AND COALESCE(page_end, page_start) >= %s", (end, start))
        if parsed.kind == "numbered-section":
            number = parsed.section_number
            # Either direction of containment: the citation may name an ancestor of the
            # chunk's section or one of its descendants. The trailing dot is what keeps
            # §13.2 from matching §13.20 — component containment, not string prefix.
            return ("(section_number = %s OR section_number LIKE %s"
                    " OR %s LIKE section_number || '.%%')",
                    (number, number + ".%", number))
        if parsed.kind in ("named-section", "design-doc"):
            if parsed.heading is None:
                return ("TRUE", ())      # a whole-document citation
            return ("EXISTS (SELECT 1 FROM unnest(section_path) part"
                    " WHERE lower(btrim(part)) = %s)", (parsed.heading,))
        if parsed.kind in ("web-fragment", "multipage-docs"):
            return ("anchor = %s", (parsed.anchor,))
        if parsed.kind == "repo-file":
            start, end = parsed.lines
            return ("anchor = %s AND line_start IS NOT NULL AND line_start <= %s"
                    " AND COALESCE(line_end, line_start) >= %s",
                    (parsed.path, end, start))
        # `video` has no ingestion backend in 1C (no transcript extractor), so a video
        # citation resolves to nothing and the claim parks in the sourcing queue — which
        # is the correct visible outcome, not a silent pass.
        return None
