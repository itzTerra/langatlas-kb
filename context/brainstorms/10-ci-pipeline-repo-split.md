# 10 — Repo→Artifacts CI Build Pipeline & Repo Split

Binding context (decisions.md): git YAML repo is canonical (D1); Postgres + pgvector from day
one via docker compose, always a derived artifact (D7); agents commit **directly, no PR gate**
— the automated verification gate (D4) + CI are the only gates (D1); repos are **split** —
knowledge-base management and the website are separate public repositories with separate issue
trackers (owner decision, D1/D9); site is fully static Astro (D10).

## Problem framing

Round 1 (07 §D) recommended a monorepo and called a split "premature"; the owner overruled that
for issue-tracker separation. So the question is no longer *whether* to split but *what the
split costs CI and how to pay the least for it*. Three sub-problems:

1. **Cross-repo plumbing** — a fact commit in the KB repo must eventually become a rebuilt,
   redeployed website in another repo. What carries the signal, and what carries the data?
2. **The pipeline itself** — validate → compile → load Postgres → incremental embed → build
   site → deploy, with rollback, determinism, and a story for direct agent commits that fail
   validation (there is no PR to bounce them off).
3. **The boundary** — which files live where, and whether a third tooling repo earns its keep.

A structural observation that shapes everything below: **the split is only painful if the
website consumes the KB repo's *files*. If it consumes a *versioned, validated build artifact*,
the split becomes a clean producer/consumer contract** — the same one-way-derivation principle
D1 already established for Postgres and the vector index, applied once more at the repo
boundary. Almost every "split hurts" scenario dissolves under that pattern; almost every one is
real under raw-file coupling.

## (1) Does the repo split hurt CI? — concrete analysis

### 1a. Cross-repo build triggers

| Mechanism | How | Trade-offs |
|---|---|---|
| **`repository_dispatch`** (recommended) | KB repo's CI, after a green build, calls the GitHub API to fire an event in the site repo; site workflow listens on `repository_dispatch: [kb-updated]` | The standard pattern. One catch: the default `GITHUB_TOKEN` cannot trigger workflows in *another* repo — needs a fine-grained PAT (scoped to the site repo, `contents:write` or `actions:write`) or a GitHub App token stored as a KB-repo secret. ~10 lines of workflow YAML. |
| `workflow_dispatch` (manual/API) | Same API shape, but semantically "a human pressed the button" | Fine as the manual override path; wrong as the automatic path. |
| Scheduled polling | Site repo cron job (e.g. every 6 h) checks whether the KB `latest-green` release changed; rebuilds if so | Zero secrets, zero coupling — but adds hours of latency and burns Actions minutes on no-ops. **Keep as the fallback** (daily), not the primary. |
| External webhook relay | KB webhook → some server → site API | Requires a hosted server; violates the no-infra posture (D12 absent-on-purpose). Reject. |

**Cost of the split here: one fine-grained PAT (or GitHub App) to create, store, and rotate.**
Annoying once a year, not architecturally significant. The scheduled daily rebuild doubles as
insurance against missed dispatches and rotates the site's link-freshness anyway.

### 1b. How the website repo consumes KB data

This is the decision that determines whether the split hurts.

| Option | Mechanism | Trade-offs |
|---|---|---|
| **A. Git submodule** | Site repo pins KB at a SHA; a bot bumps the pin | Reproducible builds (pin = version), but every KB change needs a bump commit in the site repo — a bot writing commits whose only content is a SHA. Submodule ergonomics are famously miserable for contributors; and the site would consume *raw YAML*, meaning it must re-run validation/compilation itself (duplication, see 1d). Reject. |
| **B. Checkout-at-build** | Site CI does `actions/checkout` of the KB repo at `main` (or a ref) during build | Simplest possible. But building from `main` HEAD is non-hermetic: an agent can push between validation and site build, so the site could build *unvalidated* data — unacceptable with no PR gate. Pinning to "last green SHA" fixes that but you must plumb the SHA through the dispatch payload, and the site still consumes raw YAML (duplication again). Workable, second choice. |
| **C. Published validated data artifact** (recommended) | KB CI, on green `main`, compiles YAML → one canonical dataset bundle (e.g. `dataset.json`/JSONL + compiled graph + schema version), publishes it as a **GitHub Release asset** on a rolling `latest-green` tag plus immutable `data-vN` tags; the dispatch payload carries the tag. Site CI downloads the named artifact and builds from it. | The site *cannot* build from unvalidated or half-validated data — invalid states are unrepresentable downstream. Immutable tags give free rollback ("rebuild from `data-v41`"). The artifact is the contract; the site never parses YAML, never runs KB validation, never needs the KB toolchain. Costs: defining the bundle format + version field (needed anyway for Postgres/MCP), and accepting that site data is a snapshot, not a live checkout. |
| D. Published package (npm/PyPI) or OCI artifact | Same as C with heavier packaging ceremony | Registry versioning for free, but publish tokens, registry policies, and package overhead for a consumer that is one CI job. GitHub Releases already gives versioned, immutable, public, free hosting. Reject for now; trivial to migrate to later since it's the same contract. |

**Recommendation: C.** Note it is not extra work invented to serve the split — a compiled
canonical bundle is *already* the natural input to the Postgres loader, the embedder, and the
MCP server (D7/D8). The split merely forces you to name and version an interface you wanted
anyway. This is the honest sense in which the split *helps*: it makes the derivation boundary
explicit instead of letting the site grow quiet dependencies on raw file layout (C13's file
granularity can then change without touching the site).

### 1c. Schema sharing

The site should depend on the **artifact contract** (bundle format + `schema_version` field),
not on the KB's authoring schema (JSON Schema for YAML files). Authoring schema lives in the KB
repo and is the KB's private concern; the bundle carries a copy of whatever the site needs
(entity shapes, edge types) *inside itself*, self-describing. Site CI asserts
`schema_version` compatibility and fails loudly on a major bump — that failure is the correct
behavior (site code must be updated deliberately), and it is the one genuinely
non-atomic moment the split creates (see 1e). No third "shared schema repo": for a solo
developer that is three-way version skew with no compensating benefit.

### 1d. CI duplication

With option C there is almost none: KB repo runs validation, compilation, embedding,
Postgres smoke-load, golden-set eval; site repo runs only "download bundle → Astro build →
deploy" plus its own site concerns (link check of *site-internal* hrefs, Lighthouse budget if
desired). The only shared code is the bundle *reader*, which is small; vendor a copy or accept
a ~50-line duplication rather than minting a shared package for it at MVP. Under options A/B
the site would re-run schema validation to protect itself — that duplication is the trap C
avoids.

### 1e. Atomicity of "fact changed → site updated"

Strict atomicity is already gone the moment the site is a CI-built static artifact — even a
monorepo has a minutes-long window between merge and deploy. The split changes the window from
"one pipeline's latency" to "two chained pipelines' latency" (realistically 3–10 min total at
this scale). For a knowledge site this is irrelevant.

The real atomicity loss is **coordinated breaking change**: a schema change that requires both
new KB data and new site rendering code cannot land in one commit. Mitigation is the standard
one: `schema_version` in the bundle, site declares a supported range, sequence deploys
(site code that accepts both versions → KB bump → site cleanup). This will happen a handful of
times a year and is a 30-minute inconvenience each time, not a design flaw. Rank: the single
largest genuine cost of the split, and it is modest.

### 1f. Secrets & permissions

- **KB repo secrets**: university-API key (embeddings, verifier), the cross-repo dispatch
  PAT/App token, Wayback SavePageNow (no key needed). Public repo is safe: GitHub does not
  expose secrets to fork-PR workflows, and the no-PR-gate model means the write path is
  agents/owner pushing to `main` directly — untrusted code never runs with secrets.
  One rule: workflows triggered by `pull_request` (outside contributors do exist — D9
  challenges may come with PRs eventually) must run *validation only*, never embedding or
  publish steps.
- **Site repo secrets**: deploy credentials only (or none, if GitHub Pages with OIDC /
  `GITHUB_TOKEN`). The split is actually a *security improvement* here: the repo agents write
  to holds no deploy credentials, and the repo that deploys accepts no agent commits.
- Agent runner pushes to KB `main` need a machine identity — a GitHub App ("hermes-agent") is
  cleaner than the owner's PAT: attributable commits, revocable, and it satisfies D5's
  provenance ("proposer agent" visible in git author).

### 1g. Where the derived Postgres + embeddings build lives

Postgres is **not a hosted production service** at MVP — the site is static (D10) and RAG is
local (D8). So there are two instantiations of the same derivation:

- **Locally** (docker compose): `compose up` gives postgres+pgvector; a `just rebuild` target
  compiles YAML → bundle → loads Postgres → incrementally embeds (content-hash cache, local
  cache dir). This is the copy agents and MCP actually query.
- **In KB CI**: a Postgres *service container* is spun up per run to prove the bundle loads and
  the golden retrieval eval passes (D7). It is a smoke test, then discarded. Embeddings in CI
  are made cheap by a content-hash-keyed cache (`actions/cache`, or restored from the previous
  release's embeddings asset) so a typical commit embeds only the facts it touched.
- **Embeddings distribution**: never committed to git (D1), but *publishing them as a release
  asset* (parquet keyed by content-hash + model id) is allowed and useful — a fresh clone can
  `just bootstrap` by downloading the embedding cache instead of re-embedding the corpus
  through the slow university API. Check licensing posture in brainstorm 15 before making the
  embeddings asset public (tentatively fine under CC BY-SA data since they're derived).

Nothing about this placement is affected by the split at all: Postgres/embeddings are entirely
a KB-repo concern; the site consumes the bundle, not the database.

### 1h. Verdict

**The split does not meaningfully hurt CI — provided the website consumes a versioned
validated artifact rather than the KB repo's files.** Concretely:

- Real costs: one cross-repo token to manage; one bundle format to define and version (mostly
  needed anyway); breaking schema changes need two sequenced deploys instead of one commit;
  total fact→live latency is two pipelines instead of one (minutes either way).
- Real benefits: agents can never touch deploy credentials; the site can never build from
  unvalidated data; KB file layout can evolve freely; issue trackers separate (the owner's
  goal); rollback of the site to any `data-vN` is a one-parameter rebuild.
- The one configuration to actively avoid: submodule or HEAD-checkout coupling, which imports
  every monorepo downside (tight file-layout coupling, duplicated validation) while keeping
  every split downside. If the artifact pattern were rejected, the split *would* hurt, and the
  honest fallback recommendation would be checkout-at-last-green-SHA.

## (2) The pipeline

### KB repo pipeline (on every push to `main`)

```
push to main
  └─ 1. fast-validate      YAML parse, JSON Schema, normalizer idempotency (fail = red main)
  └─ 2. integrity          referential integrity (edges/instances/citekeys resolve),
                           dimension-exclusivity + hard-conflict rules, ID determinism
  └─ 3. citation checks    citekey→sources/ resolution, locator format; NETWORK link-check is
                           NOT here — it runs on a daily schedule (flaky-network failures must
                           not redden data commits; it opens issues instead)
  └─ 4. compile            YAML → canonical bundle (dataset + graph + schema_version +
                           source manifest + content hash per fact)
  └─ 5. incremental embed  restore hash-keyed cache → embed only changed facts (university
                           API) → refresh cache
  └─ 6. load + eval        Postgres service container ← bundle; golden-set Recall@5/MRR gate
  └─ 7. publish            release assets: bundle + embeddings parquet; move `latest-green`
                           tag; cut `data-vN` on schema bumps or on a daily rollup
  └─ 8. dispatch           repository_dispatch → site repo {tag, sha, schema_version}
```

Determinism: steps 1–4 must be byte-stable given the same tree (already a D11 CI requirement);
step 5 is cache-stable given (content hash, model id); pin the embedding model id in the bundle
manifest so a silent university-side model swap is detectable.

### Site repo pipeline

`repository_dispatch` (or daily cron, or push to site `main`) → download bundle at the given
tag → assert `schema_version` in supported range → Astro build → deploy (Pages/Cloudflare) →
stamp the deployed site with `{data tag, kb sha}` in a build-info footer/meta so "what data is
live?" is always answerable. **Rollback** = re-run the deploy workflow with a previous
`data-vN` input (`workflow_dispatch` with a tag parameter) — no git surgery in either repo.

### Direct agent commits × CI failure (no PR gate)

With no PR gate, `main` *can* go red. Three-layer answer, ordered by where failures should die:

1. **Pre-commit gate in the agent runner (primary defense).** The runner runs the *exact same*
   steps 1–3 (the fast, offline subset — target < 5 s, no network) via one command
   (`just validate`, shared code with CI, not a reimplementation) before every commit, and
   simply refuses to commit on failure — the agent gets the validator output and retries.
   This is the D4 verification gate's mechanical sibling and should stop ~all failures.
   Also install it as a plain `pre-commit` hook so the owner's manual edits get the same gate.
2. **Last-green publication semantics (containment).** Downstream (bundle, Postgres, site)
   is only ever produced from a *green* commit; a red `main` publishes nothing and the world
   keeps serving the previous green state. Red main is therefore an internal work-queue item,
   not an incident. This property falls out of the artifact pattern for free.
3. **Failure bot (repair).** On red main: open a KB issue with the validator output and the
   offending commit(s); if the failure is attributable to the tip commit and reverting it makes
   the tree green (checked mechanically — revert in a temp branch, re-validate), auto-push the
   revert and note it in the issue; otherwise (interleaved agent commits, bisect ambiguity)
   leave main red, halt the agent runner (it must check "is main green?" before starting new
   work), and page the owner. No quarantine branch: a staging branch that agents write to with
   auto-promotion-on-green is equivalent to last-green semantics but adds a second ref to
   reason about; skip it unless concurrent-agent push contention (below) becomes real.

Concurrency note: two agent runners pushing to `main` race on non-fast-forward; the runner
needs a fetch-rebase-retry loop. One-fact-per-file (07 §F) makes textual conflicts near-zero;
*semantic* conflicts (two agents editing related facts) are the reconciler's job (D5), not
git's. If runners multiply, revisit a lightweight commit queue — new brainstorm topic below.

### Local dev story (docker compose)

- KB repo: `docker compose up -d` (postgres+pgvector, volumes for data + embedding cache) →
  `just bootstrap` (download latest embeddings asset → compile → load → embed deltas) →
  `just validate` / `just rebuild` in the loop; MCP server points at local Postgres. CI-parity
  guaranteed because CI calls the same `just` targets.
- Site repo: `just dev` defaults to downloading `latest-green`, but honors
  `HERMES_BUNDLE=../hermes-kb/build/dataset.json` to point at a local KB working copy — the
  one place raw cross-repo file coupling is allowed, because it's a human dev loop, not CI.

## (3) Repo boundary proposal

**Two repos, not three.**

- **`hermes-kb`** (the knowledge-base-management repo — data *and* the machinery that manages
  it): `schema/` (authoring schemas), `sources/`, `features/`, `languages/`, `instances/`,
  `edges/`, `rules/` (exact granularity per C13), `pipeline/` (validate/compile/embed/load,
  prompts-as-code), `agents/` (sweep, debate, reconciler, verifier runners), `mcp/` (read-only
  server, D8), `eval/` (golden set), `compose.yaml`, `.github/workflows/`. Its issue tracker
  receives fact challenges (D9 prefilled forms point here) and pipeline/agent bugs.
- **`hermes-site`**: Astro site, design system, JSON-LD emitters, bundle reader, deploy
  workflow. Its issue tracker receives website bugs/UX issues only.

Why no third pipeline/tooling repo: the pipeline versions in lockstep with the authoring
schema — splitting them manufactures version skew between validator and data with zero
consumer besides the KB repo itself. The owner's motivation for splitting (separate issue
trackers) is fully satisfied by two repos; "knowledge-base management" naturally includes the
agents and pipeline that manage it. Extract a tooling repo later only if a second data corpus
ever wants to reuse the pipeline. Two nuances: (a) agent chat logs (D1) are volume-unbounded
and should *not* bloat `hermes-kb` — park them as release assets or a dedicated logs repo,
final call in brainstorm 24; (b) `context/` (this brainstorm corpus) lives in `hermes-kb` as
the project's brain.

## Recommendation

1. Adopt the **validated-dataset-artifact pattern**: KB CI publishes a compiled bundle +
   embeddings cache as GitHub Release assets (`latest-green` rolling tag, `data-vN` immutable
   tags) on every green push to `main`; this is the only interface the site consumes.
2. Cross-repo trigger via `repository_dispatch` using a fine-grained GitHub App/PAT, with a
   daily scheduled site rebuild as fallback; deploy workflow accepts a `data-vN` parameter for
   one-click rollback.
3. Agent-commit safety = same-code pre-commit gate in the runner (fast offline subset) +
   last-green publication + a failure bot that auto-reverts only mechanically-safe tip commits
   and otherwise halts the runner and files an issue. Network link-checking runs on a schedule,
   never on data pushes.
4. Postgres + embeddings remain wholly inside `hermes-kb` (local compose for real use, service
   container in CI as a smoke/eval gate); embeddings distributed as release assets, never in
   git.
5. Two repos as proposed; no third tooling repo; agents get a GitHub App identity.

**Direct answer to the owner: the split does not hurt CI in any way that matters, *conditional
on* artifact-based consumption. Its one genuine cost is that breaking schema changes need two
sequenced deploys instead of one atomic commit — a few times a year, ~30 minutes each. In
exchange it buys a hard security boundary (agents never near deploy credentials) and a hard
quality boundary (the site can only ever build from validated data).**

## Open questions for the owner

1. **Bundle format & channel**: one JSON/JSONL bundle on GitHub Releases OK, or preference for
   a package registry from day one? (Recommendation: Releases; migration later is cheap.)
2. **Public embeddings asset**: comfortable publishing the embedding cache (derived from the
   CC BY-SA corpus, university-hosted model outputs) as a public release asset? If not,
   contributors re-embed locally via… what API access? (Interacts with brainstorm 15.)
3. **GitHub App vs PAT** for (a) cross-repo dispatch and (b) the agent-runner commit identity —
   is the owner willing to register a GitHub App (one-time ~30 min, cleaner), or prefer PATs?
4. **`data-vN` cadence**: immutable tag per green push (noisy), daily rollup, or only on
   schema bumps? Affects how precisely "the site as of last Tuesday" can be reproduced.
5. **Red-main policy confirmation**: is "halt the agent runner while main is red, owner fixes
   non-trivial breakage" acceptable, given the no-owner-bottleneck posture of D1? (It should be
   rare — the pre-commit gate catches the mechanical failures — but it is an owner-serialized
   path.)
6. Should the deployed site visibly display its `data-vN` build stamp (transparency win, minor
   design-chrome cost against D10's clean aesthetic)?

## New brainstorm topics surfaced

- **Dataset bundle contract design** — exact format, schema_version semantics/compat ranges,
  manifest fields (embedding model id, source snapshot hashes); consumed by site, Postgres
  loader, MCP; interacts with C13 file granularity.
- **Agent-runner commit protocol** — fetch-rebase-retry loop, machine identity, batching per
  commit, `is-main-green` gating, and a commit queue if concurrent runners materialize
  (extends D5/07-§F).
- **Failure-bot design** — mechanical-safety criteria for auto-revert, bisect strategy for
  batched agent pushes, issue templates, halt/resume signaling to the runner.
- **Link-checker service design** — scheduled network checks, caching, Wayback fallback
  swap-in, and how link-rot findings become work-queue items instead of red builds (feeds D3).
- **Site preview environments** — whether `hermes-site` PRs (human-authored, site-only) get
  preview deploys with the latest-green data, and whether KB schema bumps get a paired preview.
