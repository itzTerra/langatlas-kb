# 35 — Run Orchestrator & Checkpointing

> Backlog brainstorm for LangAtlas. Topic: the batch-run driver that sits *above* the D26
> provider layer and the D27/D36 commit protocol — the thing that actually starts, pauses,
> checkpoints, and resumes an unattended run (a research-phase R3 survey sweep, a per-language
> sweep-pipeline run, a nightly verification batch, or one of the smaller scheduled jobs already
> named by other topics). Binding context: D26 (`RunContext` owns budget enforcement —
> `max_calls/tokens/wall_seconds` per run manifest, "hard-stop with resumable checkpoint" named
> but not designed — the gap this topic closes); D36/topic 27 (agent-runner commit protocol —
> already ships a typed `LandResult` union (`landed | blocked_red_main | contention_exhausted |
> reverted | unsafe_halt`) and an idempotent `LangAtlas-Record-Key` git trailer specifically so
> this topic's driver has "something concrete to call and react to," per topic 27's own stated
> boundary — this brainstorm consumes that interface, it does not redesign the commit mechanics
> behind it); D41/topic 32 (pipeline observability — defines a typed reactive `ClaudeLimitSignal`
> raised by the Claude channel of `RunContext` and explicitly hands the pause/resume/checkpoint
> logic for it to this topic); D25 (the 18-month backstop re-verification sweep, budgeted at
> ~200 facts/night, plus nightly controversy-assessor batches); D37/topic 28 (the monthly
> link-checker job and the quarterly edition-check job, both needing scheduling mechanics this
> topic owns); D11/D27 (iteration hygiene already committed to "one-cell-per-invocation resumable
> batches" as a pipeline-wide convention, and D30's precedent of reusing existing logged data
> rather than inventing new infrastructure); D12 (absent-on-purpose: no message queues, no
> Kubernetes/microservices — binds this topic's shape choice directly). Surfaced by brainstorm 13
> §5 ("Run orchestrator & checkpointing design... extends brainstorm 07 §F") and reiterated by 27
> and 32. All proposals below are *proposed* until the developer ratifies.

## 1. Problem framing

Three other topics have already built pieces of what this one has to assemble into something
runnable overnight, unattended, on a solo developer's machine:

1. **D26** gives every call a `RunContext` with budget caps and says a hard-stop should leave a
   "resumable checkpoint" — without saying what a checkpoint contains, where it lives, or what
   "resume" does differently from "start."
2. **D36** gives every *commit attempt* a typed result (`LandResult`) and an idempotency
   guarantee at the git level (`LangAtlas-Record-Key`) — but topic 27 explicitly stopped at
   "this is a library topic 35 calls once per record," leaving the loop that calls it, decides
   what to do with each result, and persists progress across process restarts entirely to this
   topic.
3. **D41** gives the Claude channel a typed `ClaudeLimitSignal` for the one failure mode that is
   *reactive-only* (no quota-headroom API exists on a Pro subscription) — and explicitly says
   "building the actual pause/checkpoint/resume-after-reset-window logic stays topic 35's job."

None of this is new call-making machinery. This topic is pure **control flow**: given a batch of
work items (sweep cells, survey themes, verification candidates, link checks), drive them through
the already-built layers below, and be correct about what happens when the process stops for any
of five reasons — normal completion, a self-imposed D26 budget cap, a reactive Claude usage-limit
hit, an `unsafe_halt` from the commit protocol, or a plain crash (power loss, an unhandled
exception, the developer's laptop going to sleep) — and correct about what "resuming" means for
each of those five, since they are not interchangeable (a budget cap means "come back later, on
purpose"; an `unsafe_halt` means "don't come back until a human looked at the filed issue").

Scale/urgency check, mirroring D36's own framing: today this runs as **one unattended process at a
time**, on the developer's own machine, well below any concurrency where a real scheduler or
queueing system would earn its keep. CLAUDE.md's "boring, solo-maintainable technology" bias and
D12's explicit "no message queues, no Kubernetes/microservices" rule both point the same direction
as D26 §2.8's "library, no daemon" verdict for the provider layer: **this topic should produce a
script, not a service.**

Scope boundaries, restated from the other three topics' own boundary notes so this brainstorm
doesn't re-litigate them: D26 owns `RunContext`'s internals (transcript writer, cost log, cache) —
this topic only consumes its budget-exceeded signal. D36 owns git commit/rebase mechanics — this
topic only consumes `LandResult`. D41 owns the *shape* of `ClaudeLimitSignal` — this topic owns
what happens when one arrives. This topic's own job is everything above all three: enumerating
work, looping over it, checkpointing progress, and deciding when a run stops or resumes.

## 2. Options with trade-offs

### 2.1 What runs a batch

**Option A — a set of independent per-job-kind scripts, each with its own bespoke checkpoint
file and ad hoc resume logic.** Fastest to write a first version of any one job, but every job
reinvents the same five-way stop/resume decision tree slightly differently, and the pipeline
already has four-plus job kinds that need it (sweep cells, R3/R4 survey items, nightly
verification, monthly link-checker, quarterly edition-check, the 18-month backstop) — divergent
implementations of "what does resume mean" is exactly the kind of drift that turns into silent
double-commits or silently-dropped work six months in, with nobody noticing until an incident.

**Option B — a lightweight task queue (Celery/RQ-class, backed by Redis or a DB table).**
Rejected outright, same reasoning D12/D27 §2.7 Option C already applied to a real coordination
service: no plausible scale at a solo developer's single-runner cadence justifies a broker
process, and it directly contradicts the "absent on purpose" list. A queue's real value —
distributing work across many concurrent workers — doesn't exist here; there is one worker.

**Option C (recommended) — one thin driver library + a per-job-kind config file, no daemon.** A
single `tools/orchestrator/driver.py` implements one generic loop (enumerate work items → for each,
call into the appropriate lower layer → interpret the typed result → checkpoint → decide
continue/pause/halt) parameterized by a **batch spec** — a small YAML file naming the job kind,
where its work items come from, and its budget. Concretely:

```
config/jobs/
  nightly-verification.yaml
  monthly-link-checker.yaml
  quarterly-edition-check.yaml
  backstop-sweep-18mo.yaml
  sweep-<language>.yaml        # one per active per-language sweep run
  research-r3-<theme>.yaml     # one per active R3 survey theme
```

Each spec is small: `kind` (an enum the driver dispatches on), `work_item_source` (how to
enumerate pending items — a plain function reference per kind, e.g. "unswept questionnaire cells
for language X" or "url-locator sources due for a monthly check"), `budget` (passed straight
through to D26's `RunContext`), and `checkpoint_path`. Adding a new job kind is "write one
enumerator function + one YAML file," not "design a new subsystem." One driver invocation = one
`RunContext`-scoped run, exactly matching D18/D26's existing `run_id` granularity.

- Pros: exactly one place implements the stop/resume decision tree (§2.3, §2.4), so every job
  kind gets crash-safety and budget/limit handling for free instead of by convention; no daemon,
  no new standing process; a new job kind is additive, not a redesign.
- Cons: the generic loop has to be written carefully once, since every job kind depends on it
  being correct — but that concentration of correctness-risk in one well-tested place is the
  point, not a hidden cost.

**Recommendation: C.** It is the direct continuation of D26's "library, no daemon" verdict one
layer up, and it is the only option that gives every current and future scheduled job (D25's two
jobs, D37's two jobs, D5's sweep, D27's research survey) the same crash-safe resume behavior
without reimplementing it per job.

### 2.2 Resumable checkpoints — unit and storage

**What is the checkpoint unit?** Not a fixed global answer — it is **whatever the batch spec's
`work_item_source` already enumerates**, which is deliberately not standardized to one grain
project-wide, because the pipeline already has legitimate different grains: one questionnaire
*cell* for the per-language sweep (matching D11's already-ratified "one-cell-per-invocation
resumable batches" convention), one *theme* for an R3 survey pass, one *fact* for the 18-month
backstop sweep, one *URL-locator source* for the monthly link-checker, one *spec source record*
for the quarterly edition-check. The orchestrator's contract with each job kind is only: "give me
an ordered, enumerable, individually-idempotent list of items," not "use my grain."

**Where does checkpoint state live, and in what form?**

- **Option A — a Postgres table.** Rejected: checkpoint state is pipeline-run bookkeeping, not
  derived corpus data (D1's whole architecture keeps Postgres a *derived, rebuildable* artifact —
  writing live run state into it would be the first thing in the project that makes Postgres
  non-derived, undermining D7's own premise).
- **Option B — a file committed to the git repo.** Rejected: checkpoint state changes every few
  seconds during a run and carries no corpus meaning; committing it would spam `main` with
  noise commits unrelated to any record (D36's whole commit-granularity design assumes one
  commit = one landed record) and give the failure bot (D36 §2.5) nothing sensible to reason
  about if a checkpoint commit itself needed reverting.
- **Option C (recommended) — a local, private, non-git SQLite file, one row per (batch spec,
  work item key), living in the same private work area as D26's own cache and cost log** (the
  D15/D26-established "private tier" — periodic tarball backup, not git). One table:
  `orchestrator_checkpoint(run_id, spec_kind, item_key, status, land_result, attempted_at,
  last_pause_reason)`, `status` ∈ `{pending, in_progress, done, blocked, contention, halted}`.

**How this interacts with D36 without duplicating it** (the brief's own load-bearing
requirement): this checkpoint is **driver-level bookkeeping only** — "have I attempted this item
this run/across runs, and what did the commit protocol last tell me about it." It is explicitly
**not** the source of truth for "did this actually land on `main`" — that ground truth is, and
stays, the `LangAtlas-Record-Key` git trailer D36 already specifies, looked up via `git log
--grep` before any resumed item is re-attempted. This is the same "belt and suspenders" split D36
§2.6 itself already names ("topic 35 keeps its own checkpoint of attempted records for
driver-level bookkeeping, but the git trailer is ground truth that survives even a corrupted or
lost checkpoint file"): the SQLite checkpoint makes resume *fast* (skip items already marked
`done` without hitting git at all), the git trailer makes resume *correct* even if the SQLite file
is lost, corrupted, or simply never existed (a first run after a crash before any checkpoint was
even written). Concretely, on resume the driver treats a `done` checkpoint row as a fast-path
skip, but treats any row in `in_progress`, `blocked`, or `contention` state as needing a
git-trailer lookup before acting — the checkpoint's job for those rows is only "which items to
look at first," not "what happened to them."

**Crash safety property this buys:** because the checkpoint row is written *before* the driver
calls into the commit protocol for a given item (status `in_progress`) and updated immediately
after (status `done`/`blocked`/`contention`/`halted`), a process crash mid-item leaves at worst one
`in_progress` row whose real-world status the git-trailer lookup resolves unambiguously on
restart — there is no window where an item can be silently double-committed, because D36's own
idempotency key (not this checkpoint) is what a resumed attempt checks first.

### 2.3 Budget hard-stops — the mechanism D26 named but didn't design

D26's manifest already declares `budget: {max_calls, max_total_tokens, max_wall_seconds}` and says
the wrapper "enforces it and hard-stops with a resumable checkpoint." This topic designs the
concrete mechanism:

1. `RunContext` (D26, unchanged) raises a typed `BudgetExceeded` exception/signal the moment any
   call would cross a declared cap — before making the call, not after (a mid-call token overshoot
   is logged as an over-budget outcome but not retried).
2. The orchestrator driver wraps its per-item call into the lower layers in a single
   try/except for exactly two signal types it must distinguish (mirroring D41's own distinction
   requirement): `BudgetExceeded` (self-imposed cap, D26) and `ClaudeLimitSignal` (external,
   reactive, D41). Both route to the same **pause** path, tagged with a different `reason` field,
   because the resume policy differs (§2.4).
3. On either signal: the driver marks the *current* item's checkpoint row `blocked` (not `done`,
   not `failed` — its content, if any was produced, is still valid and re-attemptable per D36's
   idempotency guarantee), writes a run-level `paused` record (`run_id`, `reason`,
   `paused_at`, `items_remaining`), and exits with a distinct process exit code (e.g. `75` —
   conventionally "temporary failure," distinguishing a clean pause from a crash or a hard error
   for any wrapping cron/shell logic to detect).
4. **Resume is re-invocation of the identical command.** There is no separate "resume mode" —
   the driver always starts by reading the checkpoint for its batch spec, skipping `done` rows,
   git-trailer-verifying ambiguous rows (§2.2), and continuing from the first `pending`/`blocked`
   item. This is the same principle D27 already applies to commit-level idempotency, one layer up:
   *resume is not a special code path, it's what happens automatically when you run the thing
   again.* A human re-invoking the run and a cron job re-invoking it on the next scheduled slot
   are indistinguishable to the driver.

### 2.4 Claude usage-limit / halt-resume signaling

D41 stops at defining `ClaudeLimitSignal`'s shape and logging path, explicitly handing "the actual
pause/checkpoint/resume-after-reset-window logic" here. Building on §2.3's shared pause path:

**Detection:** unchanged from D41 — the Claude channel of `RunContext` classifies any
usage-limit-shaped failure from the Agent SDK/session into `ClaudeLimitSignal {detected_at,
signal_type: hard_stop | soft_warning | unknown, raw_message, run_id}`.

**What the orchestrator does differently for a `ClaudeLimitSignal` versus a `BudgetExceeded`:**
a self-imposed budget cap is *known-safe* to retry immediately (the developer's own configured
ceiling, no external state to wait out); a real Claude limit is *not* — retrying immediately would
just hit the same wall again and waste the retry. So:

- **Cool-down before any resume attempt.** On `ClaudeLimitSignal`, the orchestrator records
  `paused_until = paused_at + cooldown` using a conservative, configurable default (proposed: 4
  hours, since there is no documented reset-window API to calibrate against per D41's own framing
  — chosen to be safely longer than the shortest plausible reset window rather than tuned to a
  real number that doesn't exist yet). A resumed invocation before `paused_until` immediately
  no-ops (logs "still cooling down, N hours remaining" and exits) rather than re-attempting and
  re-triggering the same signal.
- **"Alert" in a solo-dev, no-infra project, concretely:** no push/paging channel exists in this
  project's stack (D12's absent-on-purpose list has no room for one, and building one for a single
  developer's own overnight runs is disproportionate). The alert **is** the run halting with a
  clearly labeled, glanceable state: (a) the process exit code (§2.3) and its final stdout line
  are visible to whatever invoked it — for a cron-triggered run, that means **standard cron mail**
  (`MAILTO` in the crontab, already a zero-code, decades-old mechanism) is the entire notification
  layer; (b) a small `orchestrator/status.json` (one row per active batch spec: `paused |
  running | done`, `reason`, `paused_until`) that `report.py` (D41/topic 32) can surface as one
  more subcommand (`report.py orchestrator-status`) for the developer's own morning check-in. No
  bespoke notification service is built — "the run halts and the developer notices" (the brief's
  own framing) is accepted as the actual answer, made slightly less blind by the status file and
  cron mail rather than requiring the developer to guess from a bare process exit.
- **After the cool-down window, resume is the same re-invocation mechanism as §2.3** — nothing
  Claude-specific about the resume path itself, only about the wait before attempting it.

### 2.5 Scheduling mechanics for background jobs

Four scheduled jobs already exist on paper and need to actually run: D25's nightly
controversy-assessor batch (~200 facts/night) and its 18-month backstop re-verification sweep;
D37/topic 28's monthly link-checker and quarterly edition-check.

**Option A — a scheduling table / lightweight internal scheduler the orchestrator itself runs
continuously.** Rejected: this is a daemon by another name — exactly the "keep something alive to
decide when to run things" shape D26 §2.8 already rejected for the provider layer, D12 rejects
generally, and there is no reason to build a second, project-specific cron when the developer's
machine already has one.

**Option B (recommended) — plain `cron` on the developer's machine, one line per job, each
invoking the same `driver.py` with a different batch-spec YAML.** A checked-in
`config/jobs/crontab.example` documents the intended schedule (not itself executable — the
developer's real crontab is local machine state, same tier as D26's local cache) so the mapping
from job to cadence is legible and versioned even though cron itself isn't:

```
# nightly ~200-fact controversy assessment + re-verification backstop candidates (D25)
0 2 * * *   cd <repo> && python -m tools.orchestrator.driver run config/jobs/nightly-verification.yaml
# monthly link-checker (D37/topic 28)
0 3 1 * *   cd <repo> && python -m tools.orchestrator.driver run config/jobs/monthly-link-checker.yaml
# quarterly edition-check (D37/topic 28)
0 4 1 1,4,7,10 *  cd <repo> && python -m tools.orchestrator.driver run config/jobs/quarterly-edition-check.yaml
# 18-month backstop sweep, checked monthly (job itself decides if 18 months have elapsed)
0 5 1 * *   cd <repo> && python -m tools.orchestrator.driver run config/jobs/backstop-sweep-18mo.yaml
```

The 18-month sweep's actual cadence lives inside its own batch-spec logic (a monthly cron trigger
that checks "is it time yet" and no-ops otherwise) rather than trying to express an 18-month
period in cron syntax directly — cron is good at recurring short cycles, not multi-year ones.

- Pros: zero new code beyond the one driver already being built for every other job kind; cron
  is already the boring, decades-proven answer for "run X on a schedule" on a single machine;
  every job's cadence is one crontab line, reviewable in a PR/commit like any other config.
- Cons: cron doesn't itself know if the developer's machine was asleep/off at the scheduled time
  (a missed run is silently skipped, not queued) — acceptable for a hobby project with no SLA
  (the resume-on-next-invocation design in §2.3/§2.4 already means a missed nightly run just
  picks up more backlog next time it does run, not a correctness problem, only a latency one).

**Recommendation: B.** Cron plus the one shared driver, with per-job cadence documented in a
committed example crontab rather than invented scheduler machinery — the same "reuse infra you
already have" instinct D30 and D26 already applied to reporting scripts and record/replay tests.

## 3. Recommendation (*proposed*)

1. **Orchestrator shape (§2.1):** one thin driver library, `tools/orchestrator/driver.py`, no
   daemon, parameterized per job by a small batch-spec YAML in `config/jobs/`. One driver
   invocation = one `RunContext`-scoped run (D26). Adding a job kind = one enumerator function +
   one YAML file.
2. **Checkpoint unit & storage (§2.2):** whatever grain each job's own `work_item_source` already
   enumerates (cell, theme, fact, source) — no forced global granularity. State lives in a local,
   private, non-git SQLite file in the same private tier as D26's cache/cost log
   (`orchestrator_checkpoint` table, one row per (run, item)). This checkpoint is driver-level
   bookkeeping only; the `LangAtlas-Record-Key` git trailer (D36) stays ground truth for "did it
   actually land," looked up before re-attempting anything not cleanly marked `done`.
3. **Budget hard-stops (§2.3):** `RunContext` raises typed `BudgetExceeded` before crossing a
   declared cap; the driver catches it (and `ClaudeLimitSignal`, §2.4, via the same path with a
   different `reason`), checkpoints the in-flight item as `blocked` (not failed — still valid and
   re-attemptable), records a run-level pause, and exits with a distinct code. **Resume is plain
   re-invocation** — no separate resume mode, matching D27's own idempotent-resume philosophy one
   layer up.
4. **Claude-limit handling (§2.4):** on `ClaudeLimitSignal`, apply a conservative fixed cool-down
   (proposed 4 hours, no calibration data exists yet) before any resume attempt; a
   too-early re-invocation no-ops rather than re-triggering the same limit. "Alerting" in this
   solo-dev, no-new-infra project is the run halting plus two already-cheap surfaces: standard
   cron mail and a small glanceable `orchestrator/status.json` (feeding a new `report.py`
   subcommand, D41) — no bespoke notification service.
5. **Scheduling (§2.5):** plain cron on the developer's machine, one line per scheduled job
   (nightly verification/controversy batch, monthly link-checker, quarterly edition-check, the
   18-month backstop sweep's monthly cadence-check), each invoking the same driver against a
   different batch spec. A committed `config/jobs/crontab.example` documents intended cadence;
   the developer's real crontab is local machine state.

## 4. Open questions for the developer

1. **Is the per-language sweep pipeline (D5) itself run unattended via cron, or always
   developer-initiated by hand?** Everything above works either way (the driver doesn't care who
   invokes it), but it changes whether sweep runs need the same "missed run" tolerance as the
   background jobs or can assume prompt developer attention.
2. **Is the proposed 4-hour Claude-limit cool-down (§2.4) reasonable as a starting default, or
   does the developer have a better instinct** (e.g. from having already hit Pro usage limits and
   observed how long they take to clear) that should replace the guess?
3. **Is cron mail (`MAILTO`) actually configured/wanted on the developer's machine**, or is the
   `orchestrator/status.json` + manual `report.py` check-in the only alerting the developer
   actually intends to rely on? (Affects whether cron-mail setup is worth documenting at all.)
4. **Is a committed `config/jobs/crontab.example` (documentation only, not live) worth
   maintaining**, or is that one file's worth of legibility not worth the upkeep given the
   developer's real crontab is the actual source of truth regardless?
5. **Does the 18-month backstop sweep's "checked monthly, no-ops until due" pattern (§2.5) match
   the developer's expectation**, or would a coarser trigger (e.g. a manually-run job the
   developer remembers to invoke roughly every year and a half) be simpler and equally
   sufficient given the low stakes of a few weeks' slip either way?

## 5. New brainstorm topics surfaced

None. Every sub-problem in the checklist's topic-35 entry resolves within this brainstorm's own
scope (the driver, checkpoint design, budget-stop mechanism, Claude-limit pause/resume, and the
four named scheduled jobs' cadence) by directly consuming interfaces D26, D36, and D41 already
built and handed here — there is no piece left over that needs its own dedicated design pass.

## Sources

- D26 (`context/decisions.md`) — `RunContext` budget block and cache location.
- D36 (`context/decisions.md`) / [brainstorms/27-agent-runner-commit-protocol.md](27-agent-runner-commit-protocol.md)
  — `LandResult` union, `LangAtlas-Record-Key` idempotency trailer, the explicit hand-off to this
  topic.
- D41 (`context/decisions.md`, proposed) / [brainstorms/32-pipeline-observability-prompt-registry.md](32-pipeline-observability-prompt-registry.md)
  — `ClaudeLimitSignal` shape and its explicit hand-off of pause/resume logic to this topic.
- D25 (`context/decisions.md`) — 18-month backstop sweep, ~200-facts/night nightly budget.
- D37 (`context/decisions.md`) / [brainstorms/28-locator-normalization-ingestion-qa.md](28-locator-normalization-ingestion-qa.md)
  — monthly link-checker, quarterly edition-check job definitions.
