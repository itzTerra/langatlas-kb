# 13 — Provider-Abstraction Layer

> Round-3 brainstorm for LangAtlas. Topic: the minimal interface that lets extraction /
> adjudication / verification work swap between Claude (Claude Code Pro — session-based, not a
> raw API key), the university API (aliases `glm`, `kimi`, `deepseek`, `deepseek-thinking`,
> `mini`, `coder`/`agentic`, `thinker`; embedding + reranker models per D6), and possible
> future local models. Binding context: D6 (Claude does judgment, university API does volume;
> shared wrapper with throttling, backoff, caching, cost caps, cost log,
> cost-per-accepted-fact), D18 (every call logged; one run = `manifest.yaml` +
> `transcript.jsonl`), D15 (embeddings + reranker are pipeline dependencies), D5/D11 (the
> consumers: sweeps, debates, verification, research phase). Surfaced by brainstorm 07 §New
> topics. All proposals below are *proposed* until the developer ratifies.

## 1. Problem framing

The pipeline has two structurally different LLM channels, and the abstraction must not
pretend otherwise:

1. **Claude via Claude Code / the Agent SDK.** The developer's Claude access is a **Pro
   subscription, not an API key**. Claude work therefore runs as Claude Code sessions —
   interactive, `claude -p` headless, or Python Agent SDK `query()` runs. This channel is
   *agentic by nature*: it brings its own tool loop, file access, MCP clients, and session
   transcripts. It cannot be wrapped as a plain `chat()` call without losing exactly the
   things it is used for (judgment work over files and tools). Note the billing landscape
   moves under us: as of mid-2026, headless/SDK runs draw from a pool separate from
   interactive sessions on subscription plans — a fact to track, not to design around.
2. **The university API.** Every alias on the D6 table (`glm-5.2`, `kimi-k2.7`,
   `deepseek-v4-pro[-thinking]`, `gpt-oss-120b`, `qwen3.5-122b`) is an open-weights model of
   the kind universally served by vLLM / SGLang / an OpenAI-compatible gateway (LiteLLM
   proxy, OpenWebUI). An alias table like this **is itself strong evidence of an
   OpenAI-compatible `/v1/chat/completions` + `/v1/embeddings` gateway** — that is how every
   mainstream serving stack exposes named model routing. This is a plausibility judgment,
   not a verified fact; confirming the exact endpoint shape (and whether `/v1/rerank` or a
   TEI/Cohere-style rerank route exists for `qwen3-reranker-4b`) is developer action #1
   below. This channel is *completion-shaped*: stateless request/response, no tools, high
   volume, latency-tolerant.

The trap this brainstorm exists to avoid is the classic one: building a grand
"LLM provider framework" that unifies both channels behind one interface. The channels
should share **policy** (logging, cost accounting, caching, budget caps, prompt identity) but
not **call shape**. D6 already assigns work by judgment level; the abstraction's job is to
make that assignment explicit in code and to guarantee that *no call on either channel can
bypass the D18 transcript or the D6 cost log*.

Scope boundaries: topic 32 owns the prompt registry (only its interface appears here);
brainstorm 24 owns transcript format and publishing (this layer is "Tap A" and the Tap-B
normalizer's caller); brainstorm 11 owns what the verifier checks (this layer only carries
its calls).

## 2. Options with trade-offs

### 2.1 Client technology for the completion channel

**A — LiteLLM (library or proxy).** Pros: 100+ providers, unified params, built-in cost
tracking, retries, proxy mode with spend dashboards. Cons: it is a large, fast-churning
dependency (weekly releases, occasional breaking changes) whose main value — provider
*breadth* — LangAtlas does not need: there is exactly one completion endpoint (the
university gateway), possibly a second (a local Ollama/llama.cpp server), **both already
OpenAI-compatible**. Its cost tables don't know university-internal pricing (effectively
free/quota'd), its proxy mode is a daemon (violates the boring-library preference), and its
logging would have to be bent into the D18 transcript format anyway. Heavy machinery for a
problem that is one `base_url` swap wide.

**B — Plain `openai` Python SDK with `base_url` pointed at the gateway.** Pros: boring,
stable, first-party-maintained, typed; talks to the university gateway, to a local
Ollama/vLLM, and (if ever needed) to any commercial OpenAI-compatible endpoint by changing
one constructor argument; `/v1/embeddings` comes for free. Cons: no built-in multi-provider
routing (not needed), no built-in cost accounting (we must count tokens from the `usage`
field ourselves — which D18/D6 require us to do in our own format regardless), rerank is not
part of the OpenAI spec (a ~20-line `httpx` call whatever client we pick).

**C — Hand-rolled `httpx` client.** Maximum control, zero dependencies of note. But it
re-implements request/response types, retries, and streaming that the `openai` SDK already
does well, for no gain. Worth it only for the rerank endpoint, which is nonstandard anyway.

**Verdict (proposed): B, with C for rerank only.** The `openai` SDK is the transport;
LangAtlas's own thin wrapper (§3) is the policy layer. LiteLLM is rejected as a dependency;
its *proxy* would additionally be a daemon.

### 2.2 Claude channel mechanics

**A — Anthropic API SDK.** Rejected: requires pay-as-you-go API credit; the budget is the
Pro subscription (D6). Revisit only if the project ever acquires API budget.

**B — Claude Agent SDK (Python) for scripted runs + interactive Claude Code for design
work.** The Agent SDK gives programmatic `query()` runs with tool allowlists, MCP config,
system-prompt control, a structured-output option (`output_format` with a JSON schema), and
the full message stream — which is exactly what the D18 Tap-B normalizer consumes.
Interactive sessions produce JSONL under `~/.claude/projects/` that the same normalizer
converts. Pros: uses the subscription; agentic work keeps its tools; transcripts are native.
Cons: session/usage limits mean orchestration must be resumable batch-of-one-cell (already
D11/brainstorm 07 doctrine); model choice is limited to what Claude Code exposes; headless
billing policy is Anthropic's to change.

**C — Route Claude through the same completion interface** (pretend it's an OpenAI
endpoint). Rejected: no raw key, and flattening agentic runs into `chat()` loses tools/MCP —
the reason Claude is in the system.

**Verdict (proposed): B.** Two channel types, one policy layer.

### 2.3 Structured output (JSON) reliability, per model class

The pipeline is overwhelmingly *structured*-output work (claim files, challenge records,
verdicts). Strategies, strongest first:

1. **Schema-constrained decoding** — vLLM/SGLang-backed gateways usually support
   `response_format={"type": "json_schema", ...}` (guided decoding). If the university
   gateway passes it through, malformed JSON becomes near-impossible for all five chat
   aliases. Must be *probed per alias* (feature support varies by serving config), and the
   probe results recorded in the provider config file.
2. **JSON-object mode + validate + bounded retry** — fallback when (1) is absent:
   `response_format={"type": "json_object"}` or prompt-level "output only JSON", then
   `pydantic` validation; on failure, one **repair turn** (feed back the error message), then
   at most one full retry with higher-temperature-zero determinism; then fail the item into
   the run's reject list. Never unbounded retry loops (cost cap, §3).
3. **Reasoning-model caveat** — `deepseek-thinking`/`thinker` emit reasoning traces;
   depending on gateway config the trace may arrive in-band (`<think>…</think>`) or in a
   separate field. The wrapper must strip/segregate reasoning before JSON parsing, and the
   transcript keeps it (D18 logs what the model actually said).
4. **Claude channel** — the Agent SDK's `output_format` json-schema option for SDK runs;
   for interactive work, structured residue is written to files by the agent and validated
   by the same pre-commit validators (D13), so wrapper-level JSON enforcement is not needed
   there.

*Proposed policy:* every structured call site declares a `pydantic` model; the wrapper
negotiates the strongest supported mode per alias (constrained → json-mode+retry) from the
probed capability table; parse failures are first-class logged outcomes, not exceptions
swallowed upstream.

### 2.4 Context-window differences

Windows will differ per alias (order 128k-class for the DeepSeek/GLM/Kimi generation,
smaller for `gpt-oss-120b`; embeddings 40,960 vs 512 tokens per D6 — the embedding gap is
already handled by chunking in D15). The wrapper's job is **not** to auto-truncate — silent
truncation corrupts verification work. *Proposed:* a per-alias `max_input_tokens` entry in
the provider config; the wrapper counts tokens (tokenizer-approximate is fine — a
conservative chars/4 bound with a 10% margin, upgraded to real tokenizers only if it ever
misfires) and **refuses** oversized calls with a typed error; the *call site* decides how to
shrink (drop context, chunk, or route to a bigger-window alias). Routing-by-window stays a
call-site decision, not wrapper magic.

### 2.5 Rate limiting / backoff / throttling

The university API is described as "fairly slow" and shared infrastructure — politeness is a
sustainability requirement, not just robustness. *Proposed:* per-endpoint token-bucket
concurrency (default: low single-digit parallelism for chat, higher for embeddings —
tunable), exponential backoff with jitter on 429/5xx/timeouts honoring `Retry-After`, a
per-call timeout generous enough for reasoning models (minutes, not seconds), and a
circuit-breaker: N consecutive transport failures pause the run and persist a resumable
checkpoint rather than hammering a down service overnight. The Claude channel needs no
client-side throttle (Claude Code self-limits), but the orchestrator must treat
"usage limit reached" as the same *pause-and-checkpoint* outcome.

### 2.6 Response caching

*Proposed:* content-addressed cache keyed by
`hash(endpoint, model_alias → resolved model id, messages, sampling params, schema,
prompt_id@version)` — the resolved model id matters because aliases float (`deepseek` →
whatever v-next the university deploys); a silent upgrade must be a cache *miss*. Storage: a
local SQLite file in the private (non-git) work area — same tier as the D15 snapshot store.
Policy: cache **on by default for pipeline runs, keyed-forever** (facts derived from a cached
response are exactly as good), with a `--no-cache` flag for prompt-tuning sessions; cache
hits are still written to the transcript with `cache_hit: true` per brainstorm 24 §2.1, and
logged in the cost log at zero marginal cost (so cost-per-accepted-fact stays honest about
*marginal* spend while `tokens_if_uncached` preserves the counterfactual). Sampling defaults
to temperature 0 for extraction/verification precisely so the cache is meaningful.

### 2.7 Cost caps and the cost log

There is no cash meter, but there are three real budgets: Claude usage limits, university
goodwill, and wall-clock. *Proposed:* every run's `manifest.yaml` (D18) declares
`budget: {max_calls, max_total_tokens, max_wall_seconds}`; the wrapper enforces it and
hard-stops with a resumable checkpoint (mirrors brainstorm 08 §12). The cost log is
**derived, not separate**: one CSV/JSONL row per call `(ts, run_id, seq, endpoint, alias,
resolved_model, prompt_id@version, tokens_in, tokens_out, latency_ms, cache_hit, outcome)` —
written by the same code path that writes the transcript event, so the two can never
disagree. **Cost-per-accepted-fact** is then a pure join: cost-log rows grouped by `run_id`
against the manifests' `resulting_fact_ids` — a report script, not wrapper machinery
(observability dashboard topic from brainstorm 24 owns presentation).

### 2.8 Library vs service shape

**Library, no daemon** (*proposed*, and firmly): a single Python package
`langatlas_pipeline.providers` inside `langatlas-kb`, constructed per-run from a config file
+ env-var secrets. No proxy process, no background service, nothing to keep alive — pipeline
runs are batch scripts (D11/brainstorm 07), and a daemon would add an ops burden and a
second place for config drift. The one standing service in the project remains Postgres
under docker compose (D7), which this layer does not touch.

## 3. Recommendation (*proposed*)

**One thin policy layer, two channel types, zero frameworks.**

```
langatlas_pipeline/providers/
  config.yaml        # endpoints, alias→capability table (probed), windows, budgets defaults
  core.py            # RunContext: transcript writer + cost log + budget enforcement (D18/D6)
  completion.py      # CompletionClient (openai SDK, base_url=university gateway | local)
  embedding.py       # embed(texts, model) → matrix   (openai SDK /v1/embeddings)
  rerank.py          # rerank(query, docs, model) → scores  (httpx, endpoint-specific)
  claude_runs.py     # Agent SDK runner + Tap-B normalizer glue (interactive + headless)
  cache.py           # sqlite content-addressed cache (§2.6)
  replay.py          # record/replay for tests (§ testing)
```

**The interface surface** (everything a pipeline stage may call):

- `ctx = RunContext(run_id, kind, budget)` — owns the transcript, cost log, cache handle,
  and budget; *every* call below requires a `ctx`. There is deliberately no way to call a
  provider without one — that is how D18 becomes non-bypassable.
- `ctx.complete(alias, messages, *, schema: type[BaseModel] | None, prompt: PromptRef,
  sampling) → Completion | ParsedResult` — chat completion; when `schema` is given, applies
  §2.3 (constrained decoding if the alias supports it, else json-mode + validate + one
  repair + one retry). Returns typed parse failures.
- `ctx.embed(texts, model) → list[vector]` and `ctx.rerank(query, docs, model) → scores` —
  batch-friendly, cached by content hash, logged as tool-class events (token counts, no
  message transcript bloat — D18's truncation rules apply).
- `ctx.claude_run(prompt | task_file, *, options) → AgentRunResult` — wraps an Agent SDK
  `query()`; streams messages into the same transcript; interactive sessions are ingested
  post-hoc by the same normalizer. Budget accounting counts messages/tokens from the stream.
- `PromptRef` — the **only** prompt-registry touchpoint: an opaque `(prompt_id, version,
  render(vars) → messages)` handle. The wrapper never loads prompt files itself; it records
  `prompt_id@version` in cache keys, cost-log rows, and manifests. Registry design,
  storage, and version minting are topic 32's, wholesale.

**Deliberately out of scope** (kept out so the layer stays ~small-hundreds of lines):
streaming to UIs (batch pipeline; the only streaming consumer is the transcript writer),
tool-calling/agent loops on the completion channel (agentic work belongs to the Claude
channel; the university models do drafting/entailment, not tool use), multi-provider
routing/fallback logic (one gateway; failures pause, they don't silently reroute — a
different model answering is a *provenance* change), fine-tuning, image/audio, token-exact
tokenization, and any queueing/scheduling (the orchestrator's job).

**Model-class policy baked into config, not code:** the D6 alias table lives in
`config.yaml` with per-alias probed capabilities (`supports_json_schema`,
`supports_json_object`, `reasoning_field`, `max_input_tokens`, default sampling). Adding a
local Ollama model later = one more endpoint block, zero code.

**Testing strategy: record/replay.** The cache (§2.6) already makes calls
content-addressed; `replay.py` adds a mode where a test run (a) `record`: executes real
calls and commits scrubbed fixtures (request-hash → response JSON) under
`tests/fixtures/providers/`, or (b) `replay`: any cache miss is a test failure. This gives
deterministic, offline CI for orchestration logic (D13's validators run without network),
plus a tiny live smoke-test marker (`pytest -m live`) run manually against the gateway.
VCR.py-style HTTP taping is unnecessary — replay at the wrapper interface is simpler and
survives transport-library upgrades. Fixture scrubbing reuses the D18 secret-scrub rules.

**Sequencing:** this layer plus the D18 tap is the first pipeline code to build (brainstorm
24 already scoped the pair at ~2–4 days; the wrapper adds ~2–3 more including endpoint
probing). Nothing else in the pipeline should be written before it, because every later
stage takes a `ctx` as its first argument.

## 4. Open questions for the developer

1. **Gateway ground truth (action item):** confirm the university endpoint is
   OpenAI-compatible (`/v1/chat/completions`, `/v1/embeddings`), how auth works (static
   key? per-user token?), what `Retry-After`/rate-limit headers it emits, and — per alias —
   whether `response_format: json_schema` (guided decoding) is passed through. A one-hour
   probing script settles §2.3/§2.5; results land in `config.yaml`.
2. **Reranker endpoint shape:** does `qwen3-reranker-4b` sit behind a `/v1/rerank`
   (Cohere/TEI-style) route, or must it be driven as a completion? Determines whether
   `rerank.py` is 20 lines or a prompt-based scorer.
3. **Concurrency politeness ceiling:** is there a stated or informal fair-use limit on the
   university API (requests/min, parallel streams, overnight batch etiquette)? The default
   token-bucket numbers should encode it rather than guess.
4. **Alias-drift policy:** when the university silently upgrades an alias (e.g. `deepseek` →
   v5), the cache treats it as a miss and provenance records the resolved id — but should
   in-flight *multi-day runs* pin the resolved model id at run start and abort on
   mid-run drift, or tolerate it? (Proposal: pin and abort — cheap and clean.)
5. **Claude headless budget posture:** given the 2026 split of interactive vs headless/SDK
   pools on subscription plans, does the developer want SDK runs capped separately in run
   budgets (e.g. `max_claude_messages`) from day one? (Proposal: yes — the budget block
   grows one field.)
6. **Local-model channel now or later:** reserve config space only (recommended), or stand
   up an actual CPU Ollama endpoint in v1 as a third smoke-test target? No GPU exists, so
   local models would be tiny — useful for replay-free integration tests, little else.
7. **Cache location & lifetime:** SQLite file in the private work area with no eviction
   (proposal), or inside the D15 snapshot-store directory so the periodic tarball backup
   covers it too?

## 5. New brainstorm topics surfaced

- **Endpoint capability probing as a maintained artifact** — a `probe.py` that regenerates
  the per-alias capability table (JSON-mode support, windows, latency percentiles) on
  demand; when and how its output is re-run and diffed (feeds topic 25's embedding
  benchmark subphase too).
- **Run orchestrator & checkpointing design** — this layer deliberately excludes
  queueing/resume logic; the batch driver (make-style staleness, pause-on-budget,
  circuit-breaker resume) needs its own design pass (extends brainstorm 07 §F).
- **Claude Code usage-limit telemetry** — how the orchestrator detects "limit reached" from
  Agent SDK runs reliably (exit codes? message classes?) and schedules the next batch
  window; small but load-bearing for unattended overnight operation.
- **Provenance of sampling parameters** — D5 provenance records model + prompt version;
  temperature/seed/sampling config arguably belong there too (they change outputs); decide
  where they live in the fact provenance schema (touches topic 09).

## Sources

- Claude Agent SDK overview & Python reference (structured `output_format`, headless runs,
  auth modes) — https://code.claude.com/docs/en/agent-sdk/overview ·
  https://platform.claude.com/docs/en/agent-sdk/python ·
  https://github.com/anthropics/claude-agent-sdk-python
- Claude Code billing split, interactive vs headless pools (2026) —
  https://tygartmedia.com/claude-code-billing-credit-pool-2026/
- LiteLLM OpenAI-compatible endpoint docs (evaluated, not adopted) —
  https://docs.litellm.ai/docs/providers/openai_compatible ·
  https://docs.litellm.ai/docs/proxy/user_keys
- OpenAI Python SDK `base_url` usage against compatible endpoints —
  https://docs.litellm.ai/docs/providers/openai · https://openai.github.io/openai-agents-python/models/
