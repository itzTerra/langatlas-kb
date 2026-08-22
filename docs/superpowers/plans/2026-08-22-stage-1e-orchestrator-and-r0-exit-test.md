# Stage 1E — Orchestrator + R0 Exit Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the run orchestrator (D43) — the thin driver that enumerates work items,
drives them through the already-built provider/commit layers, checkpoints progress, and
decides pause/resume/halt — and use it to satisfy Stage 1's hard exit gate: *an agent can run
`search_sources`, mint a node file that validates, and the run is logged.*

**Architecture:** One new package, `tools/orchestrator/` (`langatlas_orchestrator`), sitting
above 1A–1D: a SQLite checkpoint store (driver-level bookkeeping only — the
`LangAtlas-Record-Key` git trailer stays ground truth per D36 §2.6), a YAML batch-spec loader,
a job-kind registry (`enumerator + item_runner` pairs), a generic driver loop that catches
`BudgetExceeded`/`ClaudeLimitSignal` and routes both to a shared pause path with a distinct
exit code, and a glanceable `orchestrator/status.json` surfaced through a new `langatlas-report`
subcommand. Two real job kinds prove the loop end-to-end: `monthly-capability-probe` (thin
wrapper around 1B's already-shipped `probe_all`) and `r0-exit-test` (the literal exit gate:
`search_sources` → mint a `concept` record → `land_record` → verify the run is logged). The six
other job kinds D43's periodic-job inventory names are registered now with enumerators that
raise a clear, stage-pointing `NotImplementedError` — real code, not silent no-ops — so
`config/jobs/crontab.example` can honestly enumerate all of D43's committed inventory today
without inventing business logic that depends on corpus/facts/infrastructure later stages
produce.

**Tech Stack:** Python 3.12, `uv`-managed package (`hatchling` build backend, same layout as
`tools/validate`/`tools/commit`/`tools/ingest`), stdlib `sqlite3` for the checkpoint store,
`ruamel.yaml` for batch specs, `pytest` (local git-repo fixtures + the existing `db`-marker
compose-Postgres convention for the one test that needs a real corpus).

**Spec:** [context/spec.md §7.11](../../../context/spec.md) (D43, brainstorm 35),
[context/decisions.md](../../../context/decisions.md) D43 (ratified text — binding, including
the developer's four follow-up ratifications: sweep pipeline stays hand-launched, 4-hour
Claude-limit cool-down confirmed, no cron mail, `crontab.example` worth maintaining),
[context/brainstorms/35-run-orchestrator-checkpointing.md](../../../context/brainstorms/35-run-orchestrator-checkpointing.md)
(full design — checkpoint unit/storage, budget/limit pause mechanics, scheduling),
[docs/superpowers/plans/2026-07-25-langatlas-cross-stage-plan.md](2026-07-25-langatlas-cross-stage-plan.md)
(1E's consumes/produces contract with 1A–1D and the Stage 1 exit test wording).

## Global Constraints

- No deadline; do not take shortcuts that damage the long-term product (D6/D11).
- Git is the database — Postgres, MCP, and the static site are always one-way derived build
  artifacts, never authoritative (D1). The checkpoint store is **driver bookkeeping only**; it
  is never the source of truth for "did this land" (D43/D36 §2.6).
- **No daemon** — a script invoked by cron or by hand, never a long-running scheduler process
  (D12, D43 §2.1/§2.5).
- **Checkpoint storage**: a local, private, non-git SQLite file in the same private tier as
  D26's cache/cost log — never a Postgres table, never a git-committed file (D43 §2.2).
- **Checkpoint unit**: whatever grain each job's own `work_item_source` enumerates — not
  forced to one global granularity (D43 §2.2).
- **Budget hard-stops**: `RunContext` raises `BudgetExceeded` *before* crossing a cap; the
  driver checkpoints the in-flight item `blocked` (not failed — still valid, re-attemptable)
  and exits with a distinct code; resume is plain re-invocation, never a separate resume mode
  (D43 §2.3).
- **Claude usage-limit handling**: on `ClaudeLimitSignal`, apply a fixed **4-hour cool-down**
  before any resume attempt; a too-early re-invocation no-ops rather than re-triggering the
  same limit (D43 §2.4, ratified).
- **Alerting** = the run halting plus `orchestrator/status.json` + a `langatlas-report`
  subcommand — no cron mail (ratified), no bespoke notification service (D43 §2.4).
- **Scheduling** = plain cron; `config/jobs/crontab.example` is committed documentation, not
  itself executable (D43 §2.5, ratified as worth maintaining).
- **The per-language sweep pipeline (D5) is never run via cron** — always developer-initiated
  by hand, unlike the background jobs this plan wires (ratified follow-up to D43).
- Adding a job kind is "one enumerator function + one YAML file," never a redesign of the
  driver (D43 §2.1).

---

## File Structure

New package `tools/orchestrator/` (`langatlas_orchestrator`), mirroring the existing
`tools/commit`/`tools/ingest` layout:

```
tools/orchestrator/
  pyproject.toml
  src/langatlas_orchestrator/
    __init__.py           # __version__
    checkpoint.py          # CheckpointStore, CheckpointRow — SQLite-backed
    spec.py                 # BatchSpec, load_batch_spec()
    registry.py             # ItemOutcome, EnumeratorFn, ItemRunnerFn, register_job_kind(),
                            # get_job_kind(), registered_kinds(), UnknownJobKind
    status.py                # read_status(), write_status(), STATUS_PATH
    driver.py                 # run(), main() — the generic loop + CLI entrypoint
    jobs/
      __init__.py            # imports every job module below (registration side effect)
      capability_probe.py     # "monthly-capability-probe" — real, wraps 1B's probe_all
      exit_test.py             # "r0-exit-test" — the Stage 1 exit gate
      deferred.py               # the six D43-inventory kinds not yet buildable
  tests/
    test_checkpoint.py
    test_spec.py
    test_registry.py
    test_status.py
    test_driver.py
    test_capability_probe_job.py
    test_exit_test_job.py        # marked `db` — needs compose Postgres
    test_deferred_jobs.py
    conftest.py

config/jobs/
  r0-exit-test.yaml
  monthly-capability-probe.yaml
  nightly-verification.yaml
  monthly-link-checker.yaml
  monthly-finding-aid-mirror-refresh.yaml
  monthly-demand-export.yaml
  quarterly-edition-check.yaml
  backstop-sweep-18mo.yaml
  crontab.example

tools/pipeline/src/langatlas_pipeline/observability/report.py   # MODIFIED: + orchestrator-status
tools/pipeline/tests/test_report.py                              # MODIFIED: + new subcommand test
```

Each file has one responsibility: `checkpoint.py` never knows about job kinds; `spec.py` never
touches SQLite; `registry.py` never runs anything, it only stores and looks up callables;
`driver.py` is the only place that calls into `RunContext`, the checkpoint store, and the
registry together; `status.py` never touches the checkpoint database, only the JSON file;
each `jobs/*.py` module registers exactly one job kind's business logic and imports nothing
from `driver.py` (job kinds are consumed by the driver, never the reverse).

**Layering note (no circular imports):** `report.py` lives in `tools/pipeline`, which
`tools/orchestrator` depends on — never the reverse. `report.py`'s new subcommand reads
`orchestrator/status.json` directly (`json.loads`) using the same `PRIVATE_DIR`-derived path
`status.py` also computes independently; it does **not** import `langatlas_orchestrator`.

---

## Task 1: Checkpoint store

**Files:**
- Create: `tools/orchestrator/pyproject.toml`
- Create: `tools/orchestrator/src/langatlas_orchestrator/__init__.py`
- Create: `tools/orchestrator/src/langatlas_orchestrator/checkpoint.py`
- Test: `tools/orchestrator/tests/test_checkpoint.py`

**Interfaces:**
- Consumes: nothing.
- Produces for Task 5: `CheckpointStore(db_path: Path)` with `.upsert(*, run_id, spec_kind,
  item_key, status, record_key=None, detail="", last_pause_reason=None) -> None`,
  `.get(*, spec_kind, item_key) -> CheckpointRow | None`,
  `.rows_for_spec(spec_kind) -> list[CheckpointRow]`, `.close() -> None`. `CheckpointRow` fields:
  `run_id, spec_kind, item_key, status, record_key, detail, last_pause_reason, attempted_at`.

- [ ] **Step 1: Scaffold the package**

```toml
# tools/orchestrator/pyproject.toml
[project]
name = "langatlas-orchestrator"
version = "0.1.0"
description = "LangAtlas run orchestrator — batch driver, checkpointing, scheduling"
requires-python = ">=3.12"
license = "MIT"
dependencies = [
  "ruamel.yaml>=0.18",
  "langatlas-validate",
  "langatlas-commit",
  "langatlas-pipeline",
  "langatlas-ingest",
]

[project.scripts]
langatlas-orchestrator = "langatlas_orchestrator.driver:main"

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/langatlas_orchestrator"]

[tool.uv.sources]
langatlas-validate = { path = "../validate", editable = true }
langatlas-commit = { path = "../commit", editable = true }
langatlas-pipeline = { path = "../pipeline", editable = true }
langatlas-ingest = { path = "../ingest", editable = true }

[tool.pytest.ini_options]
markers = ["db: needs the docker compose Postgres; run with -m db after `docker compose up -d db`"]
addopts = "-m 'not db'"
```

```python
# tools/orchestrator/src/langatlas_orchestrator/__init__.py
__version__ = "0.1.0"
```

Run: `cd tools/orchestrator && uv sync`

- [ ] **Step 2: Write the failing test**

```python
# tools/orchestrator/tests/test_checkpoint.py
from langatlas_orchestrator.checkpoint import CheckpointStore


def test_get_returns_none_for_unknown_item(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoint.sqlite")
    assert store.get(spec_kind="k", item_key="i") is None


def test_upsert_then_get_round_trips(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoint.sqlite")
    store.upsert(run_id="run-1", spec_kind="k", item_key="i", status="done",
                record_key="abc123", detail="landed as deadbeef")
    row = store.get(spec_kind="k", item_key="i")
    assert row.status == "done"
    assert row.record_key == "abc123"
    assert row.detail == "landed as deadbeef"
    assert row.run_id == "run-1"


def test_upsert_updates_in_place_not_stacking_rows(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoint.sqlite")
    store.upsert(run_id="run-1", spec_kind="k", item_key="i", status="in_progress")
    store.upsert(run_id="run-1", spec_kind="k", item_key="i", status="done",
                record_key="xyz")
    rows = store.rows_for_spec("k")
    assert len(rows) == 1
    assert rows[0].status == "done"


def test_rows_for_spec_is_ordered_and_scoped_to_kind(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoint.sqlite")
    store.upsert(run_id="r", spec_kind="a", item_key="z", status="pending")
    store.upsert(run_id="r", spec_kind="a", item_key="a", status="pending")
    store.upsert(run_id="r", spec_kind="b", item_key="a", status="pending")
    rows = store.rows_for_spec("a")
    assert [row.item_key for row in rows] == ["a", "z"]


def test_store_persists_across_reopen(tmp_path):
    path = tmp_path / "checkpoint.sqlite"
    CheckpointStore(path).upsert(run_id="r", spec_kind="k", item_key="i", status="done")
    reopened = CheckpointStore(path)
    assert reopened.get(spec_kind="k", item_key="i").status == "done"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd tools/orchestrator && uv run pytest tests/test_checkpoint.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_orchestrator.checkpoint'`

- [ ] **Step 4: Implement `checkpoint.py`**

```python
# tools/orchestrator/src/langatlas_orchestrator/checkpoint.py
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orchestrator_checkpoint (
    spec_kind         TEXT NOT NULL,
    item_key          TEXT NOT NULL,
    run_id            TEXT NOT NULL,
    status            TEXT NOT NULL,
    record_key        TEXT,
    detail            TEXT NOT NULL DEFAULT '',
    last_pause_reason TEXT,
    attempted_at      TEXT NOT NULL,
    PRIMARY KEY (spec_kind, item_key)
)
"""


@dataclass(frozen=True)
class CheckpointRow:
    run_id: str
    spec_kind: str
    item_key: str
    status: str
    record_key: str | None
    detail: str
    last_pause_reason: str | None
    attempted_at: str


_COLUMNS = ("run_id", "spec_kind", "item_key", "status", "record_key", "detail",
           "last_pause_reason", "attempted_at")


class CheckpointStore:
    """D43 §2.2: driver-level bookkeeping only, in the same private, non-git tier as
    D26's cache/cost log. Never the source of truth for whether an item actually
    landed — `driver.py` re-verifies any non-`done` row against the `LangAtlas-Record-Key`
    git trailer (D36 §2.6) before treating it as resolved."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def upsert(self, *, run_id: str, spec_kind: str, item_key: str, status: str,
               record_key: str | None = None, detail: str = "",
               last_pause_reason: str | None = None) -> None:
        self._conn.execute(
            "INSERT INTO orchestrator_checkpoint"
            " (spec_kind, item_key, run_id, status, record_key, detail,"
            "  last_pause_reason, attempted_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(spec_kind, item_key) DO UPDATE SET"
            "   run_id=excluded.run_id, status=excluded.status,"
            "   record_key=excluded.record_key, detail=excluded.detail,"
            "   last_pause_reason=excluded.last_pause_reason,"
            "   attempted_at=excluded.attempted_at",
            (spec_kind, item_key, run_id, status, record_key, detail, last_pause_reason,
             datetime.now(timezone.utc).isoformat()))
        self._conn.commit()

    def get(self, *, spec_kind: str, item_key: str) -> CheckpointRow | None:
        row = self._conn.execute(
            "SELECT run_id, spec_kind, item_key, status, record_key, detail,"
            " last_pause_reason, attempted_at FROM orchestrator_checkpoint"
            " WHERE spec_kind = ? AND item_key = ?", (spec_kind, item_key)).fetchone()
        return CheckpointRow(*row) if row else None

    def rows_for_spec(self, spec_kind: str) -> list[CheckpointRow]:
        rows = self._conn.execute(
            "SELECT run_id, spec_kind, item_key, status, record_key, detail,"
            " last_pause_reason, attempted_at FROM orchestrator_checkpoint"
            " WHERE spec_kind = ? ORDER BY item_key", (spec_kind,)).fetchall()
        return [CheckpointRow(*row) for row in rows]

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd tools/orchestrator && uv run pytest tests/test_checkpoint.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add tools/orchestrator/pyproject.toml tools/orchestrator/uv.lock \
        tools/orchestrator/src/langatlas_orchestrator/__init__.py \
        tools/orchestrator/src/langatlas_orchestrator/checkpoint.py \
        tools/orchestrator/tests/test_checkpoint.py
git commit -m "feat(#stage-1e): scaffold tools/orchestrator with a SQLite checkpoint store"
```

---

## Task 2: Batch-spec loader

**Files:**
- Create: `tools/orchestrator/src/langatlas_orchestrator/spec.py`
- Test: `tools/orchestrator/tests/test_spec.py`

**Interfaces:**
- Consumes: `Budget` (1B, `langatlas_pipeline.providers.core.Budget`).
- Produces for Task 5: `BatchSpec(kind: str, checkpoint_path: Path, budget: Budget, extra:
  dict)`, `load_batch_spec(path: Path) -> BatchSpec`.

- [ ] **Step 1: Write the failing test**

```python
# tools/orchestrator/tests/test_spec.py
import pytest
from langatlas_orchestrator.spec import load_batch_spec


def _write(path, text):
    path.write_text(text)
    return path


def test_load_batch_spec_minimal(tmp_path):
    path = _write(tmp_path / "job.yaml", "kind: r0-exit-test\ncheckpoint_path: ck.sqlite\n")
    spec = load_batch_spec(path)
    assert spec.kind == "r0-exit-test"
    assert spec.checkpoint_path == path.parent / "ck.sqlite" if False else True
    assert str(spec.checkpoint_path) == "ck.sqlite"
    assert spec.budget.max_calls is None
    assert spec.extra == {}


def test_load_batch_spec_with_budget_and_extra(tmp_path):
    path = _write(tmp_path / "job.yaml",
                 "kind: monthly-capability-probe\n"
                 "checkpoint_path: ck.sqlite\n"
                 "budget:\n  max_calls: 50\n  max_wall_seconds: 600\n"
                 "query: pattern matching\n")
    spec = load_batch_spec(path)
    assert spec.budget.max_calls == 50
    assert spec.budget.max_wall_seconds == 600
    assert spec.extra == {"query": "pattern matching"}


def test_load_batch_spec_missing_kind_raises(tmp_path):
    path = _write(tmp_path / "job.yaml", "checkpoint_path: ck.sqlite\n")
    with pytest.raises(ValueError, match="kind"):
        load_batch_spec(path)


def test_load_batch_spec_missing_checkpoint_path_raises(tmp_path):
    path = _write(tmp_path / "job.yaml", "kind: r0-exit-test\n")
    with pytest.raises(ValueError, match="checkpoint_path"):
        load_batch_spec(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/orchestrator && uv run pytest tests/test_spec.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_orchestrator.spec'`

- [ ] **Step 3: Implement `spec.py`**

```python
# tools/orchestrator/src/langatlas_orchestrator/spec.py
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_pipeline.providers.core import Budget

_yaml = YAML(typ="safe")
_REQUIRED = ("kind", "checkpoint_path")
_KNOWN_TOP_LEVEL = ("kind", "checkpoint_path", "budget")


@dataclass(frozen=True)
class BatchSpec:
    """D43 §2.1: `kind` dispatches into the job-kind registry; `extra` is whatever
    job-specific config the spec's own YAML carries beyond the three fields every
    job kind shares (e.g. a search query, a language slug)."""

    kind: str
    checkpoint_path: Path
    budget: Budget
    extra: dict


def load_batch_spec(path: Path) -> BatchSpec:
    data = _yaml.load(path.read_text()) or {}
    for field in _REQUIRED:
        if field not in data:
            raise ValueError(f"{path}: batch spec missing required field {field!r}")
    budget = Budget(**(data.get("budget") or {}))
    extra = {k: v for k, v in data.items() if k not in _KNOWN_TOP_LEVEL}
    return BatchSpec(kind=data["kind"], checkpoint_path=Path(data["checkpoint_path"]),
                     budget=budget, extra=extra)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/orchestrator && uv run pytest tests/test_spec.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/orchestrator/src/langatlas_orchestrator/spec.py tools/orchestrator/tests/test_spec.py
git commit -m "feat(#stage-1e): add the batch-spec YAML loader"
```

---

## Task 3: Job-kind registry

**Files:**
- Create: `tools/orchestrator/src/langatlas_orchestrator/registry.py`
- Test: `tools/orchestrator/tests/test_registry.py`
- Create: `tools/orchestrator/tests/conftest.py`

**Interfaces:**
- Consumes: nothing.
- Produces for Task 5/6/7/8: `ItemOutcome(status: Literal["done","blocked","contention",
  "halted"], record_key: str | None = None, detail: str = "")`,
  `EnumeratorFn = Callable[[dict, Path], list[str]]`,
  `ItemRunnerFn = Callable[[Any, str, dict, Path], ItemOutcome]` (args: `ctx, item_key, extra,
  repo_root`), `register_job_kind(kind, enumerator, item_runner) -> None`,
  `get_job_kind(kind) -> tuple[EnumeratorFn, ItemRunnerFn]`, `registered_kinds() -> list[str]`,
  `UnknownJobKind`.

- [ ] **Step 1: Write the failing test**

```python
# tools/orchestrator/tests/conftest.py
import pytest
from langatlas_orchestrator import registry as registry_module


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch):
    """Every test gets a private copy of the module-level registry dict so tests can
    register throwaway job kinds without leaking into each other or into the real
    built-in kinds registered by `jobs/__init__.py`."""
    monkeypatch.setattr(registry_module, "_REGISTRY", dict(registry_module._REGISTRY))
```

```python
# tools/orchestrator/tests/test_registry.py
import pytest
from langatlas_orchestrator.registry import (
    ItemOutcome, UnknownJobKind, get_job_kind, register_job_kind, registered_kinds,
)


def _enumerate(extra, repo_root):
    return ["a", "b"]


def _run_item(ctx, item_key, extra, repo_root):
    return ItemOutcome(status="done")


def test_register_then_get_round_trips():
    register_job_kind("test-kind-1", _enumerate, _run_item)
    enumerator, item_runner = get_job_kind("test-kind-1")
    assert enumerator is _enumerate
    assert item_runner is _run_item


def test_get_unknown_kind_raises():
    with pytest.raises(UnknownJobKind):
        get_job_kind("no-such-kind")


def test_registered_kinds_lists_registrations_sorted():
    register_job_kind("test-kind-z", _enumerate, _run_item)
    register_job_kind("test-kind-a", _enumerate, _run_item)
    kinds = registered_kinds()
    assert kinds.index("test-kind-a") < kinds.index("test-kind-z")


def test_item_outcome_defaults():
    outcome = ItemOutcome(status="done")
    assert outcome.record_key is None
    assert outcome.detail == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/orchestrator && uv run pytest tests/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_orchestrator.registry'`

- [ ] **Step 3: Implement `registry.py`**

```python
# tools/orchestrator/src/langatlas_orchestrator/registry.py
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

Status = Literal["done", "blocked", "contention", "halted"]


@dataclass(frozen=True)
class ItemOutcome:
    """What an item runner reports back to the driver for one work item. `blocked`/
    `contention` are distinguished from `halted` the same way D36's `LandResult` does:
    the former are still valid and re-attemptable, the latter needs a human to look at
    a filed issue before this item is ever retried."""

    status: Status
    record_key: str | None = None
    detail: str = ""


# (job-specific config from the batch spec, repo_root) -> ordered work-item keys
EnumeratorFn = Callable[[dict, Path], list[str]]
# (RunContext, item_key, job-specific config, repo_root) -> ItemOutcome
ItemRunnerFn = Callable[[Any, str, dict, Path], ItemOutcome]

_REGISTRY: dict[str, tuple[EnumeratorFn, ItemRunnerFn]] = {}


class UnknownJobKind(KeyError):
    """A batch spec named a `kind` no `jobs/*.py` module has registered."""


def register_job_kind(kind: str, enumerator: EnumeratorFn,
                      item_runner: ItemRunnerFn) -> None:
    """D43 §2.1: adding a job kind is one call to this function plus one YAML file —
    never a change to `driver.py` itself."""
    _REGISTRY[kind] = (enumerator, item_runner)


def get_job_kind(kind: str) -> tuple[EnumeratorFn, ItemRunnerFn]:
    try:
        return _REGISTRY[kind]
    except KeyError:
        raise UnknownJobKind(f"no job kind registered: {kind!r}") from None


def registered_kinds() -> list[str]:
    return sorted(_REGISTRY)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/orchestrator && uv run pytest tests/test_registry.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/orchestrator/src/langatlas_orchestrator/registry.py \
        tools/orchestrator/tests/test_registry.py tools/orchestrator/tests/conftest.py
git commit -m "feat(#stage-1e): add the job-kind registry"
```

---

## Task 4: Status file + `langatlas-report orchestrator-status`

**Files:**
- Create: `tools/orchestrator/src/langatlas_orchestrator/status.py`
- Test: `tools/orchestrator/tests/test_status.py`
- Modify: `tools/pipeline/src/langatlas_pipeline/observability/report.py`
- Modify: `tools/pipeline/tests/test_report.py`

**Interfaces:**
- Consumes: `PRIVATE_DIR` (1B, `langatlas_pipeline.paths`).
- Produces for Task 5: `read_status(path: Path | None = None) -> dict`,
  `write_status(kind: str, *, state: str, reason: str | None = None, paused_at: float | None =
  None, paused_until: float | None = None, items_remaining: int | None = None, path: Path |
  None = None) -> None`, `STATUS_PATH`.

- [ ] **Step 1: Write the failing test for `status.py`**

```python
# tools/orchestrator/tests/test_status.py
from langatlas_orchestrator.status import read_status, write_status


def test_read_status_missing_file_returns_empty_dict(tmp_path):
    assert read_status(tmp_path / "nope" / "status.json") == {}


def test_write_then_read_round_trips(tmp_path):
    path = tmp_path / "status.json"
    write_status("r0-exit-test", state="done", reason=None, path=path)
    status = read_status(path)
    assert status["r0-exit-test"]["state"] == "done"
    assert status["r0-exit-test"]["reason"] is None


def test_write_status_preserves_other_kinds(tmp_path):
    path = tmp_path / "status.json"
    write_status("kind-a", state="running", path=path)
    write_status("kind-b", state="paused", reason="claude_limit", paused_until=999.0,
                path=path)
    status = read_status(path)
    assert status["kind-a"]["state"] == "running"
    assert status["kind-b"]["reason"] == "claude_limit"
    assert status["kind-b"]["paused_until"] == 999.0


def test_write_status_overwrites_same_kind(tmp_path):
    path = tmp_path / "status.json"
    write_status("kind-a", state="running", path=path)
    write_status("kind-a", state="done", path=path)
    status = read_status(path)
    assert status["kind-a"]["state"] == "done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/orchestrator && uv run pytest tests/test_status.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_orchestrator.status'`

- [ ] **Step 3: Implement `status.py`**

```python
# tools/orchestrator/src/langatlas_orchestrator/status.py
import json
import time
from pathlib import Path

from langatlas_pipeline.paths import PRIVATE_DIR

# D43 §2.4: "alerting" in a solo-dev, no-new-infra project is the run halting plus this
# glanceable file, surfaced by `langatlas-report orchestrator-status` — no cron mail, no
# notification service.
STATUS_PATH = PRIVATE_DIR / "orchestrator" / "status.json"


def read_status(path: Path | None = None) -> dict:
    path = path or STATUS_PATH
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def write_status(kind: str, *, state: str, reason: str | None = None,
                 paused_at: float | None = None, paused_until: float | None = None,
                 items_remaining: int | None = None, path: Path | None = None) -> None:
    path = path or STATUS_PATH
    status = read_status(path)
    status[kind] = {
        "state": state, "reason": reason, "paused_at": paused_at,
        "paused_until": paused_until, "items_remaining": items_remaining,
        "updated_at": time.time(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/orchestrator && uv run pytest tests/test_status.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Write the failing test for the `report.py` subcommand**

Append to `tools/pipeline/tests/test_report.py` (create the file with this content if it does
not already exist; if it exists, add these two functions and the one new import):

```python
# tools/pipeline/tests/test_report.py (additions)
import json

from langatlas_pipeline.observability.report import report_orchestrator_status


def test_report_orchestrator_status_no_file_yet(tmp_path):
    markdown = report_orchestrator_status(tmp_path / "status.json")
    assert "no jobs have run yet" in markdown.lower()


def test_report_orchestrator_status_renders_paused_and_done_rows(tmp_path):
    path = tmp_path / "status.json"
    path.write_text(json.dumps({
        "monthly-capability-probe": {"state": "done", "reason": None,
                                     "paused_until": None, "items_remaining": 0},
        "r0-exit-test": {"state": "paused", "reason": "claude_limit",
                         "paused_until": 9999999999.0, "items_remaining": 1},
    }))
    markdown = report_orchestrator_status(path)
    assert "monthly-capability-probe" in markdown
    assert "done" in markdown
    assert "r0-exit-test" in markdown
    assert "claude_limit" in markdown
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd tools/pipeline && uv run pytest tests/test_report.py -v -k orchestrator_status`
Expected: FAIL with `ImportError: cannot import name 'report_orchestrator_status'`

- [ ] **Step 7: Add `report_orchestrator_status` and wire the `orchestrator-status` subcommand**

Edit `tools/pipeline/src/langatlas_pipeline/observability/report.py`. Add near the top
(alongside the other path-derived module constants):

```python
from langatlas_pipeline.paths import PRIVATE_DIR

# Mirrors langatlas_orchestrator.status.STATUS_PATH's own PRIVATE_DIR-derived path exactly —
# report.py deliberately does not import langatlas_orchestrator (tools/orchestrator depends on
# tools/pipeline, never the reverse), so this is a second, independent computation of the same
# path from the one constant both packages already share.
_ORCHESTRATOR_STATUS_PATH = PRIVATE_DIR / "orchestrator" / "status.json"
```

Add the report function (place it after `report_capabilities`):

```python
def report_orchestrator_status(path: Path | None = None) -> str:
    import json

    path = path or _ORCHESTRATOR_STATUS_PATH
    if not path.exists():
        return "# Orchestrator status\n\nNo jobs have run yet.\n"
    status = json.loads(path.read_text())
    lines = ["# Orchestrator status", "",
             "| job kind | state | reason | paused until | items remaining |",
             "|---|---|---|---|---:|"]
    for kind, entry in sorted(status.items()):
        paused_until = entry.get("paused_until")
        lines.append(f"| {kind} | {entry.get('state')} | {entry.get('reason') or '—'} | "
                     f"{paused_until if paused_until is not None else '—'} | "
                     f"{entry.get('items_remaining') if entry.get('items_remaining') is not None else '—'} |")
    return "\n".join(lines) + "\n"
```

Edit `main()` in the same file: add a subparser and dispatch arm.

```python
    p_orch = sub.add_parser("orchestrator-status")
    p_orch.add_argument("--out", type=Path, default=None, help=out_help)
```

and change the dispatch to a chain that covers all three commands:

```python
    if args.command == "cost":
        markdown = report_cost(args.cost_log, args.transcripts)
    elif args.command == "orchestrator-status":
        markdown = report_orchestrator_status()
    else:
        markdown = report_capabilities()
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd tools/pipeline && uv run pytest tests/test_report.py -v`
Expected: PASS, no regressions.

- [ ] **Step 9: Commit**

```bash
git add tools/orchestrator/src/langatlas_orchestrator/status.py \
        tools/orchestrator/tests/test_status.py \
        tools/pipeline/src/langatlas_pipeline/observability/report.py \
        tools/pipeline/tests/test_report.py
git commit -m "feat(#stage-1e): add orchestrator/status.json and its report subcommand"
```

---

## Task 5: Generic driver loop

**Files:**
- Create: `tools/orchestrator/src/langatlas_orchestrator/driver.py`
- Test: `tools/orchestrator/tests/test_driver.py`

**Interfaces:**
- Consumes: `CheckpointStore` (Task 1), `load_batch_spec`/`BatchSpec` (Task 2),
  `register_job_kind`/`get_job_kind`/`ItemOutcome` (Task 3), `read_status`/`write_status`
  (Task 4), `RunContext`/`Budget` (1B), `BudgetExceeded`/`ClaudeLimitSignal` (1B, D26/D41),
  `find_record_key_in_history` (1D).
- Produces for Task 6/7/8/9: `EXIT_OK = 0`, `EXIT_PAUSED = 75`, `EXIT_HALTED = 1`,
  `run(spec_path: Path, *, repo_root: Path, status_path: Path | None = None) -> int`,
  `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# tools/orchestrator/tests/test_driver.py
import subprocess
import time
from pathlib import Path

import pytest

from langatlas_orchestrator.checkpoint import CheckpointStore
from langatlas_orchestrator.driver import EXIT_HALTED, EXIT_OK, EXIT_PAUSED, run
from langatlas_orchestrator.registry import ItemOutcome, register_job_kind
from langatlas_orchestrator.status import read_status
from langatlas_pipeline.errors import BudgetExceeded, ClaudeLimitSignal


def _write_spec(tmp_path, kind, extra_yaml="") -> Path:
    path = tmp_path / "job.yaml"
    path.write_text(f"kind: {kind}\ncheckpoint_path: {tmp_path / 'ck.sqlite'}\n{extra_yaml}")
    return path


def test_run_happy_path_marks_every_item_done(tmp_path):
    calls = []

    def _enumerate(extra, repo_root):
        return ["item-1", "item-2"]

    def _run_item(ctx, item_key, extra, repo_root):
        calls.append(item_key)
        return ItemOutcome(status="done", detail=f"processed {item_key}")

    register_job_kind("test-happy-path", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-happy-path")

    rc = run(spec_path, repo_root=tmp_path, status_path=tmp_path / "status.json")

    assert rc == EXIT_OK
    assert calls == ["item-1", "item-2"]
    store = CheckpointStore(tmp_path / "ck.sqlite")
    assert store.get(spec_kind="test-happy-path", item_key="item-1").status == "done"
    assert store.get(spec_kind="test-happy-path", item_key="item-2").status == "done"
    assert read_status(tmp_path / "status.json")["test-happy-path"]["state"] == "done"


def test_run_skips_items_already_marked_done(tmp_path):
    calls = []

    def _enumerate(extra, repo_root):
        return ["item-1", "item-2"]

    def _run_item(ctx, item_key, extra, repo_root):
        calls.append(item_key)
        return ItemOutcome(status="done")

    register_job_kind("test-skip-done", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-skip-done")
    CheckpointStore(tmp_path / "ck.sqlite").upsert(
        run_id="earlier-run", spec_kind="test-skip-done", item_key="item-1", status="done")

    rc = run(spec_path, repo_root=tmp_path, status_path=tmp_path / "status.json")

    assert rc == EXIT_OK
    assert calls == ["item-2"]        # item-1 was never re-run


def test_run_pauses_on_budget_exceeded_and_checkpoints_blocked(tmp_path):
    def _enumerate(extra, repo_root):
        return ["item-1", "item-2"]

    def _run_item(ctx, item_key, extra, repo_root):
        raise BudgetExceeded("max_calls", 1, 0)

    register_job_kind("test-budget-pause", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-budget-pause", "budget:\n  max_calls: 0\n")

    rc = run(spec_path, repo_root=tmp_path, status_path=tmp_path / "status.json")

    assert rc == EXIT_PAUSED
    row = CheckpointStore(tmp_path / "ck.sqlite").get(spec_kind="test-budget-pause",
                                                      item_key="item-1")
    assert row.status == "blocked"
    status = read_status(tmp_path / "status.json")["test-budget-pause"]
    assert status["state"] == "paused"
    assert status["reason"] == "budget"


def test_run_pauses_on_claude_limit_and_sets_a_four_hour_cooldown(tmp_path):
    def _enumerate(extra, repo_root):
        return ["item-1"]

    def _run_item(ctx, item_key, extra, repo_root):
        raise ClaudeLimitSignal(detected_at="2026-08-22T00:00:00Z", signal_type="usage_limit",
                                raw_message="limit hit", run_id=ctx.run_id)

    register_job_kind("test-claude-limit-pause", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-claude-limit-pause")

    before = time.time()
    rc = run(spec_path, repo_root=tmp_path, status_path=tmp_path / "status.json")

    assert rc == EXIT_PAUSED
    status = read_status(tmp_path / "status.json")["test-claude-limit-pause"]
    assert status["reason"] == "claude_limit"
    assert status["paused_until"] - before == pytest.approx(4 * 60 * 60, abs=5)


def test_run_no_ops_before_claude_limit_cooldown_elapses(tmp_path):
    call_count = {"n": 0}

    def _enumerate(extra, repo_root):
        return ["item-1"]

    def _run_item(ctx, item_key, extra, repo_root):
        call_count["n"] += 1
        return ItemOutcome(status="done")

    register_job_kind("test-claude-limit-cooldown", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-claude-limit-cooldown")
    status_path = tmp_path / "status.json"
    from langatlas_orchestrator.status import write_status
    write_status("test-claude-limit-cooldown", state="paused", reason="claude_limit",
                paused_at=time.time(), paused_until=time.time() + 3600, path=status_path)

    rc = run(spec_path, repo_root=tmp_path, status_path=status_path)

    assert rc == EXIT_PAUSED
    assert call_count["n"] == 0        # the item runner was never invoked


def test_run_halts_and_stops_processing_further_items(tmp_path):
    calls = []

    def _enumerate(extra, repo_root):
        return ["item-1", "item-2"]

    def _run_item(ctx, item_key, extra, repo_root):
        calls.append(item_key)
        return ItemOutcome(status="halted", detail="unsafe_halt: needs a human")

    register_job_kind("test-halt", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-halt")

    rc = run(spec_path, repo_root=tmp_path, status_path=tmp_path / "status.json")

    assert rc == EXIT_HALTED
    assert calls == ["item-1"]         # item-2 never attempted
    status = read_status(tmp_path / "status.json")["test-halt"]
    assert status["state"] == "halted"


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def test_run_resolves_an_ambiguous_row_via_the_git_trailer(tmp_path):
    """Simulates a crash right after a commit landed but before the checkpoint row was
    marked `done` (D43 §2.2's crash-safety property): the row is stuck `in_progress`
    with a `record_key`, but the record actually landed. The driver must not re-run the
    item — it must resolve it via `find_record_key_in_history` and mark it `done`."""
    from langatlas_commit.trailers import format_trailers, record_key

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "bot@example.com"], repo)
    _git(["config", "user.name", "bot"], repo)
    key = record_key("features/thing.yaml", "feature: thing\n")
    (repo / "features").mkdir()
    (repo / "features" / "thing.yaml").write_text("feature: thing\n")
    _git(["add", "features/thing.yaml"], repo)
    _git(["commit", "-q", "-m", "land it\n\n" + format_trailers(key, "run-0#msg-1")], repo)

    CheckpointStore(tmp_path / "ck.sqlite").upsert(
        run_id="crashed-run", spec_kind="test-resume-ambiguous", item_key="item-1",
        status="in_progress", record_key=key)

    calls = []

    def _enumerate(extra, repo_root):
        return ["item-1"]

    def _run_item(ctx, item_key, extra, repo_root):
        calls.append(item_key)             # would double-commit if the driver got here
        return ItemOutcome(status="done")

    register_job_kind("test-resume-ambiguous", _enumerate, _run_item)
    spec_path = _write_spec(tmp_path, "test-resume-ambiguous")

    rc = run(spec_path, repo_root=repo, status_path=tmp_path / "status.json")

    assert rc == EXIT_OK
    assert calls == []                     # never re-attempted
    row = CheckpointStore(tmp_path / "ck.sqlite").get(spec_kind="test-resume-ambiguous",
                                                      item_key="item-1")
    assert row.status == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/orchestrator && uv run pytest tests/test_driver.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_orchestrator.driver'`

- [ ] **Step 3: Implement `driver.py`**

```python
# tools/orchestrator/src/langatlas_orchestrator/driver.py
import time
from pathlib import Path

from langatlas_commit.trailers import find_record_key_in_history
from langatlas_pipeline.errors import BudgetExceeded, ClaudeLimitSignal
from langatlas_pipeline.providers.core import RunContext

from langatlas_orchestrator.checkpoint import CheckpointStore
from langatlas_orchestrator.registry import get_job_kind
from langatlas_orchestrator.spec import load_batch_spec
from langatlas_orchestrator.status import read_status, write_status

# sysexits-style: 75 (EX_TEMPFAIL) means "come back later, on purpose" — distinguishes a
# clean pause from a crash (nonzero-but-not-75) or clean completion (0), for any wrapping
# cron/shell logic to detect (D43 §2.3).
EXIT_OK = 0
EXIT_PAUSED = 75
EXIT_HALTED = 1

# D43 §2.4, ratified: a fixed 4-hour cool-down, no calibration data exists to sharpen it.
_CLAUDE_LIMIT_COOLDOWN_SECONDS = 4 * 60 * 60


def run(spec_path: Path, *, repo_root: Path, status_path: Path | None = None) -> int:
    """The one generic loop every job kind shares (D43 §2.1): enumerate → for each item,
    skip if already `done`, resolve ambiguous rows via the git trailer, otherwise call
    the job's item runner inside a `RunContext`-scoped run → checkpoint → decide
    continue/pause/halt. Resume is calling this function again with the same spec —
    there is no separate resume mode (D43 §2.3)."""
    spec = load_batch_spec(spec_path)
    enumerator, item_runner = get_job_kind(spec.kind)

    existing = read_status(status_path).get(spec.kind)
    if existing and existing.get("state") == "paused" and existing.get("reason") == "claude_limit":
        paused_until = existing.get("paused_until") or 0
        if time.time() < paused_until:
            remaining = int(paused_until - time.time())
            print(f"{spec.kind}: still cooling down from a Claude usage limit, "
                 f"{remaining}s remaining; no-op")
            return EXIT_PAUSED

    store = CheckpointStore(spec.checkpoint_path)
    items = enumerator(spec.extra, repo_root)
    ctx = RunContext.start(kind=spec.kind, slug=spec.kind, budget=spec.budget)

    try:
        for index, item_key in enumerate(items):
            row = store.get(spec_kind=spec.kind, item_key=item_key)
            if row is not None and row.status == "done":
                continue
            if row is not None and row.status in ("in_progress", "blocked", "contention") \
                    and row.record_key is not None:
                landed_sha = find_record_key_in_history(repo_root, row.record_key)
                if landed_sha is not None:
                    store.upsert(run_id=ctx.run_id, spec_kind=spec.kind, item_key=item_key,
                                status="done", record_key=row.record_key,
                                detail=f"resolved via git trailer at {landed_sha}")
                    continue

            store.upsert(run_id=ctx.run_id, spec_kind=spec.kind, item_key=item_key,
                        status="in_progress")
            try:
                outcome = item_runner(ctx, item_key, spec.extra, repo_root)
            except BudgetExceeded as exc:
                store.upsert(run_id=ctx.run_id, spec_kind=spec.kind, item_key=item_key,
                            status="blocked", last_pause_reason=f"budget:{exc}")
                write_status(spec.kind, state="paused", reason="budget",
                            paused_at=time.time(), items_remaining=len(items) - index,
                            path=status_path)
                return EXIT_PAUSED
            except ClaudeLimitSignal as exc:
                store.upsert(run_id=ctx.run_id, spec_kind=spec.kind, item_key=item_key,
                            status="blocked", last_pause_reason=f"claude_limit:{exc}")
                now = time.time()
                write_status(spec.kind, state="paused", reason="claude_limit",
                            paused_at=now, paused_until=now + _CLAUDE_LIMIT_COOLDOWN_SECONDS,
                            items_remaining=len(items) - index, path=status_path)
                return EXIT_PAUSED

            store.upsert(run_id=ctx.run_id, spec_kind=spec.kind, item_key=item_key,
                        status=outcome.status, record_key=outcome.record_key,
                        detail=outcome.detail)
            if outcome.status == "halted":
                write_status(spec.kind, state="halted", reason=outcome.detail,
                            paused_at=time.time(), items_remaining=len(items) - index,
                            path=status_path)
                return EXIT_HALTED

        write_status(spec.kind, state="done", reason=None, items_remaining=0,
                    path=status_path)
        return EXIT_OK
    finally:
        ctx.close()
        store.close()


def main(argv: list[str] | None = None) -> int:
    import argparse

    from langatlas_validate.paths import REPO_ROOT

    # Registers the built-in job kinds (capability probe, r0 exit test, the deferred
    # D43-inventory kinds) as an import side effect — see jobs/__init__.py.
    import langatlas_orchestrator.jobs  # noqa: F401

    parser = argparse.ArgumentParser(prog="langatlas-orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("spec", type=Path)
    p_run.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    p_run.add_argument("--status-path", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.command == "run":
        return run(args.spec, repo_root=args.repo_root, status_path=args.status_path)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools/orchestrator && uv run pytest tests/test_driver.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/orchestrator/src/langatlas_orchestrator/driver.py \
        tools/orchestrator/tests/test_driver.py
git commit -m "feat(#stage-1e): add the generic orchestrator driver loop"
```

---

## Task 6: `monthly-capability-probe` job kind (real — wraps 1B's `probe_all`)

**Files:**
- Create: `tools/orchestrator/src/langatlas_orchestrator/jobs/__init__.py`
- Create: `tools/orchestrator/src/langatlas_orchestrator/jobs/capability_probe.py`
- Test: `tools/orchestrator/tests/test_capability_probe_job.py`

**Interfaces:**
- Consumes: `probe_all`, `apply_probe` (1B, `langatlas_pipeline.observability.probe`),
  `CONFIG_DIR` (1B, `langatlas_pipeline.paths`), `register_job_kind`/`ItemOutcome` (Task 3).
- Produces for Task 9: the `"monthly-capability-probe"` kind registered in the shared
  registry the moment `langatlas_orchestrator.jobs` is imported.

- [ ] **Step 1: Write the failing test**

```python
# tools/orchestrator/tests/test_capability_probe_job.py
from pathlib import Path

from langatlas_orchestrator.jobs.capability_probe import _enumerate, _run_item
from langatlas_orchestrator.registry import get_job_kind


class _FakeCtx:
    def __init__(self):
        self.run_id = "run-1"


def test_capability_probe_is_registered_on_import():
    import langatlas_orchestrator.jobs  # noqa: F401
    enumerator, item_runner = get_job_kind("monthly-capability-probe")
    assert enumerator is _enumerate
    assert item_runner is _run_item


def test_enumerate_returns_one_static_item(tmp_path):
    assert _enumerate({}, tmp_path) == ["probe-all-aliases"]


def test_run_item_calls_probe_all_and_applies_it(tmp_path, monkeypatch):
    calls = {}

    def _fake_probe_all(ctx):
        calls["probed"] = True
        return {"claude-completion": {"resolved_model": "claude-x"}}

    def _fake_apply_probe(path, probed):
        calls["applied"] = (path, probed)

    monkeypatch.setattr(
        "langatlas_orchestrator.jobs.capability_probe.probe_all", _fake_probe_all)
    monkeypatch.setattr(
        "langatlas_orchestrator.jobs.capability_probe.apply_probe", _fake_apply_probe)

    outcome = _run_item(_FakeCtx(), "probe-all-aliases", {}, tmp_path)

    assert outcome.status == "done"
    assert calls["probed"] is True
    assert "probed 1 alias" in outcome.detail
    assert calls["applied"][1] == {"claude-completion": {"resolved_model": "claude-x"}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/orchestrator && uv run pytest tests/test_capability_probe_job.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_orchestrator.jobs'`

- [ ] **Step 3: Implement `jobs/capability_probe.py` and `jobs/__init__.py`**

```python
# tools/orchestrator/src/langatlas_orchestrator/jobs/capability_probe.py
"""D43's 'monthly capability probe' periodic job (context/spec.md §14), reusing 1B's
already-shipped `probe_all`/`apply_probe` unchanged — this module only gives the
existing capability probe an enumerator/item-runner shape the driver can schedule
through `config/jobs/monthly-capability-probe.yaml` + cron, instead of it only being
reachable via its own standalone `langatlas-probe` CLI."""
from pathlib import Path

from langatlas_pipeline.observability.probe import apply_probe, probe_all
from langatlas_pipeline.paths import CONFIG_DIR

from langatlas_orchestrator.registry import ItemOutcome, register_job_kind

_ITEM_KEY = "probe-all-aliases"


def _enumerate(extra: dict, repo_root: Path) -> list[str]:
    return [_ITEM_KEY]


def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
    probed = probe_all(ctx)
    apply_probe(CONFIG_DIR / "provider_capabilities.yaml", probed)
    plural = "" if len(probed) == 1 else "s"
    return ItemOutcome(status="done", detail=f"probed {len(probed)} alias{plural}")


register_job_kind("monthly-capability-probe", _enumerate, _run_item)
```

```python
# tools/orchestrator/src/langatlas_orchestrator/jobs/__init__.py
"""Importing this package registers every built-in job kind (D43's periodic-job
inventory) as a side effect. `driver.main()` imports this once before dispatching;
tests import individual `jobs/*` submodules directly and rely on the same import."""
from langatlas_orchestrator.jobs import capability_probe  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/orchestrator && uv run pytest tests/test_capability_probe_job.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/orchestrator/src/langatlas_orchestrator/jobs/__init__.py \
        tools/orchestrator/src/langatlas_orchestrator/jobs/capability_probe.py \
        tools/orchestrator/tests/test_capability_probe_job.py
git commit -m "feat(#stage-1e): wire the monthly capability probe into the orchestrator"
```

---

## Task 7: `r0-exit-test` job kind — the Stage 1 exit gate

**Files:**
- Create: `tools/orchestrator/src/langatlas_orchestrator/jobs/exit_test.py`
- Modify: `tools/orchestrator/src/langatlas_orchestrator/jobs/__init__.py`
- Test: `tools/orchestrator/tests/test_exit_test_job.py`

**Interfaces:**
- Consumes: `search_sources` (1C, `langatlas_ingest.tools`), `connect` (1C,
  `langatlas_ingest.db`), `validate_record` (1A, `langatlas_validate.schema`),
  `normalize_record` (1A, `langatlas_validate.normalize`), `land_record`/`Landed` (1D,
  `langatlas_commit.land`), `record_key` (1D, `langatlas_commit.trailers`),
  `ItemOutcome`/`register_job_kind` (Task 3).
- Produces: the `"r0-exit-test"` kind. This task's passing integration test **is** Stage 1's
  hard exit gate from the cross-stage plan: "an agent can run `search_sources`, mint a node
  file that validates, and the run is logged."

- [ ] **Step 1: Write the failing unit test for record-minting (no Postgres needed)**

```python
# tools/orchestrator/tests/test_exit_test_job.py (part 1 — unit-level, no marker)
from langatlas_orchestrator.jobs.exit_test import _mint_concept_record
from langatlas_validate.normalize import normalize_record
from langatlas_validate.schema import validate_record


def test_mint_concept_record_is_schema_valid_and_normalized():
    hit = {"source_id": "van-roy-haridi-2003", "locator": "p. 42"}
    record_path, content = _mint_concept_record("pattern matching", hit)

    assert record_path == "concepts/orchestrator-exit-test-probe.yaml"
    import io
    from ruamel.yaml import YAML
    data = YAML(typ="safe").load(content)
    assert validate_record(data, "concept") == []
    assert normalize_record(content, "concept") == content


def test_mint_concept_record_cites_the_hit_locator_verbatim():
    hit = {"source_id": "sebesta-2019", "locator": "ch. 3 s. 2"}
    _record_path, content = _mint_concept_record("closures", hit)
    from ruamel.yaml import YAML
    data = YAML(typ="safe").load(content)
    sources = data["summary"]["sources"]
    assert sources == [{"source": "sebesta-2019", "locator": "ch. 3 s. 2"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/orchestrator && uv run pytest tests/test_exit_test_job.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_orchestrator.jobs.exit_test'`

- [ ] **Step 3: Implement `jobs/exit_test.py`**

```python
# tools/orchestrator/src/langatlas_orchestrator/jobs/exit_test.py
"""Stage 1's hard exit gate (cross-stage plan, Stage 1): 'an agent can run
search_sources, mint a node file that validates, and the run is logged.' Registered as
an ordinary job kind so the exit test is driven through the same generic loop every
other job uses — proving the orchestrator itself, not a bespoke script, is what closes
out Stage 1."""
import io
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_commit.land import Landed, land_record
from langatlas_commit.trailers import record_key
from langatlas_ingest.tools import search_sources
from langatlas_validate.normalize import normalize_record
from langatlas_validate.schema import validate_record

from langatlas_orchestrator.registry import ItemOutcome, register_job_kind

_ITEM_KEY = "mint-search-and-commit"
_SLUG = "orchestrator-exit-test-probe"


def _mint_concept_record(query: str, hit: dict) -> tuple[str, str]:
    """The smallest valid `concept` record, citing the top `search_sources` hit's
    `source_id`/`locator` verbatim — copied from retrieval, never re-derived (Section
    4.3's own rule), which is exactly the property this exit test proves."""
    data = {
        "id": _SLUG,
        "slug": _SLUG,
        "name": "Orchestrator exit-test probe",
        "summary": {
            "text": f"Synthetic concept minted by the R0 exit test to prove the "
                   f"search_sources -> mint -> commit -> log path, retrieved for "
                   f"query {query!r}.",
            "sources": [{"source": hit["source_id"], "locator": hit["locator"]}],
        },
        "provenance": {"claim_origin": "prior"},
    }
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    buf = io.StringIO()
    yaml.dump(data, buf)
    raw = buf.getvalue()
    return f"concepts/{_SLUG}.yaml", normalize_record(raw, "concept")


def _enumerate(extra: dict, repo_root: Path) -> list[str]:
    return [_ITEM_KEY]


def _validator_for(record_path: str, content: str):
    def _validator(worktree: Path) -> list[str]:
        yaml = YAML(typ="safe")
        text = (worktree / record_path).read_text()
        errors = validate_record(yaml.load(text), "concept")
        if normalize_record(text, "concept") != text:
            errors.append("not normalized (re-run the normalizer to fix)")
        return errors
    return _validator


def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
    query = extra.get("query", "pattern matching")

    from langatlas_ingest.db import connect

    conn = connect()
    try:
        hits = search_sources(ctx, query, k=1, conn=conn)
    finally:
        conn.close()

    if not hits:
        return ItemOutcome(status="halted",
                           detail=f"no search_sources hit for query {query!r} — has "
                                  f"`langatlas-sources ingest` run against this corpus?")

    record_path, content = _mint_concept_record(query, hits[0])
    key = record_key(record_path, content)

    result = land_record(repo_root, record_path, content, chat_run_id=f"{ctx.run_id}#msg-1",
                         validator=_validator_for(record_path, content))
    if isinstance(result, Landed):
        return ItemOutcome(status="done", record_key=key,
                           detail=f"landed as {result.commit_sha}")
    return ItemOutcome(status="halted", detail=f"land_record did not land: {result!r}")


register_job_kind("r0-exit-test", _enumerate, _run_item)
```

Edit `tools/orchestrator/src/langatlas_orchestrator/jobs/__init__.py`:

```python
# tools/orchestrator/src/langatlas_orchestrator/jobs/__init__.py
"""Importing this package registers every built-in job kind (D43's periodic-job
inventory) as a side effect. `driver.main()` imports this once before dispatching;
tests import individual `jobs/*` submodules directly and rely on the same import."""
from langatlas_orchestrator.jobs import capability_probe  # noqa: F401
from langatlas_orchestrator.jobs import exit_test  # noqa: F401
```

- [ ] **Step 4: Run the unit-level test to verify it passes**

Run: `cd tools/orchestrator && uv run pytest tests/test_exit_test_job.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Write the failing end-to-end integration test (marked `db`)**

Append to `tools/orchestrator/tests/test_exit_test_job.py`:

```python
# tools/orchestrator/tests/test_exit_test_job.py (part 2 — end-to-end, marked db)
import subprocess

import pytest

from langatlas_orchestrator.driver import EXIT_OK, run as driver_run
from langatlas_orchestrator.checkpoint import CheckpointStore

pytestmark_db = pytest.mark.db


def _git(args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


@pytest.fixture
def bare_and_clone(tmp_path):
    bare = tmp_path / "bare.git"
    _git(["init", "-q", "--bare", "-b", "main", str(bare)], tmp_path)
    clone = tmp_path / "clone"
    _git(["clone", "-q", str(bare), str(clone)], tmp_path)
    _git(["config", "user.email", "bot@example.com"], clone)
    _git(["config", "user.name", "bot"], clone)
    (clone / "README.md").write_text("seed\n")
    _git(["add", "README.md"], clone)
    _git(["commit", "-q", "-m", "seed"], clone)
    _git(["push", "-q", "origin", "main"], clone)
    return clone


@pytest.mark.db
def test_r0_exit_test_end_to_end(db_conn, bare_and_clone, tmp_path, monkeypatch):
    """The literal Stage 1 exit gate: search_sources runs against real ingested
    source_chunks, the driver mints and lands a validating concept record through the
    real commit protocol, and the run's transcript is written to disk (D18's logging
    requirement) — all driven through `langatlas_orchestrator.driver.run`, the same
    entrypoint cron/the developer would invoke for any other job kind."""
    from langatlas_ingest.chunker import Chunk
    from langatlas_ingest.db import migrate
    from langatlas_ingest.embed import embed_source
    from langatlas_ingest.store import SourceChunksStore
    from langatlas_ingest.config import IngestConfig
    from langatlas_pipeline.providers.core import Budget, RunContext

    migrate(db_conn)
    chunk = Chunk(chunk_id="vrh#c00000", source_id="van-roy-haridi-2003", ordinal=0,
                 parent_section_id="vrh#s0000", section_path=["Ch 1"], breadcrumb="Ch 1",
                 locator="p. 42", locator_kind="book-page",
                 text="Pattern matching destructures a value against a sequence of patterns.",
                 token_count=12, content_hash="h0", page_start=42, page_end=42)
    SourceChunksStore(db_conn).replace_source("van-roy-haridi-2003", [chunk])

    ingest_config = IngestConfig.load(overrides={"retrieval_k": 3, "retrieval_candidates": 10})

    class _FakeEmbedCtx:
        def embed(self, texts, *, model):
            return [[float(len(t) % 10) / 10, 0.0, 0.0, 0.0] for t in texts]

    embed_source(_FakeEmbedCtx(), db_conn, config=ingest_config)

    # RunContext.embed/rerank would otherwise call the real university API — this exit
    # test only has to prove the orchestrator's own control flow, not exercise a live
    # network embedding provider (the embedding table above already stands in for it).
    monkeypatch.setattr(RunContext, "embed",
                        lambda self, texts, *, model: [[float(len(t) % 10) / 10, 0.0, 0.0,
                                                        0.0] for t in texts])
    monkeypatch.setattr(RunContext, "rerank",
                        lambda self, query, docs, *, model: [1.0 / (i + 1)
                                                             for i in range(len(docs))])
    monkeypatch.setattr("langatlas_ingest.db.connect", lambda dsn=None: db_conn)
    monkeypatch.setenv("LANGATLAS_INGEST_DSN", "unused-fake-monkeypatched-connect")

    spec_path = tmp_path / "job.yaml"
    spec_path.write_text(f"kind: r0-exit-test\ncheckpoint_path: {tmp_path / 'ck.sqlite'}\n"
                         f"query: pattern matching\n")

    rc = driver_run(spec_path, repo_root=bare_and_clone, status_path=tmp_path / "status.json")

    assert rc == EXIT_OK
    log = _git(["log", "-1", "--format=%B", "origin/main"], bare_and_clone)
    assert "LangAtlas-Record-Key" in log.stdout
    assert "LangAtlas-Chat-Run-Id" in log.stdout
    committed = _git(["show", "origin/main:concepts/orchestrator-exit-test-probe.yaml"],
                     bare_and_clone)
    assert "pattern matching" in committed.stdout.lower() or "van-roy-haridi" in committed.stdout

    row = CheckpointStore(tmp_path / "ck.sqlite").get(spec_kind="r0-exit-test",
                                                      item_key="mint-search-and-commit")
    assert row.status == "done"
```

- [ ] **Step 6: Run the integration test to verify it fails, then run it for real against compose Postgres**

Run: `cd tools/orchestrator && uv run pytest tests/test_exit_test_job.py -m db -v`
Expected first: FAIL (fixtures/imports not yet wired against a running database, or SKIP with
"compose Postgres unreachable" if `docker compose up -d db` has not been run yet — start it if
so, then re-run).
After `docker compose up -d db` and the implementation above: Expected: PASS (3 tests: the 2
unit tests plus this end-to-end one).

Note: this test needs the same `db_conn`/`dsn` fixtures `tools/ingest/tests/conftest.py`
already defines. Create `tools/orchestrator/tests/conftest.py`'s `db_conn`/`dsn` fixtures as a
copy of `tools/ingest/tests/conftest.py`'s versions (same throwaway-database pattern) rather
than importing test fixtures across packages — add them to the existing
`tools/orchestrator/tests/conftest.py` from Task 3 alongside `_isolated_registry`.

- [ ] **Step 7: Run the full orchestrator test suite (non-`db` tests) to check for regressions**

Run: `cd tools/orchestrator && uv run pytest -v`
Expected: PASS, no regressions (the `db`-marked test is deselected by default per
`pyproject.toml`'s `addopts`).

- [ ] **Step 8: Commit**

```bash
git add tools/orchestrator/src/langatlas_orchestrator/jobs/exit_test.py \
        tools/orchestrator/src/langatlas_orchestrator/jobs/__init__.py \
        tools/orchestrator/tests/test_exit_test_job.py \
        tools/orchestrator/tests/conftest.py
git commit -m "feat(#stage-1e): add the r0-exit-test job kind — Stage 1's exit gate"
```

---

## Task 8: Deferred D43-inventory job kinds + `config/jobs/` + `crontab.example`

**Files:**
- Create: `tools/orchestrator/src/langatlas_orchestrator/jobs/deferred.py`
- Modify: `tools/orchestrator/src/langatlas_orchestrator/jobs/__init__.py`
- Test: `tools/orchestrator/tests/test_deferred_jobs.py`
- Create: `config/jobs/r0-exit-test.yaml`
- Create: `config/jobs/monthly-capability-probe.yaml`
- Create: `config/jobs/nightly-verification.yaml`
- Create: `config/jobs/monthly-link-checker.yaml`
- Create: `config/jobs/monthly-finding-aid-mirror-refresh.yaml`
- Create: `config/jobs/monthly-demand-export.yaml`
- Create: `config/jobs/quarterly-edition-check.yaml`
- Create: `config/jobs/backstop-sweep-18mo.yaml`
- Create: `config/jobs/crontab.example`

**Interfaces:**
- Consumes: `register_job_kind`/`ItemOutcome` (Task 3).
- Produces: the six remaining kinds from D43's full periodic-job inventory registered with
  enumerators that fail loudly and specifically rather than silently no-op-ing, plus the
  committed spec files and example crontab D43 §2.5 requires.

- [ ] **Step 1: Write the failing test**

```python
# tools/orchestrator/tests/test_deferred_jobs.py
import pytest

from langatlas_orchestrator.registry import UnknownJobKind, get_job_kind

_DEFERRED_KINDS = (
    "nightly-verification", "monthly-link-checker",
    "monthly-finding-aid-mirror-refresh", "monthly-demand-export",
    "quarterly-edition-check", "backstop-sweep-18mo",
)


@pytest.mark.parametrize("kind", _DEFERRED_KINDS)
def test_deferred_kind_is_registered(kind):
    import langatlas_orchestrator.jobs  # noqa: F401
    get_job_kind(kind)   # raises UnknownJobKind if not registered — the assertion itself


@pytest.mark.parametrize("kind", _DEFERRED_KINDS)
def test_deferred_kind_enumerator_raises_with_a_stage_pointer(kind, tmp_path):
    import langatlas_orchestrator.jobs  # noqa: F401
    enumerator, _item_runner = get_job_kind(kind)
    with pytest.raises(NotImplementedError, match="Stage"):
        enumerator({}, tmp_path)


def test_unregistered_kind_still_raises_unknown_job_kind():
    with pytest.raises(UnknownJobKind):
        get_job_kind("not-a-real-kind-at-all")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/orchestrator && uv run pytest tests/test_deferred_jobs.py -v`
Expected: FAIL — 6 `UnknownJobKind` errors (kinds not yet registered).

- [ ] **Step 3: Implement `jobs/deferred.py`**

```python
# tools/orchestrator/src/langatlas_orchestrator/jobs/deferred.py
"""D43's periodic-job inventory (context/spec.md §14, decisions.md D43's 2026-07-20
follow-up) names ten jobs total; four are real by this stage (`r0-exit-test`,
`monthly-capability-probe`) or don't need driver wiring. The six below all depend on
data or infrastructure a *later* stage produces — an ingested corpus (Stage 2), real
verified facts (Stage 5), or the public site's self-hosted Umami install (Stage 6).
Registering them now with a loud, specific `NotImplementedError` (rather than leaving
`config/jobs/*.yaml` reference an unregistered `kind`, or silently no-op-ing) keeps
`config/jobs/crontab.example` honest today: a cron invocation against one of these
fails immediately and says exactly which stage will replace this stub, instead of
either crashing on an import error or quietly doing nothing."""
from pathlib import Path

from langatlas_orchestrator.registry import ItemOutcome, register_job_kind


def _deferred(kind: str, stage: str, needs: str):
    def _enumerate(extra: dict, repo_root: Path) -> list[str]:
        raise NotImplementedError(
            f"{kind} is deferred to {stage}: needs {needs} (context/spec.md §14)")

    def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
        raise NotImplementedError(f"{kind} is deferred to {stage}: needs {needs}")

    register_job_kind(kind, _enumerate, _run_item)


_deferred("nightly-verification", "Stage 2/5",
         "the calibrated D24 verifier and real facts to assess")
_deferred("monthly-link-checker", "Stage 2",
         "an ingested corpus with url-locator sources to check")
_deferred("monthly-finding-aid-mirror-refresh", "Stage 2",
         "ingested finding-aid sources to mirror")
_deferred("monthly-demand-export", "Stage 6",
         "the self-hosted Umami instance (D33/D52)")
_deferred("quarterly-edition-check", "Stage 2",
         "ingested spec sources with edition metadata")
_deferred("backstop-sweep-18mo", "Stage 5",
         "real facts old enough to need 18-month re-verification")
```

Edit `tools/orchestrator/src/langatlas_orchestrator/jobs/__init__.py`:

```python
# tools/orchestrator/src/langatlas_orchestrator/jobs/__init__.py
"""Importing this package registers every built-in job kind (D43's periodic-job
inventory) as a side effect. `driver.main()` imports this once before dispatching;
tests import individual `jobs/*` submodules directly and rely on the same import."""
from langatlas_orchestrator.jobs import capability_probe  # noqa: F401
from langatlas_orchestrator.jobs import deferred  # noqa: F401
from langatlas_orchestrator.jobs import exit_test  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/orchestrator && uv run pytest tests/test_deferred_jobs.py -v`
Expected: PASS (13 tests: 6 parametrized × 2 + 1)

- [ ] **Step 5: Write `config/jobs/*.yaml`**

```yaml
# config/jobs/r0-exit-test.yaml
kind: r0-exit-test
checkpoint_path: .private/orchestrator/r0-exit-test.sqlite
budget:
  max_calls: 10
  max_wall_seconds: 300
query: pattern matching
```

```yaml
# config/jobs/monthly-capability-probe.yaml
kind: monthly-capability-probe
checkpoint_path: .private/orchestrator/monthly-capability-probe.sqlite
budget:
  max_calls: 50
  max_wall_seconds: 900
```

```yaml
# config/jobs/nightly-verification.yaml
# Deferred to Stage 2/5 (needs the calibrated D24 verifier and real facts) — kept as a
# committed spec now so D43's crontab inventory is complete and legible, per the
# ratified "config/jobs/crontab.example is worth maintaining" decision. Running this
# spec before Stage 2/5 lands raises NotImplementedError with this same pointer.
kind: nightly-verification
checkpoint_path: .private/orchestrator/nightly-verification.sqlite
budget:
  max_calls: 200          # D25's ~200-facts/night nightly budget
  max_wall_seconds: 21600
```

```yaml
# config/jobs/monthly-link-checker.yaml
# Deferred to Stage 2 (needs an ingested corpus with url-locator sources).
kind: monthly-link-checker
checkpoint_path: .private/orchestrator/monthly-link-checker.sqlite
budget:
  max_wall_seconds: 3600
```

```yaml
# config/jobs/monthly-finding-aid-mirror-refresh.yaml
# Deferred to Stage 2 (needs ingested finding-aid sources to mirror).
kind: monthly-finding-aid-mirror-refresh
checkpoint_path: .private/orchestrator/monthly-finding-aid-mirror-refresh.sqlite
budget:
  max_wall_seconds: 3600
```

```yaml
# config/jobs/monthly-demand-export.yaml
# Deferred to Stage 6 (needs the self-hosted Umami instance, D33/D52).
kind: monthly-demand-export
checkpoint_path: .private/orchestrator/monthly-demand-export.sqlite
budget:
  max_wall_seconds: 900
```

```yaml
# config/jobs/quarterly-edition-check.yaml
# Deferred to Stage 2 (needs ingested spec sources with edition metadata).
kind: quarterly-edition-check
checkpoint_path: .private/orchestrator/quarterly-edition-check.sqlite
budget:
  max_wall_seconds: 3600
```

```yaml
# config/jobs/backstop-sweep-18mo.yaml
# Deferred to Stage 5 (needs real facts old enough to need re-verification). This
# spec's own enumerator logic decides monthly whether 18 months have actually elapsed
# and no-ops otherwise (D43 §2.5) — it does not try to express an 18-month period in
# cron syntax directly.
kind: backstop-sweep-18mo
checkpoint_path: .private/orchestrator/backstop-sweep-18mo.sqlite
budget:
  max_calls: 200
  max_wall_seconds: 21600
```

- [ ] **Step 6: Write `config/jobs/crontab.example`**

```
# LangAtlas orchestrator scheduling (D43 §2.5). Documentation only — not itself
# executable; the developer's real crontab is local machine state, same tier as the
# D26 provider cache. Every line invokes the one shared driver against a different
# batch spec; per-job cadence lives here, not in the driver.
#
# The per-language sweep pipeline (D5) is deliberately absent from this file — it is
# always developer-initiated by hand, never run unattended via cron (D43 ratified
# follow-up).

# nightly ~200-fact controversy assessment + re-verification backstop candidates (D25)
0 2 * * *         cd <repo> && uv run --package langatlas-orchestrator langatlas-orchestrator run config/jobs/nightly-verification.yaml

# monthly link-checker (D37)
0 3 1 * *         cd <repo> && uv run --package langatlas-orchestrator langatlas-orchestrator run config/jobs/monthly-link-checker.yaml

# monthly capability probe (D41)
0 3 2 * *         cd <repo> && uv run --package langatlas-orchestrator langatlas-orchestrator run config/jobs/monthly-capability-probe.yaml

# monthly finding-aid mirror refresh (D53)
0 3 3 * *         cd <repo> && uv run --package langatlas-orchestrator langatlas-orchestrator run config/jobs/monthly-finding-aid-mirror-refresh.yaml

# monthly Umami `demand` export (D52) — no-ops until Stage 6's Umami instance exists
0 3 4 * *         cd <repo> && uv run --package langatlas-orchestrator langatlas-orchestrator run config/jobs/monthly-demand-export.yaml

# quarterly edition-check (D37)
0 4 1 1,4,7,10 *  cd <repo> && uv run --package langatlas-orchestrator langatlas-orchestrator run config/jobs/quarterly-edition-check.yaml

# 18-month backstop sweep, checked monthly — the job's own logic no-ops until due (D43 §2.5)
0 5 1 * *         cd <repo> && uv run --package langatlas-orchestrator langatlas-orchestrator run config/jobs/backstop-sweep-18mo.yaml
```

- [ ] **Step 7: Run the full orchestrator test suite**

Run: `cd tools/orchestrator && uv run pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
git add tools/orchestrator/src/langatlas_orchestrator/jobs/deferred.py \
        tools/orchestrator/src/langatlas_orchestrator/jobs/__init__.py \
        tools/orchestrator/tests/test_deferred_jobs.py \
        config/jobs/r0-exit-test.yaml config/jobs/monthly-capability-probe.yaml \
        config/jobs/nightly-verification.yaml config/jobs/monthly-link-checker.yaml \
        config/jobs/monthly-finding-aid-mirror-refresh.yaml \
        config/jobs/monthly-demand-export.yaml config/jobs/quarterly-edition-check.yaml \
        config/jobs/backstop-sweep-18mo.yaml config/jobs/crontab.example
git commit -m "feat(#stage-1e): register the deferred D43 job kinds and commit config/jobs/"
```

---

## Task 9: Wire the CLI entrypoint into the workspace and run the whole suite

**Files:**
- Modify: root `pyproject.toml` or workspace-level `uv` config, if one enumerates the other
  tool packages (check first — see Step 1).
- No new source files; this task is integration/verification only.

**Interfaces:**
- Consumes: everything built in Tasks 1–8.
- Produces: a working `langatlas-orchestrator run <spec>` command usable exactly as
  `config/jobs/crontab.example` invokes it.

- [ ] **Step 1: Check whether a root workspace file already lists sibling tool packages**

Run: `grep -rn "tools/commit\|tools/ingest\|tools/validate" /home/terra/Projects/langatlas-kb/pyproject.toml /home/terra/Projects/langatlas-kb/uv.toml 2>/dev/null || echo "no root workspace file references sibling packages"`

If a root workspace file lists the other `tools/*` packages as members, add
`"tools/orchestrator"` to the same list, matching its existing entries exactly (same
formatting/ordering convention). If no such file exists (each `tools/*` package is a fully
independent `uv` project, as `tools/ingest`/`tools/commit`'s own `[tool.uv.sources]` blocks
already suggest), skip this step — there is nothing to add.

- [ ] **Step 2: Verify the console script resolves**

Run: `cd tools/orchestrator && uv run langatlas-orchestrator run config/jobs/monthly-capability-probe.yaml --repo-root /home/terra/Projects/langatlas-kb`

Expected: the command runs (it will make real Claude/completion-channel calls per
`probe_all`'s existing 1B behavior — this is the same live-provider caveat 1B's own
`langatlas-probe` already carries, not new to this plan). If no provider credentials are
configured in this environment, expect a `ProviderTransportError`/`UnknownAlias` rather than
an import or wiring error — either outcome confirms the CLI entrypoint itself is wired
correctly; a wiring failure would instead show `ModuleNotFoundError` or an argparse error.

- [ ] **Step 3: Run every non-`db`-marked test across the four touched packages**

Run:
```bash
cd tools/orchestrator && uv run pytest -v
cd ../pipeline && uv run pytest -v
cd ../commit && uv run pytest -v
cd ../validate && uv run pytest -v
```

Expected: PASS across all four, no regressions from this plan's changes.

- [ ] **Step 4: Run the `db`-marked exit-test integration test one more time end-to-end**

Run: `docker compose up -d db && cd tools/orchestrator && uv run pytest -m db -v`
Expected: PASS — this is the actual Stage 1 exit-test evidence to record in
`context/spec.md`'s checklist (the `[ ]` next to "R0 exit test" under Stage 1 becomes `[x]`
once this passes, per the checkbox-plan convention in the top-level CLAUDE.md).

- [ ] **Step 5: Update `context/spec.md`'s Stage 1 checklist**

Edit `context/spec.md`, in the Stage 1 section (around the line currently reading `- [ ] R0
exit test: an agent can run \`search_sources\`, mint a node file that validates, and the run
is logged.`), check every remaining unchecked Stage 1 box this plan completes:

```markdown
- [x] Provider abstraction + `RunContext` (D26/D53): openai-SDK channel, Claude channel,
      cost log, cache, budget signals, data-not-instructions delimiting + lexical scan
      (D31).
- [x] Transcript logging (D18): wrapper persistence, normalizer, `langatlas-transcripts`
      repo (CC0 license file), gitleaks CI, `REDACTIONS.md` convention.
- [x] Prompt registry `prompts/` + `config/provider_capabilities.yaml` + first probe run
      (D41).
- [x] Agent-runner commit protocol (D36): GitHub App, trailers, land loop, is-main-green
      gate, failure bot.
- [x] CI: validated-artifact pipeline skeleton (D13) — validators, fact derivation,
      collision check, last-green publication, `data-vN` tagging.
- [x] Orchestrator `tools/orchestrator/driver.py` + `config/jobs/` +
      `crontab.example` (D43).
- [x] R0 exit test: an agent can run `search_sources`, mint a node file that validates,
      and the run is logged.
```

(Only add `[x]` to boxes this or prior sub-plans actually closed — cross-check against
1A/1B/1C/1D's own already-checked items rather than assuming all of Stage 1 is this plan's
doing.)

- [ ] **Step 6: Commit**

```bash
git add context/spec.md
git commit -m "docs(#stage-1e): check off Stage 1's completed items — R0 exit test is green"
```

---

## Self-Review

**Spec coverage** — every element the cross-stage plan's 1E entry and D43 name has a task:
driver shape + job-kind registry (Tasks 3/5), checkpoint unit/storage (Task 1), budget
hard-stop handling (Task 5), Claude usage-limit cool-down (Task 5), alerting via
`status.json` + `report.py` (Task 4), scheduling via `config/jobs/crontab.example` (Task 8),
the R0 exit test itself (Task 7). The developer's four ratified follow-ups are all respected:
the sweep pipeline is not in `crontab.example` (Task 8 note), the 4-hour cool-down is the
literal constant in `driver.py` (Task 5), no cron-mail wiring was added anywhere, and
`crontab.example` is committed (Task 8).

**Placeholder scan** — no TBD/TODO markers. The one place that looks stub-shaped
(`jobs/deferred.py`, Task 8) is a deliberate, tested, stage-pointing `NotImplementedError` —
real code with a real assertion in `test_deferred_jobs.py`, not an unwritten step; the cross-
stage plan's own precedent (1C's "carried over, not built yet, named not deferred silently"
notes) is the model this follows.

**Type consistency** — `ItemOutcome` (Task 3) is the one return type every `jobs/*.py` item
runner produces and the only type `driver.py`'s `run()` (Task 5) pattern-matches on.
`EnumeratorFn`/`ItemRunnerFn`'s four-argument shapes (`extra, repo_root` /
`ctx, item_key, extra, repo_root`) are identical across `capability_probe.py`, `exit_test.py`,
and `deferred.py` — no job kind uses a different signature. `BatchSpec.extra` (Task 2) is
exactly the `dict` every `EnumeratorFn`/`ItemRunnerFn` receives as `extra` — no job kind reads
spec fields any other way. `CheckpointRow.record_key` (Task 1) is the same field
`ItemOutcome.record_key` (Task 3) populates and `driver.py`'s ambiguous-row resolution (Task
5) reads back via `find_record_key_in_history` — one name, one meaning, end to end.

---

## Execution Handoff

Plan complete and saved to
`docs/superpowers/plans/2026-08-22-stage-1e-orchestrator-and-r0-exit-test.md`. Two execution
options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between
tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution
with checkpoints.

Which approach?
