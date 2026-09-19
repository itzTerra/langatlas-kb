# Stage 3G — Structure plasticity (draft-only batch + structure review) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the seed ontology structure a testable hypothesis during the research phase: misfits become recorded findings instead of rejected runs, the first four themes are drafted without minting, and a developer structure review gates the first mint.

**Architecture:** This re-opens sub-plan 3C (R4). A new `structure-friction` finding kind and a `blocked` flag on carve-plan entries let the ontologist and edge drafter keep structural misfits in the plan. Debates gain a `wrong-structure` challenge type. Minting is gated on one file, `research/structure-review.yaml`, written by the developer's `structure release` act; until it exists `draft finalize` lands the plan and moves the cycle to a new `r4-drafted` status instead of minting. `structure report` reads every plan's friction findings for the review.

**Tech Stack:** the existing `langatlas_research` package (`tools/research/`): Python, pydantic, ruamel.yaml, jsonschema, pytest, `langatlas_commit.land_record`, the prompt registry (`mint_prompt_version`).

**Spec:** [context/decisions.md](../../../context/decisions.md) D70 (ratified 2026-09-19) and [context/brainstorms/65-schema-plasticity-in-the-research-phase.md](../../../context/brainstorms/65-schema-plasticity-in-the-research-phase.md). Parent map: [2026-09-13-stage-3-theme-cycles.md](2026-09-13-stage-3-theme-cycles.md) (sub-plan 3C). Spec detail: [context/spec.md](../../../context/spec.md) §7.4.

## Global Constraints

- Every node is source-backed; priors steer only where to look; agent-generated text is never citable (D4). The D24 verification gate stays the admissibility authority (D1/D4).
- Every agent chat is logged through `RunContext` (D18); fetched or corpus text is data, never instructions (D31).
- The developer signs off every cycle before it runs (D27); nothing in this plan bypasses `require_sign_off`.
- Claude does judgment work; the university API does volume (D6). This plan adds no new model calls of either kind.
- **The structure is provisional, the process is fixed** (D70): the layers, the concept/feature split, `realizes`, the edge types, the dimension model and the seed qualities may change at the structure review; sourcing and process invariants may not.
- The structure review's decision authority is ontology structure only. Every friction finding carries an `area` (`ontology` | `adjacent`); `adjacent` ones are listed for case-by-case decisions, never acted on by the review automatically (D70).
- Model ids and aliases are configuration, never hardcoded.
- Commit messages use `feat(#stage-3g): …` / `test(#stage-3g): …` (the branch name has no issue number of more than three digits). **Per the developer's standing rule, stop after every commit and let them review before continuing.** Commit this plan file before the first implementation commit, and check its boxes in the same commit as the step they belong to.
- Run tests from the repo root with `uv --directory tools/research run pytest -q <path>`.

---

## File structure

| File | Change | Responsibility |
|---|---|---|
| `tools/research/src/langatlas_research/draft/findings.py` | create | The finding vocabulary the R4 roles share, incl. `structure-friction` |
| `tools/research/src/langatlas_research/draft/structure.py` | create | `Misfit`, `is_blocked`, `block_entries`, `synthesize_friction` |
| `tools/research/src/langatlas_research/structure_review.py` | create | The mint gate and the developer's release act; friction report |
| `tools/research/src/langatlas_research/draft/ontologist.py` | modify | Shape check returns misfits; `plan_store_view` |
| `tools/research/src/langatlas_research/draft/edges.py` | modify | Concept endpoints become misfits when collecting; friction |
| `tools/research/src/langatlas_research/draft/{contested,gate,minting,finalize,debate,debate_record}.py` | modify | Blocked carves are skipped; draft finalize; `wrong-structure` |
| `tools/research/src/langatlas_research/{cycle,cli,errors,paths,schema}.py` | modify | `r4-drafted` status; new commands; `MintHeld`; schema check |
| `tools/research/src/langatlas_research/consolidate/cross_theme.py` | modify | Findings dump via the shared model |
| `research/schema/{draft,debate,cycle}.schema.json` | modify | New enum members and fields |
| `research/schema/structure-review.schema.json` | create | The review record |
| `prompts/r4-{ontologist,edge-drafter,challenger,moderator}/` | new versions | Tell the roles the structure is provisional |
| `tools/research/tests/…`, `docs/runbooks/theme-cycle.md`, `context/spec.md` | modify/create | Tests and docs |

---

### Task 1: The `structure-friction` finding vocabulary

**Files:**
- Create: `tools/research/src/langatlas_research/draft/findings.py`
- Modify: `tools/research/src/langatlas_research/draft/ontologist.py:68-72,78,232`
- Modify: `tools/research/src/langatlas_research/draft/edges.py:76-80,87,236-237`
- Modify: `tools/research/src/langatlas_research/consolidate/cross_theme.py:167-168`
- Modify: `research/schema/draft.schema.json` (the `findings` block, last property)
- Test: `tools/research/tests/test_draft_findings.py`

**Interfaces:**
- Produces:
  - `FindingOut` (pydantic): `kind`, `detail`, `keys`, `area: "ontology"|"adjacent"|None`, `element: <STRUCTURE_ELEMENTS member>|None`; `.as_entry() -> dict` (no `None` values).
  - `friction_entry(detail: str, *, keys, element: str, area: str = "ontology") -> dict`.
  - Constants `FINDING_KINDS`, `STRUCTURE_ELEMENTS`, `STRUCTURE_AREAS`.

- [x] **Step 1: Write the failing tests**

```python
# tools/research/tests/test_draft_findings.py
import pytest
from pydantic import ValidationError

from langatlas_research.draft.findings import (
    FindingOut, STRUCTURE_ELEMENTS, friction_entry,
)
from langatlas_research.draft.plan import build_plan_record
from langatlas_research.schema import validate_research_record


def test_a_friction_finding_must_name_its_area_and_element():
    with pytest.raises(ValidationError):
        FindingOut(kind="structure-friction", detail="no slot for refinement")
    with pytest.raises(ValidationError):
        FindingOut(kind="structure-friction", detail="d", area="ontology")


def test_only_a_friction_finding_may_carry_area_or_element():
    with pytest.raises(ValidationError):
        FindingOut(kind="rule-candidate", detail="d", area="ontology")


def test_an_element_outside_the_closed_vocabulary_is_refused():
    with pytest.raises(ValidationError):
        FindingOut(kind="structure-friction", detail="d", area="ontology", element="vibes")


def test_as_entry_drops_unset_fields_so_old_finding_kinds_keep_their_shape():
    old = FindingOut(kind="rule-candidate", detail="d", keys=["a"])
    assert old.as_entry() == {"kind": "rule-candidate", "detail": "d", "keys": ["a"]}


def test_friction_entry_builds_a_valid_finding_dict():
    entry = friction_entry("d", keys=["a"], element="realizes")
    assert entry == {"kind": "structure-friction", "detail": "d", "keys": ["a"],
                     "area": "ontology", "element": "realizes"}
    assert "realizes" in STRUCTURE_ELEMENTS


def test_the_plan_schema_accepts_friction_and_requires_its_classification(
        research_repo, signed_cycle):
    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="r",
                             generated_at="2026-09-20T10:00:00Z")
    plan["findings"] = [friction_entry("d", keys=["a"], element="realizes")]
    assert validate_research_record(plan, "draft", repo_root=research_repo) == []
    plan["findings"] = [{"kind": "structure-friction", "detail": "d", "keys": []}]
    assert validate_research_record(plan, "draft", repo_root=research_repo) != []
```

- [x] **Step 2: Run to verify failure**

Run: `uv --directory tools/research run pytest -q tests/test_draft_findings.py`
Expected: FAIL (`ModuleNotFoundError: langatlas_research.draft.findings`).

- [x] **Step 3: Write `findings.py`**

```python
# tools/research/src/langatlas_research/draft/findings.py
"""The finding vocabulary the R4 roles share (ontologist, edge drafter, R6's cross-theme drafter).

`structure-friction` is the D70 addition: the sign that the seed structure, not the carve, is
what does not fit. It is classified, not free prose, so the structure review can group findings
by the structural element at issue and by whether they concern ontology structure or a
neighbouring ("adjacent") schema."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

FINDING_KINDS = ("rule-candidate", "cross-theme-edge", "unmappable-candidate",
                 "missing-locator-backend", "structure-friction")
STRUCTURE_ELEMENTS = ("layers", "concept-feature-split", "realizes", "edge-types",
                      "dimension-model", "qualities", "record-kinds", "other")
STRUCTURE_AREAS = ("ontology", "adjacent")


class FindingOut(BaseModel):
    kind: Literal[FINDING_KINDS]                    # type: ignore[valid-type]
    detail: str
    keys: list[str] = Field(default_factory=list)
    area: Literal[STRUCTURE_AREAS] | None = None    # type: ignore[valid-type]
    element: Literal[STRUCTURE_ELEMENTS] | None = None   # type: ignore[valid-type]

    @model_validator(mode="after")
    def _only_friction_is_classified(self):
        friction = self.kind == "structure-friction"
        if friction and (self.area is None or self.element is None):
            raise ValueError("a structure-friction finding needs `area` and `element`")
        if not friction and (self.area is not None or self.element is not None):
            raise ValueError("only a structure-friction finding carries `area` / `element`")
        return self

    def as_entry(self) -> dict:
        """The plan-file shape: unset fields are absent, so a finding of an older kind is
        byte-identical to what the plan held before D70."""
        return self.model_dump(exclude_none=True)


def friction_entry(detail: str, *, keys, element: str, area: str = "ontology") -> dict:
    return {"kind": "structure-friction", "detail": detail, "keys": list(keys),
            "area": area, "element": element}
```

- [x] **Step 4: Point the three call sites at the shared model**

In `ontologist.py`: delete `class FindingOut` (lines 68-72), add `from langatlas_research.draft.findings import FindingOut` to the imports, and change the dump at the end of `run_ontologist`:

```python
    plan["findings"] = [finding.as_entry() for finding in out.findings]
```

In `edges.py`: delete `class EdgeFindingOut`, add the import, and keep the old name as an alias so `consolidate/cross_theme.py` and its tests still import it:

```python
from langatlas_research.draft.findings import FindingOut

EdgeFindingOut = FindingOut
```
Change the dump: `*(finding.as_entry() for finding in out.findings)`.

In `consolidate/cross_theme.py:168` change `finding.model_dump()` to `finding.as_entry()`.

- [x] **Step 5: Extend the plan schema's `findings` block**

Replace the `findings` property in `research/schema/draft.schema.json` with:

```json
    "findings": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["kind", "detail"],
        "properties": {
          "kind": { "enum": ["rule-candidate", "cross-theme-edge", "unmappable-candidate",
                             "missing-locator-backend", "structure-friction"] },
          "detail": { "type": "string", "minLength": 1 },
          "keys": { "type": "array", "items": { "type": "string" } },
          "area": { "enum": ["ontology", "adjacent"] },
          "element": { "enum": ["layers", "concept-feature-split", "realizes", "edge-types",
                                "dimension-model", "qualities", "record-kinds", "other"] }
        },
        "allOf": [
          { "if": { "properties": { "kind": { "const": "structure-friction" } },
                    "required": ["kind"] },
            "then": { "required": ["area", "element"] } }
        ]
      }
    }
```

- [x] **Step 6: Run the whole package's tests**

Run: `uv --directory tools/research run pytest -q`
Expected: PASS (the new file plus every existing test; a failure in an existing test means a call site was missed).

- [x] **Step 7: Commit**

```bash
git add docs/superpowers/plans/2026-09-19-stage-3g-structure-plasticity.md \
  tools/research research/schema/draft.schema.json
git commit -m "feat(#stage-3g): add the structure-friction finding kind"
```
Stop for review.

---

### Task 2: The ontologist keeps structural misfits as blocked carves

**Files:**
- Create: `tools/research/src/langatlas_research/draft/structure.py`
- Modify: `tools/research/src/langatlas_research/draft/ontologist.py:133-180,212-243`
- Modify: `research/schema/draft.schema.json` (node items and edge items)
- Modify: `tools/research/tests/test_draft_ontologist.py:115-145` (the two refusal tests)
- Test: `tools/research/tests/test_draft_structure.py`

**Interfaces:**
- Consumes: `friction_entry` (Task 1).
- Produces:
  - `Misfit(key: str, element: str, reason: str)` (frozen dataclass).
  - `BLOCKED = "structure"`; `is_blocked(entry: dict) -> bool`.
  - `block_entries(entries: list[dict], misfits: list[Misfit]) -> list[dict]`.
  - `synthesize_friction(misfits: list[Misfit], findings: list[dict]) -> list[dict]`.
  - `_check_shape(out, store, max_nodes) -> list[Misfit]`: **raises `DraftOutputInvalid` only for hygiene errors**.
  - Plan node and edge entries may carry `blocked: "structure"` and `block_reason: str`.

The split: hygiene errors are defects (invalid slug, duplicate key, re-minting a committed id, node cap exceeded, a `realizes` id that is not a valid slug). Structural misfits are information: a layer outside 1-3, a layer-3 feature with no dimension, an unknown dimension, a `realizes` target that is not a concept, a concept carrying a layer or dimension.

- [x] **Step 1: Write the failing tests**

```python
# tools/research/tests/test_draft_structure.py
from langatlas_research.draft.structure import (
    BLOCKED, Misfit, block_entries, is_blocked, synthesize_friction,
)


def test_block_entries_marks_only_the_misfit_keys_and_joins_reasons():
    entries = [{"key": "a"}, {"key": "b"}]
    blocked = block_entries(entries, [Misfit("b", "realizes", "r1"),
                                      Misfit("b", "layers", "r2")])
    assert blocked[0] == {"key": "a"}
    assert blocked[1] == {"key": "b", "blocked": BLOCKED, "block_reason": "r1; r2"}
    assert is_blocked(blocked[1]) and not is_blocked(blocked[0])


def test_a_misfit_the_model_already_reported_is_not_reported_twice():
    reported = [{"kind": "structure-friction", "detail": "d", "keys": ["b"],
                 "area": "ontology", "element": "realizes"}]
    assert synthesize_friction([Misfit("b", "realizes", "r")], reported) == []


def test_an_unreported_misfit_becomes_one_finding_per_key_and_element():
    found = synthesize_friction([Misfit("b", "realizes", "r1"),
                                 Misfit("b", "realizes", "r1"),
                                 Misfit("b", "layers", "r2")], [])
    assert [(f["keys"], f["element"], f["detail"]) for f in found] == [
        (["b"], "realizes", "r1"), (["b"], "layers", "r2")]
    assert all(f["kind"] == "structure-friction" and f["area"] == "ontology" for f in found)
```

Replace the two refusal tests in `test_draft_ontologist.py` (`test_an_unknown_realizes_target_is_refused`, `test_a_layer_3_node_without_a_dimension_is_refused`) with:

```python
def _run(fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path, out):
    fake_ctx.claude_results.append(_result(out))
    return run_ontologist(fake_ctx, signed_cycle, repo_root=research_repo, survey=SURVEY,
                          lookup=fake_lookup, config=config,
                          prompt=mint_prompt_version("r4-ontologist-test", PROMPT_TEXT,
                                                     root=tmp_path))


def test_realizing_a_feature_blocks_the_carve_instead_of_failing_the_run(
        fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path):
    child = {**OUT["nodes"][1], "key": "child", "id": "child", "name": "Child",
             "from_candidates": [], "realizes": ["static-typing"]}
    plan, _ = _run(fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path,
                   {**OUT, "nodes": [*OUT["nodes"], child]})
    by_key = {node["key"]: node for node in plan["nodes"]}
    assert by_key["child"]["blocked"] == "structure"
    assert "a feature" in by_key["child"]["block_reason"]
    assert "blocked" not in by_key["static-typing"]
    friction = [f for f in plan["findings"] if f["kind"] == "structure-friction"]
    assert friction == [{"kind": "structure-friction", "keys": ["child"],
                         "detail": by_key["child"]["block_reason"],
                         "area": "ontology", "element": "realizes"}]
    assert validate_research_record(plan, "draft", repo_root=research_repo) == []


def test_an_unknown_realizes_target_blocks_the_carve(
        fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path):
    bad = {**OUT, "nodes": [{**OUT["nodes"][1], "realizes": ["no-such-concept"]}]}
    plan, _ = _run(fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path, bad)
    assert plan["nodes"][0]["blocked"] == "structure"
    assert "not a node" in plan["nodes"][0]["block_reason"]


def test_a_layer_3_node_without_a_dimension_blocks_the_carve(
        fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path):
    bad = {**OUT, "nodes": [{**OUT["nodes"][1], "dimension": None}], "dimensions": []}
    plan, _ = _run(fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path, bad)
    node = plan["nodes"][0]
    assert node["blocked"] == "structure"
    assert plan["findings"][-1]["element"] == "dimension-model"
    assert validate_research_record(plan, "draft", repo_root=research_repo) == []


def test_a_layer_outside_the_three_is_stored_without_a_layer_and_blocked(
        fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path):
    bad = {**OUT, "nodes": [{**OUT["nodes"][1], "layer": 4}]}
    plan, _ = _run(fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path, bad)
    assert "layer" not in plan["nodes"][0] and plan["nodes"][0]["blocked"] == "structure"
    assert plan["findings"][-1]["element"] == "layers"
    assert validate_research_record(plan, "draft", repo_root=research_repo) == []


def test_a_model_reported_friction_finding_is_not_duplicated(
        fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path):
    child = {**OUT["nodes"][1], "key": "child", "id": "child", "from_candidates": [],
             "realizes": ["static-typing"]}
    reported = {"kind": "structure-friction", "detail": "features specialise features",
                "keys": ["child"], "area": "ontology", "element": "realizes"}
    plan, _ = _run(fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path,
                   {**OUT, "nodes": [*OUT["nodes"], child],
                    "findings": [*OUT["findings"], reported]})
    assert [f["kind"] for f in plan["findings"]].count("structure-friction") == 1


def test_a_hygiene_error_still_fails_the_run(
        fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path):
    from langatlas_research.errors import DraftOutputInvalid

    twice = {**OUT, "nodes": [OUT["nodes"][0], OUT["nodes"][0]]}
    fake_ctx.claude_results.append(_result(twice))
    with pytest.raises(DraftOutputInvalid, match="appears twice"):
        run_ontologist(fake_ctx, signed_cycle, repo_root=research_repo, survey=SURVEY,
                       lookup=fake_lookup, config=config,
                       prompt=mint_prompt_version("r4-ontologist-test", PROMPT_TEXT,
                                                  root=tmp_path))
```
(`validate_research_record` is already imported in that file.)

- [x] **Step 2: Run to verify failure**

Run: `uv --directory tools/research run pytest -q tests/test_draft_structure.py tests/test_draft_ontologist.py`
Expected: FAIL (`ModuleNotFoundError: …draft.structure`).

- [x] **Step 3: Write `structure.py`**

```python
# tools/research/src/langatlas_research/draft/structure.py
"""Blocked carves: an entry the seed structure cannot hold (D70).

A structural misfit is information about the structure, not a defect in the model's output,
so it stays in the carve plan — evidence and all — flagged `blocked: structure` and linked to a
`structure-friction` finding. A blocked entry is never debated, verified or minted; it waits for
the structure review, after which the batch is re-atomized against the revised structure.
Hygiene errors (invalid slugs, duplicate keys, re-minting a committed id) are defects and still
reject the run — that split lives in each role's shape check, not here."""
from dataclasses import dataclass

from langatlas_research.draft.findings import friction_entry

BLOCKED = "structure"


@dataclass(frozen=True)
class Misfit:
    key: str
    element: str      # a `STRUCTURE_ELEMENTS` member
    reason: str


def is_blocked(entry: dict) -> bool:
    return entry.get("blocked") == BLOCKED


def block_entries(entries: list[dict], misfits: list[Misfit]) -> list[dict]:
    """`entries` with each misfit's entry marked blocked. A key with several misfits keeps
    all its reasons, in the order they were found."""
    reasons: dict[str, list[str]] = {}
    for misfit in misfits:
        reasons.setdefault(misfit.key, []).append(misfit.reason)
    return [{**entry, "blocked": BLOCKED, "block_reason": "; ".join(reasons[entry["key"]])}
            if entry["key"] in reasons else entry
            for entry in entries]


def synthesize_friction(misfits: list[Misfit], findings: list[dict]) -> list[dict]:
    """One `structure-friction` finding per (key, element) the model did not already report.
    A key the model reported friction for is left alone: its own words are the better record."""
    covered = {key for finding in findings if finding.get("kind") == "structure-friction"
               for key in finding.get("keys") or []}
    seen: set[tuple[str, str]] = set()
    made = []
    for misfit in misfits:
        if misfit.key in covered or (misfit.key, misfit.element) in seen:
            continue
        seen.add((misfit.key, misfit.element))
        made.append(friction_entry(misfit.reason, keys=[misfit.key], element=misfit.element))
    return made
```

- [x] **Step 4: Rewrite `_check_shape` in `ontologist.py`**

Add imports `from langatlas_research.draft.structure import Misfit, block_entries, synthesize_friction`. Replace `_check_shape` (currently lines 133-180) with:

```python
def _check_shape(out: OntologistOut, store: StoreView, max_nodes: int) -> list[Misfit]:
    """Hygiene errors raise, all at once, so the developer reads one message. Structural
    misfits (D70) are returned: the seed structure may be what is wrong, so the carve is kept.

    @raises DraftOutputInvalid: invalid slugs, duplicate keys, a committed id re-minted, or
        more nodes than the configured cap."""
    errors: list[str] = []
    misfits: list[Misfit] = []
    if len(out.nodes) > max_nodes:
        errors.append(f"{len(out.nodes)} nodes exceeds the configured cap of {max_nodes}")

    proposed_dimensions = {d.slug for d in out.dimensions}
    known_dimensions = proposed_dimensions | store.dimensions
    concept_ids = {n.id for n in out.nodes if n.kind == "concept"} | store.concepts
    feature_ids = {n.id for n in out.nodes if n.kind == "feature"} | store.features
    keys: set[str] = set()

    for dimension in out.dimensions:
        for slug in (dimension.key, dimension.slug):
            if not is_valid_slug(slug):
                errors.append(f"dimension {dimension.slug}: {slug!r} is not a valid slug")
        if dimension.slug in store.dimensions:
            errors.append(f"dimension {dimension.slug!r} is already committed; changing an"
                          f" existing dimension is a restructure, not a mint")
        if dimension.key in keys:
            errors.append(f"key {dimension.key!r} appears twice")
        keys.add(dimension.key)

    for node in out.nodes:
        if not is_valid_slug(node.key) or not is_valid_slug(node.id):
            errors.append(f"node {node.key!r}/{node.id!r}: not a valid slug (§3.5)")
        if node.key in keys:
            errors.append(f"key {node.key!r} appears twice")
        keys.add(node.key)
        if node.id in store.nodes:
            errors.append(f"node {node.id!r} is already committed; extend or point at it"
                          f" instead of re-minting it")
        if node.kind == "feature":
            if node.layer not in (1, 2, 3):
                misfits.append(Misfit(node.key, "layers",
                                      f"layer {node.layer!r} is not one of the three layers"))
            elif node.layer == 3 and not node.dimension:
                misfits.append(Misfit(node.key, "dimension-model",
                                      "a layer-3 feature names no dimension"))
            if node.dimension and node.dimension not in known_dimensions:
                misfits.append(Misfit(node.key, "dimension-model",
                                      f"dimension {node.dimension!r} is neither committed"
                                      f" nor proposed in this run"))
            for concept_id in node.realizes:
                if not is_valid_slug(concept_id):
                    errors.append(f"node {node.key}: realizes {concept_id!r}, not a valid slug")
                elif concept_id not in concept_ids:
                    what = "a feature" if concept_id in feature_ids else "not a node"
                    misfits.append(Misfit(node.key, "realizes",
                                          f"realizes {concept_id!r}, which is {what};"
                                          f" `realizes` may only name a concept"))
        elif node.layer is not None or node.dimension:
            misfits.append(Misfit(node.key, "concept-feature-split",
                                  "a concept has no layer or dimension"))
    if errors:
        raise DraftOutputInvalid(f"{ONTOLOGIST_PROMPT_ID}: " + "; ".join(errors))
    return misfits
```

In `run_ontologist`: call `misfits = _check_shape(out, store, role.max_candidates)`; in the feature branch build the entry with the layer only when it is one of the three:

```python
        if node.kind == "feature":
            entry.update({"dimension": node.dimension, "cross_cutting": node.cross_cutting,
                          "aliases": list(node.aliases), "realizes": list(node.realizes)})
            if node.layer in (1, 2, 3):
                entry["layer"] = node.layer
```
and replace the findings line with:

```python
    plan["nodes"] = block_entries(plan["nodes"], misfits)
    plan["findings"] = [finding.as_entry() for finding in out.findings]
    plan["findings"] += synthesize_friction(misfits, plan["findings"])
```
Update the module docstring's "fails the run" sentence to say misfits are kept and blocked (D70).

- [x] **Step 5: Add `blocked` / `block_reason` to the plan schema**

In `research/schema/draft.schema.json`, in the `properties` of the **`nodes`** items and of the **`edges`** items only (each already has `"waiver"`), add beside `"waiver"`:

```json
          "blocked": { "enum": ["structure"] },
          "block_reason": { "type": "string", "minLength": 1 },
```
Run `grep -n '"waiver"' research/schema/draft.schema.json` to find the four `waiver` sites (dimensions, qualities, nodes, edges, quality_edges use `$defs/tail` or their own); edit nodes and edges.

- [x] **Step 6: Run the tests**

Run: `uv --directory tools/research run pytest -q tests/test_draft_structure.py tests/test_draft_ontologist.py tests/test_draft_plan.py`
Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add tools/research research/schema/draft.schema.json
git commit -m "feat(#stage-3g): keep structural misfits in the carve plan as blocked carves"
```
Stop for review.

---

### Task 3: The edge drafter keeps structural misfits; edges can be drafted against a carve plan

**Files:**
- Modify: `tools/research/src/langatlas_research/draft/edges.py:106-150,182-246`
- Modify: `tools/research/src/langatlas_research/draft/ontologist.py` (add `plan_store_view`)
- Test: `tools/research/tests/test_draft_edges.py` (append)

**Interfaces:**
- Consumes: `Misfit`, `is_blocked`, `BLOCKED`, `synthesize_friction` (Task 2).
- Produces:
  - `check_shape(out, store, known_qualities, max_edges, *, collect_misfits: bool = False) -> dict[int, str]`. With the default `False` nothing changes: a concept endpoint raises, as before, so R6's cross-theme pass keeps its strict behaviour. With `True` a concept endpoint is returned as `{index into out.edges: reason}`.
  - `plan_store_view(store: StoreView, plan: dict) -> StoreView`: the store plus the plan's unblocked, undropped nodes.
  - Edge plan entries may carry `blocked` / `block_reason`.

- [x] **Step 1: Write the failing tests**

```python
# appended to tools/research/tests/test_draft_edges.py
import pytest as _pytest

from langatlas_research.draft.edges import EdgeDrafterOut, check_shape
from langatlas_research.draft.ontologist import StoreView, plan_store_view
from langatlas_research.errors import DraftOutputInvalid as _Invalid


def _edges(*pairs):
    return EdgeDrafterOut.model_validate({"edges": [
        {"type": "requires", "from": frm, "to": to, "statement": "s",
         "evidence": [{"chunk_id": "x#c1"}]} for frm, to in pairs]})


def _view(concepts=(), features=()):
    return StoreView(concepts=frozenset(concepts), features=frozenset(features),
                     dimensions=frozenset())


def test_a_concept_endpoint_still_raises_by_default():
    with _pytest.raises(_Invalid, match="is a concept"):
        check_shape(_edges(("a", "c")), _view(concepts=["c"], features=["a"]), set(), 10)


def test_a_concept_endpoint_is_a_misfit_when_collecting():
    misfits = check_shape(_edges(("a", "b"), ("a", "c")),
                          _view(concepts=["c"], features=["a", "b"]), set(), 10,
                          collect_misfits=True)
    assert list(misfits) == [1] and "is a concept" in misfits[1]


def test_an_endpoint_that_exists_nowhere_is_a_hygiene_error_even_when_collecting():
    with _pytest.raises(_Invalid, match="not a committed node"):
        check_shape(_edges(("a", "ghost")), _view(features=["a"]), set(), 10,
                    collect_misfits=True)


def test_the_plan_store_view_adds_unblocked_undropped_plan_nodes():
    plan = {"nodes": [
        {"key": "c1", "id": "c1", "kind": "concept", "status": "verified"},
        {"key": "f1", "id": "f1", "kind": "feature", "status": "proposed"},
        {"key": "f2", "id": "f2", "kind": "feature", "status": "dropped"},
        {"key": "f3", "id": "f3", "kind": "feature", "status": "proposed",
         "blocked": "structure", "block_reason": "r"}]}
    view = plan_store_view(_view(features=["old"]), plan)
    assert view.concepts == {"c1"} and view.features == {"old", "f1"}
```

- [x] **Step 2: Run to verify failure**

Run: `uv --directory tools/research run pytest -q tests/test_draft_edges.py`
Expected: FAIL (`ImportError: plan_store_view` / unexpected keyword `collect_misfits`).

- [x] **Step 3: Implement**

In `ontologist.py`, below `read_store`:

```python
def plan_store_view(store: StoreView, plan: dict) -> StoreView:
    """The store plus the carve plan's own live nodes, for drafting edges while nothing is
    minted yet (D70's draft-only batch). A blocked or dropped carve is not an endpoint: it is
    waiting on the structure review or gone."""
    from langatlas_research.draft.structure import is_blocked

    concepts, features = set(store.concepts), set(store.features)
    for entry in plan.get("nodes") or []:
        if is_blocked(entry) or entry["status"] == "dropped":
            continue
        (concepts if entry["kind"] == "concept" else features).add(entry["id"])
    return StoreView(concepts=frozenset(concepts), features=frozenset(features),
                     dimensions=store.dimensions)
```

In `edges.py` change `check_shape`'s signature and edge loop:

```python
def check_shape(out: EdgeDrafterOut, store, known_qualities: set[str], max_edges: int,
                *, collect_misfits: bool = False) -> dict[int, str]:
    """... With `collect_misfits`, an edge that touches a concept is returned as
    `{index into out.edges: reason}` instead of raising (D70: a missing edge type is
    information about the structure). Everything else stays a hygiene error."""
    errors: list[str] = []
    misfits: dict[int, list[str]] = {}
```
and inside the edge loop, replace `for edge in out.edges:` with `for index, edge in enumerate(out.edges):` and the concept branch with:

```python
            if endpoint in store.concepts:
                message = (f"{edge.type} {edge.frm}->{edge.to}: {endpoint!r} is a concept;"
                           f" §3.1's edge types connect features")
                if collect_misfits:
                    misfits.setdefault(index, []).append(message)
                else:
                    errors.append(message)
```
At the end of the function:

```python
    if errors:
        raise DraftOutputInvalid(f"{EDGE_DRAFTER_PROMPT_ID}: " + "; ".join(errors))
    return {index: "; ".join(reasons) for index, reasons in misfits.items()}
```

In `run_edge_drafter`: import `BLOCKED, Misfit, synthesize_friction` from `draft.structure`; call `misfits = check_shape(out, store, known_qualities, role.max_candidates, collect_misfits=True)`; after `updated, edge_warnings = append_edges(...)` add:

```python
    base = len(updated["edges"]) - len(out.edges)
    edge_misfits = []
    if misfits:
        edges = list(updated["edges"])
        for index, reason in misfits.items():
            edges[base + index] = {**edges[base + index], "blocked": BLOCKED,
                                   "block_reason": reason}
            edge_misfits.append(Misfit(edges[base + index]["key"], "edge-types", reason))
        updated["edges"] = edges
```
and replace the findings assembly with:

```python
    findings = [*(plan.get("findings") or []), *(f.as_entry() for f in out.findings)]
    updated["findings"] = [*findings, *synthesize_friction(edge_misfits, findings)]
```

- [x] **Step 4: Run the tests**

Run: `uv --directory tools/research run pytest -q tests/test_draft_edges.py tests/test_consolidate_cross_theme.py`
Expected: PASS (the cross-theme tests prove R6 kept its strict default).

- [x] **Step 5: Commit**

```bash
git add tools/research
git commit -m "feat(#stage-3g): keep edge misfits as blocked edges and draft against a carve plan"
```
Stop for review.

---

### Task 4: Blocked carves are skipped downstream; the developer can drop a carve

**Files:**
- Modify: `tools/research/src/langatlas_research/draft/contested.py:41-84,102-108` (+ new `drop`)
- Modify: `tools/research/src/langatlas_research/draft/gate.py:138-144`
- Modify: `tools/research/src/langatlas_research/draft/minting.py:_mintable`
- Modify: `tools/research/src/langatlas_research/draft/finalize.py:r4_blockers`
- Modify: `tools/research/src/langatlas_research/cli.py` (`draft drop`)
- Test: `tools/research/tests/test_draft_structure.py` (append), `tests/test_draft_cli.py` (append)

**Interfaces:**
- Consumes: `is_blocked` (Task 2).
- Produces:
  - `gate._ready(entry: dict) -> bool` (extracted predicate; blocked entries are never ready).
  - `contested.drop(plan: dict, key: str, reason: str) -> dict` (`@raises ValueError` for a minted entry or a blank reason; `KeyError` for an unknown key).
  - `langatlas-research draft drop N KEY --reason "…"`.

A blocked carve is never debated (no triggers), never verified, never minted, and `finalize_r4` (the mint-mode finalize) reports it as a blocker so a plan with a stuck carve cannot reach `r4-done` silently. `draft drop` is the developer's way out of a carve the revised structure still cannot hold.

- [x] **Step 1: Write the failing tests**

```python
# appended to tools/research/tests/test_draft_structure.py
import pytest

from langatlas_research.draft.contested import contested_triggers, drop, open_carves
from langatlas_research.draft.finalize import r4_blockers
from langatlas_research.draft.gate import _ready
from langatlas_research.draft.minting import _mintable


def _entry(**over):
    return {"key": "child", "from_candidates": ["child"], "kind": "feature", "id": "child",
            "name": "Child", "summary": "s", "layer": 2, "dimension": None,
            "evidence": [{"source": "a", "locator": "§1"}],
            "contested": [], "debate_id": None, "status": "proposed",
            "verification": None, "note": "", **over}


BLOCKED_ENTRY = {"blocked": "structure", "block_reason": "realizes a feature"}


def test_a_blocked_carve_is_never_contested_so_never_debated():
    plan = {"dimensions": [], "qualities": [], "edges": [], "quality_edges": [],
            "nodes": [_entry(**BLOCKED_ENTRY, contested=["ontologist-flagged"])]}
    assert contested_triggers(plan, store=_Store()) == {}
    assert open_carves(plan) == []


class _Store:
    nodes = frozenset()


def test_a_blocked_carve_is_not_ready_for_the_gate_and_never_mints():
    assert _ready(_entry()) is True
    assert _ready(_entry(**BLOCKED_ENTRY)) is False
    assert _mintable("nodes", _entry(**BLOCKED_ENTRY, status="verified")) is False


def test_a_blocked_carve_blocks_the_mint_mode_finalize(research_repo, signed_cycle):
    from langatlas_research.draft.plan import build_plan_record

    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="r", generated_at="t")
    plan["nodes"] = [_entry(**BLOCKED_ENTRY)]
    assert any("blocked" in b and "structure review" in b
               for b in r4_blockers(signed_cycle, plan, repo_root=research_repo))


def test_drop_marks_a_carve_dropped_with_the_reason():
    plan = {"dimensions": [], "qualities": [], "edges": [], "quality_edges": [],
            "nodes": [_entry(**BLOCKED_ENTRY)]}
    dropped = drop(plan, "child", "the revised structure still has no slot for it")
    assert dropped["nodes"][0]["status"] == "dropped"
    assert dropped["nodes"][0]["drop_reason"].startswith("the revised structure")


def test_drop_refuses_a_minted_carve_and_a_blank_reason():
    plan = {"dimensions": [], "qualities": [], "edges": [], "quality_edges": [],
            "nodes": [_entry(status="minted")]}
    with pytest.raises(ValueError, match="minted"):
        drop(plan, "child", "why")
    plan["nodes"][0]["status"] = "proposed"
    with pytest.raises(ValueError, match="reason"):
        drop(plan, "child", "  ")
```
Append to `tests/test_draft_cli.py`:

```python
def test_draft_drop_records_the_reason(research_repo, signed_cycle, capsys):
    _plan(signed_cycle, research_repo, [_node()])
    assert main(["--repo-root", str(research_repo), "draft", "drop", "1", "type-system",
                 "--reason", "no slot in the revised structure"]) == 0
    entry = load_plan(signed_cycle.slug, repo_root=research_repo)["nodes"][0]
    assert entry["status"] == "dropped" and "no slot" in entry["drop_reason"]
```

- [x] **Step 2: Run to verify failure**

Run: `uv --directory tools/research run pytest -q tests/test_draft_structure.py tests/test_draft_cli.py`
Expected: FAIL (`ImportError: drop` / `_ready`).

- [x] **Step 3: Implement**

`contested.py`: import `from langatlas_research.draft.structure import is_blocked`. In `contested_triggers`, right after the terminal-status skip add `if is_blocked(entry): continue`. In `open_carves` add `and not is_blocked(entry)` to the condition. Append:

```python
def drop(plan: dict, key: str, reason: str) -> dict:
    """The developer's way out of a carve that cannot be minted — for a blocked carve, one the
    revised structure still has no slot for. Never called by an agent.

    @raises KeyError: no entry with this key.
    @raises ValueError: the entry is already minted, or `reason` is blank."""
    _name, entry = find_entry(plan, key)
    if entry["status"] == "minted":
        raise ValueError(f"{key} is minted; git already holds it")
    if not reason.strip():
        raise ValueError("a drop needs a reason")
    return set_entry(plan, key, status="dropped", drop_reason=reason.strip())
```

`gate.py`: import `is_blocked` and extract the predicate; `verify_plan` uses it:

```python
def _ready(entry: dict) -> bool:
    """A blocked carve waits for the structure review (D70); one still waiting on a debate is
    simply not ready, and stamping a verdict on it would hide that."""
    if is_blocked(entry):
        return False
    return entry["status"] in ("debated", "waived") or (
        entry["status"] == "proposed" and not entry.get("contested"))
```
and in the loop replace the `ready = …` / `if not ready: continue` lines with `if not _ready(entry): continue`.

`minting.py` `_mintable`: first statement `if is_blocked(entry): return False` (import from `draft.structure`).

`finalize.py` `r4_blockers`: at the top of the entry loop, after the `_TERMINAL` skip:

```python
        if is_blocked(entry):
            blockers.append(f"{entry['key']}: blocked by the seed structure"
                            f" ({entry['block_reason']}) — resolve at the structure review,"
                            f" or `draft drop` it")
            continue
```

`cli.py`: add the parser next to `waive`:

```python
    p_drop = p_draft.add_parser("drop", help="developer: drop a carve that cannot be minted")
    p_drop.add_argument("number", type=int)
    p_drop.add_argument("key")
    p_drop.add_argument("--reason", required=True)
```
and in `_dispatch_draft` (offline, beside `waive`):

```python
    if args.draft_command == "drop":
        from langatlas_research.draft.contested import drop

        plan = load_plan(cycle.slug, repo_root=repo)
        try:
            save_plan(drop(plan, args.key, args.reason), repo_root=repo)
        except (KeyError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"dropped {args.key} ({cycle.slug}): {args.reason}")
        return 0
```

- [x] **Step 4: Run the package tests**

Run: `uv --directory tools/research run pytest -q`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add tools/research
git commit -m "feat(#stage-3g): skip blocked carves downstream and add draft drop"
```
Stop for review.

---

### Task 5: The mint gate, the `r4-drafted` status and the draft-only finalize

**Files:**
- Create: `tools/research/src/langatlas_research/structure_review.py`
- Create: `research/schema/structure-review.schema.json`
- Modify: `tools/research/src/langatlas_research/{errors,paths,cycle,schema,cli}.py`
- Modify: `tools/research/src/langatlas_research/draft/{minting,finalize}.py`
- Modify: `research/schema/cycle.schema.json` (status enum)
- Modify: `tools/research/tests/conftest.py` (open the gate in the two repo fixtures)
- Test: `tools/research/tests/test_structure_review.py`, `tests/test_cycle.py`, `tests/test_draft_finalize.py`, `tests/test_draft_cli.py`

**Interfaces:**
- Produces:
  - `errors.MintHeld(ResearchError)`, `errors.StructureReviewRefused(ResearchError)`.
  - `paths.structure_review_path(repo_root=None) -> Path` = `research/structure-review.yaml`.
  - `CYCLE_STATUSES = ("drafted", "signed-off", "r3-done", "r4-drafted", "r4-done", "r5-done", "settled")`.
  - `structure_review.mint_open(repo_root=None) -> bool`; `require_mint_open(repo_root=None) -> None` (`@raises MintHeld`); `drafted_cycles(repo_root=None) -> list[int]`; `release_structure_review(*, by, date, summary, repo_root=None) -> Path` (`@raises StructureReviewRefused`).
  - `finalize.r4_draft_blockers(cycle, plan, *, repo_root) -> list[str]`; `finalize.finalize_r4_draft(cycle_number, *, repo_root, status_checker=None, lander=land_record) -> tuple[Cycle, list]`.
  - `mint_plan` raises `MintHeld` while the gate is closed.

The gate is a single file: while `research/structure-review.yaml` does not exist, no cycle mints and `draft finalize` lands the plan and moves the cycle to `r4-drafted`. Writing the file is the developer's `structure release` act (Task 8), so the first four cycles are held by default and later cycles mint normally.

- [ ] **Step 1: Write the failing tests**

```python
# tools/research/tests/test_structure_review.py
import pytest

from langatlas_research.cycle import advance, save_cycle
from langatlas_research.errors import MintHeld, StructureReviewRefused
from langatlas_research.paths import structure_review_path
from langatlas_research.schema import validate_research_record
from langatlas_research.structure_review import (
    drafted_cycles, mint_open, release_structure_review, require_mint_open,
)


@pytest.fixture
def closed_repo(research_repo):
    structure_review_path(research_repo).unlink()
    return research_repo


def test_the_gate_is_closed_until_a_review_is_recorded(closed_repo):
    assert mint_open(closed_repo) is False
    with pytest.raises(MintHeld, match="structure review"):
        require_mint_open(closed_repo)


def test_release_needs_at_least_one_drafted_cycle(closed_repo, signed_cycle):
    with pytest.raises(StructureReviewRefused, match="no cycle is at r4-drafted"):
        release_structure_review(by="Michal", date="2026-09-25", summary="s",
                                 repo_root=closed_repo)


def test_release_records_the_batch_and_opens_the_gate(closed_repo, signed_cycle):
    cycle = advance(advance(signed_cycle, "r3-done"), "r4-drafted")
    save_cycle(cycle, repo_root=closed_repo)
    assert drafted_cycles(closed_repo) == [1]
    path = release_structure_review(by="Michal", date="2026-09-25",
                                    summary="added a specialises edge type",
                                    repo_root=closed_repo)
    assert mint_open(closed_repo) is True
    from ruamel.yaml import YAML

    data = YAML(typ="safe").load(path.read_text())
    assert data["batch"] == [1] and data["reviewed_by"] == "Michal"
    assert validate_research_record(data, "structure-review", repo_root=closed_repo) == []


def test_a_review_is_recorded_once(closed_repo, signed_cycle):
    save_cycle(advance(advance(signed_cycle, "r3-done"), "r4-drafted"),
               repo_root=closed_repo)
    release_structure_review(by="M", date="d", summary="s", repo_root=closed_repo)
    with pytest.raises(StructureReviewRefused, match="already recorded"):
        release_structure_review(by="M", date="d", summary="s", repo_root=closed_repo)


def test_a_blank_summary_is_refused(closed_repo, signed_cycle):
    save_cycle(advance(advance(signed_cycle, "r3-done"), "r4-drafted"),
               repo_root=closed_repo)
    with pytest.raises(StructureReviewRefused, match="summary"):
        release_structure_review(by="M", date=" ", summary=" ", repo_root=closed_repo)
```
Append to `tests/test_cycle.py`:

```python
def test_r4_drafted_sits_between_r3_done_and_r4_done(repo):
    from langatlas_research.cycle import CYCLE_STATUSES, advance, new_cycle

    assert CYCLE_STATUSES.index("r3-done") < CYCLE_STATUSES.index("r4-drafted") \
        < CYCLE_STATUSES.index("r4-done")
    cycle = advance(advance(new_cycle(1, "typing", repo_root=repo), "r3-done"), "r4-drafted")
    assert advance(cycle, "r4-done").status == "r4-done"
    with pytest.raises(InvalidTransition):
        advance(cycle, "r3-done")
```
(use the imports already at the top of `test_cycle.py`; add `InvalidTransition` from `langatlas_research.errors` if absent).

Append to `tests/test_draft_finalize.py`:

```python
from langatlas_research.draft.finalize import finalize_r4_draft, r4_draft_blockers


def test_a_blocked_carve_does_not_block_the_draft_finalize(research_repo, r3_done):
    blocked = _node(key="child", id="child", kind="feature", layer=2, status="proposed",
                    verification=None, blocked="structure", block_reason="realizes a feature")
    plan = _saved_plan(r3_done, research_repo, [_node(status="verified"), blocked])
    assert r4_draft_blockers(r3_done, plan, repo_root=research_repo) == []


def test_an_unverified_live_carve_blocks_the_draft_finalize(research_repo, r3_done):
    plan = _saved_plan(r3_done, research_repo,
                       [_node(status="proposed", verification=None)])
    assert any("never reached the verifier" in b
               for b in r4_draft_blockers(r3_done, plan, repo_root=research_repo))


def test_an_unlanded_verified_carve_is_fine_while_drafting(research_repo, r3_done):
    plan = _saved_plan(r3_done, research_repo, [_node(status="verified")])
    assert r4_draft_blockers(r3_done, plan, repo_root=research_repo) == []


def test_draft_finalize_lands_the_plan_and_moves_the_cycle_to_r4_drafted(
        research_repo, r3_done):
    _saved_plan(r3_done, research_repo, [_node(status="verified")])
    landed = []

    def _lander(repo_root, path, content, *, chat_run_id, validator, status_checker=None):
        landed.append(path)
        return Landed(commit_sha="abc1234")

    cycle, _ = finalize_r4_draft(r3_done.number, repo_root=research_repo, lander=_lander)
    assert cycle.status == "r4-drafted"
    assert landed == [f"research/drafts/{r3_done.slug}.yaml",
                      f"research/cycles/{r3_done.slug}.yaml"]
    assert load_cycle(r3_done.number, repo_root=research_repo).status == "r4-drafted"
    # ...and the same cycle can still close R4 for real once the gate opens.
    plan = _saved_plan(cycle, research_repo, [_node()])
    final, _ = finalize_r4(cycle.number, repo_root=research_repo, lander=_lander)
    assert final.status == "r4-done"
```
Append to `tests/test_draft_cli.py`:

```python
def test_draft_mint_is_held_until_a_structure_review(research_repo, signed_cycle, capsys):
    from langatlas_research.paths import structure_review_path

    structure_review_path(research_repo).unlink()
    _plan(signed_cycle, research_repo, [_node()])
    assert main(["--repo-root", str(research_repo), "draft", "mint", "1"]) == 1
    assert "structure review" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify failure**

Run: `uv --directory tools/research run pytest -q tests/test_structure_review.py tests/test_cycle.py tests/test_draft_finalize.py tests/test_draft_cli.py`
Expected: FAIL (missing module / status).

- [ ] **Step 3: Implement the plumbing**

`errors.py` (append):

```python
class MintHeld(ResearchError):
    """D70: nothing mints until the developer has recorded the structure review
    (`langatlas-research structure release`). Drafting, debating and verifying still run."""


class StructureReviewRefused(ResearchError):
    """`structure release` cannot record the review: none is due, one is already recorded, or
    the record would be blank."""
```
`paths.py` (append):

```python
def structure_review_path(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "structure-review.yaml"
```
`cycle.py`: `CYCLE_STATUSES = ("drafted", "signed-off", "r3-done", "r4-drafted", "r4-done", "r5-done", "settled")`. `research/schema/cycle.schema.json`: add `"r4-drafted"` between `"r3-done"` and `"r4-done"` in the status enum.

`research/schema/structure-review.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://langatlas.dev/research-schema/structure-review",
  "type": "object",
  "additionalProperties": false,
  "required": ["reviewed_by", "date", "summary", "batch"],
  "properties": {
    "reviewed_by": { "type": "string", "minLength": 1 },
    "date": { "type": "string", "minLength": 1 },
    "summary": { "type": "string", "minLength": 1 },
    "batch": { "type": "array", "minItems": 1, "items": { "type": "integer", "minimum": 1 } }
  }
}
```
`schema.py` `validate_research_tree`: after the themes block add

```python
    review = root / "structure-review.yaml"
    if review.exists():
        errors.extend(f"research/structure-review.yaml: {e}" for e in validate_research_record(
            _yaml.load(review.read_text()) or {}, "structure-review", repo_root=repo_root))
```

`structure_review.py`:

```python
"""D70's structure review: the one developer act that opens minting.

The gate is a file, not a flag on a cycle, because the decision is about the *ontology*: the
structure the first cycles' carves were drafted against is either confirmed or revised, once, for
the whole batch. Until `research/structure-review.yaml` exists no cycle mints, and `draft
finalize` lands the carve plan and moves the cycle to `r4-drafted` instead. Later cycles find the
file already there and mint per cycle as the runbook always described."""
import io
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.cycle import load_cycle
from langatlas_research.errors import MintHeld, StructureReviewRefused
from langatlas_research.paths import cycles_dir, structure_review_path
from langatlas_research.schema import validate_research_record


def mint_open(repo_root: Path | None = None) -> bool:
    return structure_review_path(repo_root).exists()


def require_mint_open(repo_root: Path | None = None) -> None:
    """@raises MintHeld: no structure review is recorded yet."""
    if not mint_open(repo_root):
        raise MintHeld(
            "minting is held until the structure review (D70): finish the draft-only batch,"
            " read `langatlas-research structure report`, decide the schema changes, then run"
            " `langatlas-research structure release`")


def drafted_cycles(repo_root: Path | None = None) -> list[int]:
    numbers = (int(path.name[:2]) for path in cycles_dir(repo_root).glob("[0-9][0-9]-*.yaml"))
    return sorted(n for n in numbers
                  if load_cycle(n, repo_root=repo_root).status == "r4-drafted")


def release_structure_review(*, by: str, date: str, summary: str,
                             repo_root: Path | None = None) -> Path:
    """Records the review and opens the gate. The batch is every cycle at `r4-drafted`: they are
    the carve plans the review looked at, and the ones to re-atomize.

    @raises StructureReviewRefused: a review is already recorded, no cycle is at r4-drafted,
        or `by` / `date` / `summary` is blank."""
    path = structure_review_path(repo_root)
    if path.exists():
        raise StructureReviewRefused(f"a structure review is already recorded ({path.name})")
    if not (by.strip() and date.strip() and summary.strip()):
        raise StructureReviewRefused("a review needs who, when, and a summary of the decisions")
    batch = drafted_cycles(repo_root)
    if not batch:
        raise StructureReviewRefused("no cycle is at r4-drafted: there is no draft-only batch"
                                     " to review")
    data = {"reviewed_by": by.strip(), "date": date.strip(), "summary": summary.strip(),
            "batch": batch}
    errors = validate_research_record(data, "structure-review", repo_root=repo_root)
    if errors:
        raise StructureReviewRefused("; ".join(errors))
    yaml = YAML()
    yaml.width = 100
    buf = io.StringIO()
    yaml.dump(data, buf)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buf.getvalue())
    return path
```

`minting.py` `mint_plan`: first statement `require_mint_open(repo_root)` (import inside the function: `from langatlas_research.structure_review import require_mint_open`; `mint_plan` already has `repo_root`).

`finalize.py`: extract the landing tail of `finalize_r4` into `_land_plan` and add the draft variant:

```python
_GATED_LISTS = ("nodes", "edges", "quality_edges")


def r4_draft_blockers(cycle: Cycle, plan: dict, *, repo_root: Path | None) -> list[str]:
    """What stops a *draft-only* R4 from closing (D70). Debates must be done and every live
    carve must have reached the verifier — verification does not depend on the structure, so
    it runs during the draft — but nothing has to be minted, and a blocked carve is the point
    of the batch, not a blocker."""
    blockers = [f"schema: {error}" for error in
                validate_research_record(plan, "draft", repo_root=repo_root)]
    if plan.get("theme_digest") != cycle.signed_off["theme_digest"]:
        blockers.append("the carve plan predates the current sign-off: re-run"
                        " `draft atomize`")
    if not any(True for _name, _entry in entries(plan)):
        blockers.append("the carve plan has no entries at all")
    for key in open_carves(plan):
        blockers.append(f"{key}: contested with no debate and no waiver — run"
                        f" `draft debate` or `draft waive`")
    for name, entry in entries(plan):
        if entry["status"] in _TERMINAL or is_blocked(entry):
            continue
        if entry.get("debate_id") and entry["status"] == "proposed":
            blockers.append(f"{entry['key']}: escalated — the developer must rule (see"
                            f" draft debate record {entry['debate_id']})")
            continue
        if name in _GATED_LISTS:
            verification = entry.get("verification")
            if verification is None:
                blockers.append(f"{entry['key']}: never reached the verifier — run"
                                f" `draft verify`")
            elif not verification["admissible"]:
                blockers.append(f"{entry['key']}: the gate refused it"
                                f" ({verification['verdict']}) — fix the claim or its"
                                f" citations, or drop the carve")
    return blockers


def _land_plan(cycle: Cycle, plan: dict, *, target: str, repo_root: Path,
               status_checker, lander) -> tuple[Cycle, list]:
    """Land the debate records, the plan and the cycle file (in that order) and advance the
    cycle to `target`. Shared by the mint-mode and draft-only finalizers."""
    run_id = plan["runs"]["ontologist"]
    # The debate records go first: a debate record is 3C's hand-off to 3D, and the cycle is
    # about to point at these paths as its artifacts. `draft debate` writes them but does not
    # land them — a debate can still be re-run or superseded while the plan is open, so they
    # are committed here, with the plan that reached its conclusions.
    results = []
    for debate_rel in _debate_artifacts(plan):
        debate_result = lander(repo_root, debate_rel, (repo_root / debate_rel).read_text(),
                               chat_run_id=run_id, validator=store_validator,
                               status_checker=status_checker)
        results.append(debate_result)
        if not isinstance(debate_result, Landed):
            return cycle, results

    plan_rel = f"research/drafts/{cycle.slug}.yaml"
    plan_result = lander(repo_root, plan_rel, render_plan(plan), chat_run_id=run_id,
                         validator=store_validator, status_checker=status_checker)
    results.append(plan_result)
    if not isinstance(plan_result, Landed):
        return cycle, results

    updated = cycle if cycle.status == target else advance(cycle, target)
    artifacts = {**(cycle.artifacts or {}), "draft": plan_rel}
    debates = _debate_artifacts(plan)
    if debates:
        artifacts["debates"] = debates
    updated = replace(updated, artifacts=artifacts)
    cycle_file = save_cycle(updated, repo_root=repo_root)
    cycle_result = lander(repo_root, str(cycle_file.relative_to(repo_root)),
                          cycle_file.read_text(), chat_run_id=run_id,
                          validator=store_validator, status_checker=status_checker)
    results.append(cycle_result)
    if not isinstance(cycle_result, Landed):
        save_cycle(cycle, repo_root=repo_root)
        return cycle, results
    return updated, results
```
This is today's `finalize_r4` landing tail moved verbatim, with exactly two substitutions: `target` replaces the literal `"r4-done"` in both the `advance(...)` call and the `cycle.status ==` comparison. Then

```python
def finalize_r4(cycle_number, *, repo_root, status_checker=None, lander=land_record):
    """@raises SignOffMissing / SignOffStale / R4Incomplete / DraftMissing"""
    cycle = load_cycle(cycle_number, repo_root=repo_root)
    require_sign_off(cycle, repo_root=repo_root)
    plan = load_plan(cycle.slug, repo_root=repo_root)
    blockers = r4_blockers(cycle, plan, repo_root=repo_root)
    if blockers:
        raise R4Incomplete(f"{cycle.slug} cannot close R4: " + "; ".join(blockers))
    return _land_plan(cycle, plan, target="r4-done", repo_root=repo_root,
                      status_checker=status_checker, lander=lander)


def finalize_r4_draft(cycle_number, *, repo_root, status_checker=None, lander=land_record):
    """D70's draft-only close: land the plan and debates, mint nothing, move to `r4-drafted`.
    @raises SignOffMissing / SignOffStale / R4Incomplete / DraftMissing"""
    cycle = load_cycle(cycle_number, repo_root=repo_root)
    require_sign_off(cycle, repo_root=repo_root)
    plan = load_plan(cycle.slug, repo_root=repo_root)
    blockers = r4_draft_blockers(cycle, plan, repo_root=repo_root)
    if blockers:
        raise R4Incomplete(f"{cycle.slug} cannot close its draft: " + "; ".join(blockers))
    return _land_plan(cycle, plan, target="r4-drafted", repo_root=repo_root,
                      status_checker=status_checker, lander=lander)
```
Import `is_blocked` and `open_carves` (already imported) in `finalize.py`.

`cli.py`:
- In `_dispatch_draft`, right after `cycle = load_cycle(...)`: `if args.draft_command == "mint": from langatlas_research.structure_review import require_mint_open; require_mint_open(repo)` (offline, so it fires before any database connection).
- Replace the `finalize` branch with:

```python
    if args.draft_command == "finalize":
        from langatlas_research.draft.finalize import finalize_r4, finalize_r4_draft
        from langatlas_research.structure_review import mint_open

        if mint_open(repo):
            updated, results = finalize_r4(cycle.number, repo_root=repo)
            expected = "r4-done"
        else:
            updated, results = finalize_r4_draft(cycle.number, repo_root=repo)
            expected = "r4-drafted"
        for result in results:
            print(repr(result))
        print(f"cycle {updated.slug} -> {updated.status}")
        return 0 if updated.status == expected else 1
```
- In the `debate` branch (`_dispatch_draft_online`), skip D45's contradiction mint while held: `from langatlas_research.structure_review import mint_open` and

```python
                contradiction = (None if not mint_open(repo)
                                 else mint_debate_contradiction(debate, repo_root=repo))
```
(a contradiction names carve-plan nodes that are not committed, so it cannot land; the debate record keeps `resolution.contradiction`, and re-atomization repeats the debates.)

- [ ] **Step 4: Open the gate in the two repo fixtures**

In `tests/conftest.py`, add near the top:

```python
def _open_structure_review_gate(repo):
    from langatlas_research.paths import structure_review_path

    structure_review_path(repo).write_text(
        "reviewed_by: test\ndate: '2026-09-20'\nsummary: fixture\nbatch: [1]\n")
```
Call it in `store_repo` right after `ensure_layout(clone)` (before the `git add -A`) and in `research_repo` right after its `ensure_layout(repo)` call. Existing mint tests keep passing; the new tests unlink the file to close the gate.

- [ ] **Step 5: Run the package tests**

Run: `uv --directory tools/research run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/research research/schema
git commit -m "feat(#stage-3g): hold minting until the structure review and add the r4-drafted status"
```
Stop for review.

---

### Task 6: The `wrong-structure` challenge type

**Files:**
- Modify: `tools/research/src/langatlas_research/draft/debate_record.py:22`
- Modify: `tools/research/src/langatlas_research/draft/debate.py:104-115,321-353`
- Modify: `research/schema/debate.schema.json` (two challenge-type enums, `resolution`)
- Test: `tools/research/tests/test_draft_debate.py` (append)

**Interfaces:**
- Consumes: `friction_entry`, `STRUCTURE_ELEMENTS` (Task 1).
- Produces:
  - `CHALLENGE_TYPES` gains `"wrong-structure"`.
  - `ModeratorOut.structure_element: <STRUCTURE_ELEMENTS member> | None`; `resolution.structure_element` in the debate record when set.
  - `debate.add_debate_friction(plan: dict, debate: dict) -> dict`: appends one `structure-friction` finding (area `ontology`, element `structure_element` or `other`, keyed by the debated carve, detail = the moderator's rationale) when `wrong-structure` was upheld; otherwise returns `plan` unchanged.

A `wrong-structure` resolution never changes the carve: the moderator still picks a disposition on the carve's own merits (usually `keep`).

- [ ] **Step 1: Write the failing tests**

```python
# appended to tools/research/tests/test_draft_debate.py
def test_wrong_structure_is_a_challenge_type():
    from langatlas_research.draft.debate_record import CHALLENGE_TYPES

    assert "wrong-structure" in CHALLENGE_TYPES


def test_an_upheld_wrong_structure_challenge_files_a_friction_finding():
    from langatlas_research.draft.debate import add_debate_friction

    plan = {"findings": []}
    debate = {"id": "d-01-typing-001", "target": {"key": "type-classes"},
              "resolution": {"upheld_challenges": ["wrong-structure"],
                             "structure_element": "edge-types",
                             "rationale": "no relation expresses that this specialises another"}}
    updated = add_debate_friction(plan, debate)
    assert updated["findings"] == [{
        "kind": "structure-friction", "keys": ["type-classes"], "area": "ontology",
        "element": "edge-types",
        "detail": "no relation expresses that this specialises another"}]
    assert plan["findings"] == []          # pure


def test_a_missing_element_defaults_to_other_and_other_debates_add_nothing():
    from langatlas_research.draft.debate import add_debate_friction

    debate = {"id": "d", "target": {"key": "k"},
              "resolution": {"upheld_challenges": ["wrong-structure"], "rationale": "r"}}
    assert add_debate_friction({"findings": []}, debate)["findings"][0]["element"] == "other"
    quiet = {"id": "d", "target": {"key": "k"},
             "resolution": {"upheld_challenges": ["scope"], "rationale": "r"}}
    assert add_debate_friction({"findings": []}, quiet) == {"findings": []}


def test_the_debate_schema_accepts_wrong_structure(research_repo, signed_cycle):
    from langatlas_research.draft.debate_record import save_debate

    save_debate({"id": f"d-{signed_cycle.slug}-001", "cycle": 1, "theme": "typing",
                 "target": {"list": "nodes", "key": "type-classes"},
                 "opened": "2026-09-20", "runs": {"debate": "r"}, "triggers": [],
                 "personas": {}, "pre_challenge": {}, "messages": [
                     {"seq": 1, "role": "challenger-a", "persona": "p", "text": "x",
                      "challenges": [{"type": "wrong-structure", "text": "no slot"}]}],
                 "resolution": {"outcome": "resolved", "disposition": "keep",
                                "standing_dissent": False, "rounds": 1,
                                "upheld_challenges": ["wrong-structure"],
                                "structure_element": "edge-types", "rationale": "sound"}},
                repo_root=research_repo)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv --directory tools/research run pytest -q tests/test_draft_debate.py`
Expected: FAIL.

- [ ] **Step 3: Implement**

`debate_record.py`: `CHALLENGE_TYPES = ("wrong-atomization", "wrong-layer", "wrong-structure", "missing-source", "redundant-with", "scope")`.

`debate.schema.json`: add `"wrong-structure"` to both enums (the message `challenges[].type` and `resolution.upheld_challenges` items) and, in `resolution.properties`, add

```json
        "structure_element": { "enum": ["layers", "concept-feature-split", "realizes",
                                        "edge-types", "dimension-model", "qualities",
                                        "record-kinds", "other"] },
```

`debate.py`: import `STRUCTURE_ELEMENTS, friction_entry` from `draft.findings`. In `ModeratorOut` add

```python
    structure_element: Literal[STRUCTURE_ELEMENTS] | None = None     # type: ignore[valid-type]
```
In `run_debate`, extend the loop that copies optional resolution fields:

```python
    for field, value in (("revision", verdict.revision),
                         ("merge_into", verdict.merge_into),
                         ("drop_reason", verdict.drop_reason),
                         ("structure_element", verdict.structure_element)):
```
and replace `updated = apply_resolution(plan, record, lookup=lookup)` with

```python
    updated = add_debate_friction(apply_resolution(plan, record, lookup=lookup), record)
```
Add:

```python
def add_debate_friction(plan: dict, debate: dict) -> dict:
    """D70: an upheld `wrong-structure` challenge means the carve is fine but the structure has
    no slot for it. The carve keeps whatever disposition it earned; the structure review reads
    the finding. Pure."""
    resolution = debate["resolution"]
    if "wrong-structure" not in resolution["upheld_challenges"]:
        return plan
    finding = friction_entry(resolution["rationale"], keys=[debate["target"]["key"]],
                             element=resolution.get("structure_element") or "other")
    return {**plan, "findings": [*(plan.get("findings") or []), finding]}
```

- [ ] **Step 4: Run the package tests**

Run: `uv --directory tools/research run pytest -q`
Expected: PASS (including `test_debate_goldens.py` and `test_exit_3c.py`, which prove the extra challenge type broke nothing in 3D's contract).

- [ ] **Step 5: Commit**

```bash
git add tools/research research/schema/debate.schema.json
git commit -m "feat(#stage-3g): let debates contest the structure with wrong-structure"
```
Stop for review.

---

### Task 7: Tell the roles the structure is provisional (four prompt versions)

**Files:**
- New versions (via the registry, never hand-edited): `prompts/r4-ontologist/`, `prompts/r4-edge-drafter/`, `prompts/r4-challenger/`, `prompts/r4-moderator/`
- Test: `tools/research/tests/test_prompts_provisional.py`

**Interfaces:**
- Produces: a new latest version of each of the four prompts; no variable changes (each paragraph is static text inserted at the end of the `# system` section, before `# user`).

- [ ] **Step 1: Write the failing test**

```python
# tools/research/tests/test_prompts_provisional.py
import pytest
from langatlas_pipeline.prompts import load_prompt

EXPECT = {
    "r4-ontologist": ("CURRENT WORKING MODEL", "structure-friction"),
    "r4-edge-drafter": ("CURRENT WORKING MODEL", "structure-friction"),
    "r4-challenger": ("wrong-structure",),
    "r4-moderator": ("wrong-structure", "structure_element"),
}


@pytest.mark.parametrize("prompt_id", EXPECT)
def test_the_latest_version_carries_the_provisional_structure_paragraph(prompt_id):
    text = load_prompt(prompt_id).text
    for needle in EXPECT[prompt_id]:
        assert needle in text, f"{prompt_id} does not mention {needle!r}"
    assert text.index(EXPECT[prompt_id][0]) < text.index("# user")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv --directory tools/research run pytest -q tests/test_prompts_provisional.py`
Expected: FAIL (4 failures).

- [ ] **Step 3: Mint the four versions**

Run from the repo root:

```bash
uv --directory tools/pipeline run python - <<'EOF'
from langatlas_pipeline.prompts import load_prompt, mint_prompt_version

PROVISIONAL = """The layers, the concept/feature split, the meaning of `realizes` and the
dimension model described above are the project's CURRENT WORKING MODEL, not settled truth.
They were sketched before any theme was researched, and this research exists to test them.
Carve what the sources support, even where it does not fit the model. When a carve does not
fit (a feature that specialises another feature, a relation `realizes` cannot express, a layer
that does not match), carve it honestly with its evidence, fill the fields as best you can, and
report a `structure-friction` finding: name the structural element at issue in `element`
(layers, concept-feature-split, realizes, edge-types, dimension-model, qualities,
record-kinds, other), set `area` to `ontology` for the ontology's own structure or `adjacent`
for a neighbouring schema (provenance, ids, instance fields), and say what the model would need
in order to express it. Never bend a carve to make it fit, and never flatten a distinction into
prose to avoid a misfit: the misfit is the finding.
"""

EDGE = """The edge types listed above are the project's CURRENT WORKING MODEL, not settled
truth. If two features relate in a way none of them expresses (for example one specialises
another), do not force the closest type: report a `structure-friction` finding with
`element: edge-types` (`area: ontology`), name the two features in `keys`, and say what
relation would express it. The five types connect features only; a relation that touches a
concept is also a finding, not an edge.
"""

CHALLENGER = """You may also raise a `wrong-structure` challenge: the carve is defensible on the
sources, but the ontology's structure (its layers, its concept/feature split, what `realizes`
can say, its relation types) has no slot for what the sources describe, so the carve is being
bent to fit. That structure is a working model under test, not settled truth. Raise this
instead of arguing that the carve should change, and cite the passage that shows the misfit.
"""

MODERATOR = """If a `wrong-structure` challenge is upheld, choose the disposition on the carve's
own merits (usually `keep`: the carve is not what is wrong), list `wrong-structure` in
`upheld_challenges`, and set `structure_element` to the structural element at issue (layers,
concept-feature-split, realizes, edge-types, dimension-model, qualities, record-kinds, other).
Your rationale becomes the finding the structure review reads, so state what the structure
would need in order to hold the carve.
"""

PARAGRAPHS = {"r4-ontologist": PROVISIONAL, "r4-edge-drafter": EDGE,
              "r4-challenger": CHALLENGER, "r4-moderator": MODERATOR}
for prompt_id, paragraph in PARAGRAPHS.items():
    old = load_prompt(prompt_id)
    assert "\n# user" in old.text, prompt_id
    new_text = old.text.replace("\n# user", "\n" + paragraph + "\n# user", 1)
    ref = mint_prompt_version(
        prompt_id, new_text,
        note="D70: the seed structure is provisional; misfits are findings, not conformance")
    print(prompt_id, old.version, "->", ref.version)
EOF
```
Expected: four lines `prompt_id v-old -> v-new`, and one new `v<N>` line appended to each `CHANGELOG.md`.

- [ ] **Step 4: Run the tests**

Run: `uv --directory tools/research run pytest -q tests/test_prompts_provisional.py` then `uv --directory tools/pipeline run pytest -q`
Expected: PASS. (The pipeline suite covers the prompt registry and any regression-fixture checks that new versions trigger.)

- [ ] **Step 5: Commit**

```bash
git add prompts tools/research/tests/test_prompts_provisional.py
git commit -m "feat(#stage-3g): tell the R4 roles the seed structure is provisional"
```
Stop for review.

---

### Task 8: `structure report` and `structure release`

**Files:**
- Modify: `tools/research/src/langatlas_research/structure_review.py` (add report functions)
- Modify: `tools/research/src/langatlas_research/cli.py`
- Test: `tools/research/tests/test_structure_review.py` (append), `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `drafts_dir`, `release_structure_review` (Task 5).
- Produces:
  - `FrictionRow(cycle: int, theme: str, area: str, element: str, detail: str, keys: tuple[str, ...])`.
  - `collect_friction(repo_root=None) -> list[FrictionRow]`: every `structure-friction` finding in every carve plan under `research/drafts/`, ordered by cycle.
  - `render_report(rows: list[FrictionRow]) -> str`: grouped by `area` (`ontology` first) then `element`, each element headed by its finding count and distinct-theme count.
  - CLI: `structure report [--area ontology|adjacent]`, `structure release --by NAME --summary TEXT [--date YYYY-MM-DD]`.

- [ ] **Step 1: Write the failing tests**

```python
# appended to tools/research/tests/test_structure_review.py
from langatlas_research.draft.findings import friction_entry
from langatlas_research.draft.plan import build_plan_record, save_plan
from langatlas_research.structure_review import collect_friction, render_report


def _plan_with(cycle, repo, *findings):
    plan = build_plan_record(cycle=cycle, ontologist_run_id="r", generated_at="t")
    plan["findings"] = list(findings)
    save_plan(plan, repo_root=repo)


def test_collect_friction_reads_every_plans_friction_findings(research_repo, signed_cycle):
    _plan_with(signed_cycle, research_repo,
               friction_entry("no refinement relation", keys=["gadt", "adts"],
                              element="edge-types"),
               {"kind": "rule-candidate", "detail": "x", "keys": []},
               friction_entry("provenance has no slot for a chat link", keys=["a"],
                              element="other", area="adjacent"))
    rows = collect_friction(research_repo)
    assert [(r.cycle, r.theme, r.area, r.element) for r in rows] == [
        (1, "typing", "ontology", "edge-types"), (1, "typing", "adjacent", "other")]
    assert rows[0].keys == ("gadt", "adts")


def test_the_report_groups_by_area_then_element_and_says_how_widespread(
        research_repo, signed_cycle):
    _plan_with(signed_cycle, research_repo,
               friction_entry("a", keys=["k1"], element="realizes"),
               friction_entry("b", keys=["k2"], element="realizes"),
               friction_entry("c", keys=["k3"], element="other", area="adjacent"))
    text = render_report(collect_friction(research_repo))
    assert text.index("== ontology ==") < text.index("== adjacent ==")
    assert "realizes: 2 finding(s) across 1 theme(s)" in text
    assert "[01 typing] k1: a" in text


def test_an_empty_report_says_so():
    assert render_report([]) == "no structure-friction findings"
```
Append to `tests/test_cli.py`:

```python
def test_structure_report_and_release(research_repo, signed_cycle, capsys):
    from langatlas_research.cycle import advance, save_cycle
    from langatlas_research.paths import structure_review_path

    structure_review_path(research_repo).unlink()
    assert main(["--repo-root", str(research_repo), "structure", "report"]) == 0
    assert "no structure-friction findings" in capsys.readouterr().out
    assert main(["--repo-root", str(research_repo), "structure", "release",
                 "--by", "Michal", "--summary", "kept the model"]) == 1
    assert "no cycle is at r4-drafted" in capsys.readouterr().err
    save_cycle(advance(advance(signed_cycle, "r3-done"), "r4-drafted"),
               repo_root=research_repo)
    assert main(["--repo-root", str(research_repo), "structure", "release",
                 "--by", "Michal", "--summary", "kept the model"]) == 0
    assert structure_review_path(research_repo).exists()
```
(`main` is already imported in `test_cli.py`; if not, add `from langatlas_research.cli import main`.)

- [ ] **Step 2: Run to verify failure**

Run: `uv --directory tools/research run pytest -q tests/test_structure_review.py tests/test_cli.py`
Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `structure_review.py`:

```python
from dataclasses import dataclass

from langatlas_research.paths import drafts_dir

_read = YAML(typ="safe")


@dataclass(frozen=True)
class FrictionRow:
    cycle: int
    theme: str
    area: str
    element: str
    detail: str
    keys: tuple[str, ...]


def collect_friction(repo_root: Path | None = None) -> list[FrictionRow]:
    """Every `structure-friction` finding in every carve plan — the structure review's agenda.
    Read it *before* re-atomizing: a re-atomized plan replaces its findings (git keeps the old
    plan)."""
    rows = []
    for path in sorted(drafts_dir(repo_root).glob("*.yaml")):
        plan = _read.load(path.read_text()) or {}
        for finding in plan.get("findings") or []:
            if finding.get("kind") == "structure-friction":
                rows.append(FrictionRow(plan["cycle"], plan["theme"], finding["area"],
                                        finding["element"], finding["detail"],
                                        tuple(finding.get("keys") or ())))
    return sorted(rows, key=lambda row: (row.cycle, row.area != "ontology", row.element))


def render_report(rows: list[FrictionRow]) -> str:
    """Grouped by area (`ontology` first), then element. How widespread a misfit is — the
    number of distinct themes it appears in — is the first thing a review wants to know."""
    if not rows:
        return "no structure-friction findings"
    lines: list[str] = []
    for area in ("ontology", "adjacent"):
        in_area = [row for row in rows if row.area == area]
        if not in_area:
            continue
        lines.append(f"== {area} ==")
        for element in sorted({row.element for row in in_area}):
            group = [row for row in in_area if row.element == element]
            themes = len({row.theme for row in group})
            lines.append(f"{element}: {len(group)} finding(s) across {themes} theme(s)")
            for row in group:
                lines.append(f"  [{row.cycle:02d} {row.theme}] {', '.join(row.keys)}:"
                             f" {row.detail}")
        lines.append("")
    return "\n".join(lines).rstrip()
```

`cli.py`: in `main` add

```python
    p_structure = sub.add_parser("structure").add_subparsers(dest="structure_command",
                                                             required=True)
    p_report = p_structure.add_parser("report", help="the structure review's agenda (D70)")
    p_report.add_argument("--area", choices=("ontology", "adjacent"), default=None)
    p_release = p_structure.add_parser(
        "release", help="developer: record the structure review and open minting")
    p_release.add_argument("--by", required=True)
    p_release.add_argument("--summary", required=True,
                           help="the schema decisions the review reached")
    p_release.add_argument("--date", default=None)
```
and in `_dispatch`:

```python
    if args.command == "structure":
        from langatlas_research.structure_review import (
            collect_friction, release_structure_review, render_report,
        )

        if args.structure_command == "report":
            rows = [row for row in collect_friction(root)
                    if args.area in (None, row.area)]
            print(render_report(rows))
            return 0
        path = release_structure_review(
            by=args.by, date=args.date or _dt.date.today().isoformat(),
            summary=args.summary, repo_root=root)
        print(f"recorded {path}; minting is open")
        return 0
```

- [ ] **Step 4: Run the package tests**

Run: `uv --directory tools/research run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/research
git commit -m "feat(#stage-3g): add the structure report and the release act"
```
Stop for review.

---

### Task 9: Exit test, runbook and spec

**Files:**
- Create: `tools/research/tests/test_exit_3g.py`
- Modify: `docs/runbooks/theme-cycle.md`
- Modify: `context/spec.md` (§7.4, after the "Graduated 0.x minting ceremony" paragraph)
- Modify: `research/drafts/README.md`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the exit test (the whole draft-only path, offline)**

```python
# tools/research/tests/test_exit_3g.py
"""Stage 3G's exit: a draft-only cycle keeps a structural misfit, closes without minting, is
held at the gate, shows up in the review's agenda, and mints only once the review is recorded —
and even then never mints the blocked carve."""
import pytest

from langatlas_commit.land import Landed
from langatlas_research.cycle import advance, load_cycle, save_cycle
from langatlas_research.draft.finalize import finalize_r4_draft, r4_blockers
from langatlas_research.draft.findings import friction_entry
from langatlas_research.draft.minting import mint_items, mint_plan
from langatlas_research.draft.plan import build_plan_record, save_plan
from langatlas_research.errors import MintHeld
from langatlas_research.paths import structure_review_path
from langatlas_research.structure_review import (
    collect_friction, mint_open, release_structure_review, render_report,
)


def _concept():
    return {"key": "type-system", "from_candidates": ["type-system"], "kind": "concept",
            "id": "type-system", "name": "Type system", "summary": "s",
            "evidence": [{"source": "pierce-tapl-2002", "locator": "§1.1"},
                         {"source": "scott-plp", "locator": "§7.2"}],
            "contested": [], "debate_id": None, "status": "verified",
            "verification": {"fact_id": "f-1", "verdict": "verified", "admissible": True,
                             "pairs": 2}, "note": ""}


def _blocked_feature():
    return {"key": "type-classes", "from_candidates": ["type-classes"], "kind": "feature",
            "id": "type-classes", "name": "Type classes", "summary": "s", "layer": 2,
            "dimension": None, "cross_cutting": False, "aliases": [],
            "realizes": ["ad-hoc-polymorphism"],
            "evidence": [{"source": "scott-plp", "locator": "§7.2"}],
            "contested": [], "debate_id": None, "status": "proposed", "verification": None,
            "note": "", "blocked": "structure",
            "block_reason": "realizes 'ad-hoc-polymorphism', which is a feature"}


def test_the_draft_only_path_end_to_end(research_repo, signed_cycle):
    structure_review_path(research_repo).unlink()             # a fresh, unreviewed repo
    cycle = advance(signed_cycle, "r3-done")
    save_cycle(cycle, repo_root=research_repo)
    plan = build_plan_record(cycle=cycle, ontologist_run_id="run-1",
                             generated_at="2026-09-20T10:00:00Z")
    plan["nodes"] = [_concept(), _blocked_feature()]
    plan["findings"] = [friction_entry("a feature refines a feature; realizes cannot say so",
                                       keys=["type-classes"], element="realizes")]
    save_plan(plan, repo_root=research_repo)

    # 1. the draft closes without minting: the blocked carve is the point, not a blocker
    closed, _ = finalize_r4_draft(cycle.number, repo_root=research_repo,
                                  lander=lambda *a, **k: Landed(commit_sha="abc1234"))
    assert closed.status == "r4-drafted"
    assert load_cycle(cycle.number, repo_root=research_repo).nodes_minted == ()

    # 2. the gate holds
    assert mint_open(research_repo) is False
    with pytest.raises(MintHeld):
        mint_plan(plan, repo_root=research_repo, cycle=closed, chat_run_id="r",
                  prompt_version="v")

    # 3. the review's agenda shows the finding
    report = render_report(collect_friction(research_repo))
    assert "realizes: 1 finding(s) across 1 theme(s)" in report
    assert "[01 typing] type-classes" in report

    # 4. release opens the gate for the batch...
    release_structure_review(by="Michal", date="2026-09-25",
                             summary="kept the seed structure", repo_root=research_repo)
    assert mint_open(research_repo) is True

    # 5. ...but a blocked carve still never mints, and still blocks the mint-mode finalize
    items = mint_items(plan, repo_root=research_repo, ctx_run_id="r", prompt_version="v")
    assert len(items) == 1                                     # only the admitted concept
    assert any("blocked" in b for b in r4_blockers(closed, plan, repo_root=research_repo))
```

- [ ] **Step 2: Run it**

Run: `uv --directory tools/research run pytest -q tests/test_exit_3g.py`
Expected: PASS (all earlier tasks landed). A failure here is a defect in the task it names, not in this test.

- [ ] **Step 3: Update the runbook**

In `docs/runbooks/theme-cycle.md`:

1. Replace the paragraph under the title ("Cycle 1 was the shakedown…") by adding after it:

```markdown
**Draft-only batch (D70).** Until the developer records the **structure review** (§ "Structure
review" below), no cycle mints: `draft mint` refuses, `draft finalize` lands the carve plan and
moves the cycle to `r4-drafted`, and R5/R6 wait. The seed structure (layers, concept/feature
split, `realizes`, edge types, dimensions) is a hypothesis these first cycles test. Cycles 1-4
(typing, memory-management, concurrency, syntax-layer-constructs) form the batch.
```

2. In §3 (R4) add, after the `draft mint` lines, a note and change the sequence's edge steps:

```markdown
While the gate is closed the sequence is: `draft atomize` → `draft contested` →
`draft debate --all` → `draft verify` → `draft edges` (drafted against the carve plan's own
nodes) → `draft debate --all` → `draft verify` → `draft finalize` (→ `r4-drafted`). Skip
`draft mint`. A carve the structure cannot hold appears in `draft status` as `blocked` with a
`structure-friction` finding; it is never debated, verified or minted. `draft drop N KEY
--reason "…"` retires one you decide not to keep.
```

3. Add a new section after §6 ("Settle"):

```markdown
## Structure review (D70) — the checkpoint that opens minting

After the four batch cycles are `r4-drafted`:

```bash
$R structure report                  # every structure-friction finding, grouped
$R structure report --area adjacent  # adjacent-schema friction: decide case by case
```

**[developer]** Read the report and decide the schema changes (ordinary 0.x changes: schemas,
`ontology/taxonomy/*.yaml`, and the role prompts' structure text — `_LAYERS` in
`draft/ontologist.py` and `EDGE_TYPES` in `draft/edges.py`). The review's authority is ontology
structure; `adjacent` findings are decided one by one. Then:

```bash
$R structure release --by "Your Name" --summary "the decisions, in a sentence or two"
```

This writes `research/structure-review.yaml` and opens minting. Re-atomize each batch cycle from
its existing survey, then run R4 with minting on:

```bash
$R draft atomize $N                  # a fresh carve plan against the revised structure
# ... draft contested → debate → verify → mint → edges → … → draft finalize   (→ r4-done)
```

Read `structure report` **before** re-atomizing: a re-atomized plan replaces its findings (git
keeps the old plan). A friction finding raised in any later cycle is reviewed at that cycle's R6;
a change that touches a settled theme goes through the migration manifest. R5 stays out of the
batch unless the structure is still unclear after it (then `reality compile` would need to read
a carve plan — not built).
```

4. In the failure table add two rows:

```markdown
| `MintHeld` | no structure review is recorded (D70) | finish the batch, `structure report`, then `structure release` |
| `blocked by the seed structure … resolve at the structure review` | a carve the structure cannot hold | wait for the review and re-atomize, or `draft drop` it |
```

- [ ] **Step 4: Update the spec and the drafts README**

In `context/spec.md`, after the "Graduated 0.x minting ceremony" paragraph in §7.4, add:

```markdown
**Structure plasticity (D70)**: the seed structure (layers, concept/feature split, `realizes`,
relation set, dimension model, seed qualities) is provisional until a developer **structure
review**. R4's roles record misfits as `structure-friction` findings (classified by structural
element and by `ontology` | `adjacent` area) rather than conforming; a carve the structure cannot
hold stays in the carve plan as a `blocked` entry; R4 debates may raise `wrong-structure`.
The first four themes run R3→R4 draft-only (carve plans and debates land, `r4-drafted`, nothing
mints) until `structure release` records the review, after which the batch is re-atomized from
the same surveys and mints; later cycles mint per cycle. Sourcing and process invariants (D1,
D4, D18, D24, D27, D31) are not part of the provisional structure.
```

In `research/drafts/README.md` append: `An entry marked `blocked: structure` is a carve the seed structure cannot hold (D70); it is never debated, verified or minted, and is linked to a `structure-friction` finding the structure review reads (`langatlas-research structure report`).`

- [ ] **Step 5: Run everything**

Run: `uv --directory tools/research run pytest -q` and `uv --directory tools/pipeline run pytest -q` and `uv --directory tools/validate run pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/research/tests/test_exit_3g.py docs/runbooks/theme-cycle.md context/spec.md research/drafts/README.md
git commit -m "feat(#stage-3g): prove the draft-only path end to end and document it"
```
Stop for review.

---

## Out of scope (recorded so nothing is assumed)

- **R5 from a carve plan.** Kept as an option only if the structure is still unclear after the batch (developer, 2026-09-19); `reality compile` still reads the committed subtree.
- **Structure text in code.** `_LAYERS` (ontologist) and `EDGE_TYPES` (edge drafter) are still constants; after a structure review that changes them, the developer edits them (the runbook says so). Externalising them into one structure document is a follow-up if the review changes them more than once.
- **Quality-edge misfits.** `check_shape`'s quality-edge checks stay hygiene errors; no cycle-1 evidence of a structural misfit there.
- **R6's cross-theme pass.** It keeps `check_shape`'s strict default; friction there is reported through the shared finding model only.
- **Sub-plan 3G's own parent map.** [2026-09-13-stage-3-theme-cycles.md](2026-09-13-stage-3-theme-cycles.md) is not edited by this plan (it holds the developer's in-progress changes).

## Then run the batch (data, not code)

1. `cycle new 2 memory-management`, `3 concurrency`, `4 syntax-layer-constructs`; the developer signs each off.
2. Cycle 1 is at `r3-done` already; R3 (survey → tag → scout) runs for cycles 2-4.
3. Run R4 draft-only for cycles 1-4 (runbook §3), then `structure report`, the review, `structure release`, re-atomization and the normal R4→R6 flow.
