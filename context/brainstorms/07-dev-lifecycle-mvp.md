# 07 — Developer Lifecycle & MVP Scoping

Owner profile: solo developer, proof-of-concept MVP, Claude Code Pro (session/usage limits), no
GPU, fairly slow university-hosted model API. Everything below is optimized for that reality:
minimize burn, maximize the number of cheap "is this working?" checkpoints, and never let an
agent pipeline run unattended against the expensive resource.

## Problem framing

Project Hermes as described in the brief is at least five products (knowledge base, builder,
selector, forum/challenge flow, agent debate system). A solo dev on Pro limits cannot build all
of them, and — more importantly — doesn't need to in order to *prove the concept*. The concept
that actually needs proving is a single chain:

> **Agents can produce structured, sourced facts about programming-language features → those
> facts survive validation → they are retrievable by other agents (RAG via MCP into Claude
> Code) → they are presentable to humans with citations → a human can challenge any fact.**

If any link in that chain fails, the builder and selector are moot. If the whole chain works
for even a tiny N×M matrix, everything else is "just" scale-up and UI. So the MVP question is
not "which modules to build" but "what is the thinnest end-to-end traversal of that chain."

The second framing problem is **budget shape**. Claude Code Pro is limited per-session and
per-week; the university API is slow but effectively unmetered (or at least not the same
scarce resource). Knowledge-population is a high-volume, medium-judgment task; system
development and fact adjudication are low-volume, high-judgment tasks. The lifecycle must
route each workload to the right resource, and must never re-do expensive work (idempotency,
caching, diffability).

Third: a solo dev has no reviewer. The substitute for a reviewer is (a) CI that mechanically
checks data quality, and (b) git diffs of human-readable fact files so the owner can eyeball
what an agent run actually changed. This pushes hard toward "facts as files in git" (brief
option 5a) at least for the MVP.

## Options with trade-offs

### A. Size of the vertical slice (pick N languages × M features)

| Option | N × M | Pros | Cons |
|---|---|---|---|
| A1: Micro | 2 × 3 | Cheapest; done in days | Too small to exercise cross-language disagreement or the "conflicts/alternative-to" edges; graph is trivial; doesn't feel like a proof |
| A2: Small-diverse (recommended) | 3 × 5 | Enough diversity to force real modelling decisions; ~15 feature-instance cells + ~5 feature nodes is one afternoon of agent runs; still fully reviewable by hand | Some Notion layers (design choices, emergent interactions) only lightly touched |
| A3: One-layer-complete | 5 × 12 (all "design choices" for 5 langs) | Exercises the mutually-exclusive layer properly | ~60 cells; review burden explodes before the pipeline is trusted; burns budget on content before validating the pipe |

Concrete recommendation for A2 — chosen to maximize *disagreement surface* per cell:

- **Languages (N=3): Python, Rust, Haskell.** Dynamic/impure vs. ownership/systems vs.
  lazy/pure. Nearly every feature manifests differently in all three, so agents must actually
  model, not copy-paste. (Runner-up 4th if budget allows: JavaScript, for the "messy
  mainstream" case.)
- **Features (M=5):**
  1. *Pattern matching* (semantic feature; recent + contested in Python — good citation test)
  2. *Algebraic data types* (semantic; exercises the `influences` edge to pattern matching)
  3. *Memory management* (design choice; exercises `alternative to` — GC ↔ ownership)
  4. *First-class functions* (semantic; has sub-abilities → tests schema nesting)
  5. *Evaluation strategy* (design choice; eager vs. lazy — exercises mutually-exclusive
     modelling and Haskell's oddness)

This 3×5 slice touches: both feature layers (semantic + design choice), at least three edge
types (requires/influences/alternative-to), syntax-vs-functionality separation, and per-cell
citations. That is the whole conceptual model in miniature.

### B. Which Notion modules defer entirely

- **Defer entirely (not even stubs):** Language Builder, Public Language Library, Language
  Selector, upvote/usage ranking, TIOBE statistics, "THE CODE" preview, private feature
  definitions, custom forum module (option 5b), comments. None of these test the fact chain.
- **Defer as modules but keep as schema affordances:** similarity edges,
  required/impossible-combination validation — represent them as *edge types in the schema*
  now (cheap), build no UI/logic on them (expensive).
- **Keep, minimal form:** knowledge base (facts + sources), one feature page + one language
  page on the static site, per-fact source link, per-fact "Challenge this" link → a GitHub
  Discussion (option 5a; zero code), MCP retrieval endpoint.

Trade-off note: deferring the builder removes the "usage rate" ranking signal the Notion page
leans on. That's fine for MVP — ranking is meaningless with one user anyway — but record it as
a known schema gap (facts have no popularity field yet).

### C. Where knowledge-population runs

| Option | Pros | Cons |
|---|---|---|
| C1: Everything on Claude Code interactively | Best quality; single toolchain | Burns Pro limits on bulk drafting; owner becomes a babysitter; unrepeatable |
| C2: Everything on university API, scripted | Free-ish, repeatable | Slow model likely produces weaker citations & schema violations; more retry loops; MCP/agent-debate quality suffers |
| C3: Split by judgment level (recommended) | Each resource does what it's good at | Two model integrations to maintain; needs a provider-agnostic pipeline layer |

C3 concretely:
- **University API (scripted, headless, overnight-tolerant):** first-draft fact extraction per
  (language, feature) cell from named sources; syntax snippet drafting; source metadata
  (CSL-JSON/BibTeX-ish) extraction; embedding generation if the university hosts an embedding
  model (else use a small local CPU embedding model — no GPU needed for e.g. bge-small /
  all-MiniLM via sentence-transformers on CPU at this scale).
- **Claude (interactive or short headless `claude -p` runs, budget-capped):** schema design;
  adjudicating conflicts between drafted facts; the "expert agents argue" debate step (this is
  the high-judgment core — do it on the strong model, but only on the 15-cell slice); final
  editorial pass; all *system development*.
- Rule of thumb: **Claude never does volume; the university API never has the last word.**
  Every university-API output passes mechanical validation (CI checks below) and then a
  cheap Claude adjudication pass before merging.
- Headless Claude runs (`claude -p` / Agent SDK scripts) are fine for the adjudication pass,
  but keep them *small and resumable*: one (language, feature) cell per invocation, output to
  a file, so a hit usage limit mid-run loses one cell, not the batch.

### D. Repo layout

| Option | Pros | Cons |
|---|---|---|
| D1: Monorepo (recommended) | One clone, one CI, atomic commits across schema+facts+site; right for solo dev | Repo mixes data and code (acceptable at MVP scale) |
| D2: Separate facts repo + code repo | Clean fact-diff history; facts repo is the future public contribution surface | Cross-repo sync ceremony a solo dev will hate; premature |
| D3: Facts only in vector DB, no files | No sync problem | Kills diffability, challengeability, and the git-based review workflow — directly contradicts brief item 5a |

D1 sketch (split into D2 later only if outside contributors materialize):

```
hermes/
  context/            # brainstorms, CLAUDE.md sources (already exists)
  schema/             # JSON Schema (or similar) for facts, sources, edges
  facts/              # human-readable canonical truth (YAML/JSON), one file per node
    features/pattern-matching.yaml
    languages/rust.yaml
    instances/rust--pattern-matching.yaml     # deterministic ID = lang--feature
    edges/adt--influences--pattern-matching.yaml
  sources/            # CSL-JSON entries, one per source, keyed by citekey
  pipeline/           # extraction, adjudication, embedding, load-to-vector-store scripts
    prompts/          # versioned prompt templates (they ARE source code here)
  index/              # vector store build artifacts (gitignored) + MCP server
  site/               # static site generator reading facts/ directly
  .github/workflows/  # CI: schema + citation checks on every PR
```

Key principle: **`facts/` + `sources/` are the database.** The vector store is a derived,
rebuildable index (like a lockfile you can regenerate) — never edited directly, always
rebuilt from files. This dissolves the brief's "GitHub vs production DB sync" worry for the
MVP: there is no production DB to sync; the site and the index are both compiled from git.

### E. Testing strategy

| Option | Pros | Cons |
|---|---|---|
| E1: Heavy unit tests on pipeline code | Traditional rigor | Pipeline code is glue that changes weekly; tests rot; wrong risk focus |
| E2: Data-quality CI as the primary suite (recommended) | Guards the actual asset (facts); cheap; runs on every agent PR | Doesn't catch pipeline logic bugs directly — but bad data output catches them indirectly |
| E3: LLM-judge tests in CI | Catches semantic nonsense | Costs model budget per CI run; non-deterministic; save for a manual pre-release pass |

E2 concretely, in rough order of value:
1. **Schema validation** — every file in `facts/` and `sources/` validates against `schema/`.
2. **Referential integrity** — every citekey referenced by a fact exists in `sources/`; every
   edge endpoint exists; every feature instance references a real language and feature.
3. **Citation integrity** — every source has a resolvable locator (URL 200-check, cached and
   rate-limited; DOI format check; page/section locator present for books like Van Roy &
   Haridi). Optional stretch: verify quoted strings appear in the fetched source text.
4. **Coverage matrix** — a generated N×M report showing which cells are filled/empty/stale;
   fails CI only on regressions (a cell losing its source).
5. **Determinism check** — rebuilding the vector index and site from `facts/` is byte-stable
   (or at least idempotent), proving files are truly canonical.
6. A handful of unit tests only where logic is genuinely tricky (ID generation, edge
   validation). Everything else is E2.

### F. Iteration hygiene (idempotent, diffable agent runs)

- **Deterministic identity:** fact/edge IDs derived from content keys (`rust--pattern-matching`),
  never from run timestamps or model output. Re-running a cell overwrites the same file path →
  `git diff` shows exactly what the model changed its mind about.
- **Agent runs land as branches/PRs, not direct commits.** A headless run's entire output is
  one diff the owner reviews like a code review. CI (section E) runs on the PR. This *is* the
  review process — no separate QA phase.
- **One cell per invocation, resumable batches:** the batch driver skips cells whose file
  exists and is newer than the prompt template + source list (make-style staleness). Interrupted
  runs (usage limits, slow API timeouts) resume for free.
- **Prompts are versioned code** in `pipeline/prompts/`; each generated fact file records
  `generated_by: {model, prompt_version, run_date}` in metadata so diffs are attributable and
  stale cells (old prompt version) are findable.
- **Normalize before commit:** sort keys, wrap text, canonical YAML formatting via a formatter
  in the pipeline — otherwise every re-run produces noisy whitespace diffs that hide real changes.
- **Never let agents edit derived artifacts** (index, site output); they're gitignored or
  build-only, so a bad run can always be discarded by deleting the branch.

## Recommendation (phase plan)

Each phase ends at a **checkpoint where the owner validates before more budget is burned**.
Phases are ordered so the cheapest-to-fail things fail first.

**Phase 0 — Schema & skeleton (Claude Code interactive; ~1–2 sessions).**
Define fact/source/edge schemas, repo layout above, ID convention, formatter, and the CI
schema+integrity checks. Hand-write ONE complete cell (e.g. `rust--pattern-matching`) with
real citations as the golden example that all prompts and validators are tuned against.
→ *Checkpoint 0: owner reads the golden fact file and says "if the whole KB looked like this,
I'd be happy." If not, iterate here — this is the cheapest place to change your mind.*

**Phase 1 — Pipeline dry run on university API (scripts; near-zero Claude budget).**
Build the extraction script (provider-agnostic HTTP client so Claude/uni-API/local are
swappable). Run it on 3 cells. Expect schema violations; tighten prompts/validators until the
slow model passes CI mechanically.
→ *Checkpoint 1: 3 university-API-drafted cells pass CI. Owner reviews the diffs: is draft
quality "fixable by adjudication" or "garbage"? If garbage, fallback: drafting moves to
headless Claude for the 15-cell slice only (small enough to afford), and the uni API is
demoted to embeddings/link-checking.*

**Phase 2 — Populate the 3×5 slice + Claude adjudication (mixed).**
University API drafts all 15 cells + 5 feature nodes + ~6 edges overnight. Short headless
Claude runs adjudicate each cell (fact-check against cited sources, resolve, flag). The
"expert agents argue" idea is piloted here in its minimal form: one Claude debate over ONE
contested cell (suggested: "does Python have real pattern matching or sugar?") to see if
debate output is worth its cost.
→ *Checkpoint 2: full 3×5 matrix green in CI; owner spot-checks 5 random citations by hand.
Also: verdict on whether multi-agent debate earns its budget or a single critique pass suffices.*

**Phase 3 — Index + MCP (Claude Code interactive; ~1–2 sessions).**
Build vector index from `facts/` (CPU embeddings; chroma/sqlite-vec/LanceDB class of tool —
embedded, no server to run). Wrap in a minimal MCP server exposing `search_facts` /
`get_fact_with_sources`. Connect to the owner's own Claude Code.
→ *Checkpoint 3: the demo — owner asks Claude Code "compare memory management in Rust and
Python, with sources" and gets an answer grounded in Hermes facts with citekeys. This is the
proof-of-concept moment for the agent-facing half.*

**Phase 4 — Static site slice (Claude Code interactive; 1–2 sessions).**
SSG (Astro/Eleventy/Zola class) reading `facts/` directly. Pages: 1 feature page (pattern
matching across 3 languages, syntax previews, citations), 1 language page (Rust with its 5
features), each fact with source link + "Challenge this" → auto-created GitHub Discussion link.
No search, no ranking, no builder.
→ *Checkpoint 4: owner (and ideally one outside programmer) reads the two pages; can they find
the source of any claim in ≤2 clicks and see how to challenge it? This is the proof for the
human-facing half.*

**Phase 5 — Retrospective & scale decision (cheap, mostly human).**
Write down per-cell cost (Claude budget + wall-clock), measured quality, and what broke.
Decide: scale to more languages/features, or pivot (e.g., quality demands more human curation
than expected). Only after this does builder/selector planning re-enter the conversation.

Budget posture throughout: interactive Claude Code sessions for Phases 0/3/4 and adjudication
prompt-tuning; university API for all volume; headless Claude only in Phase 2, cell-by-cell,
resumable. Nothing in the plan requires a GPU or a hosted server (site is static, index is
embedded, MCP server runs locally).

## Open questions for the owner

1. **University API capabilities:** which models, context window, rate limits, and — crucially —
   does it host an *embedding* model? (Determines whether embeddings run there or on local CPU.)
2. **Is 3×5 (Python/Rust/Haskell × the 5 features above) acceptable as the proof slice**, or is
   there a language/feature the owner considers non-negotiable for credibility (e.g., a logic
   language for the paradigm axis)?
3. **Citation depth bar for MVP:** is "URL + section locator" enough, or must every fact carry a
   verbatim quote from the source? (Quote-verification is the most expensive CI check.)
4. **Where do GitHub Discussions live** — this repo, or a future public `hermes-facts` repo? The
   challenge links baked into the site depend on this choice being stable-ish.
5. **How much is the multi-agent debate part of the thesis?** If the debate mechanism itself is
   a research goal (not just a quality tool), Phase 2's one-cell pilot should be expanded and
   instrumented (logs kept as data) even at extra cost.
6. **Weekly Claude budget the owner is willing to allocate to Hermes** vs. other work — decides
   whether Phase 2 adjudication is headless Claude or done interactively over more days.
7. Any hard **deadline** (thesis/demo date)? The phase plan compresses by cutting Phase 4 to one
   page, not by skipping checkpoints.

## New brainstorm topics surfaced

- **Provider-abstraction layer design** — the minimal interface that lets extraction/adjudication
  swap between Claude, university API, and future local models (incl. handling wildly different
  context windows and JSON-mode reliability).
- **Golden-example-driven prompt engineering** — methodology for tuning extraction prompts
  against one hand-written perfect fact file; regression-testing prompts when they change.
- **Fact staleness & re-verification lifecycle** — languages evolve (Python got pattern matching
  in 3.10); when and how are cells marked stale and re-run, and what does "fact versioning"
  look like in git-canonical data?
- **Cost/quality instrumentation of agent debate** — how to measure whether N-agent debate beats
  a single critique pass (needed for Phase 2's verdict and possibly the academic write-up).
- **Contribution funnel design for the post-MVP public repo** — templates for GitHub Discussions
  challenges, how an accepted challenge becomes a fact-file PR, and how CI gates community edits.
- **Coverage-matrix as product** — the N×M fill-state report could itself be a public site page
  ("help wanted: Haskell effect handlers"), doubling as contributor recruitment.
