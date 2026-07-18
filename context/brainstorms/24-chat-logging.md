# 24 — Agent Chat Logging & Publishing

> Round-2 brainstorm for Project Hermes. Topic: logging every agent chat (D1), the optional
> "AI chat" link on each published fact, and whether/how past debates should become a
> searchable corpus for agents. Binding context: D1 (all chats logged, facts optionally link
> to them; no PR gate; split public repos), D4 (agent text is never citable), D5 (provenance
> carries debate/run IDs), D6 (shared provider wrapper), D8 (public MCP is read-only),
> D10 (Astro static site).

## 1. Problem framing

Three distinct deliverables hide in "log every chat":

1. **Capture** — reliably producing a transcript for every agent interaction across pipeline
   stages (sweeps, verification, reconciliation, debates, challenge re-argument sessions, and
   the frontloaded research phase of D11), in one normalized format.
2. **Publishing** — storing transcripts publicly and cheaply, and rendering a chat from a
   fact page via a stable link ("show me the conversation that produced this fact").
3. **Retrieval for agents** — optionally making the debate/argument history searchable by the
   pipeline itself ("has this been debated before?"), without violating D4's wall between
   agent prose and citable knowledge.

Key asymmetry from brainstorm 04's reframe: the *structured residue* (claims, typed
challenges, resolution blocks, contradiction records) is the product; transcripts are the
**audit trail**. So transcripts must be complete, immutable, and inspectable — but they never
need to be queryable for the site to work. That ordering drives every recommendation below:
capture is load-bearing (it can't be retrofitted for past runs), rendering and retrieval are
layerable later.

A second framing point: capture is *cheap insurance*. If a fact is ever challenged (D9), the
transcript answers "what was the agent thinking?" — this is the project's transparency story
("every fact traceable to its source *and* to the reasoning that filed it"), and a genuine
differentiator vs PLDB-style databases (risk P1).

## 2. Options with trade-offs

### 2.1 Capture: where transcripts come from

Every pipeline stage's LLM traffic passes through one of two funnels:

**Tap A — the shared provider wrapper (D6).** The wrapper already exists conceptually for
throttling, caching, and cost logging. Extending it to persist full request/response message
lists is the natural tap: one code path covers university-API roles (verification,
entailment, bulk drafting, embeddings) *and* scripted Claude calls, with zero per-stage
effort. Anything the wrapper caches by `(model, prompt-hash)` should still log the logical
call (with a `cache_hit: true` marker) so transcripts stay complete.

**Tap B — Claude Code sessions.** Interactive and headless (`claude -p` / Agent SDK) sessions
don't go through the wrapper. Claude Code already writes session transcripts as JSONL under
`~/.claude/projects/<dir>/`; a post-run step in each pipeline script copies the session file
and converts it to the normalized format. For headless SDK runs, the SDK surfaces the message
stream directly — the orchestrator writes it out itself. Owner's *interactive design
sessions* are a policy question (see §4) — pipeline runs are unambiguous.

There is no credible third option ("agents self-report their transcript") — self-reporting is
exactly the kind of thing an agent forgets or summarizes; capture must be infrastructural.

**Normalized format.** One run = one directory:

```
<run_id>/
  manifest.yaml     # who/what/why — small, greppable
  transcript.jsonl  # the chat itself, one event per line
```

- `transcript.jsonl` event: `{seq, ts, role (system|user|assistant|tool), agent (persona id),
  model, content, tool_call {name, args} | null, tool_result_ref | inline, tokens_in/out}`.
  JSONL because runs are append-only streams, line-diffable, and trivially parseable by the
  viewer and by any embedding job.
- `manifest.yaml`: `run_id, kind (sweep | debate | verification | reconcile | research |
  challenge), languages/cells touched, debate_id | null, agents [{persona, model,
  prompt_version}], started/ended, wrapper_version, resulting_fact_ids [], redaction
  {status, rules_version}, files []`.
- **ID scheme:** `run_id = <date>-<kind>-<slug>-<seq>` (e.g. `2026-08-02-debate-rust-ownership-01`).
  D5's `debate_id` maps 1:1 to a run; sweeps are one run per language batch. Fact provenance
  already stores `debate_id` — add optional `chat_run_id` for non-debate origins, and the
  fact→chat link is fully derivable.

Resulting-fact back-references are written by the orchestrator *after* verification (the run
ends before fact acceptance is known), so the manifest is finalized by the pipeline stage
that commits facts — a small but important sequencing detail.

### 2.2 Storage & size

**Size reality check.** A debate is ≤6 messages (D5) plus tool traffic: ~20–100 KB raw. A
per-language sweep touching a few hundred features with retrieval calls: ~1–5 MB. Overnight
verification batches: a few KB per claim × hundreds of claims = low MBs per batch. The
frontloaded research phase (D11) will be the biggest producer — call it tens of MB. Realistic
first-year total: **hundreds of MB of plain text, ~5–10× smaller gzipped**. Voluminous for a
content repo, trivial for infrastructure.

Options:

**A — transcripts inside the KB repo.** Rejected. It bloats every contributor clone, pollutes
the KB repo's diffs and issue tracker (the repo split in D1 exists precisely to keep concerns
separate), and violates the "no bulky non-canonical data" hygiene of D1 — transcripts are
evidence *about* the process, not canonical knowledge.

**B — dedicated public transcripts repo, plain files.** `hermes-transcripts`, sharded
`transcripts/YYYY/MM/<run_id>/`. Pros: free, public, inspectable, forkable, `git log` is the
tamper-evidence story, raw.githubusercontent.com serves files to the viewer at no cost,
shallow/partial clone (`git clone --filter=blob:none`) keeps local checkouts light. GitHub's
soft repo ceiling (~5 GB) gives years of headroom; if ever hit, shard by year
(`hermes-transcripts-2027`). Cons: none serious at this scale.

**C — git LFS.** Rejected: LFS bandwidth/storage quotas cost money past the free tier
(violates the no-cash budget), breaks raw-URL serving, and adds contributor friction — all to
solve a size problem we don't have. Transcripts are text; git already handles them.

**D — object storage (S3/R2) + static hosting.** Rejected for v1: costs cash or ties to a
provider, loses the git audit trail, less inspectable ("public, inspectable, cheap" — B wins
on all three).

**E — compile transcripts into the website build.** Rejected as *storage*: it couples site
build time to an ever-growing corpus and stuffs MBs into the site repo. But a thin version of
this is right for *rendering* — see §2.3.

**Recommendation: B.** Plain JSONL in a dedicated public repo, committed per-run by the
pipeline (each run = one commit, message = run_id — the git history doubles as a run log).
Optionally gzip transcripts over ~1 MB (`transcript.jsonl.gz`) — the viewer can inflate
client-side via `DecompressionStream`, which is standard in all evergreen browsers.

### 2.3 Linking & rendering: fact → chat viewer

**URL scheme.** On the website: `/chats/<run_id>/` (optionally `#msg-<seq>` deep links to the
message that filed the claim). Each fact's citation popover (D10) gains a quiet secondary
link — "AI chat" — next to "Challenge this fact", present only when `chat_run_id`/`debate_id`
is set. The fact page never *depends* on the transcript; it is an optional provenance layer.

**Rendering options:**

- **Raw GitHub link (v0).** `href` straight to the file in the transcripts repo. Zero effort,
  fully honest, ugly. Acceptable as a stopgap the day logging starts, before the viewer exists.
- **Static viewer page with client-side fetch (recommended v1).** One Astro island at
  `/chats/[run_id]` — a small JS component that fetches `manifest.yaml` +
  `transcript.jsonl(.gz)` from the transcripts repo's raw URL and renders roles, collapsible
  tool calls, and timestamps. Fits D10 (islands are allowed off the zero-JS KB pages), keeps
  the site build independent of transcript volume, and keeps the transcripts repo out of the
  KB repo's concerns. Chat pages get `noindex` — they are provenance, not SEO surface, and
  thin-content chat dumps would dilute the site's search profile.
- **Build-time rendered chat pages.** Prettier and JS-free, but couples site builds to the
  transcript corpus and rebuild time grows forever. Not worth it; revisit only if the
  client-side viewer proves annoying.

**Redaction (decide before the first published run, because transcripts are immutable):**

- **Secrets:** the wrapper logs *message content only* — auth headers, keys, and endpoint
  config never enter the transcript by construction. Add a belt-and-suspenders regex scrub
  (key-shaped strings, bearer tokens) + a CI secret-scan (gitleaks) on the transcripts repo
  before push; a leak in a public immutable log is the one unrecoverable failure here.
- **System prompts: publish them.** Prompts are versioned artifacts in the KB-management repo
  anyway (D5 provenance records `prompt_version`); hiding them would undercut the
  transparency story. The manifest's `prompt_version` links transcript to prompt file.
- **Tool noise / fetched source text:** the real problem is **copyright, not noise** —
  retrieval and fetch results can embed large verbatim excerpts of copyrighted sources
  (Van Roy & Haridi, specs). Policy: tool results above a threshold (~1–2 KB) are truncated
  in the *published* transcript to a head-excerpt + content hash + `source_id`/snapshot
  reference; the full text lives only in the private snapshot store (D4). This also keeps
  transcripts readable. Record `redaction.rules_version` in the manifest so the policy is
  auditable per-run.
- **Rendering safety:** transcripts contain arbitrary fetched web text (prompt-injection
  surface, brainstorm 04 §5). The viewer renders content as escaped plain text/code — never
  interprets embedded HTML or follows embedded instructions. Same rule for any future
  agent-side consumption (§2.4).
- **Mistake escape hatch:** the transcripts repo is append-only *by policy*, but the owner
  retains the right to force-push a redaction fix (secret leaked, copyright complaint). Note
  the amendment in a `REDACTIONS.md` log so the audit trail acknowledges the rewrite.

### 2.4 Retrieval over chat history for agents

**Is it beneficial?** Genuinely, in three places:

1. **"Has this been debated before?"** — before opening a new debate on a cell, the
   orchestrator/moderator checks for prior debates on the same cell or a sibling
   (`alternative-to` features, same dimension). Avoids re-litigating settled arguments and
   gives the moderator the prior resolution as context.
2. **Argument dedup** in challenge handling (D9): when a human challenge arrives, the
   re-arguing session benefits from "these three counterarguments were already raised and
   answered in debate X".
3. **Process introspection**: which challenge types keep recurring on a feature → schema
   smell (already envisioned in brainstorm 04, but retrieval makes it queryable).

**But first-line retrieval should be the *structured residue*, not raw transcripts.** D5
already records resolutions as structured blocks, contradictions as first-class records, and
debates keyed by cell. An exact-key lookup ("prior debates for cell (rust, ownership)") plus
FTS over resolution summaries covers cases 1–2 for near-zero cost and with zero D4 risk.
Raw-transcript semantic search is a *second-line* nicety for the long tail ("someone argued
something like this in a different cell's debate").

**The D4 wall.** Agent text is never citable; therefore debate-history retrieval must be
impossible to confuse with fact/source retrieval:

- **Separate index**: a distinct `chat_chunks` table (pgvector) — never mixed into the
  fact/source embedding space, never reachable by the same query path. Chunking: one chunk
  per debate turn (a turn is a self-contained argument, typically well under the 40k-token
  window of `qwen3-embedding-4b`), metadata `{run_id, seq, kind, cell, agent, date}`.
- **Separate tool, pipeline-only**: `search_debate_history` exposed only to the internal
  pipeline tooling — **never on the read-only public MCP server (D8)**. Cleanest is a
  separate MCP server (or FastAPI route group) enabled only in the pipeline's environment,
  so a config mistake can't leak it to public consumers.
- **Tagged output**: every returned chunk is wrapped in an explicit banner —
  "NON-CITABLE AGENT TEXT: use for orientation only; any claim must be re-derived from
  sources" — so even a sloppy prompt can't quietly treat a past argument as evidence. The
  source-first gate + verifier (D4) remain the hard backstop: a laundered argument still
  cannot enter the store without a real source.

**Feasibility/cost**: trivially cheap. Embedding is free on the university API; first-year
volume is thousands of turns; indexing rides the same pgvector instance and the same
derived-artifact build (D7) — the index is regenerable from the transcripts repo, so nothing
new is canonical. The only real cost is the segregation discipline, which is a design
decision, not an engineering burden.

## 3. Recommendation

**Capture from day one; publish cheap; render minimal; retrieve later.**

1. **v1 (do with the first pipeline code, ~2–4 days total):**
   - Provider wrapper persists every call; pipeline scripts finalize `manifest.yaml` +
     `transcript.jsonl` per run; Claude Code/SDK runs export their session stream through the
     same normalizer.
   - Dedicated public `hermes-transcripts` repo, `YYYY/MM/<run_id>/`, one commit per run,
     truncation-redaction of large tool results + secret scrub + gitleaks in CI.
   - Fact provenance gains optional `chat_run_id` (debates derive it from `debate_id`); the
     citation popover shows an "AI chat" link — initially pointing at the raw GitHub file.
   - No retrieval index yet; the structured debate/resolution records already answer
     "prior debates for this cell" by exact key.
2. **v1.5:** the `/chats/<run_id>/` Astro island viewer (fetches raw JSONL, collapsible tool
   calls, `#msg-<seq>` anchors, noindex).
3. **v2 (when debates accumulate, likely post-research-phase):** `chat_chunks` pgvector index
   chunked by debate turn, `search_debate_history` as a pipeline-internal tool with the
   NON-CITABLE banner, wired into the debate orchestrator's "prior art" pre-check.

What makes this the right shape: capture is the only part that can't be added retroactively,
so it ships first and everything else is derived and re-buildable — the same one-way
philosophy as D1. Total ongoing cost is near zero (git hosting, free embeddings), and every
layer honors the repo split, the read-only public MCP, and the D4 citability wall.

## 4. Open questions for the owner

1. **Interactive-session publishing scope:** D1 says every *agent chat* is logged — does that
   include the owner's own interactive Claude Code design/dev sessions, or only pipeline runs
   (sweeps, debates, verification, research-phase, challenge re-arguments)? Proposal:
   pipeline runs mandatory; interactive sessions opt-in per session.
2. **Copyright posture for tool results:** is the proposed truncate-to-excerpt+hash policy
   for fetched source text in *published* transcripts acceptable, or should published
   transcripts keep full tool results for maximal transparency (higher copyright exposure —
   overlaps licensing brainstorm 15)?
3. **Verification-run granularity:** overnight verification touches hundreds of claims; log
   one run-per-batch (one big transcript, facts link into it by `#msg-<seq>`) or
   one-run-per-claim (many tiny transcripts, cleaner links)? Proposal: per-batch with
   per-claim anchors recorded in the manifest.
4. **Raw-GitHub-link stopgap:** acceptable as the initial "AI chat" target before the viewer
   exists, or should the link only appear once `/chats/` ships?
5. **Force-push redaction policy:** confirm the escape hatch (history rewrite allowed for
   secret/copyright incidents, logged in `REDACTIONS.md`) — it trades absolute immutability
   for recoverability.

## 5. New brainstorm topics surfaced

- **Pipeline observability dashboard** — the transcripts repo + wrapper cost log together
  contain everything needed for cost-per-accepted-fact, verifier failure rates, and debate
  outcome stats (D6 asks to track these); a small static report page could compile from them.
- **Prompt registry & versioning** — `prompt_version` appears in provenance, manifests, and
  transcripts; where prompt files live (KB-management repo?), how versions are minted, and
  how prompt changes trigger re-evaluation (ties to brainstorm 04's eval-harness topic).
- **Transcript-corpus research value** — a public corpus of structured multi-agent debates
  about programming-language facts is itself a publishable dataset; licensing and citation
  format for the *corpus* (CC BY-SA per D12?) deserves a decision in brainstorm 15.
- **Session-capture tooling for Claude Code** — a small reusable exporter from Claude Code
  session JSONL to the normalized format could be its own utility (and useful beyond Hermes).
