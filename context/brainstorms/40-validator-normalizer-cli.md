# 40 — Validator/Normalizer CLI

> Backlog brainstorm for LangAtlas. Topic: the concrete tool design behind a phrase five prior
> brainstorms each used without building it — "the validator" — plus the shared `validate-locator`
> routine (D37/topic 28), migration-manifest disposition-DSL exhaustiveness checking (D38/topic 29),
> and a unified regression-fixture convention (D26/D30/D41/D46). Binding context: D13 (CI
> validated-artifact pattern — "the agent runner runs the same fast offline validators pre-commit
> (refuses to commit on failure)... a failure bot auto-reverts only mechanically-safe tip commits");
> D23/brainstorm 09 (fact schema, stable IDs, the YAML normalization spec this topic must turn into
> code, the locator grammar this topic must turn into a validator); D26 (provider-abstraction layer
> — record/replay fixtures at the wrapper interface, `tests/fixtures/providers/`, hard CI-blocking
> pass/fail); D30 (debate cost/quality instrumentation — regression fixtures in a
> `tests/fixtures/providers/regression/` subfolder, lighter-weight human-diff review, not
> CI-blocking); D36 (agent-runner commit protocol — the pre-commit gate that refuses to commit on
> validator failure, is-main-green gating, the four-condition auto-revert checklist keyed on "a
> deterministic, reproducible failure of topic 40's offline validator"); D37/brainstorm 28 (locator
> normalization & ingestion QA — confirms brainstorm 09's locator grammar verbatim, names the shared
> `validate-locator` routine explicitly as this topic's scope); D38/brainstorm 29 (ontology change
> tooling — the disposition DSL's `op: split|merge|move|remove` vocabulary, the closed four-action
> `fact_remap` vocabulary `remap|requeue|tombstone|untouched`, and the ratified note that
> `action: untouched` is an **allowed implicit default**, not something CI must hard-require every
> anchor to state); D41 (pipeline observability & prompt registry — new prompt versions trigger a
> "soft (log-only) regression-fixture re-run check under topic 40's validator"); D44 (golden-set
> authoring methodology — `tests/golden/` as a *sibling*, scored/threshold-gated harness, explicitly
> distinct from topic-16's diff-reviewed `tests/fixtures/providers/regression/`, with golden-set
> staleness enforced as "a soft/log-only flag" mirroring D41's stance); D46/brainstorm 38
> (questionnaire compiler — a schema-shape regression fixture catching drift between the compiler's
> hardcoded fact-bearing field list and D23's JSON Schema, explicitly named "shared pattern with
> D26/D30," and the source of this topic's fifth deliverable). Read alongside brainstorms
> 09, 27, 28, 29, 38, which each assumed this tool exists and deferred its actual design here. All
> proposals below are *proposed* until the developer ratifies.

## 1. Problem framing

Every prior brainstorm that touched commit-time or build-time correctness checking wrote some
version of "the validator (topic 40) will do this" and moved on. That deferral was correct
prioritization at the time — none of those topics needed this tool's internals to finish their own
design — but it leaves five genuinely separate design gaps that this brainstorm has to close in one
pass, because they aren't independent: a single piece of code (the shape of `validate_locator`,
say) has to satisfy three call sites with materially different performance and invocation
constraints, and the regression-fixture convention has to unify three mechanisms (D26, D30, D41)
that were each specified as "regression fixtures, details TBD by topic 40" without knowing whether
the other two would turn out to want the same knobs.

**The three call sites, concretely, and why their constraints differ:**

1. **The agent-runner's pre-commit gate (D36).** Runs once per landing attempt, inside the
   fetch-rebase-retry loop (brainstorm 27 §2.1) — "run topic 40's validator once per rebase
   attempt against the rebased worktree." Must be fast (seconds, not minutes — it runs inside a
   retry loop with a 3-minute give-up window per brainstorm 27 §2.1) and must **refuse to commit**
   on failure (a nonzero exit is what makes D36's "refuses to commit on failure" real). It operates
   on a worktree on disk, so it can shell out or import — but D36's contention-retry loop means it
   may run several times per record in quick succession, so repeated DB round-trips are a real cost
   to avoid if a leaner offline mode exists.
2. **CI, on every push to `main` (D13).** Runs once per push, no tight time budget comparable to
   the pre-commit retry loop's (a few minutes is fine), gates whether the corpus stays eligible for
   the next `data-vN` publish. This is the natural place for the *complete* check — full corpus
   scan, not just the touched files — since D13's "red main publishes nothing" posture means CI is
   the backstop that catches anything a narrower/faster pre-commit pass let through (a
   cross-file constraint two concurrently-landing commits each individually satisfied, for
   instance).
3. **The D24 verifier's stage-2 locator-resolution step.** Runs *inside* a verification batch, once
   per claim, as a step in an existing filter ladder — not a subprocess-per-claim (that would be a
   process-spawn cost multiplied across a batch of hundreds of claims, and the verifier already
   holds an open connection to the same `source_chunks` index this check needs). This call site is
   the one that makes "one CLI binary" alone insufficient: it needs a **plain importable Python
   function**, not a shell-out, and it needs to be called with a caller-supplied index handle
   rather than the tool owning its own DB connection lifecycle.

**The five deliverables**, each previously deferred here by name:

1. A **structure** answering "one binary or many scripts, and how does the verifier call in
   without a subprocess."
2. **`validate_locator`** as a concrete, dependency-injectable function (brainstorm 28 §2.1 named it
   exactly, deferred its interior).
3. **Migration-manifest disposition-DSL validation** (brainstorm 29 §5 named it exactly): does every
   `remap`/`requeue`/`tombstone` action's matcher and target actually resolve — while *not*
   requiring every discovered anchor to be explicitly listed, per D38's ratified
   `action: untouched`-is-implicit-default amendment.
4. A **unified regression-fixture convention** spanning D26's hard CI-blocking provider fixtures,
   D30's softer human-diff regression subset, D41's soft prompt-version re-run check, and D46's
   schema-shape check — four independently-motivated "regression fixture" mentions that need one
   shared harness, not four incompatible ad hoc scripts.
5. **YAML normalization** as a single implementation (brainstorm 09's spec) that every other
   component — the pre-commit formatter, CI's idempotency check, and the canonical-claim-hashing
   code that needs *value* normalization, not just whole-file formatting — imports rather than
   reimplements.

Scale check (carried from 09/25/27): low hundreds of ontology nodes growing toward thousands,
tens of thousands of derived facts, a pre-commit gate that has to run inside a 3-minute retry
window per landing attempt. Nothing here is a scale problem — corpus-wide checks at this size are
a script that finishes in low seconds — so the design questions below are about interface
consolidation and mode semantics, not performance engineering.

## 2. Options with trade-offs

### O1 — Structure: one binary with subcommands, several scripts, or a library-first package

**Option 1a — several independent scripts** (`validate_schema.py`, `validate_locator.py`,
`normalize.py`, `check_migration.py`, one per concern, each its own `if __name__ == "__main__"`
entry point). Cheapest to start, but immediately fails the third call site: the D24 verifier can't
cleanly "import a script" — it would have to either subprocess out (rejected by the task's own
framing: "callable as a library function, not just shell-out") or duplicate the script's logic as
a second implementation, which is exactly the drift risk this whole brainstorm exists to prevent
(brainstorm 09 already flagged "the pre-commit/CI/verifier three call sites... drift into three
slightly different regexes" as the failure mode to avoid).

**Option 1b — a single monolithic CLI binary, no separate library surface.** One `langatlas-validate`
executable with subcommands (`validate schema`, `validate locator`, `validate migration`,
`normalize yaml`, `regression run`), all logic living inside command-handler functions. Solves
nothing beyond 1a for the verifier's needs — "one CLI" was never actually the constraint; "callable
as a Python function from inside a batch" is, and a CLI's command handlers are not, by construction,
independently importable without either restructuring them or shelling out to `argparse`'s own
entry point.

**Option 1c (recommended) — library-first package, thin CLI wrapper.** A plain importable Python
package (`tools/validate/`, a proper package with `__init__.py`, not a scripts folder) where every
check is a normal function with a typed signature and no argparse/click coupling; a single thin
`cli.py` dispatches subcommands to those functions and handles process exit codes / stdout
formatting. This is the same shape the project already uses for D38's blast-radius script and
D41's `report.py` (small Python CLI, no daemon) — the only addition here is the explicit
library/CLI split, which those two tools didn't need because nothing calls them mid-batch from
inside another Python process. Concretely:

```
tools/validate/
  __init__.py            # exposes langatlas_validate as an importable package
  cli.py                 # thin dispatch: argparse subcommands -> library calls -> exit code
  schema.py              # record-vs-JSON-Schema validation (ontology/schema/*)
  referential.py         # cross-file id resolution: feature exists, edge endpoints exist, ...
  locators.py            # validate_locator() — O2 below; the one the verifier imports directly
  normalize.py           # normalize_record() (whole-file) + normalize_value() (claim hashing)
  migration.py           # disposition-DSL checks — O3 below
  regression.py          # fixture harness — O4 below
  factid.py              # corpus-wide fact-id collision check (D23)
```

Three call-site contracts, now concrete:

- **Pre-commit (D36):** `langatlas-validate precommit <changed-file-paths...>` — a CLI invocation
  from the agent runner's worktree, one process per rebase attempt (brainstorm 27 §2.1). Runs
  `schema.py` + `referential.py` scoped to the touched files and their direct referential neighbors
  (an edge file touching feature X re-checks that X still exists; it does not re-scan the whole
  corpus), `normalize.py --check` (fails if the runner produced non-normalized output — in practice
  this should never fire, since the runner's own pre-commit step calls `normalize` to *write* the
  canonical form before this check runs, but the check stays as the actual gate D36 depends on),
  and `locators.py`'s **phase-1-only** (regex shape, no DB) check on any new/changed `sources:`
  entries — see O2 for why phase 2 is optional here. Nonzero exit blocks the commit, per D36.
- **CI (D13):** `langatlas-validate ci` — full corpus scan, no file-list argument. Runs every check
  above corpus-wide, plus `locators.py`'s **phase 2** (DB-backed `source_chunks` resolution — CI
  always has DB access, unlike the pre-commit gate), `factid.py`'s collision check, `migration.py`
  against any manifest under `ontology/migrations/**/manifest.yaml` or `sources/_tombstones.yaml`
  touched by the push, and `regression.py run` (honoring each fixture's declared hard/soft mode,
  O4). This is the complete check D13's "red main publishes nothing" posture actually depends on.
- **Verifier stage-2 (D24):** `from langatlas_validate.locators import validate_locator` — a plain
  function call, no subprocess, no CLI invocation at all. The verifier's own batch-processing loop
  already holds a `source_chunks` connection/index handle; it passes that handle in (O2's
  dependency-injection design) rather than the library owning its own connection lifecycle.

**Recommendation: 1c.** This is the only option where "one shared tool" and "callable as a library
function" are simultaneously true rather than in tension, and it costs nothing beyond an ordinary
package/CLI split any of the project's other small tools (D38, D41) could have used too had they
needed a non-CLI caller.

### O2 — `validate_locator`: the concrete shared routine (D37/topic 28)

D37 named this exactly: "regex shape + `source_chunks` resolution check... reused by the pre-commit
gate, CI, and the D24 verifier's stage-2 step." Two genuinely separate sub-checks, deliberately
split so a caller without DB access can still run the cheap half:

```python
# tools/validate/locators.py

class LocatorResult(NamedTuple):
    ok: bool
    stage: Literal["shape", "resolution"]     # which phase failed, if any
    reason: Literal["ok", "malformed", "unknown_locator_kind",
                     "source_unknown", "source_unresolvable",
                     "locator_not_found"] | None
    detail: str | None                        # human-readable, for CI/pre-commit stdout

class SourceChunksIndex(Protocol):
    """Whatever the caller already holds — a DB connection wrapper in CI/the verifier,
    or a manifest-only stub in pre-commit when no DB is configured (see below)."""
    def resolve(self, source_id: str, locator: str) -> bool: ...
    def locator_kinds_for(self, source_id: str) -> list[str]: ...   # custom.locator_kinds

def validate_locator_shape(source_id: str, locator: str,
                            allowed_kinds: list[str]) -> LocatorResult:
    """Phase 1: pure regex-shape check against brainstorm-09 §O5's grammar table.
    No I/O. Safe to run with zero DB dependency — this is what the pre-commit
    gate runs by default."""
    ...

def validate_locator(source_id: str, locator: str,
                      index: SourceChunksIndex) -> LocatorResult:
    """Phase 1 + phase 2: shape check, then index.resolve() for
    source_chunks range/section-overlap resolution. This is the function the
    D24 verifier's stage-2 step imports directly and calls per-claim inside a
    batch, passing its own already-open index handle — no subprocess, no new
    connection per call."""
    shape = validate_locator_shape(source_id, locator, index.locator_kinds_for(source_id))
    if not shape.ok:
        return shape
    return LocatorResult(ok=index.resolve(source_id, locator), stage="resolution",
                          reason=None if index.resolve(source_id, locator)
                                 else "locator_not_found", detail=...)
```

The grammar table implementing brainstorm 09 §O5 verbatim (confirmed unchanged by D37): `pp. N–M`
(book/paper), `§N(.N)*` (numbered spec/section), `ch. N` / `§ <heading>` (named chapter),
`#<fragment>` (web page), `<path>#<fragment>` (multi-page docs site), `<commit-sha7>:<path>#LN-LM`
(repo file), `t=HH:MM:SS` (video/talk) — each pattern gated per-source by `custom.locator_kinds`
(D3's `custom` key), matching D37's "a `custom.locator_kinds` hint on the source record tells CI
which grammars are admissible for that source" rule exactly.

**Why phase 1/phase 2 split matters for the three call sites:** the pre-commit gate, by default,
runs phase 1 only (`validate_locator_shape`, zero I/O, zero DB dependency) — this keeps the
fetch-rebase-retry loop's per-attempt validator invocation cheap and DB-connection-free even when
the runner's own machine has no local Postgres running. CI and the verifier always have DB access
and always run the full `validate_locator` (phase 1 + 2). This is a deliberate asymmetry, not an
oversight: a malformed locator (phase 1) is exactly the kind of typo-class error worth catching at
commit time per D37's own rationale ("caught at commit time rather than wasting a verifier batch"),
but a *resolution* failure (phase 2 — the cited page genuinely doesn't exist, or the source hasn't
finished ingesting) is not something the pre-commit gate can always distinguish from "this source
just hasn't been chunked yet" without a live index, so deferring phase 2 to CI (which runs after
ingestion jobs have had a chance to complete) avoids false pre-commit rejections on records citing
a source that's mid-ingestion. If the developer's machine does run a local Postgres available to
the runner, running phase 2 in pre-commit too is a pure quality improvement with no downside —
flagged as open question 1.

### O3 — Migration-manifest disposition-DSL validation (D38/topic 29)

D38's own §5 named this precisely: "does every blast-radius-discovered fact anchor appear in
`fact_remap`? does every `remap` target resolve?" — but the ratified amendment to D38
(`action: untouched` is an allowed **implicit** default) means the first half of that question, read
literally, is **not** the check to build: CI must **not** hard-require every discovered anchor to
appear explicitly. What the validator does need to check, concretely, over any manifest under
`ontology/migrations/<id>/manifest.yaml` or `sources/_tombstones.yaml` (the two ledger locations
D38 §2.6 specifies, sharing one schema):

1. **Matcher resolvability.** Every `fact_remap[].match` entry's `anchor` (or `citing_source`, for
   `kind: source` entries) must actually match ≥1 real anchor/citation in the current corpus at the
   manifest's stated `ontology_version_before`. A matcher that matches zero anchors is very likely a
   typo (a renamed feature id, a mis-copied anchor pattern) — this is the check that actually earns
   its keep, since it catches the kind of error that D38's "implicit untouched default" would
   otherwise silently swallow (a matcher meant to remap something, but silently matching nothing,
   is indistinguishable from "nothing to do here" without this check).
2. **Target resolvability.** Every `remap` action's `target` must resolve to a real node id —
   either already present in the corpus, or declared in the same manifest's own `to:` list (for
   `split`/`merge` ops minting new node ids as part of the same migration). A `target` pointing at
   neither is a dangling reference.
3. **Op-shape completeness.** Each `op` value (`split | merge | move | remove` for ontology-node
   manifests; `supersede` for the source-registry sibling ledger) carries its own required fields
   per D38's schema — `split` needs `to` (a list) + `old_node_disposition` + `url_policy`; `merge`
   needs `from` (a list) + `to` + `url_policy`; `move` needs `to_layer`/`to_dimension` +
   `url_policy`; `remove` needs `url_policy`; `supersede` needs `to` (a single source id) +
   `reason: edition-superseded` + `detected_by`. Missing required fields fail the check.
4. **Closed action vocabulary, scoped by ledger kind.** Ontology-node manifests may only use
   `remap | requeue | tombstone | untouched` (D38's closed four-action set); `sources/_tombstones.yaml`
   entries (`kind: source`) may additionally use `flag-stale` (D38 §2.6's fifth, source-scoped
   action) but never the other four's node-remapping actions. An unrecognized action, or an action
   used outside its declared scope (`flag-stale` inside an ontology-node manifest, say), fails.
5. **Auto-generated `impact.md` section diff-check.** D38 §2.2 already specifies that `impact.md`
   splits into an auto-generated section (rendered from the blast-radius script's JSON output) and
   an authored section, with the auto-generated half "CI diff-checked against a fresh blast-radius
   run and fail[ing] the PR if they've drifted." This validator owns running that diff: re-run
   `tools/ontology-tools/blast_radius.py` (topic 29's own deliverable) fresh against the manifest's
   `affected_node_ids`, and byte-diff the result against `impact.md`'s auto-generated section.

**Explicitly not a check:** exhaustiveness in the "every anchor must appear" sense. `migration.py`
must not fail a manifest merely because some blast-radius-discovered anchor is absent from
`fact_remap` — per D38's ratification, that anchor's implicit disposition is `untouched`, and the
validator's job stops at "everything that *is* declared, declares something coherent," not
"everything that *could* be declared, is."

### O4 — Unified regression-fixture convention (D26/D30/D41/D46)

Four prior decisions each said "regression fixtures" and left the mechanics to this topic:

| Source | What gets checked | Blocking behavior (as already ratified) |
|---|---|---|
| D26 | provider-wrapper record/replay conformance | **hard**, CI-blocking pass/fail |
| D30 | a hand-curated regression subset, diffed on prompt/model change | **soft**, human-diff review, not CI-blocking |
| D41 | new prompt-registry version → regression-fixture re-run | **soft** (log-only), "a uniform soft gate everywhere... no special hard-block carve-out" |
| D46 | compiler's fact-bearing field list vs D23's JSON Schema | not yet ratified as hard/soft — this topic decides |

The risk this brainstorm has to close: without one shared harness, each of these becomes its own
bespoke script with its own fixture file format, its own idea of what "pass" means, and its own
place to look when something drifts — exactly the "three independently drifting regexes" failure
mode brainstorm 09 named for locators, recurring here for regression checking.

**Design: one fixture format, one runner, mode as fixture metadata rather than tool-hardcoded
behavior.**

```yaml
# tests/fixtures/providers/regression/glm-drafting-002.yaml
fixture_id: glm-drafting-002
kind: provider-record-replay       # provider-record-replay | schema-shape | questionnaire-shape
mode: soft                         # hard | soft — the ONE thing that changes CI behavior
description: "GLM drafting call for fi.rust.pattern-matching#characteristics, captured 2026-07."
recorded_call:
  model: glm-5.2
  prompt_id: sweep-draft-characteristics
  prompt_version: v-3a9f21c0
  messages: [...]
recorded_response: {...}
```

```yaml
# tests/fixtures/providers/schema-shape-001.yaml
fixture_id: schema-shape-001
kind: schema-shape
mode: hard                         # deterministic code-vs-schema check — no reason to be soft
description: >-
  compile.py's FeatureInstance fact-bearing field list must equal
  ontology/schema/feature-instance.json's fact-bearing-tagged properties.
check: compiler-field-list-matches-schema
target_schema: ontology/schema/feature-instance.json
target_field_list: tools.questionnaire.compile.FACT_BEARING_FIELDS
```

`tools/validate/regression.py` provides:

- **A pluggable checker registry** keyed by `kind` — `provider-record-replay` (D26/D30: replays a
  recorded provider call against the current wrapper code path and diffs the response shape),
  `schema-shape` (D46, and generically reusable for any "does generated-artifact-X's field list
  match schema-Y" check — the exact pattern D46's own brainstorm flagged as wanting "a single
  unified treatment... rather than each topic inventing its own"), `questionnaire-shape` (a second
  instance of the same `schema-shape` checker, parameterized differently, satisfying D46's own
  fixture without new code), `prompt-version-rerun` (D41: on a detected `prompt_id` version bump,
  re-run every fixture referencing that `prompt_id` and diff).
- **One CLI entry point**, `langatlas-validate regression run [--kind K] [--mode hard|soft]`,
  invoked by CI (all fixtures, all modes — but only `mode: hard` fixture failures affect CI's exit
  code; `mode: soft` failures are printed/logged to a report and never fail the process, matching
  D30/D41's explicit "uniform soft gate" ratification) and, per D41, by the prompt-registry
  tooling whenever a new prompt version lands (filtered to `--kind provider-record-replay --mode
  soft` fixtures referencing that prompt).
- **Mode is fixture metadata, not a tool-level branch per `kind`.** This is the key design choice
  that actually unifies the four decisions above rather than just co-locating them: D26's core
  wrapper-conformance fixtures are `mode: hard` because they check a deterministic code path; D30's
  regression subset living in the same directory tree is `mode: soft` because it's checking
  LLM-output stability, which is expected to drift benignly on model/prompt updates; a future
  fixture of either `kind` can be declared either `mode` without the runner needing new branches —
  the semantics live in the YAML, not in an if/else keyed on `kind`.

**Scope boundary with D44's `tests/golden/`, stated explicitly since it's the likeliest confusion
point:** `tests/golden/` (verifier golden set, controversy golden set, retrieval golden queries,
the future debate-outcome golden set) is **not** this harness. D44 already ratified it as a
*sibling*, scored/threshold-gated evaluation directory, explicitly contrasted against "topic-16's
diff-reviewed `tests/fixtures/providers/regression/`" — golden-set items carry a numeric score
(Recall@5, false-accept rate, …) against a threshold, not a hard/soft pass-fail diff against a
recorded fixture. This topic owns the fixture-diff convention (`tests/fixtures/providers/**`); D44
owns the scored-evaluation convention (`tests/golden/**`). They are structurally different checks
(diff-against-recording vs. score-against-threshold) that happen to have gotten linguistically
tangled ("regression," "golden set," "fixture" all used loosely across different brainstorms) —
this brainstorm's contribution is drawing that line precisely, not merging the two.

**Recommendation:** the format/runner/mode-as-metadata design above, with `mode: hard` for
D26's provider-conformance fixtures and any `schema-shape`/`questionnaire-shape` check (both are
deterministic code-vs-schema comparisons with no reason to tolerate drift), `mode: soft` for D30's
LLM-output regression subset and D41's prompt-version re-run check (both inherently expect
benign output drift on legitimate changes) — see open question 2 for whether D46's specific fixture
should default hard or start soft during the compiler's shakeout period.

### O5 — YAML normalization: the actual implementation

Brainstorm 09 specified the rules; nobody wrote the code. `tools/validate/normalize.py` implements
two related but distinct functions, both single-sourced here so every consumer imports rather than
reimplements:

```python
def normalize_record(path: Path) -> str:
    """Whole-file YAML normalization per brainstorm-09's spec: YAML 1.2, UTF-8, NFC;
    2-space indent, no tabs; keys in schema-declared order; one record per file, no
    multi-doc streams; no anchors/aliases/merge keys/custom tags; plain scalars unless
    quoting required (then double-quoted); prose in `>-` folded blocks, code in `|`
    literal blocks; 100-column soft wrap for prose; dates as quoted ISO-8601 strings;
    `null` spelled `null`; keyed lists sorted by `key`, `sources:` lists kept in
    authored order. Idempotent: normalize_record(normalize_record(x)) == normalize_record(x).
    """

def normalize_value(raw: str, *, kind: Literal["free_text", "structured"]) -> str:
    """Value-level normalization feeding canonical-claim hashing (brainstorm 09 §O6),
    NOT the same operation as normalize_record above (that's whole-file formatting;
    this is claim-content normalization for the content-keyed fact id). NFC + trim +
    collapse internal whitespace always; for kind="free_text" (characteristic/syntax/
    rule-antecedent sentences) additionally lowercase + strip terminal punctuation —
    the "copyedit-tolerant hashing" D23 ratified, so a typo fix doesn't mint a new fact
    id but a semantic rewrite still does.
    """
```

**Consumers, all importing from this one module rather than re-deriving the rules:** the pre-commit
hook calls `normalize_record` to rewrite each touched file in place before the commit attempt
(making diffs always semantic, per brainstorm 09's own framing); `langatlas-validate ci`/`precommit`
call `normalize_record` again in **check mode** (compare current file content to
`normalize_record(current_content)`; any difference is a CI/pre-commit failure — a file that
reached CI un-normalized means the runner's own pre-commit step was bypassed or a human edited the
file directly without running the formatter) — this doubles as the D36 auto-revert checklist's
"deterministic, reproducible failure of topic 40's offline validator" condition for the specific
case of a badly-formatted commit slipping through; and the fact-id-minting code (wherever brainstorm
09 §O6's canonical-claim-string construction lives, likely alongside `factid.py` or in the build
pipeline proper) imports `normalize_value` for the free-text-sentence hashing step, rather than
reimplementing the lowercase-and-strip rule a second time.

## 3. Recommendation (*proposed*)

1. **Structure (O1):** a library-first Python package, `tools/validate/` (module name
   `langatlas_validate`), with a thin `cli.py` dispatching to plain, independently-importable
   functions in `schema.py`/`referential.py`/`locators.py`/`normalize.py`/`migration.py`/
   `regression.py`/`factid.py`. Three call-site contracts: `langatlas-validate precommit
   <files...>` (fast, scoped to touched files + direct referential neighbors, phase-1-only
   locator check by default, refuses to commit on nonzero exit per D36); `langatlas-validate ci`
   (full corpus, phase-2 locator resolution, fact-id collision check, migration-manifest
   validation, full regression run honoring per-fixture mode); and `from langatlas_validate.locators
   import validate_locator` as a direct, no-subprocess import inside the D24 verifier's stage-2
   step, called with the verifier's own already-open `source_chunks` index handle.
2. **`validate_locator` (O2):** a two-phase function — `validate_locator_shape` (pure regex-shape
   check against brainstorm-09 §O5's grammar table, zero I/O, always run) and `validate_locator`
   (shape + `source_chunks` resolution, requires a caller-supplied `SourceChunksIndex` handle,
   always run in CI and the verifier, run in pre-commit only if a local index is configured). One
   implementation, three call sites, dependency-injected rather than owning its own DB connection.
3. **Migration-manifest validation (O3):** checks matcher resolvability (every `fact_remap[].match`
   pattern matches ≥1 real anchor/citation — catching typo-class dead matchers), target
   resolvability (every `remap` target is a real or manifest-declared node id), per-op required
   fields, a closed action vocabulary scoped correctly by ledger kind (ontology-node manifests vs.
   `sources/_tombstones.yaml`'s `flag-stale`-inclusive set), and the `impact.md` auto-generated-
   section diff-check against a fresh blast-radius run. **Explicitly does not** require every
   blast-radius-discovered anchor to appear in `fact_remap` — `action: untouched` stays a valid
   implicit default per D38's ratification.
4. **Regression-fixture convention (O4):** one fixture file format (`fixture_id`, `kind`, `mode:
   hard|soft`, plus kind-specific fields) under the existing `tests/fixtures/providers/` tree, one
   runner (`langatlas-validate regression run`) with a pluggable checker registry
   (`provider-record-replay`, `schema-shape`, `questionnaire-shape`, `prompt-version-rerun`), and
   mode declared as fixture metadata rather than hardcoded per-kind tool behavior — this is what
   actually unifies D26 (hard), D30 (soft), D41 (soft), and D46 (developer's call, open question 2)
   into one harness instead of four scripts. Explicitly scoped apart from D44's `tests/golden/`
   scored-evaluation harness, a structurally different (score-vs-threshold, not diff-vs-recording)
   sibling mechanism.
5. **YAML normalization (O5):** two functions in `normalize.py` — `normalize_record` (whole-file
   formatting per brainstorm 09's full spec, idempotent, run by the pre-commit hook to write and
   by CI/pre-commit-check-mode to verify) and `normalize_value` (claim-content normalization for
   fact-id hashing, copyedit-tolerant per D23's ratification) — both imported by every consumer
   (pre-commit writer, CI checker, fact-id-minting code) rather than reimplemented per-caller.

## Open questions for the developer

1. **Pre-commit locator-check depth (O2)** — should the pre-commit gate always run phase-1-only
   (regex shape, zero DB dependency, fastest and most portable) by default, or should it
   auto-upgrade to full phase-2 resolution whenever a local Postgres happens to be reachable from
   the runner's machine? The former is simpler and more predictable across environments; the
   latter catches more at commit time whenever the infrastructure happens to be available, at the
   cost of the pre-commit gate's behavior depending on local environment state.
2. **D46's schema-shape fixture: hard or soft by default (O4)?** Deterministic code-vs-schema
   checks (this one, and D26's provider-conformance fixtures) seem to argue for `mode: hard` on
   principle — there's no legitimate reason for the compiler's field list and the JSON Schema to
   ever disagree. But the compiler (`compile.py`) doesn't exist yet and hasn't shipped a real
   version (per D46's own ratification deferring `questionnaire_schema_version`); is a soft
   shakeout period warranted for this specific fixture before it becomes CI-blocking, or should it
   be hard from its very first commit?
3. **Console-script packaging** — should `langatlas-validate` ship as an installable entry point
   (`pyproject.toml` `[project.scripts]`, invoked as a bare command from `PATH`) or stay a plain
   `python -m tools.validate.cli` invocation? Affects how the pre-commit hook, CI workflow YAML,
   and the verifier's import path all reference it — worth deciding once, since changing it later
   touches every call site simultaneously.
4. **Package location/naming** — is `tools/validate/` (matching the existing `tools/questionnaire/`,
   `tools/orchestrator/`, `tools/observability/` naming convention) the right home, or does this
   tool's unusually central role (imported directly by the D24 verifier, invoked by both the agent
   runner and CI) argue for a more prominent top-level package name that signals "this is
   infrastructure other subsystems depend on," not just another `tools/` entry?
5. **Migration-matcher-resolution severity (O3)** — should a `fact_remap` matcher that resolves to
   zero anchors be a hard CI failure (blocking the migration PR outright) or a warning surfaced in
   the impact report for the human RFC reviewer to catch, given that ontology MAJORs already go
   through D16 O5b's human-gated process review regardless?

## New brainstorm topics surfaced

None. This brainstorm's explicit purpose was to close out the fold-in notes five prior brainstorms
(09, 27, 28, 29, 38) each filed against this exact backlog number — every "fold into topic 40"
pointer from those documents is addressed above (the validator/normalizer CLI itself; the shared
`validate-locator` routine; migration-manifest disposition-DSL validation; the unified
regression-fixture convention). No new capability surfaced during this design that isn't already
either resolved here or already tracked elsewhere (the external-PR "provenance/scope skim" checks
brainstorm 27 §2.8 named as "an extension of the validator-CLI scope" are covered by this topic's
`referential.py`/file-type checks once that lane needs them, not a separate design).
