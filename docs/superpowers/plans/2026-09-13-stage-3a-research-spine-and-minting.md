# Stage 3A — Research Spine & the Node-Minting Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic, provider-free core of Stage 3's theme cycles — cycle
bookkeeping with a real developer sign-off gate, and a minting path that turns a structured draft
into a validated, normalized, landed canonical-store record — so every later agent role (surveyor,
ontologist, edge drafter, reality checker) has one tested place to end at.

**Architecture:** One new package, `tools/research/` (`langatlas_research`), holding four
concerns: `research/`-directory bookkeeping (themes, cycles, sign-off), draft dataclasses, a
renderer that produces normalized schema-valid YAML at the §3.3 path, and a lander that drives
`langatlas_commit.land_record`. Two additions to the existing `langatlas_validate` package:
referential-integrity checks in `validate_store` (Stage 3 is the first stage that can violate
them) and the 0.x version ceremony (`version-bump`). No model is called anywhere in 3A — every
input is hand-written or comes from a later sub-plan's agent.

**Tech Stack:** Python 3.12, `uv` per-package workspaces, `ruamel.yaml`, `jsonschema`, `pytest`;
`langatlas-validate`, `langatlas-commit`, `langatlas-pipeline` as path dependencies.

**Spec:** [context/spec.md](../../../context/spec.md) — §3.1–3.3, §3.5, §5.1, §7.4 (the graduated
0.x minting ceremony), §7.9, §7.12.

**Sequencing map:** [2026-09-13-stage-3-theme-cycles.md](2026-09-13-stage-3-theme-cycles.md) —
3A's "Produces for 3B–3F" list is this plan's required deliverables.

## Global Constraints

Every task's requirements implicitly include this section. Values copied verbatim from the spec.

- **Source-first (D4/§6.1).** A node may not be minted without `source_id` + `locator`. The
  renderer refuses an unsourced draft; `claim_origin` is `source-derived` or `prior`, and a `prior`
  draft still needs evidence — the field records *what steered the search*, never a licence to
  skip a citation.
- **Git is the database (D1).** Everything 3A writes is a file in the repo. No database, no
  service, no derived store.
- **One commit per record file (D36/§7.9).** Records land through
  `langatlas_commit.land_record`, which owns the fetch-rebase-retry loop, the is-main-green gate,
  and the `LangAtlas-Record-Key` / `LangAtlas-Chat-Run-Id` trailers. 3A never shells out to `git`
  on its own for landing.
- **Ids are deterministic compositions, never free identities (§3.3).** `fi.<lang>.<feature>`,
  `edge.<type>.<from>.<to>`, `rule-<slug>`, `<instance-id>.sx.<key>`.
- **Immutable `id`, renameable `slug` (§5.1).** Renames are PATCH events resolved through
  `ontology/redirects.yaml`; ids never change.
- **Slug grammar:** `[a-z0-9]+(-[a-z0-9]+)*`, ≤48 chars, ASCII, no leading digit
  (`langatlas_validate.ids.is_valid_slug` is the one implementation — never re-derive it).
- **Canonical ordering (§3.3/D64):** `alternative-to` endpoints lexicographic; a rule's `when_all`
  lexicographically sorted; `then` stays in authored order; rule arity floor `len(when_all) ≥ 2`.
- **YAML normalization (§3.5):** every record passes `normalize_record(text, kind)` unchanged
  before it is landed. 2-space indent, schema key order, 100-column soft wrap, prose in `>-`,
  code in `|`, no anchors/aliases/tags, quoted ISO-8601 dates.
- **Graduated 0.x ceremony (§7.4).** While `ontology/VERSION` is `0.x`: immutable ids, content
  keys, validation and logging from the first node; restructures are ordinary commits; CI
  auto-bumps MINOR. The RFC-gated D16 MAJOR process switches on at `1.0.0` — **Stage 4, not here.**
- **The developer signs off every cycle's theme list before R3 runs (D27).** Agents never cycle
  autonomously.
- English-only; code MIT, corpus CC BY-SA 4.0.

## File structure

| File | Responsibility |
|---|---|
| `tools/research/pyproject.toml` | Package metadata; path deps on validate/commit/pipeline; `langatlas-research` script |
| `tools/research/src/langatlas_research/paths.py` | Where `research/` lives; `ensure_layout` |
| `tools/research/src/langatlas_research/errors.py` | The package's typed failures |
| `tools/research/src/langatlas_research/schema.py` | Research-artifact JSON Schema loading + tree validation |
| `tools/research/src/langatlas_research/themes.py` | `research/themes.yaml` reader + `theme_digest` |
| `tools/research/src/langatlas_research/cycle.py` | Cycle records, status machine, sign-off gate, minted-node bookkeeping |
| `tools/research/src/langatlas_research/rotation.py` | R5's rotating 4–5-language sample planner |
| `tools/research/src/langatlas_research/drafts.py` | Draft dataclasses (the shape every agent role produces) |
| `tools/research/src/langatlas_research/mint.py` | Drafts → `MintedRecord(path, text, node_ids, kind, base_digest)` |
| `tools/research/src/langatlas_research/taxonomy.py` | Shared-file mints: dimensions, qualities, the language registry |
| `tools/research/src/langatlas_research/land.py` | `land_drafts` — render, land, re-render on contention, bookkeep |
| `tools/research/src/langatlas_research/cli.py` | `langatlas-research` subcommands |
| `research/schema/theme-registry.schema.json` | Schema for `research/themes.yaml` |
| `research/schema/cycle.schema.json` | Schema for `research/cycles/*.yaml` |
| `research/themes.yaml` | The seeded ~12-theme list |
| `tools/validate/src/langatlas_validate/store.py` | **Modified:** referential integrity + filename/id agreement |
| `tools/validate/src/langatlas_validate/version.py` | **New:** 0.x version ceremony |
| `tools/validate/src/langatlas_validate/cli.py` | **Modified:** `version-bump` subcommand |
| `.github/workflows/ci.yml` | **Modified:** install/test the research package; auto-bump on main |

---

## Task 1: Package skeleton and the `research/` directory contract

**Files:**
- Create: `tools/research/pyproject.toml`
- Create: `tools/research/src/langatlas_research/__init__.py`
- Create: `tools/research/src/langatlas_research/paths.py`
- Create: `tools/research/src/langatlas_research/errors.py`
- Test: `tools/research/tests/test_paths.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `research_root(repo_root=None)`, `themes_path(repo_root=None)`,
  `cycles_dir/surveys_dir/debates_dir/reality_checks_dir/research_schema_dir(repo_root=None)`,
  `ensure_layout(repo_root=None) -> list[Path]`, and the exception hierarchy
  `ResearchError` → `SignOffMissing`, `SignOffStale`, `UnsourcedNode`, `DegenerateRule`,
  `InvalidDraft`, `InvalidTransition`, `UnknownTheme`.

- [ ] **Step 1: Write the failing test**

```python
# tools/research/tests/test_paths.py
from langatlas_research.paths import (
    cycles_dir, ensure_layout, research_root, surveys_dir, themes_path,
)


def test_paths_hang_off_the_given_repo_root(tmp_path):
    assert research_root(tmp_path) == tmp_path / "research"
    assert themes_path(tmp_path) == tmp_path / "research" / "themes.yaml"
    assert cycles_dir(tmp_path) == tmp_path / "research" / "cycles"


def test_ensure_layout_creates_every_directory_with_a_readme(tmp_path):
    created = ensure_layout(tmp_path)

    assert (tmp_path / "research" / "cycles" / "README.md").exists()
    assert (tmp_path / "research" / "surveys" / "README.md").exists()
    assert (tmp_path / "research" / "debates" / "README.md").exists()
    assert (tmp_path / "research" / "reality-checks" / "README.md").exists()
    assert (tmp_path / "research" / "schema").is_dir()
    assert created, "the first run reports what it created"


def test_ensure_layout_is_idempotent_and_never_rewrites_a_readme(tmp_path):
    ensure_layout(tmp_path)
    (surveys_dir(tmp_path) / "README.md").write_text("edited by hand\n")

    assert ensure_layout(tmp_path) == []
    assert (surveys_dir(tmp_path) / "README.md").read_text() == "edited by hand\n"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv --directory tools/research sync --extra dev && uv --directory tools/research run pytest tests/test_paths.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_research'`.

- [ ] **Step 3: Write the package and the implementation**

```toml
# tools/research/pyproject.toml
[project]
name = "langatlas-research"
version = "0.1.0"
description = "LangAtlas research phase — theme cycles, sign-off gate, and the node-minting path"
requires-python = ">=3.12"
license = "MIT"
dependencies = [
  "ruamel.yaml>=0.18",
  "jsonschema>=4.21",
  "langatlas-validate",
  "langatlas-commit",
  "langatlas-pipeline",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
langatlas-research = "langatlas_research.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/langatlas_research"]

[tool.uv.sources]
langatlas-validate = { path = "../validate", editable = true }
langatlas-commit = { path = "../commit", editable = true }
langatlas-pipeline = { path = "../pipeline", editable = true }

[tool.pytest.ini_options]
markers = ["git: creates throwaway git repositories and runs the real commit protocol"]
```

```python
# tools/research/src/langatlas_research/errors.py
class ResearchError(Exception):
    """Base for every failure this package raises deliberately."""


class SignOffMissing(ResearchError):
    """D27's hard checkpoint: this cycle has no developer sign-off at all."""


class SignOffStale(ResearchError):
    """The theme was edited after it was signed off, so the sign-off no longer
    describes what would run. The gate re-opens rather than silently passing."""


class UnsourcedNode(ResearchError):
    """D4/§6.1: a node with no (source, locator) evidence is not mintable."""


class DegenerateRule(ResearchError):
    """D64: a 1-antecedent Rule belongs in the matching edge type instead."""


class InvalidDraft(ResearchError):
    """The rendered record failed schema or normalization validation."""


class InvalidTransition(ResearchError):
    """Cycle status moves forward through the fixed ladder, never backward."""


class UnknownTheme(ResearchError):
    """A cycle names a theme that `research/themes.yaml` does not define."""
```

```python
# tools/research/src/langatlas_research/paths.py
"""Where the research phase's bookkeeping lives.

`research/` is *committed bookkeeping, not canonical store*: `iter_store_records`
deliberately does not walk it, and these artifacts validate against their own schemas under
`research/schema/` rather than against `ontology/schema/`'s closed `RECORD_KINDS`. Keeping
the two vocabularies separate is what stops a survey candidate — which is a lead, not a
fact — from ever looking like a mintable record."""
import os
from pathlib import Path

# src layout: .../tools/research/src/langatlas_research/paths.py -> parents[4] == repo root.
REPO_ROOT = Path(os.environ.get("LANGATLAS_ROOT", Path(__file__).resolve().parents[4]))

_READMES = {
    "cycles": "One file per theme cycle (`<NN>-<theme>.yaml`): the developer's sign-off, the\n"
              "cycle's rotating R5 language sample, its status, and the node ids it minted.\n"
              "Written by `langatlas-research cycle`; read by every R3-R6 runner and by\n"
              "`coverage report.py dossier`.\n",
    "surveys": "R3 candidate inventories (`<cycle>-<theme>.yaml`), one entry per candidate with\n"
               "1-3 evidence chunk ids and cross-book aliases. Written by the surveyor (Stage 3B);\n"
               "read by the ontologist (Stage 3C). Candidates are leads, never facts.\n",
    "debates": "R4 debate records (`<debate-id>.yaml`): proposer, two challengers, moderator\n"
               "resolution, typed challenges. Written by the debate machinery (Stage 3C); read by\n"
               "the controversy assessor (Stage 3D) and the D30 instrumentation scripts.\n",
    "reality-checks": "R5 structured findings (`<cycle>-<theme>.yaml`): unmappable features,\n"
                      "uninhabited dimension values, unfittable languages, exclusivity violations.\n"
                      "Written by the reality-check runner (Stage 3E); read by\n"
                      "`coverage report.py dossier` (Stage 3F) as the one dossier item that is not\n"
                      "pure computation.\n",
}


def _root(repo_root: Path | None) -> Path:
    return REPO_ROOT if repo_root is None else Path(repo_root)


def research_root(repo_root: Path | None = None) -> Path:
    return _root(repo_root) / "research"


def themes_path(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "themes.yaml"


def cycles_dir(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "cycles"


def surveys_dir(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "surveys"


def debates_dir(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "debates"


def reality_checks_dir(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "reality-checks"


def research_schema_dir(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "schema"


def ensure_layout(repo_root: Path | None = None) -> list[Path]:
    """Creates the `research/` tree if it is missing. Idempotent, and never rewrites an
    existing README — the directory READMEs are documentation the developer may edit.

    @param repo_root: repository root; defaults to this checkout.
    @returns: the paths this call created, empty when there was nothing to do."""
    created: list[Path] = []
    research_schema_dir(repo_root).mkdir(parents=True, exist_ok=True)
    for name, body in _READMES.items():
        directory = research_root(repo_root) / name
        if not directory.exists():
            directory.mkdir(parents=True)
            created.append(directory)
        readme = directory / "README.md"
        if not readme.exists():
            readme.write_text(body)
            created.append(readme)
    return created
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv --directory tools/research sync --extra dev && uv --directory tools/research run pytest -v`
Expected: 3 passed.

- [ ] **Step 5: Create the layout in the real repo and commit**

```bash
cd /home/terra/Projects/langatlas-kb
uv --directory tools/research run python -c \
  "from langatlas_research.paths import ensure_layout; print(ensure_layout())"
git add docs/superpowers/plans/2026-09-13-stage-3-theme-cycles.md \
        docs/superpowers/plans/2026-09-13-stage-3a-research-spine-and-minting.md \
        tools/research/ research/
git commit -m "feat(#stage-3a): add the research package and the research/ directory contract"
```

---

## Task 2: Research-artifact schemas and their validator

**Files:**
- Create: `research/schema/theme-registry.schema.json`
- Create: `research/schema/cycle.schema.json`
- Create: `tools/research/src/langatlas_research/schema.py`
- Test: `tools/research/tests/test_schema.py`

**Interfaces:**
- Consumes: Task 1's `research_schema_dir`, `research_root`.
- Produces: `validate_research_record(data: dict, kind: str) -> list[str]`,
  `validate_research_tree(repo_root=None) -> list[str]`, and the directory→kind map
  `DIR_KINDS = {"cycles": "cycle", "surveys": "survey", "debates": "debate",
  "reality-checks": "reality-check"}`. 3B/3C/3E add their schema files; this validator
  picks them up by filename with no code change.

- [x] **Step 1: Write the failing test**

```python
# tools/research/tests/test_schema.py
import json

import pytest

from langatlas_research.paths import cycles_dir, ensure_layout, research_schema_dir, surveys_dir
from langatlas_research.schema import validate_research_record, validate_research_tree

REPO = __import__("pathlib").Path(__file__).resolve().parents[3]


@pytest.fixture
def research_repo(tmp_path):
    ensure_layout(tmp_path)
    for name in ("theme-registry", "cycle"):
        (research_schema_dir(tmp_path) / f"{name}.schema.json").write_text(
            (REPO / "research" / "schema" / f"{name}.schema.json").read_text())
    return tmp_path


def test_a_valid_cycle_record_has_no_errors(research_repo):
    record = {"cycle": 1, "theme": "typing", "theme_digest": "0" * 16,
              "status": "drafted", "languages": ["python", "haskell"],
              "nodes_minted": [], "artifacts": {}}

    assert validate_research_record(record, "cycle", repo_root=research_repo) == []


def test_an_unknown_status_is_an_error(research_repo):
    record = {"cycle": 1, "theme": "typing", "theme_digest": "0" * 16,
              "status": "nearly-done", "languages": [], "nodes_minted": [], "artifacts": {}}

    errors = validate_research_record(record, "cycle", repo_root=research_repo)

    assert any("status" in e for e in errors), errors


def test_the_tree_walk_reports_the_offending_file(research_repo):
    (cycles_dir(research_repo) / "01-typing.yaml").write_text("cycle: 1\n")

    errors = validate_research_tree(research_repo)

    assert any("research/cycles/01-typing.yaml" in e for e in errors), errors


def test_a_populated_directory_with_no_schema_yet_is_a_loud_error(research_repo):
    (surveys_dir(research_repo) / "01-typing.yaml").write_text("candidates: []\n")

    errors = validate_research_tree(research_repo)

    assert any("survey.schema.json" in e for e in errors), errors
```

- [x] **Step 2: Run the test to verify it fails**

Run: `uv --directory tools/research run pytest tests/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_research.schema'`.

- [x] **Step 3: Write the schemas and the validator**

```json
// research/schema/theme-registry.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://langatlas.dev/research-schema/theme-registry",
  "type": "object",
  "additionalProperties": false,
  "required": ["themes"],
  "properties": {
    "themes": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["slug", "label", "summary"],
        "properties": {
          "slug": { "type": "string" },
          "label": { "type": "string" },
          "summary": { "type": "string" },
          "seed_terms": { "type": "array", "items": { "type": "string" } },
          "note": { "type": "string" }
        }
      }
    }
  }
}
```

```json
// research/schema/cycle.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://langatlas.dev/research-schema/cycle",
  "type": "object",
  "additionalProperties": false,
  "required": ["cycle", "theme", "theme_digest", "status", "languages", "nodes_minted",
               "artifacts"],
  "properties": {
    "cycle": { "type": "integer", "minimum": 1 },
    "theme": { "type": "string" },
    "theme_digest": { "type": "string", "pattern": "^[0-9a-f]{16}$" },
    "status": {
      "enum": ["drafted", "signed-off", "r3-done", "r4-done", "r5-done", "settled"]
    },
    "languages": { "type": "array", "items": { "type": "string" } },
    "signed_off": {
      "type": "object",
      "additionalProperties": false,
      "required": ["by", "date", "theme_digest"],
      "properties": {
        "by": { "type": "string" },
        "date": { "type": "string" },
        "theme_digest": { "type": "string", "pattern": "^[0-9a-f]{16}$" }
      }
    },
    "nodes_minted": { "type": "array", "items": { "type": "string" } },
    "artifacts": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "survey": { "type": "string" },
        "reality_check": { "type": "string" },
        "debates": { "type": "array", "items": { "type": "string" } }
      }
    }
  }
}
```

```python
# tools/research/src/langatlas_research/schema.py
"""Research artifacts validate against their own schemas, not against the canonical
store's `RECORD_KINDS`. `validate_research_tree` maps a directory to a kind and validates
every file in it — a later sub-plan adds `survey.schema.json` or `debate.schema.json` and
this module picks it up with no code change. A directory that holds files but has no schema
yet is a hard error rather than a silent skip: an unvalidated artifact directory is exactly
how a format drifts."""
import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from ruamel.yaml import YAML

from langatlas_research.paths import research_root, research_schema_dir

DIR_KINDS = {"cycles": "cycle", "surveys": "survey", "debates": "debate",
             "reality-checks": "reality-check"}

_yaml = YAML(typ="safe")


@lru_cache(maxsize=None)
def _validator(schema_path: str, mtime: float) -> Draft202012Validator:
    return Draft202012Validator(json.loads(Path(schema_path).read_text()))


def _load_validator(kind: str, repo_root: Path | None) -> Draft202012Validator | None:
    path = research_schema_dir(repo_root) / f"{kind}.schema.json"
    if not path.exists():
        return None
    return _validator(str(path), path.stat().st_mtime)


def validate_research_record(data: dict, kind: str, *,
                             repo_root: Path | None = None) -> list[str]:
    """@returns: error strings, one per violation, empty when the record is valid.
    @raises FileNotFoundError: when no schema for `kind` is committed yet."""
    validator = _load_validator(kind, repo_root)
    if validator is None:
        raise FileNotFoundError(
            f"research/schema/{kind}.schema.json is missing — the sub-plan that writes"
            f" {kind} records must ship its schema")
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in sorted(validator.iter_errors(data), key=str)]


def validate_research_tree(repo_root: Path | None = None) -> list[str]:
    """Validates `research/themes.yaml` and every artifact directory. @returns: error
    strings prefixed with the offending repo-relative path."""
    errors: list[str] = []
    root = research_root(repo_root)
    if not root.exists():
        return errors

    registry = root / "themes.yaml"
    if registry.exists():
        errors.extend(f"research/themes.yaml: {e}" for e in validate_research_record(
            _yaml.load(registry.read_text()) or {}, "theme-registry", repo_root=repo_root))

    for name, kind in DIR_KINDS.items():
        directory = root / name
        files = sorted(directory.glob("*.yaml")) if directory.exists() else []
        if not files:
            continue
        if _load_validator(kind, repo_root) is None:
            errors.append(f"research/{name}: no schema (research/schema/{kind}.schema.json)"
                          f" — the sub-plan that writes this directory must ship one")
            continue
        for path in files:
            data = _yaml.load(path.read_text()) or {}
            errors.extend(f"research/{name}/{path.name}: {e}"
                          for e in validate_research_record(data, kind, repo_root=repo_root))
    return errors
```

- [x] **Step 4: Run the test to verify it passes**

Run: `uv --directory tools/research run pytest -v`
Expected: 7 passed.

- [x] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-09-13-stage-3a-research-spine-and-minting.md \
        research/schema/ tools/research/
git commit -m "feat(#stage-3a): validate research artifacts against their own schemas"
```

---

## Task 3: The seeded theme list and its digest

**Files:**
- Create: `research/themes.yaml`
- Create: `tools/research/src/langatlas_research/themes.py`
- Test: `tools/research/tests/test_themes.py`

**Interfaces:**
- Consumes: Task 1's `themes_path`, Task 2's `validate_research_record`.
- Produces: `Theme(slug, label, summary, seed_terms, note)`,
  `load_themes(repo_root=None) -> dict[str, Theme]`, `theme_digest(theme: Theme) -> str`
  (16 lowercase hex chars). Task 4's sign-off gate is built on `theme_digest`.

**Why a digest:** the sign-off is the one hard human checkpoint in Stage 3 (D27). Binding it to a
digest of the exact theme entry means editing a theme's scope after sign-off invalidates the
sign-off instead of silently inheriting it — §7.4 explicitly makes the final theme list itself an
R3 deliverable, so theme edits mid-stage are expected, not exceptional.

- [x] **Step 1: Write the failing test**

```python
# tools/research/tests/test_themes.py
import pytest

from langatlas_research.paths import REPO_ROOT
from langatlas_research.themes import Theme, load_themes, theme_digest


def test_the_committed_seed_list_covers_the_twelve_spec_themes():
    themes = load_themes(REPO_ROOT)

    assert "typing" in themes
    assert "qualities-vocabulary" in themes
    assert len(themes) >= 12


def test_the_digest_is_sixteen_hex_chars_and_stable_across_cosmetic_whitespace():
    a = Theme(slug="typing", label="Typing", summary="Static and dynamic typing.",
              seed_terms=("type system", "type inference"), note="")
    b = Theme(slug="typing", label="Typing", summary="  Static and  dynamic typing. ",
              seed_terms=("type system", "type inference"), note="")

    assert len(theme_digest(a)) == 16
    assert all(c in "0123456789abcdef" for c in theme_digest(a))
    assert theme_digest(a) == theme_digest(b)


def test_the_digest_changes_when_the_scope_changes():
    a = Theme(slug="typing", label="Typing", summary="Static and dynamic typing.",
              seed_terms=("type system",), note="")
    b = Theme(slug="typing", label="Typing", summary="Static typing only.",
              seed_terms=("type system",), note="")

    assert theme_digest(a) != theme_digest(b)


def test_loading_an_invalid_registry_raises(tmp_path):
    from langatlas_research.paths import ensure_layout, themes_path
    ensure_layout(tmp_path)
    themes_path(tmp_path).write_text("themes: [{slug: typing}]\n")

    with pytest.raises(ValueError, match="label"):
        load_themes(tmp_path)
```

- [x] **Step 2: Run the test to verify it fails**

Run: `uv --directory tools/research run pytest tests/test_themes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_research.themes'`.

- [x] **Step 3: Write the seed list and the loader**

```yaml
# research/themes.yaml
# The R3 theme list (context/spec.md §7.4). Seeded from the spec's twelve, NOT frozen:
# §7.4 makes the final theme list itself an early R3 deliverable, so the surveyor may
# propose amendments. Amending a theme changes its digest, which re-opens the sign-off
# gate for any cycle that signed the old text (D27).
themes:
  - slug: typing
    label: Typing
    summary: >-
      Type systems, checking discipline, inference, polymorphism and the design choices
      that distinguish them.
    seed_terms: [type system, static typing, dynamic typing, type inference, generics,
                 subtyping, algebraic data types]
  - slug: memory-management
    label: Memory management
    summary: >-
      How storage is allocated, reclaimed and made safe: manual management, garbage
      collection, ownership, regions, reference counting.
    seed_terms: [garbage collection, manual memory management, ownership, borrow checking,
                 reference counting, region inference]
  - slug: concurrency
    label: Concurrency
    summary: >-
      Models for concurrent and parallel execution and the synchronization they imply.
    seed_terms: [threads, actors, message passing, communicating sequential processes,
                 software transactional memory, async await, data race freedom]
  - slug: higher-order-programming
    label: Higher-order programming
    summary: >-
      First-class functions, closures, currying and the abstractions built from them.
    seed_terms: [first-class functions, closures, lambda, currying, partial application,
                 higher-order function]
  - slug: adts-and-pattern-matching
    label: ADTs and pattern matching
    summary: >-
      Algebraic data types, variants, destructuring and exhaustiveness.
    seed_terms: [algebraic data type, sum type, product type, pattern matching,
                 exhaustiveness checking, destructuring]
  - slug: modules
    label: Modules
    summary: >-
      Modularity, namespacing, interfaces, separate compilation and functors.
    seed_terms: [module system, namespace, interface, separate compilation, functor,
                 information hiding]
  - slug: metaprogramming
    label: Metaprogramming
    summary: >-
      Macros, reflection, staged computation and code generation.
    seed_terms: [macro, hygienic macro, reflection, staged computation, code generation,
                 template metaprogramming]
  - slug: evaluation-and-parameter-passing
    label: Evaluation and parameter passing
    summary: >-
      Evaluation order, strictness, and how arguments reach a callee.
    seed_terms: [call by value, call by reference, call by name, lazy evaluation,
                 strictness, evaluation order]
  - slug: effects-and-exceptions
    label: Effects and exceptions
    summary: >-
      Effect tracking, exception handling, error values and resource safety.
    seed_terms: [exception handling, checked exceptions, effect system, error values,
                 resource acquisition is initialization, algebraic effects]
  - slug: dispatch-and-inheritance
    label: Dispatch and inheritance
    summary: >-
      Method dispatch, subtyping relationships, inheritance, traits and protocols.
    seed_terms: [dynamic dispatch, single dispatch, multiple dispatch, inheritance,
                 mixin, trait, protocol, interface default method]
  - slug: syntax-layer-constructs
    label: Syntax-layer constructs
    summary: >-
      Layer-1 surface constructs: block structure, significant whitespace, operators,
      literals and the grammar-level choices they encode.
    seed_terms: [significant whitespace, block delimiter, operator overloading,
                 literal syntax, expression-oriented syntax]
  - slug: qualities-vocabulary
    label: Qualities vocabulary
    summary: >-
      The controlled quality vocabulary itself (readability, safety, performance,
      learnability, ...) and what the literature actually supports about it.
    seed_terms: [readability, maintainability, safety, performance, learnability,
                 expressiveness, empirical evidence]
    note: >-
      Feeds ontology/taxonomy/qualities.yaml rather than features/; Kaijanaho (2015) is
      the ratified empirical-evidence source for quality edges.
```

```python
# tools/research/src/langatlas_research/themes.py
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.paths import themes_path
from langatlas_research.schema import validate_research_record
from langatlas_validate.normalize import normalize_value

_yaml = YAML(typ="safe")
DIGEST_HEX_LEN = 16


@dataclass(frozen=True)
class Theme:
    slug: str
    label: str
    summary: str
    seed_terms: tuple[str, ...] = ()
    note: str = ""


def theme_digest(theme: Theme) -> str:
    """Content key over the parts of a theme a sign-off is an opinion *about*.

    Whitespace-insensitive (§3.5's normalization rules), so reflowing a summary does not
    re-open the gate, while changing what the theme covers does.

    @returns: 16 lowercase hex chars."""
    body = json.dumps({
        "slug": theme.slug,
        "label": normalize_value(theme.label),
        "summary": normalize_value(theme.summary),
        "seed_terms": sorted(normalize_value(t) for t in theme.seed_terms),
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:DIGEST_HEX_LEN]


def load_themes(repo_root: Path | None = None) -> dict[str, Theme]:
    """@returns: themes keyed by slug, in file order.
    @raises ValueError: when the registry does not satisfy its schema."""
    data = _yaml.load(themes_path(repo_root).read_text()) or {}
    errors = validate_research_record(data, "theme-registry", repo_root=repo_root)
    if errors:
        raise ValueError("research/themes.yaml is invalid: " + "; ".join(errors))
    return {
        entry["slug"]: Theme(
            slug=entry["slug"], label=entry["label"], summary=entry["summary"],
            seed_terms=tuple(entry.get("seed_terms", ())), note=entry.get("note", ""))
        for entry in data["themes"]
    }
```

- [x] **Step 4: Run the test to verify it passes**

Run: `uv --directory tools/research run pytest -v`
Expected: 11 passed.

- [x] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-09-13-stage-3a-research-spine-and-minting.md \
        research/themes.yaml tools/research/
git commit -m "feat(#stage-3a): seed the R3 theme list and key it by a sign-off digest"
```

---

## Task 4: Cycle records, the status ladder, and the sign-off gate

**Files:**
- Create: `tools/research/src/langatlas_research/cycle.py`
- Test: `tools/research/tests/test_cycle.py`

**Interfaces:**
- Consumes: Task 2's `validate_research_record`, Task 3's `load_themes` / `theme_digest`,
  Task 5's `plan_languages` (imported lazily so Task 4 can be implemented first — until Task 5
  lands, `new_cycle` requires an explicit `languages=`).
- Produces:
  - `CYCLE_STATUSES = ("drafted", "signed-off", "r3-done", "r4-done", "r5-done", "settled")`
  - `Cycle` (frozen dataclass: `number: int`, `theme: str`, `theme_digest: str`, `status: str`,
    `languages: tuple[str, ...]`, `signed_off: dict | None`, `nodes_minted: tuple[str, ...]`,
    `artifacts: dict`), with `.slug -> "<NN>-<theme>"`
  - `new_cycle(number, theme, *, repo_root=None, languages=None) -> Cycle`
  - `load_cycle(number, *, repo_root=None) -> Cycle`
  - `save_cycle(cycle, *, repo_root=None) -> Path`
  - `sign_off(cycle, *, by, date, repo_root=None) -> Cycle`
  - `require_sign_off(cycle, *, repo_root=None) -> None`
  - `advance(cycle, status) -> Cycle`
  - `record_minted(cycle, node_ids, *, repo_root=None) -> Cycle`
- 3B/3C/3E all call `require_sign_off` as their first act.

**Note on who may write a sign-off:** nothing technically stops an agent from writing the block —
git has no per-field ACL, and D1 rejects a PR gate. The gate is a *checkpoint artifact*: the
`signed_off.by` value is the developer's git identity, it appears in a diff the developer reads,
and the digest binding makes a forged or stale sign-off visible rather than invisible. Do not add
enforcement theater on top; state the property and move on.

- [x] **Step 1: Write the failing test**

```python
# tools/research/tests/test_cycle.py
import pytest

from langatlas_research.cycle import (
    Cycle, advance, load_cycle, new_cycle, record_minted, require_sign_off, save_cycle, sign_off,
)
from langatlas_research.errors import (
    InvalidTransition, SignOffMissing, SignOffStale, UnknownTheme,
)
from langatlas_research.paths import REPO_ROOT, cycles_dir, ensure_layout, themes_path


@pytest.fixture
def repo(tmp_path):
    ensure_layout(tmp_path)
    (tmp_path / "research" / "schema").mkdir(parents=True, exist_ok=True)
    for name in ("theme-registry", "cycle"):
        (tmp_path / "research" / "schema" / f"{name}.schema.json").write_text(
            (REPO_ROOT / "research" / "schema" / f"{name}.schema.json").read_text())
    themes_path(tmp_path).write_text(themes_path(REPO_ROOT).read_text())
    return tmp_path


def test_new_cycle_writes_a_valid_file_named_by_number_and_theme(repo):
    cycle = new_cycle(1, "typing", repo_root=repo, languages=("python", "haskell"))

    assert cycle.slug == "01-typing"
    assert (cycles_dir(repo) / "01-typing.yaml").exists()
    assert cycle.status == "drafted"
    assert load_cycle(1, repo_root=repo) == cycle


def test_a_cycle_for_an_unknown_theme_is_refused(repo):
    with pytest.raises(UnknownTheme):
        new_cycle(1, "quantum-typing", repo_root=repo, languages=("python",))


def test_an_unsigned_cycle_fails_the_gate(repo):
    cycle = new_cycle(1, "typing", repo_root=repo, languages=("python",))

    with pytest.raises(SignOffMissing):
        require_sign_off(cycle, repo_root=repo)


def test_signing_off_passes_the_gate_and_advances_the_status(repo):
    cycle = new_cycle(1, "typing", repo_root=repo, languages=("python",))

    signed = sign_off(cycle, by="Michal Dolezel", date="2026-09-20", repo_root=repo)

    assert signed.status == "signed-off"
    require_sign_off(signed, repo_root=repo)


def test_editing_the_theme_after_sign_off_re_opens_the_gate(repo):
    cycle = sign_off(new_cycle(1, "typing", repo_root=repo, languages=("python",)),
                     by="Michal Dolezel", date="2026-09-20", repo_root=repo)
    text = themes_path(repo).read_text().replace(
        "Type systems, checking discipline", "Only nominal type systems")
    themes_path(repo).write_text(text)

    with pytest.raises(SignOffStale):
        require_sign_off(cycle, repo_root=repo)


def test_status_only_moves_forward(repo):
    cycle = advance(new_cycle(1, "typing", repo_root=repo, languages=("python",)), "signed-off")
    cycle = advance(cycle, "r3-done")

    with pytest.raises(InvalidTransition):
        advance(cycle, "signed-off")


def test_recording_minted_nodes_is_append_only_and_deduped(repo):
    cycle = new_cycle(1, "typing", repo_root=repo, languages=("python",))

    cycle = record_minted(cycle, ["pattern-matching", "type-inference"], repo_root=repo)
    cycle = record_minted(cycle, ["type-inference", "row-polymorphism"], repo_root=repo)

    assert cycle.nodes_minted == ("pattern-matching", "row-polymorphism", "type-inference")
    assert load_cycle(1, repo_root=repo).nodes_minted == cycle.nodes_minted
```

- [x] **Step 2: Run the test to verify it fails**

Run: `uv --directory tools/research run pytest tests/test_cycle.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_research.cycle'`.

- [x] **Step 3: Write the implementation**

```python
# tools/research/src/langatlas_research/cycle.py
"""One file per theme cycle. The cycle record is the only place that knows which nodes a
theme minted: node schemas have no `theme` field (and `additionalProperties: false` means
they cannot grow one casually), so theme membership lives here, where 3F's settled-theme
ceremony and `coverage report.py dossier` read it."""
import io
from dataclasses import dataclass, replace
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.errors import (
    InvalidTransition, SignOffMissing, SignOffStale, UnknownTheme,
)
from langatlas_research.paths import cycles_dir
from langatlas_research.schema import validate_research_record
from langatlas_research.themes import load_themes, theme_digest

CYCLE_STATUSES = ("drafted", "signed-off", "r3-done", "r4-done", "r5-done", "settled")

_yaml = YAML(typ="safe")


def _dumper() -> YAML:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    return yaml


@dataclass(frozen=True)
class Cycle:
    number: int
    theme: str
    theme_digest: str
    status: str
    languages: tuple[str, ...]
    nodes_minted: tuple[str, ...] = ()
    artifacts: dict | None = None
    signed_off: dict | None = None

    @property
    def slug(self) -> str:
        return f"{self.number:02d}-{self.theme}"

    def as_dict(self) -> dict:
        data = {"cycle": self.number, "theme": self.theme,
                "theme_digest": self.theme_digest, "status": self.status,
                "languages": list(self.languages),
                "nodes_minted": list(self.nodes_minted),
                "artifacts": dict(self.artifacts or {})}
        if self.signed_off is not None:
            data["signed_off"] = dict(self.signed_off)
        return data


def cycle_path(number: int, theme: str, repo_root: Path | None = None) -> Path:
    return cycles_dir(repo_root) / f"{number:02d}-{theme}.yaml"


def _current_digest(theme: str, repo_root: Path | None) -> str:
    themes = load_themes(repo_root)
    if theme not in themes:
        raise UnknownTheme(f"{theme!r} is not in research/themes.yaml")
    return theme_digest(themes[theme])


def new_cycle(number: int, theme: str, *, repo_root: Path | None = None,
              languages: tuple[str, ...] | None = None) -> Cycle:
    """Drafts cycle `number` for `theme`. @raises UnknownTheme: unknown theme slug."""
    if languages is None:
        from langatlas_research.rotation import plan_languages
        languages = plan_languages(number)
    cycle = Cycle(number=number, theme=theme,
                  theme_digest=_current_digest(theme, repo_root), status="drafted",
                  languages=tuple(languages), nodes_minted=(), artifacts={})
    save_cycle(cycle, repo_root=repo_root)
    return cycle


def save_cycle(cycle: Cycle, *, repo_root: Path | None = None) -> Path:
    """@raises ValueError: when the record does not satisfy cycle.schema.json."""
    data = cycle.as_dict()
    errors = validate_research_record(data, "cycle", repo_root=repo_root)
    if errors:
        raise ValueError(f"cycle {cycle.slug} is invalid: " + "; ".join(errors))
    path = cycle_path(cycle.number, cycle.theme, repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    _dumper().dump(data, buf)
    path.write_text(buf.getvalue())
    return path


def load_cycle(number: int, *, repo_root: Path | None = None) -> Cycle:
    """@raises FileNotFoundError: when no cycle with that number is committed."""
    matches = sorted(cycles_dir(repo_root).glob(f"{number:02d}-*.yaml"))
    if not matches:
        raise FileNotFoundError(f"no cycle {number:02d} in research/cycles/")
    data = _yaml.load(matches[0].read_text())
    return Cycle(number=data["cycle"], theme=data["theme"],
                 theme_digest=data["theme_digest"], status=data["status"],
                 languages=tuple(data["languages"]),
                 nodes_minted=tuple(data["nodes_minted"]),
                 artifacts=dict(data.get("artifacts") or {}),
                 signed_off=data.get("signed_off"))


def sign_off(cycle: Cycle, *, by: str, date: str, repo_root: Path | None = None) -> Cycle:
    """D27's hard checkpoint. Re-stamps the digest from the current theme text, so a
    sign-off always describes the theme as it stands at the moment of signing."""
    digest = _current_digest(cycle.theme, repo_root)
    signed = replace(cycle, theme_digest=digest, status="signed-off",
                     signed_off={"by": by, "date": date, "theme_digest": digest})
    save_cycle(signed, repo_root=repo_root)
    return signed


def require_sign_off(cycle: Cycle, *, repo_root: Path | None = None) -> None:
    """The gate every R3-R6 runner calls first.

    @raises SignOffMissing: no sign-off block.
    @raises SignOffStale: the theme changed after it was signed — the developer signed a
        different scope than the one that would now run."""
    if not cycle.signed_off:
        raise SignOffMissing(
            f"cycle {cycle.slug} has no developer sign-off (D27): run"
            f" `langatlas-research cycle sign-off {cycle.number}` first")
    current = _current_digest(cycle.theme, repo_root)
    if cycle.signed_off.get("theme_digest") != current:
        raise SignOffStale(
            f"cycle {cycle.slug} was signed off against theme digest"
            f" {cycle.signed_off.get('theme_digest')}, but research/themes.yaml now reads"
            f" {current} — re-sign the cycle before running it")


def advance(cycle: Cycle, status: str) -> Cycle:
    """@raises InvalidTransition: for an unknown status or a backward move. Returns the
    updated cycle; the caller saves it (so a runner can advance only after its own work
    actually landed)."""
    if status not in CYCLE_STATUSES:
        raise InvalidTransition(f"unknown cycle status: {status!r}")
    if CYCLE_STATUSES.index(status) <= CYCLE_STATUSES.index(cycle.status):
        raise InvalidTransition(
            f"cycle {cycle.slug} is already at {cycle.status!r}; cannot move to {status!r}")
    return replace(cycle, status=status)


def record_minted(cycle: Cycle, node_ids, *, repo_root: Path | None = None) -> Cycle:
    """Append-only, sorted, deduped — the theme-membership list 3F's settled-theme
    ceremony reads."""
    merged = tuple(sorted(set(cycle.nodes_minted) | set(node_ids)))
    updated = replace(cycle, nodes_minted=merged)
    save_cycle(updated, repo_root=repo_root)
    return updated
```

- [x] **Step 4: Run the test to verify it passes**

Run: `uv --directory tools/research run pytest -v`
Expected: 18 passed.

- [x] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-09-13-stage-3a-research-spine-and-minting.md tools/research/
git commit -m "feat(#stage-3a): add cycle records and the digest-bound developer sign-off gate"
```

---

## Task 5: The R5 rotating-language planner

**Files:**
- Create: `tools/research/src/langatlas_research/rotation.py`
- Test: `tools/research/tests/test_rotation.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SPREAD_ORDER: tuple[str, ...]` (the D28 15-language set, family-interleaved),
  `PARADIGM_FAMILIES: dict[str, str]`, `plan_languages(cycle_number: int, *, size: int = 5) ->
  tuple[str, ...]`. Task 4's `new_cycle` calls it; 3E's reality-check runner reads the result off
  the cycle record, never re-plans.

**Design:** D27 ratified the *rotating 4–5-language sample per cycle*, not the full 15-language set
every cycle, and §7.4 requires paradigm spread. The order below interleaves paradigm families, so
any consecutive window is spread by construction; cycle N takes a `size`-wide window starting at
`(N-1) * size`, wrapping. At the default size 5 that means cycles 1–3 cover all fifteen exactly
once before any language repeats.

- [x] **Step 1: Write the failing test**

```python
# tools/research/tests/test_rotation.py
from langatlas_research.rotation import PARADIGM_FAMILIES, SPREAD_ORDER, plan_languages


def test_the_spread_order_is_exactly_the_d28_fifteen():
    assert len(SPREAD_ORDER) == 15
    assert set(SPREAD_ORDER) == set(PARADIGM_FAMILIES)
    assert {"python", "c", "java", "rust", "haskell", "prolog"} <= set(SPREAD_ORDER)


def test_a_plan_is_deterministic():
    assert plan_languages(4) == plan_languages(4)


def test_the_first_three_cycles_cover_all_fifteen_languages_exactly_once():
    drawn = plan_languages(1) + plan_languages(2) + plan_languages(3)

    assert sorted(drawn) == sorted(SPREAD_ORDER)


def test_every_plan_spans_at_least_three_paradigm_families():
    for cycle in range(1, 13):
        plan = plan_languages(cycle)
        families = {PARADIGM_FAMILIES[lang] for lang in plan}
        assert len(plan) == len(set(plan)), plan
        assert len(families) >= 3, (cycle, plan, families)


def test_a_four_language_sample_is_supported():
    plan = plan_languages(2, size=4)

    assert len(plan) == 4
    assert len({PARADIGM_FAMILIES[lang] for lang in plan}) >= 3
```

- [x] **Step 2: Run the test to verify it fails**

Run: `uv --directory tools/research run pytest tests/test_rotation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_research.rotation'`.

- [x] **Step 3: Write the implementation**

```python
# tools/research/src/langatlas_research/rotation.py
"""R5's rotating sample (D27: 4-5 languages per cycle, not the full set every cycle).

The order is family-interleaved rather than alphabetical or TIOBE-ranked, because the
property R5 needs is *paradigm spread inside one cycle* -- a cycle that checks five
curly-brace imperative languages cannot surface an unfittable language or an uninhabited
dimension value, which is the whole point of the exercise (§7.4)."""

PARADIGM_FAMILIES = {
    "c": "systems", "cpp": "systems", "rust": "systems", "go": "systems",
    "java": "oop-managed", "csharp": "oop-managed", "swift": "oop-managed",
    "python": "scripting", "javascript": "scripting", "r": "scripting",
    "haskell": "functional", "ocaml": "functional",
    "erlang": "actor", "elixir": "actor",
    "prolog": "logic",
}

# Round-robin across families, so consecutive windows are spread by construction.
SPREAD_ORDER = (
    "c", "java", "python", "haskell", "erlang",
    "prolog", "cpp", "csharp", "javascript", "ocaml",
    "elixir", "rust", "swift", "r", "go",
)


def plan_languages(cycle_number: int, *, size: int = 5) -> tuple[str, ...]:
    """@param cycle_number: 1-based cycle number.
    @param size: sample width; D27 ratified 4-5.
    @returns: the cycle's language sample, deterministic for a given (number, size).
    @raises ValueError: for a non-positive cycle number or an out-of-range size."""
    if cycle_number < 1:
        raise ValueError(f"cycle numbers are 1-based: {cycle_number}")
    if not 1 <= size <= len(SPREAD_ORDER):
        raise ValueError(f"sample size out of range: {size}")
    start = ((cycle_number - 1) * size) % len(SPREAD_ORDER)
    return tuple(SPREAD_ORDER[(start + offset) % len(SPREAD_ORDER)] for offset in range(size))
```

- [x] **Step 4: Run the test to verify it passes**

Run: `uv --directory tools/research run pytest -v`
Expected: 23 passed.

- [x] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-09-13-stage-3a-research-spine-and-minting.md tools/research/
git commit -m "feat(#stage-3a): plan R5's rotating paradigm-spread language sample"
```

---

## Task 6: Drafts and the renderer — concepts and features

**Files:**
- Create: `tools/research/src/langatlas_research/drafts.py`
- Create: `tools/research/src/langatlas_research/mint.py`
- Test: `tools/research/tests/test_mint_nodes.py`

**Interfaces:**
- Consumes: `langatlas_validate.schema.validate_record`,
  `langatlas_validate.normalize.normalize_record`, `langatlas_validate.ids.is_valid_slug`.
- Produces:
  - `Evidence(source: str, locator: str, quote: str | None = None)` with `.as_entry() -> dict`
  - `Proposer(agent: str, model: str, prompt_version: str)` with `.as_dict() -> dict`
  - `ConceptDraft(id, name, summary, evidence, proposer, chat_run_id, slug=None,
    excluded_rationale=None, debate_id=None, claim_origin="source-derived",
    candidate_source="internal-survey")`
  - `FeatureDraft(id, name, layer, summary, evidence, proposer, chat_run_id, slug=None,
    dimension=None, cross_cutting=False, aliases=(), realizes=(), debate_id=None,
    claim_origin="source-derived", candidate_source="internal-survey")`
  - `MintedRecord(path: str, text: str, kind: str, node_ids: tuple[str, ...],
    base_digest: str | None)`
  - `render_draft(draft, *, repo_root=None) -> MintedRecord`
- 3C's ontologist builds `FeatureDraft`/`ConceptDraft` objects and calls nothing else.

**Why `render_draft` never writes:** landing is Task 9's job and owns the retry loop. Keeping
rendering pure means the renderer is testable without git and re-runnable after a rebase, which
is exactly what the shared-file mints in Task 8 need.

- [ ] **Step 1: Write the failing test**

```python
# tools/research/tests/test_mint_nodes.py
import pytest
from ruamel.yaml import YAML

from langatlas_research.drafts import ConceptDraft, Evidence, FeatureDraft, Proposer
from langatlas_research.errors import InvalidDraft, UnsourcedNode
from langatlas_research.mint import render_draft

yaml = YAML(typ="safe")

PROPOSER = Proposer(agent="ontologist", model="claude-opus-5", prompt_version="v1")
EVIDENCE = (Evidence(source="vanroy-haridi-2003", locator="p. 142",
                     quote="Pattern matching selects a clause by the shape of a value."),)


def _feature(**overrides) -> FeatureDraft:
    base = dict(id="pattern-matching", name="Pattern matching", layer=2,
                summary="Selection of a branch by the structural shape of a value.",
                evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0001")
    return FeatureDraft(**(base | overrides))


def test_a_feature_renders_to_its_spec_path_and_validates():
    minted = render_draft(_feature())

    assert minted.path == "features/pattern-matching.yaml"
    assert minted.kind == "feature"
    assert minted.node_ids == ("pattern-matching",)
    data = yaml.load(minted.text)
    assert data["slug"] == "pattern-matching"
    assert data["summary"]["sources"][0]["source"] == "vanroy-haridi-2003"
    assert data["provenance"]["claim_origin"] == "source-derived"
    assert data["provenance"]["chat_run_id"] == "r4-typing-0001"


def test_the_rendered_text_is_already_normalized():
    from langatlas_validate.normalize import normalize_record

    minted = render_draft(_feature())

    assert normalize_record(minted.text, "feature") == minted.text


def test_an_unsourced_node_is_refused():
    with pytest.raises(UnsourcedNode, match="pattern-matching"):
        render_draft(_feature(evidence=()))


def test_a_layer_three_feature_without_a_dimension_is_refused():
    with pytest.raises(InvalidDraft, match="dimension"):
        render_draft(_feature(layer=3))


def test_a_layer_three_feature_with_a_dimension_validates():
    minted = render_draft(_feature(layer=3, dimension="typing-discipline"))

    assert yaml.load(minted.text)["dimension"] == "typing-discipline"


def test_an_invalid_id_is_refused_before_the_schema_sees_it():
    with pytest.raises(InvalidDraft, match="slug"):
        render_draft(_feature(id="Pattern Matching"))


def test_a_concept_renders_with_its_excluded_rationale():
    minted = render_draft(ConceptDraft(
        id="scope", name="Scope", summary="The region of a program where a binding is visible.",
        evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0002",
        excluded_rationale="Staged as a Concept; atomizes into features through an ordinary split."))

    assert minted.path == "concepts/scope.yaml"
    assert "excluded_rationale" in yaml.load(minted.text)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv --directory tools/research run pytest tests/test_mint_nodes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_research.drafts'`.

- [ ] **Step 3: Write the implementation**

```python
# tools/research/src/langatlas_research/drafts.py
"""The shape every Stage 3 agent role produces. Deliberately dumb data: no I/O, no
provider, no validation — so a role's output can be logged, replayed and diffed before
anything touches the store."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Evidence:
    """One entry in a record's `sources:` list (§3.4). `locator` is REQUIRED — D4's
    source-first rule has no exception, and a quote is optional and capped at ~50 words
    (D14)."""
    source: str
    locator: str
    quote: str | None = None

    def as_entry(self) -> dict:
        entry = {"source": self.source, "locator": self.locator}
        if self.quote:
            entry["quote"] = self.quote
        return entry


@dataclass(frozen=True)
class Proposer:
    agent: str
    model: str
    prompt_version: str

    def as_dict(self) -> dict:
        return {"agent": self.agent, "model": self.model,
                "prompt_version": self.prompt_version}


@dataclass(frozen=True)
class _NodeDraft:
    id: str
    name: str
    summary: str
    evidence: tuple[Evidence, ...]
    proposer: Proposer
    chat_run_id: str
    slug: str | None = None
    debate_id: str | None = None
    claim_origin: str = "source-derived"
    candidate_source: str = "internal-survey"


@dataclass(frozen=True)
class ConceptDraft(_NodeDraft):
    excluded_rationale: str | None = None


@dataclass(frozen=True)
class FeatureDraft(_NodeDraft):
    layer: int = 2
    dimension: str | None = None
    cross_cutting: bool = False
    aliases: tuple[str, ...] = ()
    realizes: tuple[str, ...] = ()
```

```python
# tools/research/src/langatlas_research/mint.py
"""Drafts -> validated, normalized record text at its §3.3 path.

Pure: nothing here writes a file or runs git. `land.py` owns landing, so a render can be
re-run after a rebase — which is how a shared-file mint (taxonomy.py) survives losing a
race without clobbering the winner."""
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.drafts import ConceptDraft, FeatureDraft
from langatlas_research.errors import InvalidDraft, UnsourcedNode
from langatlas_validate.ids import is_valid_slug
from langatlas_validate.normalize import normalize_record
from langatlas_validate.schema import validate_record


@dataclass(frozen=True)
class MintedRecord:
    """@param path: repo-relative record path (what `land_record` commits).
    @param text: normalized YAML, already schema-valid.
    @param kind: the `RECORD_KINDS` value this validated against.
    @param node_ids: the node ids this record introduces, for cycle bookkeeping.
    @param base_digest: for a shared-file mint, the SHA-256 of the file content this
        render was based on — `land_drafts` re-renders when it no longer matches. `None`
        for one-file-per-record mints, which have no read-modify-write hazard."""
    path: str
    text: str
    kind: str
    node_ids: tuple[str, ...]
    base_digest: str | None = None


def dump_yaml(data: dict) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def content_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def finish(data: dict, *, path: str, kind: str, node_ids: tuple[str, ...],
           base_digest: str | None = None) -> MintedRecord:
    """Shared tail of every record mint: validate, normalize, wrap.

    @raises InvalidDraft: with every schema and slug error the record has, at once —
        an agent fixing one error at a time burns a session per error."""
    errors = validate_record(data, kind)
    if errors:
        raise InvalidDraft(f"{path}: " + "; ".join(errors))
    text = normalize_record(dump_yaml(data), kind)
    return MintedRecord(path=path, text=text, kind=kind, node_ids=node_ids,
                        base_digest=base_digest)


def _provenance(draft) -> dict:
    provenance = {"proposer": draft.proposer.as_dict(),
                  "claim_origin": draft.claim_origin,
                  "chat_run_id": draft.chat_run_id,
                  "candidate_source": draft.candidate_source}
    if draft.debate_id is not None:
        provenance["debate_id"] = draft.debate_id
    return provenance


def _fact_block(draft) -> dict:
    if not draft.evidence:
        raise UnsourcedNode(
            f"{draft.id}: a node needs at least one (source, locator) (D4/§6.1) — priors"
            f" steer where to look, they never make a fact")
    return {"text": draft.summary,
            "sources": [e.as_entry() for e in draft.evidence]}


def _require_id(draft) -> str:
    if not is_valid_slug(draft.id):
        raise InvalidDraft(f"{draft.id!r}: invalid slug/id (§3.5: [a-z0-9]+(-[a-z0-9]+)*,"
                           f" <=48 chars, no leading digit)")
    return draft.id


def render_draft(draft, *, repo_root: Path | None = None) -> MintedRecord:
    """@raises UnsourcedNode, InvalidDraft, DegenerateRule: per the draft's own rules.
    @raises TypeError: for an unknown draft type."""
    if isinstance(draft, FeatureDraft):
        return _render_feature(draft)
    if isinstance(draft, ConceptDraft):
        return _render_concept(draft)
    from langatlas_research.mint_edges import render_edge_like  # Task 7

    return render_edge_like(draft)


def _render_concept(draft: ConceptDraft) -> MintedRecord:
    node_id = _require_id(draft)
    data = {"id": node_id, "slug": draft.slug or node_id, "name": draft.name,
            "summary": _fact_block(draft), "provenance": _provenance(draft)}
    if draft.excluded_rationale:
        data["excluded_rationale"] = draft.excluded_rationale
    return finish(data, path=f"concepts/{node_id}.yaml", kind="concept",
                  node_ids=(node_id,))


def _render_feature(draft: FeatureDraft) -> MintedRecord:
    node_id = _require_id(draft)
    data = {"id": node_id, "slug": draft.slug or node_id, "name": draft.name,
            "layer": draft.layer, "summary": _fact_block(draft),
            "provenance": _provenance(draft)}
    if draft.dimension:
        data["dimension"] = draft.dimension
    if draft.cross_cutting:
        data["cross_cutting"] = True
    if draft.aliases:
        data["aliases"] = list(draft.aliases)
    if draft.realizes:
        data["realizes"] = list(draft.realizes)
    return finish(data, path=f"features/{node_id}.yaml", kind="feature",
                  node_ids=(node_id,))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv --directory tools/research run pytest tests/test_mint_nodes.py -v`
Expected: 7 passed. (`test_mint_nodes.py` only; the full suite goes green at the end of Task 7,
when `mint_edges` exists.)

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-09-13-stage-3a-research-spine-and-minting.md tools/research/
git commit -m "feat(#stage-3a): render concept and feature drafts into validated records"
```

---

## Task 7: Drafts and the renderer — edges, quality edges, and rules

**Files:**
- Modify: `tools/research/src/langatlas_research/drafts.py` (add three dataclasses)
- Create: `tools/research/src/langatlas_research/mint_edges.py`
- Test: `tools/research/tests/test_mint_edges.py`

**Interfaces:**
- Consumes: Task 6's `finish`, `_provenance` (re-exported as `provenance_block`), `Evidence`,
  `Proposer`; `langatlas_validate.ids.compose_edge_id`, `compose_rule_id`, `canonical_endpoints`,
  `canonical_when_all`.
- Produces:
  - `EdgeDraft(type, frm, to, statement, evidence, proposer, chat_run_id, polarity=None,
    debate_id=None, claim_origin="source-derived", candidate_source="internal-survey")`
  - `Assessment(key, assessor: Proposer, polarity, strength, statement, evidence)`
  - `QualityEdgeDraft(frm, to, assessments, proposer, chat_run_id, debate_id=None,
    claim_origin="source-derived", candidate_source="internal-survey")`
  - `RuleDraft(slug, when_all, effect, then, message, evidence, proposer, chat_run_id,
    debate_id=None, claim_origin="source-derived", candidate_source="internal-survey")`
  - `render_edge_like(draft) -> MintedRecord`
- 3C's edge drafter builds these; nothing else in Stage 3 constructs edge records.

**Rules this task encodes (all CI-enforced elsewhere; enforced here at mint time so a bad record
never reaches a commit):** `alternative-to` endpoints in lexicographic order so the edge id is
canonical; one `influences` edge per ordered pair with `polarity` as a field; `when_all`
lexicographically sorted before it is written (`then` stays in authored order — its order can
carry meaning); arity floor `len(when_all) >= 2` with the D64 message naming the edge type the
degenerate case belongs in instead.

- [ ] **Step 1: Write the failing test**

```python
# tools/research/tests/test_mint_edges.py
import pytest
from ruamel.yaml import YAML

from langatlas_research.drafts import Assessment, EdgeDraft, Evidence, Proposer, QualityEdgeDraft, RuleDraft
from langatlas_research.errors import DegenerateRule, InvalidDraft, UnsourcedNode
from langatlas_research.mint import render_draft

yaml = YAML(typ="safe")

PROPOSER = Proposer(agent="edge-drafter", model="claude-opus-5", prompt_version="v1")
EVIDENCE = (Evidence(source="pierce-2002", locator="ch. 11"),)


def test_an_influences_edge_renders_to_its_sharded_path():
    minted = render_draft(EdgeDraft(
        type="influences", frm="algebraic-data-types", to="pattern-matching", polarity="+",
        statement="Algebraic data types make pattern matching worth having.",
        evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-adt-0001"))

    assert minted.path == "edges/algebraic-data-types/influences--pattern-matching.yaml"
    data = yaml.load(minted.text)
    assert data["id"] == "edge.influences.algebraic-data-types.pattern-matching"
    assert data["polarity"] == "+"
    assert minted.node_ids == ("edge.influences.algebraic-data-types.pattern-matching",)


def test_an_influences_edge_without_polarity_is_refused():
    with pytest.raises(InvalidDraft, match="polarity"):
        render_draft(EdgeDraft(
            type="influences", frm="a-feature", to="b-feature", statement="x.",
            evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r"))


def test_alternative_to_endpoints_are_canonically_ordered():
    minted = render_draft(EdgeDraft(
        type="alternative-to", frm="pattern-matching", to="algebraic-data-types",
        statement="Two ways of expressing the same selection.",
        evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r"))

    assert minted.path == "edges/algebraic-data-types/alternative-to--pattern-matching.yaml"
    assert yaml.load(minted.text)["from"] == "algebraic-data-types"


def test_a_quality_edge_carries_its_assessments():
    minted = render_draft(QualityEdgeDraft(
        frm="ownership", to="learnability", proposer=PROPOSER, chat_run_id="r",
        assessments=(Assessment(key="a-steep-onboarding", assessor=PROPOSER, polarity="hurts",
                                strength="moderate",
                                statement="Ownership raises the initial learning cost.",
                                evidence=EVIDENCE),)))

    assert minted.path == "edges/ownership/affects-quality--learnability.yaml"
    data = yaml.load(minted.text)
    assert data["type"] == "affects-quality"
    assert data["assessments"][0]["polarity"] == "hurts"


def test_a_rule_sorts_its_antecedents_and_keeps_then_in_authored_order():
    minted = render_draft(RuleDraft(
        slug="laziness-needs-purity", when_all=("lazy-evaluation", "algebraic-data-types"),
        effect="requires", then=("purity", "referential-transparency"),
        message="Lazy evaluation is only predictable under purity.",
        evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r"))

    data = yaml.load(minted.text)
    assert minted.path == "rules/rule-laziness-needs-purity.yaml"
    assert data["when_all"] == ["algebraic-data-types", "lazy-evaluation"]
    assert data["then"] == ["purity", "referential-transparency"]


def test_a_one_antecedent_rule_names_the_edge_type_it_belongs_in():
    with pytest.raises(DegenerateRule, match="requires"):
        render_draft(RuleDraft(
            slug="degenerate", when_all=("lazy-evaluation",), effect="requires",
            then=("purity",), message="x.", evidence=EVIDENCE, proposer=PROPOSER,
            chat_run_id="r"))


def test_an_unsourced_edge_is_refused():
    with pytest.raises(UnsourcedNode):
        render_draft(EdgeDraft(
            type="requires", frm="a-feature", to="b-feature", statement="x.",
            evidence=(), proposer=PROPOSER, chat_run_id="r"))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv --directory tools/research run pytest tests/test_mint_edges.py -v`
Expected: FAIL — `ImportError: cannot import name 'EdgeDraft'`.

- [ ] **Step 3: Write the implementation**

Append to `tools/research/src/langatlas_research/drafts.py`:

```python
@dataclass(frozen=True)
class EdgeDraft:
    """`frm` rather than `from`, which is a Python keyword; the rendered field is `from`."""
    type: str
    frm: str
    to: str
    statement: str
    evidence: tuple[Evidence, ...]
    proposer: Proposer
    chat_run_id: str
    polarity: str | None = None
    debate_id: str | None = None
    claim_origin: str = "source-derived"
    candidate_source: str = "internal-survey"


@dataclass(frozen=True)
class Assessment:
    """One entry in an `affects-quality` edge. `key` is minted once and immutable (§3.3):
    renaming it is a supersession, never an edit."""
    key: str
    assessor: Proposer
    polarity: str
    strength: str
    statement: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class QualityEdgeDraft:
    frm: str
    to: str
    assessments: tuple[Assessment, ...]
    proposer: Proposer
    chat_run_id: str
    debate_id: str | None = None
    claim_origin: str = "source-derived"
    candidate_source: str = "internal-survey"


@dataclass(frozen=True)
class RuleDraft:
    slug: str
    when_all: tuple[str, ...]
    effect: str
    then: tuple[str, ...]
    message: str
    evidence: tuple[Evidence, ...]
    proposer: Proposer
    chat_run_id: str
    debate_id: str | None = None
    claim_origin: str = "source-derived"
    candidate_source: str = "internal-survey"
```

```python
# tools/research/src/langatlas_research/mint_edges.py
"""Edge, quality-edge and rule rendering. Split from `mint.py` so neither file has to hold
both the node shapes and the id-canonicalization rules in one head."""
from langatlas_research.drafts import EdgeDraft, QualityEdgeDraft, RuleDraft
from langatlas_research.errors import DegenerateRule, UnsourcedNode
from langatlas_research.mint import MintedRecord, finish, provenance_block
from langatlas_validate.ids import (
    canonical_endpoints, canonical_when_all, compose_edge_id, compose_rule_id,
)

# D64: a 1-antecedent candidate is a degenerate case belonging in an edge type instead.
_DEGENERATE_TO_EDGE = {"requires": "requires", "forbids": "conflicts-with",
                       "warn": "influences"}


def render_edge_like(draft) -> MintedRecord:
    if isinstance(draft, EdgeDraft):
        return _render_edge(draft)
    if isinstance(draft, QualityEdgeDraft):
        return _render_quality_edge(draft)
    if isinstance(draft, RuleDraft):
        return _render_rule(draft)
    raise TypeError(f"not a draft this package knows how to render: {type(draft).__name__}")


def _sources(evidence, *, what: str) -> list[dict]:
    if not evidence:
        raise UnsourcedNode(f"{what}: an edge or rule needs at least one (source, locator)"
                            f" (D4/§6.1)")
    return [e.as_entry() for e in evidence]


def _render_edge(draft: EdgeDraft) -> MintedRecord:
    frm, to = draft.frm, draft.to
    if draft.type == "alternative-to":
        frm, to = canonical_endpoints(frm, to)
    edge_id = compose_edge_id(draft.type, frm, to)
    data = {"id": edge_id, "type": draft.type, "from": frm, "to": to,
            "statement": {"text": draft.statement,
                          "sources": _sources(draft.evidence, what=edge_id)},
            "provenance": provenance_block(draft)}
    if draft.polarity is not None:
        data["polarity"] = draft.polarity
    return finish(data, path=f"edges/{frm}/{draft.type}--{to}.yaml", kind="edge",
                  node_ids=(edge_id,))


def _render_quality_edge(draft: QualityEdgeDraft) -> MintedRecord:
    edge_id = compose_edge_id("affects-quality", draft.frm, draft.to)
    data = {"id": edge_id, "type": "affects-quality", "from": draft.frm, "to": draft.to,
            "assessments": [
                {"key": a.key, "assessor": a.assessor.as_dict(), "polarity": a.polarity,
                 "strength": a.strength, "statement": a.statement,
                 "sources": _sources(a.evidence, what=f"{edge_id}[{a.key}]")}
                for a in draft.assessments],
            "provenance": provenance_block(draft)}
    return finish(data, path=f"edges/{draft.frm}/affects-quality--{draft.to}.yaml",
                  kind="affects-quality-edge", node_ids=(edge_id,))


def _render_rule(draft: RuleDraft) -> MintedRecord:
    rule_id = compose_rule_id(draft.slug)
    if len(draft.when_all) < 2:
        raise DegenerateRule(
            f"{rule_id}: a Rule needs >=2 antecedents (D64). A 1-antecedent"
            f" `{draft.effect}` interaction belongs in a"
            f" `{_DEGENERATE_TO_EDGE.get(draft.effect, 'matching')}` edge instead.")
    data = {"id": rule_id, "when_all": canonical_when_all(list(draft.when_all)),
            "effect": draft.effect, "then": list(draft.then), "message": draft.message,
            "sources": _sources(draft.evidence, what=rule_id),
            "provenance": provenance_block(draft)}
    return finish(data, path=f"rules/{rule_id}.yaml", kind="rule", node_ids=(rule_id,))
```

Then in `mint.py`, rename `_provenance` to `provenance_block` (public, since `mint_edges` imports
it) and update its two call sites in `_render_concept` / `_render_feature`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv --directory tools/research run pytest -v`
Expected: 37 passed (the whole suite, including Task 6's).

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-09-13-stage-3a-research-spine-and-minting.md tools/research/
git commit -m "feat(#stage-3a): render edge, quality-edge and rule drafts with canonical ids"
```

---

## Task 8: Shared-file mints — dimensions, qualities, the language registry

**Files:**
- Create: `tools/research/src/langatlas_research/taxonomy.py`
- Test: `tools/research/tests/test_taxonomy.py`

**Interfaces:**
- Consumes: Task 6's `MintedRecord`, `dump_yaml`, `content_digest`;
  `langatlas_validate.ids.is_valid_slug`.
- Produces:
  - `mint_dimension(slug, *, label, values, exclusivity="exclusive",
    applies_to=("general-purpose",), repo_root=None) -> MintedRecord`
  - `mint_quality(slug, *, label, summary, repo_root=None) -> MintedRecord`
  - `register_language(language_id, *, name, repo_root=None) -> MintedRecord`
- Every returned record carries a `base_digest`, which Task 9's lander uses to detect a lost
  read-modify-write race.

**Why these are different from Task 6/7's mints:** `ontology/taxonomy/dimensions.yaml`,
`qualities.yaml` and `languages/_registry.yaml` are *shared files* — §3.3 chose one-file-per-record
everywhere else precisely to avoid this, but the taxonomies are genuinely single lists. Each mint
is therefore a read-modify-write and can lose a race under concurrent agent commits. The mint
records the digest of what it read; the lander re-renders when that digest no longer matches
(Task 9), which turns a silent lost update into a retry.

**Pre-emptive fields (already ratified, write them from the first dimension):** `exclusivity`
defaults to `exclusive` (D39) and `applies_to` defaults to `[general-purpose]` (D50). Neither
waits for the feature that needs it.

- [ ] **Step 1: Write the failing test**

```python
# tools/research/tests/test_taxonomy.py
import pytest
from ruamel.yaml import YAML

from langatlas_research.taxonomy import mint_dimension, mint_quality, register_language

yaml = YAML(typ="safe")


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "ontology" / "taxonomy").mkdir(parents=True)
    (tmp_path / "ontology" / "taxonomy" / "dimensions.yaml").write_text("dimensions: []\n")
    (tmp_path / "ontology" / "taxonomy" / "qualities.yaml").write_text("qualities: []\n")
    (tmp_path / "languages").mkdir()
    (tmp_path / "languages" / "_registry.yaml").write_text("languages: {}\n")
    return tmp_path


def test_a_dimension_carries_the_pre_emptive_defaults(repo):
    minted = mint_dimension("typing-discipline", label="Typing discipline",
                            values=("static", "dynamic", "gradual"), repo_root=repo)

    assert minted.path == "ontology/taxonomy/dimensions.yaml"
    entry = yaml.load(minted.text)["dimensions"][0]
    assert entry["exclusivity"] == "exclusive"
    assert entry["applies_to"] == ["general-purpose"]
    assert entry["values"] == ["static", "dynamic", "gradual"]
    assert minted.base_digest is not None


def test_minting_a_second_dimension_keeps_the_first(repo):
    (repo / "ontology" / "taxonomy" / "dimensions.yaml").write_text(
        mint_dimension("typing-discipline", label="Typing discipline",
                       values=("static",), repo_root=repo).text)

    minted = mint_dimension("memory-reclamation", label="Memory reclamation",
                            values=("manual", "traced-gc"), exclusivity="multi-valued",
                            repo_root=repo)

    slugs = [d["slug"] for d in yaml.load(minted.text)["dimensions"]]
    assert slugs == ["memory-reclamation", "typing-discipline"]


def test_re_minting_an_existing_dimension_is_refused(repo):
    (repo / "ontology" / "taxonomy" / "dimensions.yaml").write_text(
        mint_dimension("typing-discipline", label="Typing discipline",
                       values=("static",), repo_root=repo).text)

    with pytest.raises(ValueError, match="already exists"):
        mint_dimension("typing-discipline", label="Typing discipline",
                       values=("static", "dynamic"), repo_root=repo)


def test_a_quality_lands_in_the_quality_vocabulary(repo):
    minted = mint_quality("learnability", label="Learnability",
                          summary="How quickly a competent programmer becomes productive.",
                          repo_root=repo)

    assert minted.path == "ontology/taxonomy/qualities.yaml"
    assert yaml.load(minted.text)["qualities"][0]["slug"] == "learnability"


def test_registering_a_language_is_the_id_mint_authority(repo):
    minted = register_language("rust", name="Rust", repo_root=repo)

    assert minted.path == "languages/_registry.yaml"
    assert yaml.load(minted.text)["languages"]["rust"]["name"] == "Rust"
    assert minted.node_ids == ("rust",)


def test_an_invalid_slug_is_refused_everywhere(repo):
    with pytest.raises(ValueError, match="invalid slug"):
        mint_quality("Learn Ability", label="x", summary="y", repo_root=repo)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv --directory tools/research run pytest tests/test_taxonomy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_research.taxonomy'`.

- [ ] **Step 3: Write the implementation**

```python
# tools/research/src/langatlas_research/taxonomy.py
"""The three shared-list files: layer-3 dimensions, the controlled quality vocabulary, and
the language-id mint authority.

Entries are kept slug-sorted so two agents adding different entries produce a diff git can
merge, and the same entry produces the identical file regardless of who wrote it first."""
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.mint import MintedRecord, content_digest, dump_yaml
from langatlas_validate.ids import is_valid_slug

_yaml = YAML(typ="safe")

DIMENSIONS_PATH = "ontology/taxonomy/dimensions.yaml"
QUALITIES_PATH = "ontology/taxonomy/qualities.yaml"
REGISTRY_PATH = "languages/_registry.yaml"


def _read(repo_root: Path | None, rel: str) -> tuple[dict, str]:
    path = (Path(repo_root) if repo_root else Path(".")) / rel
    text = path.read_text()
    return _yaml.load(text) or {}, content_digest(text)


def _require_slug(value: str) -> str:
    if not is_valid_slug(value):
        raise ValueError(f"invalid slug: {value!r} (§3.5)")
    return value


def mint_dimension(slug: str, *, label: str, values, exclusivity: str = "exclusive",
                   applies_to=("general-purpose",),
                   repo_root: Path | None = None) -> MintedRecord:
    """Adds one layer-3 dimension. `exclusivity` (D39) and `applies_to` (D50) are written
    pre-emptively on every dimension — they are not fields a later feature turns on.

    @raises ValueError: for an invalid slug or a dimension that already exists (changing
        an existing dimension is a restructure, not a mint — 3F's ceremony owns it)."""
    _require_slug(slug)
    data, digest = _read(repo_root, DIMENSIONS_PATH)
    entries = list(data.get("dimensions") or [])
    if any(entry["slug"] == slug for entry in entries):
        raise ValueError(f"dimension {slug!r} already exists")
    entries.append({"slug": slug, "label": label,
                    "values": [_require_slug(v) for v in values],
                    "exclusivity": exclusivity, "applies_to": list(applies_to)})
    entries.sort(key=lambda entry: entry["slug"])
    return MintedRecord(path=DIMENSIONS_PATH, text=dump_yaml({"dimensions": entries}),
                        kind="taxonomy", node_ids=(slug,), base_digest=digest)


def mint_quality(slug: str, *, label: str, summary: str,
                 repo_root: Path | None = None) -> MintedRecord:
    """Adds one entry to the controlled quality vocabulary (§3.1).
    @raises ValueError: invalid slug, or the quality already exists."""
    _require_slug(slug)
    data, digest = _read(repo_root, QUALITIES_PATH)
    entries = list(data.get("qualities") or [])
    if any(entry["slug"] == slug for entry in entries):
        raise ValueError(f"quality {slug!r} already exists")
    entries.append({"slug": slug, "label": label, "summary": summary})
    entries.sort(key=lambda entry: entry["slug"])
    return MintedRecord(path=QUALITIES_PATH, text=dump_yaml({"qualities": entries}),
                        kind="taxonomy", node_ids=(slug,), base_digest=digest)


def register_language(language_id: str, *, name: str,
                      repo_root: Path | None = None) -> MintedRecord:
    """§3.3: `languages/_registry.yaml` is the language-id mint authority. A Language
    record and its instances may only use an id this file already carries.
    @raises ValueError: invalid id, or the language is already registered."""
    _require_slug(language_id)
    data, digest = _read(repo_root, REGISTRY_PATH)
    languages = dict(data.get("languages") or {})
    if language_id in languages:
        raise ValueError(f"language {language_id!r} is already registered")
    languages[language_id] = {"name": name}
    ordered = {key: languages[key] for key in sorted(languages)}
    return MintedRecord(path=REGISTRY_PATH, text=dump_yaml({"languages": ordered}),
                       kind="language-registry", node_ids=(language_id,),
                       base_digest=digest)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv --directory tools/research run pytest -v`
Expected: 43 passed.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-09-13-stage-3a-research-spine-and-minting.md tools/research/
git commit -m "feat(#stage-3a): mint dimensions, qualities and language ids into their shared lists"
```

---

## Task 9: Landing drafts through the commit protocol, plus the CLI

**Files:**
- Create: `tools/research/src/langatlas_research/land.py`
- Create: `tools/research/src/langatlas_research/cli.py`
- Create: `tools/research/tests/conftest.py`
- Test: `tools/research/tests/test_land.py`
- Test: `tools/research/tests/test_cli.py`

**Interfaces:**
- Consumes: `langatlas_commit.land.land_record` and its result types (`Landed`,
  `ContentionExhausted`, `BlockedRedMain`, `Reverted`, `UnsafeHalt`);
  `langatlas_validate.store.validate_store`; Task 2's `validate_research_tree`; Task 4's
  `record_minted`; Task 6's `render_draft`; Task 8's mint functions.
- Produces:
  - `store_validator(repo_root) -> list[str]` — the validator `land_record` gates each retry on
  - `land_drafts(items, *, repo_root, chat_run_id, cycle=None, status_checker=None,
    attempts=3) -> list[tuple[MintedRecord, LandResult]]`
  - `main(argv=None) -> int` for the `langatlas-research` console script
- 3B–3E land everything through `land_drafts` and never call `land_record` directly.

**`items` accepts two shapes:** a draft object (rendered with `render_draft`), or a zero-argument
callable returning a `MintedRecord` (how a shared-file mint is passed —
`partial(mint_dimension, "typing-discipline", label=..., values=..., repo_root=root)`). Both are
re-invoked on retry, which is what makes a shared-file mint re-read the file it lost a race on
rather than clobbering the winner.

- [ ] **Step 1: Write the failing test**

```python
# tools/research/tests/conftest.py
import subprocess

import pytest

from langatlas_research.paths import REPO_ROOT, ensure_layout


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture
def store_repo(tmp_path):
    """A throwaway origin + clone carrying just enough canonical store to validate.

    `core.hooksPath` is pointed at an empty directory so this machine's global pre-commit
    hook does not reject the commits `land_record` makes from a subprocess."""
    origin = tmp_path / "origin.git"
    clone = tmp_path / "clone"
    hooks = tmp_path / "no-hooks"
    hooks.mkdir()
    _git(["init", "--bare", "-b", "main", str(origin)], tmp_path)
    _git(["clone", str(origin), str(clone)], tmp_path)
    for key, value in (("user.email", "bot@example.com"), ("user.name", "bot"),
                       ("core.hooksPath", str(hooks)), ("commit.gpgsign", "false")):
        _git(["config", key, value], clone)

    for directory in ("concepts", "features", "edges", "rules", "sources",
                      "ontology/taxonomy", "languages"):
        (clone / directory).mkdir(parents=True, exist_ok=True)
        (clone / directory / ".gitkeep").touch()
    for rel in ("ontology/taxonomy/dimensions.yaml", "ontology/taxonomy/qualities.yaml",
                "ontology/taxonomy/layers.yaml", "ontology/taxonomy/edge-types.yaml",
                "languages/_registry.yaml"):
        (clone / rel).write_text((REPO_ROOT / rel).read_text())
    (clone / "contradictions.yaml").write_text("contradictions: []\n")
    (clone / "ontology").mkdir(exist_ok=True)
    (clone / "ontology" / "VERSION").write_text((REPO_ROOT / "ontology" / "VERSION").read_text())
    (clone / "ontology" / "CHANGELOG.md").write_text("# Ontology changelog\n")

    ensure_layout(clone)
    for name in ("theme-registry", "cycle"):
        (clone / "research" / "schema" / f"{name}.schema.json").write_text(
            (REPO_ROOT / "research" / "schema" / f"{name}.schema.json").read_text())
    (clone / "research" / "themes.yaml").write_text(
        (REPO_ROOT / "research" / "themes.yaml").read_text())

    _git(["add", "-A"], clone)
    _git(["commit", "-q", "-m", "seed"], clone)
    _git(["push", "-q", "origin", "HEAD:main"], clone)
    return clone
```

```python
# tools/research/tests/test_land.py
from functools import partial

import pytest
from langatlas_commit.land import Landed

from langatlas_research.cycle import load_cycle, new_cycle
from langatlas_research.drafts import Evidence, FeatureDraft, Proposer
from langatlas_research.land import land_drafts, store_validator
from langatlas_research.taxonomy import mint_dimension

pytestmark = pytest.mark.git

PROPOSER = Proposer(agent="ontologist", model="claude-opus-5", prompt_version="v1")
EVIDENCE = (Evidence(source="vanroy-haridi-2003", locator="p. 142"),)


def _draft(node_id="pattern-matching", **overrides):
    base = dict(id=node_id, name="Pattern matching", layer=2,
                summary="Selection of a branch by the structural shape of a value.",
                evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0001")
    return FeatureDraft(**(base | overrides))


def test_the_seed_store_validates(store_repo):
    assert store_validator(store_repo) == []


def test_landing_a_feature_commits_it_and_records_it_on_the_cycle(store_repo):
    cycle = new_cycle(1, "typing", repo_root=store_repo, languages=("python",))

    results = land_drafts([_draft()], repo_root=store_repo, chat_run_id="r4-typing-0001",
                          cycle=cycle)

    minted, outcome = results[0]
    assert isinstance(outcome, Landed)
    assert (store_repo / "features" / "pattern-matching.yaml").exists()
    assert load_cycle(1, repo_root=store_repo).nodes_minted == ("pattern-matching",)


def test_landing_is_idempotent(store_repo):
    land_drafts([_draft()], repo_root=store_repo, chat_run_id="r")
    first = (store_repo / "features" / "pattern-matching.yaml").read_text()

    land_drafts([_draft()], repo_root=store_repo, chat_run_id="r")

    assert (store_repo / "features" / "pattern-matching.yaml").read_text() == first


def test_a_shared_file_mint_re_renders_against_whatever_is_on_disk(store_repo):
    land_drafts([partial(mint_dimension, "typing-discipline", label="Typing discipline",
                         values=("static", "dynamic"), repo_root=store_repo)],
                repo_root=store_repo, chat_run_id="r")

    land_drafts([partial(mint_dimension, "memory-reclamation", label="Memory reclamation",
                         values=("manual", "traced-gc"), repo_root=store_repo)],
                repo_root=store_repo, chat_run_id="r")

    text = (store_repo / "ontology" / "taxonomy" / "dimensions.yaml").read_text()
    assert "typing-discipline" in text and "memory-reclamation" in text


def test_an_invalid_draft_never_reaches_git(store_repo):
    from langatlas_research.errors import UnsourcedNode

    with pytest.raises(UnsourcedNode):
        land_drafts([_draft(evidence=())], repo_root=store_repo, chat_run_id="r")

    assert not (store_repo / "features" / "pattern-matching.yaml").exists()
```

```python
# tools/research/tests/test_cli.py
from langatlas_research.cli import main
from langatlas_research.cycle import load_cycle
from langatlas_research.paths import REPO_ROOT, ensure_layout, themes_path


def _research_repo(tmp_path):
    ensure_layout(tmp_path)
    for name in ("theme-registry", "cycle"):
        (tmp_path / "research" / "schema" / f"{name}.schema.json").write_text(
            (REPO_ROOT / "research" / "schema" / f"{name}.schema.json").read_text())
    themes_path(tmp_path).write_text(themes_path(REPO_ROOT).read_text())
    return tmp_path


def test_cycle_new_then_sign_off(tmp_path, capsys):
    repo = _research_repo(tmp_path)

    assert main(["--repo-root", str(repo), "cycle", "new", "1", "typing"]) == 0
    assert main(["--repo-root", str(repo), "cycle", "sign-off", "1",
                 "--by", "Michal Dolezel", "--date", "2026-09-20"]) == 0

    cycle = load_cycle(1, repo_root=repo)
    assert cycle.status == "signed-off"
    assert cycle.signed_off["by"] == "Michal Dolezel"
    assert len(cycle.languages) == 5


def test_validate_reports_a_broken_artifact(tmp_path):
    repo = _research_repo(tmp_path)
    (repo / "research" / "cycles" / "09-broken.yaml").write_text("cycle: nine\n")

    assert main(["--repo-root", str(repo), "validate"]) == 1


def test_themes_list_prints_every_theme(tmp_path, capsys):
    repo = _research_repo(tmp_path)

    assert main(["--repo-root", str(repo), "themes", "list"]) == 0

    out = capsys.readouterr().out
    assert "typing" in out and "qualities-vocabulary" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/research run pytest tests/test_land.py tests/test_cli.py -v -m ''`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_research.land'`.

- [ ] **Step 3: Write the implementation**

```python
# tools/research/src/langatlas_research/land.py
"""Landing: the one place Stage 3 touches the commit protocol.

Everything is rendered fresh on each attempt. That costs nothing for a one-file-per-record
mint and is the whole mechanism for a shared-file mint: after `land_record` rebases onto
someone else's taxonomy addition, re-rendering reads their entry and adds ours on top,
instead of pushing a file that silently drops it."""
from pathlib import Path

from langatlas_commit.land import ContentionExhausted, Landed, land_record

from langatlas_research.cycle import record_minted
from langatlas_research.mint import MintedRecord, content_digest, render_draft
from langatlas_research.schema import validate_research_tree
from langatlas_validate.store import validate_store


def store_validator(repo_root: Path) -> list[str]:
    """What `land_record` re-runs after every rebase: the canonical store's own gate plus
    the research tree's, so a commit can never leave either invalid on `main`."""
    return validate_store(repo_root) + validate_research_tree(repo_root)


def _render(item, repo_root: Path) -> MintedRecord:
    return item() if callable(item) else render_draft(item, repo_root=repo_root)


def _is_stale(minted: MintedRecord, repo_root: Path) -> bool:
    """True when a shared file changed under us between render and land."""
    if minted.base_digest is None:
        return False
    path = repo_root / minted.path
    return path.exists() and content_digest(path.read_text()) != minted.base_digest


def land_drafts(items, *, repo_root: Path, chat_run_id: str, cycle=None,
                status_checker=None, attempts: int = 3):
    """Renders and lands each item, one commit per record (D36).

    @param items: draft objects, or zero-argument callables returning a `MintedRecord`.
    @param cycle: when given, every landed record's node ids are appended to it.
    @returns: one `(MintedRecord, LandResult)` per item, in input order.
    @raises ResearchError: from rendering — an invalid draft never reaches git."""
    results = []
    for item in items:
        outcome = None
        minted = None
        for _ in range(attempts):
            minted = _render(item, repo_root)
            if _is_stale(minted, repo_root):
                continue
            outcome = land_record(repo_root, minted.path, minted.text,
                                  chat_run_id=chat_run_id, validator=store_validator,
                                  status_checker=status_checker)
            if isinstance(outcome, Landed):
                if cycle is not None:
                    cycle = record_minted(cycle, minted.node_ids, repo_root=repo_root)
                break
            if not isinstance(outcome, ContentionExhausted):
                break
        results.append((minted, outcome))
    return results
```

```python
# tools/research/src/langatlas_research/cli.py
"""`langatlas-research` — the research phase's bookkeeping CLI.

Subcommand dispatch, markdown/plain text to stdout, no daemon, never canonical data
beyond the `research/` files it is the writer of (matching the established
`tools/<domain>/` shape)."""
import argparse
import datetime as _dt
import subprocess
import sys
from pathlib import Path

from langatlas_research.cycle import CYCLE_STATUSES, advance, load_cycle, new_cycle, save_cycle, sign_off
from langatlas_research.errors import ResearchError
from langatlas_research.paths import ensure_layout
from langatlas_research.rotation import plan_languages
from langatlas_research.schema import validate_research_tree
from langatlas_research.themes import load_themes


def _git_user(repo_root: Path) -> str:
    result = subprocess.run(["git", "config", "user.name"], cwd=repo_root,
                            capture_output=True, text=True, check=False)
    return result.stdout.strip() or "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-research")
    parser.add_argument("--repo-root", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the research/ layout")
    sub.add_parser("validate", help="validate every research artifact")

    p_themes = sub.add_parser("themes").add_subparsers(dest="themes_command", required=True)
    p_themes.add_parser("list")

    p_cycle = sub.add_parser("cycle").add_subparsers(dest="cycle_command", required=True)
    p_new = p_cycle.add_parser("new")
    p_new.add_argument("number", type=int)
    p_new.add_argument("theme")
    p_new.add_argument("--size", type=int, default=5, help="R5 language sample width (4-5)")
    p_sign = p_cycle.add_parser("sign-off")
    p_sign.add_argument("number", type=int)
    p_sign.add_argument("--by", default=None)
    p_sign.add_argument("--date", default=None)
    p_status = p_cycle.add_parser("status")
    p_status.add_argument("number", type=int, nargs="?")
    p_advance = p_cycle.add_parser("advance")
    p_advance.add_argument("number", type=int)
    p_advance.add_argument("--to", required=True, choices=CYCLE_STATUSES)

    args = parser.parse_args(argv)
    root = args.repo_root
    try:
        return _dispatch(args, root)
    except ResearchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _dispatch(args, root: Path | None) -> int:
    if args.command == "init":
        for path in ensure_layout(root):
            print(f"created {path}")
        return 0

    if args.command == "validate":
        errors = validate_research_tree(root)
        for error in errors:
            print(error, file=sys.stderr)
        print(f"{len(errors)} error(s)")
        return 1 if errors else 0

    if args.command == "themes":
        for theme in load_themes(root).values():
            print(f"{theme.slug:34} {theme.label}")
        return 0

    if args.cycle_command == "new":
        cycle = new_cycle(args.number, args.theme, repo_root=root,
                          languages=plan_languages(args.number, size=args.size))
        print(f"drafted cycle {cycle.slug}; R5 sample: {', '.join(cycle.languages)}")
        print("NOT signed off — nothing may run until"
              f" `langatlas-research cycle sign-off {cycle.number}`")
        return 0

    if args.cycle_command == "sign-off":
        cycle = load_cycle(args.number, repo_root=root)
        signed = sign_off(cycle, by=args.by or _git_user(root or Path(".")),
                          date=args.date or _dt.date.today().isoformat(), repo_root=root)
        print(f"cycle {signed.slug} signed off by {signed.signed_off['by']}"
              f" on {signed.signed_off['date']} (theme digest"
              f" {signed.signed_off['theme_digest']})")
        return 0

    if args.cycle_command == "status":
        numbers = [args.number] if args.number else [
            int(p.name[:2]) for p in sorted((root or Path(".")).glob("research/cycles/*.yaml"))]
        for number in numbers:
            cycle = load_cycle(number, repo_root=root)
            signed = "signed" if cycle.signed_off else "UNSIGNED"
            print(f"{cycle.slug:28} {cycle.status:12} {signed:9}"
                  f" {len(cycle.nodes_minted):3} nodes  [{', '.join(cycle.languages)}]")
        return 0

    if args.cycle_command == "advance":
        cycle = advance(load_cycle(args.number, repo_root=root), args.to)
        save_cycle(cycle, repo_root=root)
        print(f"cycle {cycle.slug} -> {cycle.status}")
        return 0

    raise AssertionError("unreachable: argparse requires a subcommand")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory tools/research run pytest -v -m ''`
Expected: 51 passed.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-09-13-stage-3a-research-spine-and-minting.md tools/research/
git commit -m "feat(#stage-3a): land minted records through the commit protocol behind a CLI"
```

---

## Task 10: Referential integrity and filename/id agreement in `validate_store`

**Files:**
- Create: `tools/validate/src/langatlas_validate/references.py`
- Modify: `tools/validate/src/langatlas_validate/store.py` (call it from `validate_store`)
- Test: `tools/validate/tests/test_references.py`

**Interfaces:**
- Consumes: `iter_store_records`, `compose_edge_id`, `compose_instance_id`, `compose_rule_id`.
- Produces: `validate_references(repo_root: Path) -> list[str]`, folded into
  `validate_store`'s returned errors — so `langatlas-validate ci`, the pre-commit hook and
  `land_drafts`'s validator all gain the checks with no further wiring.

**Why now:** Stage 3 mints the first nodes, so Stage 3 is the first stage where a dangling edge
endpoint, a feature pointing at an undeclared dimension, or a record whose filename disagrees with
its id can exist at all. §3.3 states the filename rules and §3.5 states the ordering rules; until
now there was nothing to check them against.

- [ ] **Step 1: Write the failing test**

```python
# tools/validate/tests/test_references.py
import pytest

from langatlas_validate.references import validate_references


@pytest.fixture
def store(tmp_path):
    for directory in ("concepts", "features", "rules", "sources", "ontology/taxonomy",
                      "languages"):
        (tmp_path / directory).mkdir(parents=True)
    (tmp_path / "ontology/taxonomy/dimensions.yaml").write_text(
        "dimensions:\n  - slug: typing-discipline\n    label: Typing discipline\n"
        "    values: [static, dynamic]\n    exclusivity: exclusive\n"
        "    applies_to: [general-purpose]\n")
    (tmp_path / "ontology/taxonomy/qualities.yaml").write_text(
        "qualities:\n  - slug: learnability\n    label: Learnability\n    summary: x\n")
    (tmp_path / "languages/_registry.yaml").write_text("languages: {}\n")
    return tmp_path


def _feature(store, node_id, *, layer=2, dimension=None):
    body = [f"id: {node_id}", f"slug: {node_id}", "name: X", f"layer: {layer}"]
    if dimension:
        body.append(f"dimension: {dimension}")
    body += ["summary:", "  text: X.", "  sources:",
             "    - source: s", "      locator: p. 1",
             "provenance:", "  claim_origin: source-derived"]
    (store / "features" / f"{node_id}.yaml").write_text("\n".join(body) + "\n")


def test_a_clean_store_has_no_reference_errors(store):
    _feature(store, "pattern-matching")

    assert validate_references(store) == []


def test_a_filename_that_disagrees_with_its_id_is_an_error(store):
    _feature(store, "pattern-matching")
    (store / "features" / "pattern-matching.yaml").rename(store / "features" / "patmat.yaml")

    assert any("filename" in e for e in validate_references(store))


def test_a_dangling_edge_endpoint_is_an_error(store):
    _feature(store, "pattern-matching")
    (store / "edges" / "pattern-matching").mkdir(parents=True)
    (store / "edges" / "pattern-matching" / "requires--ownership.yaml").write_text(
        "id: edge.requires.pattern-matching.ownership\ntype: requires\n"
        "from: pattern-matching\nto: ownership\n"
        "statement:\n  text: X.\n  sources:\n    - source: s\n      locator: p. 1\n"
        "provenance:\n  claim_origin: source-derived\n")

    assert any("ownership" in e and "no such feature" in e for e in validate_references(store))


def test_an_undeclared_dimension_is_an_error(store):
    _feature(store, "typing-x", layer=3, dimension="nominality")

    assert any("nominality" in e for e in validate_references(store))


def test_a_declared_dimension_on_a_layer_three_feature_is_fine(store):
    _feature(store, "static-typing", layer=3, dimension="typing-discipline")

    assert validate_references(store) == []


def test_a_rule_antecedent_must_name_a_committed_feature(store):
    _feature(store, "lazy-evaluation")
    (store / "rules" / "rule-x.yaml").write_text(
        "id: rule-x\nwhen_all: [lazy-evaluation, purity]\neffect: requires\n"
        "then: [purity]\nmessage: X.\nsources:\n  - source: s\n    locator: p. 1\n"
        "provenance:\n  claim_origin: source-derived\n")

    assert any("purity" in e for e in validate_references(store))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv --directory tools/validate run pytest tests/test_references.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_validate.references'`.

- [ ] **Step 3: Write the implementation**

```python
# tools/validate/src/langatlas_validate/references.py
"""Referential integrity across the canonical store (§3.3).

Separate from `schema.py` because JSON Schema can validate a record in isolation and
nothing more: that an edge's endpoint names a feature that actually exists is a property of
the *store*, not of the record. Stage 3 is the first stage that mints nodes, so it is the
first stage where any of this can fail."""
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_validate.ids import compose_edge_id, compose_instance_id
from langatlas_validate.store import iter_store_records

_yaml = YAML(typ="safe")


def _taxonomy_slugs(repo_root: Path, rel: str, key: str) -> set[str]:
    path = repo_root / rel
    if not path.exists():
        return set()
    data = _yaml.load(path.read_text()) or {}
    return {entry["slug"] for entry in (data.get(key) or [])}


def _registry_ids(repo_root: Path) -> set[str]:
    path = repo_root / "languages" / "_registry.yaml"
    if not path.exists():
        return set()
    data = _yaml.load(path.read_text()) or {}
    return set((data.get("languages") or {}).keys())


def validate_references(repo_root: Path) -> list[str]:
    """@returns: one error string per violation, each prefixed with the offending path."""
    records = list(iter_store_records(repo_root))
    features = {data["id"] for _, kind, _, data in records if kind == "feature"}
    concepts = {data["id"] for _, kind, _, data in records if kind == "concept"}
    dimensions = _taxonomy_slugs(repo_root, "ontology/taxonomy/dimensions.yaml", "dimensions")
    qualities = _taxonomy_slugs(repo_root, "ontology/taxonomy/qualities.yaml", "qualities")
    languages = _registry_ids(repo_root)

    errors: list[str] = []

    def require(condition: bool, path: Path, message: str) -> None:
        if not condition:
            errors.append(f"{path.relative_to(repo_root)}: {message}")

    for path, kind, _text, data in records:
        record_id = data.get("id")

        if kind in ("feature", "concept", "rule"):
            require(path.stem == record_id, path,
                    f"filename does not match id {record_id!r} (§3.3)")
        if kind == "feature":
            dimension = data.get("dimension")
            if dimension is not None:
                require(dimension in dimensions, path,
                        f"dimension {dimension!r}: not declared in"
                        f" ontology/taxonomy/dimensions.yaml")
            for concept_id in data.get("realizes", []):
                require(concept_id in concepts, path,
                        f"realizes {concept_id!r}: no such concept")
        if kind in ("edge", "affects-quality-edge"):
            frm, to = data.get("from"), data.get("to")
            expected_id = compose_edge_id(data["type"], frm, to)
            require(record_id == expected_id, path,
                    f"id {record_id!r} is not the composition of its type and endpoints"
                    f" (expected {expected_id!r})")
            require(path.name == f"{data['type']}--{to}.yaml" and path.parent.name == frm,
                    path, f"filename must be edges/{frm}/{data['type']}--{to}.yaml (§3.3)")
            require(frm in features, path, f"from {frm!r}: no such feature")
            if kind == "edge":
                require(to in features, path, f"to {to!r}: no such feature")
            else:
                require(to in qualities, path,
                        f"to {to!r}: not in ontology/taxonomy/qualities.yaml")
        if kind == "rule":
            for feature_id in list(data.get("when_all", [])) + list(data.get("then", [])):
                require(feature_id in features, path,
                        f"{feature_id!r}: no such feature")
        if kind == "feature-instance":
            language, feature = data.get("language"), data.get("feature")
            require(record_id == compose_instance_id(language, feature), path,
                    f"id {record_id!r} is not fi.<language>.<feature>")
            require(path.stem == feature, path,
                    f"filename must be languages/{language}/instances/{feature}.yaml (§3.3)")
            require(language in languages, path,
                    f"language {language!r}: not in languages/_registry.yaml")
            require(feature in features, path, f"feature {feature!r}: no such feature")
        if kind == "language":
            require(record_id in languages, path,
                    f"language {record_id!r}: not in languages/_registry.yaml")

    return errors
```

In `store.py`, extend `validate_store`'s docstring and return:

```python
def validate_store(repo_root: Path) -> list[str]:
    """CI's store-validating gate (D13): schema validity + normalization drift for
    every live record, the claim-template registry's own self-check, D64's canonical-ordering
    rule for `alternative-to` edges and rules' `when_all`, and cross-record referential
    integrity (§3.3 — added in Stage 3A, the first stage that mints nodes)."""
    from langatlas_validate.references import validate_references
    ...
    errors.extend(validate_references(repo_root))
    return errors
```

(The import is function-local: `references.py` imports `iter_store_records` from `store.py`, so a
module-level import would be circular.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory tools/validate run pytest -v && uv --directory tools/research run pytest -v -m ''`
Expected: the validate suite green (6 new tests) and the research suite still 51 passed.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-09-13-stage-3a-research-spine-and-minting.md tools/validate/
git commit -m "feat(#stage-3a): check referential integrity and filename/id agreement in the store gate"
```

---

## Task 11: The graduated 0.x version ceremony

**Files:**
- Create: `tools/validate/src/langatlas_validate/version.py`
- Modify: `tools/validate/src/langatlas_validate/cli.py` (add the `version-bump` subcommand)
- Test: `tools/validate/tests/test_version.py`

**Interfaces:**
- Consumes: `iter_store_records`.
- Produces:
  - `read_version(repo_root) -> tuple[int, int, int]`
  - `store_snapshot(repo_root) -> dict[str, dict]` (repo-relative path → record data)
  - `snapshot_at(repo_root, ref) -> dict[str, dict]` (the same, for a git ref)
  - `classify_change(before, after) -> str` — one of `"none" | "cosmetic" | "additive" |
    "restructuring"`
  - `bump(version, change) -> tuple[int, int, int]`
  - `MajorRequiresGovernance` (raised when a restructuring change is classified at `>= 1.0.0`)
  - CLI: `langatlas-validate version-bump [--since <ref>] [--apply]`
- Stage 4 flips governance on; this task's job is to make the `0.x` half real and to make the
  `1.0.0` half *refuse* rather than guess.

**The rules (§5.1 + §7.4's graduated ceremony), written out so no step has to infer them:**

| Change | `0.x` result | `>= 1.0.0` result |
|---|---|---|
| A record added, or a field/list entry added to an existing record | MINOR | MINOR |
| A record removed, an `id` changed, a `layer`/`dimension` changed, an edge endpoint changed, a `when_all` changed | **MINOR** — restructures are ordinary during the research phase | raises `MajorRequiresGovernance` (RFC-gated, Stage 4/D16) |
| Only free text changed (`name`, `slug`, `summary.text`, `statement.text`, `message`) | PATCH | PATCH |
| Nothing changed | unchanged | unchanged |

- [ ] **Step 1: Write the failing test**

```python
# tools/validate/tests/test_version.py
import pytest

from langatlas_validate.version import (
    MajorRequiresGovernance, bump, classify_change,
)

BEFORE = {"features/pattern-matching.yaml": {
    "id": "pattern-matching", "slug": "pattern-matching", "name": "Pattern matching",
    "layer": 2, "summary": {"text": "A.", "sources": [{"source": "s", "locator": "p. 1"}]}}}


def test_no_change_is_none():
    assert classify_change(BEFORE, BEFORE) == "none"


def test_a_new_record_is_additive():
    after = BEFORE | {"features/ownership.yaml": {"id": "ownership", "layer": 2}}

    assert classify_change(BEFORE, after) == "additive"


def test_a_new_field_is_additive():
    after = {"features/pattern-matching.yaml":
             BEFORE["features/pattern-matching.yaml"] | {"aliases": ["destructuring"]}}

    assert classify_change(BEFORE, after) == "additive"


def test_a_text_only_edit_is_cosmetic():
    record = dict(BEFORE["features/pattern-matching.yaml"])
    record["summary"] = {"text": "A better sentence.",
                         "sources": [{"source": "s", "locator": "p. 1"}]}

    assert classify_change(BEFORE, {"features/pattern-matching.yaml": record}) == "cosmetic"


def test_a_removed_record_is_restructuring():
    assert classify_change(BEFORE, {}) == "restructuring"


def test_a_layer_move_is_restructuring():
    record = dict(BEFORE["features/pattern-matching.yaml"]) | {"layer": 3,
                                                               "dimension": "d"}

    assert classify_change(BEFORE, {"features/pattern-matching.yaml": record}) == "restructuring"


@pytest.mark.parametrize("change,expected", [
    ("none", (0, 2, 0)), ("cosmetic", (0, 2, 1)), ("additive", (0, 3, 0)),
    ("restructuring", (0, 3, 0)),
])
def test_zero_x_bumps(change, expected):
    assert bump((0, 2, 0), change) == expected


def test_after_one_zero_a_restructure_needs_governance():
    with pytest.raises(MajorRequiresGovernance):
        bump((1, 4, 0), "restructuring")


def test_after_one_zero_additive_is_still_minor():
    assert bump((1, 4, 0), "additive") == (1, 5, 0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv --directory tools/validate run pytest tests/test_version.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_validate.version'`.

- [ ] **Step 3: Write the implementation**

```python
# tools/validate/src/langatlas_validate/version.py
"""§5.1's one semver, defined by fact blast radius, and §7.4's graduated 0.x ceremony.

During `0.x` a restructure is an ordinary MINOR: the research phase is *supposed* to
restructure, and gating it would make the ontology unwritable before it exists. At `1.0.0`
the same classification stops being auto-appliable and raises instead — the RFC-gated D16
process (Stage 4) is what resolves it. Defining the `>= 1.0.0` branch now, as a refusal,
is deliberate: the alternative is discovering at the flip that CI silently auto-bumped a
MAJOR."""
import subprocess
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_validate.store import iter_store_records

_yaml = YAML(typ="safe")

# Fields whose edit changes only wording, never a fact's meaning or identity (§3.5's
# copyedit-tolerant hashing applies the same idea to fact ids).
_COSMETIC_FIELDS = {"name", "slug", "message"}
_COSMETIC_SUBFIELDS = {("summary", "text"), ("statement", "text")}
# Fields whose edit moves or re-anchors an existing fact.
_STRUCTURAL_FIELDS = {"id", "layer", "dimension", "type", "from", "to", "when_all",
                      "language", "feature", "effect", "polarity"}

STORE_DIRS = ("concepts", "features", "edges", "rules", "languages")


class MajorRequiresGovernance(Exception):
    """A restructuring change at >= 1.0.0 is an RFC-gated MAJOR (D16/§5.3) — never an
    automatic bump."""


def read_version(repo_root: Path) -> tuple[int, int, int]:
    major, minor, patch = (repo_root / "ontology" / "VERSION").read_text().strip().split(".")
    return int(major), int(minor), int(patch)


def write_version(repo_root: Path, version: tuple[int, int, int]) -> None:
    (repo_root / "ontology" / "VERSION").write_text(".".join(str(p) for p in version) + "\n")


def store_snapshot(repo_root: Path) -> dict[str, dict]:
    return {str(path.relative_to(repo_root)): data
            for path, _kind, _text, data in iter_store_records(repo_root)}


def snapshot_at(repo_root: Path, ref: str) -> dict[str, dict]:
    """The same mapping for a git ref, read through `git show` so no worktree or
    checkout is needed."""
    listing = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref, "--", *STORE_DIRS],
                             cwd=repo_root, capture_output=True, text=True, check=True)
    snapshot: dict[str, dict] = {}
    for rel in listing.stdout.splitlines():
        if not rel.endswith(".yaml") or rel.endswith("_registry.yaml"):
            continue
        blob = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=repo_root,
                              capture_output=True, text=True, check=True)
        data = _yaml.load(blob.stdout)
        if isinstance(data, dict):
            snapshot[rel] = data
    return snapshot


def _diff_class(before: dict, after: dict) -> str:
    """The strongest class of change between two versions of one record."""
    if before == after:
        return "none"
    for field in _STRUCTURAL_FIELDS:
        if before.get(field) != after.get(field):
            return "restructuring"
    added = set(after) - set(before)
    removed = set(before) - set(after)
    if removed:
        return "restructuring"
    if added:
        return "additive"
    for field in set(before) | set(after):
        if before.get(field) == after.get(field):
            continue
        if field in _COSMETIC_FIELDS:
            continue
        if isinstance(before.get(field), dict) and isinstance(after.get(field), dict):
            changed = {k for k in set(before[field]) | set(after[field])
                       if before[field].get(k) != after[field].get(k)}
            if changed and all((field, k) in _COSMETIC_SUBFIELDS for k in changed):
                continue
        if isinstance(before.get(field), list) and isinstance(after.get(field), list):
            if len(after[field]) > len(before[field]):
                return "additive"
        return "restructuring"
    return "cosmetic"


_RANK = ("none", "cosmetic", "additive", "restructuring")


def classify_change(before: dict[str, dict], after: dict[str, dict]) -> str:
    """@returns: the strongest change class across the whole store."""
    strongest = "none"
    if set(before) - set(after):
        strongest = "restructuring"
    for path in set(after) - set(before):
        strongest = max(strongest, "additive", key=_RANK.index)
    for path in set(before) & set(after):
        strongest = max(strongest, _diff_class(before[path], after[path]), key=_RANK.index)
    return strongest


def bump(version: tuple[int, int, int], change: str) -> tuple[int, int, int]:
    """@raises MajorRequiresGovernance: restructuring change at >= 1.0.0."""
    major, minor, patch = version
    if change == "none":
        return version
    if change == "cosmetic":
        return major, minor, patch + 1
    if change == "restructuring" and major >= 1:
        raise MajorRequiresGovernance(
            "a restructuring change at >= 1.0.0 is an RFC-gated MAJOR (D16/§5.3):"
            " open the RFC instead of bumping")
    return major, minor + 1, 0
```

Add to `cli.py`'s `main`:

```python
    p_version = sub.add_parser("version-bump")
    p_version.add_argument("--since", default="HEAD~1",
                           help="git ref to diff the store against (default HEAD~1)")
    p_version.add_argument("--apply", action="store_true",
                           help="write ontology/VERSION and append to ontology/CHANGELOG.md")
```

```python
    if args.command == "version-bump":
        from langatlas_validate.version import (
            bump, classify_change, read_version, snapshot_at, store_snapshot, write_version,
        )

        root = REPO_ROOT
        change = classify_change(snapshot_at(root, args.since), store_snapshot(root))
        current = read_version(root)
        new = bump(current, change)
        rendered = ".".join(str(p) for p in new)
        print(f"change since {args.since}: {change}; version"
              f" {'.'.join(str(p) for p in current)} -> {rendered}")
        if args.apply and new != current:
            write_version(root, new)
            changelog = root / "ontology" / "CHANGELOG.md"
            changelog.write_text(changelog.read_text().rstrip("\n") +
                                 f"\n\n## {rendered}\n\n- {change} change since {args.since}\n")
        return 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory tools/validate run pytest -v`
Expected: all green, including the 9 new version tests.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-09-13-stage-3a-research-spine-and-minting.md tools/validate/
git commit -m "feat(#stage-3a): auto-bump the 0.x ontology version from the store diff"
```

---

## Task 12: CI wiring, the package README, and the 3A exit test

**Files:**
- Create: `tools/research/README.md`
- Create: `tools/research/tests/test_exit_3a.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: everything above.
- Produces: a green end-to-end run that is 3A's exit condition, and a CI that runs the research
  package's tests and keeps `ontology/VERSION` moving on `main`.

**Why the version job cannot loop:** the bump commit touches `ontology/VERSION` and
`ontology/CHANGELOG.md` only. Neither is inside `STORE_DIRS`, so the next run classifies the
change as `none` and writes nothing.

- [ ] **Step 1: Write the failing exit test**

```python
# tools/research/tests/test_exit_3a.py
"""Stage 3A's exit condition, end to end: a signed-off cycle mints a dimension, a concept,
a feature and an edge; every record validates, lands, and is bookkept on the cycle; and the
0.x ceremony turns the additive change into a MINOR bump."""
import subprocess
from functools import partial

import pytest
from langatlas_commit.land import Landed

from langatlas_research.cycle import load_cycle, new_cycle, sign_off
from langatlas_research.drafts import ConceptDraft, EdgeDraft, Evidence, FeatureDraft, Proposer
from langatlas_research.land import land_drafts, store_validator
from langatlas_research.taxonomy import mint_dimension
from langatlas_validate.version import bump, classify_change, read_version, snapshot_at, store_snapshot

pytestmark = pytest.mark.git

PROPOSER = Proposer(agent="ontologist", model="claude-opus-5", prompt_version="v1")
EVIDENCE = (Evidence(source="vanroy-haridi-2003", locator="p. 142"),)


def test_a_signed_off_cycle_mints_a_theme_subtree_and_bumps_the_version(store_repo):
    baseline = subprocess.run(["git", "rev-parse", "HEAD"], cwd=store_repo,
                              capture_output=True, text=True, check=True).stdout.strip()
    cycle = sign_off(new_cycle(1, "typing", repo_root=store_repo, languages=("python", "haskell")),
                     by="Michal Dolezel", date="2026-09-20", repo_root=store_repo)

    items = [
        partial(mint_dimension, "typing-discipline", label="Typing discipline",
                values=("static", "dynamic"), repo_root=store_repo),
        ConceptDraft(id="type", name="Type", summary="A classification of values.",
                     evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0001"),
        FeatureDraft(id="static-typing", name="Static typing", layer=3,
                     dimension="typing-discipline", realizes=("type",),
                     summary="Type checking performed before execution.",
                     evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0001"),
        FeatureDraft(id="type-inference", name="Type inference", layer=2,
                     summary="Types reconstructed without annotation.",
                     evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0001"),
        EdgeDraft(type="requires", frm="type-inference", to="static-typing",
                  statement="Inference presupposes a static discipline to infer within.",
                  evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0001"),
    ]

    results = land_drafts(items, repo_root=store_repo, chat_run_id="r4-typing-0001",
                          cycle=cycle)

    assert all(isinstance(outcome, Landed) for _, outcome in results)
    assert store_validator(store_repo) == []
    assert set(load_cycle(1, repo_root=store_repo).nodes_minted) == {
        "typing-discipline", "type", "static-typing", "type-inference",
        "edge.requires.type-inference.static-typing"}

    change = classify_change(snapshot_at(store_repo, baseline), store_snapshot(store_repo))
    assert change == "additive"
    assert bump(read_version(store_repo), change) == (0, 3, 0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv --directory tools/research run pytest tests/test_exit_3a.py -v -m ''`
Expected: FAIL. Fix whatever it exposes — this test is the first time all twelve tasks run
together, and any signature drift between them surfaces here.

- [ ] **Step 3: Write the README and wire CI**

```markdown
<!-- tools/research/README.md -->
# langatlas-research

Stage 3's research spine: theme cycles, the developer sign-off gate, and the node-minting path.

## What this package is for

Every Stage 3 agent role — surveyor (3B), ontologist and edge drafter (3C), reality checker
(3E) — ends by handing a **draft** to this package. Drafts are dumb data; this package turns
one into a validated, normalized record at its `context/spec.md` §3.3 path and lands it through
the D36 commit protocol, one commit per record.

No model is called anywhere in this package. That is deliberate: the minting rules are the part
of Stage 3 that must be deterministic and testable without a provider.

## The gate

`require_sign_off(cycle)` is D27's hard checkpoint — the developer signs off a cycle's theme
before anything runs. The sign-off is bound to a digest of the theme text, so editing the theme
afterwards re-opens the gate rather than silently inheriting it. Nothing technically prevents an
agent from writing a sign-off block; the gate is a checkpoint artifact the developer reads in a
diff, not an ACL.

## Commands

```
langatlas-research init                       # create research/
langatlas-research themes list
langatlas-research cycle new 1 typing         # draft cycle 1, plan its R5 language sample
langatlas-research cycle sign-off 1           # the developer checkpoint
langatlas-research cycle status
langatlas-research cycle advance 1 --to r3-done
langatlas-research validate                   # every research artifact against its schema
```

## Tests

```
uv --directory tools/research sync --extra dev
uv --directory tools/research run pytest -m ''   # `git`-marked tests build throwaway repos
```
```

In `.github/workflows/ci.yml`, add to the `validate` job's install step and test list:

```yaml
      - name: Install packages
        run: |
          uv --directory tools/validate sync
          uv --directory tools/pipeline sync
          uv --directory tools/ingest sync
          uv --directory tools/finding-aids sync --extra dev
          uv --directory tools/research sync --extra dev
      - name: Test the research package
        # No database, no provider; the `git`-marked tests build throwaway local repos.
        run: uv --directory tools/research run pytest -m ''
```

and add a third job:

```yaml
  version:
    needs: validate
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2
      - uses: astral-sh/setup-uv@v3
      - run: uv --directory tools/validate sync
      - name: Auto-bump the 0.x ontology version (§5.1)
        # The bump commit touches only ontology/VERSION and ontology/CHANGELOG.md, neither
        # of which is in STORE_DIRS — so the next run classifies "none" and writes nothing.
        # No loop, no [skip ci] needed.
        run: |
          uv --directory tools/validate run langatlas-validate version-bump \
            --since HEAD~1 --apply
          if ! git diff --quiet -- ontology/VERSION; then
            git config user.name "langatlas-bot"
            git config user.email "bot@langatlas.dev"
            git add ontology/VERSION ontology/CHANGELOG.md
            git commit -m "chore: bump ontology version"
            git push origin HEAD:main
          fi
```

- [ ] **Step 4: Run everything**

Run:
```bash
uv --directory tools/validate run pytest -q
uv --directory tools/research run pytest -q -m ''
uv --directory tools/validate run langatlas-validate ci
```
Expected: all green; `ci` reports no errors against the real (still node-free) store.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-09-13-stage-3a-research-spine-and-minting.md \
        tools/research/README.md tools/research/tests/ .github/workflows/ci.yml
git commit -m "feat(#stage-3a): wire the research package into CI and prove the 3A exit path"
```

---

## Stage 3A exit condition

3A is done when all five hold:

1. `langatlas-research cycle new 1 typing` then `cycle sign-off 1` produces a committed cycle
   record, and `require_sign_off` passes for it while failing for an unsigned or theme-edited one.
2. A hand-written draft set (dimension + concept + feature + edge) mints, validates, normalizes,
   and lands one commit per record through `land_record`, with every node id recorded on the cycle.
3. `validate_store` catches a dangling edge endpoint, an undeclared dimension and a
   filename/id disagreement — the three ways Stage 3's first real nodes can break the store.
4. `langatlas-validate version-bump` classifies an additive store diff and bumps `0.x` MINOR,
   and refuses to auto-apply a restructuring change once the version reaches `1.0.0`.
5. CI installs and runs the research package's tests, and the version job runs on `main`.

3B–3F treat all of this as **fixed**: they build drafts and call `land_drafts`; they do not
re-derive record shapes, paths, ids or the sign-off rule.

## Deliberately out of scope (restated from the sequencing map)

- **Any model call.** The corpus tagger, surveyor, ontologist, edge drafter, debate machinery and
  controversy assessor are 3B–3D. 3A has no provider dependency beyond `RunContext.run_id` being
  the `chat_run_id` a caller passes in.
- **Survey / debate / reality-check schemas.** Each is shipped by the sub-plan that writes that
  directory; `validate_research_tree` already fails loudly on a populated directory with no
  schema, which is how the obligation stays visible instead of drifting.
- **Migration manifests, `migrate.py`, tombstone chain walking.** 3F, at the point a theme is
  first marked settled. During an active theme, §7.4 makes a restructure an ordinary commit.
- **The blast-radius script, RFC intake, `/changelog/ontology/` pages.** Stage 4 and Stage 6.
  `bump()` raising `MajorRequiresGovernance` at `>= 1.0.0` is the seam they plug into.
- **`ontology/redirects.yaml` writing.** Slug renames start in 3F's slug-polish pass; 3A only
  guarantees that ids never change, which is what makes a later rename cheap.
- **The D57 onboarding checklist fields.** `register_language` writes `name` only; the schema
  admits `language_kind`, `syntax_check`, `file_extensions` and `first_appeared` as optional, and
  3E fills them at reality-check onboarding time (§7.5 defers the checklist build to D28 phase
  2/3 anyway).

## Self-review

**Spec coverage.** §3.3's layout and id patterns → Tasks 6, 7, 10. §3.5's slug grammar,
normalization and canonical ordering → Tasks 6, 7 (mint-time) and 10 (store-wide). §3.1's
entity set → Tasks 6–8 (Concept, Feature, Edge, affects-quality Edge, Rule, Quality, Dimension,
language registry; FeatureInstance minting is 3E's, which is why `validate_references` checks the
shape without a mint path for it). §5.1's split id/slug and one-semver rule → Tasks 6, 11. §7.4's
graduated 0.x ceremony → Task 11, with the `>= 1.0.0` refusal defining the Stage 4 seam. §7.9's
commit protocol → Task 9, reused rather than reimplemented. D27's sign-off checkpoint → Tasks 3,
4. D39/D50's pre-emptive `exclusivity` / `applies_to` → Task 8. D64's rule arity floor and
`when_all` canonicalization → Task 7. D4's source-first rule → Task 6's `UnsourcedNode`, enforced
for every draft type in Tasks 6 and 7.

**Interpretation flagged.** §7.4 says the final theme list is itself an early R3 deliverable, so
`research/themes.yaml` ships **seeded, not frozen**, and theme edits re-open the sign-off gate
(Task 4's `SignOffStale`). The alternative reading — freeze the twelve and treat an amendment as
out-of-band — would make the digest binding pointless; if the developer prefers it, Task 3's
`theme_digest` is the single place to change.

**Scope addition flagged.** `validate_references` (Task 10) and the `version-bump` CI job
(Task 11) are not named in the sequencing map's 3A "Produces" list as separate bullets, but both
are 3A obligations the map does name in prose: the map's entry-state section records that
`validate_store` has no referential checks, and its 3A bullet names the 0.x ceremony. Both live in
`langatlas_validate` rather than `langatlas_research` because they are store-wide properties, not
research-phase bookkeeping — Stage 5's sweeps inherit them for free.

**Type consistency.** `MintedRecord(path, text, kind, node_ids, base_digest)` is constructed in
`mint.finish`, `mint_edges._render_*` (through `finish`) and all three `taxonomy.mint_*`
functions, and consumed in `land.land_drafts` — same five fields everywhere. `Evidence.as_entry()`
is the only producer of a `sources:` entry. `Proposer.as_dict()` is used both for
`provenance.proposer` and for an assessment's `assessor`. `render_draft` dispatches to
`_render_feature` / `_render_concept` / `render_edge_like`, and `render_edge_like` covers exactly
`EdgeDraft`, `QualityEdgeDraft`, `RuleDraft` — no draft type is unhandled. `Cycle.nodes_minted`
is written only by `record_minted` and read by `land_drafts` and (later) 3F's dossier.
`provenance_block` (not `_provenance`) is the name `mint_edges` imports — Task 7's step 3 renames
it in `mint.py`, and Task 6's two call sites move with it.

## Execution handoff

Plan complete and saved to
`docs/superpowers/plans/2026-09-13-stage-3a-research-spine-and-minting.md`. Two execution options:

1. **Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast
   iteration (superpowers:subagent-driven-development).
2. **Inline Execution** — execute tasks in this session with checkpoints
   (superpowers:executing-plans).
