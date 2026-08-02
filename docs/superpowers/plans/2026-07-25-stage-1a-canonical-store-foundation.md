# Stage 1A — Canonical Store Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the LangAtlas canonical git store — directory layout, the `ontology/` scaffold at `VERSION 0.1.0`, the JSON Schemas with every pre-emptive field, the claim-template registry, and the `langatlas_validate` CLI (id/slug machinery, locator-shape checks, canonical-claim hashing, YAML normalization, regression runner) — so sub-plans 1B–1E can build against fixed schema shapes and CLI signatures.

**Architecture:** One Python package `langatlas_validate` under `tools/validate/` (src layout, uv-in-Docker packaging, thin `cli.py` dispatching to independently-importable pure functions), plus the versioned data-store skeleton under repo root (`ontology/`, `concepts/`, `features/`, `languages/`, `edges/`, `rules/`, `sources/`, root ledgers). Everything the CLI enforces is a pure function callable both from the `langatlas-validate` console script and inline from later subsystems (the D24 verifier imports `validate_locator` directly). No database, no network, no model calls in this sub-plan — all deferred I/O is dependency-injected.

**Tech Stack:** Python 3.12; `ruamel.yaml` (YAML 1.2 round-trip, required for the normalizer's block-style + key-order control); `jsonschema` (Draft 2020-12); `pytest`; `hatchling` build backend driven by `uv`. No other runtime dependencies.

## Global Constraints

- No deadline; do not take shortcuts that damage the long-term product (D6/D11).
- Git is the database — Postgres, MCP, and the static site are always one-way derived build artifacts, never authoritative (D1).
- No PR gate for agent-committed facts — admissibility comes from the automated verification gate (D4/D24), never human review bandwidth (D1).
- English-only; code MIT, corpus CC BY-SA 4.0 (D7, D14).
- Claude never does volume work; the university API never has the final judgment call (D6).
- Every agent chat is logged from day one — cannot be retrofitted (D18).

### 1A-specific invariants (copied verbatim from the spec)

- **Slug/id grammar (§3.5):** `[a-z0-9]+(-[a-z0-9]+)*`, ≤48 chars, ASCII, no leading digit. Node ids are minted as the initial slug and never change; slugs may diverge via `ontology/redirects.yaml`.
- **Composed record ids (§3.3):** `fi.<language>.<feature>`, `edge.<type>.<from>.<to>`, `rule-<slug>`, `<instance-id>.sx.<key>`, sub-keys `c-<key>` / `n-<slug>`. `alternative-to` endpoints and a Rule's `when_all` list are stored **lexicographically sorted** (CI-enforced) so the composed id is canonical. `then` stays in authored order.
- **Fact id (§3.2):** `f-` + first **12 hex** chars of SHA-256 of the canonical claim string.
- **Value normalization before hashing (§3.5):** strings NFC + trimmed + whitespace-collapsed; free-text sentences additionally lowercased and stripped of terminal punctuation (copyedit-tolerant); dates ISO-8601; version values verbatim.
- **YAML normalization (§3.5):** YAML 1.2, UTF-8, NFC; 2-space indent; keys in schema-declared order; one record per file; no anchors/aliases/tags; prose in `>-` folded blocks, code in `|` literal blocks; 100-column soft wrap; dates as quoted ISO-8601 strings; keyed lists sorted by `key`; `sources` lists in authored order; edge file names must equal their `id`. Idempotent.
- **Pre-emptive schema fields (§14 Stage 1):** `exclusivity`, `applies_to`, `aliases`, `absence_scope`, `language_kind`, `syntax_check`, `grounding` — all present in the schemas before the first node is authored.

---

## Interface contract produced for sub-plans 1B–1E

These are the exact names/signatures 1B–1E build against. Keep them stable; a rename here is a downstream break.

```python
# langatlas_validate.ids
def is_valid_slug(s: str) -> bool
def compose_instance_id(language: str, feature: str) -> str          # -> "fi.<language>.<feature>"
def compose_edge_id(edge_type: str, frm: str, to: str) -> str        # -> "edge.<type>.<from>.<to>"
def canonical_endpoints(a: str, b: str) -> tuple[str, str]           # lexicographic (alternative-to)
def canonical_when_all(feature_ids: list[str]) -> list[str]          # sorted copy
def compose_rule_id(slug: str) -> str                                # -> "rule-<slug>"
def compose_syntax_id(instance_id: str, key: str) -> str             # -> "<instance-id>.sx.<key>"

# langatlas_validate.schema
RECORD_KINDS: tuple[str, ...]   # ("feature","feature-instance","edge","affects-quality-edge",
                                #  "rule","language","language-registry","concept","source")
def validate_record(data: dict, kind: str) -> list[str]              # [] == valid; else error strings

# langatlas_validate.locators
def validate_locator_shape(locator: str, allowed_kinds: Iterable[str] | None = None) -> str | None
def validate_locator(locator: str, source_id: str, index: "SourceChunksIndex",
                     allowed_kinds: Iterable[str] | None = None) -> "LocatorResult"

# langatlas_validate.normalize
def normalize_value(value: str, *, freetext: bool = False) -> str
def normalize_record(text: str, kind: str) -> str                    # idempotent whole-file formatter

# langatlas_validate.claims
def build_claim(kind: str, **params: str) -> str                     # canonical S-expression string
def fact_id(claim: str) -> str                                       # -> "f-" + sha256(claim)[:12]
def render_claim(kind: str, params: dict) -> str                     # English from claim-templates/
```

---

## File structure

```
tools/validate/
  pyproject.toml                         # package langatlas_validate, console script langatlas-validate
  src/langatlas_validate/
    __init__.py                          # __version__
    cli.py                               # argparse dispatch: precommit | ci | regression
    ids.py                               # slug/id grammar + composed record ids
    schema.py                            # JSON Schema loader + validate_record
    locators.py                          # locator grammar table + two-phase validation
    normalize.py                         # normalize_value + normalize_record
    claims.py                            # canonical claims, fact-id hashing, template rendering
    regression.py                        # fixture runner + pluggable checker registry
  tests/                                 # package unit tests (pytest)
    test_ids.py test_schema.py test_locators.py
    test_normalize.py test_claims.py test_regression.py test_cli.py

ontology/
  VERSION                                # "0.1.0"
  CHANGELOG.md
  redirects.yaml                         # slug-history map (starts empty)
  migrations/                            # (empty; 1D/D38 populates)
  schema/
    defs.schema.json                     # shared $defs: sources-entry, provenance
    feature.schema.json  feature-instance.schema.json  concept.schema.json
    edge.schema.json  affects-quality-edge.schema.json  rule.schema.json
    language.schema.json  language-registry.schema.json  source.schema.json
  taxonomy/
    layers.yaml  dimensions.yaml  edge-types.yaml  qualities.yaml
  claim-templates/
    instance-exists.yaml  instance-field.yaml  edge-exists.yaml
    edge-polarity.yaml  rule-exists.yaml  quality-assessment.yaml

concepts/  features/                     # (empty dirs, .gitkeep)
languages/_registry.yaml                 # language-id mint authority (starts empty)
edges/  rules/  sources/                  # (empty dirs, .gitkeep)
tombstones.yaml  contradictions.yaml  overrides.yaml  sources/_tombstones.yaml   # empty ledgers

tests/fixtures/providers/                # regression fixtures consumed by `regression run`
  schema-shape/                          # valid + invalid record fixtures per kind
```

---

## Task 1: Package + data-store scaffold

Creates the empty directory tree, the versioned `ontology/` skeleton, the taxonomy files, and an installable package that answers `--version`. No behavior yet — this is the ground every later task stands on.

**Files:**
- Create: `tools/validate/pyproject.toml`
- Create: `tools/validate/src/langatlas_validate/__init__.py`
- Create: `tools/validate/src/langatlas_validate/cli.py`
- Create: `ontology/VERSION`, `ontology/CHANGELOG.md`, `ontology/redirects.yaml`
- Create: `ontology/taxonomy/{layers,dimensions,edge-types,qualities}.yaml`
- Create: empty ledgers `tombstones.yaml`, `contradictions.yaml`, `overrides.yaml`, `sources/_tombstones.yaml`, `languages/_registry.yaml`
- Create: `.gitkeep` in `concepts/`, `features/`, `edges/`, `rules/`, `sources/`, `ontology/migrations/`
- Test: `tools/validate/tests/test_cli.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: installed console script `langatlas-validate`; `langatlas_validate.__version__` == `"0.1.0"`.

- [x] **Step 1: Commit this plan file first (per project CLAUDE.md).**

```bash
git add docs/superpowers/plans/2026-07-25-stage-1a-canonical-store-foundation.md
git commit -m "docs(#stage-1a): add canonical store foundation plan"
```

- [x] **Step 2: Write `pyproject.toml`.**

```toml
# tools/validate/pyproject.toml
[project]
name = "langatlas-validate"
version = "0.1.0"
description = "LangAtlas canonical-store validator and normalizer"
requires-python = ">=3.12"
license = "MIT"
dependencies = ["ruamel.yaml>=0.18", "jsonschema>=4.21"]

[project.scripts]
langatlas-validate = "langatlas_validate.cli:main"

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/langatlas_validate"]
```

- [x] **Step 3: Write the package init and a minimal CLI.**

```python
# tools/validate/src/langatlas_validate/__init__.py
__version__ = "0.1.0"
```

```python
# tools/validate/src/langatlas_validate/cli.py
import argparse
from langatlas_validate import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-validate")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_subparsers(dest="command")
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: Create the data-store skeleton files.**

`ontology/VERSION` contains exactly `0.1.0` followed by a trailing newline. `ontology/redirects.yaml`, all four root/`sources/` ledgers, and `languages/_registry.yaml` each contain a single top-level empty mapping so they parse as valid YAML:

```yaml
# ontology/redirects.yaml
redirects: {}
```

```yaml
# tombstones.yaml
tombstones: []
```

Use the same one-key-empty-collection shape for `contradictions.yaml` (`contradictions: []`), `overrides.yaml` (`overrides: []`), `sources/_tombstones.yaml` (`tombstones: []`), and `languages/_registry.yaml` (`languages: {}`). `ontology/CHANGELOG.md` gets a one-line heading `# Ontology changelog`. Put a literal `.gitkeep` (empty file) in each of `concepts/`, `features/`, `edges/`, `rules/`, `sources/`, `ontology/migrations/`.

- [x] **Step 5: Write the four taxonomy files with their pre-emptive fields.**

```yaml
# ontology/taxonomy/layers.yaml
layers:
  - id: 1
    name: syntax
  - id: 2
    name: semantic
  - id: 3
    name: design-choice
```

```yaml
# ontology/taxonomy/dimensions.yaml
# Each dimension carries `exclusivity` (default exclusive, D39) and
# `applies_to` (default [general-purpose], D50) pre-emptively.
dimensions: []
```

```yaml
# ontology/taxonomy/edge-types.yaml
edge_types:
  - id: requires
  - id: enables
  - id: influences        # polarity field, ± only
  - id: conflicts-with
  - id: alternative-to
  - id: affects-quality   # feature -> quality, signed + strength
```

```yaml
# ontology/taxonomy/qualities.yaml
qualities: []
```

- [x] **Step 6: Write the failing test.**

```python
# tools/validate/tests/test_cli.py
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_version_flag(capsys):
    from langatlas_validate.cli import main
    with pytest_raises_systemexit() as code:
        main(["--version"])
    assert code.value == 0


def test_version_string():
    import langatlas_validate
    assert langatlas_validate.__version__ == "0.1.0"


def test_version_file_matches_package():
    version_file = (REPO_ROOT / "ontology" / "VERSION").read_text().strip()
    assert version_file == "0.1.0"


class pytest_raises_systemexit:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        assert exc_type is SystemExit, f"expected SystemExit, got {exc_type}"
        self.value = exc.code
        return True
```

- [x] **Step 7: Run the test to verify it fails.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_validate'` (package not yet installed).

- [x] **Step 8: Install the package in editable mode and re-run.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_cli.py -v`
Expected: PASS on all three tests (uv resolves the local package from `pyproject.toml` automatically).

- [x] **Step 9: Commit.**

```bash
git add tools/validate/pyproject.toml tools/validate/src tools/validate/tests/test_cli.py \
        ontology concepts features edges rules sources languages tombstones.yaml \
        contradictions.yaml overrides.yaml
git commit -m "feat(#stage-1a): scaffold canonical store + validate package"
```

---

## Task 2: Slug/id machinery

The deterministic id grammar every other task and every later sub-plan depends on. Pure string functions, zero I/O.

**Files:**
- Create: `tools/validate/src/langatlas_validate/ids.py`
- Test: `tools/validate/tests/test_ids.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `is_valid_slug`, `compose_instance_id`, `compose_edge_id`, `canonical_endpoints`, `canonical_when_all`, `compose_rule_id`, `compose_syntax_id` (signatures in the top-of-plan contract).

- [x] **Step 1: Write the failing test.**

```python
# tools/validate/tests/test_ids.py
from langatlas_validate.ids import (
    is_valid_slug, compose_instance_id, compose_edge_id,
    canonical_endpoints, canonical_when_all, compose_rule_id, compose_syntax_id,
)


def test_valid_slugs():
    assert is_valid_slug("pattern-matching")
    assert is_valid_slug("cpp")
    assert is_valid_slug("a")


def test_invalid_slugs():
    assert not is_valid_slug("Pattern-Matching")     # uppercase
    assert not is_valid_slug("2fa")                   # leading digit
    assert not is_valid_slug("-lead")                 # leading hyphen
    assert not is_valid_slug("double--hyphen")        # empty segment
    assert not is_valid_slug("trailing-")             # trailing hyphen
    assert not is_valid_slug("under_score")           # non [a-z0-9-]
    assert not is_valid_slug("x" * 49)                # over 48 chars
    assert is_valid_slug("x" * 48)                    # exactly 48 ok


def test_composed_ids():
    assert compose_instance_id("rust", "pattern-matching") == "fi.rust.pattern-matching"
    assert compose_edge_id("requires", "ownership", "move-semantics") == \
        "edge.requires.ownership.move-semantics"
    assert compose_rule_id("laziness-needs-purity") == "rule-laziness-needs-purity"
    assert compose_syntax_id("fi.rust.pattern-matching", "basic-match") == \
        "fi.rust.pattern-matching.sx.basic-match"


def test_canonical_ordering():
    # alternative-to endpoints stored lexicographically (§3.3)
    assert canonical_endpoints("zeta", "alpha") == ("alpha", "zeta")
    assert canonical_endpoints("alpha", "zeta") == ("alpha", "zeta")
    # when_all sorted before hashing (D64)
    assert canonical_when_all(["side-effects-allowed", "lazy-evaluation"]) == \
        ["lazy-evaluation", "side-effects-allowed"]


def test_composers_reject_bad_slugs():
    import pytest
    with pytest.raises(ValueError):
        compose_instance_id("Rust", "pattern-matching")
```

- [x] **Step 2: Run the test to verify it fails.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_ids.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_validate.ids'`.

- [x] **Step 3: Implement `ids.py`.**

```python
# tools/validate/src/langatlas_validate/ids.py
import re

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_SLUG_LEN = 48


def is_valid_slug(s: str) -> bool:
    return len(s) <= MAX_SLUG_LEN and bool(SLUG_RE.match(s))


def _require_slug(s: str) -> str:
    if not is_valid_slug(s):
        raise ValueError(f"invalid slug/id: {s!r}")
    return s


def compose_instance_id(language: str, feature: str) -> str:
    return f"fi.{_require_slug(language)}.{_require_slug(feature)}"


def compose_edge_id(edge_type: str, frm: str, to: str) -> str:
    return f"edge.{_require_slug(edge_type)}.{_require_slug(frm)}.{_require_slug(to)}"


def compose_rule_id(slug: str) -> str:
    return f"rule-{_require_slug(slug)}"


def compose_syntax_id(instance_id: str, key: str) -> str:
    return f"{instance_id}.sx.{_require_slug(key)}"


def canonical_endpoints(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((_require_slug(a), _require_slug(b))))  # type: ignore[return-value]


def canonical_when_all(feature_ids: list[str]) -> list[str]:
    return sorted(_require_slug(f) for f in feature_ids)
```

- [x] **Step 4: Run the test to verify it passes.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_ids.py -v`
Expected: PASS.

- [x] **Step 5: Commit.**

```bash
git add tools/validate/src/langatlas_validate/ids.py tools/validate/tests/test_ids.py
git commit -m "feat(#stage-1a): id/slug machinery with canonical ordering"
```

---

## Task 3: JSON Schemas + record validation

Authors the nine record schemas (with every pre-emptive field) and a loader that validates a parsed record against its kind. This is the schema-shape contract 1B–1E and Stage 2 read.

**Files:**
- Create: `ontology/schema/defs.schema.json`
- Create: `ontology/schema/{feature,feature-instance,concept,edge,affects-quality-edge,rule,language,language-registry,source}.schema.json`
- Create: `tools/validate/src/langatlas_validate/schema.py`
- Test: `tools/validate/tests/test_schema.py`

**Interfaces:**
- Consumes: `is_valid_slug` (Task 2), for the id-format check in `validate_record`.
- Produces: `RECORD_KINDS`, `validate_record(data, kind) -> list[str]`.

- [x] **Step 1: Write the shared `$defs` schema.**

```json
// ontology/schema/defs.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://langatlas.dev/schema/defs",
  "$defs": {
    "sourceEntry": {
      "type": "object",
      "additionalProperties": false,
      "required": ["source", "locator"],
      "properties": {
        "source": { "type": "string" },
        "locator": { "type": "string" },
        "quote": { "type": "string" }
      }
    },
    "sourcesList": {
      "type": "array",
      "items": { "$ref": "defs.schema.json#/$defs/sourceEntry" }
    },
    "provenance": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "proposer": { "type": "object" },
        "claim_origin": { "enum": ["source-derived", "prior"] },
        "debate_id": { "type": ["string", "null"] },
        "chat_run_id": { "type": ["string", "null"] },
        "candidate_source": {
          "enum": ["pldb", "wikidata", "hyperpolyglot", "internal-survey",
                   "sweep-questionnaire", "challenge"]
        },
        "sampling": { "type": "object" }
      }
    },
    "factBlock": {
      "type": "object",
      "additionalProperties": false,
      "required": ["text", "sources"],
      "properties": {
        "text": { "type": "string" },
        "sources": { "$ref": "defs.schema.json#/$defs/sourcesList" }
      }
    }
  }
}
```

- [x] **Step 2: Write `feature-instance.schema.json` in full (the pre-emptive-field carrier).**

```json
// ontology/schema/feature-instance.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://langatlas.dev/schema/feature-instance",
  "type": "object",
  "additionalProperties": false,
  "required": ["feature", "language", "status", "provenance"],
  "properties": {
    "feature": { "type": "string" },
    "language": { "type": "string" },
    "status": { "enum": ["present", "absent", "partial"] },
    "absence_scope": { "type": "string" },
    "since": {
      "type": "object",
      "additionalProperties": false,
      "required": ["value", "sources"],
      "properties": {
        "value": { "type": "string" },
        "sources": { "$ref": "defs.schema.json#/$defs/sourcesList" },
        "since_status": { "enum": ["as-cited", "back-dated"] }
      }
    },
    "notes_text": { "type": "string" },
    "characteristics": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["key", "text", "sources"],
        "properties": {
          "key": { "type": "string", "pattern": "^c-[a-z0-9]+(-[a-z0-9]+)*$" },
          "text": { "type": "string" },
          "sources": { "$ref": "defs.schema.json#/$defs/sourcesList" }
        }
      }
    },
    "notes": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["key", "type", "text", "sources"],
        "properties": {
          "key": { "type": "string", "pattern": "^n-[a-z0-9]+(-[a-z0-9]+)*$" },
          "type": { "enum": ["limitation", "extra", "alternative"] },
          "text": { "type": "string" },
          "sources": { "$ref": "defs.schema.json#/$defs/sourcesList" }
        }
      }
    },
    "syntax": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["key", "title", "origin", "code", "sources"],
        "properties": {
          "key": { "type": "string" },
          "title": { "type": "string" },
          "origin": { "type": "string", "pattern": "^(original|adapted-from:.+)$" },
          "code": { "type": "string" },
          "sources": { "$ref": "defs.schema.json#/$defs/sourcesList" }
        }
      }
    },
    "provenance": { "$ref": "defs.schema.json#/$defs/provenance" }
  },
  "allOf": [
    {
      "if": { "properties": { "status": { "const": "absent" } } },
      "then": { "required": ["absence_scope"] }
    }
  ]
}
```

- [x] **Step 3: Write `source.schema.json` in full (carries `grounding` + tier).**

```json
// ontology/schema/source.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://langatlas.dev/schema/source",
  "type": "object",
  "required": ["id", "type", "title", "custom"],
  "properties": {
    "id": { "type": "string" },
    "type": { "type": "string" },
    "title": { "type": "string" },
    "author": { "type": "array" },
    "issued": { "type": "object" },
    "URL": { "type": "string" },
    "DOI": { "type": "string" },
    "custom": {
      "type": "object",
      "additionalProperties": false,
      "required": ["tier", "grounding"],
      "properties": {
        "tier": { "enum": ["A", "B", "C", "D"] },
        "grounding": {
          "enum": ["formal-spec", "reference-implementation-docs",
                   "design-doc", "third-party-reference"]
        },
        "archive_url": { "type": "string" },
        "accessed": { "type": "string" },
        "added_by": { "type": "string" },
        "locator_kinds": { "type": "array", "items": { "type": "string" } },
        "edition": { "type": "string" },
        "edition_check_url": { "type": "string" },
        "canonical_source": { "type": "boolean" },
        "acquisition_note": { "type": "string" },
        "superseded_by": { "type": "string" }
      }
    }
  }
}
```

- [x] **Step 4: Write the remaining seven schemas from these field tables.**

Each is Draft 2020-12, `"type": "object"`, `"additionalProperties": false`, with `provenance` referencing `defs.schema.json#/$defs/provenance` and fact-bearing blocks referencing `#/$defs/factBlock`. Required fields are marked **R**.

`feature.schema.json`: `id` **R** (string), `slug` **R** (string), `name` **R** (string), `layer` **R** (enum 1/2/3), `dimension` (string; required iff `layer==3` via an `if/then` on `{"properties":{"layer":{"const":3}}}`), `cross_cutting` (boolean), `aliases` (array of string, default present), `realizes` (array of string), `summary` (`$ref` factBlock) **R**, `provenance` **R**.

`concept.schema.json`: `id` **R**, `slug` **R**, `name` **R**, `excluded_rationale` (string), `summary` (factBlock), `provenance` **R**.

`edge.schema.json`: `id` **R**, `type` **R** (enum `requires`/`enables`/`influences`/`conflicts-with`/`alternative-to`), `from` **R** (string), `to` **R** (string), `polarity` (enum `+`/`-`; required iff `type==influences`), `statement` **R** (`$ref` factBlock), `provenance` **R**.

`affects-quality-edge.schema.json`: `id` **R**, `type` **R** (const `affects-quality`), `from` **R** (feature id), `to` **R** (quality id), `assessments` **R** (array; each item `additionalProperties:false`, required `key`/`assessor`/`polarity`/`strength`/`statement`/`sources`; `polarity` enum `improves`/`hurts`; `strength` enum `weak`/`moderate`/`strong`; `assessor` object; `statement` string; `sources` `$ref` sourcesList), `provenance` **R**.

`rule.schema.json`: `id` **R**, `when_all` **R** (array of string, `"minItems": 2`), `effect` **R** (enum `requires`/`forbids`/`warn`), `then` **R** (array of string; may be empty only when `effect==warn` — enforce with an `if/then` requiring `"minItems":1` on `then` when `effect` is `requires` or `forbids`), `message` **R** (string), `sources` **R** (`$ref` sourcesList), `provenance` **R**.

`language.schema.json`: `id` **R**, `name` **R**, `language_kind` (enum `general-purpose`/`domain-specific`, default general-purpose), `domain` (string), `syntax_check` (enum `parser`/`none`), `file_extensions` (array of string), `first_appeared` (string), `provenance` **R**.

`language-registry.schema.json`: top-level object with one key `languages` **R** (object mapping language-id → object with the same `language_kind`/`domain`/`syntax_check`/`file_extensions`/`first_appeared` fields as `language.schema.json`, all optional except an inner `name` **R**).

- [x] **Step 5: Write the failing test.**

```python
# tools/validate/tests/test_schema.py
import pytest
from langatlas_validate.schema import RECORD_KINDS, validate_record


def test_record_kinds_complete():
    assert set(RECORD_KINDS) == {
        "feature", "feature-instance", "edge", "affects-quality-edge",
        "rule", "language", "language-registry", "concept", "source",
    }


def test_valid_feature_instance():
    rec = {
        "feature": "pattern-matching", "language": "rust", "status": "present",
        "provenance": {"claim_origin": "source-derived"},
    }
    assert validate_record(rec, "feature-instance") == []


def test_absent_requires_absence_scope():
    rec = {"feature": "x", "language": "rust", "status": "absent",
           "provenance": {"claim_origin": "source-derived"}}
    errors = validate_record(rec, "feature-instance")
    assert any("absence_scope" in e for e in errors)


def test_rule_arity_floor():
    rec = {"id": "rule-x", "when_all": ["a"], "effect": "warn", "then": [],
           "message": "m", "sources": [], "provenance": {}}
    errors = validate_record(rec, "rule")
    assert errors  # 1-antecedent rule rejected (min 2)


def test_source_requires_grounding_and_tier():
    rec = {"id": "s", "type": "book", "title": "T", "custom": {"tier": "A"}}
    errors = validate_record(rec, "source")
    assert any("grounding" in e for e in errors)


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        validate_record({}, "not-a-kind")
```

- [x] **Step 6: Run the test to verify it fails.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_validate.schema'`.

- [x] **Step 7: Implement `schema.py`.**

```python
# tools/validate/src/langatlas_validate/schema.py
import json
from functools import lru_cache
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

RECORD_KINDS = (
    "feature", "feature-instance", "edge", "affects-quality-edge",
    "rule", "language", "language-registry", "concept", "source",
)

# src layout: .../tools/validate/src/langatlas_validate/schema.py -> parents[4] == repo root
_SCHEMA_DIR = Path(__file__).resolve().parents[4] / "ontology" / "schema"


@lru_cache(maxsize=None)
def _registry() -> Registry:
    reg = Registry()
    for path in _SCHEMA_DIR.glob("*.schema.json"):
        contents = json.loads(path.read_text())
        reg = reg.with_resource(path.name, Resource.from_contents(contents))
    return reg


@lru_cache(maxsize=None)
def _validator(kind: str) -> Draft202012Validator:
    if kind not in RECORD_KINDS:
        raise ValueError(f"unknown record kind: {kind!r}")
    schema = json.loads((_SCHEMA_DIR / f"{kind}.schema.json").read_text())
    return Draft202012Validator(schema, registry=_registry())


def validate_record(data: dict, kind: str) -> list[str]:
    if kind not in RECORD_KINDS:
        raise ValueError(f"unknown record kind: {kind!r}")
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(_validator(kind).iter_errors(data), key=str)
    ]
```

Note: `referencing` ships with `jsonschema>=4.18`; no extra dependency. If `$ref` cross-file resolution needs the `defs.schema.json` id to match, ensure each schema's local `$ref` uses the `defs.schema.json#/$defs/...` form registered above.

- [x] **Step 8: Run the test to verify it passes.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_schema.py -v`
Expected: PASS. If a `$ref` fails to resolve, confirm the registry key (`defs.schema.json`) matches the `$ref` string exactly.

- [x] **Step 9: Commit.**

```bash
git add ontology/schema tools/validate/src/langatlas_validate/schema.py \
        tools/validate/tests/test_schema.py
git commit -m "feat(#stage-1a): record JSON Schemas with pre-emptive fields"
```

---

## Task 4: Locator grammar (two-phase)

Implements `validate_locator_shape` (pure regex, zero I/O — the phase-1 check used in pre-commit and imported by the D24 verifier) and the two-phase `validate_locator` whose resolution half takes a dependency-injected `SourceChunksIndex` (the real index arrives in 1C; here it is a `Protocol` + a fake used only in tests).

**Files:**
- Create: `tools/validate/src/langatlas_validate/locators.py`
- Test: `tools/validate/tests/test_locators.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `validate_locator_shape`, `validate_locator`, `SourceChunksIndex` (Protocol), `LocatorResult` (dataclass).

- [x] **Step 1: Write the failing test.**

```python
# tools/validate/tests/test_locators.py
from langatlas_validate.locators import (
    validate_locator_shape, validate_locator, LocatorResult,
)


def test_shape_matches_each_kind():
    assert validate_locator_shape("pp. 492–495") == "book-page"     # en dash
    assert validate_locator_shape("p. 492") == "book-page"
    assert validate_locator_shape("§13.2.1") == "numbered-section"
    assert validate_locator_shape("§ Match expressions") == "named-section"
    assert validate_locator_shape("#match-expressions") == "web-fragment"
    assert validate_locator_shape("reference/expr.html#match-guards") == "multipage-docs"
    assert validate_locator_shape("a1b2c3d:src/lib.rs#L10-L25") == "repo-file"
    assert validate_locator_shape("t=00:41:20") == "video"
    assert validate_locator_shape("PEP 634 §Overview") == "design-doc"


def test_shape_rejects_garbage():
    assert validate_locator_shape("just some text") is None
    assert validate_locator_shape("pp. 495-492") == "book-page"  # shape only; ordering not checked here


def test_shape_respects_allowed_kinds():
    assert validate_locator_shape("#frag", allowed_kinds=["book-page"]) is None
    assert validate_locator_shape("#frag", allowed_kinds=["web-fragment"]) == "web-fragment"


class _FakeIndex:
    def __init__(self, hits): self._hits = hits
    def resolve(self, source_id, locator): return self._hits


def test_resolution_bad_shape_short_circuits():
    res = validate_locator("garbage", "s1", _FakeIndex([]))
    assert isinstance(res, LocatorResult)
    assert res.shape_ok is False
    assert res.resolved is False


def test_resolution_hits():
    res = validate_locator("#frag", "s1", _FakeIndex(["chunk-1"]))
    assert res.shape_ok is True
    assert res.resolved is True
    assert res.chunk_ids == ["chunk-1"]
```

- [x] **Step 2: Run the test to verify it fails.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_locators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_validate.locators'`.

- [x] **Step 3: Implement `locators.py`.**

```python
# tools/validate/src/langatlas_validate/locators.py
import re
from dataclasses import dataclass, field
from typing import Iterable, Protocol

# §4.3 grammar table. Order matters: more specific patterns first.
LOCATOR_GRAMMAR: dict[str, re.Pattern] = {
    "book-page":        re.compile(r"^p{1,2}\. \d+(–\d+)?$"),
    "numbered-section": re.compile(r"^§\d+(\.\d+)*$"),
    "named-section":    re.compile(r"^(ch\. \d+|§ .+)$"),
    "design-doc":       re.compile(r"^[A-Za-z]+ \d+( §.+)?$"),
    "repo-file":        re.compile(r"^[0-9a-f]{7}:[^#]+#L\d+(-L\d+)?$"),
    "multipage-docs":   re.compile(r"^[^#]+#[^#]+$"),
    "web-fragment":     re.compile(r"^#[^#]+$"),
    "video":            re.compile(r"^t=\d{2}:\d{2}:\d{2}$"),
}


def validate_locator_shape(
    locator: str, allowed_kinds: Iterable[str] | None = None
) -> str | None:
    allowed = set(allowed_kinds) if allowed_kinds is not None else None
    for kind, pattern in LOCATOR_GRAMMAR.items():
        if allowed is not None and kind not in allowed:
            continue
        if pattern.match(locator):
            return kind
    return None


class SourceChunksIndex(Protocol):
    def resolve(self, source_id: str, locator: str) -> list[str]: ...


@dataclass
class LocatorResult:
    shape_ok: bool
    kind: str | None
    resolved: bool
    chunk_ids: list[str] = field(default_factory=list)


def validate_locator(
    locator: str,
    source_id: str,
    index: SourceChunksIndex,
    allowed_kinds: Iterable[str] | None = None,
) -> LocatorResult:
    kind = validate_locator_shape(locator, allowed_kinds)
    if kind is None:
        return LocatorResult(shape_ok=False, kind=None, resolved=False)
    chunk_ids = list(index.resolve(source_id, locator))
    return LocatorResult(
        shape_ok=True, kind=kind, resolved=bool(chunk_ids), chunk_ids=chunk_ids
    )
```

Note: `design-doc` and `multipage-docs`/`web-fragment` patterns can overlap (`PEP 634` vs a bare token). The dict order above resolves ties deterministically; the tests pin the intended winners. If a real corpus locator is mis-classified later, tighten `design-doc` to a documented `doc-kind` set — but that is out of scope here.

- [x] **Step 4: Run the test to verify it passes.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_locators.py -v`
Expected: PASS.

- [x] **Step 5: Commit.**

```bash
git add tools/validate/src/langatlas_validate/locators.py tools/validate/tests/test_locators.py
git commit -m "feat(#stage-1a): two-phase locator validation"
```

---

## Task 5: Value normalization (copyedit-tolerant)

`normalize_value` is the hashing-input normalizer that makes typo fixes free (they don't mint a new fact id) while a semantic rewrite does. Feeds Task 6's `fact_id`.

**Files:**
- Create: `tools/validate/src/langatlas_validate/normalize.py` (first half — `normalize_value`)
- Test: `tools/validate/tests/test_normalize.py` (value cases)

**Interfaces:**
- Consumes: nothing.
- Produces: `normalize_value(value, *, freetext=False) -> str`.

- [x] **Step 1: Write the failing test.**

```python
# tools/validate/tests/test_normalize.py
from langatlas_validate.normalize import normalize_value


def test_string_nfc_trim_collapse():
    assert normalize_value("  match   is\tan  expression ") == "match is an expression"


def test_non_freetext_preserves_case_and_punctuation():
    assert normalize_value("Rust 1.0.") == "Rust 1.0."


def test_freetext_lowercases_and_strips_terminal_punctuation():
    assert normalize_value("The compiler rejects it.", freetext=True) == \
        "the compiler rejects it"
    assert normalize_value("Is it exhaustive?", freetext=True) == "is it exhaustive"


def test_freetext_only_terminal_punctuation_stripped():
    assert normalize_value("a, b, and c.", freetext=True) == "a, b, and c"


def test_nfc_composition_stable():
    decomposed = "é"      # e + combining acute
    composed = "é"          # é
    assert normalize_value(decomposed) == normalize_value(composed)
```

- [x] **Step 2: Run the test to verify it fails.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_validate.normalize'`.

- [x] **Step 3: Implement the value half of `normalize.py`.**

```python
# tools/validate/src/langatlas_validate/normalize.py
import re
import unicodedata

_WS = re.compile(r"\s+")
_TERMINAL_PUNCT = ".!?;:,"


def normalize_value(value: str, *, freetext: bool = False) -> str:
    s = unicodedata.normalize("NFC", value)
    s = _WS.sub(" ", s).strip()
    if freetext:
        s = s.lower().rstrip(_TERMINAL_PUNCT)
    return s
```

- [x] **Step 4: Run the test to verify it passes.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_normalize.py -v`
Expected: PASS.

- [x] **Step 5: Commit.**

```bash
git add tools/validate/src/langatlas_validate/normalize.py tools/validate/tests/test_normalize.py
git commit -m "feat(#stage-1a): copyedit-tolerant value normalization"
```

---

## Task 6: Canonical claims, fact-id hashing, claim-template registry

Builds the canonical S-expression claim strings, the `f-`+12-hex fact id, and the D47 `ontology/claim-templates/` registry with a render function and a `claim_pattern`-vs-grammar cross-check.

**Files:**
- Create: `tools/validate/src/langatlas_validate/claims.py`
- Create: `ontology/claim-templates/{instance-exists,instance-field,edge-exists,edge-polarity,rule-exists,quality-assessment}.yaml`
- Test: `tools/validate/tests/test_claims.py`

**Interfaces:**
- Consumes: `normalize_value` (Task 5).
- Produces: `build_claim(kind, **params) -> str`, `fact_id(claim) -> str`, `render_claim(kind, params) -> str`, `load_claim_template(kind) -> dict`, `validate_claim_template(kind) -> list[str]`.

- [ ] **Step 1: Write the six claim-template files.**

Each file has a frozen `claim_pattern` (documentation/CI cross-check of the S-expression grammar) and an editable `render` block (Python `str.format`-style English). Example:

```yaml
# ontology/claim-templates/instance-exists.yaml
kind: instance-exists
claim_pattern: "instance-exists({instance_id}, status={status})"
render: "{language} {feature_verb} {feature} ({status})."
```

```yaml
# ontology/claim-templates/instance-field.yaml
kind: instance-field
claim_pattern: "instance-field({instance_id}, {field}, \"{value}\")"
render: "{feature} in {language} has {field} {value}."
```

```yaml
# ontology/claim-templates/edge-exists.yaml
kind: edge-exists
claim_pattern: "edge-exists({edge_id})"
render: "{from} {relation} {to}."
```

```yaml
# ontology/claim-templates/edge-polarity.yaml
kind: edge-polarity
claim_pattern: "edge-polarity({edge_id}, {polarity})"
render: "{from} influences {to} ({polarity})."
```

```yaml
# ontology/claim-templates/rule-exists.yaml
kind: rule-exists
claim_pattern: "rule-exists({rule_id}, sha256-16={hash})"
render: "{message}"
```

```yaml
# ontology/claim-templates/quality-assessment.yaml
# split identity (D47): templated existence claim; the assessment's free-text
# statement is hashed separately as a free-text kind, not rendered here.
kind: quality-assessment
claim_pattern: "quality-assessment({edge_id}, {assessment_key})"
render: "{from} {polarity} {quality} ({strength})."
```

- [ ] **Step 2: Write the failing test.**

```python
# tools/validate/tests/test_claims.py
import pytest
from langatlas_validate.claims import (
    build_claim, fact_id, render_claim, load_claim_template, validate_claim_template,
)


def test_build_instance_exists():
    assert build_claim("instance-exists", instance_id="fi.rust.pattern-matching",
                       status="present") == \
        "instance-exists(fi.rust.pattern-matching, status=present)"


def test_build_instance_field_quotes_value():
    assert build_claim("instance-field", instance_id="fi.rust.pattern-matching",
                       field="since", value="1.0") == \
        'instance-field(fi.rust.pattern-matching, since, "1.0")'


def test_build_freetext_kind_hashes_normalized_text():
    c1 = build_claim("characteristic", instance_id="fi.rust.pattern-matching",
                     key="c-exhaustive", text="The compiler rejects it.")
    c2 = build_claim("characteristic", instance_id="fi.rust.pattern-matching",
                     key="c-exhaustive", text="the compiler rejects it")  # copyedit
    assert c1 == c2                      # copyedit-tolerant
    assert "sha256-16=" in c1


def test_fact_id_shape_and_stability():
    fid = fact_id("instance-exists(fi.rust.pattern-matching, status=present)")
    assert fid.startswith("f-")
    assert len(fid) == 2 + 12
    assert all(ch in "0123456789abcdef" for ch in fid[2:])


def test_fact_id_changes_with_claim():
    a = fact_id("instance-exists(fi.rust.x, status=present)")
    b = fact_id("instance-exists(fi.rust.x, status=absent)")
    assert a != b


def test_render_uses_template():
    out = render_claim("instance-exists", {
        "language": "Rust", "feature_verb": "supports",
        "feature": "pattern matching", "status": "present"})
    assert out == "Rust supports pattern matching (present)."


def test_template_pattern_matches_grammar():
    assert validate_claim_template("instance-exists") == []


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        build_claim("nope")
```

- [ ] **Step 3: Implement `claims.py`.**

```python
# tools/langatlas_validate/claims.py   ->   tools/validate/src/langatlas_validate/claims.py
import hashlib
import re
from functools import lru_cache
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_validate.normalize import normalize_value

_TEMPLATE_DIR = Path(__file__).resolve().parents[4] / "ontology" / "claim-templates"
_yaml = YAML(typ="safe")

TEMPLATED_KINDS = (
    "instance-exists", "instance-field", "edge-exists",
    "edge-polarity", "rule-exists", "quality-assessment",
)
FREETEXT_KINDS = ("characteristic", "syntax-valid")


def _sha256_16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_claim(kind: str, **params: str) -> str:
    if kind == "instance-exists":
        return f"instance-exists({params['instance_id']}, status={params['status']})"
    if kind == "instance-field":
        value = normalize_value(params["value"])
        return f'instance-field({params["instance_id"]}, {params["field"]}, "{value}")'
    if kind == "edge-exists":
        return f"edge-exists({params['edge_id']})"
    if kind == "edge-polarity":
        return f"edge-polarity({params['edge_id']}, {params['polarity']})"
    if kind == "rule-exists":
        h = _sha256_16(normalize_value(params["message"], freetext=True))
        return f"rule-exists({params['rule_id']}, sha256-16={h})"
    if kind == "quality-assessment":
        return f"quality-assessment({params['edge_id']}, {params['assessment_key']})"
    if kind == "characteristic":
        h = _sha256_16(normalize_value(params["text"], freetext=True))
        return f"characteristic({params['instance_id']}, {params['key']}, sha256-16={h})"
    if kind == "syntax-valid":
        h = _sha256_16(normalize_value(params["code"], freetext=False))
        return f"syntax-valid({params['syntax_id']}, sha256-16={h})"
    raise ValueError(f"unknown claim kind: {kind!r}")


def fact_id(claim: str) -> str:
    return "f-" + hashlib.sha256(claim.encode("utf-8")).hexdigest()[:12]


@lru_cache(maxsize=None)
def load_claim_template(kind: str) -> dict:
    if kind not in TEMPLATED_KINDS:
        raise ValueError(f"no render template for kind: {kind!r}")
    return _yaml.load((_TEMPLATE_DIR / f"{kind}.yaml").read_text())


def render_claim(kind: str, params: dict) -> str:
    return load_claim_template(kind)["render"].format(**params)


_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def validate_claim_template(kind: str) -> list[str]:
    """CI cross-check: the frozen claim_pattern's shape is well-formed."""
    tpl = load_claim_template(kind)
    errors: list[str] = []
    if tpl.get("kind") != kind:
        errors.append(f"{kind}: kind field mismatch")
    if "claim_pattern" not in tpl or not _PLACEHOLDER.search(tpl["claim_pattern"]):
        errors.append(f"{kind}: claim_pattern missing or has no placeholders")
    if "render" not in tpl:
        errors.append(f"{kind}: render block missing")
    return errors
```

- [ ] **Step 4: Run the test to verify it passes.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_claims.py -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add tools/validate/src/langatlas_validate/claims.py ontology/claim-templates \
        tools/validate/tests/test_claims.py
git commit -m "feat(#stage-1a): canonical claims, fact-id hashing, claim-template registry"
```

---

## Task 7: Whole-file record normalization

`normalize_record` is the idempotent YAML formatter the pre-commit hook writes with and CI verifies. It enforces the §3.5 formatting rules against the schema-declared key order.

**Files:**
- Modify: `tools/validate/src/langatlas_validate/normalize.py` (add `normalize_record` + key-order source)
- Test: `tools/validate/tests/test_normalize.py` (add record cases)

**Interfaces:**
- Consumes: `RECORD_KINDS` and the schema files (Task 3) — key order is derived from each schema's `properties` insertion order.
- Produces: `normalize_record(text, kind) -> str`.

- [ ] **Step 1: Write the failing test (append to `test_normalize.py`).**

```python
from langatlas_validate.normalize import normalize_record


def test_record_key_order_and_indent():
    messy = "status: present\nlanguage: rust\nfeature: pattern-matching\n"
    out = normalize_record(messy, "feature-instance")
    lines = [l for l in out.splitlines() if ":" in l]
    assert lines[0].startswith("feature:")     # schema-declared order
    assert lines[1].startswith("language:")
    assert lines[2].startswith("status:")


def test_normalize_record_is_idempotent():
    messy = "status: present\nlanguage: rust\nfeature: pattern-matching\n"
    once = normalize_record(messy, "feature-instance")
    twice = normalize_record(once, "feature-instance")
    assert once == twice


def test_keyed_list_sorted_by_key():
    src = (
        "feature: pattern-matching\nlanguage: rust\nstatus: present\n"
        "characteristics:\n"
        "  - key: c-zeta\n    text: z\n    sources: []\n"
        "  - key: c-alpha\n    text: a\n    sources: []\n"
    )
    out = normalize_record(src, "feature-instance")
    assert out.index("c-alpha") < out.index("c-zeta")
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_normalize.py::test_record_key_order_and_indent -v`
Expected: FAIL — `ImportError: cannot import name 'normalize_record'`.

- [ ] **Step 3: Implement `normalize_record` in `normalize.py`.**

```python
# append to tools/validate/src/langatlas_validate/normalize.py
import io
import json
from functools import lru_cache
from pathlib import Path
from ruamel.yaml import YAML

_SCHEMA_DIR = Path(__file__).resolve().parents[4] / "ontology" / "schema"


@lru_cache(maxsize=None)
def _key_order(kind: str) -> tuple[str, ...]:
    schema = json.loads((_SCHEMA_DIR / f"{kind}.schema.json").read_text())
    return tuple(schema.get("properties", {}).keys())


def _reorder(data, order: tuple[str, ...]):
    if not isinstance(data, dict):
        return data
    ordered = {k: data[k] for k in order if k in data}
    for k in data:                       # any field not in schema keeps a stable tail slot
        if k not in ordered:
            ordered[k] = data[k]
    for k, v in ordered.items():
        if k in ("characteristics", "notes", "syntax") and isinstance(v, list):
            ordered[k] = sorted(v, key=lambda item: item.get("key", ""))
    return ordered


def normalize_record(text: str, kind: str) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    yaml.preserve_quotes = False
    data = yaml.load(text)
    data = _reorder(data, _key_order(kind))
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()
```

Note: keep the `import` statements at the top of the file when appending (Python needs them module-level). The `ruamel.yaml` round-trip loader is used here (not the `typ="safe"` one from `claims.py`) so block styles are controllable; that is fine — two `YAML` instances with different configs coexist.

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_normalize.py -v`
Expected: PASS (all value + record cases).

- [ ] **Step 5: Commit.**

```bash
git add tools/validate/src/langatlas_validate/normalize.py tools/validate/tests/test_normalize.py
git commit -m "feat(#stage-1a): idempotent whole-file record normalization"
```

---

## Task 8: Regression-fixture runner

The D48 fixture convention (`fixture_id`, `kind`, `mode: hard|soft`) with a pluggable checker registry — starting with the `schema-shape` checker (validates each fixture record against its schema and asserts the expected pass/fail). The other checkers (`provider-record-replay`, `questionnaire-shape`, `prompt-version-rerun`) are registered as stubs their owning sub-plans fill in.

**Files:**
- Create: `tools/validate/src/langatlas_validate/regression.py`
- Create: `tests/fixtures/providers/schema-shape/valid-feature-instance.yaml`
- Create: `tests/fixtures/providers/schema-shape/invalid-feature-instance.yaml`
- Test: `tools/validate/tests/test_regression.py`

**Interfaces:**
- Consumes: `validate_record` (Task 3).
- Produces: `run_regression(fixtures_dir) -> RegressionReport`, `CHECKERS` registry dict.

- [ ] **Step 1: Write two fixtures.**

```yaml
# tests/fixtures/providers/schema-shape/valid-feature-instance.yaml
fixture_id: valid-feature-instance
kind: schema-shape
mode: hard
record_kind: feature-instance
expect: pass
record:
  feature: pattern-matching
  language: rust
  status: present
  provenance:
    claim_origin: source-derived
```

```yaml
# tests/fixtures/providers/schema-shape/invalid-feature-instance.yaml
fixture_id: invalid-feature-instance
kind: schema-shape
mode: hard
record_kind: feature-instance
expect: fail
record:
  feature: pattern-matching
  language: rust
  status: absent          # absence_scope missing -> must fail
  provenance:
    claim_origin: source-derived
```

- [ ] **Step 2: Write the failing test.**

```python
# tools/validate/tests/test_regression.py
from pathlib import Path
from langatlas_validate.regression import run_regression, CHECKERS

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "providers"


def test_schema_shape_checker_registered():
    assert "schema-shape" in CHECKERS


def test_all_fixtures_pass_their_expectation():
    report = run_regression(FIXTURES)
    assert report.failures == [], report.failures
    assert report.ran >= 2


def test_report_counts():
    report = run_regression(FIXTURES)
    assert report.ran == report.passed + len(report.failures)
```

- [ ] **Step 3: Run the test to verify it fails.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_regression.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_validate.regression'`.

- [ ] **Step 4: Implement `regression.py`.**

```python
# tools/validate/src/langatlas_validate/regression.py
from dataclasses import dataclass, field
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_validate.schema import validate_record

_yaml = YAML(typ="safe")


@dataclass
class RegressionReport:
    ran: int = 0
    passed: int = 0
    failures: list[str] = field(default_factory=list)


def _schema_shape_checker(fixture: dict) -> str | None:
    """Return None on success, else an error message."""
    errors = validate_record(fixture["record"], fixture["record_kind"])
    valid = errors == []
    expected_pass = fixture["expect"] == "pass"
    if valid != expected_pass:
        return (f"{fixture['fixture_id']}: expected {fixture['expect']}, "
                f"got {'pass' if valid else 'fail'} (errors={errors})")
    return None


def _stub_checker(fixture: dict) -> str | None:
    return None   # owned by a later sub-plan; a bare stub never fails the suite


CHECKERS = {
    "schema-shape": _schema_shape_checker,
    "provider-record-replay": _stub_checker,
    "questionnaire-shape": _stub_checker,
    "prompt-version-rerun": _stub_checker,
}


def run_regression(fixtures_dir: Path) -> RegressionReport:
    report = RegressionReport()
    for path in sorted(fixtures_dir.rglob("*.yaml")):
        fixture = _yaml.load(path.read_text())
        checker = CHECKERS.get(fixture.get("kind"))
        if checker is None:
            report.failures.append(f"{path}: unknown checker kind {fixture.get('kind')!r}")
            report.ran += 1
            continue
        report.ran += 1
        err = checker(fixture)
        if err is None:
            report.passed += 1
        else:
            report.failures.append(err)
    return report
```

- [ ] **Step 5: Run the test to verify it passes.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_regression.py -v`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add tools/validate/src/langatlas_validate/regression.py tests/fixtures \
        tools/validate/tests/test_regression.py
git commit -m "feat(#stage-1a): regression-fixture runner with schema-shape checker"
```

---

## Task 9: CLI contracts (precommit / ci / regression)

Wires the pieces into the three D48 call-site contracts so the R0 pipeline (1D/1E) and the pre-commit hook can shell out to `langatlas-validate`. `precommit` is fast and phase-1-only (shape checks, no `source_chunks` I/O); `ci` adds the full regression run and a normalization-drift check; `regression run` is the standalone fixture runner.

**Files:**
- Modify: `tools/validate/src/langatlas_validate/cli.py`
- Test: `tools/validate/tests/test_cli.py` (add command cases)

**Interfaces:**
- Consumes: `validate_record` + `RECORD_KINDS` (Task 3), `validate_locator_shape` (Task 4), `normalize_record` (Task 7), `run_regression` (Task 8).
- Produces: `main(argv) -> int`; `cmd_precommit(files) -> int`; `cmd_ci() -> int`; `cmd_regression_run() -> int`.

- [ ] **Step 1: Write the failing test (append to `test_cli.py`).**

```python
from langatlas_validate.cli import main


def test_regression_run_exit_zero():
    assert main(["regression", "run"]) == 0


def test_precommit_on_clean_file(tmp_path):
    f = tmp_path / "pattern-matching.yaml"
    f.write_text(
        "feature: pattern-matching\nlanguage: rust\nstatus: present\n"
        "provenance:\n  claim_origin: source-derived\n"
    )
    assert main(["precommit", "--kind", "feature-instance", str(f)]) == 0


def test_precommit_rejects_invalid_file(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(
        "feature: x\nlanguage: rust\nstatus: absent\n"          # absence_scope missing
        "provenance:\n  claim_origin: source-derived\n"
    )
    assert main(["precommit", "--kind", "feature-instance", str(f)]) == 1


def test_ci_exit_zero_on_clean_repo():
    assert main(["ci"]) == 0
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `cd tools/validate && uv run --extra dev pytest tests/test_cli.py -v`
Expected: FAIL — the new subcommands are not wired (`SystemExit: 2` from argparse or `AttributeError`).

- [ ] **Step 3: Implement the CLI dispatch.**

```python
# tools/validate/src/langatlas_validate/cli.py
import argparse
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_validate import __version__
from langatlas_validate.schema import validate_record, RECORD_KINDS
from langatlas_validate.normalize import normalize_record
from langatlas_validate.regression import run_regression

_yaml = YAML(typ="safe")
_REPO_ROOT = Path(__file__).resolve().parents[4]   # src layout: one level deeper than tests/
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "providers"


def cmd_precommit(files: list[str], kind: str) -> int:
    rc = 0
    for f in files:
        text = Path(f).read_text()
        data = _yaml.load(text)
        errors = validate_record(data, kind)
        if normalize_record(text, kind) != text:
            errors.append(f"{f}: not normalized (run `langatlas-validate` write mode)")
        for e in errors:
            print(f"{f}: {e}")
        rc = rc or (1 if errors else 0)
    return rc


def cmd_ci() -> int:
    report = run_regression(_FIXTURES)
    for failure in report.failures:
        print(failure)
    return 1 if report.failures else 0


def cmd_regression_run() -> int:
    report = run_regression(_FIXTURES)
    for failure in report.failures:
        print(failure)
    print(f"ran={report.ran} passed={report.passed} failed={len(report.failures)}")
    return 1 if report.failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-validate")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    p_pre = sub.add_parser("precommit")
    p_pre.add_argument("--kind", required=True, choices=RECORD_KINDS)
    p_pre.add_argument("files", nargs="+")

    sub.add_parser("ci")

    p_reg = sub.add_parser("regression")
    p_reg.add_argument("regression_command", choices=["run"])

    args = parser.parse_args(argv)
    if args.command == "precommit":
        return cmd_precommit(args.files, args.kind)
    if args.command == "ci":
        return cmd_ci()
    if args.command == "regression":
        return cmd_regression_run()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: the `precommit --kind` flag is a pragmatic v0 for this sub-plan — 1D's commit protocol will infer `kind` from the file's path (`languages/*/instances/*.yaml` → `feature-instance`, etc.). Leave that path-inference to 1D; do not build it here.

- [ ] **Step 4: Run the full package test suite.**

Run: `cd tools/validate && uv run --extra dev pytest -v`
Expected: PASS — every test from Tasks 1–9.

- [ ] **Step 5: Commit.**

```bash
git add tools/validate/src/langatlas_validate/cli.py tools/validate/tests/test_cli.py
git commit -m "feat(#stage-1a): precommit/ci/regression CLI contracts"
```

---

## Definition of done (1A exit)

- `cd tools/validate && uv run --extra dev pytest` is green across all nine tasks.
- `uv run langatlas-validate ci` exits 0 against the empty canonical store.
- The interface-contract functions at the top of this plan all exist with the stated signatures — 1B can import `RunContext`-adjacent nothing yet, but 1C can import `validate_locator`, 1D can import `validate_record`/`normalize_record`, and the build can import `build_claim`/`fact_id`/`render_claim`.
- `ontology/VERSION` reads `0.1.0`; every pre-emptive field (`exclusivity`, `applies_to`, `aliases`, `absence_scope`, `language_kind`, `syntax_check`, `grounding`) is present in the schemas.
- Check off each `[ ]` in the spec's §14 Stage 1 list that 1A owns: repo scaffolding line, the `tools/validate/` line, and the claim-template registry line.

---

## Self-review notes (against the cross-stage plan's 1A "Produces for 1B–1E")

- **Schema shapes** → Task 3 (nine schemas, all pre-emptive fields) + the `defs.schema.json` shared sub-schemas. ✓
- **Canonical-claim / normalization rules** → Task 5 (`normalize_value`), Task 6 (`build_claim`/`fact_id`), Task 7 (`normalize_record`). ✓
- **CLI signatures (`normalize_record`, `validate_locator_shape`)** → exported and tested in Tasks 4 and 7; surfaced through the CLI in Task 9. ✓
- **`ontology/` at `VERSION 0.1.0`, id/slug machinery, claim-template registry, validator CLI** (the §14 Stage-1 1A checklist items) → Tasks 1, 2, 6, 9. ✓
- Types are consistent across tasks: `validate_record(data, kind) -> list[str]`, `LocatorResult` dataclass, `RegressionReport` dataclass, and the `build_claim`/`fact_id`/`render_claim` trio are referenced with the same names in every consuming task. ✓
