# Stage 3D — The Controversy Assessor (D21/D25) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build §6.4's **controversy assessor** — a university-API `thinker` that reads
*structured inputs only* (debates, contradiction records, verification verdicts,
mechanically-computed source strength, assessment spread) and assigns each derived fact one of
four ordinal levels (`0 settled | 1 noted-variance | 2 contested | 3 disputed`), writing a
machine-authored `controversy:` block into the canonical record whose `signals` list **is** the
justification — with Claude escalation for adjacent-level ambiguity and **every** level-3
assignment, event-driven nightly batching, a registered job kind, and
`goldens.controversy_assessor_entry_point` finally pointed at something real.

**Architecture:** A new `langatlas_research.controversy` subpackage, sibling to 3B's `survey` and
3C's `draft`. Four layers, deliberately separated so the model occupies the smallest possible
slice:

1. **Assembly** (`assemble.py`, no model) — walks the canonical store's derived facts and projects
   the five permitted structured inputs out of `derive_facts`, the private `VerdictLedger`,
   `contradictions.yaml`, `sources/*.yaml` tiers and 3C's `as_controversy_input(debate)`. Built by
   allow-list, exactly like the D24 verifier's `whitelist_payload`: human-challenge-derived inputs
   are never *assembled*, not stripped afterwards.
2. **Assessment** (`assessor.py`, university API) — one `thinker` call over a fixed rubric per
   fact, structured output `{level, alternative, signals}`. Signals are intersected with the set
   mechanically derivable from the inputs, so a model cannot invent a justification.
3. **Escalation** (`escalate.py`, Claude) — fires when the thinker names an adjacent alternative
   level, and unconditionally for every level-3 assignment. Each escalation review is captured as
   an uncurated golden candidate under `tests/golden/controversy/candidates/`, which is 2B's
   opportunistic lane growing the ~50-case target.
4. **Persistence** (`block.py` + `ledger.py` + `run.py`) — level ≥1 writes a `controversy:` block
   into the record through 3A's `land_drafts`, one commit per record. Level 0 writes **nothing**
   (absent block = level 0, §6.4). The `inputs_digest` that makes "unchanged inputs ⇒ unchanged
   level" a *free* re-run lives in a private SQLite ledger, never in git — the same reason D23
   keeps verdicts out of authored YAML.

The nightly batch is one more `driver.py` job kind (`nightly-controversy`), work-item grain = one
record file, so a run's commit grain and its checkpoint grain agree.

**Tech Stack:** Python 3.12, `uv`, `pydantic` (structured output), `ruamel.yaml`, `jsonschema`,
`sqlite3` (stdlib), `pytest`. No new package and no new dependency: `tools/research` already
path-depends on `langatlas-validate`, `langatlas-commit`, `langatlas-pipeline`, `langatlas-ingest`
and `langatlas-finding-aids`, and `tools/orchestrator` already imports `langatlas_research`.

**Spec:** [context/spec.md](../../../context/spec.md) — §6.4 (controversy score + golden sets),
§6.3 (status axes, confidence, re-verification triggers), §6.5 (contradiction register), §7.11
(orchestrator/scheduling), §7.1 (model tiering), §3.2 (fact granularity, anchors), §3.4 (record
schemas), §5.1 (semver).

**Sequencing map:** [2026-09-13-stage-3-theme-cycles.md](2026-09-13-stage-3-theme-cycles.md) —
3D's "Produces" list is this plan's required deliverables.
**Fixed inputs:** [3A](2026-09-13-stage-3a-research-spine-and-minting.md) (`land_drafts`,
`MintedRecord`, referential integrity in `validate_store`, the 0.x version ceremony),
[3C](2026-09-16-stage-3c-r4-drafting-and-debates.md) (`iter_debates`, `as_controversy_input`,
`debate_signals`, the `node-definition` claim kind, the debate-outcome contradiction mint path),
and Stage 2B/2D (`ControversyCase`, `run_controversy_goldens`, `score_controversy`,
`VerdictLedger`, `load_source_facts`, `are_independent`).

## Global Constraints

Every task's requirements implicitly include this section. Values copied verbatim from the spec
and the sequencing map.

- **The assessor sees structured inputs only (§6.4).** Exactly five: `debates`,
  `contradiction_records`, `verdicts`, `source_strength`, `assessment_spread` — the frozen
  `ALLOWED_CONTROVERSY_INPUTS` tuple 2B already committed. No claim text, no record prose, no
  source text, no proposer identity.
- **Everything human-challenge-derived is excluded, in code and not in prose (§6.4).** No GitHub
  activity, no challenge counts, and — per the 2026-07-20 withdrawal — not a contradiction
  record's `closure_attempt.outcome: confirmed-open`. An open contradiction record reaches the
  assessor only through its machine-produced content (`id`, `type`, `status`, participant count).
- **The controversy assessor never mints contradiction records (§6.4/§6.5).** It is a reader of
  `contradictions.yaml`; the four legal minting paths are the D24 verifier, the D5
  reconciler/debate outcome, human-challenge resolution, and the Stage-5 cross-fact scan.
- **Four levels, ordinal (§6.4):** `0 settled | 1 noted-variance | 2 contested | 3 disputed`.
  Level 4 was folded into 3 at ratification; there is no level 4 anywhere.
- **Assessor = university-API `thinker` (`deepseek-v4-pro-thinking`) over a fixed rubric**
  (§6.4/§7.1). Claude is the escalation target for adjacent-level ambiguity and **all level-3
  assignments**, and the golden-set calibrator. Claude never does the volume pass.
- **Output is a machine-written block in the canonical record whose `signals` list of machine
  references *is* the justification — no free-prose rationale. An absent block means level 0**
  (§6.4).
- **Event-driven nightly batches: unchanged inputs ⇒ unchanged level**, so a re-run is free
  (§6.4/§7.11). Registered as a job kind and wired into `config/jobs/crontab.example`.
- **Presentation thresholds belong to the site (§6.4).** This plan renders nothing, suppresses
  nothing, and ranks nothing — it assigns a level and records the signals.
- **Confidence never decreases from challenges or controversy (§6.3)** — the axes are orthogonal.
  Nothing in this plan touches `derive_confidence`, the verification axis, or the `dispute` axis.
- **Verifier verdicts are never written back into authored YAML (D23/§3.4).** The assessor reads
  the private `VerdictLedger`; the `inputs_digest` it uses for the free-re-run check lives in a
  private ledger too.
- **Git is the database (D1).** The only git-visible output is the `controversy:` block, landed
  through `land_record` (D36: one commit per record file).
- **Every agent chat is logged (D18).** Both the thinker pass and any Claude escalation run inside
  a `RunContext`; the escalation opens its own context.
- **Model ids and aliases are configuration, never hardcoded** (`config/research.yaml`,
  `config/providers.yaml`).
- **Budget hard-stops are typed (D43).** `BudgetExceeded` pauses the in-flight item as `blocked`;
  resume is plain re-invocation. D25's nightly budget is ~200 facts/night.
- **No PR gate (D1/D4)** — the nightly job commits directly to `main` through the same protocol
  every other agent uses.
- English-only; code MIT, corpus CC BY-SA 4.0.

## Design decisions this plan makes (flag for developer review)

1. **The assessor lives in `langatlas_research.controversy`, not in `langatlas_ingest`.** Its
   inputs span both packages (debates + the carve trail are research; verdicts, tiers and
   contradictions are ingest), and `langatlas_research` already depends on `langatlas_ingest`
   while the reverse would be a cycle. `golden-score` resolves the entry point with `importlib`
   at runtime, so nothing static breaks — but the scored run must be launched from the research
   package's environment (`uv --directory tools/research run langatlas-sources golden-score …`),
   which works because `langatlas-ingest` is a path dependency and its console scripts are
   installed into that venv. Task 8 documents this in the golden README, because a developer
   running it from `tools/ingest` gets a bare `ImportError` otherwise.
2. **The unit of assessment is the derived fact; the unit of work and commit is the record.** §6.4
   scores facts (2B's cases key on `fact:`), but D36 commits record files. So a work item is one
   record path, its facts are assessed in a batch, and at most one commit is made per record per
   run. This also keeps a record's block internally consistent — never half-updated by a run that
   hit its budget mid-record.
3. **`inputs_digest` lives in a private SQLite ledger, not in the YAML block.** Level 0 is the
   overwhelming majority of facts and writes no block at all, so a git-resident digest could not
   cover the common case — and "unchanged inputs ⇒ unchanged level" has to be free for *settled*
   facts above all. A private `AssessmentLedger` (same tier as `VerdictLedger`) records
   `(fact_id, inputs_digest, level, signals, assessed_at)`; a matching digest skips the model call
   entirely. Losing the private ledger costs one expensive re-run and nothing else — it is a
   cache, never ground truth.
4. **The block is a keyed list on the record, sorted by `key`, and `key` is the anchor's
   field-path suffix** (§3.2: anchor = `record-id#field-path`). `normalize_record` already sorts
   any top-level list of dicts carrying a `key`, so the block normalizes for free and a diff of
   two nightly runs is stable. The `fact_id` is stored alongside `key` because the fact id changes
   when the claim changes while the anchor does not — a block whose `fact_id` no longer matches
   the record's derived facts is stale, and Task 4 makes `validate_store` say so.
5. **A `controversy`-only edit is classified as `none` by `version-bump`.** `_diff_class` today
   reads an added key as `additive`, which would bump `ontology/VERSION` MINOR every night the
   assessor found its first contested fact. A machine annotation is not an ontology change, so
   `version.py` gains a `_MACHINE_FIELDS` set stripped before classification. This is the single
   riskiest interaction in the plan and Task 4 tests it in both directions.
6. **The thinker types a `level` plus an optional adjacent `alternative`; escalation is computed,
   never typed.** A model that could type "escalate" could opt out of review; a model that types
   the level it *nearly* chose cannot. `alternative` must be within one of `level` or it is
   dropped. Level 3 escalates whatever the model says about its own certainty.
7. **Escalation reviews land as *uncurated candidates* in
   `tests/golden/controversy/candidates/<YYYY-MM>.yaml`, not in the golden set.**
   `load_controversy_cases` globs `*.yaml` non-recursively and raises on `curated: false`, so a
   subdirectory is invisible to it — the same shape as `tests/golden/verifier/held-out/`. The
   developer promotes a candidate by hand-labelling `expected_level` and moving it up, exactly as
   `golden-candidates` already asks for the verifier lane.
8. **`source_strength` keeps 2B's exact three keys** (`tier_a`, `tier_b`,
   `independent_corroborations`) even though tier C/D backing exists. The committed golden set is
   the calibration contract; adding a fourth key would mean the rubric the goldens score is not
   the rubric production runs.

## File structure

**New — `tools/research/src/langatlas_research/controversy/`:**

| File | Responsibility |
|---|---|
| `__init__.py` | Empty marker, matching `survey/` and `draft/`. |
| `inputs.py` | `ControversyInputs`, the closed signal grammar, `derivable_signals`, `inputs_digest`. No I/O. |
| `assemble.py` | Store + ledgers → `ControversyInputs`, per derived fact. No model. |
| `ledger.py` | `AssessmentLedger` — the private `(fact_id, digest, level, signals)` cache. |
| `assessor.py` | The `thinker` call, signal filtering, and the two golden entry points. |
| `escalate.py` | Claude arbitration and the uncurated-candidate writer. |
| `block.py` | Read/merge/render the canonical `controversy:` block; the `MintedRecord` for landing. |
| `run.py` | `assess_record` — the per-record orchestration every caller (CLI, job) shares. |

**New elsewhere:**

- `prompts/controversy-assessor/v-<hash>.md` + `CHANGELOG.md` — the fixed rubric.
- `prompts/controversy-escalation/v-<hash>.md` + `CHANGELOG.md` — Claude's arbitration prompt.
- `tools/orchestrator/src/langatlas_orchestrator/jobs/controversy.py` — the `nightly-controversy`
  job kind.
- `config/jobs/nightly-controversy.yaml` — its batch spec.
- `tests/golden/controversy/candidates/README.md` — the opportunistic lane's landing zone.
- Tests: `tools/research/tests/test_controversy_inputs.py`, `…_assemble.py`, `…_ledger.py`,
  `…_assessor.py`, `…_escalate.py`, `…_block.py`, `…_run.py`, `tools/research/tests/test_exit_3d.py`,
  `tools/orchestrator/tests/test_controversy_job.py`,
  `tools/validate/tests/test_controversy_block.py`.

**Modified:**

| File | Change |
|---|---|
| `ontology/schema/defs.schema.json` | Add the `controversyBlock` `$def`. |
| `ontology/schema/{concept,feature,edge,affects-quality-edge,rule,feature-instance}.schema.json` | Add `controversy` as the **last** property (normalization orders by schema property order). |
| `tools/validate/src/langatlas_validate/store.py` | Validate blocks: level range, signal grammar, no level-0 entries, `fact_id` agreement with the record's derived facts. |
| `tools/validate/src/langatlas_validate/version.py` | `_MACHINE_FIELDS` — a `controversy`-only edit classifies as `none`. |
| `config/research.yaml` | New `controversy:` section (alias, escalation role, batch knobs). |
| `tools/research/src/langatlas_research/config.py` | `ControversyConfig` + `ResearchConfig.controversy`. |
| `tools/research/src/langatlas_research/errors.py` | `ControversyInputRefused`, `AssessorOutputInvalid`. |
| `tools/research/src/langatlas_research/paths.py` | `private_controversy_dir()`. |
| `tools/research/src/langatlas_research/cli.py` | `langatlas-research controversy {assess,status,goldens}`. |
| `config/ingest.yaml` | `goldens.controversy_assessor_entry_point` → the real assessor. |
| `config/jobs/crontab.example` | The nightly controversy line. |
| `.github/workflows/ci.yml` | Run the new validate-package test file; the research suite already runs whole. |
| `tests/golden/controversy/README.md` | Point at the live assessor, the candidates lane, and the `--directory tools/research` invocation. |

## Shared shapes (read before any task)

These names are used across tasks; they are defined once, in Task 1 and Task 2, and every later
task depends on these exact signatures.

```python
# langatlas_research.controversy.inputs
ALLOWED = ("debates", "contradiction_records", "verdicts", "source_strength",
           "assessment_spread")          # re-exported from langatlas_ingest.goldens.items

@dataclass(frozen=True)
class ControversyInputs:
    debates: tuple[dict, ...] = ()
    contradiction_records: tuple[dict, ...] = ()
    verdicts: tuple[dict, ...] = ()
    source_strength: dict = field(default_factory=dict)
    assessment_spread: dict = field(default_factory=dict)

    def as_dict(self) -> dict: ...
    @classmethod
    def from_mapping(cls, raw: dict) -> "ControversyInputs": ...   # raises ControversyInputRefused

def derivable_signals(inputs: ControversyInputs) -> set[str]: ...
def inputs_digest(inputs: ControversyInputs) -> str: ...           # 16 hex

# langatlas_research.controversy.assessor
@dataclass(frozen=True)
class Assessment:
    fact_id: str
    level: int
    signals: tuple[str, ...]
    alternative: int | None = None
    model: str = ""
    prompt: str = ""
    run_id: str = ""
    escalated_to: str | None = None       # None | "claude"

def assess_inputs(ctx, fact_id: str, inputs: ControversyInputs, *, alias: str,
                  prompt: PromptRef | None = None) -> Assessment: ...
def needs_escalation(assessment: Assessment) -> bool: ...

# langatlas_research.controversy.assemble
def assemble_inputs(fact: dict, *, record: dict, repo_root: Path, ledger: VerdictLedger,
                    source_facts: dict, contradictions: list[dict],
                    debates: dict[str, dict]) -> ControversyInputs: ...
def fact_field(claim: str) -> str: ...     # "base" | "since" | "characteristic" | …

# langatlas_research.controversy.ledger
class AssessmentLedger:
    def previous(self, fact_id: str) -> tuple[str, int, tuple[str, ...]] | None: ...
    def record(self, assessment: Assessment, *, digest: str) -> None: ...

# langatlas_research.controversy.run
@dataclass(frozen=True)
class RecordOutcome:
    record_path: str
    assessed: int = 0        # facts that got a model call
    skipped: int = 0         # facts whose digest was unchanged
    escalated: int = 0
    changed: bool = False    # the record text changed and was landed
    levels: dict = field(default_factory=dict)   # fact_id -> level

def assess_record(ctx, record_path: str, *, repo_root: Path, config, deps) -> RecordOutcome: ...
```

---

## Task 1: The structured-input shape, the closed signal grammar, and config

**Files:**
- Create: `tools/research/src/langatlas_research/controversy/__init__.py`
- Create: `tools/research/src/langatlas_research/controversy/inputs.py`
- Modify: `tools/research/src/langatlas_research/errors.py`
- Modify: `tools/research/src/langatlas_research/paths.py`
- Modify: `tools/research/src/langatlas_research/config.py`
- Modify: `config/research.yaml`
- Test: `tools/research/tests/test_controversy_inputs.py`

**Interfaces:**
- Consumes: `langatlas_ingest.goldens.items.ALLOWED_CONTROVERSY_INPUTS`,
  `FORBIDDEN_CONTROVERSY_INPUTS`, `CONTROVERSY_LEVELS`;
  `langatlas_research.config.ClaudeRoleConfig`.
- Produces: `ControversyInputs`, `derivable_signals`, `inputs_digest`, `SIGNAL_RE`,
  `ControversyInputRefused`, `AssessorOutputInvalid`, `private_controversy_dir`,
  `ControversyConfig`, `ResearchConfig.controversy`.

- [ ] **Step 1: Write the failing tests**

```python
# tools/research/tests/test_controversy_inputs.py
"""§6.4's structured-input allow-list and the closed signal grammar, with no model in sight."""
import pytest

from langatlas_research.controversy.inputs import (
    ControversyInputs, derivable_signals, inputs_digest,
)
from langatlas_research.errors import ControversyInputRefused

DEBATE = {"id": "d-01-typing-003", "outcome": "escalated", "standing_dissent": True, "rounds": 4}
CTR = {"id": "ctr-0123456789ab", "type": "verification", "status": "open", "participants": 2}
VERDICT = {"fact": "f-000000000115", "citation": 1, "verdict": "contradicted",
           "field": "base", "tier": "A"}


def test_from_mapping_accepts_exactly_the_five_permitted_keys():
    inputs = ControversyInputs.from_mapping(
        {"debates": [DEBATE], "contradiction_records": [CTR], "verdicts": [VERDICT],
         "source_strength": {"tier_a": 2, "tier_b": 0, "independent_corroborations": 1},
         "assessment_spread": {}})
    assert inputs.debates == (DEBATE,)
    assert inputs.as_dict()["source_strength"]["tier_a"] == 2


def test_from_mapping_refuses_a_human_challenge_derived_input():
    with pytest.raises(ControversyInputRefused, match="closure_attempt"):
        ControversyInputs.from_mapping({"verdicts": [], "closure_attempt": {"outcome": "confirmed-open"}})


def test_from_mapping_refuses_an_unknown_input():
    with pytest.raises(ControversyInputRefused, match="source_text"):
        ControversyInputs.from_mapping({"source_text": "..."})


def test_derivable_signals_is_exactly_what_the_inputs_can_justify():
    inputs = ControversyInputs.from_mapping(
        {"debates": [DEBATE], "contradiction_records": [CTR], "verdicts": [VERDICT],
         "assessment_spread": {"quality_edge_strength": ["strong", "weak"]}})
    assert derivable_signals(inputs) == {
        "debate:d-01-typing-003:standing-dissent",
        "contradiction:ctr-0123456789ab:open",
        "verdict:contradicted:base",
        "assessment-spread:quality_edge_strength",
    }


def test_a_debate_without_standing_dissent_signals_its_outcome():
    inputs = ControversyInputs.from_mapping(
        {"debates": [{"id": "d-01-typing-004", "outcome": "converged-after-revision",
                      "standing_dissent": False, "rounds": 2}]})
    assert derivable_signals(inputs) == {"debate:d-01-typing-004:converged-after-revision"}


def test_supported_verdicts_are_not_signals():
    """A signal is a *disagreement* reference. A clean support justifies nothing — it is the
    absence of signals that makes a fact level 0."""
    inputs = ControversyInputs.from_mapping(
        {"verdicts": [{"fact": "f-1", "citation": 1, "verdict": "supported",
                       "field": "base", "tier": "A"}]})
    assert derivable_signals(inputs) == set()


def test_digest_is_stable_across_key_order_and_changes_with_content():
    a = ControversyInputs.from_mapping({"verdicts": [VERDICT], "debates": [DEBATE]})
    b = ControversyInputs.from_mapping({"debates": [DEBATE], "verdicts": [VERDICT]})
    c = ControversyInputs.from_mapping({"debates": [DEBATE]})
    assert inputs_digest(a) == inputs_digest(b)
    assert inputs_digest(a) != inputs_digest(c)
    assert len(inputs_digest(a)) == 16
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/research run pytest tests/test_controversy_inputs.py -m '' -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_research.controversy'`

- [ ] **Step 3: Add the two errors**

Append to `tools/research/src/langatlas_research/errors.py`:

```python
class ControversyInputRefused(ResearchError):
    """§6.4's allow-list: the assessor sees exactly `debates`, `contradiction_records`,
    `verdicts`, `source_strength` and `assessment_spread`. Everything human-challenge-derived
    — GitHub activity, challenge counts, and (2026-07-20) a contradiction record's
    `closure_attempt.outcome` — is refused here rather than filtered later, because a filter
    that is ever forgotten silently calibrates the assessor against a fiction."""


class AssessorOutputInvalid(ResearchError):
    """The assessor returned a level outside 0-3, or output its schema rejects. There is no
    repair turn: the fact keeps whatever level it already had and the run says so."""
```

- [ ] **Step 4: Write `inputs.py`**

```python
# tools/research/src/langatlas_research/controversy/inputs.py
"""§6.4's structured inputs and the closed signal grammar.

Two rules are load-bearing here and nowhere else:

1. **Allow-list construction, not redaction.** `from_mapping` refuses anything outside the
   five permitted keys, so an assessor input can never acquire a human-challenge-derived
   field by someone adding one upstream. This mirrors D24's `whitelist_payload`.
2. **A signal is a machine reference the inputs can actually justify.** §6.4 makes the
   `signals` list *the* justification — there is no free-prose rationale to fall back on — so a
   signal the inputs cannot produce is not a weak justification, it is a fabricated one, and
   `assessor.py` drops it.
"""
import hashlib
import json
from dataclasses import dataclass, field

from langatlas_ingest.goldens.items import (
    ALLOWED_CONTROVERSY_INPUTS as ALLOWED,
    FORBIDDEN_CONTROVERSY_INPUTS as FORBIDDEN,
)

from langatlas_research.errors import ControversyInputRefused

# Verdicts that say something disagrees. `supported` and `source-unavailable` justify no
# signal: the first is agreement, the second is a missing measurement.
_DISSENTING_VERDICTS = frozenset({"partial", "unsupported", "contradicted",
                                  "locator-not-found"})


@dataclass(frozen=True)
class ControversyInputs:
    """Exactly what §6.4 lets the assessor see, in 2B's committed vocabulary."""

    debates: tuple[dict, ...] = ()
    contradiction_records: tuple[dict, ...] = ()
    verdicts: tuple[dict, ...] = ()
    source_strength: dict = field(default_factory=dict)
    assessment_spread: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        """The model-facing mapping, in the frozen key order.

        @returns a plain dict with all five keys present — an absent key and an empty one
            must look the same to the rubric, or "no debates" reads as "debates unknown"."""
        return {"debates": [dict(d) for d in self.debates],
                "contradiction_records": [dict(c) for c in self.contradiction_records],
                "verdicts": [dict(v) for v in self.verdicts],
                "source_strength": dict(self.source_strength),
                "assessment_spread": {k: list(v) for k, v in self.assessment_spread.items()}}

    @classmethod
    def from_mapping(cls, raw: dict) -> "ControversyInputs":
        """@raises ControversyInputRefused: any key outside `ALLOWED`, named explicitly so the
            failure message says which rule was broken."""
        for key in raw:
            if key in FORBIDDEN:
                raise ControversyInputRefused(
                    f"{key!r} is human-challenge-derived and is excluded from the assessor"
                    f" by §6.4")
            if key not in ALLOWED:
                raise ControversyInputRefused(
                    f"{key!r} is not one of §6.4's structured inputs {list(ALLOWED)}")
        return cls(debates=tuple(raw.get("debates") or ()),
                   contradiction_records=tuple(raw.get("contradiction_records") or ()),
                   verdicts=tuple(raw.get("verdicts") or ()),
                   source_strength=dict(raw.get("source_strength") or {}),
                   assessment_spread={k: list(v) for k, v
                                      in (raw.get("assessment_spread") or {}).items()})


def derivable_signals(inputs: ControversyInputs) -> set[str]:
    """Every machine reference these inputs justify — the universe the assessor may cite.

    Debate signals reuse 3C's rule verbatim (standing dissent outranks the outcome), because
    the debate record module and this one are scored by the same committed golden set."""
    signals: set[str] = set()
    for debate in inputs.debates:
        if debate.get("standing_dissent"):
            signals.add(f"debate:{debate['id']}:standing-dissent")
        else:
            signals.add(f"debate:{debate['id']}:{debate['outcome']}")
    for record in inputs.contradiction_records:
        signals.add(f"contradiction:{record['id']}:{record['status']}")
    for verdict in inputs.verdicts:
        if verdict.get("verdict") in _DISSENTING_VERDICTS:
            signals.add(f"verdict:{verdict['verdict']}:{verdict.get('field', 'base')}")
    for key in inputs.assessment_spread:
        signals.add(f"assessment-spread:{key}")
    return signals


def inputs_digest(inputs: ControversyInputs) -> str:
    """A content key over the assessed inputs — the whole mechanism behind §6.4's
    "unchanged inputs => unchanged level, so a re-run is free".

    Canonical JSON with sorted keys: two assemblies that differ only in dict ordering are the
    same inputs and must not trigger a re-assessment.

    @returns 16 hex chars, matching the store's other content keys."""
    payload = json.dumps(inputs.as_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
```

Create `tools/research/src/langatlas_research/controversy/__init__.py` as an empty file.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv --directory tools/research run pytest tests/test_controversy_inputs.py -m '' -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Add the private-tier path**

Append to `tools/research/src/langatlas_research/paths.py`:

```python
def private_controversy_dir() -> Path:
    """The private, non-git tier for the assessment ledger (§2.2). Same reasoning as
    `VerdictLedger`: a level is a measurement about the corpus made by whichever model ran
    last night, and putting its bookkeeping in git would make the canonical store depend on
    that. Read through the module attribute so tests can monkeypatch `PRIVATE_DIR`."""
    from langatlas_pipeline import paths as pipeline_paths

    return pipeline_paths.PRIVATE_DIR / "research" / "controversy"
```

- [ ] **Step 7: Add the config section**

Append to `config/research.yaml`:

```yaml
controversy:
  # D21/D25 (Stage 3D). The volume lane is the university API's thinker; Claude is only the
  # escalation target and the golden-set calibrator (§6.4/§7.1).
  alias: thinker                    # deepseek-v4-pro-thinking, per config/providers.yaml
  # A record's facts are assessed together and landed in one commit, so this bounds how much
  # of the store one nightly invocation walks. D25's nightly budget is ~200 facts.
  max_facts_per_run: 200
  # Assessment spread only counts as a signal once there is something to disagree about.
  spread_min_assessments: 2
  escalation:
    model: null
    max_turns: 20
    max_claude_messages: 40
    max_packet_terms: 0             # the escalation packet is structured inputs, not terms
    max_candidates: 1
```

Add to `tools/research/src/langatlas_research/config.py`:

```python
@dataclass(frozen=True)
class ControversyConfig:
    alias: str
    max_facts_per_run: int
    spread_min_assessments: int
    escalation: ClaudeRoleConfig
```

and in `ResearchConfig`, add the field `controversy: ControversyConfig` plus, in `load`:

```python
        controversy = data["controversy"]
        ...
                   controversy=ControversyConfig(
                       alias=controversy["alias"],
                       max_facts_per_run=controversy["max_facts_per_run"],
                       spread_min_assessments=controversy["spread_min_assessments"],
                       escalation=ClaudeRoleConfig(**controversy["escalation"])),
```

- [ ] **Step 8: Verify the config loads**

Run: `uv --directory tools/research run python -c "from langatlas_research.config import ResearchConfig; from langatlas_research.paths import research_config_path; c = ResearchConfig.load(research_config_path()); print(c.controversy)"`
Expected: `ControversyConfig(alias='thinker', max_facts_per_run=200, spread_min_assessments=2, escalation=ClaudeRoleConfig(model=None, max_turns=20, max_claude_messages=40, max_packet_terms=0, max_candidates=1))`

- [ ] **Step 9: Run the whole research suite**

Run: `uv --directory tools/research run pytest -m '' -q`
Expected: PASS — the existing suite is untouched; `test_survey_config.py` still loads the config.

- [ ] **Step 10: Commit**

```bash
git add tools/research/src/langatlas_research/controversy tools/research/src/langatlas_research/errors.py \
        tools/research/src/langatlas_research/paths.py tools/research/src/langatlas_research/config.py \
        config/research.yaml tools/research/tests/test_controversy_inputs.py \
        docs/superpowers/plans/2026-09-16-stage-3d-controversy-assessor.md
git commit -m "feat(#stage-3d): fix the controversy assessor's input allow-list and signal grammar"
```

---

## Task 2: Input assembly — the canonical store and the ledgers, with no model

**Files:**
- Create: `tools/research/src/langatlas_research/controversy/assemble.py`
- Test: `tools/research/tests/test_controversy_assemble.py`

**Interfaces:**
- Consumes: `langatlas_validate.compile.derive_facts`, `langatlas_validate.store.iter_store_records`,
  `langatlas_ingest.verify.ledger.VerdictLedger`, `langatlas_ingest.verify.sources.load_source_facts`
  / `are_independent`, `langatlas_ingest.verify.verdicts.ADMISSIBLE_TIERS`,
  `langatlas_ingest.verify.contradictions.load_records`,
  `langatlas_research.draft.debate_record.as_controversy_input` / `iter_debates`,
  Task 1's `ControversyInputs`.
- Produces: `fact_field`, `record_facts`, `contradiction_projection`, `source_strength`,
  `assessment_spread`, `assemble_inputs`, `AssembleDeps`.

**The field vocabulary.** 2B's cases carry `field: base | since | characteristic`. Facts are
already per-field (§3.2), so the fact's *own* field name comes from its claim kind, and `since`
is the one extra row a pair verdict can contribute on top:

| Claim kind | `field` |
|---|---|
| `node-definition`, `instance-exists`, `edge-exists`, `rule-exists` | `base` |
| `characteristic` | `characteristic` |
| `syntax-valid` | `syntax` |
| `edge-polarity` | `polarity` |
| `quality-assessment` | `quality-assessment` |
| (any kind, when the pair carries a `since_status`) | `since` (an additional row) |

This is what makes 2B's `c-bootstrap-0006` legible to a real fact: a `partial` on a
`characteristic` fact is a noted weakness (level 1), the same `partial` on a `base` or `since`
row is a live dispute (level 2) — §6.4's "partials on load-bearing fields" distinction,
mechanically derived rather than judged.

- [ ] **Step 1: Write the failing tests**

```python
# tools/research/tests/test_controversy_assemble.py
"""Assembly is the half of the assessor that has to be right whatever any model says: it is
where §6.4's exclusions are enforced, and it runs with no provider at all."""
import pytest

from langatlas_ingest.verify.verdicts import PairVerdict
from langatlas_research.controversy.assemble import (
    assemble_inputs, contradiction_projection, fact_field, source_strength,
)


class _Ledger:
    def __init__(self, rows):
        self._rows = rows

    def latest_for(self, fact_id):
        return [r for r in self._rows if r.fact_id == fact_id]


def _tier(source_id, tier, **csl):
    return type("S", (), {"id": source_id, "tier": tier, "grounding": "",
                          "locator_kinds": (), "csl": csl})()


FACT = {"fact_id": "f-aaaaaaaaaaaa",
        "claim": "node-definition(structural-typing, sha256-16=0123456789abcdef)",
        "record_path": "features/structural-typing.yaml",
        "sources": [{"source": "pierce-tapl-2002", "locator": "p. 251"},
                    {"source": "scott-plp", "locator": "§7.2.4"}]}

SOURCES = {"pierce-tapl-2002": _tier("pierce-tapl-2002", "A", publisher="MIT Press",
                                     author=[{"family": "Pierce", "given": "B"}]),
           "scott-plp": _tier("scott-plp", "A", publisher="Morgan Kaufmann",
                              author=[{"family": "Scott", "given": "M"}])}


def test_fact_field_reads_the_claim_kind():
    assert fact_field(FACT["claim"]) == "base"
    assert fact_field("characteristic(fi.rust.pattern-matching, c-exhaustive, sha256-16=ab)") \
        == "characteristic"
    assert fact_field("quality-assessment(edge.affects-quality.x.y, a-1)") == "quality-assessment"


def test_verdict_rows_carry_field_and_tier_and_a_stable_citation_index():
    ledger = _Ledger([
        PairVerdict(fact_id="f-aaaaaaaaaaaa", source_id="scott-plp", locator="§7.2.4",
                    verdict="contradicted"),
        PairVerdict(fact_id="f-aaaaaaaaaaaa", source_id="pierce-tapl-2002", locator="p. 251",
                    verdict="supported")])
    inputs = assemble_inputs(FACT, record={}, ledger=ledger, source_facts=SOURCES,
                             contradictions=[], debates={})
    assert sorted(inputs.verdicts, key=lambda v: v["citation"]) == [
        {"fact": "f-aaaaaaaaaaaa", "citation": 1, "verdict": "supported",
         "field": "base", "tier": "A"},
        {"fact": "f-aaaaaaaaaaaa", "citation": 2, "verdict": "contradicted",
         "field": "base", "tier": "A"}]


def test_a_since_status_adds_its_own_row_without_replacing_base():
    ledger = _Ledger([PairVerdict(fact_id="f-aaaaaaaaaaaa", source_id="pierce-tapl-2002",
                                  locator="p. 251", verdict="partial",
                                  since_status="as-of-supported")])
    inputs = assemble_inputs(FACT, record={}, ledger=ledger, source_facts=SOURCES,
                             contradictions=[], debates={})
    assert {(v["field"], v["verdict"]) for v in inputs.verdicts} == {
        ("base", "partial"), ("since", "partial")}


def test_source_strength_counts_supporting_citations_by_tier():
    pairs = [PairVerdict(fact_id="f-1", source_id="pierce-tapl-2002", locator="p. 251",
                         verdict="supported"),
             PairVerdict(fact_id="f-1", source_id="scott-plp", locator="§7.2.4",
                         verdict="supported")]
    assert source_strength(pairs, SOURCES) == {"tier_a": 2, "tier_b": 0,
                                               "independent_corroborations": 2}


def test_a_contradicted_citation_does_not_corroborate():
    pairs = [PairVerdict(fact_id="f-1", source_id="pierce-tapl-2002", locator="p. 251",
                         verdict="supported"),
             PairVerdict(fact_id="f-1", source_id="scott-plp", locator="§7.2.4",
                         verdict="contradicted")]
    assert source_strength(pairs, SOURCES) == {"tier_a": 1, "tier_b": 0,
                                               "independent_corroborations": 0}


def test_contradiction_projection_drops_everything_human_derived():
    record = {"id": "ctr-0123456789ab", "type": "verification", "status": "open",
              "participants": ["f-aaaaaaaaaaaa", "citation:scott-plp:§7.2.4"],
              "mechanism": "reconciler", "detail": "the two books disagree",
              "chat_run_id": "2026-09-16-r4-debate-01",
              "closure": {"method": "human-adjudication", "detail": "confirmed open"}}
    assert contradiction_projection(record) == {
        "id": "ctr-0123456789ab", "type": "verification", "status": "open", "participants": 2}


def test_only_contradictions_naming_this_fact_are_included():
    mine = {"id": "ctr-111111111111", "type": "verification", "status": "open",
            "participants": ["citation:scott-plp:§7.2.4", "f-aaaaaaaaaaaa"]}
    theirs = {"id": "ctr-222222222222", "type": "verification", "status": "open",
              "participants": ["f-999999999999", "f-888888888888"]}
    inputs = assemble_inputs(FACT, record={}, ledger=_Ledger([]), source_facts=SOURCES,
                             contradictions=[mine, theirs], debates={})
    assert [c["id"] for c in inputs.contradiction_records] == ["ctr-111111111111"]


def test_the_records_debate_is_projected_through_3c_not_read_raw():
    debate = {"id": "d-01-typing-003", "cycle": 1, "theme": "typing",
              "target": {"list": "nodes", "key": "structural-typing"},
              "opened": "2026-09-16", "runs": {"debate": "r"}, "triggers": [],
              "personas": {"challenger_a": "the type theorist"}, "pre_challenge": {},
              "messages": [{"seq": 1, "role": "proposer", "persona": "p", "text": "t"}],
              "resolution": {"outcome": "escalated", "disposition": "escalate",
                             "standing_dissent": True, "rounds": 4,
                             "upheld_challenges": [], "rationale": "no convergence"}}
    inputs = assemble_inputs(FACT, record={"provenance": {"debate_id": "d-01-typing-003"}},
                             ledger=_Ledger([]), source_facts=SOURCES, contradictions=[],
                             debates={"d-01-typing-003": debate})
    assert inputs.debates == ({"id": "d-01-typing-003", "outcome": "escalated",
                              "standing_dissent": True, "rounds": 4},)


def test_a_dangling_debate_id_is_ignored_rather_than_raising():
    """A record can outlive a debate record the developer deleted. The assessor degrades to
    "no debate signal" — it never takes the nightly batch down with it."""
    inputs = assemble_inputs(FACT, record={"provenance": {"debate_id": "d-01-typing-404"}},
                             ledger=_Ledger([]), source_facts=SOURCES, contradictions=[],
                             debates={})
    assert inputs.debates == ()


def test_assembly_never_produces_a_forbidden_key():
    inputs = assemble_inputs(FACT, record={"provenance": {"debate_id": None},
                                           "notes": "agent prose"},
                             ledger=_Ledger([]), source_facts=SOURCES, contradictions=[],
                             debates={})
    assert set(inputs.as_dict()) == {"debates", "contradiction_records", "verdicts",
                                     "source_strength", "assessment_spread"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/research run pytest tests/test_controversy_assemble.py -m '' -v`
Expected: FAIL — `ImportError: cannot import name 'assemble_inputs'`

- [ ] **Step 3: Write `assemble.py`**

```python
# tools/research/src/langatlas_research/controversy/assemble.py
"""Canonical store + ledgers -> §6.4's five structured inputs, for one derived fact.

Assembly is allow-list construction, exactly like D24's `whitelist_payload`: a record carries
prose, provenance, a proposer and a `detail` string, and the way to keep those away from the
assessor is to never assemble them. Nothing here calls a model, so it is fully testable
without a provider — which matters, because this is where §6.4's exclusions actually live."""
from dataclasses import dataclass
from pathlib import Path

from langatlas_ingest.verify.sources import are_independent
from langatlas_ingest.verify.verdicts import ADMITTING_VERDICTS

from langatlas_research.controversy.inputs import ControversyInputs

# Claim kind -> the `field` name 2B's cases use. `base` is the default for a fact whose claim
# *is* the record's load-bearing assertion; the rest name the field they belong to, which is
# how §6.4's "partials on load-bearing fields" distinction stays mechanical.
_FIELD_OF_KIND = {
    "node-definition": "base",
    "instance-exists": "base",
    "edge-exists": "base",
    "rule-exists": "base",
    "characteristic": "characteristic",
    "syntax-valid": "syntax",
    "edge-polarity": "polarity",
    "quality-assessment": "quality-assessment",
}


@dataclass(frozen=True)
class AssembleDeps:
    """Everything assembly reads, gathered once per run rather than per fact — a nightly
    batch over the whole store would otherwise re-read every source record thousands of
    times."""

    ledger: object                       # VerdictLedger (duck-typed: `latest_for`)
    source_facts: dict                   # source_id -> SourceFacts
    contradictions: list                 # contradictions.yaml records
    debates: dict                        # debate_id -> debate record


def fact_field(claim: str) -> str:
    """@param claim: the canonical claim string (§3.5), which always opens with its kind.
    @returns the `field` name this fact's verdict rows carry; `base` for an unknown kind, the
        conservative direction — an unknown field treated as load-bearing over-reports
        controversy rather than hiding it."""
    kind = claim.split("(", 1)[0]
    return _FIELD_OF_KIND.get(kind, "base")


def _citation_index(fact: dict, pair) -> int:
    """1-based position of the pair's citation in the fact's own `sources:` list.

    Positional rather than by source id because 2B's cases number citations, and because one
    source can legitimately back a fact at two different locators."""
    for index, entry in enumerate(fact.get("sources") or [], start=1):
        if entry.get("source") == pair.source_id and entry.get("locator") == pair.locator:
            return index
    return 0                              # a verdict for a citation the record no longer lists


def verdict_rows(fact: dict, pairs, source_facts: dict) -> list[dict]:
    """One row per (citation, field). A pair contributes its base row always, and a second
    `since` row whenever the verifier decided a `since_status` for it."""
    rows = []
    field = fact_field(fact["claim"])
    for pair in pairs:
        tier = getattr(source_facts.get(pair.source_id), "tier", "")
        index = _citation_index(fact, pair)
        rows.append({"fact": fact["fact_id"], "citation": index, "verdict": pair.verdict,
                     "field": field, "tier": tier})
        if pair.since_status:
            rows.append({"fact": fact["fact_id"], "citation": index,
                         "verdict": "supported" if pair.since_status == "since-supported"
                                    else "partial",
                         "field": "since", "tier": tier})
    return sorted(rows, key=lambda row: (row["citation"], row["field"]))


def source_strength(pairs, source_facts: dict) -> dict:
    """§6.4's "mechanically-computed source-strength context", in 2B's exact three keys.

    Only *supporting* citations count: a contradicted tier-A citation is a disagreement
    signal, not backing, and counting it as strength would let a fact look better evidenced
    the more its sources fight. Independence reuses §6.3's check verbatim rather than a second
    copy of the rule."""
    supporting = sorted({pair.source_id for pair in pairs
                         if pair.verdict in ADMITTING_VERDICTS and pair.source_id in source_facts})
    tiers = [source_facts[s].tier for s in supporting]
    corroborations = sum(
        1 for s in supporting
        if any(are_independent(source_facts[s], source_facts[other])
               for other in supporting if other != s))
    return {"tier_a": tiers.count("A"), "tier_b": tiers.count("B"),
            "independent_corroborations": corroborations}


def contradiction_projection(record: dict) -> dict:
    """The only four fields of a contradiction record the assessor may see.

    `detail` is agent-written prose, `chat_run_id` is a transcript pointer, `mechanism` says
    who minted it — none is a disagreement measurement. `closure` is dropped outright: per the
    2026-07-20 withdrawal an open record's `closure_attempt.outcome: confirmed-open` is
    human-challenge-derived and the assessor must not see it, and dropping the whole closure
    block is the version of that rule nobody can forget half of."""
    return {"id": record["id"], "type": record["type"], "status": record["status"],
            "participants": len(record.get("participants") or [])}


def _mentions(record: dict, fact: dict, record_id: str | None) -> bool:
    """True when a contradiction record names this fact, one of its citations, or the record
    that owns it. §6.5's participants are `citation:<source>:<locator>` strings or record ids."""
    participants = set(record.get("participants") or [])
    if fact["fact_id"] in participants or (record_id and record_id in participants):
        return True
    return any(f"citation:{e.get('source')}:{e.get('locator')}" in participants
               for e in fact.get("sources") or [])


def assessment_spread(record: dict, *, min_assessments: int = 2) -> dict:
    """The spread of attributed quality assessments on an `affects-quality` edge (§3.4: "no
    forced consensus" — the record keeps every assessor's view, and disagreement among them is
    exactly what level 2 is about).

    Keyed `<quality-id>_edge_strength`, matching 2B's `quality_edge_strength` /
    `readability_edge_strength` shape. A single assessment is not a spread."""
    assessments = record.get("assessments") or []
    if len(assessments) < min_assessments:
        return {}
    quality = record.get("to") or "quality"
    key = f"{quality}_edge_strength"
    return {key: sorted(f"{a['polarity']}:{a['strength']}" if a.get("polarity") else a["strength"]
                        for a in assessments)}


def assemble_inputs(fact: dict, *, record: dict, ledger, source_facts: dict,
                    contradictions: list, debates: dict,
                    spread_min_assessments: int = 2) -> ControversyInputs:
    """Build one fact's structured inputs.

    @param fact: one `derive_facts` row (`fact_id`, `claim`, `record_path`, `sources`).
    @param record: the owning record's data, read for `provenance.debate_id`, `id` and (for an
        `affects-quality` edge) `assessments` — and for nothing else.
    @param debates: debate_id -> debate record. A debate id with no record is ignored: a
        deleted debate is a missing signal, not a reason to fail a nightly batch.
    @returns the inputs, guaranteed to carry exactly §6.4's five keys."""
    from langatlas_research.draft.debate_record import as_controversy_input

    pairs = ledger.latest_for(fact["fact_id"])
    debate_id = (record.get("provenance") or {}).get("debate_id")
    debate = debates.get(debate_id) if debate_id else None
    return ControversyInputs.from_mapping({
        "debates": [as_controversy_input(debate)] if debate else [],
        "contradiction_records": [contradiction_projection(c) for c in contradictions
                                  if _mentions(c, fact, record.get("id"))],
        "verdicts": verdict_rows(fact, pairs, source_facts),
        "source_strength": source_strength(pairs, source_facts),
        "assessment_spread": assessment_spread(record,
                                               min_assessments=spread_min_assessments),
    })


def load_deps(repo_root: Path, ledger) -> AssembleDeps:
    """Gather the run-wide inputs once. Sources and contradictions are read from git, never
    from Postgres — tier and dispute state are canonical data (D1)."""
    from langatlas_ingest.verify.contradictions import load_records
    from langatlas_ingest.verify.sources import load_source_facts
    from langatlas_research.draft.debate_record import iter_debates

    return AssembleDeps(
        ledger=ledger,
        source_facts=load_source_facts(Path(repo_root) / "sources"),
        contradictions=load_records(Path(repo_root) / "contradictions.yaml"),
        debates={d["id"]: d for d in iter_debates(repo_root)})


def record_facts(path: Path, kind: str, text: str, data: dict) -> list[dict]:
    """The derived facts of one record — the assessor's work list for that file.

    Wraps `derive_facts`' whole-store signature for the single-record case so the nightly job
    never has to re-derive the entire store to assess one file."""
    from langatlas_validate.compile import derive_facts

    return derive_facts([(path, kind, text, data)])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory tools/research run pytest tests/test_controversy_assemble.py -m '' -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/research/src/langatlas_research/controversy/assemble.py \
        tools/research/tests/test_controversy_assemble.py \
        docs/superpowers/plans/2026-09-16-stage-3d-controversy-assessor.md
git commit -m "feat(#stage-3d): project the store and ledgers into the assessor's structured inputs"
```

---

## Task 3: The private assessment ledger — what makes a re-run free

**Files:**
- Create: `tools/research/src/langatlas_research/controversy/ledger.py`
- Test: `tools/research/tests/test_controversy_ledger.py`

**Interfaces:**
- Consumes: `private_controversy_dir` (Task 1), `Assessment` (Task 4 — the dataclass is defined
  there; this module only reads `.fact_id`, `.level`, `.signals`, so it stays import-free of it).
- Produces: `AssessmentLedger` with `previous(fact_id)`, `record(assessment, digest=...)`,
  `levels()`, `close()`, context-manager support.

- [ ] **Step 1: Write the failing tests**

```python
# tools/research/tests/test_controversy_ledger.py
"""The ledger is a cache, never ground truth: losing it costs one expensive re-run and
nothing else. These tests pin the one property the nightly batch depends on — an unchanged
digest means the model is never called again."""
from langatlas_research.controversy.ledger import AssessmentLedger


class _A:
    def __init__(self, fact_id, level, signals, escalated_to=None):
        self.fact_id, self.level, self.signals = fact_id, level, tuple(signals)
        self.model, self.prompt, self.run_id = "deepseek-v4-pro-thinking", "p@v-1", "r-1"
        self.escalated_to = escalated_to


def test_an_unseen_fact_has_no_previous_assessment(tmp_path):
    with AssessmentLedger(tmp_path / "a.sqlite") as ledger:
        assert ledger.previous("f-aaaaaaaaaaaa") is None


def test_a_recorded_assessment_comes_back_by_digest(tmp_path):
    with AssessmentLedger(tmp_path / "a.sqlite") as ledger:
        ledger.record(_A("f-aaaaaaaaaaaa", 2, ["verdict:partial:since"]), digest="0123456789abcdef")
        assert ledger.previous("f-aaaaaaaaaaaa") == ("0123456789abcdef", 2,
                                                     ("verdict:partial:since",))


def test_re_recording_the_same_fact_replaces_rather_than_duplicates(tmp_path):
    with AssessmentLedger(tmp_path / "a.sqlite") as ledger:
        ledger.record(_A("f-a", 1, []), digest="aaaa")
        ledger.record(_A("f-a", 3, ["verdict:contradicted:base"]), digest="bbbb")
        assert ledger.previous("f-a") == ("bbbb", 3, ("verdict:contradicted:base",))
        assert ledger.levels() == {"f-a": 3}


def test_the_ledger_survives_reopening(tmp_path):
    path = tmp_path / "a.sqlite"
    with AssessmentLedger(path) as ledger:
        ledger.record(_A("f-a", 2, ["assessment-spread:readability_edge_strength"]), digest="cc")
    with AssessmentLedger(path) as reopened:
        assert reopened.previous("f-a")[1] == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/research run pytest tests/test_controversy_ledger.py -m '' -v`
Expected: FAIL — `ModuleNotFoundError: langatlas_research.controversy.ledger`

- [ ] **Step 3: Write `ledger.py`**

```python
# tools/research/src/langatlas_research/controversy/ledger.py
"""The private assessment ledger: `(fact_id, inputs_digest, level, signals)`.

Why this is not in git, when the level itself is: §6.4 makes an absent block mean level 0, and
level 0 is the overwhelming majority of facts — so a git-resident digest could not cover the
case the free-re-run rule exists for. It is also, exactly like `VerdictLedger`, a measurement
made by whichever model ran last night rather than a fact about a language (D23).

It is a cache. A deleted ledger costs one full re-assessment and nothing else; it can never
disagree with the store in a way that matters, because the store's block is what the site and
the bundle read."""
import json
import sqlite3
from pathlib import Path

from langatlas_research.paths import private_controversy_dir

LEDGER_SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS assessments (
    fact_id       TEXT PRIMARY KEY,
    inputs_digest TEXT NOT NULL,
    level         INTEGER NOT NULL,
    signals       TEXT NOT NULL DEFAULT '[]',
    model         TEXT NOT NULL DEFAULT '',
    prompt        TEXT NOT NULL DEFAULT '',
    run_id        TEXT NOT NULL DEFAULT '',
    escalated_to  TEXT,
    assessed_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class AssessmentLedger:
    """@param db_path: defaults to `<private>/research/controversy/assessments.sqlite`."""

    def __init__(self, db_path: Path | None = None):
        self.path = Path(db_path or private_controversy_dir() / "assessments.sqlite")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_DDL)
        self.conn.commit()

    def previous(self, fact_id: str) -> tuple[str, int, tuple[str, ...]] | None:
        """@returns `(inputs_digest, level, signals)` from the last assessment, or None."""
        row = self.conn.execute(
            "SELECT inputs_digest, level, signals FROM assessments WHERE fact_id = ?",
            (fact_id,)).fetchone()
        if row is None:
            return None
        return row["inputs_digest"], int(row["level"]), tuple(json.loads(row["signals"]))

    def record(self, assessment, *, digest: str) -> None:
        """Latest-wins per fact: the history lives in git (the block) and in the transcript
        (D18), so a second copy here would be a third place to disagree."""
        self.conn.execute(
            "INSERT OR REPLACE INTO assessments (fact_id, inputs_digest, level, signals,"
            " model, prompt, run_id, escalated_to) VALUES (?,?,?,?,?,?,?,?)",
            (assessment.fact_id, digest, int(assessment.level),
             json.dumps(list(assessment.signals)), assessment.model, assessment.prompt,
             assessment.run_id, assessment.escalated_to))
        self.conn.commit()

    def levels(self) -> dict:
        """fact_id -> level, for `controversy status`."""
        return {row["fact_id"]: int(row["level"])
                for row in self.conn.execute("SELECT fact_id, level FROM assessments")}

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "AssessmentLedger":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory tools/research run pytest tests/test_controversy_ledger.py -m '' -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/research/src/langatlas_research/controversy/ledger.py \
        tools/research/tests/test_controversy_ledger.py \
        docs/superpowers/plans/2026-09-16-stage-3d-controversy-assessor.md
git commit -m "feat(#stage-3d): cache assessed input digests so an unchanged fact costs nothing"
```

---

## Task 4: The canonical `controversy:` block — schema, validation, and the version-bump exemption

**Files:**
- Modify: `ontology/schema/defs.schema.json`
- Modify: `ontology/schema/concept.schema.json`, `feature.schema.json`, `edge.schema.json`,
  `affects-quality-edge.schema.json`, `rule.schema.json`, `feature-instance.schema.json`
- Modify: `tools/validate/src/langatlas_validate/store.py`
- Modify: `tools/validate/src/langatlas_validate/version.py`
- Create: `tools/research/src/langatlas_research/controversy/block.py`
- Test: `tools/validate/tests/test_controversy_block.py`
- Test: `tools/research/tests/test_controversy_block.py`

**Interfaces:**
- Consumes: `langatlas_validate.normalize.normalize_record`, `langatlas_validate.compile.derive_facts`,
  `langatlas_research.mint.MintedRecord` / `content_digest` / `dump_yaml`, Task 1's `SIGNAL_RE`.
- Produces: `validate_controversy_blocks(repo_root)`, `_MACHINE_FIELDS`, and
  `block.merge_block(data, assessments)`, `block.block_entries(data)`,
  `block.controversy_mint(record_path, data, kind, repo_root)`.

**The block, as committed:**

```yaml
# tail of features/structural-typing.yaml
controversy:
  - key: summary
    fact_id: f-aaaaaaaaaaaa
    level: 2
    signals:
      - debate:d-01-typing-003:standing-dissent
      - verdict:partial:since
    assessed:
      date: '2026-09-17'
      model: deepseek-v4-pro-thinking
      prompt: controversy-assessor@v-1a2b3c4d
      run_id: 2026-09-17-controversy-features-structural-typing-01
      escalated_to: claude
```

`key` is the anchor's field-path suffix (§3.2: the anchor is `structural-typing#summary`), so it
survives a claim edit that changes the `fact_id`. There is **no free-prose field anywhere in this
block** — §6.4 is explicit that the `signals` list *is* the justification — and there is **no
level-0 entry**, because an absent entry already means level 0.

- [ ] **Step 1: Write the failing validator tests**

```python
# tools/validate/tests/test_controversy_block.py
"""The store gate's rules for a machine-written block: it may say a level and name machine
references, and it may say nothing else."""
import pytest

from langatlas_validate.schema import validate_record
from langatlas_validate.store import validate_controversy_blocks
from langatlas_validate.version import classify_change

GOOD = {"key": "summary", "fact_id": "f-aaaaaaaaaaaa", "level": 2,
        "signals": ["debate:d-01-typing-003:standing-dissent", "verdict:partial:since"],
        "assessed": {"date": "2026-09-17", "model": "deepseek-v4-pro-thinking",
                     "prompt": "controversy-assessor@v-1a2b3c4d", "run_id": "r-1",
                     "escalated_to": "claude"}}


def _feature(**overrides):
    data = {"id": "structural-typing", "slug": "structural-typing", "name": "Structural typing",
            "layer": 2, "summary": {"text": "t", "sources": [{"source": "s", "locator": "p. 1"}]},
            "provenance": {"claim_origin": "source-derived"}}
    data.update(overrides)
    return data


def test_a_well_formed_block_validates():
    assert validate_record(_feature(controversy=[GOOD]), "feature") == []


def test_a_free_prose_rationale_is_rejected_by_the_schema():
    """§6.4: the signals list *is* the justification. A rationale field would be an
    agent-written explanation nobody can check."""
    bad = {**GOOD, "rationale": "the sources plainly disagree"}
    assert validate_record(_feature(controversy=[bad]), "feature") != []


def test_level_4_is_rejected():
    assert validate_record(_feature(controversy=[{**GOOD, "level": 4}]), "feature") != []


def test_a_level_0_entry_is_refused_by_the_store_gate():
    """An absent block means level 0 (§6.4), so a stored 0 is a second way to say the same
    thing — and two encodings of "settled" is how a site ends up rendering one of them wrong."""
    errors = validate_controversy_blocks(
        [("features/structural-typing.yaml", "feature", _feature(controversy=[{**GOOD, "level": 0}]),
          ["f-aaaaaaaaaaaa"])])
    assert any("level 0" in e for e in errors)


def test_a_signal_outside_the_grammar_is_refused():
    bad = {**GOOD, "signals": ["the type theorist objected"]}
    errors = validate_controversy_blocks(
        [("features/structural-typing.yaml", "feature", _feature(controversy=[bad]),
          ["f-aaaaaaaaaaaa"])])
    assert any("not a machine reference" in e for e in errors)


def test_a_block_naming_a_fact_the_record_does_not_derive_is_refused():
    errors = validate_controversy_blocks(
        [("features/structural-typing.yaml", "feature", _feature(controversy=[GOOD]),
          ["f-999999999999"])])
    assert any("does not derive" in e for e in errors)


def test_a_controversy_only_edit_is_not_an_ontology_change():
    """The nightly batch must not bump `ontology/VERSION`. A machine annotation is not an
    ontology change; classifying it as `additive` would bump MINOR every night."""
    before = {"features/structural-typing.yaml": _feature()}
    after = {"features/structural-typing.yaml": _feature(controversy=[GOOD])}
    assert classify_change(before, after) == "none"


def test_a_real_edit_alongside_a_block_is_still_classified():
    before = {"features/structural-typing.yaml": _feature()}
    after = {"features/structural-typing.yaml": _feature(controversy=[GOOD], layer=3,
                                                         dimension="typing-discipline")}
    assert classify_change(before, after) == "restructuring"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv --directory tools/validate run pytest tests/test_controversy_block.py -v`
Expected: FAIL — `ImportError: cannot import name 'validate_controversy_blocks'`

- [ ] **Step 3: Add the `controversyBlock` `$def`**

In `ontology/schema/defs.schema.json`, add to `$defs`:

```json
    "controversyBlock": {
      "description": "D21/D25 (§6.4). Machine-written; absent means level 0. The `signals` list of machine references IS the justification — there is deliberately no prose field.",
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["key", "fact_id", "level", "signals", "assessed"],
        "properties": {
          "key": { "type": "string", "minLength": 1 },
          "fact_id": { "type": "string", "pattern": "^f-[0-9a-f]{12}$" },
          "level": { "enum": [1, 2, 3] },
          "signals": {
            "type": "array",
            "items": { "type": "string", "pattern": "^(debate|verdict|contradiction|assessment-spread):" }
          },
          "assessed": {
            "type": "object",
            "additionalProperties": false,
            "required": ["date", "model", "prompt", "run_id"],
            "properties": {
              "date": { "type": "string" },
              "model": { "type": "string" },
              "prompt": { "type": "string" },
              "run_id": { "type": "string" },
              "escalated_to": { "type": ["string", "null"], "enum": ["claude", null] }
            }
          }
        }
      }
    },
```

Note `"level": { "enum": [1, 2, 3] }` — the schema itself refuses a stored level 0, and the
store-gate check in step 5 gives the developer the readable message.

- [ ] **Step 4: Add `controversy` to the six record schemas**

In each of `concept`, `feature`, `edge`, `affects-quality-edge`, `rule` and `feature-instance`,
add as the **last** entry of `properties` (order matters — `normalize_record` orders record keys
by schema property order, so the block lands at the tail of every file):

```json
    "controversy": { "$ref": "defs.schema.json#/$defs/controversyBlock" }
```

- [ ] **Step 5: Add the store-gate check**

In `tools/validate/src/langatlas_validate/store.py`:

```python
# §6.4's closed signal grammar. A signal is a machine reference into a debate, a verdict, a
# contradiction record or an assessment spread — never a sentence.
_SIGNAL_RE = re.compile(
    r"^(debate:[a-z0-9-]+:[a-z-]+"
    r"|verdict:[a-z-]+:[a-z-]+"
    r"|contradiction:ctr-[0-9a-f]{12}:[a-z-]+"
    r"|assessment-spread:[a-z0-9_-]+)$")


def validate_controversy_blocks(records) -> list[str]:
    """D21/D25: what a machine-written controversy block may say.

    @param records: `(rel_path, kind, data, fact_ids)` tuples — `fact_ids` are the ids that
        record's own `derive_facts` row produced, so a block left behind by a claim edit is
        caught here rather than surfacing on the site as a level attached to nothing.
    @returns one message per violation."""
    errors = []
    for rel, _kind, data, fact_ids in records:
        seen = set()
        for entry in data.get("controversy") or []:
            where = f"{rel}[controversy:{entry.get('key')}]"
            if entry.get("level") == 0:
                errors.append(f"{where}: level 0 is written as an absent entry (§6.4), not"
                              f" as a stored 0")
            if entry.get("key") in seen:
                errors.append(f"{where}: duplicate key")
            seen.add(entry.get("key"))
            if entry.get("fact_id") not in set(fact_ids):
                errors.append(f"{where}: names fact {entry.get('fact_id')!r}, which this"
                              f" record does not derive — re-run the assessor")
            for signal in entry.get("signals") or []:
                if not _SIGNAL_RE.match(signal):
                    errors.append(f"{where}: {signal!r} is not a machine reference; §6.4's"
                                  f" signals list is the justification and admits no prose")
    return errors
```

and call it from `validate_store`, gathering the derived facts once:

```python
    from langatlas_validate.compile import derive_facts

    store_records = list(iter_store_records(repo_root))
    ...
    by_path: dict[str, list[str]] = {}
    for fact in derive_facts(store_records):
        by_path.setdefault(fact["record_path"], []).append(fact["fact_id"])
    errors.extend(validate_controversy_blocks(
        [(str(path), kind, data, by_path.get(str(path), []))
         for path, kind, _text, data in store_records]))
```

(Replace the existing `for path, kind, text, data in iter_store_records(repo_root):` loop header
with `for path, kind, text, data in store_records:` so the store is walked once.)

- [ ] **Step 6: Exempt machine fields from the version classifier**

In `tools/validate/src/langatlas_validate/version.py`:

```python
# Machine-written annotations. They are measurements about the corpus, not ontology content, so
# an edit that only touches one is not a version event at all — otherwise the nightly
# controversy batch would bump MINOR every time it found its first contested fact.
_MACHINE_FIELDS = {"controversy"}


def _without_machine_fields(record: dict) -> dict:
    return {k: v for k, v in record.items() if k not in _MACHINE_FIELDS}
```

and make `_diff_class` compare stripped records:

```python
def _diff_class(before: dict, after: dict) -> str:
    """The strongest class of change between two versions of one record."""
    before, after = _without_machine_fields(before), _without_machine_fields(after)
    if before == after:
        return "none"
    ...
```

- [ ] **Step 7: Run the validator tests**

Run: `uv --directory tools/validate run pytest tests/test_controversy_block.py tests/test_version.py tests/test_store.py -v`
Expected: PASS — including the two `classify_change` tests and the existing version suite.

- [ ] **Step 8: Write the failing block-writer tests**

```python
# tools/research/tests/test_controversy_block.py
"""The writer side: merging assessments into a record without disturbing anything else."""
import pytest
from ruamel.yaml import YAML

from langatlas_research.controversy.assessor import Assessment
from langatlas_research.controversy.block import block_entries, controversy_mint, merge_block

_yaml = YAML(typ="safe")

FEATURE = {"id": "structural-typing", "slug": "structural-typing",
           "name": "Structural typing", "layer": 2,
           "summary": {"text": "t", "sources": [{"source": "pierce-tapl-2002",
                                                 "locator": "p. 251"}]},
           "provenance": {"claim_origin": "source-derived"}}


def _assessment(level, signals=(), fact_id="f-aaaaaaaaaaaa"):
    return Assessment(fact_id=fact_id, level=level, signals=tuple(signals),
                      model="deepseek-v4-pro-thinking", prompt="controversy-assessor@v-1a2b3c4d",
                      run_id="r-1")


def test_a_level_0_assessment_writes_no_entry():
    merged = merge_block(FEATURE, {"summary": _assessment(0)}, date="2026-09-17")
    assert "controversy" not in merged


def test_a_level_0_assessment_removes_a_stale_entry():
    """A fact that stopped being contested must lose its block, or the site keeps rendering a
    dispute that resolved."""
    existing = {**FEATURE, "controversy": [{"key": "summary", "fact_id": "f-aaaaaaaaaaaa",
                                            "level": 2, "signals": [], "assessed": {}}]}
    merged = merge_block(existing, {"summary": _assessment(0)}, date="2026-09-17")
    assert "controversy" not in merged


def test_an_entry_carries_the_signals_and_the_assessed_stamp():
    merged = merge_block(FEATURE, {"summary": _assessment(2, ["verdict:partial:since"])},
                         date="2026-09-17")
    entry, = merged["controversy"]
    assert entry["key"] == "summary"
    assert entry["level"] == 2
    assert entry["signals"] == ["verdict:partial:since"]
    assert entry["assessed"]["date"] == "2026-09-17"
    assert entry["assessed"]["prompt"] == "controversy-assessor@v-1a2b3c4d"


def test_entries_for_other_facts_are_left_alone():
    """A record's facts are assessed together, but a budget stop can still leave one
    unassessed — and an untouched fact must keep the level it already had."""
    existing = {**FEATURE, "controversy": [
        {"key": "characteristics[c-width]", "fact_id": "f-bbbbbbbbbbbb", "level": 3,
         "signals": ["verdict:contradicted:base"], "assessed": {"date": "2026-09-01",
                                                                "model": "m", "prompt": "p",
                                                                "run_id": "r"}}]}
    merged = merge_block(existing, {"summary": _assessment(1, ["debate:d-01-typing-003:resolved"])},
                         date="2026-09-17")
    assert [e["key"] for e in merged["controversy"]] == ["characteristics[c-width]", "summary"]


def test_the_mint_renders_normalized_yaml_with_the_block_at_the_tail(tmp_path):
    minted = controversy_mint("features/structural-typing.yaml",
                              merge_block(FEATURE, {"summary": _assessment(2, [])},
                                          date="2026-09-17"),
                              kind="feature", base_text="")
    assert minted.path == "features/structural-typing.yaml"
    assert minted.text.rstrip().endswith("run_id: r-1")
    assert list(_yaml.load(minted.text)) [-1] == "controversy"
```

- [ ] **Step 9: Run them to verify they fail**

Run: `uv --directory tools/research run pytest tests/test_controversy_block.py -m '' -v`
Expected: FAIL — `ModuleNotFoundError: langatlas_research.controversy.block`

- [ ] **Step 10: Write `block.py`**

```python
# tools/research/src/langatlas_research/controversy/block.py
"""Reading, merging and rendering the canonical `controversy:` block.

Two asymmetries are deliberate:

- **Level 0 removes, it does not write.** §6.4 fixes an absent entry as level 0, so a fact that
  stopped being contested has to lose its entry — otherwise the site renders a dispute that
  resolved months ago.
- **Unassessed facts are untouched.** A budget stop mid-record is normal (D43), and a merge that
  dropped the entries it did not re-derive would silently downgrade every fact the run never
  reached.
"""
from pathlib import Path

from langatlas_research.mint import MintedRecord, content_digest, dump_yaml
from langatlas_validate.normalize import normalize_record


def block_entries(data: dict) -> dict:
    """@returns key -> entry for the record's existing block, empty when there is none."""
    return {entry["key"]: entry for entry in data.get("controversy") or []}


def merge_block(data: dict, assessments: dict, *, date: str) -> dict:
    """Fold this run's assessments into the record's block.

    @param assessments: field-path key (the anchor suffix, e.g. `summary`,
        `characteristics[c-exhaustive]`) -> `Assessment`.
    @param date: the assessment date stamped on every entry this run writes.
    @returns a new record dict; the input is never mutated, because the caller still needs the
        pre-merge text to decide whether anything actually changed."""
    entries = block_entries(data)
    for key, assessment in assessments.items():
        if assessment.level == 0:
            entries.pop(key, None)
            continue
        entries[key] = {
            "key": key,
            "fact_id": assessment.fact_id,
            "level": int(assessment.level),
            "signals": list(assessment.signals),
            "assessed": {"date": date, "model": assessment.model,
                         "prompt": assessment.prompt, "run_id": assessment.run_id,
                         "escalated_to": assessment.escalated_to},
        }
    merged = {k: v for k, v in data.items() if k != "controversy"}
    if entries:
        merged["controversy"] = [entries[key] for key in sorted(entries)]
    return merged


def controversy_mint(record_path: str, data: dict, *, kind: str,
                     base_text: str) -> MintedRecord:
    """The record as a shared-file `MintedRecord`, for `land_drafts`.

    `base_digest` is the digest of the text this merge was computed from, so a record another
    process rewrote between read and land is re-rendered rather than clobbered — the same
    read-modify-write protection `taxonomy.py` and the contradictions ledger use."""
    text = normalize_record(dump_yaml(data), kind)
    return MintedRecord(path=record_path, text=text, kind=kind, node_ids=(),
                        base_digest=content_digest(base_text))


def unchanged(minted: MintedRecord, base_text: str) -> bool:
    """True when the merge produced byte-identical text — the common nightly case, and the one
    that must never produce an empty commit."""
    return minted.text == base_text
```

- [ ] **Step 11: Run the block tests**

Run: `uv --directory tools/research run pytest tests/test_controversy_block.py -m '' -v`
Expected: PASS (5 tests) — note this needs `Assessment` from Task 5; if executing tasks strictly
in order, land Task 5's `assessor.py` dataclass first and re-run. (Task 5 is written to define
`Assessment` before its own first test.)

- [ ] **Step 12: Run the full store gate against the real repo**

Run: `uv --directory tools/validate run langatlas-validate ci`
Expected: exit 0 — no record carries a block yet, so the new check is a no-op on today's store.

- [ ] **Step 13: Commit**

```bash
git add ontology/schema tools/validate/src/langatlas_validate/store.py \
        tools/validate/src/langatlas_validate/version.py \
        tools/validate/tests/test_controversy_block.py \
        tools/research/src/langatlas_research/controversy/block.py \
        tools/research/tests/test_controversy_block.py \
        docs/superpowers/plans/2026-09-16-stage-3d-controversy-assessor.md
git commit -m "feat(#stage-3d): admit a machine-written controversy block that is not a version event"
```

---

## Task 5: The rubric prompt and the university-API assessor

**Files:**
- Create: `prompts/controversy-assessor/v-<hash>.md` + `prompts/controversy-assessor/CHANGELOG.md`
  (both written by `mint_prompt_version`, never by hand)
- Create: `tools/research/src/langatlas_research/controversy/assessor.py`
- Test: `tools/research/tests/test_controversy_assessor.py`

**Interfaces:**
- Consumes: `RunContext.complete` (or `FakeCtx`), `langatlas_pipeline.prompts.load_prompt` /
  `mint_prompt_version`, Task 1's `ControversyInputs` / `derivable_signals`,
  `langatlas_ingest.goldens.items.CONTROVERSY_LEVELS`.
- Produces: `Assessment`, `AssessmentOut` (pydantic), `ASSESSOR_PROMPT_ID`, `assess_inputs`,
  `needs_escalation`. (The golden entry points `GoldenAssessor` / `golden_assessor` are added to
  this same module in Task 9, once escalation exists for them to call.)

**Why there is no D31 delimiting here.** Every other Stage 3 role feeds a model document text and
must route it through `ctx.tool_result`. This one does not: §6.4's structured inputs are
*projections* — ids, enum values, counts, tier letters — assembled by Task 2 out of ledgers and
record metadata. No source text, no agent prose, no fetched page ever enters the packet, so there
is nothing to delimit. Task 2's projections are what make that true, which is why
`contradiction_projection` drops `detail` rather than truncating it.

- [ ] **Step 1: Mint the rubric prompt**

Run from the repo root:

```bash
uv --directory tools/pipeline run python - <<'PY'
from langatlas_pipeline.prompts import mint_prompt_version

TEXT = """---
prompt_id: controversy-assessor
variables: [inputs_json, signal_vocabulary]
---
# system
You assign a controversy level to one fact in a knowledge base about programming languages.

You never see the fact's text, its sources or anyone's prose. You see only structured
measurements the pipeline made about it. Judge the disagreement those measurements describe;
do not reason about whether the underlying claim is true.

The four levels are ordinal and exhaustive:

- 0 `settled` — no disagreement signal anywhere.
- 1 `noted-variance` — weak, resolved signals only: a debate that converged after revision, a
  clearly-outweighed minority assessment, or a `partial` verdict on a field that is not
  load-bearing (`characteristic`, `syntax`, `polarity`, `quality-assessment`).
- 2 `contested` — live disagreement inside the pipeline: a debate resolved but with standing
  dissent; a credible but unequal spread of quality assessments; a `partial` verdict on a
  load-bearing field (`base`, `since`).
- 3 `disputed` — non-convergence: an escalated or unresolved debate, a standing (open)
  contradiction record, or conflicting verdicts across admissible sources — including genuine
  disagreement between independent tier-A/B sources on the same field.

How to read the inputs:

- `verdicts` — one row per (citation, field). `supported` is agreement. `partial` is a
  narrowing, weak on a non-load-bearing field and serious on `base` or `since`. `contradicted`
  on a load-bearing field from a tier-A/B source is the strongest single signal there is.
  `source-unavailable` and `locator-not-found` are missing measurements, not disagreement.
- `contradiction_records` — `status: open` means a live dispute; `resolved` and `dissolved` are
  closed and cap the fact at level 2 on their own.
- `debates` — `outcome: escalated` is non-convergence. `standing_dissent: true` means the
  disagreement outlived the resolution. A high `rounds` count means the question was hard, not
  that it is unresolved.
- `source_strength` — how much admissible backing the fact has, and how much of it is
  independent. Weak backing on its own is not controversy: an uncontested single tier-A
  citation is settled, not contested.
- `assessment_spread` — attributed quality assessments that disagree. Values that agree are not
  a spread.

Return JSON with exactly three fields:

- `level`: 0, 1, 2 or 3.
- `alternative`: the adjacent level you seriously considered and rejected, or null when the
  answer was not close. Never a level more than one away from `level`.
- `signals`: the machine references that justify your level, copied verbatim from this list and
  from nowhere else:
{{signal_vocabulary}}

  Cite only signals that actually drove your level. Level 0 cites none. Never invent a
  reference, never write a sentence, and never explain — the signals list is the whole
  justification.

# user
Assess this fact's structured inputs:

{{inputs_json}}
"""

ref = mint_prompt_version("controversy-assessor", TEXT,
                          note="D21/D25 controversy rubric: four ordinal levels, "
                               "structured inputs only, signals-as-justification (Stage 3D)")
print(ref.ref())
PY
```

Expected: prints `controversy-assessor@v-<8 hex>`. Record that version — it is what
`test_controversy_assessor.py` and the block's `assessed.prompt` will show.

- [ ] **Step 2: Write the failing tests**

```python
# tools/research/tests/test_controversy_assessor.py
"""What must hold whatever the model says: the level is in range, the signals are real, and
escalation is computed rather than volunteered."""
import pytest

from langatlas_research.controversy.assessor import (
    Assessment, AssessmentOut, assess_inputs, needs_escalation,
)
from langatlas_research.controversy.inputs import ControversyInputs
from langatlas_research.errors import AssessorOutputInvalid

INPUTS = ControversyInputs.from_mapping({
    "debates": [{"id": "d-01-typing-003", "outcome": "escalated", "standing_dissent": True,
                 "rounds": 4}],
    "verdicts": [{"fact": "f-a", "citation": 1, "verdict": "contradicted", "field": "base",
                  "tier": "A"}],
    "source_strength": {"tier_a": 2, "tier_b": 0, "independent_corroborations": 1},
})


class _Completion:
    def __init__(self, parsed, model="deepseek-v4-pro-thinking"):
        self.parsed, self.resolved_model = parsed, model


def _reply(fake_ctx, **out):
    fake_ctx.completions.append(lambda alias, messages, schema: _Completion(AssessmentOut(**out)))


def test_a_clean_assessment_comes_back_with_its_signals(fake_ctx):
    _reply(fake_ctx, level=3, alternative=None,
           signals=["debate:d-01-typing-003:standing-dissent", "verdict:contradicted:base"])
    assessment = assess_inputs(fake_ctx, "f-a", INPUTS, alias="thinker")
    assert assessment.level == 3
    assert assessment.signals == ("debate:d-01-typing-003:standing-dissent",
                                  "verdict:contradicted:base")
    assert assessment.model == "deepseek-v4-pro-thinking"
    assert assessment.prompt.startswith("controversy-assessor@v-")


def test_the_thinker_alias_is_the_one_asked_for(fake_ctx):
    _reply(fake_ctx, level=0, alternative=None, signals=[])
    assess_inputs(fake_ctx, "f-a", INPUTS, alias="thinker")
    assert fake_ctx.complete_calls[0]["alias"] == "thinker"


def test_an_invented_signal_is_dropped(fake_ctx):
    """§6.4 makes the signals list the justification, so a signal the inputs cannot produce is
    a fabricated justification — not a weak one."""
    _reply(fake_ctx, level=2, alternative=1,
           signals=["verdict:contradicted:base", "debate:d-99-made-up-001:escalated"])
    assessment = assess_inputs(fake_ctx, "f-a", INPUTS, alias="thinker")
    assert assessment.signals == ("verdict:contradicted:base",)


def test_a_non_adjacent_alternative_is_dropped(fake_ctx):
    _reply(fake_ctx, level=3, alternative=0, signals=[])
    assert assess_inputs(fake_ctx, "f-a", INPUTS, alias="thinker").alternative is None


def test_an_out_of_range_level_is_refused(fake_ctx):
    fake_ctx.completions.append(
        lambda alias, messages, schema: _Completion(
            type("O", (), {"level": 4, "alternative": None, "signals": []})()))
    with pytest.raises(AssessorOutputInvalid, match="4"):
        assess_inputs(fake_ctx, "f-a", INPUTS, alias="thinker")


def test_level_3_always_escalates():
    assert needs_escalation(Assessment(fact_id="f-a", level=3, signals=(), alternative=None))


def test_an_adjacent_alternative_escalates():
    assert needs_escalation(Assessment(fact_id="f-a", level=1, signals=(), alternative=2))


def test_a_confident_low_level_does_not_escalate():
    assert not needs_escalation(Assessment(fact_id="f-a", level=1, signals=(), alternative=None))


def test_the_prompt_lists_only_derivable_signals(fake_ctx):
    """The vocabulary handed to the model is the same set the filter enforces — a model asked
    to choose from a list it is then punished for using would just look unreliable."""
    _reply(fake_ctx, level=0, alternative=None, signals=[])
    assess_inputs(fake_ctx, "f-a", INPUTS, alias="thinker")
    rendered = "\n".join(m["content"] for m in fake_ctx.complete_calls[0]["messages"])
    assert "debate:d-01-typing-003:standing-dissent" in rendered
    assert "d-99" not in rendered
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv --directory tools/research run pytest tests/test_controversy_assessor.py -m '' -v`
Expected: FAIL — `ModuleNotFoundError: langatlas_research.controversy.assessor`

- [ ] **Step 4: Write `assessor.py`**

```python
# tools/research/src/langatlas_research/controversy/assessor.py
"""§6.4's assessor: one university-API `thinker` call over a fixed rubric.

Three things the model is not allowed to decide:

1. **Whether its justification is real.** Signals are intersected with `derivable_signals`, so a
   reference the inputs cannot produce never reaches the record. §6.4 has no prose rationale to
   fall back on, which makes a fabricated signal a fabricated justification.
2. **Whether it gets reviewed.** It types the adjacent level it nearly chose; `needs_escalation`
   reads that plus the level. A model that could type "escalate" could also decline to.
3. **What model answered.** `resolved_model` comes off the completion, and `RunContext` pins the
   alias for the run (D26) — a level whose provenance said `thinker` while something else
   answered would be unauditable."""
import json
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from langatlas_ingest.goldens.items import CONTROVERSY_LEVELS
from langatlas_pipeline.prompts import PromptRef, load_prompt

from langatlas_research.controversy.inputs import ControversyInputs, derivable_signals
from langatlas_research.errors import AssessorOutputInvalid

ASSESSOR_PROMPT_ID = "controversy-assessor"


class AssessmentOut(BaseModel):
    level: int = Field(ge=0, le=3)
    alternative: int | None = None
    signals: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class Assessment:
    """One fact's level, with everything needed to stamp it into a record and audit it."""

    fact_id: str
    level: int
    signals: tuple[str, ...] = ()
    alternative: int | None = None
    model: str = ""
    prompt: str = ""
    run_id: str = ""
    escalated_to: str | None = None


def _vocabulary(inputs: ControversyInputs) -> str:
    signals = sorted(derivable_signals(inputs))
    return "\n".join(f"  - {signal}" for signal in signals) or "  (none)"


def assess_inputs(ctx, fact_id: str, inputs: ControversyInputs, *, alias: str,
                  prompt: PromptRef | None = None) -> Assessment:
    """Assess one fact.

    @param ctx: a `RunContext` (or a test double exposing `complete`).
    @param alias: the completion alias, from `config/research.yaml` — `thinker` in production.
    @raises AssessorOutputInvalid: a level outside 0-3.
    @raises BudgetExceeded / StructuredOutputError: unchanged from `ctx.complete`; the
        orchestrator turns the first into a clean pause."""
    prompt = prompt or load_prompt(ASSESSOR_PROMPT_ID)
    messages = prompt.render(
        inputs_json=json.dumps(inputs.as_dict(), indent=2, sort_keys=True),
        signal_vocabulary=_vocabulary(inputs))
    completion = ctx.complete(alias, messages, prompt=prompt, schema=AssessmentOut)
    out = completion.parsed
    if out.level not in CONTROVERSY_LEVELS:
        raise AssessorOutputInvalid(
            f"{fact_id}: level {out.level!r} is not one of {list(CONTROVERSY_LEVELS)}")

    allowed = derivable_signals(inputs)
    signals = tuple(s for s in dict.fromkeys(out.signals) if s in allowed)
    alternative = out.alternative
    if alternative is not None and (alternative not in CONTROVERSY_LEVELS
                                    or abs(alternative - out.level) != 1):
        # "Adjacent-level ambiguity" is what §6.4 routes to Claude. A two-level gap is not
        # ambiguity, it is a model contradicting itself, and treating it as a review request
        # would spend Claude credits on noise.
        alternative = None
    return Assessment(fact_id=fact_id, level=out.level, signals=signals,
                      alternative=alternative, model=completion.resolved_model,
                      prompt=prompt.ref(), run_id=getattr(ctx, "run_id", ""))


def needs_escalation(assessment: Assessment) -> bool:
    """§6.4: Claude reviews adjacent-level ambiguity and **every** level-3 assignment.

    Level 3 is unconditional because it is the level the site renders as an AI-judged dispute
    and the one a false positive is most expensive on."""
    return assessment.level == 3 or assessment.alternative is not None
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv --directory tools/research run pytest tests/test_controversy_assessor.py -m '' -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Commit**

```bash
git add prompts/controversy-assessor tools/research/src/langatlas_research/controversy/assessor.py \
        tools/research/tests/test_controversy_assessor.py \
        docs/superpowers/plans/2026-09-16-stage-3d-controversy-assessor.md
git commit -m "feat(#stage-3d): score a fact's structured inputs against the D21 rubric"
```

---

## Task 6: Claude escalation and the opportunistic golden lane

**Files:**
- Create: `prompts/controversy-escalation/v-<hash>.md` + `CHANGELOG.md` (via `mint_prompt_version`)
- Create: `tools/research/src/langatlas_research/controversy/escalate.py`
- Create: `tests/golden/controversy/candidates/README.md`
- Test: `tools/research/tests/test_controversy_escalate.py`

**Interfaces:**
- Consumes: 3B's `run_structured` / `role_budget`, `ClaudeRoleConfig`, Task 5's `Assessment` /
  `needs_escalation`, Task 1's `derivable_signals`.
- Produces: `ESCALATION_PROMPT_ID`, `EscalationOut`, `escalate`, `capture_candidate`,
  `candidates_path`.

- [ ] **Step 1: Mint the escalation prompt**

```bash
uv --directory tools/pipeline run python - <<'PY'
from langatlas_pipeline.prompts import mint_prompt_version

TEXT = """---
prompt_id: controversy-escalation
variables: [inputs_json, signal_vocabulary, proposed_level, alternative_level, proposed_signals]
---
# system
You are the review step for a controversy level that a first-pass assessor was not confident
about, or that it set to 3 — the level that renders publicly as an AI-judged dispute.

You see the same structured measurements the first pass saw, and nothing else: no claim text,
no sources, no prose. Judge the disagreement the measurements describe.

The four levels are ordinal:

- 0 `settled` — no disagreement signal anywhere.
- 1 `noted-variance` — weak, resolved signals only: a debate that converged after revision, a
  clearly-outweighed minority assessment, a `partial` verdict on a non-load-bearing field.
- 2 `contested` — live disagreement: standing dissent after a resolved debate, a credible but
  unequal assessment spread, a `partial` on `base` or `since`.
- 3 `disputed` — non-convergence: an escalated debate, an open contradiction record, or
  conflicting verdicts across admissible sources.

Your job is to choose between the proposed level and the alternative, or to set a different
level if both are wrong. Level 3 is the one to be most careful about: it should mean the
literature or the pipeline genuinely failed to converge, not that the evidence is thin.

Return JSON with exactly two fields:

- `level`: your final level, 0-3.
- `signals`: the machine references justifying it, copied verbatim from:
{{signal_vocabulary}}

  No prose, no explanation, no invented references.

# user
The first pass proposed level {{proposed_level}} with signals {{proposed_signals}}, and
considered level {{alternative_level}}.

Structured inputs:

{{inputs_json}}
"""

ref = mint_prompt_version("controversy-escalation", TEXT,
                          note="Claude review of adjacent-level ambiguity and every level-3 "
                               "assignment (D21/D25, Stage 3D)")
print(ref.ref())
PY
```

- [ ] **Step 2: Write the failing tests**

```python
# tools/research/tests/test_controversy_escalate.py
"""Escalation has to do two things: let Claude overrule the thinker, and leave a hand-labelable
case behind. The second is what grows 2B's ~15-20 bootstrap cases toward §6.4's ~50."""
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_pipeline.providers.claude_runs import AgentRunResult
from langatlas_research.config import ClaudeRoleConfig
from langatlas_research.controversy.assessor import Assessment
from langatlas_research.controversy.escalate import candidates_path, capture_candidate, escalate
from langatlas_research.controversy.inputs import ControversyInputs

_yaml = YAML(typ="safe")

ROLE = ClaudeRoleConfig(model=None, max_turns=20, max_claude_messages=40, max_packet_terms=0,
                        max_candidates=1)
INPUTS = ControversyInputs.from_mapping({
    "debates": [{"id": "d-01-typing-003", "outcome": "escalated", "standing_dissent": True,
                 "rounds": 4}],
    "verdicts": [{"fact": "f-a", "citation": 1, "verdict": "contradicted", "field": "base",
                  "tier": "A"}]})
PROPOSED = Assessment(fact_id="f-a", level=3, signals=("verdict:contradicted:base",),
                      alternative=2, model="deepseek-v4-pro-thinking",
                      prompt="controversy-assessor@v-1a2b3c4d", run_id="r-1")


def _claude(fake_ctx, level, signals):
    fake_ctx.claude_results.append(AgentRunResult(
        session_id="s", result_text="", structured_output={"level": level, "signals": signals},
        num_turns=1, is_error=False, tokens_in=1, tokens_out=1))


def test_claude_overrules_the_thinker_and_the_result_records_who_decided(fake_ctx):
    _claude(fake_ctx, 2, ["verdict:contradicted:base"])
    final = escalate(fake_ctx, PROPOSED, INPUTS, role_config=ROLE)
    assert final.level == 2
    assert final.escalated_to == "claude"
    assert final.alternative is None            # the ambiguity was resolved, not carried forward


def test_claudes_invented_signals_are_dropped_too(fake_ctx):
    _claude(fake_ctx, 3, ["verdict:contradicted:base", "contradiction:ctr-000000000000:open"])
    final = escalate(fake_ctx, PROPOSED, INPUTS, role_config=ROLE)
    assert final.signals == ("verdict:contradicted:base",)


def test_a_captured_candidate_is_uncurated_and_carries_both_levels(tmp_path):
    path = capture_candidate(
        PROPOSED, Assessment(fact_id="f-a", level=2, signals=("verdict:contradicted:base",),
                             escalated_to="claude"),
        INPUTS, repo_root=tmp_path, today="2026-09-17")
    data = _yaml.load(path.read_text())
    case, = data["cases"]
    assert case["curated"] is False
    assert case["expected_level"] == 2              # Claude's answer, pending a human label
    assert case["first_pass_level"] == 3
    assert set(case["inputs"]) <= {"debates", "contradiction_records", "verdicts",
                                   "source_strength", "assessment_spread"}


def test_candidates_land_outside_the_globbed_golden_directory(tmp_path):
    path = candidates_path(repo_root=tmp_path, today="2026-09-17")
    assert path.parent.name == "candidates"
    assert path.parent.parent.name == "controversy"


def test_capturing_twice_in_a_month_appends_rather_than_overwrites(tmp_path):
    final = Assessment(fact_id="f-b", level=2, signals=(), escalated_to="claude")
    capture_candidate(PROPOSED, final, INPUTS, repo_root=tmp_path, today="2026-09-17")
    path = capture_candidate(PROPOSED, final, INPUTS, repo_root=tmp_path, today="2026-09-28")
    assert len(_yaml.load(path.read_text())["cases"]) == 2
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv --directory tools/research run pytest tests/test_controversy_escalate.py -m '' -v`
Expected: FAIL — `ModuleNotFoundError: langatlas_research.controversy.escalate`

- [ ] **Step 4: Write `escalate.py`**

```python
# tools/research/src/langatlas_research/controversy/escalate.py
"""Claude's review of a level the thinker was unsure about, or set to 3.

Two jobs, and the second is the one that compounds: §6.4's controversy golden set has a
bootstrap lane of ~15-20 synthetic cases and an **opportunistic lane** that "the Claude-escalation
reviews produce". Every escalation here is therefore written out as an uncurated candidate the
developer can hand-label, which is how the set walks toward its ~50-case target without anybody
sitting down to invent cases.

Candidates land in `tests/golden/controversy/candidates/`, not in the golden directory itself:
`load_controversy_cases` globs `*.yaml` non-recursively and raises on `curated: false`, so a
subdirectory is invisible to it — the same arrangement `tests/golden/verifier/held-out/` uses."""
import io
from dataclasses import replace
from pathlib import Path

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from langatlas_research.controversy.assessor import Assessment
from langatlas_research.controversy.inputs import ControversyInputs, derivable_signals
from langatlas_research.survey.claude import role_budget, run_structured

ESCALATION_PROMPT_ID = "controversy-escalation"

_yaml = YAML(typ="safe")


class EscalationOut(BaseModel):
    level: int = Field(ge=0, le=3)
    signals: list[str] = Field(default_factory=list)


def escalate(ctx, proposed: Assessment, inputs: ControversyInputs, *, role_config,
             prompt=None) -> Assessment:
    """Run the Claude review and return the final assessment.

    @param ctx: a `RunContext` opened for the escalation (D18 — its own context, so the review
        is greppable separately from the volume pass).
    @returns a new `Assessment` carrying Claude's level, filtered signals, and
        `escalated_to="claude"`. `alternative` is cleared: the ambiguity has been adjudicated,
        and carrying it forward would re-escalate the same fact every night.
    @raises SurveyOutputInvalid: no usable structured output, unchanged from `run_structured`."""
    from langatlas_pipeline.prompts import load_prompt

    prompt = prompt or load_prompt(ESCALATION_PROMPT_ID)
    import json

    parsed, _result = run_structured(
        ctx, prompt,
        {"inputs_json": json.dumps(inputs.as_dict(), indent=2, sort_keys=True),
         "signal_vocabulary": "\n".join(f"  - {s}" for s in sorted(derivable_signals(inputs)))
                              or "  (none)",
         "proposed_level": str(proposed.level),
         "alternative_level": "none" if proposed.alternative is None else str(proposed.alternative),
         "proposed_signals": ", ".join(proposed.signals) or "none"},
        output_model=EscalationOut, role_config=role_config)

    allowed = derivable_signals(inputs)
    signals = tuple(s for s in dict.fromkeys(parsed.signals) if s in allowed)
    return replace(proposed, level=parsed.level, signals=signals, alternative=None,
                   escalated_to="claude")


def candidates_path(*, repo_root: Path, today: str) -> Path:
    """One file per month, so the developer reviews a manageable batch rather than a file that
    grows forever."""
    return (Path(repo_root) / "tests" / "golden" / "controversy" / "candidates"
            / f"{today[:7]}.yaml")


def capture_candidate(proposed: Assessment, final: Assessment, inputs: ControversyInputs, *,
                      repo_root: Path, today: str) -> Path:
    """Append this review to the month's candidate file.

    `expected_level` is seeded with Claude's answer and `curated: false` — a seed, not a label.
    §6.4's golden-set methodology is explicit that cases are developer-curated; promoting one is
    the developer editing `expected_level` (or agreeing with it) and moving the case up into
    `tests/golden/controversy/`."""
    path = candidates_path(repo_root=repo_root, today=today)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = (_yaml.load(path.read_text()) or {}) if path.exists() else {}
    cases = existing.get("cases") or []
    cases.append({
        "id": f"c-escalated-{final.fact_id}-{today}",
        "expected_level": int(final.level),
        "first_pass_level": int(proposed.level),
        "first_pass_alternative": proposed.alternative,
        "inputs": inputs.as_dict(),
        "expected_signals": list(final.signals),
        "authored_by": "llm-curated",
        "curated": False,
        "notes": f"escalation review on {today}; first pass {proposed.model} said"
                 f" {proposed.level}, Claude said {final.level}",
    })
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    buf = io.StringIO()
    yaml.dump({"version": 1, "cases": cases}, buf)
    path.write_text(buf.getvalue())
    return path
```

- [ ] **Step 5: Write the candidates README**

`tests/golden/controversy/candidates/README.md`:

```markdown
<!-- tests/golden/controversy/candidates/README.md -->
# Controversy golden candidates (uncurated)

§6.4's **opportunistic lane**. Every Claude escalation review the assessor runs is appended here
as a case with `curated: false` and `expected_level` seeded from Claude's answer.

Nothing in this directory is scored. `load_controversy_cases` globs
`tests/golden/controversy/*.yaml` non-recursively, so a subdirectory is invisible to it — and an
uncurated case it *could* see would be rejected outright.

To promote a case: read its `inputs`, decide the level yourself, set `expected_level` to your
label, set `curated: true`, give it a stable id (`c-escalated-NNNN`), and move it into
`tests/golden/controversy/cases-escalated.yaml`. The bootstrap lane is ~15-20 cases; the target
is ~50.
```

- [ ] **Step 6: Run the tests**

Run: `uv --directory tools/research run pytest tests/test_controversy_escalate.py -m '' -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Confirm the candidates directory is invisible to the loader**

Run: `uv --directory tools/ingest run langatlas-sources golden-validate`
Expected: exit 0 — the README and any candidate file are not picked up.

- [ ] **Step 8: Commit**

```bash
git add prompts/controversy-escalation tools/research/src/langatlas_research/controversy/escalate.py \
        tests/golden/controversy/candidates tools/research/tests/test_controversy_escalate.py \
        docs/superpowers/plans/2026-09-16-stage-3d-controversy-assessor.md
git commit -m "feat(#stage-3d): send ambiguous and level-3 assessments to Claude and keep the review"
```

---

## Task 7: Per-record orchestration and the `controversy` CLI

**Files:**
- Create: `tools/research/src/langatlas_research/controversy/run.py`
- Modify: `tools/research/src/langatlas_research/cli.py`
- Test: `tools/research/tests/test_controversy_run.py`

**Interfaces:**
- Consumes: everything from Tasks 1-6, plus `langatlas_validate.store.iter_store_records`,
  `langatlas_research.land.land_drafts`.
- Produces: `RecordOutcome`, `assess_record`, `record_key_for`, `store_record_paths`,
  `anchor_key`.

**The anchor key.** `merge_block` keys entries by field path. `derive_facts` returns a claim, not
an anchor, so `anchor_key(fact)` recovers the suffix from the claim kind and its arguments:
`node-definition(...)` → `summary`; `characteristic(<instance>, c-exhaustive, …)` →
`characteristics[c-exhaustive]`; `syntax-valid(<instance>.sx.basic-match, …)` →
`syntax[basic-match]`; `quality-assessment(<edge>, a-1)` → `assessments[a-1]`;
`instance-exists`/`edge-exists`/`rule-exists` → `exists`; `edge-polarity` → `polarity`. These are
§3.2's anchor suffixes exactly, so the block's `key` is the same string the site's `data-fact-id`
pair will carry.

- [ ] **Step 1: Write the failing tests**

```python
# tools/research/tests/test_controversy_run.py
"""The per-record loop: what gets a model call, what gets a commit, and what neither."""
import pytest

from langatlas_research.controversy.assessor import Assessment
from langatlas_research.controversy.inputs import ControversyInputs, inputs_digest
from langatlas_research.controversy.ledger import AssessmentLedger
from langatlas_research.controversy.run import Deps, anchor_key, assess_record

FEATURE_YAML = """\
id: structural-typing
slug: structural-typing
name: Structural typing
layer: 2
summary:
  text: A type system in which compatibility is determined by structure.
  sources:
    - source: pierce-tapl-2002
      locator: 'p. 251'
provenance:
  claim_origin: source-derived
"""


@pytest.fixture
def feature_repo(tmp_path):
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "structural-typing.yaml").write_text(FEATURE_YAML)
    return tmp_path


def _deps(monkeypatch, level=2, signals=("verdict:partial:base",), calls=None):
    """An assessor stub standing in for the university API; assembly is real."""
    def _assess(ctx, fact_id, inputs, *, alias, prompt=None):
        if calls is not None:
            calls.append(fact_id)
        return Assessment(fact_id=fact_id, level=level, signals=tuple(signals),
                          model="deepseek-v4-pro-thinking",
                          prompt="controversy-assessor@v-1a2b3c4d", run_id="r-1")
    return _assess


def test_anchor_key_recovers_the_field_path():
    assert anchor_key("node-definition(structural-typing, sha256-16=ab)") == "summary"
    assert anchor_key("characteristic(fi.rust.pattern-matching, c-exhaustive, sha256-16=ab)") \
        == "characteristics[c-exhaustive]"
    assert anchor_key("instance-exists(fi.rust.pattern-matching, present)") == "exists"


def test_a_contested_fact_gets_a_block_and_a_landed_commit(feature_repo, fake_ctx, monkeypatch):
    landed = []
    outcome = assess_record(
        fake_ctx, "features/structural-typing.yaml", repo_root=feature_repo,
        deps=Deps(assess=_deps(monkeypatch), escalate=None,
                  ledger=AssessmentLedger(feature_repo / "l.sqlite"),
                  land=lambda minted: landed.append(minted) or True,
                  alias="thinker", today="2026-09-17",
                  source_facts={}, contradictions=[], debates={},
                  verdict_ledger=type("L", (), {"latest_for": lambda self, f: []})()))
    assert outcome.assessed == 1
    assert outcome.changed is True
    assert "controversy:" in landed[0].text


def test_a_settled_fact_writes_nothing_and_lands_nothing(feature_repo, fake_ctx, monkeypatch):
    landed = []
    outcome = assess_record(
        fake_ctx, "features/structural-typing.yaml", repo_root=feature_repo,
        deps=Deps(assess=_deps(monkeypatch, level=0, signals=()), escalate=None,
                  ledger=AssessmentLedger(feature_repo / "l.sqlite"),
                  land=lambda minted: landed.append(minted) or True,
                  alias="thinker", today="2026-09-17", source_facts={}, contradictions=[],
                  debates={}, verdict_ledger=type("L", (), {"latest_for": lambda self, f: []})()))
    assert outcome.assessed == 1
    assert outcome.changed is False
    assert landed == []


def test_an_unchanged_digest_skips_the_model_entirely(feature_repo, fake_ctx, monkeypatch):
    """§6.4's free re-run. This is the property the nightly cadence depends on — without it a
    nightly batch re-pays for the whole store every night."""
    calls = []
    ledger = AssessmentLedger(feature_repo / "l.sqlite")
    deps = Deps(assess=_deps(monkeypatch, calls=calls), escalate=None, ledger=ledger,
                land=lambda minted: True, alias="thinker", today="2026-09-17",
                source_facts={}, contradictions=[], debates={},
                verdict_ledger=type("L", (), {"latest_for": lambda self, f: []})())
    assess_record(fake_ctx, "features/structural-typing.yaml", repo_root=feature_repo, deps=deps)
    second = assess_record(fake_ctx, "features/structural-typing.yaml", repo_root=feature_repo,
                           deps=deps)
    assert len(calls) == 1
    assert second.skipped == 1
    assert second.changed is False


def test_a_level_3_assessment_is_escalated(feature_repo, fake_ctx, monkeypatch):
    escalated = []

    def _escalate(assessment, inputs):
        escalated.append(assessment.fact_id)
        return Assessment(fact_id=assessment.fact_id, level=2, signals=assessment.signals,
                          model=assessment.model, prompt=assessment.prompt,
                          run_id=assessment.run_id, escalated_to="claude")

    outcome = assess_record(
        fake_ctx, "features/structural-typing.yaml", repo_root=feature_repo,
        deps=Deps(assess=_deps(monkeypatch, level=3, signals=("verdict:contradicted:base",)),
                  escalate=_escalate, ledger=AssessmentLedger(feature_repo / "l.sqlite"),
                  land=lambda minted: True, alias="thinker", today="2026-09-17",
                  source_facts={}, contradictions=[], debates={},
                  verdict_ledger=type("L", (), {"latest_for": lambda self, f: []})()))
    assert escalated == list(outcome.levels)
    assert outcome.escalated == 1
    assert set(outcome.levels.values()) == {2}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv --directory tools/research run pytest tests/test_controversy_run.py -m '' -v`
Expected: FAIL — `ModuleNotFoundError: langatlas_research.controversy.run`

- [ ] **Step 3: Write `run.py`**

```python
# tools/research/src/langatlas_research/controversy/run.py
"""One record in, at most one commit out.

Why the record rather than the fact is the unit of work: §6.4 scores facts, but D36 commits
record files. Assessing a record's facts together means a record's block is never half-updated,
and a budget stop (D43) pauses at a record boundary where the next run can resume cleanly.

Why `Deps`: every collaborator here is either expensive (the university API, Claude, git) or
run-wide (source tiers, the contradiction ledger, debates). Passing them in makes the loop
testable with no provider and no database, and makes the nightly job build them exactly once."""
import re
from dataclasses import dataclass, field
from pathlib import Path

from langatlas_research.controversy.assemble import assemble_inputs
from langatlas_research.controversy.assessor import needs_escalation
from langatlas_research.controversy.block import controversy_mint, merge_block, unchanged
from langatlas_research.controversy.inputs import inputs_digest

_CHARACTERISTIC = re.compile(r"^characteristic\([^,]+,\s*(c-[a-z0-9-]+)")
_SYNTAX = re.compile(r"^syntax-valid\([^,]+\.sx\.([a-z0-9-]+)")
_QUALITY = re.compile(r"^quality-assessment\([^,]+,\s*([a-z0-9-]+)")


@dataclass(frozen=True)
class Deps:
    """Everything `assess_record` needs that it must not construct itself."""

    assess: object                 # (ctx, fact_id, inputs, *, alias, prompt) -> Assessment
    escalate: object | None        # (Assessment, ControversyInputs) -> Assessment
    ledger: object                 # AssessmentLedger
    land: object                   # (MintedRecord) -> bool  (True when it landed)
    alias: str
    today: str
    source_facts: dict
    contradictions: list
    debates: dict
    verdict_ledger: object
    spread_min_assessments: int = 2


@dataclass(frozen=True)
class RecordOutcome:
    record_path: str
    assessed: int = 0
    skipped: int = 0
    escalated: int = 0
    changed: bool = False
    levels: dict = field(default_factory=dict)


def anchor_key(claim: str) -> str:
    """§3.2's anchor suffix for a derived fact, recovered from its canonical claim.

    The block is keyed by anchor rather than by fact id because the anchor survives a claim
    correction (which mints a new fact id) — so a re-assessment replaces the entry it should
    replace instead of accumulating one per historical claim."""
    kind = claim.split("(", 1)[0]
    if kind == "node-definition":
        return "summary"
    if kind in ("instance-exists", "edge-exists", "rule-exists"):
        return "exists"
    if kind == "edge-polarity":
        return "polarity"
    if (match := _CHARACTERISTIC.match(claim)):
        return f"characteristics[{match.group(1)}]"
    if (match := _SYNTAX.match(claim)):
        return f"syntax[{match.group(1)}]"
    if (match := _QUALITY.match(claim)):
        return f"assessments[{match.group(1)}]"
    return kind


def store_record_paths(repo_root: Path) -> list[str]:
    """Every canonical record file, repo-relative and in a stable order — the nightly job's
    work-item list.

    Relative, because that is what `land_record` commits and what a checkpoint row has to
    survive a repo being cloned somewhere else. `iter_store_records` yields absolute paths."""
    from langatlas_validate.store import iter_store_records

    return sorted(str(path.relative_to(repo_root))
                  for path, _kind, _text, _data in iter_store_records(repo_root))


def _load(repo_root: Path, record_path: str):
    """@raises FileNotFoundError: the path is not (or is no longer) a canonical store record —
        which the nightly job reads as finished work, not as an error to retry."""
    from langatlas_validate.store import iter_store_records

    for path, kind, text, data in iter_store_records(repo_root):
        if str(path.relative_to(repo_root)) == record_path:
            return kind, text, data
    raise FileNotFoundError(f"{record_path} is not a canonical store record")


def assess_record(ctx, record_path: str, *, repo_root: Path, deps: Deps) -> RecordOutcome:
    """Assess every fact this record derives, then land the record if its block changed.

    @raises BudgetExceeded: straight through from the assessor — the caller (the job) turns it
        into a `blocked` item, and this record is simply re-attempted on resume. Nothing is
        landed on the way out, so a half-assessed record never reaches git.
    @returns counts plus fact_id -> final level."""
    from langatlas_research.controversy.assemble import record_facts

    kind, text, data = _load(repo_root, record_path)
    facts = record_facts(Path(record_path), kind, text, data)

    assessments, levels = {}, {}
    assessed = skipped = escalated = 0
    for fact in facts:
        inputs = assemble_inputs(fact, record=data, ledger=deps.verdict_ledger,
                                 source_facts=deps.source_facts,
                                 contradictions=deps.contradictions, debates=deps.debates,
                                 spread_min_assessments=deps.spread_min_assessments)
        digest = inputs_digest(inputs)
        previous = deps.ledger.previous(fact["fact_id"])
        if previous is not None and previous[0] == digest:
            # §6.4: unchanged inputs => unchanged level, so a re-run is free. The record's
            # existing block already says what this fact's level is; nothing to do.
            skipped += 1
            levels[fact["fact_id"]] = previous[1]
            continue

        assessment = deps.assess(ctx, fact["fact_id"], inputs, alias=deps.alias)
        assessed += 1
        if deps.escalate is not None and needs_escalation(assessment):
            assessment = deps.escalate(assessment, inputs)
            escalated += 1
        assessments[anchor_key(fact["claim"])] = assessment
        levels[fact["fact_id"]] = assessment.level
        deps.ledger.record(assessment, digest=digest)

    if not assessments:
        return RecordOutcome(record_path=record_path, assessed=assessed, skipped=skipped,
                             escalated=escalated, levels=levels)

    merged = merge_block(data, assessments, date=deps.today)
    minted = controversy_mint(record_path, merged, kind=kind, base_text=text)
    if unchanged(minted, text):
        return RecordOutcome(record_path=record_path, assessed=assessed, skipped=skipped,
                             escalated=escalated, levels=levels)
    changed = bool(deps.land(minted))
    return RecordOutcome(record_path=record_path, assessed=assessed, skipped=skipped,
                         escalated=escalated, changed=changed, levels=levels)


def default_land(repo_root: Path, chat_run_id: str):
    """The production lander: 3A's `land_drafts`, one commit per record file (D36)."""
    from langatlas_commit.land import Landed
    from langatlas_research.land import land_drafts

    def _land(minted) -> bool:
        (_rendered, outcome), = land_drafts([lambda: minted], repo_root=repo_root,
                                            chat_run_id=chat_run_id)
        return isinstance(outcome, Landed)

    return _land
```

- [ ] **Step 4: Run the tests**

Run: `uv --directory tools/research run pytest tests/test_controversy_run.py -m '' -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Wire the CLI**

In `tools/research/src/langatlas_research/cli.py`, register the subcommand in `main`:

```python
    p_contro = sub.add_parser("controversy").add_subparsers(dest="controversy_command",
                                                            required=True)
    p_assess = p_contro.add_parser("assess", help="assess controversy levels (D21/D25)")
    p_assess.add_argument("records", nargs="*",
                          help="record paths; default: every record in the store")
    p_assess.add_argument("--limit", type=int, default=None,
                          help="stop after this many facts (default: config's max_facts_per_run)")
    p_assess.add_argument("--no-escalate", action="store_true",
                          help="skip the Claude review; level-3 and ambiguous facts are"
                               " assessed by the thinker alone and reported, not landed")
    p_contro.add_parser("status", help="levels recorded by the last assessment runs")
```

and add the dispatcher:

```python
def _dispatch_controversy(args, root: Path | None) -> int:
    """D21/D25's assessor. Sources, contradictions and debates are read once for the whole
    run; the verdict ledger and the assessment ledger are opened once each."""
    from langatlas_ingest.verify.ledger import VerdictLedger
    from langatlas_pipeline.providers.core import RunContext

    from langatlas_research.config import ResearchConfig
    from langatlas_research.controversy.assemble import load_deps
    from langatlas_research.controversy.assessor import assess_inputs
    from langatlas_research.controversy.escalate import capture_candidate, escalate
    from langatlas_research.controversy.ledger import AssessmentLedger
    from langatlas_research.controversy.run import Deps, assess_record, default_land, store_record_paths
    from langatlas_research.paths import research_config_path

    repo = root or REPO_ROOT
    config = ResearchConfig.load(research_config_path(repo)).controversy

    if args.controversy_command == "status":
        with AssessmentLedger() as ledger:
            levels = ledger.levels()
        counts = {level: sum(1 for v in levels.values() if v == level) for level in (0, 1, 2, 3)}
        print(f"{len(levels)} assessed fact(s): "
              + ", ".join(f"level {k}: {v}" for k, v in counts.items()))
        return 0

    today = _dt.date.today().isoformat()
    paths = list(args.records) or store_record_paths(repo)
    budget = args.limit if args.limit is not None else config.max_facts_per_run
    totals = {"assessed": 0, "skipped": 0, "escalated": 0, "changed": 0}

    with VerdictLedger() as verdicts, AssessmentLedger() as ledger, \
            RunContext.start(kind="controversy", slug=today) as ctx:
        shared = load_deps(repo, verdicts)

        def _escalate(assessment, inputs):
            # Its own RunContext (D18): the review is a different conversation with a
            # different model, and a shared transcript would make the volume pass unreadable.
            with RunContext.start(kind="controversy-escalation",
                                  slug=assessment.fact_id) as review_ctx:
                final = escalate(review_ctx, assessment, inputs,
                                 role_config=config.escalation)
            capture_candidate(assessment, final, inputs, repo_root=repo, today=today)
            return final

        deps = Deps(assess=assess_inputs,
                    escalate=None if args.no_escalate else _escalate,
                    ledger=ledger, land=default_land(repo, ctx.run_id), alias=config.alias,
                    today=today, source_facts=shared.source_facts,
                    contradictions=shared.contradictions, debates=shared.debates,
                    verdict_ledger=verdicts,
                    spread_min_assessments=config.spread_min_assessments)
        for record_path in paths:
            if totals["assessed"] >= budget:
                print(f"budget reached ({budget} facts); re-run to continue")
                break
            outcome = assess_record(ctx, record_path, repo_root=repo, deps=deps)
            totals["assessed"] += outcome.assessed
            totals["skipped"] += outcome.skipped
            totals["escalated"] += outcome.escalated
            totals["changed"] += int(outcome.changed)
            if outcome.assessed or outcome.changed:
                print(f"{record_path}: assessed {outcome.assessed}, skipped {outcome.skipped},"
                      f" escalated {outcome.escalated},"
                      f" {'landed' if outcome.changed else 'unchanged'}")
    print(f"total: {totals['assessed']} assessed, {totals['skipped']} unchanged,"
          f" {totals['escalated']} escalated, {totals['changed']} record(s) landed")
    return 0
```

and dispatch it alongside the existing commands (`if args.command == "controversy": return
_dispatch_controversy(args, args.repo_root)`).

- [ ] **Step 6: Check the CLI parses**

Run: `uv --directory tools/research run langatlas-research controversy --help`
Expected: usage text listing `assess` and `status`.

Run: `uv --directory tools/research run langatlas-research controversy status`
Expected: `0 assessed fact(s): level 0: 0, level 1: 0, level 2: 0, level 3: 0`

- [ ] **Step 7: Commit**

```bash
git add tools/research/src/langatlas_research/controversy/run.py \
        tools/research/src/langatlas_research/cli.py \
        tools/research/tests/test_controversy_run.py \
        docs/superpowers/plans/2026-09-16-stage-3d-controversy-assessor.md
git commit -m "feat(#stage-3d): assess a record's facts together and land the block once"
```

---

## Task 8: The `nightly-controversy` job kind and its cadence

**Files:**
- Create: `tools/orchestrator/src/langatlas_orchestrator/jobs/controversy.py`
- Create: `config/jobs/nightly-controversy.yaml`
- Modify: `config/jobs/crontab.example`
- Modify: `tools/orchestrator/src/langatlas_orchestrator/jobs/__init__.py` (import the module so
  the kind registers — follow whatever the existing file does for `r3_tagging`)
- Test: `tools/orchestrator/tests/test_controversy_job.py`

**Interfaces:**
- Consumes: `register_job_kind`, `ItemOutcome`, Task 7's `assess_record` / `store_record_paths` /
  `Deps`.
- Produces: job kind `nightly-controversy` (enumerator + item runner).

- [ ] **Step 1: Write the failing tests**

```python
# tools/orchestrator/tests/test_controversy_job.py
"""The job kind's contract with the driver: what it enumerates, and how it classifies failure."""
import psycopg
import pytest

from langatlas_orchestrator.jobs import controversy as job
from langatlas_orchestrator.registry import get_job_kind
from langatlas_pipeline.errors import CircuitOpen, ProviderTransportError


def test_the_kind_is_registered():
    enumerate_fn, run_fn = get_job_kind("nightly-controversy")
    assert callable(enumerate_fn) and callable(run_fn)


def test_it_enumerates_one_item_per_record(tmp_path, monkeypatch):
    monkeypatch.setattr(job, "store_record_paths",
                        lambda root: ["features/a.yaml", "concepts/b.yaml"])
    assert job._enumerate({}, tmp_path) == ["concepts/b.yaml", "features/a.yaml"]


def test_records_can_be_narrowed_from_the_spec(tmp_path, monkeypatch):
    monkeypatch.setattr(job, "store_record_paths", lambda root: ["features/a.yaml"])
    assert job._enumerate({"records": ["concepts/b.yaml"]}, tmp_path) == ["concepts/b.yaml"]


def test_a_provider_outage_blocks_the_item_rather_than_crashing(tmp_path, monkeypatch):
    monkeypatch.setattr(job, "_assess",
                        lambda *a, **k: (_ for _ in ()).throw(ProviderTransportError("down")))
    outcome = job._run_item(object(), "features/a.yaml", {}, tmp_path)
    assert outcome.status == "blocked"
    assert "provider unavailable" in outcome.detail


def test_a_database_outage_blocks_the_item(tmp_path, monkeypatch):
    monkeypatch.setattr(job, "_assess",
                        lambda *a, **k: (_ for _ in ()).throw(psycopg.OperationalError("no db")))
    assert job._run_item(object(), "features/a.yaml", {}, tmp_path).status == "blocked"


def test_a_record_that_vanished_is_done_not_blocked(tmp_path, monkeypatch):
    """The store moves under a nightly batch all the time — a record tombstoned since the
    enumerator ran is finished work, not a failure to retry forever."""
    monkeypatch.setattr(job, "_assess",
                        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("gone")))
    outcome = job._run_item(object(), "features/a.yaml", {}, tmp_path)
    assert outcome.status == "done"
    assert "no longer in the store" in outcome.detail
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv --directory tools/orchestrator run pytest tests/test_controversy_job.py -v`
Expected: FAIL — `ModuleNotFoundError: langatlas_orchestrator.jobs.controversy`

- [ ] **Step 3: Write the job kind**

```python
# tools/orchestrator/src/langatlas_orchestrator/jobs/controversy.py
"""D21/D25's nightly controversy batch (§6.4/§7.11), driven through the generic loop.

One work item per canonical record: that is the commit grain (D36), so it is the grain at which
an interrupted batch can resume without risking a half-written block. Event-driven in the sense
§6.4 means it — the run walks the whole store, but a fact whose structured inputs have not
changed costs nothing, so a quiet night is a cheap night.

Unlike R3's tagging job this one *is* cron-driven: nothing here is gated on a cycle sign-off,
because the assessor reads what is already committed and proposes no content."""
from pathlib import Path

import psycopg

from langatlas_ingest.verify.ledger import VerdictLedger
from langatlas_pipeline.errors import CircuitOpen, ProviderTransportError, StructuredOutputError
from langatlas_research.config import ResearchConfig
from langatlas_research.controversy.assemble import load_deps
from langatlas_research.controversy.assessor import assess_inputs
from langatlas_research.controversy.ledger import AssessmentLedger
from langatlas_research.controversy.run import Deps, assess_record, default_land, store_record_paths
from langatlas_research.errors import AssessorOutputInvalid
from langatlas_research.paths import research_config_path

from langatlas_orchestrator.registry import ItemOutcome, register_job_kind

KIND = "nightly-controversy"


def _enumerate(extra: dict, repo_root: Path) -> list[str]:
    """@param extra: `records: [...]` narrows a manual run to specific files; omit it for the
        whole store."""
    return sorted(extra.get("records") or store_record_paths(repo_root))


def _config(repo_root: Path):
    return ResearchConfig.load(research_config_path(repo_root)).controversy


def _assess(ctx, record_path: str, repo_root: Path, extra: dict):
    """The one provider-, database- and git-touching call, isolated so tests can replace it."""
    from datetime import date

    config = _config(repo_root)
    with VerdictLedger() as verdicts, AssessmentLedger() as ledger:
        shared = load_deps(repo_root, verdicts)
        deps = Deps(assess=assess_inputs, escalate=_escalator(repo_root, config),
                    ledger=ledger, land=default_land(repo_root, getattr(ctx, "run_id", "")),
                    alias=extra.get("alias") or config.alias, today=date.today().isoformat(),
                    source_facts=shared.source_facts, contradictions=shared.contradictions,
                    debates=shared.debates, verdict_ledger=verdicts,
                    spread_min_assessments=config.spread_min_assessments)
        return assess_record(ctx, record_path, repo_root=repo_root, deps=deps)


def _escalator(repo_root: Path, config):
    from datetime import date

    from langatlas_pipeline.providers.core import RunContext
    from langatlas_research.controversy.escalate import capture_candidate, escalate

    def _escalate(assessment, inputs):
        with RunContext.start(kind="controversy-escalation", slug=assessment.fact_id) as ctx:
            final = escalate(ctx, assessment, inputs, role_config=config.escalation)
        capture_candidate(assessment, final, inputs, repo_root=repo_root,
                          today=date.today().isoformat())
        return final

    return _escalate


def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
    try:
        outcome = _assess(ctx, item_key, repo_root, extra)
    except FileNotFoundError as exc:
        # The store moved under the enumerator (a tombstone, a migration). Finished work, not
        # a failure: re-attempting it forever would wedge the batch on a file that is gone.
        return ItemOutcome(status="done", detail=f"no longer in the store: {exc}")
    except psycopg.OperationalError as exc:
        return ItemOutcome(status="blocked", detail=f"database unavailable: {exc}")
    except (ProviderTransportError, CircuitOpen) as exc:
        return ItemOutcome(status="blocked", detail=f"provider unavailable: {exc}")
    except (AssessorOutputInvalid, StructuredOutputError) as exc:
        # Deterministic at temperature 0 and cached: a retry returns the same answer. The
        # record keeps whatever level it already had, and the run's log says which one failed.
        return ItemOutcome(status="done", detail=f"unusable assessor response: {exc}")
    return ItemOutcome(status="done", record_key=item_key,
                       detail=f"assessed {outcome.assessed}, unchanged {outcome.skipped},"
                              f" escalated {outcome.escalated},"
                              f" {'landed' if outcome.changed else 'no change'}")


register_job_kind(KIND, _enumerate, _run_item)
```

- [ ] **Step 4: Write the batch spec**

`config/jobs/nightly-controversy.yaml`:

```yaml
# D21/D25's nightly controversy batch (§6.4). Real as of Stage 3D; Stage 5 gives it volume.
# `records` narrows a manual run to specific files; omit it for the whole store.
#
#   uv run --package langatlas-orchestrator langatlas-orchestrator run \
#     config/jobs/nightly-controversy.yaml
#
# Optional per-run extra: `--set alias=<alias>` (default comes from config/research.yaml).
kind: nightly-controversy
checkpoint_path: .private/orchestrator/nightly-controversy.sqlite
budget:
  max_calls: 250            # D25's ~200 facts/night, plus headroom for escalation reviews
  max_claude_messages: 120  # escalation only; the volume pass never touches the Claude channel
  max_wall_seconds: 21600
```

- [ ] **Step 5: Add the cron line**

In `config/jobs/crontab.example`, directly under the nightly-verification entry:

```
# nightly controversy assessment (D21/D25) — runs after verification, because a fact's
# verdicts are one of the assessor's structured inputs and a stale verdict is a stale level
30 2 * * *        cd <repo> && uv run --package langatlas-orchestrator langatlas-orchestrator run config/jobs/nightly-controversy.yaml
```

and amend the existing verification comment so the pair reads as §7.11's "nightly
verification/controversy batch" — two job kinds, one nightly slot, verification first.

- [ ] **Step 6: Run the job tests**

Run: `uv --directory tools/orchestrator run pytest tests/test_controversy_job.py tests/test_registry.py -v`
Expected: PASS (6 new + the existing registry tests)

- [ ] **Step 7: Check the spec loads and the kind resolves**

Run: `uv --directory tools/orchestrator run python -c "import langatlas_orchestrator.jobs.controversy; from langatlas_orchestrator.registry import registered_kinds; print(registered_kinds())"`
Expected: a list containing `nightly-controversy` alongside the existing nine kinds.

- [ ] **Step 8: Commit**

```bash
git add tools/orchestrator/src/langatlas_orchestrator/jobs/controversy.py \
        tools/orchestrator/src/langatlas_orchestrator/jobs/__init__.py \
        tools/orchestrator/tests/test_controversy_job.py \
        config/jobs/nightly-controversy.yaml config/jobs/crontab.example \
        docs/superpowers/plans/2026-09-16-stage-3d-controversy-assessor.md
git commit -m "feat(#stage-3d): run the controversy assessment as a nightly job kind"
```

---

## Task 9: The golden entry point, the scored run, CI, and the Stage 3D exit test

**Files:**
- Modify: `tools/research/src/langatlas_research/controversy/assessor.py` (add `GoldenAssessor`,
  `golden_assessor`, `golden_assessor_thinker_only`)
- Modify: `config/ingest.yaml`
- Modify: `tools/ingest/src/langatlas_ingest/cli.py` (the `close()` hook on the controversy branch)
- Modify: `tests/golden/controversy/README.md`
- Modify: `.github/workflows/ci.yml`
- Create: `tools/research/tests/test_exit_3d.py`
- Test: `tools/research/tests/test_controversy_goldens.py`

**Interfaces:**
- Consumes: `langatlas_ingest.goldens.items.ControversyCase`,
  `langatlas_ingest.goldens.runner.run_controversy_goldens`, `score_controversy`.
- Produces: `goldens.controversy_assessor_entry_point` pointing at a real callable, and a
  committed scored run.

**What the golden set does and does not exercise.** 2B's cases supply `inputs` *directly*, so a
scored run exercises the rubric, the signal filter and the escalation policy — never Task 2's
assembly. That is the correct split: assembly is deterministic and has its own unit tests
(Task 2), while the level assignment is the part a model can get wrong in interesting ways. Do
not "improve" the goldens by making them re-derive inputs from a store; they would stop being a
calibration set and start being an integration test.

- [ ] **Step 1: Write the failing tests**

```python
# tools/research/tests/test_controversy_goldens.py
"""§6.4's calibration path: the committed cases in, an ordinal score out."""
import pytest

from langatlas_ingest.goldens.items import ControversyCase
from langatlas_ingest.goldens.loader import load_controversy_cases, validate_controversy_cases
from langatlas_ingest.goldens.runner import run_controversy_goldens
from langatlas_ingest.paths import GOLDEN_CONTROVERSY_DIR
from langatlas_research.controversy.assessor import Assessment, GoldenAssessor

CASE = ControversyCase(
    id="c-test-0001", expected_level=3,
    inputs={"debates": [{"id": "d-01-typing-003", "outcome": "escalated",
                         "standing_dissent": True, "rounds": 4}],
            "verdicts": [{"fact": "f-a", "citation": 1, "verdict": "contradicted",
                          "field": "base", "tier": "A"}],
            "source_strength": {"tier_a": 2, "tier_b": 0, "independent_corroborations": 1}},
    expected_signals=("verdict:contradicted:base", "debate:d-01-typing-003:escalated"))


def test_the_entry_point_returns_a_bare_ordinal_level():
    """`Assessor` is `(case) -> int`. The runner scores integers; anything else is a crash at
    the far end of a paid run."""
    assessor = GoldenAssessor(assess=lambda ctx, fact_id, inputs, *, alias, prompt=None:
                              Assessment(fact_id=fact_id, level=3, signals=()),
                              escalate=None, ctx=object(), alias="thinker")
    assert assessor(CASE) == 3


def test_a_case_id_stands_in_for_the_fact_id():
    seen = []

    def _assess(ctx, fact_id, inputs, *, alias, prompt=None):
        seen.append(fact_id)
        return Assessment(fact_id=fact_id, level=0, signals=())

    GoldenAssessor(assess=_assess, escalate=None, ctx=object(), alias="thinker")(CASE)
    assert seen == ["c-test-0001"]


def test_escalation_runs_for_the_golden_set_too():
    """Level 3 always escalates in production (§6.4), so a scored run that skipped escalation
    would measure something the pipeline never does — and level-3 recall is the headline
    metric."""
    escalated = []

    def _assess(ctx, fact_id, inputs, *, alias, prompt=None):
        return Assessment(fact_id=fact_id, level=3, signals=())

    def _escalate(assessment, inputs):
        escalated.append(assessment.fact_id)
        return Assessment(fact_id=assessment.fact_id, level=2, signals=(),
                          escalated_to="claude")

    assert GoldenAssessor(assess=_assess, escalate=_escalate, ctx=object(),
                          alias="thinker")(CASE) == 2
    assert escalated == ["c-test-0001"]


def test_a_refused_input_surfaces_as_a_scoring_failure_not_a_silent_zero():
    bad = ControversyCase(id="c-test-0002", expected_level=0,
                          inputs={"github_activity": {"issues": 3}})
    assessor = GoldenAssessor(assess=lambda *a, **k: Assessment(fact_id="x", level=0),
                              escalate=None, ctx=object(), alias="thinker")
    with pytest.raises(Exception):
        assessor(bad)


def test_the_committed_bootstrap_cases_still_validate():
    cases = load_controversy_cases(GOLDEN_CONTROVERSY_DIR)
    assert validate_controversy_cases(cases) == []
    assert len(cases) >= 15


def test_the_runner_scores_a_perfect_assessor_at_one():
    cases = load_controversy_cases(GOLDEN_CONTROVERSY_DIR)
    expected = {case.id: case.expected_level for case in cases}
    score = run_controversy_goldens(cases, lambda case: expected[case.id])
    assert score.exact_accuracy == 1.0
    assert score.level3_recall == 1.0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv --directory tools/research run pytest tests/test_controversy_goldens.py -m '' -v`
Expected: FAIL — `ImportError: cannot import name 'GoldenAssessor'`

- [ ] **Step 3: Add the golden entry points to `assessor.py`**

```python
class GoldenAssessor:
    """§6.4's calibration adapter: `ControversyCase -> int`, the `Assessor` protocol 2B froze.

    Deliberately thin. A golden case supplies its structured inputs directly, so this skips
    assembly entirely and exercises what a model can actually get wrong: the rubric, the signal
    filter and the escalation policy.

    It opens a `RunContext` lazily on first use and closes it in `close()`, which step 6 teaches
    `golden-score` to call — a calibration number whose transcript was never finalized is a
    number nobody can trace back to a model and a prompt version."""

    def __init__(self, *, assess=assess_inputs, escalate=None, ctx=None, alias: str = "thinker",
                 prompt: PromptRef | None = None):
        self._assess, self._escalate = assess, escalate
        self._ctx, self._alias, self._prompt = ctx, alias, prompt
        self._owns_ctx = False

    def _context(self):
        if self._ctx is None:
            from langatlas_pipeline.providers.core import RunContext

            self._ctx = RunContext.start(kind="controversy-goldens", slug="scored")
            self._owns_ctx = True
        return self._ctx

    def __call__(self, case) -> int:
        """@raises ControversyInputRefused: a case carrying a forbidden or unknown input —
            surfaced, never scored as a level, because a case the assessor may not legally see
            is a broken case, not a hard one."""
        inputs = ControversyInputs.from_mapping(case.inputs or {})
        assessment = self._assess(self._context(), case.id, inputs, alias=self._alias,
                                  prompt=self._prompt)
        if self._escalate is not None and needs_escalation(assessment):
            assessment = self._escalate(assessment, inputs)
        return int(assessment.level)

    def close(self) -> None:
        if self._owns_ctx and self._ctx is not None:
            self._ctx.close()
            self._ctx, self._owns_ctx = None, False


def _claude_escalator():
    from langatlas_pipeline.providers.core import RunContext
    from langatlas_research.config import ResearchConfig
    from langatlas_research.controversy.escalate import escalate as _escalate
    from langatlas_research.paths import research_config_path

    config = ResearchConfig.load(research_config_path()).controversy

    def _run(assessment, inputs):
        with RunContext.start(kind="controversy-escalation", slug=assessment.fact_id) as ctx:
            return _escalate(ctx, assessment, inputs, role_config=config.escalation)

    return _run


def golden_assessor():
    """The entry point `config/ingest.yaml` names — what production actually does, escalation
    included. Costs Claude messages: a scored run is a measurement, deliberately not a CI gate
    (§8.6)."""
    from langatlas_research.config import ResearchConfig
    from langatlas_research.paths import research_config_path

    config = ResearchConfig.load(research_config_path()).controversy
    return GoldenAssessor(escalate=_claude_escalator(), alias=config.alias)


def golden_assessor_thinker_only():
    """The cheap variant: the university-API pass alone, no Claude. Useful for measuring the
    first pass in isolation — e.g. how much of level-3 recall the escalation step is carrying."""
    from langatlas_research.config import ResearchConfig
    from langatlas_research.paths import research_config_path

    return GoldenAssessor(alias=ResearchConfig.load(research_config_path()).controversy.alias)
```

Add the missing import at the top of `assessor.py`: `from langatlas_research.controversy.inputs
import ControversyInputs, derivable_signals` already covers `ControversyInputs`.

- [ ] **Step 4: Run the golden tests**

Run: `uv --directory tools/research run pytest tests/test_controversy_goldens.py -m '' -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Make the entry point a case-callable, not a factory**

`_cmd_golden_score` hands `load_entry_point(assessor_dotted)` **straight to
`run_controversy_goldens` as the assessor** (`tools/ingest/src/langatlas_ingest/cli.py:250-255`),
so the resolved attribute must itself satisfy `Assessor` — `(case) -> int`. A factory there would
fail on the first case, after the verifier half of a paid run had already been spent. Add to
`assessor.py`:

```python
def _default_alias() -> str:
    from langatlas_research.config import ResearchConfig
    from langatlas_research.paths import research_config_path

    return ResearchConfig.load(research_config_path()).controversy.alias


class _LazyGoldenAssessor(GoldenAssessor):
    """The module-level entry point `config/ingest.yaml` names.

    Config is read on first call rather than at import, so merely importing this module — which
    `load_entry_point` does — never touches the filesystem or a provider."""

    def __init__(self, *, escalate_factory=None):
        super().__init__(escalate=None, alias="")
        self._escalate_factory = escalate_factory
        self._configured = False

    def __call__(self, case) -> int:
        if not self._configured:
            self._alias = _default_alias()
            if self._escalate_factory is not None:
                self._escalate = self._escalate_factory()
            self._configured = True
        return super().__call__(case)


#: What production does, escalation included — the entry point `config/ingest.yaml` names.
golden_assessor = _LazyGoldenAssessor(escalate_factory=_claude_escalator)
#: The university-API pass alone. Useful for measuring how much of level-3 recall the
#: escalation step is carrying.
golden_assessor_thinker_only = _LazyGoldenAssessor()
```

and delete the two factory functions `golden_assessor()` / `golden_assessor_thinker_only()`
sketched in step 3 — the singletons replace them. Add the guard test:

```python
def test_the_configured_entry_point_resolves_to_a_case_callable():
    """The bug this guards: `golden-score` calls `load_entry_point(...)` and hands the result
    straight to the runner as the assessor."""
    from langatlas_ingest.config import IngestConfig
    from langatlas_ingest.goldens.runner import load_entry_point

    dotted = IngestConfig.load().controversy_assessor_entry_point
    assert dotted
    assessor = load_entry_point(dotted)
    assert callable(assessor) and not isinstance(assessor, type)
```

- [ ] **Step 6: Give the controversy branch the same `close()` hook the verifier branch has, and point the config**

The verifier branch of `_cmd_golden_score` calls a duck-typed `close()` in a `finally` so a
verifier that opened a `RunContext` gets its transcript and `manifest.yaml` written. The
controversy branch has no such hook, and `GoldenAssessor` opens a `RunContext` lazily — so
without this, a scored run leaves its own transcript unfinalized. A calibration number nobody can
trace is not a calibration number. In `tools/ingest/src/langatlas_ingest/cli.py`:

```python
    if assessor_dotted:
        cases = load_controversy_cases(Path(args.controversy_dir
                                            or GOLDEN_CONTROVERSY_DIR))
        assessor = load_entry_point(assessor_dotted)
        try:
            print(run_controversy_goldens(cases, assessor).to_markdown())
        finally:
            # Same duck-typed hook as the verifier branch above: 3D's `GoldenAssessor` opens a
            # `RunContext` lazily, and `close()` is what finalizes its transcript and manifest.
            close = getattr(assessor, "close", None)
            if callable(close):
                close()
```

Then, in `config/ingest.yaml`:

```yaml
  # Dotted `module:attr` path to the D21/D25 assessor (Stage 3D). `golden-score` resolves it and
  # calls it once per case, so it is the assessor itself, not a factory. The module lives in
  # `langatlas_research`, so score it from that package's environment:
  #   uv --directory tools/research run langatlas-sources golden-score \
  #     --controversy-assessor langatlas_research.controversy.assessor:golden_assessor
  controversy_assessor_entry_point: langatlas_research.controversy.assessor:golden_assessor
```

Run: `uv --directory tools/research run pytest tests/test_controversy_goldens.py -m '' -v`
Expected: PASS (7 tests)

Run: `uv --directory tools/ingest run pytest tests/test_goldens_cli.py -v`
Expected: PASS — the existing CLI tests still pass with the new `finally`.

- [ ] **Step 7: Update the golden README**

Append to `tests/golden/controversy/README.md`:

```markdown
## The assessor is live (Stage 3D)

`goldens.controversy_assessor_entry_point` points at
`langatlas_research.controversy.assessor:golden_assessor`, which lives in the **research**
package. Score it from there — `tools/ingest`'s environment cannot import it:

    uv --directory tools/research run langatlas-sources golden-score \
      --controversy-assessor langatlas_research.controversy.assessor:golden_assessor

A scored run costs university-API calls *and* Claude messages (every level-3 assignment
escalates, §6.4). `langatlas_research.controversy.assessor:golden_assessor_thinker_only` scores
the first pass alone when you want to know how much of level-3 recall the escalation step is
carrying.

The run is a **measurement, not a CI gate** (§8.6): CI shape-checks these cases and never scores
them. New cases arrive from `candidates/` — see that directory's README.
```

- [ ] **Step 8: Write the Stage 3D exit test**

```python
# tools/research/tests/test_exit_3d.py
"""Stage 3D's exit condition, end to end against a real git repo and the real commit protocol.

No provider: the assessor and the escalation are injected. What this proves is the part that has
to be true whatever any model says — that a level reaches the canonical store only as a
schema-valid, signal-justified block, in one commit per record, without moving `ontology/VERSION`
and without ever minting a contradiction record."""
import subprocess

import pytest
from ruamel.yaml import YAML

from langatlas_research.controversy.assessor import Assessment
from langatlas_research.controversy.ledger import AssessmentLedger
from langatlas_research.controversy.run import Deps, assess_record, default_land
from langatlas_validate.store import validate_store

_yaml = YAML(typ="safe")

pytestmark = pytest.mark.git

FEATURE = """\
id: structural-typing
slug: structural-typing
name: Structural typing
layer: 2
summary:
  text: A type system in which type compatibility is determined by structure.
  sources:
    - source: pierce-tapl-2002
      locator: 'p. 251'
provenance:
  claim_origin: source-derived
"""


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


def test_a_contested_fact_lands_as_a_block_and_nothing_else_moves(store_repo, fake_ctx, tmp_path):
    repo = store_repo
    (repo / "features" / "structural-typing.yaml").write_text(FEATURE)
    (repo / "sources" / "pierce-tapl-2002.yaml").write_text(
        "id: pierce-tapl-2002\ntype: book\ntitle: Types and Programming Languages\n"
        "custom:\n  tier: A\n  grounding: secondary\n  locator_kinds: [page]\n"
        "  acquisition_note: library copy\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "seed the feature"], repo)
    _git(["push", "-q", "origin", "HEAD:main"], repo)
    version_before = (repo / "ontology" / "VERSION").read_text()
    head_before = _git(["rev-parse", "HEAD"], repo).strip()

    def _assess(ctx, fact_id, inputs, *, alias, prompt=None):
        return Assessment(fact_id=fact_id, level=3, signals=("verdict:contradicted:base",),
                          model="deepseek-v4-pro-thinking",
                          prompt="controversy-assessor@v-1a2b3c4d", run_id="r-1")

    def _escalate(assessment, inputs):
        return Assessment(fact_id=assessment.fact_id, level=2, signals=assessment.signals,
                          model=assessment.model, prompt=assessment.prompt,
                          run_id=assessment.run_id, escalated_to="claude")

    class _Verdicts:
        def latest_for(self, fact_id):
            from langatlas_ingest.verify.verdicts import PairVerdict
            return [PairVerdict(fact_id=fact_id, source_id="pierce-tapl-2002",
                                locator="p. 251", verdict="contradicted")]

    with AssessmentLedger(tmp_path / "assessments.sqlite") as ledger:
        deps = Deps(assess=_assess, escalate=_escalate, ledger=ledger,
                    land=default_land(repo, "r-1"), alias="thinker", today="2026-09-17",
                    source_facts={}, contradictions=[], debates={},
                    verdict_ledger=_Verdicts())
        outcome = assess_record(fake_ctx, "features/structural-typing.yaml", repo_root=repo,
                                deps=deps)

    assert outcome.changed is True
    assert outcome.escalated == 1

    # 1. The block is in the committed record, at level 2, with a machine signal and no prose.
    data = _yaml.load((repo / "features" / "structural-typing.yaml").read_text())
    entry, = data["controversy"]
    assert (entry["key"], entry["level"]) == ("summary", 2)
    assert entry["signals"] == ["verdict:contradicted:base"]
    assert entry["assessed"]["escalated_to"] == "claude"
    assert "rationale" not in entry

    # 2. The store still validates, block and all.
    assert validate_store(repo) == []

    # 3. Exactly one commit, and it touched exactly one file (D36).
    log = _git(["log", "--oneline", f"{head_before}..HEAD"], repo).splitlines()
    assert len(log) == 1
    assert _git(["show", "--name-only", "--format=", "HEAD"], repo).split() == \
        ["features/structural-typing.yaml"]

    # 4. A machine annotation is not an ontology change (§5.1).
    assert (repo / "ontology" / "VERSION").read_text() == version_before

    # 5. The assessor never mints a contradiction record (§6.4).
    assert _yaml.load((repo / "contradictions.yaml").read_text())["contradictions"] == []


def test_a_second_run_over_unchanged_inputs_is_free_and_silent(store_repo, fake_ctx, tmp_path):
    """§6.4's "unchanged inputs => unchanged level, so a re-run is free" — measured as: no
    model call, and no second commit."""
    repo = store_repo
    (repo / "features" / "structural-typing.yaml").write_text(FEATURE)
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "seed"], repo)
    _git(["push", "-q", "origin", "HEAD:main"], repo)

    calls = []

    def _assess(ctx, fact_id, inputs, *, alias, prompt=None):
        calls.append(fact_id)
        return Assessment(fact_id=fact_id, level=1, signals=(), run_id="r-1")

    class _Verdicts:
        def latest_for(self, fact_id):
            return []

    with AssessmentLedger(tmp_path / "assessments.sqlite") as ledger:
        deps = Deps(assess=_assess, escalate=None, ledger=ledger,
                    land=default_land(repo, "r-1"), alias="thinker", today="2026-09-17",
                    source_facts={}, contradictions=[], debates={}, verdict_ledger=_Verdicts())
        assess_record(fake_ctx, "features/structural-typing.yaml", repo_root=repo, deps=deps)
        head = _git(["rev-parse", "HEAD"], repo).strip()
        second = assess_record(fake_ctx, "features/structural-typing.yaml", repo_root=repo,
                               deps=deps)

    assert len(calls) == 1
    assert second.skipped == 1
    assert second.changed is False
    assert _git(["rev-parse", "HEAD"], repo).strip() == head
```

- [ ] **Step 9: Run the exit test**

Run: `uv --directory tools/research run pytest tests/test_exit_3d.py -m '' -v`
Expected: PASS (2 tests)

- [ ] **Step 10: Wire CI**

In `.github/workflows/ci.yml`, add a step after "Test the research package":

```yaml
      - name: Test the validate package
        # No database, no provider. Stage 3D added the controversy-block gate and the
        # machine-field exemption in `version-bump`, both of which are pure-Python checks.
        run: uv --directory tools/validate run pytest
```

and extend the orchestrator step's file list with `tests/test_controversy_job.py`.

- [ ] **Step 11: Run everything**

```bash
uv --directory tools/research run pytest -m '' -q
uv --directory tools/validate run pytest -q
uv --directory tools/orchestrator run pytest tests/test_r3_tagging_job.py tests/test_controversy_job.py tests/test_driver_overrides.py -q
uv --directory tools/validate run langatlas-validate ci
uv --directory tools/ingest run langatlas-sources golden-validate
```
Expected: all green.

- [ ] **Step 12: Score the assessor against the controversy golden set**

This one costs real provider calls and is run by hand, not in CI (§8.6):

```bash
uv --directory tools/research run langatlas-sources golden-score \
  --controversy-assessor langatlas_research.controversy.assessor:golden_assessor
```

Expected: a `# Controversy golden-case score` table with exact accuracy, within-one accuracy, the
4x4 confusion matrix and level-3 recall over the ~18 committed bootstrap cases. **Record the
numbers in the commit message.** There is no threshold to pass — §6.4 sets no bar for the
assessor, and the ordinal metrics are a measurement the developer reads. What *is* worth
reacting to: a level-3 recall below 1.0 (a missed level 3 is a dispute the site never shows) and
any confusion cell two levels off the diagonal.

- [ ] **Step 13: Commit**

```bash
git add tools/research/src/langatlas_research/controversy/assessor.py config/ingest.yaml \
        tools/ingest/src/langatlas_ingest/cli.py \
        tests/golden/controversy/README.md .github/workflows/ci.yml \
        tools/research/tests/test_controversy_goldens.py tools/research/tests/test_exit_3d.py \
        docs/superpowers/plans/2026-09-16-stage-3d-controversy-assessor.md
git commit -m "feat(#stage-3d): point the controversy golden set at the live assessor and prove the 3D exit path"
```

---

## Stage 3D exit condition

3D is done when all of the following are true:

1. `langatlas-research controversy assess` walks the canonical store, assigns every derived fact
   a level from structured inputs only, and lands a `controversy:` block for every fact at level
   ≥1 — one commit per record, no `ontology/VERSION` movement, no contradiction record minted.
2. A second run over unchanged inputs makes **zero** model calls and **zero** commits.
3. Every level-3 assignment, and every adjacent-level ambiguity, has been through the Claude
   escalation, and each review is sitting in `tests/golden/controversy/candidates/<YYYY-MM>.yaml`
   for the developer to hand-label.
4. `goldens.controversy_assessor_entry_point` resolves to a real `(case) -> int` callable, and a
   scored run against the bootstrap cases has been recorded.
5. `nightly-controversy` is a registered job kind with a committed batch spec and a line in
   `config/jobs/crontab.example`.
6. `validate_store` refuses a block that stores level 0, names a fact its record does not derive,
   carries a signal outside the grammar, or duplicates a key.
7. `uv --directory tools/validate run langatlas-validate ci` is green on a store that carries
   blocks.

**What 3D hands to 3E/3F:** a level on every fact, readable from the record itself — which is the
"graph health" input of 3F's R6 dossier and the controversy column the Stage-6 site renders behind
its explicitly-AI-judged glyph.

## Deliberately out of scope

Named here so no task drifts into them:

- **The cross-fact scan (D59)** and `type: cross-fact` contradiction records — they need
  `knowledge_embeddings` (§8.3/D62), which is Stage 5. The assessor reads whatever
  `contradictions.yaml` holds; today that is only `type: verification` records.
- **Presentation.** Thresholds, glyphs, popovers and the "AI-judged" label belong to the site
  (§6.4/§10.2), Stage 6. This plan stores a level and stores signals.
- **The `dispute` axis, the `verification` axis and confidence.** Orthogonal by §6.3; nothing here
  touches `derive_confidence` or the display-status precedence.
- **Human challenges.** No GitHub read, no `overrides.yaml`, no `challenge_activity` — §6.4
  excludes all of it from the assessor by construction, and the challenge path itself is Stage 6.
- **Re-verification triggers.** §6.3's event-driven re-verification is the verifier's job; a
  changed level never queues a re-verification.
- **Back-filling the golden set to ~50 cases.** The opportunistic lane is *built* here; filling it
  is the developer hand-labelling candidates over the remaining theme cycles.

## Self-review

**Spec coverage** (§6.4, walked clause by clause):

| Spec clause | Task |
|---|---|
| Four ordinal levels, 4 folded into 3 | Task 4 (schema `enum: [1,2,3]` + absent = 0), Task 5 (rubric) |
| Assessor = university-API `thinker` over a fixed rubric | Task 5 |
| Structured inputs only — the five permitted keys | Task 1 (allow-list), Task 2 (assembly) |
| Human-challenge-derived inputs excluded, incl. `closure_attempt` | Task 1 (refusal), Task 2 (`contradiction_projection`) |
| Claude = escalation target for adjacent ambiguity and all level 3 | Task 5 (`needs_escalation`), Task 6 |
| Claude = golden-set calibrator; opportunistic lane grows the set | Task 6 (`capture_candidate`), Task 9 |
| Event-driven nightly batches; unchanged inputs ⇒ unchanged level | Task 3 (ledger), Task 7 (skip path), Task 8 (cron) |
| Machine-written block; `signals` **is** the justification; absent = 0 | Task 4 (schema, no prose field), Task 5 (signal filter) |
| Never mints contradiction records | Task 2 (read-only), Task 9 exit test assertion 5 |
| Presentation thresholds belong to the site | Out of scope, stated |
| `goldens.controversy_assessor_entry_point` filled; scored run | Task 9 |
| One more job kind + `crontab.example` (§7.11) | Task 8 |

**Placeholder scan:** every step carries the actual prompt text, schema fragment, test body or
command. The two places that legitimately defer are (a) the prompt version hash, which is
computed by `mint_prompt_version` in Task 5 step 1 and printed for the implementer to record, and
(b) the scored numbers in Task 9 step 12, which are a measurement and cannot be known in advance.

**Type consistency:** `Assessment` is defined once (Task 5) and consumed by Tasks 3, 4, 6, 7, 9
with the same field names (`fact_id`, `level`, `signals`, `alternative`, `model`, `prompt`,
`run_id`, `escalated_to`). `ControversyInputs` is defined once (Task 1) and always constructed
through `from_mapping`. `merge_block` takes anchor keys, which only `anchor_key` (Task 7)
produces. Two cross-task ordering notes are called out in the tasks themselves: Task 4's
block-writer tests import `Assessment` from Task 5, and Task 9 step 6 corrects the entry-point
shape that step 5's config comment assumed.

**Known follow-ups for the developer, not defects in this plan:**

1. `anchor_key` covers today's eight claim kinds. Stage 5's `notes[n-<slug>]` facts (§3.4's
   `status: partial` notes) have no claim template yet, so they derive no facts and need no
   anchor — when they gain one, `anchor_key` gains a branch.
2. `source_strength` keeps 2B's three keys and therefore says nothing about tier-C/D backing. If
   the scored run shows the rubric under-reading thin-but-uncontested facts, the fix is a new
   golden stratum first and a fourth key second — in that order, or the goldens stop scoring the
   rubric that runs.

## Execution handoff

Plan complete and saved to
`docs/superpowers/plans/2026-09-16-stage-3d-controversy-assessor.md`. Two execution options:

1. **Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast
   iteration.
2. **Inline Execution** — execute tasks in this session using superpowers:executing-plans, batch
   execution with checkpoints.

Which approach?
