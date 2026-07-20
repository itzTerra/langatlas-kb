# 53 — Postgres Loader Implementation & Blue-Green Load Mechanics

> Backlog brainstorm for LangAtlas. Topic: the concrete Postgres loader that turns a published
> `data-vN` bundle (brainstorm 26/D35: a zstd-compressed single SQLite file + JSON manifest,
> published as GitHub Release assets) into the live docker-compose Postgres (D7) — the loader
> script's shape, the shadow-schema-then-atomic-swap pattern so the read-only MCP server and any
> future FastAPI adapter (D8) never observe a half-loaded state mid-reload, and the
> embedding-cache-reuse keying decision D35/brainstorm 26 flagged as open question 4 but
> explicitly deferred to this topic. Direct follow-on to brainstorm 26 — this brainstorm does not
> relitigate the bundle format, only designs what consumes it. Binding context: D1 (git is the
> database; Postgres is a one-way derived artifact, never migrated in place — always rebuilt),
> D7 (Postgres + pgvector + tsvector FTS from day one, via docker compose; retrieval stays behind
> a small library interface), D8 (MCP is read-only and queries Postgres directly; a FastAPI
> adapter serves non-MCP providers and site search — both are the services this loader must never
> let observe a half-loaded state), D13 (validated-artifact CI pattern; `data-vN` immutable tags;
> failure-closed posture — red main publishes nothing), D22 (embedding-model benchmarking; the
> source-corpus default is `qwen3-embedding-4b` pending that benchmark), D26/brainstorm 13
> (`RunContext` provider-abstraction layer — any embedding calls the loader makes go through it,
> including its own content-addressed cache keyed on resolved-model-id + input + schema), D35
> (this topic's direct predecessor — bundle format, three version axes, the `facts` table shape,
> MCP's Postgres-primary/bundle-lite-mode split, the caution contract). All proposals below are
> *proposed* until the developer ratifies.

## 1. Problem framing

D35 settled *what* gets published (a single SQLite file + manifest) and *who reads it* (the site
build, the loader, MCP indirectly via Postgres). It explicitly left one job unspecified: the
program that actually walks the SQLite file and populates the live Postgres instance backing
MCP and the FastAPI adapter. That program has three distinct correctness obligations, not one:

1. **Bulk-copy correctness** — every row in the bundle's tables ends up in Postgres with the
   right types, the right indexes (pgvector ANN index over fact/source embeddings, tsvector FTS
   index over `rendered_text`/`anchor`), and nothing silently dropped or truncated.
2. **No half-loaded state, ever** — MCP and FastAPI are live services queried by real agents
   at arbitrary times; a reload that is mid-flight for even a few seconds must not be visible to
   a concurrent `search_knowledge` call as a database with `features` populated but `facts`
   still empty, or an FTS index that only covers half the new facts.
3. **Reload without redundant work** — recomputing every fact's embedding on every publish, when
   the median publish touches a small fraction of records, is wasteful against D6's cost
   posture and D22's benchmarking effort; but too loose a cache-reuse rule risks serving a stale
   or simply wrong vector for a fact whose text actually changed.

These three obligations pull in different directions structurally — obligation 2 wants "swap
everything atomically, all or nothing," while obligation 3 wants "reuse per-item state across
loads," which only works if the reuse key is *derived from immutable content*, not from load
sequence. The design below treats them as one coherent script with two clearly separated
concerns (schema-level blue-green swap; row-level embedding cache), not one undifferentiated
"loader" blob.

Scale check (carried from brainstorms 09/25/26): tens of thousands of facts, low thousands of
instances/edges, ~15–25 languages. A full reload — recomputing every embedding from scratch — is
a bounded, non-alarming cost even in the worst case; the cache-reuse question is about
*efficiency and staleness risk*, not about whether a full rebuild is feasible at all. This keeps
the design pressure on correctness and simplicity, per the project's "boring, solo-maintainable
technology" mandate, rather than on shaving load time that was never actually a problem.

## 2. Options with trade-offs

### 2.1 Loader script shape and tooling

**Option A (recommended) — A single Python script/module, `tools/loader/load_bundle.py`,
following the same `tools/<domain>/` CLI-family shape as D41's `tools/observability/report.py`
and D26's provider layer**, invoked by CI (or manually for local dev) with the bundle path/URL
and target Postgres DSN as arguments.

- Pros: matches the project's existing tooling convention (D41's `tools/<domain>/` family) and
  language choice — Python is already load-bearing everywhere else in the pipeline (agent
  runner, `RunContext`, validators), so the loader gains nothing from a different language and
  loses consistency (one fewer runtime to install, one fewer set of dependency-pinning rules).
  Python's stdlib `sqlite3` reads the bundle with zero extra dependency; `psycopg` (v3,
  the actively maintained line) does the Postgres side; both are "boring" per the project's own
  standard. The script is naturally three composable stages — **extract** (stream rows out of
  the bundle's SQLite tables), **transform** (resolve which facts need fresh embeddings, per
  §2.3), **load** (bulk insert into a shadow schema, per §2.2) — which keeps each stage
  independently testable against the record/replay fixture pattern D26 already established for
  provider calls.
- Cons: none structural. The only real design work is stages 2 and 3 below, not the choice of
  language.

**Option B — A dedicated Go/Rust binary for raw bulk-copy throughput.** Rejected outright: at
this project's scale (§1's scale check), Postgres's own `COPY` command bulk-loads tens of
thousands of rows in well under a second regardless of which language issues the `COPY` — the
bottleneck, if any exists at all, is embedding computation (an API call to the university host or
Claude, not local CPU work), which a faster host language does nothing to speed up. Introducing a
second implementation language for a solo-maintained project's build tooling directly conflicts
with "boring, solo-maintainable technology" for a throughput problem that doesn't exist here.

**Mechanics of the extract→load step itself:** the script opens the decompressed bundle SQLite
file read-only, and for each bundle table issues either (a) `psycopg`'s `copy_expert`/`COPY …
FROM STDIN` fed by a generator that reads SQLite rows and re-serializes them (fastest, avoids
building Python-side row objects for tens of thousands of rows), or (b) batched
`executemany`-style inserts where a table needs light transform (e.g. `sources_json`/
`provenance_json` text columns landing as native Postgres `jsonb` rather than opaque text, so the
FastAPI adapter and any future ad hoc queries can index/query into them directly instead of
parsing JSON application-side). Recommendation: `jsonb` for anything the manifest or D35's
`facts` table currently carries as a JSON-in-TEXT column (`sources_json`, `provenance_json`,
`controversy_signals_json`) — this is a one-line type change in the loader's `CREATE TABLE`
statements, costs nothing in the bundle format itself (the bundle stays SQLite-portable TEXT;
only the Postgres side upgrades the column type on load), and turns "MCP wants to filter facts by
source tier" from a client-side JSON-parse-every-row operation into a real `WHERE
sources_json @> '...'` index-backed query if that need ever arises.

### 2.2 Blue-green / shadow-schema-then-atomic-swap mechanics

This is the topic's core mechanical question: how does Postgres guarantee MCP/FastAPI never see
a half-loaded state.

**Option A — Truncate-and-reload the live tables in place, inside one transaction.** `BEGIN;
TRUNCATE facts, instances, edges, ...; COPY ... FROM STDIN; ... COMMIT;`.

- Pros: simplest possible code — no schema juggling, one set of table names forever.
- Cons: this is the option that most directly risks the failure mode the checklist entry names.
  Postgres transactional DDL/DML visibility means concurrent readers *do* see a consistent
  snapshot under MVCC (a `SELECT` mid-transaction sees either all-old or all-new, never a mix,
  because the whole reload is one transaction) — so it is not technically unsafe in the
  read-consistency sense. But it has two real problems: (1) it holds table-level locks
  (`TRUNCATE` takes `ACCESS EXCLUSIVE`) for the full duration of the reload, meaning every live
  MCP/FastAPI query queues or times out for as long as the `COPY` + index rebuild takes, which
  for pgvector's ANN index (`ivfflat`/`hnsw`) build over tens of thousands of embeddings is not
  instant; and (2) a mid-transaction failure (embedding-fetch timeout partway through a
  transform step that happens inside the same transaction, a constraint violation on a later
  table) rolls the whole thing back cleanly, which is *fine* for correctness but means the retry
  has to redo the entire load from scratch inside the lock window, worsening (1). **Rejected**
  as the primary mechanism — the checklist entry specifically asks for a pattern that avoids
  observable disruption, and a multi-second-to-minutes `ACCESS EXCLUSIVE` lock on every
  MCP-serving table is observable disruption even if it's never a *correctness* violation.

**Option B (recommended) — Build into a freshly-created, schema-suffixed shadow schema, then
flip a single `search_path`-equivalent pointer atomically.** Concretely:

1. Each load creates a new Postgres schema named after the bundle's `data_tag`, e.g. `schema
   data_v418;` (D35's `data_tag` is already the immutable per-publish identifier, so it is the
   natural schema-name suffix — no new naming scheme to invent).
2. All bulk-copy work (§2.1) targets tables inside `data_v418` — `data_v418.facts`,
   `data_v418.instances`, etc. — fully isolated from whatever the currently-live schema is.
   Index builds (pgvector ANN, tsvector FTS, PK/FK constraints) happen here too, against a schema
   nothing is querying yet, so there is no lock contention with live traffic at all during the
   entire build — this is the load's slow part, and it now costs zero visible disruption.
3. Once `data_v418` is fully built and validated (row counts match the manifest, sha256 spot
   checks, a smoke-test query against `get_fact`/`search_knowledge`-shaped SQL), the swap is a
   single, fast, transactional operation: a `current` schema is never itself a data-holding
   schema, only a set of views (`current.facts`, `current.instances`, …) each defined as `CREATE
   VIEW current.facts AS SELECT * FROM data_v418.facts`. The swap is `BEGIN; CREATE OR REPLACE
   VIEW current.facts AS SELECT * FROM data_v418.facts; ... (one per table) ... COMMIT;` — a
   batch of `CREATE OR REPLACE VIEW` statements inside one transaction, each individually
   near-instant (view definition swaps don't touch underlying data, just catalog metadata), and
   collectively atomic (MVCC guarantees no concurrent reader ever sees `current.facts` pointing
   at `data_v418` while `current.instances` still points at `data_v417`).
4. MCP and the FastAPI adapter query `current.*` exclusively — never a `data_vN`-suffixed table
   name directly. This is the one piece of connection-string/query discipline the swap mechanism
   depends on, and it's a one-time convention, not per-query ceremony.
5. After a successful swap, the *previous* `data_vN` schema is left in place (not dropped) for
   exactly one more cycle — this is what makes rollback (§2.4) a schema-pointer flip back, not a
   re-load.

- Pros: this is the concrete shadow-schema-then-atomic-swap pattern the checklist entry asks
  for, by name. Build time (the slow, lock-risky part) happens entirely off to the side with zero
  live-query impact. The swap itself is sub-second regardless of data volume, because it moves
  view definitions, not rows. Rollback and "keep N previous versions for safety" fall out of the
  same mechanism for free (§2.4). This mirrors, one layer down, the same "immutable versioned
  artifact + a pointer that moves" shape D13 already uses for `data-vN` release tags and
  `latest-green` — the loader's schema-per-`data_tag` + `current` view-pointer is the Postgres-side
  echo of exactly that pattern, not a new design idiom.
- Cons: views add one indirection layer application code must respect (query `current.facts`,
  never `data_v418.facts` directly) — mitigated by making this a documented, single-sentence
  connection convention, and optionally enforced by granting the MCP/FastAPI Postgres role
  `SELECT` only on the `current` schema, not on `data_vN` schemas directly, so the convention is
  structurally enforced rather than merely documented. Old schemas accumulate disk space until
  pruned (§2.4 gives a retention rule). `CREATE OR REPLACE VIEW` requires the view's column
  list/types to stay compatible across the swap — a MAJOR `bundle_schema_version` bump (D35 §2.2)
  that changes a column's type or removes a column needs the loader to `DROP VIEW` +
  `CREATE VIEW` fresh rather than `CREATE OR REPLACE`, which is a slightly different code path
  the loader needs to detect from the manifest's `bundle_schema_version` before attempting the
  swap — a small, known, testable branch, not an open design question.

**Option C — Two permanently-provisioned physical schemas (`blue`/`green`), alternating which
one is "live" via an application-level config flag (not a Postgres-native view swap).** Classic
blue-green from web-service deployment practice.

- Pros: familiar pattern name; no `CREATE OR REPLACE VIEW` type-compatibility subtlety.
- Cons: the "which one is live" flag has to live *somewhere* MCP/FastAPI can read it — either a
  config file redeployed alongside the services (which reintroduces exactly the coordinated-
  redeploy problem D13 built the whole bundle-publish pattern to avoid) or a small control-plane
  table those services poll (extra moving part, extra query on every request unless cached, and
  now a cache-invalidation problem of its own). Option B's view-based swap gets the identical
  end result — one atomic switch, zero service redeploys, zero extra runtime query — using
  Postgres's own transactional DDL as the coordination mechanism instead of inventing an
  external one. **Rejected** — strictly more moving parts than Option B for the same guarantee.

**Recommendation:** Option B — schema-per-`data_tag`, `current.*` views as the atomic swap
point, MCP/FastAPI query `current` exclusively (structurally enforced via role grants).

### 2.3 Embedding-cache-reuse keying decision

The task brief and D35 open question 4 pose this as exact `(embedding_model_id, corpus_hash)`
match vs. a looser per-fact content-hash match. Restating precisely what each means in practice:

**Option A — Exact `(embedding_model_id, corpus_hash)` keying.** `corpus_hash` is a single hash
over the *entire* fact corpus (e.g. a hash of the bundle's full `facts` table content, or of the
sorted concatenation of every fact's `rendered_text`). The cache entry says "these embeddings are
valid for embedding_model X against corpus-state Y as a whole." Any single fact changing —
one new record, one corrected typo — changes `corpus_hash`, invalidating the *entire* cache
entry, forcing every fact's embedding to be recomputed on the next load even though only one
fact's text actually changed.

- Pros: maximally safe against subtle correctness bugs — there is no possible mismatch between
  "which facts changed" bookkeeping and "which embeddings are stale," because the granularity is
  coarse enough that there's nothing to get wrong. Trivial to implement and reason about.
- Cons: this is close to a full-recompute-on-every-publish policy in practice. D13 already
  established `data-vN` tags cut daily (only on changed days) — with an actively-run agent
  pipeline committing facts continuously, *most* days will have at least one changed fact
  somewhere, so `corpus_hash` changes on most publishes, and this option's "cache reuse"
  degenerates to "cache reuse only on days with literally zero fact changes anywhere," which is
  not the common case this cache exists to serve.

**Option B (recommended) — Per-fact content-hash keying**, keyed on `(embedding_model_id,
fact_id)` where `fact_id` is already D23's content-keyed `f-<12hex SHA-256 of the canonical claim
string>` — **not a new hash the loader invents**, the identity fact IDs already carry. Because
D23 already made fact IDs content-derived (a corrected claim mints a *new* fact ID, the old one
tombstoned per D23's append-only `tombstones.yaml`), `fact_id` unchanged **is** "this exact claim
text is unchanged," by construction — there is no separate staleness question to get right,
because the fact ID *is* the content hash of the thing being embedded. The loader's cache-reuse
check per fact becomes: has this `fact_id` (paired with the target `embedding_model_id`) been
embedded before? If yes, reuse; if no (new fact, or an old fact_id's claim text changed and thus
its ID changed), compute fresh.

- Pros: this is not actually a "looser, riskier" alternative to Option A in the way the open
  question's framing implies — it inherits Option A's exact-match safety property *for free*,
  because D23's fact-ID identity discipline already guarantees `fact_id` stability tracks content
  stability one-to-one (copyedit-tolerant hashing per D23's ratification means trivial rewording
  doesn't even mint a new ID, which is the *correct* behavior here too: if the claim's meaning is
  unchanged, the old embedding is still semantically valid). The granularity match is what
  changes the outcome: a corpus of 40,000 facts where 30 changed on a given publish recomputes 30
  embeddings and reuses 39,970, instead of Option A's all-or-nothing. This directly serves D6's
  cost posture and D22's benchmarking effort (embedding calls are a real, metered cost through
  `RunContext`) without inventing any new identity mechanism — it is simply *using* D23's fact-ID
  discipline for a second purpose it was already structurally suited for.
- Cons: requires the cache to be keyed and looked up per-fact rather than checked once per load
  (a few tens of thousands of key lookups instead of one) — negligible cost against a local
  SQLite or Postgres-table-backed cache. Requires the loader to route every embedding call
  through `RunContext` (D26) so the existing content-addressed cache (already keyed on
  resolved-model-id + input + schema, per D26's ratified design) is the *actual* cache
  implementation — this is not new cache infrastructure, it's confirming the loader is simply
  another `RunContext` client, keying its embedding calls on `(embedding_model_id, fact_id,
  rendered_text)` the same way any other `RunContext` call is keyed on its own inputs. The one
  genuinely new piece of bookkeeping is a small `fact_embeddings` table (or reuse of D26's
  existing cache store directly) mapping `fact_id → embedding vector` so the loader can distinguish
  "already embedded, reuse" from "new fact_id, embed" without re-querying `RunContext`'s cache by
  full input replay for every fact on every load — a straightforward index, not new design.

**Why not go looser than per-fact content hash (e.g. embed at the `record` level, or a fuzzy
near-duplicate match)?** Not evaluated as a serious option — D23's fact granularity is already
the unit the embedding index is chunked at (D7: "embed fact cards... with `{chunk_type,
feature_id, language_id, source_id, status}` metadata"), so keying cache reuse at any coarser
grain than the embedding's own chunking unit would just reintroduce Option A's over-invalidation
problem one level up, and keying it looser (fuzzy/near-duplicate) trades a small, well-understood
efficiency gain for a real correctness risk (two similar-but-meaningfully-different claims
sharing a stale embedding) that the exact `fact_id` match already avoids at zero extra cost.

**Recommendation:** Option B. It is not a safety-for-efficiency trade-off at all once D23's
fact-ID discipline is taken seriously — `fact_id` stability already *is* content stability, so
per-`fact_id` keying gets Option A's exactness and a realistic cache-hit rate simultaneously. The
firm recommendation to the developer: implement per-`fact_id` keying from the start; do not build
Option A's coarser `corpus_hash` gate at all, even as an interim step — it would need to be torn
out once Option B's cache-hit-rate benefit becomes visible on the first multi-day gap between
touched and untouched facts, and building it first adds a migration step with no compensating
benefit.

### 2.4 pgvector/FTS index interaction and rollback

**Index rebuilding during the swap:** because §2.2's Option B builds the entire shadow schema
before anything is exposed, index builds (pgvector ANN index, tsvector FTS index, standard
btree PK/FK indexes) happen *inside* `data_v418` against a schema no live query touches — there
is no "rebuild the index in place while serving traffic" problem to solve at all, which is the
main practical win of the shadow-schema approach over Option A's truncate-in-place alternative.
The loader builds indexes after the bulk `COPY` completes (standard Postgres practice —
`CREATE INDEX` after bulk load is faster than incrementally maintaining an index row-by-row
during a bulk insert), then runs its own validation pass (row counts against the manifest,
smoke-test queries) before proceeding to the swap. Embeddings themselves are computed *before*
the shadow schema's `COPY` step (per §2.3's cache-reuse logic — resolved to a full vector per
fact ahead of time), so the ANN index build has complete data to index in one pass, never a
partial one.

**Rollback if a load fails partway:** because the shadow schema is fully isolated until the
swap, "fails partway" during the build phase (embedding fetch timeout, a constraint violation,
CI cancellation) simply leaves an incomplete `data_v418` schema sitting unused — `current` still
points at `data_v417`, live traffic is entirely unaffected, and the fix is to drop the broken
`data_v418` schema and retry the load (cheap — nothing live was ever touched). The only
genuinely dangerous failure window is *during the swap transaction itself* — but per §2.2 this is
a single short transaction of `CREATE OR REPLACE VIEW` statements, which either fully commits or
fully rolls back per ordinary Postgres transactional guarantees; there is no partial-swap state
representable in Postgres's own consistency model. **Rollback to an older `data-vN` after a swap
already succeeded** (the bundle loaded fine, but a problem is discovered afterward) is exactly as
cheap: as long as the previous schema (`data_v417`) hasn't been pruned yet, rollback is the same
atomic `CREATE OR REPLACE VIEW ... FROM data_v417...` swap run in reverse — a one-parameter
operation mirroring D13's existing "rollback to any `data-vN`" release-asset guarantee, now given
its Postgres-side mechanism.

**Retention rule (new, this brainstorm's contribution, needed to bound disk growth):** keep the
current schema plus the **previous** one only (two live schemas at any time, `data_vN` and
`data_v(N-1)`), pruning anything older once a new swap succeeds — this gives exactly "one-step
rollback always available, cheaply" without unbounded schema accumulation, and matches D13's own
rollback framing (rollback is described as a recovery action for *the* prior state, not an
arbitrary-depth version browser; deeper rollback already has a recovery path — re-run the loader
against an arbitrarily old `data-vN` release asset directly, since D35 confirms every bundle is a
self-contained full snapshot, never a delta).

## 3. Recommendation (*proposed*)

1. **Loader shape (§2.1):** a single Python script, `tools/loader/load_bundle.py`, matching the
   D41 `tools/<domain>/` CLI-family convention; stdlib `sqlite3` + `psycopg` v3; JSON-in-TEXT
   columns (`sources_json`, `provenance_json`, `controversy_signals_json`) upgrade to native
   `jsonb` on the Postgres side during load (bundle format itself unchanged).
2. **Blue-green mechanics (§2.2):** each load builds into a fresh, `data_tag`-suffixed schema
   (`data_v418`); all bulk-copy and index-build work happens there with zero live-query impact;
   the swap is a single transaction of `CREATE OR REPLACE VIEW current.<table> AS SELECT * FROM
   data_v418.<table>` statements, atomic and sub-second regardless of data volume; MCP/FastAPI
   query `current.*` exclusively, structurally enforced via Postgres role grants (`SELECT` only
   on `current`, not on `data_vN` schemas). A MAJOR `bundle_schema_version` bump requires
   `DROP VIEW` + fresh `CREATE VIEW` instead of `CREATE OR REPLACE VIEW`, detected from the
   manifest before the swap begins.
3. **Embedding-cache-reuse keying (§2.3):** key on `(embedding_model_id, fact_id)`, using D23's
   existing content-keyed fact IDs directly rather than inventing a new corpus- or record-level
   hash — this gets exact-match safety and a realistic cache-hit rate simultaneously, because
   fact-ID stability already tracks content stability one-to-one. Route all embedding calls
   through the existing `RunContext` (D26) cache; add one small `fact_embeddings` lookup table so
   the loader can decide reuse-vs-recompute per fact without replaying full cache keys for every
   fact on every load. Do not build the coarser `corpus_hash` gate even as an interim step.
4. **Index rebuilding (§2.4):** embeddings are resolved before the shadow schema's bulk `COPY`;
   pgvector ANN and tsvector FTS indexes are built after `COPY` completes, entirely inside the
   isolated shadow schema, never against a live-queried table.
5. **Rollback (§2.4):** a failed build-phase load leaves `current` untouched (drop the broken
   shadow schema, retry); rollback after a successful swap is the same atomic view-swap run in
   reverse. Retain exactly two live schemas (current + previous) at any time, pruning older ones
   after each successful swap; deeper rollback re-runs the loader against an older `data-vN`
   release asset directly (every bundle is a full snapshot per D35).

## 4. Open questions for the developer

1. **Postgres role/grant setup for the `current`-only enforcement (§2.2)** — should this be
   provisioned by the loader script itself on first run (idempotent `CREATE ROLE IF NOT
   EXISTS`/`GRANT` statements it re-applies every load) or by a separate one-time docker-compose
   init script, so the loader's own code stays focused on data movement rather than role
   management?
2. **Smoke-test validation depth before the swap (§2.2 step 3)** — is a row-count-against-
   manifest + a handful of hand-picked smoke queries sufficient gating before flipping `current`,
   or should the loader run the full D7 golden-set Recall@5/MRR eval against the shadow schema
   as a pre-swap gate (higher confidence, but ties the loader's runtime to the eval suite's, and
   risks the loader itself becoming a second place retrieval-quality regressions get caught,
   duplicating a check that already lives elsewhere in the pipeline)?
3. **Where does `tools/loader/load_bundle.py` get invoked from** — a step in the `langatlas-site`
   repo's `repository_dispatch`-triggered build (per D13's existing site-consumes-bundle
   trigger), a separate scheduled job against the `langatlas-kb` repo's own docker-compose stack,
   or both (site build triggers site-owned Postgres; a developer-run local instance is loaded
   manually for local MCP testing)? D13 specifies the site's consumption trigger but not whether
   the *Postgres-backing* load is the same event or a distinct one.
4. **Retention depth (§2.4)** — is exactly two live schemas (current + previous) the right
   default, or should the developer want a slightly deeper window (e.g. three) for a brief grace
   period after a swap before the previous schema is pruned, trading a small amount of disk for
   a wider one-step-rollback safety margin?

## 5. New brainstorm topics surfaced

None. This brainstorm resolves brainstorm 26's open question 4 in full and completes the
Postgres-loader design space the checklist entry scoped; no new sub-problem surfaced during the
design that isn't already covered by an existing backlog item (the loader's invocation trigger,
open question 3 above, is a scheduling/CI-wiring detail to settle with the developer, not a
design space large enough to warrant its own brainstorm number).
