# 27 — Agent-Runner Commit Protocol & Failure Bot

> Backlog brainstorm for LangAtlas. Topic: the concrete git-level mechanics by which an agent
> run actually lands a commit on `main` under D1's no-PR-gate architecture — fetch-rebase-retry,
> the GitHub App committer identity, commit granularity, gating a push on main's own CI health,
> the failure bot's auto-revert safety envelope, the halt/resume signal this layer exposes
> upward, and (lightly, per the judgment call in §2.8) a serializer for the day more than one
> runner commits concurrently. Binding context: `context/decisions.md` D1 (git-is-the-database;
> **"Agents commit directly; a fact is admissible because it is backed by a verified source, not
> because a human reviewed it. The automated verification gate (D4) + CI checks are the only
> gates."** — the load-bearing premise this whole brainstorm implements the mechanics for), D13
> (validated-artifact CI pattern; states the seed this brainstorm expands: **"the agent runner
> runs the same fast offline validators pre-commit (refuses to commit on failure), publication is
> last-green (red main publishes nothing), and a failure bot auto-reverts only
> mechanically-safe tip commits, otherwise halts the runner and files an issue. Agents commit
> under a GitHub App identity."**), D14 (DCO, not CLA — scoped to human contributors; this topic
> has to say what DCO means for an automated committer, see §2.2), D18 (chat logging; "one
> transcript per batch" — a *different* batch axis than this topic's commit granularity, see the
> note in §2.3), D20/D23 (fact granularity: the authoring unit is one record per feature
> instance with per-field `sources:`; per-field facts are *derived* at build time, never authored
> directly — the key fact this topic's commit-granularity design turns on), D24 (verifier verdict
> vocabulary — the pre-commit gate in §2.3/§2.5 is a fast mechanical validator, not a re-run of
> the full entailment pipeline, which already ran before a record is proposed for commit), D26
> (`RunContext` provider layer: budget hard-stops with a resumable checkpoint — the layer this
> topic's halt signal reports into), D32 (contribution funnel's graduated external-authorship
> posture: source/proposal PRs from external humans now, developer-skimmed full fact-PRs later,
> auto-merge reserved indefinitely — **a different trust domain from this topic**, see §2.8 for
> why the two must not be conflated even though brainstorm 18 flagged a possible fold-in here).
>
> **Boundary with topic 35 (run orchestrator & checkpointing):** topic 35 owns the batch-run
> driver above the provider layer — deciding *when* to start/stop/resume a run, budget
> bookkeeping across an entire overnight session, and where checkpoint state physically lives.
> This brainstorm does not redesign that. What it does design is the *interface* the commit
> protocol exposes so topic 35's driver has something concrete to call and react to (§2.6's
> `LandResult` vocabulary and the content-derived idempotency key) — the commit protocol is a
> library topic 35 calls once per record, not a competing orchestrator. Also touches, without
> redesigning: topic 40 (validator/normalizer CLI — the one offline tool this topic assumes is
> shared, verbatim, between CI and the agent runner's pre-commit gate, per D13's own wording) and
> topic 38 (questionnaire compiler — upstream of this topic, not referenced further). All
> proposals below are *proposed* until the developer ratifies.

## 1. Problem framing

D1 removed the human merge gate; D13 sketched, in one paragraph, that this is survivable because
the runner pre-validates before committing, publication only ever happens from a green `main`,
and a failure bot cleans up the rare bad commit that slips past pre-validation. That paragraph is
a policy statement, not a protocol. Five things it doesn't say, and this brainstorm has to:

1. **How does a commit actually reach `main` without clobbering someone else's concurrent work?**
   Even with a single runner today, a run can be interrupted mid-push (network blip, a Claude Code
   Pro usage-limit hit mid-session) and resumed later against a `main` that has moved. With more
   than one runner (§2.7's future case), the collision surface is real, not hypothetical.
2. **Who is "the agent" as a git committer?** D13 already named GitHub App over PATs; this topic
   has to say what permissions that App actually needs, and reconcile the App's automated commits
   with D14's DCO policy, which was written with human submitters in mind.
3. **What is the unit of a commit?** D20/D23 already answered the *authoring* unit (one YAML
   record); this topic has to decide whether that's also the *commit* unit, or whether an agent
   turn that touches several records should land as one commit, several, or something else.
4. **What does "main is green" mean operationally, and what happens when it isn't?** D13 commits
   to "red main publishes nothing" on the *publish* side; this topic has to decide what the
   *commit* side does when it discovers main is currently red before it would push.
5. **What exactly is a "mechanically-safe tip commit," concretely enough that a script (not a
   judgment call) can decide whether to auto-revert it or hand off to a human?** D13's one
   sentence names the concept; nothing yet defines its boundary.

Scale/urgency check: near-term, this runs as a single unattended runner, one Claude Code Pro
session at a time, well below the concurrency where races are common — but D13, D18, and D26 are
all already written assuming this machinery exists (chat logging assumes commits happen; budget
hard-stops assume there's something safe to resume into), so the protocol needs to be correct
from the first real run, not bolted on retroactively once it breaks. The failure bot in
particular is exactly the kind of "cheap now, expensive to retrofit" surface D18's chat-logging
decision already called out for a different reason — safety nets are worth building before the
first incident, not after.

## 2. Options with trade-offs

### 2.1 The fetch-rebase-retry loop

**Option A — GitHub Contents/Git-Data API only, no local clone.** Every commit goes through
GitHub's REST API: for a single-file record write, `PUT /repos/.../contents/<path>` with the
blob's current `sha` gives free optimistic concurrency (a stale `sha` returns `409`, meaning
someone else moved the file since the runner last read it); for a multi-file commit, the Git Data
API (create blobs → create a tree → create a commit → update the `refs/heads/main` ref with an
expected `sha`) offers the same optimistic-concurrency check at the ref level.

- Pros: no local git state to keep consistent between runs — every call is stateless and
  naturally idempotent-checkable against the API's own response. The single-file case is
  genuinely elegant: conflict detection is a `409`, not a manual diff.
- Cons: the multi-file path (create blob × N, create tree, create commit, update ref) is a lot of
  API round-trips per commit, and D23's per-file sharding means a single agent turn realistically
  does touch more than one file (a new feature instance plus, occasionally, a same-turn edge
  update) — so the multi-file path isn't a rare case this can lean on the simple single-file API
  for. No local working tree also means the runner can't easily run topic 40's validator CLI
  *before* committing (that CLI needs files on disk) without first materializing them elsewhere,
  which erodes most of the "no local state" simplicity this option was chosen for.

**Option B — a persistent local clone, `git fetch` + naive re-push loop (no `rebase`, just retry
the same commit against the new tip).** Keep one working clone; on push rejection, `git fetch`,
`git reset --hard origin/main`, re-apply the pending change from the runner's own in-memory
record of what it meant to write, re-commit, re-push.

- Pros: simple mental model, no `rebase` machinery to reason about conflicts.
- Cons: "re-apply the pending change" is doing the same job `git rebase` does, just reimplemented
  by hand and worse — it has no principled way to detect that the *target file itself* changed
  underneath it (e.g. a rare same-file race) short of re-diffing, which `git rebase` already does
  correctly via three-way merge. This is reinventing rebase without its conflict detection.

**Option C (recommended) — a local git clone/worktree per run, real `git fetch` + `git rebase
origin/main` + push, retried on rejection.** Standard flow: `git fetch origin`, `git rebase
origin/main` (the pending commit(s) are the runner's own unpushed local commits — see §2.3 for
what "the pending commit(s)" means concretely), run topic 40's validator against the rebased
worktree, `git push origin HEAD:main` (fast-forward only, never `--force`). On non-fast-forward
rejection (meaning someone else landed in between the fetch and the push): fetch again, rebase
again, revalidate, retry the push. Give-up criteria: whichever comes first of **5 retries** or a
**3-minute wall-clock window** for a single record's landing attempt — then the record is not
dropped (its content and verification result stay valid and re-attemptable), but this landing
attempt reports `contention_exhausted` (§2.6) rather than looping forever.

- Pros: uses git's actual conflict machinery (three-way merge) rather than reimplementing a worse
  version of it; because D23 already shards edges by from-feature and puts each feature instance
  in its own file specifically to keep concurrent agent commits from touching the same file, the
  overwhelmingly common case is a **content-free rebase** — the rejection was purely "the tip
  moved," not "someone touched the same lines," so almost every retry is a cheap replay with zero
  merge work. True content conflicts (two runs landing different values into literally the same
  file's same field before either pushes) are the rare case D23 was explicitly designed to make
  rare, and when they do happen, rebase's three-way merge either resolves them cleanly (different
  fields, same file) or produces a real conflict marker the runner is right to refuse to
  auto-resolve — that case is *not* mechanically safe and should fall out of the retry loop into
  a halt (§2.5's criteria apply to landing failures generally, not only post-hoc reverts).
- Cons: needs a persistent local clone kept fresh across runs (modest operational surface — a
  clone that's occasionally garbage-collected/re-cloned if it drifts too far, standard git
  hygiene, nothing new). The validator (topic 40) has to run once per rebase attempt, not once
  per record — a small, bounded cost given the retry ceiling above.

**Recommendation:** Option C. It is the only option that gets git's real conflict resolution for
free while matching D23's design intent (sharded files → conflict-free rebases in the common
case) instead of fighting it with a stateless API that doesn't know how to run the local
pre-commit validator, or a hand-rolled retry loop that reimplements rebase badly.

### 2.2 GitHub App identity and DCO interaction

D13 already ratified **GitHub App over PATs**; this section works out what that means
concretely, since D13's sentence names the choice without specifying scope.

**Permissions (proposed, narrowest sufficient set):** `Contents: write` (commit/push),
`Metadata: read` (implied by any App), `Issues: write` (the failure bot files halt/revert issues,
§2.5), `Checks: read` and `Statuses: read` (is-main-green gating, §2.4). Explicitly **not**
`Pull requests: write` — the agent runner's own lane never opens PRs (D1), so granting that scope
would be an unused privilege on the exact kind of credential D13 was trying to keep narrowly
scoped by choosing an App over a PAT in the first place. If topic 18's external-PR skim (§2.8)
ever needs PR-scoped permissions, that is a strong argument for a **second, separately-scoped
App** rather than widening this one — the two lanes are different trust domains (D32 already
makes this point about the *policy*; the credential boundary should mirror it).

**Commit attribution:** commits land as the App's installation identity
(`langatlas-bot[bot]` in GitHub's UI, distinct from the developer's own commits and from any
future external contributor). This gives git blame a clean three-way split (bot / developer /
external contributor) for free, and lets the failure bot's revert criteria (§2.5) key on
*author identity* as a hard, mechanically-checkable precondition rather than a heuristic.

**Token handling:** GitHub App installation tokens are short-lived (≈1 hour). The `RunContext`
(D26) is the natural place to own token refresh — it already owns budget enforcement and the
D18 transcript writer as the two other things every provider call must pass through; adding "get
a fresh installation token before any git operation" as a third `RunContext` responsibility keeps
the same non-bypassable-wrapper property D26 was built around, and — same reasoning D18 already
applied to fetched-source content — the token itself must never be echoed into anything that
gets logged into a published transcript.

**DCO interaction (the genuinely open piece):** D14 ratified DCO over CLA for *human*
contributors, meaning a `Signed-off-by:` trailer asserting the individual signer has the right to
contribute the content. An automated commit has no individual human "signing off" per-commit in
that sense — the developer, as the person who operates and is legally responsible for the
pipeline, is the closest analogue to "the contributor" for the runner's own commits. Two
plausible conventions:

- **(a) Every agent-runner commit carries `Signed-off-by: <developer name/email>`**, i.e. the DCO
  trailer names the developer as the accountable party for everything the pipeline produces
  (consistent with git's own DCO text, which is about the *right to contribute* the content, not
  about who typed it).
- **(b) A documented CONTRIBUTING.md carve-out** stating that GitHub App-authored commits under
  the `langatlas-bot[bot]` identity are DCO-exempt by design, because the App's authorization to
  commit is itself the developer's act of contribution (installing the App on the repo *is* the
  sign-off, once, rather than per-commit) — with the DCO requirement applying, as originally
  intended, only to human-submitted PRs (D14/D32's separate lane).

This brainstorm leans toward **(b)** as simpler and avoiding a slightly fictional per-commit
trailer naming a person who didn't literally review that commit, but flags it as needing an
explicit developer call (§4.1) rather than assuming — DCO policy touches the project's legal
posture (D14) and shouldn't be decided as a side effect of a commit-mechanics brainstorm.

### 2.3 Batching per commit

The task brief asks whether a turn produces one commit, one fact, or a batch. D20/D23 already
answers half of this: **facts are not authored artifacts** — an agent never directly writes "a
fact"; it writes or updates a **record** (one feature-instance file, one sharded edge file, one
rule file), and per-field facts are *derived* from that record at build time. This means "one
commit per fact" (the brief's second option) is not actually available without the runner
duplicating brainstorm 09's derivation logic just to figure out where fact boundaries fall inside
a record it already wrote whole — the same "compute once, ship as data" principle brainstorm 26
already applied to the dataset bundle's `facts` table applies here in the opposite direction:
derivation logic belongs in exactly one place (the build pipeline), and the commit layer should
not need to know where fact boundaries are at all.

That leaves the real choice at the **record** level:

**Option A — one commit per agent turn**, whatever set of records a single turn happened to
touch (potentially several feature-instance files plus an edge file in one commit).

- Pros: fewest commits, fewest pushes, most closely mirrors "what actually happened in one LLM
  turn" as a unit of history.
- Cons: bundles unrelated records into one atomic commit. This directly hurts §2.5's auto-revert
  precision — if one record in a five-record commit fails a mechanical check, either the whole
  commit reverts (dragging down four good records) or the failure bot has to cherry-pick, which
  is exactly the kind of judgment call D13 reserves for "not mechanically safe." **Rejected** as
  the default: it manufactures unsafe-to-revert situations that a finer commit grain would avoid
  entirely.

**Option B — one commit per touched record file**, generated deterministically regardless of how
many records a single agent turn produced. A turn that writes five records yields five
independent commit attempts, each running the full fetch-rebase-retry cycle (§2.1)
independently — a contention or validation failure on one file never blocks or contaminates the
other four.

- Pros: the natural unit given D20's authoring model (one file = one record = one self-contained
  unit of admissibility); maximizes auto-revert precision (§2.5 can revert exactly the bad record,
  never collateral-damaging a good one); matches D23's sharding intent at the git level too — the
  whole point of sharding edges by from-feature was to make independent files independently
  landable, and one-commit-per-file is what actually cashes that design in at commit time, not
  just at merge-conflict-avoidance time.
- Cons: more commits, more pushes, more CI-trigger events if `main`'s CI runs on every push
  (a CI-configuration concern, not this topic's — D13's daily `data-vN` tagging already decouples
  *publication* cadence from commit count, so extra commits don't mean extra publishes, only
  extra CI runs to validate them, which is exactly what should happen for each independently
  admissible unit).

**A clarifying note on "batch," since the word is already used elsewhere for a different axis:**
D18 settled "one transcript per batch" for *chat logging* — one run's-worth (or one sweep
batch's-worth) of conversation becomes one transcript file, with per-claim `#msg-N` anchors
letting individual facts point into the right spot in that one file. That is a **logging**
granularity decision, orthogonal to this section's **commit** granularity decision. A single
D18 transcript can and typically will span many of this section's individual record commits (a
transcript documents "what happened in this run"; each commit documents "one record landed").
The two are related only via the commit message trailer described below, not via a shared unit.

**Recommendation:** Option B, with the commit message on every record commit carrying a
structured trailer connecting the two batching axes and enabling §2.6's idempotent-resume check
in one place:

```
<one-line summary of the record change>

LangAtlas-Record-Key: <sha256 of final file content + target path>
LangAtlas-Chat-Run-Id: <run_id>#msg-<N>
```

### 2.4 Is-main-green gating

Before a runner pushes, it needs to know whether `main`'s current tip is green — not because a
red tip blocks the *push itself* mechanically (git doesn't know about CI status), but because
D13's failure-closed posture ("red main publishes nothing") is undermined in spirit if the runner
keeps stacking new commits on top of a `main` that's already known-broken, making the eventual
diagnosis (which commit actually broke things?) harder for no benefit.

**Option A — block entirely while red.** The runner refuses to do *any* work — drafting,
verifying, or committing — until `main` goes green, polling on an interval.

- Cons: wasteful. Drafting and the D24 verification pipeline don't depend on `main`'s CI state at
  all; stalling the entire run over a CI-status check that only actually matters at the final
  push step throws away hours of an unattended overnight run's budget for no reason.

**Option B (recommended) — decouple "prepare" from "land."** The runner keeps drafting and
running records through the full local pipeline (D24 verification already happened upstream of
this topic; what's local *here* is topic 40's fast offline validator, §2.1) regardless of
`main`'s CI state — none of that reads or writes `main`. Only the final step, "check is-main-green
immediately before push," gates on CI status (via the App's `Checks:read`/`Statuses:read`
permissions against `main`'s current tip). If green: proceed with §2.1's push loop. If red (or no
status reported yet — treat "no status" as "not confirmed green," never as an implicit pass): do
**not** push. Hold the record's already-validated, ready-to-land state in a local queue and
report `blocked_red_main` (§2.6) rather than either pushing anyway or discarding the work.

- Pros: no wasted verification/drafting effort; the actual gate (don't push onto red) is exactly
  as strict as D13 intends, applied at the one step where it's mechanically meaningful.
- Cons: needs a small local queue for records that are ready-to-land-but-blocked, which has to
  survive a pause/resume cycle (handled by §2.6's durable-state contract, not a new mechanism).

**What "red" typically means here, and why the runner shouldn't try to fix it itself:** a red
`main` is either (a) the failure bot's own miss — a bad tip commit that slipped past pre-commit
validation and wasn't judged mechanically-safe to auto-revert (rare, and exactly the halt case
§2.5 already routes to a human), (b) CI infrastructure flake, or (c) a schema/tooling change the
developer landed directly. In none of these cases is "the agent runner" the right actor to
resolve the redness — its only correct behavior is to stop landing more on top of it and signal
clearly (§2.6), leaving remediation to whatever already-designed channel applies (the failure
bot's own issue, a flake that resolves itself on CI retry, or the developer's own follow-up).
Whether a bounded polling wait (e.g. 30 minutes) elapses before escalating from
`blocked_red_main` to a stronger halt signal is left to topic 35's orchestrator, since that's a
budget/patience trade-off belonging to the run driver, not to this protocol layer.

### 2.5 Auto-revert safety criteria

This is the concrete definition D13's one sentence deferred: what makes a tip commit
"mechanically safe" to auto-revert, versus a case that must halt the runner and file an issue for
human or fresh-session remediation.

**Proposed checklist — all four must hold, or the failure bot does not touch `main`:**

1. **The failing commit is `main`'s current tip.** Reverting anything else risks conflicting with
   commits layered on top, or silently reordering history in a way nobody asked for. If `main`
   has already moved past the bad commit by the time it's detected, this condition fails by
   construction — halt and file an issue instead; a non-tip revert is a judgment call, not a
   mechanical one.
2. **The failing commit's author is the GitHub App bot identity** (§2.2). Auto-revert is a safety
   valve for the runner's *own* mistakes only — never for a developer's manual commit, and never
   for an external contributor's merged PR (D32's separate trust domain, §2.8). Keying this off
   commit author identity, which git already records immutably, makes the check exact rather than
   heuristic.
3. **The failure is a deterministic, reproducible failure of topic 40's offline validator** —
   schema validity, referential integrity, citation-locator well-formedness, D23's fact-id
   collision check, D25's identity constraints — **not** a flaky/transient check (a link-checker
   timeout, an infrastructure hiccup). Before reverting, CI reruns the failing check exactly
   **once** to distinguish flake from real failure; a failure that doesn't reproduce on that one
   rerun is treated as `main` being fine and the failure bot takes no action (this also protects
   against the failure bot itself becoming a source of unnecessary reverts on noisy checks).
4. **`git revert <sha>` applies cleanly, with no conflicts.** If the revert itself would conflict
   — meaning something already depends on the bad commit's content in a way that doesn't cleanly
   undo — that is definitionally not "mechanically safe," and the failure bot must not attempt a
   manual conflict resolution; it halts instead.

**If all four hold:** auto-revert immediately. Push the revert commit through the same
fetch-rebase-retry mechanics (§2.1) — a revert push can race exactly like any other push and gets
no special exemption. File a GitHub issue (auto-labeled, e.g. `auto-revert`) documenting the
reverted sha, the validator output that triggered it, and a link into the D18 transcript via the
`LangAtlas-Chat-Run-Id` trailer already on the reverted commit — the same provenance path every
other fact-linked-to-chat mechanism already uses, applied to failures instead of successes.

**If any condition fails:** the failure bot does not touch `main` further. It halts the runner
(no further commit attempts this run — a strong signal, not `blocked_red_main`'s soft pause) and
files a GitHub issue with full diagnostic context (failing sha, validator output, which of the
four conditions failed and why) for human or fresh-agent-session remediation — the same
`langatlas-kb` issue tracker D9 already uses for human fact challenges, just a different
auto-applied label so the two failure classes (content disputes vs. mechanical breakage) don't
get mixed in the same queue.

**Explicitly out of scope for auto-revert, by design:** content disputes (a later-challenged
fact — D9's human channel, unrelated to this mechanism), controversy/partial-verification flags
(D25 — these are *supposed* to land and render visibly flagged, not get reverted; reverting a
correctly-flagged-as-disputed fact would undermine D25's entire non-suppression policy), and
anything the D24 verifier already gated on entailment (a verified fact that later turns out to be
contested isn't a bad commit — it's D25's dispute axis doing its job).

**Repeat-revert circuit breaker:** if the failure bot auto-reverts more than **2 commits within a
single run**, it halts anyway, even though each individual revert satisfied all four conditions.
Repeated reverts are themselves evidence something systemic is wrong (most plausibly: the
runner's local pre-commit validator has drifted from CI's copy of topic 40's tool, meaning every
commit this run produces is silently bad) — continuing to auto-revert one-by-one stops being
"safe" in aggregate even though each instance passed the checklist. This mirrors §2.6's design
principle generally: individual-event safety and run-level safety are checked separately, and a
run-level pattern can override an individually-safe per-event verdict.

### 2.6 Halt/resume signaling — the interface handed to topic 35

Per the boundary stated in the header, this section designs the *signal*, not the orchestrator
that consumes it. The commit protocol is a library topic 35's driver calls once per record; it
needs to return enough structured information for that driver to decide what "pause the run,"
"resume it," or "stop and wait for a human" concretely mean — decisions that belong to topic 35,
not here.

**Proposed result vocabulary** (a small discriminated union returned from "attempt to land this
record," not a raw boolean or a thrown exception, so the driver can pattern-match rather than
parse error strings):

- `landed(commit_sha)` — success; safe to continue with the next record.
- `blocked_red_main(since, last_checked)` — §2.4's soft pause; the record's validated state is
  queued, not lost; the driver decides whether to keep the runner busy on other records, poll,
  or pause the whole run.
- `contention_exhausted(retries, last_conflict_summary)` — §2.1's retry ceiling was hit; the
  record itself is still valid and re-attemptable (idempotent retry, not a failure of the
  content), so the driver may retry immediately, defer to later in the run, or checkpoint and
  resume next session.
- `reverted(commit_sha, reason)` — informational: something this runner landed earlier in the
  run (or a prior run) was auto-reverted by the failure bot (§2.5) between attempts. The driver
  should treat the underlying fact as "back to not-landed" and decide whether to re-queue it for
  re-drafting rather than silently treating the run as complete for that record.
- `unsafe_halt(commit_sha, diagnostic)` — §2.5's hard-halt case. The driver **must** stop issuing
  new commit attempts until a human or fresh session resolves the filed issue — this is D13's
  "halts the runner and files an issue" made concrete as a typed signal instead of a side effect
  the driver would otherwise have to notice on its own.

**Idempotent resume — the load-bearing property.** A run can pause between "record locally
verified and validated" and "record actually landed on `main`" for reasons entirely outside this
protocol's control: a budget hard-stop (D26), a Claude Code Pro usage-limit hit mid-session, an
unhandled error. On resume, the commit protocol's land-attempt function must be safe to call
again for the same record **without double-committing**. The mechanism: the
`LangAtlas-Record-Key` trailer already specified in §2.3 (a content-derived hash of the record's
final file content + target path) is checked *before* attempting any push — a cheap
`git log --grep` lookup against `main`'s reachable history for that exact key. If a commit with
that key already exists, the attempt short-circuits to `landed(existing_sha)` immediately, with
no re-push. This makes "did I already commit this" an exact, git-native lookup rather than a
fuzzy question topic 35's own checkpoint file would otherwise have to answer alone — belt and
suspenders: topic 35 keeps its own checkpoint of attempted records for driver-level bookkeeping,
but the git trailer is ground truth that survives even a corrupted or lost checkpoint file, since
checkpoint state and actual repository state can never disagree once this exists.

**What this layer hands topic 35 to persist, without dictating how:** for any record left in
`blocked_red_main` or `contention_exhausted` state at pause time, the durable unit this protocol
needs rehydrated on resume is: the record's file path, its content hash (== the eventual
`LangAtlas-Record-Key`), and a reference to the D24 verification result that already cleared it
(not the verification result itself — that already lives wherever D24's pipeline persists it).
Where and how that gets written to disk between sessions is topic 35's checkpoint-file design to
own; this brainstorm only specifies the shape of what needs to survive.

### 2.7 Commit queue if runners multiply

Today: one runner, gated by Claude Code Pro session/usage limits, is the realistic near-term
shape. The design should not preclude more, but shouldn't build for a scale that doesn't exist
yet either — the same "don't invent for a future that hasn't arrived" discipline already applied
in brainstorm 20 (§2.1's stub-sweep tier) and brainstorm 16 (deferring the heavier debate
instrumentation until real volume exists).

**Option A (recommended for now) — no queue; rely on §2.1's optimistic concurrency.** Each
runner independently fetches, rebases, and races to push; the loser of a race simply retries
(§2.1). At low concurrency (2–3 runners) this is cheap specifically *because* D23's file sharding
means most races are "who pushes first," not real content conflicts — the losing runner's retry
is a fast rebase-and-replay, not a redo of verification work. This degrades gracefully rather
than catastrophically as concurrency creeps up from 1: more retries, not more correctness risk.

**Option B — a lightweight lease/lock for the push step only** (drafting and verification stay
fully parallel; only the "land it" critical section serializes). Concretely: a single small
`RUNNER_LOCK` file whose content is updated via the GitHub Contents API's SHA-based optimistic
concurrency, acting as a mutex — whoever successfully `PUT`s a new value with the current `sha`
holds the lease for their push window; releasing is another `PUT`. No new infrastructure, reuses
a mechanism already described in §2.1's Option A as available (just applied narrowly here, to one
coordination file, instead of to every commit).

- Pros: turns "many runners racing" into "one runner pushes at a time," eliminating retry storms
  entirely once concurrency is high enough that Option A's degradation stops being graceful.
- Cons: a genuine new moving part (lease acquisition/release/timeout-on-crash logic) — not
  justified while D23's sharding keeps Option A's failure mode cheap.

**Option C — a real coordination service** (Redis, SQS-alike). **Rejected outright**: directly
contradicts CLAUDE.md's absent-on-purpose list (D12: "no message queues"), and there is no
plausible scale at which this solo-maintained project's commit volume would need it.

**Recommendation:** Option A now, with Option B named as the specific, already-scoped escalation
path — not designed further here — for if/when the developer actually runs concurrent runners (a
trigger event, not a number to hit, mirroring D34's own "the trigger is the event, not a
threshold" framing for the Builder's public-library backend). No new backlog topic needed for
this: Option B is fully specified above (a single Contents-API-mediated lock file) and is a small
enough addition to implement directly inside this topic's own eventual build, not a separate
design pass.

### 2.8 External-PR abuse handling — judgment call: fold-in, not a full section

The checklist entry names this as a possible fold-in *or* a full section "if it grows past a
fold-in note." Making that call here: **fold-in note, not a full section**, for three reasons.

First, D32 already settled that external-human contribution is a **structurally different trust
domain** from this topic's own concern (the project's own GitHub App committing its own agents'
verified output) — brainstorm 18 flagged the possible fold-in specifically because "both touch
the repo's commit hygiene," not because the underlying problems are the same. Mixing them here
would blur exactly the boundary D32's graduated posture and this brainstorm's §2.2 credential
separation both depend on staying sharp.

Second, D32's own scope for the near term is narrow by design (Option C: source/candidate-
proposal PRs only, mechanically checkable, no entailment judgment, no auto-merge) — there is no
external-contributor traffic yet to abuse, and per the same evidence-first instinct D30 already
applied to debate instrumentation ("defer any scored simulator until phase-1 onboarding produces
real volume"), designing a detailed abuse-mitigation protocol against a threat model with zero
observed instances risks over-building against guessed attack patterns rather than real ones.

Third, the cheap, load-bearing mitigation that *is* worth naming now costs nothing to state and
needs no new design: GitHub Actions natively supports **requiring maintainer approval before
workflows run for first-time contributors** — a repo setting, not custom code — which directly
answers the checklist's "CI cost of spam PRs" concern (a spam PR simply never triggers a CI run
at all until the developer looks at it once) without building any bespoke rate-limiting or
scoring system. Combined with GitHub's native "first-time contributor" labeling (used to flag
review queues), this is sufficient scaffolding for the current zero-volume reality.

**What "provenance/scope skim" concretely checks for, stated briefly since D32 left it as a
named-but-unspecified concept:** given D32's Option-C scope (Source records + candidate-proposal
files only, not fact claims), the skim is not a content-accuracy judgment — that's still the D24
verifier's job even for these mechanically-checkable record types. It is: does the PR touch only
the file types Option C permits (a `Source` YAML record or a `candidate-*` proposal file, nothing
under `instances/`, no edits to existing files outside the contributor's own new additions); is
it single-topic (one source or one proposal per PR, not a bulk drop); does the bibliographic data
in a `Source` record resolve to a real, checkable identifier (DOI/ISBN/URL) rather than being
fabricated. All three are yes/no checks a script can run in CI — genuinely mechanical, matching
D32's own framing ("no entailment judgment involved") — which is itself an argument this doesn't
need a bespoke design pass: it's an extension of topic 40's validator CLI scope, not a new
protocol.

**If this changes:** should real external-PR volume ever produce actual spam/abuse patterns, that
evidence is precisely the trigger for promoting this from a fold-in note to its own brainstorm
(already flagged as a possible future topic in brainstorm 18's §5 and carried forward, unchanged,
in §5 below) — consistent with the same evidence-before-design posture applied throughout D30's
and this section's own reasoning.

## 3. Recommendation (*proposed*)

1. **Fetch-rebase-retry (§2.1):** a persistent local clone/worktree; `git fetch` + `git rebase
   origin/main` + fast-forward-only `git push`, retried on non-fast-forward rejection. Give up
   after **5 retries or 3 minutes**, whichever first, reporting `contention_exhausted` (§2.6)
   rather than looping indefinitely or dropping the record. Runs topic 40's validator once per
   rebase attempt against the rebased worktree.
2. **GitHub App identity (§2.2):** scope to `Contents: write`, `Issues: write`, `Checks: read`,
   `Statuses: read` — deliberately no `Pull requests` scope on this App, since the agent runner's
   own lane never opens PRs; a second, separately-scoped App if/when topic 18's external-PR skim
   needs PR permissions. Token refresh owned by `RunContext` (D26), never logged (D18). DCO
   handling for automated commits needs an explicit developer call between (a) a per-commit
   `Signed-off-by: <developer>` trailer or (b) a documented CONTRIBUTING.md carve-out treating
   App-installation itself as the sign-off — this brainstorm leans (b) but flags it open (§4.1).
3. **Commit granularity (§2.3):** one commit per touched record file, not per agent turn and not
   per derived fact (facts have no independent existence to commit — D20/D23). A turn producing
   five records yields five independently landed, independently revertable commits. Every commit
   carries a `LangAtlas-Record-Key` trailer (content hash + path) and a `LangAtlas-Chat-Run-Id`
   trailer (linking to D18's separate, coarser transcript-batch granularity).
4. **Is-main-green gating (§2.4):** decouple preparation (drafting, D24 verification, topic-40
   local validation) from landing. Only the final push step checks `main`'s CI status; on red (or
   unknown), hold the record in a local ready-to-land queue and report `blocked_red_main` rather
   than pushing or discarding work. The runner never attempts to fix a red `main` itself.
5. **Auto-revert safety criteria (§2.5):** all four must hold — tip commit, bot-authored,
   deterministic/reproduced-once validator failure, clean `git revert` — or the failure bot halts
   and files an issue instead of acting. A run-level circuit breaker halts after **2 reverts in
   one run** even if each individually passed the checklist. Content disputes, controversy flags,
   and anything D24 already gated stay explicitly out of auto-revert's scope.
6. **Halt/resume interface (§2.6):** a typed `LandResult` (`landed | blocked_red_main |
   contention_exhausted | reverted | unsafe_halt`) is this protocol's entire contract with topic
   35's orchestrator. Idempotent resume is guaranteed by checking the `LangAtlas-Record-Key`
   trailer against `main`'s reachable history before any push attempt — ground truth that
   survives even a lost orchestrator checkpoint.
7. **Multi-runner scale (§2.7):** no queue for now — rely on §2.1's optimistic concurrency, cheap
   specifically because D23's sharding keeps real content conflicts rare. A single
   Contents-API-mediated `RUNNER_LOCK` lease is the named, already-specified escalation path if
   concurrent runners become real; no new backlog topic needed for it.
8. **External-PR abuse handling (§2.8):** stays a fold-in note, not a full section, given zero
   current external-PR volume and D32's already-narrow near-term scope. Immediate, zero-code
   mitigation: GitHub's native "require approval for first-time-contributor workflow runs"
   setting. The "provenance/scope skim" is three mechanical checks (permitted file types only,
   single-topic PR, resolvable bibliographic identifiers) — an extension of topic 40's validator
   scope, not a new protocol. Promote to a full brainstorm only once real abuse evidence exists.

## 4. Open questions for the developer

1. **DCO convention for agent-runner commits (§2.2)** — a per-commit `Signed-off-by: <developer>`
   trailer, or a documented CONTRIBUTING.md carve-out treating the GitHub App's installation
   itself as the one-time sign-off, with per-commit DCO trailers reserved for human-submitted PRs
   only? This brainstorm leans toward the carve-out but the choice touches D14's legal posture and
   should be an explicit ratification, not an inferred default.
2. **Confirm the retry/give-up thresholds (§2.1, §2.5)**: 5 retries / 3 minutes for
   fetch-rebase-retry contention, and a 2-revert-per-run circuit breaker for the failure bot — or
   does the developer want different numbers? These are proposed defaults with no operational
   history behind them yet.
3. **Should time spent `blocked_red_main` count against a run's overall budget/wall-clock
   hard-stop (D26), or get an exemption since the delay isn't the runner's own doing?** This is
   ultimately topic 35's interface question to answer, but worth an early developer instinct
   since it affects how aggressively the orchestrator should poll versus simply pausing the run.
4. **Second GitHub App for the external-PR skim (§2.2, §2.8), or reuse the same App with a wider
   permission set once that lane needs `Pull requests` access?** This brainstorm recommends
   keeping the credentials separate to mirror D32's trust-domain separation, but it's a real
   operational cost (a second App to register and maintain) worth the developer weighing
   explicitly rather than defaulting to.
5. **Is the one-rerun-to-distinguish-flake-from-real-failure rule (§2.5, condition 3) sufficient,
   or does the developer want a stricter bar (e.g. two reruns) before the failure bot is allowed
   to auto-revert at all**, given how consequential a wrong auto-revert would be to diagnose after
   the fact?

## 5. New brainstorm topics surfaced

- **External-PR abuse handling** — unchanged from brainstorm 18's own §5 flag; this brainstorm's
  §2.8 makes the call to keep it a fold-in note here rather than promoting it, pending real
  external-PR volume. No new backlog number needed — it stays exactly where brainstorm 18 already
  filed it (folded into topic 27, i.e. this document), with the explicit condition that real abuse
  evidence is what would justify splitting it into its own future topic.
- **DCO-for-automated-commits documentation** — once open question 1 above is ratified, the actual
  wording belongs in `CONTRIBUTING.md` alongside the three human-contribution lanes topic 18
  already scoped. No new backlog number: this folds into the existing **topic 48 (CONTRIBUTING.md
  content)**, which already exists as a doc-writing task rather than a design brainstorm.
- No other genuinely new design topics emerged — the multi-runner lease (§2.7 Option B) and the
  external-PR skim's mechanical checks (§2.8) are both small enough to implement directly as part
  of this topic's own eventual build, not separate design passes.
