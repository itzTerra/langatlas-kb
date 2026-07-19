# 32 — Pipeline Observability & Prompt Registry

> Backlog brainstorm for LangAtlas. Scope (checklist item 32): cost-per-accepted-fact/verifier-
> failure/debate-outcome reporting compiled from transcripts + cost logs; where prompt files live,
> version minting, prompt-change re-evaluation triggers; the per-alias endpoint capability table as
> a maintained artifact; Claude usage-limit telemetry for unattended overnight batches; whether
> `provenance.candidate_source` (D29) belongs in a broader "why did the pipeline look here"
> telemetry model; the topic-16/D30 verifier-replay counterfactual script as reusable tooling
> shared with this topic rather than built twice; the unified sourcing work queue spanning topic
> 28's `pending-source`, link-checker findings, and edition-check triage; the light-touch interface
> boundary with topic 29 if its blast-radius script ever broadens to chat logs/`source_chunks`.
> Binding context: D6 (Claude never does volume, cost-per-accepted-fact already named as a metric
> to track), D13 (validated-artifact CI, last-green publish), D18 (chat logging → public
> `langatlas-transcripts` repo, `run_id`/`debate_id`/`chat_run_id` keys), D24 (verifier six-verdict
> vocabulary, `partial` verdicts must be filterable, published error-rate estimates), D26
> (provider-abstraction `RunContext`: D18 transcript writer + D6 cost log share one code path,
> budget enforcement with resumable checkpoints, per-alias probed capability table, opaque
> `PromptRef` handle explicitly deferring registry mechanics to this topic, record/replay testing
> at `tests/fixtures/providers/`), D27 (research-phase R3/R4 debate repurposing), D29 (narrow
> `provenance.candidate_source` enum, pipeline-analytics-only, never public), D30 (verifier-replay
> counterfactual + cost join as two cheap zero-new-infra scripts reusing D18/D24/D26 logs;
> regression fixtures in a `tests/fixtures/providers/regression/` subfolder with human-diff review,
> not CI-blocking), D35 (dataset bundle manifest already carries published verifier error-rate
> estimates — the one place this topic's data is genuinely public-facing), D37/D38 (the private
> build-side-ledger pattern already established for verifier verdicts, `link_status`, and
> `sourcing_queue`-style state — never written back into authored YAML). Also draws on brainstorms
> 07, 13, 14, 16, 24, 28, 29 as named in the checklist entry. All proposals below are *proposed*
> until the developer ratifies.

## 1. Problem framing

Every sub-problem this topic bundles shares one property with topic 28's six sub-problems: none of
it is new data to capture. D18 already logs every chat, D26 already logs every cost/call, D24
already writes verifier verdicts to a build-side ledger, D25 already computes controversy scores,
D29 already tags candidate-fact provenance. This topic is entirely about the **read side** — what
turns logs nobody queries into numbers the developer can act on — plus two small pieces of
write-side design the pipeline still lacks a home for (the prompt registry, the capability table).
CLAUDE.md's own constraint set (solo developer, no cash budget, "boring, solo-maintainable
technology") and D30's own precedent ("stand up two cheap, zero-new-infrastructure scripts...
reusing data already logged") both point the same direction: **this is a reporting layer over
existing logs, not a new system that generates new state.** The one genuine design risk is scope
creep into a live dashboard — D1's whole architecture is "git is the database, everything
downstream is a derived build artifact you can regenerate," and a stateful web dashboard would be
the first thing in the whole project that doesn't fit that mold. Reject it up front, for the same
reason D30 rejected a debate-vs-no-debate live A/B simulator: no volume yet to justify the
build cost, and a periodically-run script serves the same need at a fraction of the maintenance
burden.

The prompt registry and capability-table pieces are different in kind from the reporting pieces —
they're small write-side artifacts the pipeline needs *before* volume exists, not reports compiled
after the fact. D26 left both as explicit stubs pointing here (`PromptRef` "topic 32 owns the
rest"; the capability table "a maintained artifact... how does it get updated"), so this brainstorm
has to actually design them, not just report on them.

## 2. Options with trade-offs

### 2.1 Reporting mechanism — cost/verifier/debate stats

**Option A — a live web dashboard (Grafana/Metabase-class, or a bespoke page).** Rejected outright.
Contradicts D1's build-artifact architecture, adds a service to keep running (violates D12's
"absent on purpose" service list in spirit even if not by name), and there's no audience for it —
the developer is the only consumer, and the developer already reads CLI output and markdown files
throughout this project (D28's QA reports, D24's calibration reports). No volume exists yet to
justify the build cost, mirroring D30's rejection of a debate-vs-no-debate simulator for the same
reason.

**Option B — a static site page fed by a periodic report script.** Plausible given D10/D13's
"static site fed by build artifacts" pattern, and it would put pipeline health next to the
D24-published verifier error rates (D35's manifest already ships those). But the reporting
audience here is the developer's own prompt-engineering/cost-tuning loop, not site visitors — this
is operational telemetry, not corpus content, and publishing it on the public site conflates two
different audiences (readers wanting sourced facts vs. the developer wanting a cost breakdown).
The one exception already exists and is already solved: D35's bundle manifest carries the
published verifier error-rate estimates as a deliberate "honesty feature," which is public-facing
*by design* (D24's ratification). That case doesn't need this topic to invent anything new — it
rides the existing manifest pipeline.

**Option C (recommended) — a CLI reporting tool, `tools/observability/report.py`, run on demand
(and later, on a schedule, by topic 35's orchestrator), printing markdown to stdout and optionally
writing a local, gitignored `reports/<date>.md` snapshot.** This mirrors D30's own precedent
exactly (two small scripts, not a service) and extends it with a shared subcommand structure
instead of one-off scripts per metric:

- `report.py cost` — `claude_messages_per_accepted_fact` (D30 §2.2's metric), segmented by
  `debate_id`, `run_id`, and onboarding phase (D28), joined from the D26 cost log against D23 fact
  ids.
- `report.py verifier` — verdict distribution (D24's six verdicts), with `partial` broken out
  identifiably per D24's ratification ("logged in an identifiable, filterable way for manual
  inspection"), segmented by source tier and language.
- `report.py debates` — R3/R4 schema-dispute outcomes now, phase-1+ fact-debate outcomes later
  (D30 §2.4's timing split), reusing the verifier-replay counterfactual (§2.6 below) as its core
  computation rather than a separate implementation.
- `report.py sourcing-queue` — the unified queue view (§2.7 below).
- `report.py capabilities` — capability-table staleness/drift (§2.3 below).

Reports read directly from: the local clone of `langatlas-transcripts` (D18), the D26 cost log, and
whatever local store holds the D24 verifier ledger / D25 controversy scores (the same private
build-side store already used for `link_status` per D37 and `sourcing_queue` per D38's fold-in —
one store, not a new one). Nothing here is committed to a public repo as canonical data; it is
regenerable at will from data that already is.

**Recommendation: C.** No new service, reuses D30's precedent and extends it into one CLI with
subcommands instead of scattered one-off scripts, keeps the public/private split clean (D35 already
owns the one legitimately public number), and gives topic 35 a ready-made hook (`report.py` run
as a scheduled job) without this topic having to design scheduling itself.

### 2.2 Prompt registry — location, versioning, re-evaluation triggers

D26 fixed the *interface* (`PromptRef` = opaque `prompt_id@version` handle feeding the cache key)
but explicitly left the registry itself to this topic.

**Location.** A `prompts/` directory in `langatlas-kb`, one subdirectory per `prompt_id`
(`prompts/<prompt_id>/`), each version as its own file. Prompts are configuration the pipeline
depends on for correctness — exactly the kind of thing this project already prefers to keep in git
rather than a database (matching D1's whole posture), so no new storage decision is actually needed
here, just a directory convention.

**Version minting — two options:**

- **Option A — sequential integers (`v1`, `v2`, ...) with a discipline rule** ("never edit a
  version file once it's been used by any logged call — bump the integer instead"). Simple and
  human-readable in commit messages and `impact.md`-style reports, but the discipline is
  unenforced: nothing stops an agent or the developer from editing `v3` in place, silently
  invalidating the D26 content-addressed cache's correctness (a cached response keyed on `prompt_v3`
  would now be paired with different prompt text than what actually produced it) and making any
  later "did this prompt change?" audit unreliable.
- **Option B (recommended) — content-addressed versions**, mirroring D23's fact-id pattern and
  D16's id/slug split: the version tag is a short hash of the rendered prompt template
  (`v-<8hex>`), computed automatically, with an optional human-readable sequential alias
  (`v-a3f9c210` ≡ "v4") recorded in a per-`prompt_id` `CHANGELOG.md` purely for human legibility in
  commit messages and reports. Editing the prompt text *always* produces a new version
  automatically — there is no discipline to maintain, because the content hash makes "did this
  change" a mechanical fact rather than a convention. This is the same move D23 already made for
  facts (content-keyed ids over developer-assigned sequence numbers) and D16 made for ontology
  nodes (immutable id vs. renameable slug) — reusing a pattern this project has already validated
  twice rather than introducing a third versioning scheme.

**Re-evaluation trigger.** Wire prompt-version changes into the topic-16/D30 regression harness
that already exists for this purpose (§2.6 makes the sharing concrete): whenever a new
`prompts/<prompt_id>/v-<hash>.md` file is committed, a pre-batch check (living with the topic-40
validator CLI, not a new tool) looks for a corresponding fixture set under
`tests/fixtures/providers/regression/<prompt_id>/` and, if one exists, requires it to have been
re-run and diff-reviewed more recently than the new version's commit date — a soft gate (a logged
warning surfaced by `report.py`, per D30's "human-diff review, not CI-blocking pass/fail"), not a
hard CI failure, matching D30's own ratified stance on regression-fixture strictness. Prompt ids
with no fixture set yet simply get no gate — this only bites once a `prompt_id` has accumulated
enough real transcripts to be worth curating fixtures for, exactly as D30 already describes fixture
growth ("naturally grows from real debate transcripts").

### 2.3 Per-alias capability table as a maintained artifact

D26 already established the concept (per-alias `json_schema` support, since the gateway doesn't
document it formally) but not its lifecycle.

**Location:** a single git-tracked file, e.g. `config/provider_capabilities.yaml`, keyed by alias
(`glm`, `kimi`, `deepseek`, `deepseek-thinking`, `mini`, `coder`/`agentic`, `thinker`), recording:
resolved model id at last probe, `json_schema` support (probed empirically per D26), context
window, embedding/rerank applicability, and `last_probed` date. Being a plain committed YAML file
means it's diffable in git history exactly like every other config artifact in this project — no
new storage mechanism.

**Update mechanism — three options:**

- **Option A — fully automatic, re-probed and auto-committed on every pipeline run.** Cheapest to
  keep fresh, but auto-committing a file that changes *decoding strategy* (schema-constrained vs.
  json-mode-plus-repair) without a human glance is a bigger blast radius than it looks — a silent
  alias re-point (D26's "alias-drift" risk) changing `json_schema` support would change how every
  downstream call decodes structured output, and D26 already chose "abort on drift by default"
  precisely because this class of change deserves attention, not silent absorption.
- **Option B (recommended) — a manual/periodic probe script, `probe_capabilities.py`, run by the
  developer (or, later, on a monthly cadence via topic 35's scheduler — cheap, since probing is a
  handful of completion calls, not a batch job), diffing its findings against the committed table
  and flagging drift rather than auto-writing it.** The script reports "alias `X` now resolves to
  model `Y` (was `Z`)" or "`json_schema` support for alias `X` appears to have changed" as a
  reviewable diff; the developer commits the update after a glance, same trust posture D26 already
  applies to alias-drift generally. This also gives `report.py capabilities` (§2.1) something
  concrete to surface: "capability table last verified N days ago," turning table staleness itself
  into a visible metric rather than a silent risk.
- **Option C — probe on every batch start, abort the batch on any detected drift (extending D26's
  existing pin-and-abort-on-drift policy from resolved-model-id to the full capability table).**
  Technically consistent with D26's existing posture, but probing on every run start adds latency
  and university-API load for a signal that changes rarely (the gateway's alias resolutions aren't
  expected to churn day-to-day) — disproportionate to the actual drift rate.

**Recommendation: B**, with C's underlying principle (abort-on-resolved-model-drift) staying
exactly as D26 already ratified it for the model-id case specifically; the broader capability table
gets the lighter periodic-probe-and-diff treatment since its risk profile (occasional, reviewable)
differs from resolved-model pinning (immediate, per-run).

### 2.4 Claude usage-limit telemetry for unattended batches

This is explicitly an interface topic 32 owes to topic 35 (the run orchestrator, not yet designed)
— the brief is right to flag "don't over-design 35's territory." What this topic *can* define now:
the typed signal the Claude channel emits when it detects it's approaching or has hit a Pro
session/usage limit, so that whatever eventually drives batches (currently: the developer running
things by hand; later: topic 35's orchestrator) has something concrete to catch.

**The asymmetry to design around:** the university-API channel has real, if undocumented, rate
limits the D26 token-bucket already guards against proactively; the Claude channel, per D26, "has
no raw API key on Pro" — there is no documented quota-headroom API to poll predictively. The only
signal available is **reactive**: the SDK/session surfaces some form of limit-reached condition
when it actually happens, not a gauge beforehand.

**Recommendation:** the Claude channel of `RunContext` classifies any usage-limit-shaped
failure it observes into a small typed signal, e.g.:

```
ClaudeLimitSignal {
  detected_at: timestamp
  signal_type: hard_stop | soft_warning | unknown
  raw_message: str          # exactly what the SDK/session reported, for debugging
  run_id: str                # ties back to the D18 transcript/manifest
}
```

logged through the existing D18/D26 channel (so it's visible in the transcript and joinable in
`report.py`), and raised as a distinguishable exception/return type from the channel rather than a
generic error — the one non-negotiable interface requirement this topic hands to topic 35, since
topic 35 needs to tell "hit a real Anthropic-side limit" apart from "hit our own self-imposed D26
budget cap" (`max_calls/tokens/wall_seconds`) to decide whether resuming later is even possible
right now versus just a matter of the run's own checkpoint. The self-imposed D26 budget is already
the proactive half of this story (conservative caps chosen precisely because there's no headroom
gauge to poll); `ClaudeLimitSignal` is the reactive fallback for when the actual limit is hit
despite the conservative cap. `report.py` gets one more cheap subcommand out of this for free: "how
often did runs stop on a real Claude limit vs. our own self-imposed cap" is itself a useful
pipeline-health number, distinguishing "we're leaving Claude Pro capacity on the table" from "we're
actually bumping the ceiling."

Building the actual pause/checkpoint/resume-after-reset-window logic stays topic 35's job, as the
brief directs — this topic stops at defining the signal shape and its logging path.

### 2.5 `provenance.candidate_source` — narrow field or broader "why did the pipeline look here" model?

**Option A — build a broader telemetry model**: a dedicated event log tracing every
finding-aid/checklist-generation query (topic 45's eventual `search_finding_aids` tool, PLDB/
Wikidata/Hyperpolyglot lookups during R3 surveys and sweeps) as its own timeline, so "why did the
pipeline look here" is reconstructable step-by-step, not just summarized as one enum value on the
eventual fact.

**Option B (recommended) — D29's field is already sufficient; no new model needed.** The deeper
trace Option A wants already exists for free: every tool call an agent makes — including a
finding-aid lookup — is already captured as an ordinary logged message in its D18 transcript
(`RunContext`'s non-bypassable logging, per D26, applies to every call regardless of which tool is
invoked). `provenance.candidate_source` is the durable, cheap, per-fact *summary* of that trace
(which family of finding aid ultimately produced the candidate); the full step-by-step "why" is
already sitting in the transcript, joinable via the fact's `chat_run_id` (D18) the moment anyone
actually needs it. Building a second, parallel event-log specifically for finding-aid provenance
would duplicate data D18 already writes, for a query pattern ("show me the finding-aid trace for
fact X") that's already answerable today by looking up `chat_run_id` and reading the transcript at
its anchor. The only genuinely new thing this topic contributes is naming the join: `report.py`
(or an ad hoc lookup) can cross-reference `candidate_source` against transcript tool-call entries
if a deeper trace is ever wanted, with no new logging field required to make that possible.

**Recommendation: B.** No broader model — D29's field plus existing D18 transcript logging already
covers the full spectrum from "cheap per-fact summary" to "full step-by-step trace," and topic 32
doesn't need to add anything except the observation that the join key already exists.

### 2.6 Verifier-replay counterfactual as shared tooling

D30/brainstorm 16 already flagged this explicitly as topic 32's job to avoid a duplicate build.
**Recommendation:** one shared library function, e.g. `langatlas.observability.replay.replay_verdict
(draft_or_fact_id) -> Verdict`, that re-runs the current D24 verifier against a given historical
draft or accepted fact exactly as topic 16 §2.1 Option A already specifies, with two callers built
on the same core:

1. **Topic 16's debate-instrumentation use** — single-draft mode: re-score one pre-challenge draft,
   compare its verdict against the eventually-accepted fact's recorded verdict, flag "debate
   changed nothing detectable" vs. "debate demonstrably changed the outcome."
2. **This topic's own use, feeding `report.py`** — bulk mode: sweep a sample (or all) of the
   currently-accepted facts through the *current* verifier prompt/model version and report what
   fraction would still pass unchanged — a drift/regression health metric answering "has the
   verifier itself changed enough that old acceptances deserve a second look," distinct from but
   built on the identical mechanism.

Building this as one shared module from the start (rather than topic 16 building its own
single-purpose script first) costs nothing extra now and avoids the exact duplicate-build risk the
checklist entry names.

### 2.7 Unified sourcing work queue

Topic 28's own brainstorm (§3 item 7, §5) already named this as belonging here, not as a new
number. **Recommendation:** one private table/log — reusing D38's `sourcing_queue` name rather than
inventing a second one — with a `kind` discriminator (`pending-source | link-dead | anchor-drift |
content-drift | edition-mismatch`) over a common shape (`source_id`, `opened_at`, `age_days`,
`bounce_count` where D24's 2-bounce budget applies, `status: open | resolved`,
`resolution_note`), written by the three existing producers into the same location:

- the D24 verifier's stage-1 `pending-source` logic (kind `pending-source`),
- the D37 monthly link-checker (kinds `link-dead`, `anchor-drift`, `content-drift`),
- the D37 quarterly edition-check job (kind `edition-mismatch`).

All three already write to "a private, build-side ledger" per D23/D37's established pattern for
pipeline state that never belongs in authored YAML — this topic doesn't introduce a new storage
location, just a shared schema across the three existing writers. `report.py sourcing-queue`
becomes a single sorted-by-`age_days` view spanning all four kinds — the concrete answer to "one
combined view rather than three half-built dashboards."

### 2.8 Interface boundary with topic 29's blast-radius script

Light touch only, per the brief. If topic 29's blast-radius script ever broadens beyond
facts/edges/rules (its D38-ratified current scope) to chat logs and `source_chunks`, the one
requirement this topic places on that broadening: **its "who's affected" output should use the
same join keys this topic's reporting layer already keys on** — `chat_run_id` (D18), `source_id`
(D15/D37), `run_id` (D26) — rather than inventing parallel identifiers. If that requirement holds,
`report.py` could gain a "blast radius of change X, including affected transcripts/chunks" view
later by pointing at the broadened script's output, with no redesign of the reporting pipeline
itself. Nothing else about that broadening is this topic's to design (D38 already scoped it
out for now).

## 3. Recommendation (*proposed*)

1. **Reporting mechanism (§2.1):** a CLI tool, `tools/observability/report.py`, with subcommands
   (`cost`, `verifier`, `debates`, `sourcing-queue`, `capabilities`, and a bulk verifier-drift mode
   per §2.6) reading directly from the D18 transcripts repo, the D26 cost log, and the existing
   private build-side ledger. Output is markdown to stdout, optionally snapshotted to a gitignored
   local file — never committed as canonical data, never a live service. The one legitimately
   public number (verifier error rates) already ships via D35's bundle manifest and needs nothing
   new here.
2. **Prompt registry (§2.2):** `prompts/<prompt_id>/v-<8hex-content-hash>.md` files in
   `langatlas-kb`, content-addressed versions (mirroring D16/D23's id-immutability pattern) with a
   human-readable sequential alias recorded in a per-prompt `CHANGELOG.md`. New versions trigger a
   soft (log-and-warn, not CI-blocking) check for a stale-or-missing regression-fixture re-run
   under `tests/fixtures/providers/regression/<prompt_id>/`, living with the topic-40 validator.
3. **Capability table (§2.3):** `config/provider_capabilities.yaml`, git-tracked, updated by a
   manual/periodic `probe_capabilities.py` script that diffs live-probed findings against the
   committed table and flags drift for developer review rather than auto-committing; `report.py
   capabilities` surfaces table staleness as a metric.
4. **Claude usage-limit telemetry (§2.4):** a typed `ClaudeLimitSignal` (`detected_at`,
   `signal_type`, `raw_message`, `run_id`) raised by the Claude channel of `RunContext` on any
   limit-shaped failure, logged per D18, distinguishable from a self-imposed D26 budget stop — the
   interface handed to topic 35, no pause/resume logic designed here.
5. **`provenance.candidate_source` (§2.5):** no broader model needed. The field stays as D29
   ratified it; the deeper "why did the pipeline look here" trace already exists for free in D18
   transcripts, joinable via `chat_run_id` whenever actually wanted.
6. **Verifier-replay counterfactual (§2.6):** one shared library function
   (`langatlas.observability.replay.replay_verdict`) used both by topic 16's single-draft debate
   instrumentation and this topic's own bulk verifier-drift reporting — built once.
7. **Unified sourcing queue (§2.7):** one `sourcing_queue` table (per D38's naming) with a `kind`
   discriminator spanning `pending-source`/link-checker/edition-check entries, written by the three
   existing jobs into the existing private ledger location, read by one `report.py` subcommand.
8. **Topic 29 interface (§2.8):** no design now beyond naming the join-key compatibility
   requirement (`chat_run_id`/`source_id`/`run_id`) a future broadened blast-radius script would
   need to honor to slot into this reporting layer without rework.

## 4. Open questions for the developer

1. **Report persistence** — is `report.py`'s output purely ephemeral (stdout, optionally a
   gitignored local snapshot), or does the developer want periodic reports committed somewhere
   (a private log, or even a `reports/` directory in the kb repo) for their own historical
   trend-watching, beyond what D35's bundle manifest already publishes?
2. **Prompt-version scheme** — confirm content-hash-addressed versions (§2.2 Option B, recommended)
   over plain sequential integers with a discipline rule (§2.2 Option A)?
3. **Prompt regression-check strictness** — should a new prompt version with a stale/missing
   regression re-run block that version from being used in an *unattended overnight* batch
   specifically (even while staying a soft, log-only gate for interactive/manual use), or is a
   uniform soft gate acceptable everywhere per D30's existing stance?
4. **Capability-probe cadence** — is monthly the right frequency for `probe_capabilities.py`
   (§2.3), or should it run only on-demand before the developer starts a significant new batch
   (e.g. before onboarding a new language phase)?
5. **Claude-limit signal granularity** — is the reactive-only `ClaudeLimitSignal` (§2.4)
   sufficient, or does the developer want this topic to also attempt some proactive heuristic
   (e.g. tracking wall-clock/message-count history to estimate "probably close" before an actual
   limit hit), despite there being no documented quota API to calibrate such a heuristic against?

## 5. New brainstorm topics surfaced

No genuinely new backlog number — every piece of this topic's scope either resolves fully within
this brainstorm (reporting CLI, prompt registry, capability table, `candidate_source` scope
decision, sourcing-queue unification) or hands off cleanly to a topic that already claims the
next layer:

- **Claude usage-limit pause/resume/checkpoint logic** — the `ClaudeLimitSignal` interface (§2.4)
  is this topic's contribution; the actual scheduling/resume mechanics belong to topic 35 (run
  orchestrator & checkpointing), exactly as the checklist entry already anticipated.
- **Prompt-version regression-gate enforcement mechanics** — living inside topic 40's validator
  CLI scope ("the one offline tool shared by CI and the agent runner's pre-commit gate"), not a
  new tool.
- **Blast-radius broadening to chat logs/`source_chunks`** — stays topic 29's call to make in the
  first place (§2.8); this topic only names the join-key requirement it would need to honor.
