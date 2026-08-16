# tools/ingest/src/langatlas_ingest/index.py
from langatlas_ingest.locators import parse_locator

_SELECT = "SELECT chunk_id FROM source_chunks WHERE source_id = %s AND "
_ORDER = " ORDER BY ordinal"


def _heading_clause(heading: str) -> tuple[str, tuple]:
    """The `section_path` containment clause, shared by `named-section` and the
    heading-qualified half of `design-doc`.

    `regexp_replace(..., '\\s+', ' ', 'g')` mirrors `locators.canonical_text`'s whitespace
    collapse, which `heading` has already had applied to it. Belt and braces: extraction
    now canonicalizes heading text before it ever becomes a `section_path` entry, but 975
    of the real corpus's 1263 chunks were ingested before that fix and still carry runs
    like "11.8 Partial   failure". Without the collapse here, *neither* spelling of the
    citation resolved against them — a false negative in the join the D24 verifier trusts,
    which makes a true fact look unverifiable."""
    return ("EXISTS (SELECT 1 FROM unnest(section_path) part"
            r" WHERE lower(btrim(regexp_replace(part, '\s+', ' ', 'g'))) = %s)",
            (heading,))


class PostgresSourceChunksIndex:
    """The concrete `SourceChunksIndex` 1A's `validate_locator` takes by injection, and
    the same table the D24 verifier reads (D15: one index, two consumers).

    Section 4.3's join is *overlap*, not string equality — a citation to `p. 11` is backed
    by a chunk covering pages 10-12, and a citation to a whole section is backed by any
    chunk inside it. The overlap rules live in `locators.ranges_overlap` for the in-memory
    case; here the same rules are expressed as SQL against the indexed columns, so a
    resolution never scans chunk text. `test_sql_resolution_agrees_with_ranges_overlap`
    pins the two expressions of the rule together so they cannot drift apart.

    THREE differences from `ranges_overlap`. The first two are deliberate and widen what
    resolves; the third is a gap that lets *too much* resolve, and the D24 verifier trusts
    this join completely — a false positive here attaches a fact to a passage that does not
    support it. `test_sql_resolution_agrees_with_ranges_overlap` pins the kinds that agree,
    and `test_repo_file_commit_is_ignored_and_diverges_from_ranges_overlap` pins the
    remaining gap, so none of this is invisible.

    Deliberate (this side has the chunk's *columns*, not only its display locator):

    1. The comparable span comes from `page_start`/`page_end` (and `line_start`/`line_end`),
       not from parsing `locator` — a chunk labelled `p. 10` may genuinely cover pages
       10-12, and `ranges_overlap` reading its locator alone would miss that.
    2. `locator_kind` is not required to match the citation's kind. A chunk of a PDF
       carries pages whatever locator kind it prefers to display, and refusing to back
       `p. 11` with it would be a false negative — the failure mode that makes a true
       fact look unverifiable. `named-section` also resolves through `section_path`
       containment, a relation `ranges_overlap` cannot express at all.

    Remaining known gap (resolves MORE than `ranges_overlap` would, in the false-positive
    direction):

    3. `repo-file` ignores the `commit`: it matches on `anchor` (the path) and line
       overlap alone, so the same path at a different commit resolves, and line numbers
       move between commits. `source_chunks` has no `commit` column, and adding one now
       would be a column nothing could ever fill: no extraction backend in this package
       produces `line_start`/`line_end` on a `Chunk`, and this branch requires
       `line_start IS NOT NULL`, so it cannot match a real row at all today. That makes
       the gap currently *unreachable* rather than currently dangerous — but it is still
       a live design debt to close before any git-repo ingestion backend ships, because
       the backend that populates the lines is exactly the one that makes this matchable.

    Closed (db/0005_locator_identity_columns.sql added `doc_kind`, `doc_number`, `path`):

    - `design-doc` compares the cited document's identity. It used to share its clause
      with `named-section` and check heading text alone, so `RFC 1` and `PEP 484` each
      compiled to `TRUE` and resolved to *every* chunk of the cited source even when that
      source was PEP 8, and `RFC 2119 §Indentation` compiled to the same `section_path`
      clause as `PEP 8 §Indentation` and resolved against a PEP 8 chunk — a citation that
      looked precise and was not.
    - `multipage-docs` compares `path` as well as `anchor`. It used to share its clause
      with `web-fragment`, so two different pages sharing a fragment id resolved to each
      other.

    The storage exists; no current backend fills it. `chunker._locator_for` only ever
    emits `numbered-section`, `web-fragment`, `book-page` and `named-section`, so
    `doc_kind`/`doc_number`/`path` are NULL on every chunk in the corpus, and `column = %s`
    is false against NULL. Both kinds therefore resolve to NOTHING against today's corpus.
    That is the correct outcome, not a regression: a citation naming a document the index
    cannot prove a chunk belongs to must fail to resolve (the claim then parks in the
    sourcing queue, visibly) rather than attach a fact to an unrelated passage. The
    comparison itself is pinned by tests that hand-build a chunk with the columns
    populated, so it is genuinely correct and not merely always-empty."""

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
        if parsed.kind == "named-section":
            return _heading_clause(parsed.heading)
        if parsed.kind == "design-doc":
            # The document's own identity, which this branch used to ignore entirely
            # because it shared its clause with `named-section` and no column carried it.
            # `doc_kind = %s` is false when the column is NULL — which is every chunk any
            # current backend produces — so a design-doc citation now resolves to nothing
            # rather than to whatever chunk happened to share a heading. Deliberately not
            # `doc_kind IS NULL OR doc_kind = %s`: that is the gap, written out.
            identity = "doc_kind = %s AND doc_number = %s"
            params = (parsed.doc_kind, parsed.doc_number)
            if parsed.heading is None:
                # A whole-document citation is backed by any section *of that document* —
                # `TRUE` before, which resolved `PEP 484` to every chunk of a PEP 8 source.
                return (identity, params)
            clause, heading_params = _heading_clause(parsed.heading)
            return (f"{identity} AND {clause}", params + heading_params)
        if parsed.kind == "web-fragment":
            return ("anchor = %s", (parsed.anchor,))
        if parsed.kind == "multipage-docs":
            # Same fix, same reason: `anchor = %s` alone matched any chunk sharing the
            # fragment id whatever page it sat on. `path` is NULL on every current chunk,
            # so these citations resolve to nothing until a backend populates it.
            return ("path = %s AND anchor = %s", (parsed.path, parsed.anchor))
        if parsed.kind == "repo-file":
            start, end = parsed.lines
            return ("anchor = %s AND line_start IS NOT NULL AND line_start <= %s"
                    " AND COALESCE(line_end, line_start) >= %s",
                    (parsed.path, end, start))
        # `video` has no ingestion backend in 1C (no transcript extractor), so a video
        # citation resolves to nothing and the claim parks in the sourcing queue — which
        # is the correct visible outcome, not a silent pass.
        return None
