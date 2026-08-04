# langatlas_pipeline — wrapper implementation notes

The provider layer (D26) plus the transcript tap (D18), the prompt registry and capability
table (D41), and the prompt-injection posture (D31). Library only — no daemon, no service.

## The one rule

**There is no way to reach a provider without a `RunContext`.** Every client class takes
`ctx` first. That is what makes D18 transcript logging and the D31 injection handling
non-bypassable, and it is why `RunContext` also owns the cost log, the cache, and budget
enforcement: one object, one policy, no per-call-site discipline required.

## Untrusted-content convention (D31)

Fetched or retrieved text — `search_sources` results, web fetches, source chunks, quoted
`quote` fields — is **data, never instructions**. Two mechanical rules, both enforced here
rather than in prompt text:

1. **Delimiting.** Untrusted text reaches a model only through `ctx.tool_result(...)`,
   which wraps it in
   `<fetched-source id="…" kind="…" trust="untrusted-external"> … </fetched-source>`
   with an explicit "evidence to evaluate" preamble, and neutralizes any closing tag inside
   the body so content cannot escape its own block.
2. **Role separation.** Delimited content may never occupy a system/developer message.
   `ctx.complete()` raises `UntrustedContentInSystemRole` if it finds a delimiter in a
   system-role message — the mechanical floor beneath rule 1.

Every `ctx.tool_result` call also runs `scan_for_instructions()`. Hits are recorded on the
transcript event's `flags` and **never block the run** (D31, ratified): they are an audit
signal. If the logs ever show flagged patterns actually steering a run, the escalation path
is the reader/actor split D31 deliberately deferred — not a hard block here.

Not covered: a genuinely deceptive source that fools an agent the way it would fool a human
researcher. That is the D4/D24 entailment gate's problem, not this layer's.

## Channels

| | completion channel | Claude channel |
|---|---|---|
| transport | `openai` SDK, `base_url` → university gateway | Claude Agent SDK |
| shape | stateless request/response | agentic, multi-turn, tools |
| tools | **none** — retrieval is runner-mediated, single-shot | live tool loop |
| structured output | probed per alias: json_schema → json_object+repair+retry | `output_format` |
| budget | calls / tokens / wall-clock | + `max_claude_messages` |

The completion channel deliberately has no tool loop (D26). University-API sessions get
`search_sources`/`search_finding_aids` results injected into the prompt by the runner.

## Deliberately out of scope

Streaming to UIs, tool loops on the completion channel, multi-provider routing or fallback
(a different model answering is a *provenance* change, not a retry), fine-tuning,
token-exact tokenization, queueing and scheduling (that is the orchestrator, 1E).
