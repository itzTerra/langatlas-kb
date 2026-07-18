# 02 — Source & Citation System

> Brainstorm output. Owner requirements (input brief §2.1, §2.3): every user-facing fact links to a
> source; sources have a structured identification format ("some kind of .bib, most
> universal/modern"); source records may live in a normal DB (not the vector DB) but surface in the
> user-facing app. Constraint: solo dev, PoC MVP, keep it simple.

## 1. Problem framing

Hermes makes falsifiable claims about programming languages ("Rust has affine types",
"call-by-need hurts predictability of performance") and the whole credibility model rests on
*"source code link for every bit of info on the site"* (Notion). That splits into four
sub-problems:

1. **Source records** — a structured bibliographic format for heterogeneous source types: academic
   papers (DOI), books (Van Roy & Haridi), language specs/reference manuals (ISO C++, Haskell
   Report), official docs pages, blog posts, GitHub repos/threads, and stats sites (TIOBE, PLDB).
   Web sources rot, so they need an archival/permalink strategy.
2. **Fact→source links** — a claim must point at a source *plus a locator* (page, section, URL
   fragment), support multiple sources per fact, and carry a quality tier (peer-reviewed spec vs
   random blog).
3. **Agent minting** — AI agents add sources while arguing (input brief §2.4). They must dedup
   against existing records and be verified to not hallucinate ("the source actually says the
   claimed thing").
4. **Rendering** — citations must look clean on the SEO site (brief §2.6: pretty, not cluttered)
   and be human-challengeable via GitHub (brief §2.5a leaning).

Note the interaction with topic 05/GitHub-files decision: if facts live as YAML files in a repo,
the source registry should be a file in the same repo too, so a PR can add a fact and its source
atomically.

## 2. Options with trade-offs

### Bibliographic format candidates

| Format | Pros | Cons |
|---|---|---|
| **CSL-JSON** | De-facto modern interchange standard; native to Zotero/citeproc; ~100 fields incl. software, webpage, dataset; renders any of 2,600+ CSL styles via citeproc-js/citation.js in the site build; JSON = trivially stored in Postgres jsonb or as files; agents emit JSON natively and it's schema-validatable | JSON is less pleasant for humans to hand-edit/PR-review than YAML; no built-in archival fields (needs `custom` extension) |
| **BibTeX / BibLaTeX** | Universally recognized by programmers; huge ecosystem | Legacy: weak entry types for web/software sources, brittle syntax, no schema validation, awkward to parse/generate programmatically; owner asked for "most modern" — this isn't it |
| **Hayagriva YAML** | Cleanest human-readable syntax; modern (Typst's native format, actively maintained through 2026); supports CSL styles; good `serial-number` map (doi, isbn, arxiv) and parent/child model (chapter-in-book, page-on-site) | Rust-first ecosystem — thin JS/Python tooling; smaller community; converting to CSL-JSON needed anyway for web rendering; betting on a younger standard |
| **RIS** | Ancient interchange support | Flat tag format, lossy, nothing modern about it; skip |
| **Wikidata-style (QIDs)** | Ultimate linked-data universality; PL entities already exist (Q2005 etc.) | Massive overkill for solo dev; you don't control the data; slow round-trips; better used as an *identifier field*, not the format |
| **schema.org (JSON-LD)** | Exactly what Google wants for SEO rich results | Designed for markup, not bibliography management; poor locator/citation-style support. Best used as a *render target* generated from CSL-JSON, not as the store |

**Verdict on universality/modernity in 2026:** CSL-JSON is the interchange hub — citation.js
converts BibTeX, DOIs, and Wikidata *into* CSL-JSON, and citeproc renders *from* it. Hayagriva is
the nicest to write but Typst-centric. BibTeX is the legacy format everyone converts away from.
(Sources: [citation.js](https://citation.js.org/),
[twineconvert CSL-JSON guide](https://twineconvert.com/formats/csl-json),
[typst/hayagriva](https://github.com/typst/hayagriva),
[Hayagriva file format](https://github.com/typst/hayagriva/blob/main/docs/file-format.md).)

### Storage/authoring shape

- **(a) CSL-JSON as canonical, stored as YAML on disk** — write records in YAML 1.2 (superset of
  JSON semantics) using CSL-JSON field names; trivially load-and-pass to citeproc. Human-friendly
  diffs, machine-standard fields. Cheap best-of-both.
- **(b) Pure CSL-JSON files** — one `sources.json` or one file per source. Slightly worse PR
  review ergonomics; zero conversion.
- **(c) Hayagriva YAML canonical, convert to CSL-JSON at build** — prettiest authoring, but adds a
  Rust dependency or a hand-written converter to the pipeline. Not worth it unless the site is
  built with Typst tooling (it won't be).

### Fact→source link shape

- **Inline in fact files** — each fact carries a `sources:` list of `{id, locator, quote}`.
  Simple, atomic PRs, no join table. Fits the GitHub-files direction.
- **Separate claims table/graph edges** — normalized `fact_id ↔ source_id` with metadata.
  Cleaner queries, but a second moving part; can be *derived* from the files at build/ingest time
  rather than authored.

### Quality tiers

Keep a tiny fixed enum rather than numeric confidence scores (scores invite false precision):

- `A` peer-reviewed publication / official language specification or standard
- `B` official documentation, reference manual, textbook by recognized authors
- `C` talks, well-known community references (PLDB, Hyperpolyglot), maintainer blog posts
- `D` other blogs, forum posts, TIOBE-like popularity indexes (methodology-limited)

Tier lives on the **source record** (intrinsic quality) — a fact's displayed confidence is the max
tier among its citations. Facts citing only C/D sources get flagged as "needs stronger source" in
CI, which doubles as an agent work queue.

### Web-source rot

- **Wayback Machine on mint** — call the SavePageNow API when a URL source is added; store the
  resulting `archive_url` + `accessed` date on the record. Free, scriptable, standard.
- Prefer **version-pinned permalinks** where they exist: GitHub blob links at a commit SHA, docs
  URLs with version segments (`docs.python.org/3.12/...`), spec revision numbers, DOIs (already
  permanent). A CI link-checker (weekly cron, `lychee` or similar) flags dead links; the archive
  URL is the fallback shown to users.

### Agent minting safety

- **Dedup:** on mint, match by strong identifier first (DOI / ISBN / normalized URL — strip
  tracking params, trailing slash, `www.`), then fuzzy title+author+year match against the
  registry; agent must reuse an existing ID on a hit. IDs are human-readable slugs
  (`vanroy-haridi-2003`), so collisions are also visible in review.
- **Verification ("does the source say that?"):** require a short verbatim `quote` in every
  citation. Verification then becomes mechanical: fetch the source (or the page range of the PDF),
  check the quote appears (fuzzy match for OCR/formatting noise). A cheap CI script or a dedicated
  verifier agent with *only* the source text in context — never the same agent that authored the
  fact. Unverifiable citations fail CI and go to a human-review queue. This one rule kills most
  hallucinated-citation risk and is what makes facts "easily challengeable": the challenger sees
  exactly which sentence the claim rests on.
- Registry file changes are always PRs (even agent-made ones), so the human owner remains the
  final gate for new sources during MVP.

### Rendering on the SEO site

- **Numbered superscripts** `[1]` per page, popover/tooltip on hover with formatted reference +
  quote + tier badge, full "Sources" list at page bottom. Wikipedia-familiar, visually quiet —
  fits the "clean, not Amazon" mandate.
- Render formatted entries at **build time** with citeproc-js/citation.js from CSL-JSON (one
  style, e.g. APA or IEEE — satisfies the brief's "unified citation style").
- Emit **schema.org JSON-LD** (`ScholarlyArticle`/`Book`/`WebPage` in `citation` of the page's
  `Article`) generated from the same CSL-JSON — free SEO signal.
- Each rendered citation links: primary URL, archive link, and "challenge this" → GitHub
  discussion/edit link (Notion's contribution requirement).

## 3. Recommendation

**Canonical format: CSL-JSON field vocabulary, authored as YAML files in the repo** (option a).
One registry directory `sources/` (one file per source or sharded by first letter), converted 1:1
to CSL-JSON at build/ingest for citeproc rendering and DB loading. Hermes-specific metadata
(tier, archive URL, accessed date) goes under CSL-JSON's sanctioned `custom` key so records stay
valid CSL-JSON. Human-readable slug IDs. Wayback-archive every web source on mint. Verbatim-quote
requirement on every citation, verified by a separate check. Fixed A–D tier enum. Build-time
citeproc rendering + schema.org JSON-LD on the site.

### Example source record (`sources/vanroy-haridi-2003.yaml`)

```yaml
id: vanroy-haridi-2003
type: book                       # CSL-JSON type
title: "Concepts, Techniques, and Models of Computer Programming"
author:
  - { family: Van Roy, given: Peter }
  - { family: Haridi, given: Seif }
issued: { date-parts: [[2003]] }
publisher: MIT Press
ISBN: "978-0-262-22069-9"
URL: https://webperso.info.ucl.ac.be/~pvr/VanRoyHaridi2003-book.pdf
custom:
  tier: B                        # A spec/peer-reviewed, B docs/textbook, C community, D blog/stats
  archive_url: https://web.archive.org/web/2026/https://webperso.info.ucl.ac.be/~pvr/VanRoyHaridi2003-book.pdf
  accessed: 2026-07-17
  added_by: agent:oz-expert      # provenance of the mint
```

A docs-page example differs only in `type: webpage`, `container-title: Rust Reference`, a
version-pinned URL, and `custom.tier: B`.

### Example fact with citation (inside a fact/feature-instance file)

```yaml
fact: rust-memory-management-ownership
subject: lang:rust
predicate: implements
object: feature:ownership-memory-management
sources:
  - source: rust-reference-1.79-ownership     # id in sources/
    locator: "§10.2 Ownership"                # page/section/anchor
    quote: "When a variable goes out of scope, the value is dropped."
  - source: klabnik-nichols-2023-trpl
    locator: "ch. 4"
    quote: "Ownership is Rust's most unique feature."
confidence: B    # derived (max tier of cited sources); stored for display, recomputed in CI
```

Why this wins: CSL-JSON is the most universal *and* modern choice (everything converts into it,
citeproc renders out of it, schema.org falls out of it), YAML authoring keeps GitHub-based human
challenge pleasant, and the whole pipeline is ~three small scripts (yaml→csl-json converter,
quote verifier, link checker) — solo-dev sized.

## 4. Open questions for the owner

1. **Citation style for the site** — IEEE-style numeric `[1]` (compact, technical) or APA-ish
   author-year? (Numeric recommended for visual quietness.)
2. **Quote requirement strictness** — mandatory verbatim quote for *every* citation, or waived
   for self-evident sources (e.g. citing a repo as existence proof of an implementation)?
3. **Granularity of the fact unit** — is one YAML "fact" a single triple (as sketched above) or a
   whole feature-instance record with per-field citations? Affects file layout more than the
   citation schema.
4. **TIOBE/stats licensing** — TIOBE's terms restrict republication of their index; is linking +
   tier-D citation enough, or do we avoid reproducing their numbers entirely?
5. **PDF page-anchoring** — for the two core PDFs (Van Roy & Haridi, Jordan et al.), is
   `locator: "p. 493"` enough, or do you want self-hosted excerpts? (Copyright says: locator +
   short quote only.)
6. **Who can mint tier A/B sources without review** — during MVP everything is PR-gated; is that
   acceptable long-term or should trusted agents auto-merge C/D-supported facts?

## 5. New brainstorm topics surfaced

- **Quote-verification pipeline design** — fetching paywalled/PDF sources, fuzzy matching, and
  the verifier-agent-vs-CI-script split deserves its own small design note (overlaps agent-workflow
  topic).
- **Legal/licensing audit of quoted excerpts** — fair-use limits for quotes from books/specs and
  TIOBE-style data reuse.
- **Locator conventions per source type** — a tiny controlled vocabulary (`p.`, `§`, `ch.`,
  URL `#fragment`, commit SHA + line range for repos) so agents emit consistent locators.
- **Source registry ↔ vector DB sync** — chunks in the RAG store should carry `source_id` +
  locator metadata so agent answers cite the same registry as the site (ties into topic on RAG
  architecture).
- **Fact challenge lifecycle** — statuses like `disputed`/`superseded` on facts and how a GitHub
  discussion resolution flows back into the YAML.
