# 26 — Dataset Bundle Contract Design

> Backlog brainstorm for LangAtlas. Topic: the exact shape of the "compiled, validated dataset
> bundle" that D13 already commits the KB repo's CI to publishing as GitHub Release assets on
> every green push to `main` — archive/file format, `schema_version` semantics and compatibility
> ranges, manifest fields, and how the three declared consumers (the Astro site build, a
> Postgres loader, and the read-only stdio MCP server) each read it. A distinct sub-problem
> flagged in the same checklist entry — the **MCP caution contract**, how the read-only MCP
> conveys confidence/controversy so a consuming agent can't treat every fact as equally settled
> — is designed concretely in §2.5. Binding context: `context/decisions.md` D1 (git-is-the-
> database, everything downstream is a one-way derived artifact), D7 (Postgres + pgvector/FTS
> from day one — **not** a SQLite serving phase, a distinction this brainstorm has to be careful
> about, see §2.1), D8 (MCP tools: `search_knowledge`, `get_fact`, `get_feature`,
> `get_neighbors`, `get_source`; MCP is read-only; a FastAPI adapter for non-MCP providers and
> site search), D13 (validated-artifact CI pattern, `latest-green`/`data-vN` release tags,
> rollback, embeddings cache stays private for now, site displays its `data-vN` build stamp),
> D15/brainstorm 21 (private `source_chunks` full-source index — explicitly **not** shipped in
> any public bundle), D16/D22 (ontology versioning: immutable node ids vs renameable slugs,
> blast-radius semver on `ontology/VERSION`, migrations-as-scripts, derived stores always
> rebuilt never migrated), D20/D23/brainstorm 09 (fact granularity: one record per feature
> instance with per-field `sources:`; facts are build artifacts derived from `(record, field)`
> paths; the concrete v0 YAML schemas, two-part anchor+`f-<hash>` fact identity, and directory
> layout this bundle compiles from), D24 (verifier verdict vocabulary, published error-rate
> honesty metric), D25/brainstorm 12 (three orthogonal status axes — verification/freshness/
> dispute — a derived display status, ordinal confidence, four-level controversy score),
> D26/brainstorm 13 (`RunContext` provider layer — the embedding calls the loader makes go
> through it), D31 (fetched-content-as-data-not-instructions pattern, generalized here to
> epistemic status). All proposals below are *proposed* until the developer ratifies.

## 1. Problem framing

D13 already settled *that* a bundle gets published and roughly *why* (the site never reads raw
KB files; agents never touch deploy credentials; red-main publishes nothing). It did not settle
*what is inside the box*. Three consumers with structurally different access patterns need to
agree on one artifact:

- **The Astro site build** wants page-shaped bulk reads — "every instance for language X,"
  "every edge touching feature Y" — and needs none of the private source-corpus material
  (D15), no raw embeddings, nothing beyond what a public page can legally and honestly render.
- **The Postgres loader** wants a bulk-insertable, table-shaped copy it can pour into the
  docker-compose Postgres (D7) that backs both the FastAPI adapter and the MCP server's
  semantic search, plus enough manifest information to decide whether it can reuse cached
  embeddings (D13's private cache) or must recompute them.
- **The read-only MCP server** wants point lookups (`get_fact`, `get_feature`, `get_source`)
  and hybrid lexical+semantic search (`search_knowledge`), and — per this topic's second
  half — must not hand a consuming agent a bare sentence with no indication that the claim is
  contested, unverified, or stale.

Four sub-problems, matching the task brief:

1. **Exact bundle format** — archive/container, file formats, directory/table layout.
2. **`schema_version` semantics** — what compatibility a consumer must check before trusting a
   bundle, and how this interacts with D22's ontology semver (a related but *not identical*
   axis — conflating the two is the main trap here, see §2.2).
3. **Manifest fields** — what a consumer needs to trust and validate the bundle without
   re-deriving anything.
4. **The D20 interaction** — per-field derived fact IDs are the unit three different consumers
   all need efficient access to; the bundle's internal shape either makes that efficient or
   forces every consumer to re-implement brainstorm 09's derivation logic.
5. **The MCP caution contract** — concrete response shaping, not just a schema field nobody
   reads.

Scale check (carried from brainstorm 09/25): low hundreds of features, ~15–25 languages in the
D28 curated set, tens of thousands of derived facts. This is comfortably desktop-scale — the
design below optimizes for correctness, simplicity, and "boring, solo-maintainable technology"
over anything web-scale.

## 2. Options with trade-offs

### 2.1 Archive format and file shapes

**Option A — JSONL files inside a tarball.** One `.jsonl` (or `.json`) file per entity type
(`features.jsonl`, `instances.jsonl`, `edges.jsonl`, `facts.jsonl`, …), wrapped in a single
`.tar.zst`, plus a sibling `manifest.json`.

- Pros: maximally boring and portable — any language can stream-parse JSONL with zero
  dependencies; naturally splits for bulk `COPY`-style Postgres ingestion (one file → one
  `COPY` statement); trivially diffable line-by-line if that ever matters.
- Cons: no built-in indexing, so both the site build and MCP point lookups need to build their
  own in-memory index (a `Map<fact_id, row>`) after loading — fine at this scale, but it's
  logic every consumer re-implements; no single-file integrity story (checksums have to cover N
  files, and a partial tar extraction is a subtler failure mode than "the file didn't open").

**Option B — Parquet files inside a tarball.** Same directory idea, columnar Parquet instead
of JSONL.

- Pros: better for large analytical bulk scans.
- Cons: solves a problem this project doesn't have (columnar scan performance) while
  introducing the one it does have (a less "boring" dependency — a Parquet reader is a heavier,
  less universally-available library than JSONL or SQLite, particularly on the Astro/Node side
  of the site build). **Rejected** — no access pattern here benefits from columnar storage over
  row storage at tens-of-thousands-of-rows scale, and D7 already put pgvector/FTS effort into
  Postgres, not a columnar analytics story.

**Option C (recommended) — A single SQLite file, zstd-compressed, alongside a small JSON
manifest, published as two release assets (no wrapping archive needed at all).**

`langatlas-data-vN.sqlite.zst` + `langatlas-data-vN.manifest.json`, both attached to the same
`data-vN` GitHub Release (D13 already established the tagging scheme; GitHub Releases natively
support multiple named assets per tag, so no custom archive container is needed — one fewer
format to invent).

- Pros: one self-contained, directly-queryable file. The site build issues plain SQL against
  it (joins handle page-shaped reads natively — no custom index-building step). The Postgres
  loader does straightforward `SELECT` → `COPY`/`INSERT` per table. The MCP server can point
  lookups by primary key (`get_fact`, `get_feature`) directly, and SQLite's FTS5 extension
  gives free lexical search — see §2.4 for why this matters for a documented MCP "lite mode."
  Built-in single-file integrity: one sha256 of the compressed file (checked before
  decompression) and one of the decompressed file (checked before opening) cover the whole
  payload, versus N per-file checksums for Option A. SQLite is about as boring as storage
  engines get — bundled into Python's stdlib, trivial in Node via `better-sqlite3`, a single
  static binary in most languages.
- Cons: binary, not line-diffable — but that is fine and expected: the bundle is a *derived*
  build artifact under D1, never the canonical store, so "diffable" is a property the YAML repo
  needs and the bundle does not. Requires a small build step (YAML → validated in-memory model
  → SQLite writer) instead of "just serialize the in-memory model" — modest, one-time
  tooling cost.

**A note on D7, to head off an apparent conflict:** D7 rejected a *SQLite serving phase* — i.e.
running the project's live, queried database on SQLite before "graduating" to Postgres. That is
a decision about which engine backs the *running services* (FastAPI adapter, MCP server,
site search). This option does not relitigate that: SQLite here is purely an **interchange file
format** for the release asset — the thing that gets downloaded once and then loaded *into* the
real Postgres (or read directly for the narrow MCP lite-mode case in §2.4, which is a
deliberately reduced-capability fallback, not the primary serving path). Nothing about D7
changes; the live services still run on Postgres.

**Recommendation:** Option C. It gives every consumer a directly queryable, indexable,
single-file artifact with the cheapest possible integrity story, at negligible file-size cost
(§2.6), without introducing a heavier dependency than the project already carries elsewhere.

### 2.2 `schema_version` semantics — one axis or three?

The task brief asks for "`schema_version` semantics/compat ranges" as if there's one number.
There should be **three**, because they change for different reasons and at different rates,
and collapsing them into one either makes the compatibility check too strict (a trivial
ontology MINOR bump forces a site rebuild-and-redeploy dance it doesn't actually need) or too
loose (a real breaking change to the bundle's table shape ships silently because the ontology
happened not to move that week).

1. **`data_tag`** — the specific publish, e.g. `data-v418`, exactly D13's existing immutable
   release tag. Identifies *which* snapshot, used for rollback. Not a compatibility signal at
   all.
2. **`ontology_version`** — D16/D22's blast-radius semver over the *content* schema (node ids,
   layer/dimension taxonomy, edge types). Rides along in the manifest purely as **provenance
   and the D25 freshness backstop** ("the coarse audit backstop" language from D25 is exactly
   this field) — not something consumers need a compatibility *range* for, because D22 already
   settled that "derived stores are always rebuilt, never migrated": every bundle publish
   already reflects facts computed fully against the ontology version it shipped with. There is
   no cross-ontology-version reconciliation a consumer ever has to do. This is also literally
   the number D13's already-ratified "site displays its `data-vN` build stamp" amendment refers
   to conceptually — this brainstorm just makes explicit that the stamp is really two numbers
   (`data_tag` for "which publish," `ontology_version` for "against which taxonomy version"),
   both worth showing.
3. **`bundle_schema_version`** (new, this brainstorm's actual contribution) — a semver over the
   bundle's own **structural** contract: SQLite table/column names, their types and meaning,
   and the manifest's own field set. This is the number that matters for compatibility, because
   it's the one that determines whether a given version of the site-build script, loader
   script, or MCP server code can correctly read a given bundle's *shape* at all — independent
   of what data is in it. MAJOR = a breaking structural change (table/column renamed or
   removed, a column's meaning changes, a previously-optional manifest field becomes load-
   bearing); MINOR = purely additive (new optional column, new table, new manifest field —
   old consumer code keeps working and simply ignores what it doesn't know about); PATCH =
   no structural change at all (e.g. a bug fix in what value a column gets populated with).
   This deliberately mirrors D22's blast-radius methodology one layer down, at the interchange-
   format level rather than the ontology-content level — the same "does this force downstream
   code changes" test, applied to schema-of-the-bundle instead of schema-of-the-knowledge.

Each consumer (site-build script, loader script, MCP server) pins a compiled-in compatibility
range for `bundle_schema_version` — e.g. `^1.2` (same MAJOR, MINOR at least 1.2) — as a small
constant in its own repo, not derived at runtime from anything clever. On load, it compares the
manifest's `bundle_schema_version` against its own pinned range:

- **Range satisfied:** proceed normally.
- **MAJOR mismatch (bundle is newer or older across a MAJOR boundary):** hard refuse to load,
  print a clear "this consumer needs bundle_schema_version ^2.0, got 1.4.0, upgrade the
  consumer" error, exit non-zero. No partial/degraded load. This matches D13's existing
  failure-closed posture ("red main publishes nothing") applied to the consumption side too —
  a version-incompatible bundle should behave like a bundle that failed to build, not like one
  that silently serves stale-shaped data.
- **MINOR/PATCH within range:** always fine by construction (additive changes never break a
  pinned range that only checks MAJOR + a MINOR floor).

This directly answers "old MCP server against a new bundle, or vice versa": the old server's
pinned range simply won't include the new bundle's MAJOR, so it refuses to start rather than
mis-querying tables that no longer mean what it thinks they mean. The failure is loud and
immediate (server won't boot), not silent (server boots, serves subtly wrong data).

### 2.3 The D20 interaction — what the bundle ships for facts specifically

D20/D23 settled that **records** (one YAML file per feature instance, edge, rule, …) are the
authoring unit, and **facts** — the per-field, independently challengeable, stably-IDed units —
are derived at build time. The open question here is what the *bundle* ships: raw records that
every consumer re-derives facts from, or the already-derived fact table.

**Option A — Ship only records; each consumer re-derives facts.** The bundle carries
`instances`, `edges`, `rules`, etc. tables shaped like the YAML records; anyone who wants
per-field facts (their IDs, rendered sentences, canonical claims, status) re-runs brainstorm
09's O6 template-and-hash logic.

- Pros: smaller bundle, one less table to maintain.
- Cons: reimplements brainstorm 09's derivation logic in (at least) three places — the site
  build, the Postgres loader, and, if the MCP lite mode (§2.4) exists, potentially a fourth. Any
  drift between implementations (a template edit, a normalization tweak) silently produces
  different fact IDs in different consumers, which is exactly the identity-integrity problem
  D16/D20/brainstorm-09 exist to prevent. **Rejected** — this reintroduces the "facts must be
  computed once, consistently" property the whole schema design was built around, for no
  benefit worth the risk.

**Option B (recommended) — Ship a single flat, precomputed `facts` table as a first-class part
of the bundle**, one row per derived fact:

```
facts(
  fact_id            TEXT PRIMARY KEY,   -- f-<12hex>
  anchor             TEXT,               -- record-id#field-path
  kind               TEXT,               -- instance-field | instance-exists | characteristic | ...
  record_id          TEXT,
  field_path         TEXT,
  canonical_claim     TEXT,
  rendered_text       TEXT,               -- the human sentence
  sources_json         TEXT,               -- [{source_id, locator, quote?}]
  provenance_json      TEXT,
  verification_result  TEXT,               -- verified | partial | unverified | failed
  confidence           TEXT,               -- high | medium | low   (D25)
  freshness            TEXT,               -- fresh | stale         (D25)
  dispute               TEXT,               -- none | contradicted | superseded  (D25)
  controversy_score      INTEGER,            -- 0-3                  (D25, merged 4→3)
  controversy_signals_json TEXT,
  display_status        TEXT               -- derived by D25's fixed precedence, precomputed
)
```

with `instances`, `edges`, `rules`, `sources`, `concepts`, `features`, `languages` tables
carrying the *record*-shaped data (for the site's page assembly, which genuinely wants the
whole record, not a bag of disconnected fact rows) plus `tombstones` and `redirects` tables
mirroring `tombstones.yaml`/`ontology/redirects.yaml` verbatim.

- Pros: this is the direct, concrete answer to "how do per-field fact IDs get referenced/looked
  up efficiently by three different consumers with different access patterns." The site's
  citation popover renders straight from a `facts` row by `fact_id` — no re-derivation, no risk
  of drifting from what the verifier actually verified. The Postgres loader bulk-inserts the
  table as-is (it's already the shape brainstorm 09 designed for embedding as the fact-RAG
  chunking unit — D7's "embed fact cards... with `{chunk_type, feature_id, language_id,
  source_id, status}` metadata" maps onto exactly these columns). MCP's `get_fact(fact_id)` is
  a primary-key lookup with **all D25 status axes already attached** — which is also the
  concrete mechanism that makes §2.5's caution contract cheap to implement: the caution block
  isn't computed per-request, it's a column read.
- Cons: the facts table is the single largest table in the bundle (tens of thousands of rows
  vs. low thousands for instances/edges) — acceptable at this scale (§2.6) and it is, after
  all, the actual point of the whole project (embeddable, provenance-carrying, independently
  challengeable claims), not overhead to be minimized.

**Recommendation:** Option B. The bundle's `facts` table *is* D20's derived-fact concept made
concrete and portable — computing it once, in the build pipeline, and shipping it as data
rather than logic, is what keeps three independently-maintained consumers from ever disagreeing
about what a fact's ID, status, or rendered text is.

### 2.4 How MCP actually reads the bundle

The task brief lists MCP as a direct bundle consumer alongside the site and the loader, but
D8's architecture has the MCP server querying **Postgres** (the retrieval core sits on top of
the same Postgres+pgvector the FastAPI adapter and site search use) — it does not parse the
release asset itself in the primary deployment. That needs to be stated plainly rather than
glossed over, because it changes what "MCP consumes the bundle" means in practice.

**Option A — MCP only ever queries Postgres; it never touches the bundle file directly.** The
Postgres loader is the only direct-bundle-reading path that feeds MCP; MCP's own compatibility
check is against whatever `bundle_schema_version`/`ontology_version` the loader stamped into a
`_meta` table in Postgres when it last loaded (mirroring the bundle manifest fields into the
live database), not against the release asset.

- Pros: simplest possible story — one direct-bundle-reader (the loader) instead of two; MCP
  code never needs a SQLite driver at all; matches D8's existing architecture exactly, no new
  moving parts.
- Cons: anyone who wants to run the MCP server without standing up the full docker-compose
  Postgres stack (a real accessibility concern for D8's "other/local providers" audience, and
  for external contributors who just want to point Claude Code at LangAtlas without running
  infrastructure) has no path to do so.

**Option B (recommended) — Option A as the primary path, plus a documented, explicitly reduced-
capability "lite mode" where the MCP server can be pointed directly at a decompressed bundle
`.sqlite` file with no Postgres at all.** In lite mode: `get_fact`, `get_feature`,
`get_source`, `get_neighbors` work identically (they're primary-key/foreign-key lookups,
trivial in SQLite); `search_knowledge` falls back to the bundle's SQLite FTS5 index over
`facts.rendered_text`/`anchor` — lexical only, no pgvector semantic ranking — and **every
response in this mode carries an explicit `"retrieval_mode": "lexical-fallback"` field** so a
consuming agent (or its operator) can tell retrieval quality is reduced, rather than silently
serving worse results under the same contract as the full deployment.

- Pros: gives the "read-only MCP server... for Claude Code and other/local providers" (D8) a
  genuine zero-infrastructure on-ramp — download two files, point the server at the `.sqlite`,
  done. Directly serves the project's stated agent-facing-RAG surface without forcing every
  consumer through Docker. Costs nothing in the primary path (Option A's architecture is
  unchanged; this is strictly additive).
  self-labeling (`retrieval_mode`) means the reduced-capability mode never masquerades as
  full-quality search.
- Cons: a second code path to keep in sync with the primary Postgres-backed query logic
  (mitigated by both paths reading the *same* table shapes, since the bundle and Postgres load
  from the same schema by construction — see §2.3). Needs its own small test suite. Worth
  flagging as its own follow-up design pass rather than fully speccing here (§5).

**Recommendation:** Option B. The primary MCP deployment stays exactly as D8 designed it
(Postgres-backed, full hybrid search); the lite mode is a clearly-labeled, additive
accessibility feature that costs the primary path nothing and directly serves the "other/local
providers" half of D8's stated audience.

### 2.5 The MCP caution contract

This is the sub-problem the checklist entry calls out by name: how does the read-only MCP
convey confidence/controversy/dispute status (D25) to a consuming agent in a way that can't
just be ignored? Three failure modes to design against: (a) the agent never requests a status
field that exists but is optional; (b) the agent requests it but treats a "disputed" badge as
just more metadata to skip past in a JSON blob it's skimming; (c) the tool's own description,
which the agent reads once per session, gives no reason to expect caution matters at all.

**Option A — A `status` field in the response schema, documented, optional to read.** Standard
API design: the field exists, well-typed, in the OpenAPI-equivalent MCP tool schema.

- Pros: cheap, conventional, exactly what §2.3's `facts` table already gives you for free.
- Cons: this is precisely the failure mode the checklist entry is worried about — an LLM
  consuming a tool result under time/token pressure reliably skims past well-behaved-looking
  structured fields it wasn't specifically told to weight, especially when most facts *are*
  settled and the field is silent 90%+ of the time. A field nobody is primed to look for is
  functionally invisible. **Rejected as insufficient on its own.**

**Option B (recommended) — Three reinforcing layers, none of them individually sufficient, all
present simultaneously:**

1. **Mandatory, always-present `caution` block on every fact object**, never omitted even when
   fully settled — the block's *presence* carries no signal (so an agent can't learn "block
   present ⇒ ignore this claim" and pattern-match around it), only its *content* does:
   ```json
   "caution": {
     "status": "disputed",          // settled | noted-variance | contested | disputed
     "confidence": "low",           // high | medium | low
     "verification": "partial",     // verified | partial | unverified | failed
     "dispute": "contradicted",     // none | contradicted | superseded
     "note": "Independent tier-A/B sources disagree on this claim; corroborate before treating it as settled."
   }
   ```
   `note` is `null` when `status == "settled"`, populated with a short fixed-template sentence
   otherwise (templated per `(status, dispute)` combination, not free LLM prose — consistent
   with D25's "output is machine-referenced... no free prose as justification" for the
   controversy assessor itself; the caution note should be exactly as mechanical).
2. **The caution note, when non-null, is prepended into the tool's returned text content**
   (not only the structured JSON side-channel), e.g. `search_knowledge`'s text result for a
   contested fact literally begins with "⚠ Contested claim — independent sources disagree. …"
   before the claim's own sentence. This borrows D31's already-ratified instinct — fetched
   content gets delimited so a consuming agent can't confuse data for instruction — and applies
   it to the opposite failure direction: instead of *hiding* an untrusted signal inside data,
   this *surfaces* an epistemic-status signal that must not get lost inside data. An agent
   skimming plain text still sees the caveat; it does not depend on the agent choosing to parse
   a JSON field.
3. **The MCP tool descriptions themselves state the contract**, read once per session by any
   MCP client: *"Every fact returned by this server carries a `caution` block. A `status` other
   than `settled` means treat the claim skeptically and prefer corroborating it against another
   source before asserting it as fact in your own output."* This is the most durable surface —
   it doesn't depend on any specific tool call noticing anything, because it's loaded into the
   agent's context as part of understanding what the tool *is*, before any specific fact is
   even in play.

- Pros: three independent surfaces (structured field, inline prose, tool-level framing) fail
  differently — an agent has to actively disregard all three to end up treating a disputed
  fact as settled, versus Option A's single point of failure. Costs nothing extra at the data
  layer (§2.3's `facts` table already computes every input this needs); the only new work is
  response-shaping code in the MCP server and a small fixed note-template table.
- Cons: verbosity — every single-fact response grows by a few dozen tokens even when settled
  (the `caution` block with `note: null` still costs schema overhead). Judged acceptable: token
  cost is trivial relative to LangAtlas's whole positioning (D19: per-fact sourcing is half the
  wedge; an agent that can't tell settled from disputed facts apart undermines that wedge more
  than a few extra tokens per call ever could).

**A related design choice: does MCP ever suppress a fact for low confidence/high
controversy?** No — mirrors D9 ("unchallenged facts count as unverified, not verified") and
D25 ("partially-verified facts render publicly, visibly marked with a badge — not suppressed
from public pages"). The MCP server applies the identical non-suppression policy: every fact
that would render on the site is retrievable via MCP, always caution-labeled, never hidden. A
consuming agent may of course choose to discard a disputed claim itself — that choice belongs
to the agent, not to LangAtlas silently withholding data it has.

**`search_knowledge` result ordering:** relevance stays the primary sort key (not confidence or
controversy) — D7's retrieval-quality metrics (Recall@5, MRR) were built and will be evaluated
against relevance-ranked results, and re-sorting by an orthogonal axis would both fight that
existing eval and bury the single most relevant hit behind lower-relevance-but-more-settled
ones, which is its own kind of misleading. Confidence/controversy stay a per-result annotation
(the caution block), not a ranking signal.

### 2.6 Snapshot shape and practicality

**Option A — Incremental/diffable bundles** (a base snapshot plus periodic deltas a consumer
applies in sequence).

- Pros: smaller downloads per publish once a base is established.
- Cons: real added complexity — change-data-capture logic in the build pipeline, sequencing/
  gap-detection in every consumer, and a corrupt-or-missing-delta failure mode that doesn't
  exist for full snapshots. At this project's scale (§ below), the bandwidth this saves is
  immaterial; the operational complexity it adds is not. **Rejected.**

**Option B (recommended) — Always a full snapshot**, exactly matching D13's existing
`data-vN` model (each tag is independently loadable, and rollback to any prior `data-vN` is
already a one-parameter operation per D13 — that design already implicitly assumes full
snapshots; this brainstorm just makes it explicit for the bundle's *internal* format too, not
introducing a new position).

- Pros: every `data-vN` is self-contained and independently verifiable/loadable; rollback,
  reproducibility, and "detect a truncated/corrupt bundle" (sha256 check against the manifest,
  refuse to proceed on mismatch — covers both the compressed download and the decompressed
  file) are all simpler with no cross-snapshot state to reason about.
- Cons: none structural at this scale.

**Size estimate:** brainstorm 09's own corpus-scale note ("low hundreds of features, ~10
languages initially, tens of thousands of derived facts") and D28's 15-language curated set
put the bundle in the same rough order as D15's source-corpus estimate ("~12–20k chunks,
~200 MB" — for the much larger full-text corpus). The dataset bundle itself, carrying only
structured records and derived facts (no embeddings, no source text), should land at most in
the low tens of MB compressed — trivial for a GitHub Release asset (2 GB per-asset limit) and
for CI transfer time on every green push. No compression/format cleverness beyond zstd on the
SQLite file is warranted at this scale.

## 3. Recommendation (*proposed*)

1. **Format (§2.1):** two GitHub Release assets per `data-vN` tag — a zstd-compressed single
   SQLite file (`langatlas-data-vN.sqlite.zst`) and a small JSON manifest
   (`langatlas-data-vN.manifest.json`). No wrapping archive; GitHub Releases already support
   multiple named assets per tag. This is an interchange-format choice only — it does not
   reopen D7's "no SQLite serving phase" decision; the live services still run on Postgres.
2. **Three independent version axes in the manifest (§2.2):** `data_tag` (the D13 release tag,
   identifies the snapshot, drives rollback), `ontology_version` (D16/D22's content semver,
   carried for provenance/D25-freshness-backstop display only, no compatibility logic needed
   because derived stores are always fully rebuilt), and the new `bundle_schema_version` (a
   semver over the bundle's own table/column/manifest structure — MAJOR = breaking structural
   change, MINOR = additive, PATCH = non-structural). Consumers pin a compiled-in
   `bundle_schema_version` compatibility range and **hard-refuse to load on a MAJOR mismatch**
   (loud failure, matching D13's failure-closed publish posture — never a silent partial load).
3. **Manifest fields:** `bundle_schema_version`, `ontology_version`, `data_tag`, `git_commit`,
   `built_at`, `embedding_model_id` (nullable — null until D22's research-phase benchmark picks
   one, or if the fact index simply isn't embedded yet), a pointer/flag for whether a matching
   private embeddings-cache entry exists (D13: the cache itself stays a private artifact, not
   public), `sqlite_sha256` + `sqlite_zst_sha256` + `sqlite_bytes` (integrity/truncation
   detection), per-table row counts, and the D24-ratified **published verifier error-rate
   estimates** (false-accept/false-reject) so the site's existing "measured error rates are a
   site-visible honesty feature" commitment has a natural data source to build from.
4. **D20 interaction (§2.3):** the bundle ships a **single flat, precomputed `facts` table** —
   one row per derived fact, already carrying `fact_id`, `anchor`, `canonical_claim`,
   `rendered_text`, `sources_json`, `provenance_json`, and all D25 status axes
   (`verification_result`, `confidence`, `freshness`, `dispute`, `controversy_score`,
   `display_status`) — alongside record-shaped tables (`instances`, `edges`, `rules`, `sources`,
   `features`, `concepts`, `languages`) for page-shaped reads, plus `tombstones` and
   `redirects` tables. Facts are computed once, in the build pipeline, and shipped as data —
   never re-derived independently by each consumer.
5. **MCP consumption (§2.4):** primary path unchanged from D8 — MCP queries the same Postgres
   the loader populates, checking a `_meta` table the loader stamps with the manifest's version
   fields. Additionally, ship a documented, explicitly-labeled **lite mode**: the MCP server can
   be pointed directly at a decompressed bundle `.sqlite` file with no Postgres, giving full
   point-lookup tools and SQLite-FTS5-only lexical search; every lite-mode response carries
   `"retrieval_mode": "lexical-fallback"` so reduced quality is never silently served as if it
   were the full hybrid-search deployment.
6. **The MCP caution contract (§2.5):** every fact object in every MCP tool response carries a
   mandatory, always-present `caution` block (status/confidence/verification/dispute/note, note
   null only when fully settled); non-null captions are additionally prepended as plain-text
   caveats into the tool's returned text content, not left as structured-only metadata; and the
   MCP tool descriptions themselves state the caution contract so it's loaded into a consuming
   agent's context once per session regardless of which fact gets fetched. No fact is ever
   suppressed for low confidence or high controversy (mirrors D9/D25's public-site
   non-suppression policy); `search_knowledge` keeps relevance as its primary sort key,
   confidence/controversy stay per-result annotations, not a re-ranking signal.
7. **Snapshot shape (§2.6):** always a full snapshot, never incremental/diffable — matches
   D13's existing rollback model and this project's modest data scale (bundle should land in
   the low tens of MB compressed, trivial for GitHub Release assets).

## 4. Open questions for the developer

1. **`bundle_schema_version` starting point and ownership** — start at `1.0.0` once this design
   is implemented (treating the pre-implementation period as `0.x`, consistent with D16/D22's
   own graduated-ceremony pattern for the ontology), or is a lighter-touch versioning scheme
   (e.g. skip the axis entirely until the bundle's shape actually changes once) acceptable for
   a solo-maintained project where the developer controls all three consumer codebases anyway
   and can just redeploy them together?
2. **Is the MCP lite mode (bundle-direct, lexical-only) worth building at all in v0**, or should
   it stay a documented future accessibility feature (flagged in §5) while the primary
   Postgres-backed MCP path ships first? The primary path alone already satisfies D8's original
   design; lite mode is this brainstorm's addition on top, not something any prior decision
   committed to.
3. **Manifest verbosity for the caution contract's note templates** — should the fixed
   `(status, dispute)` → note-sentence template table live in the bundle itself (so it's
   versioned alongside the data it describes) or in the MCP server's own code (so wording can be
   improved without a full data republish)? Leaning toward MCP-server-side (wording is a
   presentation concern, not data), but worth confirming given the "ship as data, not logic"
   instinct driving most of this design's other choices.
4. **Should the Postgres loader's embedding-cache-reuse check be keyed on exact
   `(embedding_model_id, corpus_hash)` match only (safe but frequently forces a full recompute)
   or allow a looser per-fact content-hash match so unchanged facts skip re-embedding even
   across an otherwise-changed publish** — this interacts with D22's embedding-benchmark
   subphase and D6's cost posture but wasn't scoped there; worth a firm answer before the loader
   is actually implemented so recompute cost doesn't become a surprise.

## 5. New brainstorm topics surfaced

- **Postgres loader implementation & blue-green load mechanics** — the concrete loader script
  (SQLite → Postgres bulk copy), the shadow-schema-then-atomic-swap pattern needed so MCP/
  FastAPI never observe a half-loaded state mid-reload, and the embedding-cache-reuse decision
  from open question 4 above. No existing backlog item covers Postgres-loader mechanics
  specifically (topic 27 is the *agent-runner commit protocol*, a different part of the
  pipeline); this would need a **new backlog number** (next available at time of writing: 53).
- **MCP lite-mode design** — if open question 2 above resolves toward building it, the actual
  FTS5 query quality bar, packaging/distribution story (how someone downloads and points a
  local MCP config at a bare `.sqlite` file with no Docker), and how prominently it's documented
  versus the primary deployment. Related to, but distinct in scope from, topic 45 (finding-aid
  tooling) — that topic is about PLDB/Wikidata-style external finding aids during the research
  phase, not about MCP's own retrieval backend options. Would also need a **new backlog number**
  (54) unless the developer judges it small enough to fold directly into topic 26's own
  eventual implementation without a dedicated design pass.
