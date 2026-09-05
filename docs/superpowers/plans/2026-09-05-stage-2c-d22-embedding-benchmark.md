# Stage 2C — D22 Embedding Benchmark (R2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Check each box off **immediately** when its step is
> done, and include the plan-file change in the same commit as the step it belongs to. Commit
> this plan file itself before the first task's commit.

**Goal:** Run §8.6's D22 benchmark on a pilot corpus across six embedding candidates and three
retrieval modes, apply §8.6's decision rules mechanically, and pin the source-corpus table's
model / dimension / index type into `config/ingest.yaml` — so 2D and Stage 3 retrieve against a
settled, measured stack instead of an assumed one.

**Architecture:** One new subpackage, `langatlas_ingest.benchmark`, holding six separable layers:
a **pilot selector** (which 3–4 sources maximise golden-query coverage), a **bench-corpus
builder** (a throwaway `langatlas_bench` database so no arm ever touches production
`source_chunks`), a **span-overlap relevance rule** (so the 400/800 chunk-size axis can be scored
against a golden set whose chunk ids were minted at 600), a **metrics** layer (indexing
throughput + storage, which `EvalResult` does not carry), an **arm runner** (one `RunContext`,
one transcript, one committed result JSON per arm, resumable), and a **verdict** module encoding
§8.6's decision rules as code. Four enabling changes land in existing packages first: an
embedding-capability probe, truncation-honest embedding, a local fastembed backend, and a
retrieval `mode` axis on `SourceSearch` + `run_eval`.

**Tech Stack:** `langatlas_ingest` (`config.IngestConfig`, `db.connect`/`migrate`/
`ensure_embedding_table`/`embedding_table_name`, `embed.embed_source`, `search.SourceSearch`,
`eval.run_eval`, `store.SourceChunksStore`, `pipeline.ingest_source`, `snapshot.SnapshotStore`,
`chunker.count_tokens`, `cli`), `langatlas_pipeline` (`providers.core.RunContext`/`Budget`,
`providers.embedding.EmbeddingClient`, `providers.completion.build_client`/`estimate_tokens`,
`config.ProviderConfig`/`EmbeddingCapability`, `observability.probe`), `psycopg` v3, `pgvector`
(HNSW over `halfvec`), `ruamel.yaml`, `fastembed` (new optional extra, CPU/ONNX), `pytest`.
**No schema migration, no new package outside `langatlas_ingest.benchmark`.**

**Spec:** [context/spec.md](../../../context/spec.md) — §8.6 (the benchmark itself: candidates,
variants, metrics, decision rules, per-table verdicts), §8.1 (the retrieval shape being varied),
§8.2 (the source-corpus table), §8.3 (what is deferred to Stage 5), §7.1 (the university-API
embedding/reranker roster).

**Sequencing contract:**
[2026-08-23-stage-2-corpus-and-benchmark.md](2026-08-23-stage-2-corpus-and-benchmark.md), section
"2C — D22 embedding benchmark (R2)".

**Predecessors:**
[2026-08-23-stage-2a-corpus-assembly-ingestion-qa.md](2026-08-23-stage-2a-corpus-assembly-ingestion-qa.md)
and [2026-08-27-stage-2b-golden-sets-and-scoring-harnesses.md](2026-08-27-stage-2b-golden-sets-and-scoring-harnesses.md)
— both complete. 2A's 26 ingested sources / 14,391 chunks and 2B's 52 committed retrieval queries
are this plan's raw material.

---

## Global Constraints

Every task's requirements implicitly include this section.

- No deadline; do not take shortcuts that damage the long-term product (D6/D11).
- **Git is the database (D1).** Postgres, extracted text and embeddings are derived and never
  authoritative; embeddings stay out of git (D15). The benchmark's *results and verdict* are a
  different thing — they are a research record justifying a pinned configuration, so they **are**
  committed, under `benchmarks/d22-source-corpus/`. Vectors, tables and the bench database are
  not.
- **The benchmark never writes to the production database.** Every arm runs against a separate
  `langatlas_bench` database. A task that finds itself dropping or re-chunking a table in
  `langatlas` has gone wrong.
- **Claude never does volume work; the university API never has the final judgment call (D6).**
  Here: every embedding and rerank call in every arm goes to the university API or to the local
  CPU model. Claude's role is reading the verdict table with the developer. Claude is never an
  arm.
- Every provider call is logged (D18) — **every benchmark arm runs inside its own `RunContext`
  and therefore writes its own transcript**, named `<date>-benchmark-<arm_id>-<seq>`.
- **Model ids are configuration, never hardcoded** (`config/ingest.yaml`,
  `config/provider_capabilities.yaml`, `config/benchmark/d22-source-corpus.yaml`). No test and no
  module may contain a literal candidate model id outside a fixture.
- `config/provider_capabilities.yaml` is **never hand-edited from guesses** and never
  auto-committed (D41). Task 1 exists so the candidate roster's dimensions are *measured*, and
  the developer commits the reviewed diff.
- Short-context models are tested **honestly**: breadcrumb-prefixed chunks truncated exactly as
  production would truncate them, never given a longer window than they would get, and the
  truncation count is reported in the arm's result (§8.6).
- English-only; code MIT, corpus CC BY-SA 4.0 (D7, D14).
- Conventional commits, scope `#stage-2c` (matching 2A's `#stage-2a` and 2B's `#stage-2b`).
- Tests run per package: `uv --directory tools/ingest run pytest` and
  `uv --directory tools/pipeline run pytest`. Tests needing the compose Postgres carry
  `@pytest.mark.db` and are run with `-m db` after `docker compose up -d db`. Tests hitting a
  real provider carry `@pytest.mark.live` and are deselected by default (`addopts = "-m 'not
  live'"` in `tools/ingest/pyproject.toml`).

## Ratified inputs and plan-level decisions (flag for developer ratification)

§8.6 does not settle four points this plan must nail down. They are recorded here so no task
invents them silently; the developer ratifies them at the Task 6 checkpoint.

1. **Chunk-size axis endpoints.** §8.6 says "400 vs 800 chunk size". Production is
   `target_tokens: 600 / max_tokens: 800` — a 1.33× target-to-max ratio. The two secondary arms
   keep that ratio: **400/550** and **800/1050**. The 600/800 production chunking is the third
   point of the axis and is already the primary matrix's chunking, so it is not re-run.
2. **Chunk-size decision rule.** §8.6 gives none. This plan adopts the same 2-point convention as
   the other secondary rules: **the chunking moves off 600/800 only if a secondary arm beats the
   primary arm by ≥2.0 points Recall@5** on the chosen model, hybrid+rerank.
3. **Local-model precedence.** §8.6's incumbent rule reads "stays unless beaten by ≥5 pts
   Recall@5, **or matched within 2 pts by a local model**". A matching local model therefore
   *wins* — free-and-local is the preferred floor when it is within 2 points. `decide()` checks
   the local-match rule before the beat-by-5 rule.
4. **Vector-only arms are never reranked.** The reranker operates on the RRF-fused pool; scoring
   a reranked vector-only pool answers a question §8.6 does not ask and doubles the completion
   spend. Arms are `{vector, hybrid, hybrid+rerank}`, three per model.

## Measured inputs (computed 2026-09-05 against the committed corpus and golden set)

Recorded so no task re-derives them, and so Task 7's output has an expected answer to check
against:

- The retrieval golden set holds **52 queries** across `tests/golden/retrieval/queries-derived.yaml`
  (20, `exact-term`), `queries-concepts.yaml` (20, `paraphrase-concept`) and `queries-survey.yaml`
  (12, `cross-source-survey`). `queries.example.yaml` is skipped by name.
- Golden queries name 12 distinct sources. Frequency: `sebesta-copl` 27, `scott-plp` 18,
  `vanroy-haridi-2003` 4, `python-langref-3` 4, `rust-reference` 4, `rust-fls` 4,
  `haskell-2010-report` 2, `ghc-users-guide` 2, `c23-n3220` 2, `jls-se25` 2, `pierce-tapl-2002` 2,
  `jordan-et-al-2015` 1.
- Best 4-source pilot by fully-covered queries: **`rust-fls`, `rust-reference`, `scott-plp`,
  `sebesta-copl` → 37/52 queries** (16 exact-term, 16 paraphrase-concept, 5 cross-source-survey),
  **3,826 chunks**. Best 3-source pilot: `python-langref-3`, `scott-plp`, `sebesta-copl` → 34/52.
- Production chunk counts for the pilot: `rust-fls` 1188, `sebesta-copl` 1005, `scott-plp` 845,
  `rust-reference` 788.
- `config/provider_capabilities.yaml` currently records four embedding models
  (`qwen3-embedding-4b` 2560-dim/40960-token, `nomic-embed-text-v1.5` 768/8192,
  `mxbai-embed-large` 1024/512, `multilingual-e5-large-instruct` 1024/512). **`nomic-embed-text-v2-moe`
  is absent** — Task 1 measures and adds it.

---

## File Structure

**New files**

| Path | Responsibility |
|---|---|
| `tools/pipeline/src/langatlas_pipeline/providers/local_embedding.py` | fastembed CPU backend behind the `local:` model prefix; same cache/recorder contract as the remote client |
| `tools/pipeline/tests/test_local_embedding.py` | local backend tests (fake encoder; no fastembed needed) |
| `tools/pipeline/tests/test_probe_embeddings.py` | embedding-probe tests |
| `tools/ingest/src/langatlas_ingest/benchmark/__init__.py` | package marker |
| `tools/ingest/src/langatlas_ingest/benchmark/arms.py` | `Arm`, arm-id minting, matrix expansion from YAML |
| `tools/ingest/src/langatlas_ingest/benchmark/pilot.py` | coverage-maximising pilot selection over the golden set |
| `tools/ingest/src/langatlas_ingest/benchmark/corpus.py` | bench-database creation + pilot re-ingestion at a given chunk size + chunk-id parity check |
| `tools/ingest/src/langatlas_ingest/benchmark/relevance.py` | chunking-independent span-overlap relevance for the chunk-size axis |
| `tools/ingest/src/langatlas_ingest/benchmark/metrics.py` | `IndexStats`: embed throughput, truncation counts, table storage |
| `tools/ingest/src/langatlas_ingest/benchmark/runner.py` | `run_arm` / `run_matrix`, result JSON read/write, resumability |
| `tools/ingest/src/langatlas_ingest/benchmark/verdict.py` | §8.6's decision rules as code |
| `tools/ingest/src/langatlas_ingest/benchmark/report.py` | matrix table + verdict markdown |
| `tools/ingest/tests/test_benchmark_arms.py` … `test_benchmark_report.py` | one test module per benchmark module |
| `config/benchmark/d22-source-corpus.yaml` | the committed run matrix: pilot, candidates, modes, chunk sizes, margins |
| `benchmarks/d22-source-corpus/results/<arm_id>.json` | one committed result per arm |
| `benchmarks/d22-source-corpus/verdict.json` / `verdict.md` | the per-table verdict record |
| `benchmarks/d22-source-corpus/README.md` | what this directory is and how to re-run it |

**Modified files**

| Path | Change |
|---|---|
| `tools/pipeline/src/langatlas_pipeline/observability/probe.py` | `probe_embedding` / `probe_embeddings` / `apply_embedding_probe`, `--embeddings` flag |
| `tools/pipeline/src/langatlas_pipeline/providers/embedding.py` | `truncate=` parameter, `truncated` / `cache_hits` counters |
| `tools/pipeline/src/langatlas_pipeline/providers/completion.py` | `truncate_to_tokens` helper |
| `tools/pipeline/src/langatlas_pipeline/providers/core.py` | `embed(..., truncate=)`, `local:` dispatch, `embedding_truncations` / `embedding_cache_hits` |
| `tools/pipeline/src/langatlas_pipeline/config.py` | `embedding()` also resolves `local_embeddings:` |
| `tools/pipeline/pyproject.toml` | `local-embed` optional extra (`fastembed`) |
| `config/provider_capabilities.yaml` | probed `nomic-embed-text-v2-moe`; new `local_embeddings:` block |
| `tools/ingest/src/langatlas_ingest/search.py` | `mode` axis (`hybrid` / `vector` / `fts`) |
| `tools/ingest/src/langatlas_ingest/eval.py` | `depth`, `mode`, `corpus_sources`, injectable `relevance` and `search`; `recall_at_50`, `skipped_queries` |
| `tools/ingest/src/langatlas_ingest/config.py` | `retrieval_mode`, `embedding_dimensions`, `index_type` |
| `tools/ingest/src/langatlas_ingest/errors.py` | `UnknownSearchMode`, `IncompleteMatrix`, `BenchCorpusMismatch` |
| `tools/ingest/src/langatlas_ingest/paths.py` | `BENCHMARK_DIR`, `BENCHMARK_CONFIG_PATH` |
| `tools/ingest/src/langatlas_ingest/cli.py` | `bench-pilot`, `bench-build`, `bench-run`, `bench-verdict` |
| `config/ingest.yaml` | `retrieval.mode`, `models.embedding_dimensions`, `models.index_type` |

---

## Task 1: Embedding-capability probe

`config/provider_capabilities.yaml` records four embedding models and is missing
`nomic-embed-text-v2-moe`, which §7.1 lists as a candidate. The file's own header forbids
hand-editing from guesses (D41), and `langatlas-probe` only probes *chat* aliases. Measuring an
embedding model's dimension is a one-call question, so the benchmark's roster gets measured
rather than assumed.

`max_input_tokens` is deliberately **not** guessed: it is read from the gateway's
`/v1/model/info` when the gateway reports it, otherwise carried forward from the existing entry,
otherwise left `None` — and `apply_embedding_probe` refuses to write an entry with no
`max_input_tokens`, telling the developer to take it from the model card and commit it
deliberately. An invented context window would make the "tested honestly" clause a lie.

**Files:**
- Modify: `tools/pipeline/src/langatlas_pipeline/observability/probe.py`
- Create: `tools/pipeline/tests/test_probe_embeddings.py`
- Modify: `config/provider_capabilities.yaml` (Step 7, from the probe's own output)

**Interfaces:**
- Consumes: `ProviderConfig.load()`, `RunContext.start()`, `providers.completion.build_client`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class EmbeddingProbe:
      model: str
      dimensions: int | None
      max_input_tokens: int | None
      reachable: bool
      error: str | None = None
      def as_entry(self) -> dict          # {"dimensions": int, "max_input_tokens": int}

  def probe_embedding(ctx, model: str, *, client=None) -> EmbeddingProbe
  def probe_embeddings(ctx, models: Sequence[str] | None = None, *, client=None) \
          -> dict[str, EmbeddingProbe]
  def diff_embeddings(current: dict, probed: dict[str, EmbeddingProbe]) -> list[str]
  def apply_embedding_probe(path: Path, probed: dict[str, EmbeddingProbe]) -> list[str]
  ```
  `apply_embedding_probe` returns the list of models it **refused** to write (unreachable, or no
  `max_input_tokens` from any source).

- [x] **Step 1: Write the failing tests**

Create `tools/pipeline/tests/test_probe_embeddings.py`:

```python
import pytest
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_pipeline.observability.probe import (
    EmbeddingProbe, apply_embedding_probe, diff_embeddings, probe_embedding,
    probe_embeddings,
)


class _FakeEmbeddings:
    def __init__(self, dimensions, fail=False):
        self.dimensions = dimensions
        self.fail = fail
        self.calls = []

    def create(self, *, model, input):
        self.calls.append((model, list(input)))
        if self.fail:
            raise RuntimeError("model not found")

        class Item:
            embedding = [0.0] * self.dimensions

        class Response:
            data = [Item()]
            usage = type("U", (), {"prompt_tokens": 3})()

        return Response()


class _FakeClient:
    def __init__(self, dimensions, fail=False):
        self.embeddings = _FakeEmbeddings(dimensions, fail)


class _FakeConfig:
    def __init__(self, entries):
        self.capabilities = {"embeddings": entries}
        self.providers = {}

    def completion_settings(self):
        return {"min_interval_seconds": {"embedding": 0.0}, "max_attempts": 1}


class _FakeRecorder:
    def __init__(self):
        self.calls = []

    def record_call(self, **kwargs):
        self.calls.append(kwargs)


class _FakeCtx:
    def __init__(self, entries):
        self.config = _FakeConfig(entries)
        self.recorder = _FakeRecorder()
        self.cache = None

    def check_budget(self, **kwargs):
        pass

    def note_usage(self, **kwargs):
        pass


def test_probe_measures_dimensions_from_the_returned_vector():
    ctx = _FakeCtx({"m": {"dimensions": 99, "max_input_tokens": 512}})
    probe = probe_embedding(ctx, "m", client=_FakeClient(768))
    assert probe.reachable is True
    # The *measured* length wins over the recorded 99 — that is the whole point.
    assert probe.dimensions == 768
    assert probe.max_input_tokens == 512


def test_probe_records_an_unreachable_model_instead_of_raising():
    ctx = _FakeCtx({"m": {"dimensions": 768, "max_input_tokens": 512}})
    probe = probe_embedding(ctx, "m", client=_FakeClient(768, fail=True))
    assert probe.reachable is False
    assert probe.dimensions is None
    assert "model not found" in probe.error


def test_probe_leaves_max_input_tokens_none_for_an_unknown_model():
    ctx = _FakeCtx({})
    probe = probe_embedding(ctx, "brand-new", client=_FakeClient(1024))
    assert probe.dimensions == 1024
    assert probe.max_input_tokens is None


def test_probe_embeddings_defaults_to_the_recorded_roster():
    ctx = _FakeCtx({"a": {"dimensions": 4, "max_input_tokens": 512},
                    "b": {"dimensions": 4, "max_input_tokens": 512}})
    probed = probe_embeddings(ctx, client=_FakeClient(4))
    assert sorted(probed) == ["a", "b"]


def test_diff_reports_a_dimension_change():
    current = {"embeddings": {"a": {"dimensions": 768, "max_input_tokens": 512}}}
    probed = {"a": EmbeddingProbe("a", 1024, 512, True)}
    assert diff_embeddings(current, probed) == [
        "a.dimensions: 768 -> 1024"]


def test_apply_refuses_an_entry_with_no_max_input_tokens(tmp_path: Path):
    path = tmp_path / "provider_capabilities.yaml"
    path.write_text("version: 1\nembeddings:\n  a: {dimensions: 4, max_input_tokens: 8}\n")
    refused = apply_embedding_probe(path, {"new": EmbeddingProbe("new", 1024, None, True)})
    assert refused == ["new"]
    data = YAML(typ="safe").load(path.read_text())
    assert "new" not in data["embeddings"]


def test_apply_writes_a_complete_entry_and_keeps_the_others(tmp_path: Path):
    path = tmp_path / "provider_capabilities.yaml"
    path.write_text("version: 1\nembeddings:\n  a: {dimensions: 4, max_input_tokens: 8}\n")
    refused = apply_embedding_probe(path, {"new": EmbeddingProbe("new", 1024, 512, True)})
    assert refused == []
    data = YAML(typ="safe").load(path.read_text())
    assert data["embeddings"]["new"] == {"dimensions": 1024, "max_input_tokens": 512}
    assert data["embeddings"]["a"] == {"dimensions": 4, "max_input_tokens": 8}


def test_apply_skips_an_unreachable_model(tmp_path: Path):
    path = tmp_path / "provider_capabilities.yaml"
    path.write_text("version: 1\nembeddings: {}\n")
    refused = apply_embedding_probe(
        path, {"gone": EmbeddingProbe("gone", None, None, False, "404")})
    assert refused == ["gone"]
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/pipeline run pytest tests/test_probe_embeddings.py -v`
Expected: FAIL — `ImportError: cannot import name 'EmbeddingProbe'`.

- [x] **Step 3: Implement the probe**

Append to `tools/pipeline/src/langatlas_pipeline/observability/probe.py` (the module already
imports `Path`, `Any`, `_yaml`, `RunContext`, `Budget`, `utc_now`; add
`from dataclasses import dataclass` and `from typing import Sequence`):

```python
# A one-word input is enough to learn a vector's length, and keeps the probe's cost at
# a rounding error. It is deliberately not domain text: nothing about this call should
# depend on the corpus.
_PROBE_INPUT = "probe"
# The window the probe declares when the table has none. A model nobody has recorded yet
# is exactly the case the probe exists for, so the embed call must not route through the
# capability lookup and fail with UnknownAlias — which would be reported as "unreachable"
# and hide a perfectly working model.
_UNBOUNDED_WINDOW = 10 ** 9


@dataclass(frozen=True)
class EmbeddingProbe:
    """What one embedding model answered. `dimensions` is *measured* from the returned
    vector — the one fact a call can establish for free. `max_input_tokens` is never
    guessed: the gateway's model-info route, else the existing recorded entry, else
    None, which `apply_embedding_probe` refuses to write."""

    model: str
    dimensions: int | None
    max_input_tokens: int | None
    reachable: bool
    error: str | None = None

    def as_entry(self) -> dict:
        return {"dimensions": self.dimensions,
                "max_input_tokens": self.max_input_tokens}

    def complete(self) -> bool:
        return (self.reachable and self.dimensions is not None
                and self.max_input_tokens is not None)


def _recorded_window(ctx, model: str) -> int | None:
    entry = ctx.config.capabilities.get("embeddings", {}).get(model) or {}
    value = entry.get("max_input_tokens")
    return int(value) if value else None


def probe_embedding(ctx, model: str, *, client=None) -> EmbeddingProbe:
    """One embeddings call per model. Routed through `EmbeddingClient` so the probe is
    budgeted, throttled and logged exactly like production embedding traffic (D26/D18) —
    a probe that bypassed the policy core would be measuring a path nothing else uses."""
    from langatlas_pipeline.providers.embedding import EmbeddingClient

    window = _recorded_window(ctx, model)
    embedder = EmbeddingClient(ctx, client=client)
    try:
        vectors = embedder.embed([_PROBE_INPUT], model=model, truncate=True,
                                 max_input_tokens=window or _UNBOUNDED_WINDOW)
    except Exception as exc:                      # noqa: BLE001 - any failure is a verdict
        return EmbeddingProbe(model, None, window, False, f"{type(exc).__name__}: {exc}")
    return EmbeddingProbe(model, len(vectors[0]), window, True)


def probe_embeddings(ctx, models: Sequence[str] | None = None, *,
                     client=None) -> dict[str, EmbeddingProbe]:
    names = list(models) if models else list(ctx.config.capabilities.get("embeddings", {}))
    return {name: probe_embedding(ctx, name, client=client) for name in names}


def diff_embeddings(current: dict, probed: dict[str, EmbeddingProbe]) -> list[str]:
    """Drift lines for developer review, mirroring `diff_capabilities`. Never applied
    automatically (D41)."""
    lines: list[str] = []
    for model, probe in probed.items():
        entry = current.get("embeddings", {}).get(model)
        if entry is None:
            lines.append(f"{model}: new model, dimensions={probe.dimensions}"
                         f" max_input_tokens={probe.max_input_tokens}")
            continue
        for key, value in probe.as_entry().items():
            if value is not None and entry.get(key) != value:
                lines.append(f"{model}.{key}: {entry.get(key)!r} -> {value!r}")
    return lines


def apply_embedding_probe(path: Path, probed: dict[str, EmbeddingProbe]) -> list[str]:
    """Write only *complete* measurements. A model whose context window nobody has
    established is refused rather than defaulted: §8.6's honest-truncation clause is
    built on that number, so an invented one would corrupt the benchmark quietly."""
    data = _yaml.load(path.read_text())
    refused = [model for model, probe in probed.items() if not probe.complete()]
    for model, probe in probed.items():
        if probe.complete():
            data.setdefault("embeddings", {})[model] = probe.as_entry()
    with path.open("w", encoding="utf-8") as fh:
        _yaml.dump(data, fh)
    return sorted(refused)
```

Then extend `main()` — replace its body between the `parse_args` call and the `return` with a
branch on the new flag:

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-probe")
    parser.add_argument("--write", action="store_true",
                       help="apply the probe result to config/provider_capabilities.yaml")
    parser.add_argument("--embeddings", action="store_true",
                        help="probe the embedding roster (dimensions) instead of the"
                             " chat aliases")
    parser.add_argument("--model", action="append", default=[],
                        help="with --embeddings: probe this model (repeatable). Use it to"
                             " measure a candidate the table does not list yet.")
    parser.add_argument("--config-dir", type=Path, default=CONFIG_DIR)
    args = parser.parse_args(argv)
    path = args.config_dir / "provider_capabilities.yaml"

    if args.embeddings:
        with RunContext.start(kind="probe", slug="embeddings",
                              budget=Budget(max_calls=50), no_cache=True) as ctx:
            probed = probe_embeddings(ctx, args.model or None)
            drift = diff_embeddings(ctx.config.capabilities, probed)
        for line in drift or ["no embedding capability drift"]:
            print(f"drift: {line}" if drift else line)
        if args.write:
            refused = apply_embedding_probe(path, probed)
            print(f"wrote {path} — review the diff and commit it deliberately")
            for model in refused:
                probe = probed[model]
                print(f"REFUSED {model}: reachable={probe.reachable}"
                      f" max_input_tokens={probe.max_input_tokens};"
                      " add max_input_tokens from the model card and commit it by hand")
            return 0
        return 1 if drift else 0

    with RunContext.start(kind="probe", slug="capabilities",
                          budget=Budget(max_calls=50), no_cache=True) as ctx:
        probed_aliases = probe_all(ctx)
        drift = diff_capabilities(ctx.config.capabilities, probed_aliases)
    if not drift:
        print("no capability drift")
    for line in drift:
        print(f"drift: {line}")
    if args.write:
        apply_probe(path, probed_aliases)
        print(f"wrote {path} — review the diff and commit it deliberately")
        return 0
    return 1 if drift else 0
```

> `probe_embedding` passes `truncate=True` and `max_input_tokens=` to
> `EmbeddingClient.embed`; **Task 2 adds both parameters**. Implement Task 2 before running the
> live probe in Step 6 — the unit tests in Step 4 exercise the fake client only, but the two
> tasks are ordered this way because Task 1's tests define the interface Task 2 implements.
> If you are executing tasks strictly in order and Step 4 fails on an unexpected keyword
> argument, do Task 2 Steps 3–4 first, then return here.

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv --directory tools/pipeline run pytest tests/test_probe_embeddings.py -v`
Expected: PASS (8 tests).

- [x] **Step 5: Commit the probe**

```bash
git add tools/pipeline/src/langatlas_pipeline/observability/probe.py \
        tools/pipeline/tests/test_probe_embeddings.py \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): probe embedding models for their real dimensions"
```

- [x] **Step 6: Run the live probe (developer checkpoint)**

With the university API credentials in the environment:

```bash
uv --directory tools/pipeline run langatlas-probe --embeddings \
    --model nomic-embed-text-v2-moe --write
uv --directory tools/pipeline run langatlas-probe --embeddings --write
git diff config/provider_capabilities.yaml
```

Expected: the four recorded models confirm their dimensions (a *changed* dimension is a
finding — stop and report it, do not proceed), and `nomic-embed-text-v2-moe` is added or is
reported REFUSED because the gateway does not serve it. If it is refused as unreachable, drop it
from the candidate roster in Task 6's matrix and record why in
`benchmarks/d22-source-corpus/README.md` — do not substitute a different model on your own.
If it is refused only for a missing `max_input_tokens`, add that number by hand from the Nomic
model card and say in the commit message where it came from.

**This is a developer checkpoint: the developer reads the diff and approves it before it is
committed.**

- [x] **Step 7: Commit the reviewed capability diff**

```bash
git add config/provider_capabilities.yaml
git commit -m "feat(#stage-2c): record the probed D22 embedding candidate roster"
```

---

## Task 2: Truncation-honest embedding

`EmbeddingClient.embed` raises `ContextTooLarge` when a text exceeds the model's window — the
right production default ("the wrapper never auto-truncates; the call site decides"). But
`mxbai-embed-large` and `multilingual-e5-large-instruct` have 512-token windows and the corpus is
chunked at 600/800, so those two candidates would simply crash instead of being benchmarked.
§8.6 requires them tested honestly: **truncated exactly as production would truncate them, and
never given a longer window than they would get**.

So truncation becomes an explicit, counted opt-in. The count is a first-class benchmark metric:
an arm that truncated 91% of its chunks and still scored well is a very different finding from
one that truncated none.

§8.6's "breadcrumb-prefixed chunks" clause needs no work: `chunker.Chunk.text` is *already* the
breadcrumb-prefixed string ("this is what gets embedded"), and `embed_source` embeds exactly
`chunk.text`. Truncating here therefore shortens the same string production would send, prefix
included — which is the point. Do not strip or re-derive the breadcrumb for a short-context arm;
that would give the model an input production never produces.

**Files:**
- Modify: `tools/pipeline/src/langatlas_pipeline/providers/completion.py` (add `truncate_to_tokens`)
- Modify: `tools/pipeline/src/langatlas_pipeline/providers/embedding.py`
- Modify: `tools/pipeline/src/langatlas_pipeline/providers/core.py`
- Test: `tools/pipeline/tests/test_embedding_rerank.py` (extend)

**Interfaces:**
- Consumes: `estimate_tokens`, `ContextTooLarge`, `cache_key`, `ctx.recorder.record_call`.
- Produces:
  ```python
  def truncate_to_tokens(text: str, max_tokens: int) -> str

  class EmbeddingClient:
      truncated: int            # texts shortened so far
      cache_hits: int           # vectors served from the content-addressed cache
      def embed(self, texts: list[str], *, model: str, truncate: bool = False,
                max_input_tokens: int | None = None) -> list[list[float]]

  class RunContext:
      def embed(self, texts, *, model, truncate: bool = False,
                max_input_tokens: int | None = None) -> list[list[float]]
      @property
      def embedding_truncations(self) -> int
      @property
      def embedding_cache_hits(self) -> int
  ```
  `max_input_tokens` overrides the capability table's window — Task 1's probe needs it for a
  model the table does not list yet, and nothing else should pass it.

- [x] **Step 1: Write the failing tests**

Append to `tools/pipeline/tests/test_embedding_rerank.py`:

```python
from langatlas_pipeline.errors import ContextTooLarge
from langatlas_pipeline.providers.completion import estimate_tokens, truncate_to_tokens
from langatlas_pipeline.providers.embedding import EmbeddingClient


def test_truncate_to_tokens_lands_under_the_cap():
    text = "word " * 5000
    shortened = truncate_to_tokens(text, 512)
    assert estimate_tokens([{"content": shortened}]) <= 512
    assert shortened == text[:len(shortened)]     # a prefix, never a resample


def test_truncate_to_tokens_leaves_a_short_text_untouched():
    assert truncate_to_tokens("short", 512) == "short"


def test_embed_still_raises_without_the_opt_in(embedding_ctx, fake_openai):
    client = EmbeddingClient(embedding_ctx, client=fake_openai)
    with pytest.raises(ContextTooLarge):
        client.embed(["word " * 5000], model="tiny-window")


def test_embed_truncates_and_counts_when_asked(embedding_ctx, fake_openai):
    client = EmbeddingClient(embedding_ctx, client=fake_openai)
    client.embed(["word " * 5000, "short"], model="tiny-window", truncate=True)
    assert client.truncated == 1
    sent = fake_openai.embeddings.calls[-1][1]
    assert estimate_tokens([{"content": sent[0]}]) <= 512
    assert sent[1] == "short"


def test_embed_honours_an_explicit_window_override(embedding_ctx, fake_openai):
    client = EmbeddingClient(embedding_ctx, client=fake_openai)
    # `unlisted` is not in the capability table; without the override this raises
    # UnknownAlias, which is exactly what Task 1's probe needs to bypass.
    client.embed(["hello"], model="unlisted", truncate=True, max_input_tokens=512)
    assert fake_openai.embeddings.calls[-1][0] == "unlisted"


def test_cache_hits_are_counted(embedding_ctx, fake_openai):
    client = EmbeddingClient(embedding_ctx, client=fake_openai)
    client.embed(["hello"], model="tiny-window")
    client.embed(["hello"], model="tiny-window")
    assert client.cache_hits == 1
```

Add the two fixtures the new tests use to the same module (or to
`tools/pipeline/tests/conftest.py` if one exists — check first and follow whatever the module
already does for its existing tests):

```python
@pytest.fixture
def fake_openai():
    class Embeddings:
        def __init__(self):
            self.calls = []

        def create(self, *, model, input):
            self.calls.append((model, list(input)))

            class Item:
                embedding = [0.1, 0.2, 0.3, 0.4]

            class Response:
                data = [Item() for _ in input]
                usage = type("U", (), {"prompt_tokens": 7})()

            return Response()

    return type("Client", (), {"embeddings": Embeddings()})()


@pytest.fixture
def embedding_ctx(tmp_path):
    from langatlas_pipeline.providers.core import Budget, RunContext
    from langatlas_pipeline.transcripts.events import RunManifest
    from langatlas_pipeline.config import ProviderConfig

    config = ProviderConfig(
        providers={"completion": {"min_interval_seconds": {"embedding": 0.0},
                                  "max_attempts": 1},
                   "transcripts": {"publish": False, "push": False}},
        capabilities={"embeddings": {"tiny-window": {"dimensions": 4,
                                                     "max_input_tokens": 512}}},
        config_dir=tmp_path)
    manifest = RunManifest(run_id="r", kind="test", started="now", budget={})
    ctx = RunContext(run_id="r", kind="test", budget=Budget(), config=config,
                     run_dir=tmp_path / "run", private_dir=tmp_path / "private",
                     manifest=manifest)
    (tmp_path / "run").mkdir(parents=True, exist_ok=True)
    (tmp_path / "private").mkdir(parents=True, exist_ok=True)
    yield ctx
    ctx.close(publish=False)
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/pipeline run pytest tests/test_embedding_rerank.py -v -k "truncat or cache_hits or window"`
Expected: FAIL — `ImportError: cannot import name 'truncate_to_tokens'`.

- [x] **Step 3: Implement truncation and the counters**

In `tools/pipeline/src/langatlas_pipeline/providers/completion.py`, after `estimate_tokens`:

```python
def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Shorten `text` until `estimate_tokens` puts it inside `max_tokens`, as a prefix.

    Deliberately built on `estimate_tokens` rather than a real tokenizer: it is the
    same conservative bound the refuse-or-proceed check uses, so a text this function
    returns can never be rejected by the check that follows it. Shaving 5% at a time
    converges in a handful of passes for any realistic input and never overshoots into
    a needlessly short prefix the way a single chars/4 division would.
    """
    if estimate_tokens([{"content": text}]) <= max_tokens:
        return text
    # First cut analytically, then shave — the analytic cut lands close, the loop makes
    # it correct.
    cut = max(1, int(len(text) * max_tokens / max(1, estimate_tokens([{"content": text}]))))
    shortened = text[:cut]
    while shortened and estimate_tokens([{"content": shortened}]) > max_tokens:
        shortened = shortened[:max(1, int(len(shortened) * 0.95))]
    return shortened
```

In `tools/pipeline/src/langatlas_pipeline/providers/embedding.py`, extend the class. Add
`truncate_to_tokens` to the existing `from ...completion import` line, initialise the two
counters in `__init__` (`self.truncated = 0`, `self.cache_hits = 0`), and replace `embed`'s
signature and its per-text loop:

```python
    def embed(self, texts: list[str], *, model: str, truncate: bool = False,
              max_input_tokens: int | None = None) -> list[list[float]]:
        """`truncate` is off by default: the wrapper never silently shortens production
        text, because a claim verified against a half-read chunk is worse than a refused
        call. §8.6's benchmark turns it on deliberately, so a 512-token candidate is
        measured on exactly the input production would give it — and `self.truncated`
        makes the cost of that visible in the arm's result rather than invisible.

        `max_input_tokens` overrides the capability table for a model the table does not
        list yet (Task 1's probe). Nothing in the benchmark passes it.
        """
        window = max_input_tokens
        if window is None:
            window = self.ctx.config.embedding(model).max_input_tokens
        vectors: dict[int, list[float]] = {}
        pending: list[tuple[int, str, str]] = []
        cache_hits = 0

        for index, text in enumerate(texts):
            if estimate_tokens([{"content": text}]) > window:
                if not truncate:
                    raise ContextTooLarge(model, estimate_tokens([{"content": text}]),
                                          window)
                text = truncate_to_tokens(text, window)
                self.truncated += 1
            key = cache_key(endpoint="embeddings", resolved_model=model,
                            messages=[{"role": "user", "content": text}], sampling={},
                            schema_name=None, prompt_ref=None)
            hit = self.ctx.cache.get(key) if self.ctx.cache is not None else None
            if hit is not None:
                vectors[index] = hit["vector"]
                cache_hits += 1
            else:
                pending.append((index, text, key))

        self.cache_hits += cache_hits
```

Everything below that line in `embed` — the `if cache_hits:` aggregate record and the batch loop
— stays exactly as it is.

In `tools/pipeline/src/langatlas_pipeline/providers/core.py`, replace `RunContext.embed` and add
the two properties beside it:

```python
    def embed(self, texts: list[str], *, model: str, truncate: bool = False,
              max_input_tokens: int | None = None) -> list[list[float]]:
        from langatlas_pipeline.providers.embedding import EmbeddingClient

        if self._embedding is None:
            self._embedding = EmbeddingClient(self)
        return self._embedding.embed(texts, model=model, truncate=truncate,
                                     max_input_tokens=max_input_tokens)

    @property
    def embedding_truncations(self) -> int:
        """How many texts this run shortened to fit a short-context model. §8.6's
        benchmark reports it per arm; a production run reading a non-zero number here has
        a configuration problem, not a metric."""
        return self._embedding.truncated if self._embedding is not None else 0

    @property
    def embedding_cache_hits(self) -> int:
        """Vectors served from the content-addressed cache. Indexing throughput measured
        over a warm cache is not throughput, so the benchmark reports this alongside it
        rather than quietly dividing by a wall time that includes no provider work."""
        return self._embedding.cache_hits if self._embedding is not None else 0
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv --directory tools/pipeline run pytest tests/test_embedding_rerank.py -v`
Expected: PASS — the six new tests plus every pre-existing test in the module.

- [x] **Step 5: Run the whole pipeline suite for regressions**

Run: `uv --directory tools/pipeline run pytest`
Expected: PASS. `EmbeddingClient.embed`'s new parameters are keyword-only with defaults, so
`langatlas_ingest.embed.embed_source`'s existing call site is unaffected.

- [x] **Step 6: Commit**

```bash
git add tools/pipeline/src/langatlas_pipeline/providers/completion.py \
        tools/pipeline/src/langatlas_pipeline/providers/embedding.py \
        tools/pipeline/src/langatlas_pipeline/providers/core.py \
        tools/pipeline/tests/test_embedding_rerank.py \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): test short-context embedding models honestly"
```

---

## Task 3: Local-CPU embedding backend

§8.6 requires "one local-CPU fastembed representative as the 'does free-and-local suffice'
floor", and §8.6's decision rule gives a local model a *privileged* path to winning (matched
within 2 points beats the incumbent outright). There is no local path today: `ctx.embed` always
goes to the university gateway.

The representative is **`BAAI/bge-small-en-v1.5`** (384-dim, 512-token window) — fastembed's
default model, small enough to run on CPU without a GPU (a hard developer constraint), and short
enough that Task 2's honest truncation is exercised on the local arm too.

Local models are addressed by a `local:` prefix, so a model id stays a plain configuration
string everywhere: `embedding_table_name("local:BAAI/bge-small-en-v1.5")` →
`source_chunk_emb_local_baai_bge_small_en_v1_5`, and `config/ingest.yaml`'s `models.embedding`
could name it verbatim if the verdict picks it.

**Files:**
- Create: `tools/pipeline/src/langatlas_pipeline/providers/local_embedding.py`
- Create: `tools/pipeline/tests/test_local_embedding.py`
- Modify: `tools/pipeline/src/langatlas_pipeline/config.py`
- Modify: `tools/pipeline/src/langatlas_pipeline/providers/core.py`
- Modify: `tools/pipeline/pyproject.toml`
- Modify: `config/provider_capabilities.yaml`

**Interfaces:**
- Consumes: `ctx.config.embedding(model)`, `ctx.cache`, `ctx.recorder.record_call`,
  `ctx.check_budget`, `ctx.note_usage`, `cache_key`, `truncate_to_tokens`, `estimate_tokens`.
- Produces:
  ```python
  LOCAL_PREFIX = "local:"
  def is_local(model: str) -> bool
  def local_model_name(model: str) -> str          # strips the prefix

  class LocalEmbeddingClient:
      truncated: int
      cache_hits: int
      def __init__(self, ctx, *, encoder=None, batch_size: int = 64)
      def embed(self, texts, *, model, truncate: bool = False,
                max_input_tokens: int | None = None) -> list[list[float]]
  ```
  `ProviderConfig.embedding(model)` now resolves ids in both the `embeddings:` and
  `local_embeddings:` blocks and returns the same `EmbeddingCapability`.

- [x] **Step 1: Write the failing tests**

Create `tools/pipeline/tests/test_local_embedding.py`:

```python
import pytest
from langatlas_pipeline.config import ProviderConfig
from langatlas_pipeline.errors import UnknownAlias
from langatlas_pipeline.providers.local_embedding import (
    LOCAL_PREFIX, LocalEmbeddingClient, is_local, local_model_name,
)

MODEL = LOCAL_PREFIX + "BAAI/bge-small-en-v1.5"


class _FakeEncoder:
    """Stands in for fastembed's TextEmbedding: same duck type (`embed(iterable)` ->
    an iterable of vectors), so the tests never need the real package or its download."""

    def __init__(self, dimensions=4):
        self.dimensions = dimensions
        self.seen = []

    def embed(self, texts):
        texts = list(texts)
        self.seen.extend(texts)
        return [[float(len(text) % 10)] + [0.0] * (self.dimensions - 1) for text in texts]


def test_is_local_recognises_the_prefix():
    assert is_local(MODEL) is True
    assert is_local("qwen3-embedding-4b") is False
    assert local_model_name(MODEL) == "BAAI/bge-small-en-v1.5"


def test_config_resolves_a_local_model(tmp_path):
    config = ProviderConfig(
        providers={}, config_dir=tmp_path,
        capabilities={"embeddings": {"remote": {"dimensions": 8, "max_input_tokens": 99}},
                      "local_embeddings": {MODEL: {"dimensions": 384,
                                                   "max_input_tokens": 512}}})
    cap = config.embedding(MODEL)
    assert (cap.model, cap.dimensions, cap.max_input_tokens) == (MODEL, 384, 512)
    assert config.embedding("remote").dimensions == 8
    with pytest.raises(UnknownAlias):
        config.embedding("nope")


def test_local_client_embeds_and_logs(local_ctx):
    encoder = _FakeEncoder()
    client = LocalEmbeddingClient(local_ctx, encoder=encoder)
    vectors = client.embed(["alpha", "beta"], model=MODEL)
    assert len(vectors) == 2 and len(vectors[0]) == 4
    assert encoder.seen == ["alpha", "beta"]
    # D18: a local call costs nothing but is still a call the run made.
    assert [c["endpoint"] for c in local_ctx.recorder.calls] == ["embeddings"]
    assert local_ctx.recorder.calls[0]["tokens_in"] > 0


def test_local_client_truncates_when_asked(local_ctx):
    encoder = _FakeEncoder()
    client = LocalEmbeddingClient(local_ctx, encoder=encoder)
    client.embed(["word " * 5000], model=MODEL, truncate=True)
    assert client.truncated == 1
    assert len(encoder.seen[0]) < len("word " * 5000)


def test_local_client_refuses_an_oversized_text_by_default(local_ctx):
    from langatlas_pipeline.errors import ContextTooLarge

    client = LocalEmbeddingClient(local_ctx, encoder=_FakeEncoder())
    with pytest.raises(ContextTooLarge):
        client.embed(["word " * 5000], model=MODEL)


def test_local_client_reuses_the_cache(local_ctx):
    encoder = _FakeEncoder()
    client = LocalEmbeddingClient(local_ctx, encoder=encoder)
    client.embed(["alpha"], model=MODEL)
    client.embed(["alpha"], model=MODEL)
    assert encoder.seen == ["alpha"]           # second call served from cache
    assert client.cache_hits == 1


def test_run_context_dispatches_local_models(local_ctx, monkeypatch):
    encoder = _FakeEncoder()
    monkeypatch.setattr(
        "langatlas_pipeline.providers.local_embedding.build_encoder",
        lambda name: encoder)
    vectors = local_ctx.embed(["alpha"], model=MODEL)
    assert len(vectors[0]) == 4
    assert encoder.seen == ["alpha"]
    assert local_ctx.embedding_cache_hits == 0
```

Add the `local_ctx` fixture to the same module — it is `embedding_ctx` from Task 2 with a
`local_embeddings:` capability block and a real `CallCache` (the cache test needs one):

```python
@pytest.fixture
def local_ctx(tmp_path):
    from langatlas_pipeline.providers.core import Budget, RunContext
    from langatlas_pipeline.transcripts.events import RunManifest

    config = ProviderConfig(
        providers={"completion": {"min_interval_seconds": {"embedding": 0.0},
                                  "max_attempts": 1},
                   "transcripts": {"publish": False, "push": False}},
        capabilities={"local_embeddings": {MODEL: {"dimensions": 4,
                                                   "max_input_tokens": 512}}},
        config_dir=tmp_path)
    manifest = RunManifest(run_id="r", kind="test", started="now", budget={})
    (tmp_path / "run").mkdir(parents=True, exist_ok=True)
    (tmp_path / "private").mkdir(parents=True, exist_ok=True)
    ctx = RunContext(run_id="r", kind="test", budget=Budget(), config=config,
                     run_dir=tmp_path / "run", private_dir=tmp_path / "private",
                     manifest=manifest)
    yield ctx
    ctx.close(publish=False)
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/pipeline run pytest tests/test_local_embedding.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_pipeline.providers.local_embedding'`.

- [x] **Step 3: Implement the local backend**

Create `tools/pipeline/src/langatlas_pipeline/providers/local_embedding.py`:

```python
import time
from langatlas_pipeline.cache import cache_key
from langatlas_pipeline.errors import ContextTooLarge
from langatlas_pipeline.providers.completion import estimate_tokens, truncate_to_tokens

# `local:` rather than a separate config key, so a local model id stays an ordinary
# string everywhere else: config/ingest.yaml's `models.embedding`, the per-model
# embedding table name, an arm id, a verdict record. One namespace, one lookup.
LOCAL_PREFIX = "local:"


def is_local(model: str) -> bool:
    return model.startswith(LOCAL_PREFIX)


def local_model_name(model: str) -> str:
    return model[len(LOCAL_PREFIX):]


def build_encoder(name: str):
    """Imported lazily and behind an optional extra: `fastembed` pulls onnxruntime and a
    model download, and nothing outside §8.6's local-floor arm needs either. A developer
    who never runs that arm should never have to install it."""
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:        # pragma: no cover - exercised by the install path
        raise ImportError(
            "the local embedding arm needs the `local-embed` extra:"
            " `uv --directory tools/pipeline sync --extra local-embed`") from exc
    return TextEmbedding(model_name=name)


class LocalEmbeddingClient:
    """§8.6's free-and-local floor. Deliberately the same shape as `EmbeddingClient`:
    same cache keys, same recorder events, same truncation contract, same counters — so
    a benchmark arm cannot accidentally measure a local model on a different code path
    than a remote one, and D18's "every call is logged" holds for calls that cost
    nothing.

    Budget: a local batch is counted as a call. It buys no API quota, but the budget is
    also a runaway-loop stop-loss, and a run that embeds the corpus twice by mistake
    should hit a cap whichever backend it used.
    """

    def __init__(self, ctx, *, encoder=None, batch_size: int = 64):
        self.ctx = ctx
        self._encoder = encoder
        self._encoder_name: str | None = None
        self.batch_size = batch_size
        self.truncated = 0
        self.cache_hits = 0

    def encoder(self, model: str):
        name = local_model_name(model)
        if self._encoder is None:
            self._encoder = build_encoder(name)
            self._encoder_name = name
        elif self._encoder_name is not None and self._encoder_name != name:
            # Mirrors D26's alias pinning: one client, one model, for the life of a run.
            raise ValueError(f"local encoder pinned to {self._encoder_name!r},"
                             f" refusing to serve {name!r}")
        return self._encoder

    def embed(self, texts: list[str], *, model: str, truncate: bool = False,
              max_input_tokens: int | None = None) -> list[list[float]]:
        window = max_input_tokens
        if window is None:
            window = self.ctx.config.embedding(model).max_input_tokens
        vectors: dict[int, list[float]] = {}
        pending: list[tuple[int, str, str]] = []
        cache_hits = 0

        for index, text in enumerate(texts):
            if estimate_tokens([{"content": text}]) > window:
                if not truncate:
                    raise ContextTooLarge(model, estimate_tokens([{"content": text}]),
                                          window)
                text = truncate_to_tokens(text, window)
                self.truncated += 1
            key = cache_key(endpoint="embeddings", resolved_model=model,
                            messages=[{"role": "user", "content": text}], sampling={},
                            schema_name=None, prompt_ref=None)
            hit = self.ctx.cache.get(key) if self.ctx.cache is not None else None
            if hit is not None:
                vectors[index] = hit["vector"]
                cache_hits += 1
            else:
                pending.append((index, text, key))

        self.cache_hits += cache_hits
        if cache_hits:
            self.ctx.recorder.record_call(
                endpoint="embeddings", alias=model, resolved_model=model, messages=[],
                response_text=None, tokens_in=0, tokens_out=0, latency_ms=0,
                cache_hit=True, outcome="ok",
                tool_call={"name": "embed-local",
                           "args": {"n": cache_hits, "model": model}})

        encoder = self.encoder(model) if pending else None
        for start in range(0, len(pending), self.batch_size):
            batch = pending[start:start + self.batch_size]
            self.ctx.check_budget(calls=1)
            began = time.monotonic()
            produced = list(encoder.embed([text for _, text, _ in batch]))
            latency_ms = int((time.monotonic() - began) * 1000)
            tokens_in = estimate_tokens([{"content": text} for _, text, _ in batch])
            for (index, _, key), vector in zip(batch, produced, strict=True):
                vectors[index] = [float(value) for value in vector]
                if self.ctx.cache is not None:
                    self.ctx.cache.put(key, {"vector": vectors[index]})
            self.ctx.note_usage(calls=1, tokens=tokens_in)
            self.ctx.recorder.record_call(
                endpoint="embeddings", alias=model, resolved_model=model, messages=[],
                response_text=None, tokens_in=tokens_in, tokens_out=0,
                latency_ms=latency_ms, cache_hit=False, outcome="ok",
                tool_call={"name": "embed-local",
                           "args": {"n": len(batch), "model": model}})

        return [vectors[index] for index in range(len(texts))]
```

In `tools/pipeline/src/langatlas_pipeline/config.py`, replace `ProviderConfig.embedding`:

```python
    def embedding(self, model: str) -> EmbeddingCapability:
        """One lookup across both rosters. A `local:`-prefixed id lives under
        `local_embeddings:` because it is not something the gateway probe can measure —
        but every consumer (the embed table, the search query, an arm id) treats the two
        identically, so they return the same type."""
        entry = (self.capabilities.get("embeddings", {}).get(model)
                 or self.capabilities.get("local_embeddings", {}).get(model))
        if entry is None:
            raise UnknownAlias(f"unknown embedding model: {model!r}")
        return EmbeddingCapability(model, int(entry["dimensions"]),
                                   int(entry["max_input_tokens"]))
```

In `tools/pipeline/src/langatlas_pipeline/providers/core.py`, add `self._local_embedding = None`
beside the other channel slots in `__init__`, and dispatch in `embed`:

```python
    def embed(self, texts: list[str], *, model: str, truncate: bool = False,
              max_input_tokens: int | None = None) -> list[list[float]]:
        from langatlas_pipeline.providers.local_embedding import (
            LocalEmbeddingClient, is_local,
        )

        if is_local(model):
            if self._local_embedding is None:
                self._local_embedding = LocalEmbeddingClient(self)
            return self._local_embedding.embed(texts, model=model, truncate=truncate,
                                               max_input_tokens=max_input_tokens)

        from langatlas_pipeline.providers.embedding import EmbeddingClient

        if self._embedding is None:
            self._embedding = EmbeddingClient(self)
        return self._embedding.embed(texts, model=model, truncate=truncate,
                                     max_input_tokens=max_input_tokens)
```

and make the two counter properties sum both backends:

```python
    @property
    def embedding_truncations(self) -> int:
        return sum(client.truncated for client
                   in (self._embedding, self._local_embedding) if client is not None)

    @property
    def embedding_cache_hits(self) -> int:
        return sum(client.cache_hits for client
                   in (self._embedding, self._local_embedding) if client is not None)
```

In `tools/pipeline/pyproject.toml`, under `[project.optional-dependencies]`:

```toml
# §8.6's local-CPU floor arm only. Pulls onnxruntime and downloads a model on first use,
# so it stays out of the default install: nothing in the production pipeline embeds
# locally unless the D22 verdict says so.
local-embed = ["fastembed>=0.4,<0.8"]
```

In `config/provider_capabilities.yaml`, after the `embeddings:` block:

```yaml
# Local-CPU candidates (§8.6's free-and-local floor). Not probeable through the gateway:
# these numbers come from the model card and are checked at first use — `embed_source`
# passes the measured vector length to `ensure_embedding_table`, which refuses a table
# whose dimension disagrees.
local_embeddings:
  local:BAAI/bge-small-en-v1.5: {dimensions: 384, max_input_tokens: 512}
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv --directory tools/pipeline run pytest tests/test_local_embedding.py -v`
Expected: PASS (7 tests).

- [x] **Step 5: Verify the dimension claim against the real encoder (developer checkpoint)**

```bash
uv --directory tools/pipeline sync --extra local-embed
uv --directory tools/pipeline run python -c "
from langatlas_pipeline.providers.local_embedding import build_encoder
v = list(build_encoder('BAAI/bge-small-en-v1.5').embed(['probe']))[0]
print('dimensions', len(v))"
```

Expected: `dimensions 384`. If it prints anything else, correct
`config/provider_capabilities.yaml` to the measured value before committing — the recorded number
must be the one the encoder actually produces.

- [x] **Step 6: Run both suites for regressions**

Run: `uv --directory tools/pipeline run pytest && uv --directory tools/ingest run pytest`
Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add tools/pipeline/src/langatlas_pipeline/providers/local_embedding.py \
        tools/pipeline/src/langatlas_pipeline/providers/core.py \
        tools/pipeline/src/langatlas_pipeline/config.py \
        tools/pipeline/pyproject.toml tools/pipeline/uv.lock \
        tools/pipeline/tests/test_local_embedding.py \
        config/provider_capabilities.yaml \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): add the local-CPU fastembed floor candidate"
```

---

## Task 4: The retrieval `mode` axis

§8.6's first variant axis is "vector-only vs hybrid+RRF vs hybrid+reranker". `SourceSearch`
always fuses both branches, so the vector-only arm cannot be measured today. This task adds a
`mode` axis and makes it configurable — because if the verdict picks vector-only, production has
to be able to *be* vector-only without a code change.

`fts` is included as a third mode. §8.6 does not ask for a lexical-only arm, but it is free (the
same code path, no embedding call at all) and it is the honest denominator for "what does the
vector branch actually add" — the same question the 2-point hybrid rule is asking from the other
side. It is a reported arm, never a candidate for the verdict.

**Files:**
- Modify: `tools/ingest/src/langatlas_ingest/search.py`
- Modify: `tools/ingest/src/langatlas_ingest/errors.py`
- Modify: `tools/ingest/src/langatlas_ingest/config.py`
- Modify: `config/ingest.yaml`
- Modify: `tools/ingest/src/langatlas_ingest/cli.py` (`search` gets `--mode`)
- Test: `tools/ingest/tests/test_search.py` (extend)

**Interfaces:**
- Consumes: `IngestConfig`, `embedding_table_name`, `embedding_dimensions`, `SourceChunksStore`.
- Produces:
  ```python
  SEARCH_MODES = ("hybrid", "vector", "fts")

  class SourceSearch:
      def __init__(self, conn, ctx, *, config=None, rerank=None, mode: str | None = None)
      self.mode: str          # resolved: explicit argument, else config.retrieval_mode

  class UnknownSearchMode(IngestError):
      def __init__(self, mode: str)

  # IngestConfig gains:
  retrieval_mode: str
  embedding_dimensions: int | None
  index_type: str
  ```

- [x] **Step 1: Write the failing tests**

Append to `tools/ingest/tests/test_search.py`:

```python
import pytest
from langatlas_ingest.errors import UnknownSearchMode
from langatlas_ingest.search import SEARCH_MODES, SourceSearch


def test_unknown_mode_is_rejected_at_construction(searchable, fake_ctx):
    with pytest.raises(UnknownSearchMode):
        SourceSearch(searchable, fake_ctx, config=CONFIG, mode="semantic-ish")


def test_vector_mode_drops_the_fts_branch(searchable, fake_ctx):
    search = SourceSearch(searchable, fake_ctx, config=CONFIG, mode="vector",
                          rerank=False)
    sql, params = search.build_query("anything", vector="[0,0,0,0]", k=5,
                                     source_ids=None)
    assert "plainto_tsquery" not in sql
    assert "vec.rank" in sql
    assert "query" not in params        # no lexical parameter is bound


def test_fts_mode_drops_the_vector_branch_and_never_embeds(searchable, fake_ctx):
    search = SourceSearch(searchable, fake_ctx, config=CONFIG, mode="fts", rerank=False)
    before = len(fake_ctx.embed_calls)  # the `searchable` fixture embeds the corpus
    hits = search.search("lazy evaluation", k=5)
    assert len(fake_ctx.embed_calls) == before   # no embedding round trip for the query
    sql, _ = search.build_query("boolean", vector="", k=5, source_ids=None)
    assert "halfvec" not in sql
    assert isinstance(hits, list)


def test_hybrid_stays_the_default(searchable, fake_ctx):
    assert SourceSearch(searchable, fake_ctx, config=CONFIG).mode == "hybrid"
    assert set(SEARCH_MODES) == {"hybrid", "vector", "fts"}


def test_mode_comes_from_config_when_unset(searchable, fake_ctx):
    from dataclasses import replace

    assert SourceSearch(searchable, fake_ctx,
                        config=replace(CONFIG, retrieval_mode="vector")).mode == "vector"


def test_config_exposes_the_pinned_index_identity():
    from langatlas_ingest.config import IngestConfig

    config = IngestConfig.load()
    assert config.retrieval_mode in SEARCH_MODES
    assert config.index_type == "hnsw-halfvec-cosine"
    assert config.embedding_dimensions == 2560
```

> These reuse the module's existing `searchable` fixture (two sources, `s` and `t`, chunked,
> stored and embedded through `fake_ctx`) and its module-level `CONFIG`. Do not add a second
> seeding fixture. `CONFIG` must gain the new `retrieval_mode` field — it is built by
> `IngestConfig(...)` at the top of the module, so add `retrieval_mode="hybrid"`,
> `embedding_dimensions=4`, `index_type="hnsw-halfvec-cosine"` to that constructor call in the
> same step, or every test in the module fails on a missing argument.

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/ingest run pytest tests/test_search.py -v -m db -k "mode or index_identity"`
Expected: FAIL — `ImportError: cannot import name 'SEARCH_MODES'`.

- [x] **Step 3: Implement the mode axis**

In `tools/ingest/src/langatlas_ingest/errors.py`:

```python
class UnknownSearchMode(IngestError):
    """§8.6's retrieval variant axis is a closed set. Typed and raised at construction
    rather than producing an empty result set, because a silently-wrong mode in a
    benchmark arm would be recorded as a real measurement."""

    def __init__(self, mode: str):
        from langatlas_ingest.search import SEARCH_MODES

        super().__init__(f"unknown search mode {mode!r}; expected one of"
                         f" {', '.join(SEARCH_MODES)}")
        self.mode = mode
```

In `tools/ingest/src/langatlas_ingest/search.py`, add the constant and rework `__init__`,
`build_query` and `search`:

```python
# §8.6's first variant axis. `fts` is not a verdict candidate — it is the lexical-only
# denominator that makes "what does the vector branch add" answerable from both sides.
SEARCH_MODES = ("hybrid", "vector", "fts")


    def __init__(self, conn, ctx, *, config: IngestConfig | None = None,
                 rerank: bool | None = None, mode: str | None = None):
        from langatlas_ingest.errors import UnknownSearchMode

        self.conn = conn
        self.ctx = ctx
        self.config = config or IngestConfig.load()
        self.mode = self.config.retrieval_mode if mode is None else mode
        if self.mode not in SEARCH_MODES:
            raise UnknownSearchMode(self.mode)
        self.rerank = self.config.rerank_default_on if rerank is None else rerank
        self.store = SourceChunksStore(conn)
```

`build_query` keeps its existing docstring and its existing `fts`/`vec` subquery text verbatim;
the change is that each branch is now emitted conditionally, and the fused select adapts:

```python
    def build_query(self, query: str, *, vector: str, k: int,
                    source_ids: Sequence[str] | None) -> tuple[str, dict]:
        """(existing docstring, unchanged)

        `mode` selects which branches are emitted. The RRF score expression keeps its
        shape in every mode — a single-branch score is `1/(rrf_k + rank)`, which is the
        same monotone function of rank the fused score uses, so `relevance_floor` and
        every recorded score stay comparable across arms.
        """
        candidates = max(int(self.config.retrieval_candidates), int(k))
        filter_sql = " AND c.source_id = ANY(%(sources)s)" if source_ids else ""
        params: dict = {"rrf_k": self.config.rrf_k,
                        "sources": list(source_ids) if source_ids else []}
        ctes, joins, score_terms, presence = [], [], [], []

        if self.mode in ("hybrid", "fts"):
            params["query"] = query
            ctes.append(f"""fts AS (
            SELECT chunk_id, row_number() OVER (ORDER BY lexical DESC, chunk_id) AS rank
            FROM (
                SELECT c.chunk_id, ts_rank_cd(c.tsv, q.query) AS lexical
                FROM source_chunks c, plainto_tsquery('english', %(query)s) AS q(query)
                WHERE c.tsv @@ q.query{filter_sql}
                ORDER BY lexical DESC, c.chunk_id
                LIMIT {int(candidates)}
            ) ranked
        )""")
            joins.append("LEFT JOIN fts ON fts.chunk_id = c.chunk_id")
            score_terms.append("COALESCE(1.0 / (%(rrf_k)s + fts.rank), 0)")
            presence.append("fts.chunk_id IS NOT NULL")

        if self.mode in ("hybrid", "vector"):
            table = embedding_table_name(self.config.embedding_model)
            dimensions = embedding_dimensions(self.conn, table)
            if dimensions <= 0:
                raise MissingEmbeddingTable(self.config.embedding_model, table)
            params["vector"] = vector
            distance = (f"e.embedding::halfvec({dimensions})"
                        f" <=> %(vector)s::halfvec({dimensions})")
            vec_filter = ("\n                WHERE e.chunk_id IN (SELECT chunk_id FROM"
                          " source_chunks WHERE source_id = ANY(%(sources)s))"
                          if source_ids else "")
            ctes.append(f"""vec AS (
            SELECT chunk_id, row_number() OVER (ORDER BY distance, chunk_id) AS rank
            FROM (
                SELECT e.chunk_id, {distance} AS distance
                FROM {table} e{vec_filter}
                ORDER BY {distance}
                LIMIT {int(candidates)}
            ) ranked
        )""")
            joins.append("LEFT JOIN vec ON vec.chunk_id = c.chunk_id")
            score_terms.append("COALESCE(1.0 / (%(rrf_k)s + vec.rank), 0)")
            presence.append("vec.chunk_id IS NOT NULL")

        rank_columns = ", ".join(
            ("fts.rank" if "fts" in cte.split(" AS ")[0] else "vec.rank")
            for cte in ctes)
        sql = f"""
        WITH {', '.join(ctes)}
        SELECT {_CHUNK_COLUMNS}, {rank_columns},
               {' + '.join(score_terms)} AS score
        FROM source_chunks c
        {' '.join(joins)}
        WHERE {' OR '.join(presence)}
        ORDER BY score DESC, c.chunk_id
        LIMIT {int(candidates)}
        """
        return sql, params
```

`search()` must stop embedding in `fts` mode and unpack the variable number of rank columns:

```python
    def search(self, query: str, *, k: int | None = None,
               source_ids: Sequence[str] | None = None) -> list[SearchHit]:
        k = self.config.retrieval_k if k is None else int(k)
        if k <= 0:
            return []
        # An `fts` arm must cost zero embedding calls — otherwise the lexical-only
        # denominator is quietly paying the price of the branch it is there to isolate.
        vector = ""
        if self.mode in ("hybrid", "vector"):
            vector = vector_literal(
                self.ctx.embed([query], model=self.config.embedding_model)[0])
        sql, params = self.build_query(query, vector=vector, k=k, source_ids=source_ids)
        with self.conn.cursor() as cur:
            if self.mode in ("hybrid", "vector"):
                self.tune_ef_search(cur, k=k)
            cur.execute(sql, params)
            rows = cur.fetchall()

        width = len(_COLUMNS)
        hits = []
        for row in rows:
            chunk = SourceChunk(**dict(zip(_COLUMNS, row[:width])))
            if self.mode == "hybrid":
                fts_rank, vector_rank, score = row[width], row[width + 1], row[width + 2]
            elif self.mode == "fts":
                fts_rank, vector_rank, score = row[width], None, row[width + 1]
            else:
                fts_rank, vector_rank, score = None, row[width], row[width + 1]
            hits.append(SearchHit(chunk=chunk, fts_rank=fts_rank,
                                  vector_rank=vector_rank, score=float(score)))
        hits = [hit for hit in hits if hit.score >= self.config.relevance_floor]
        if self.rerank and hits:
            depth = max(int(self.config.rerank_candidates), k)
            hits = self._rerank(query, hits[:depth]) + hits[depth:]
        return hits[:k]
```

In `config/ingest.yaml`, extend the two blocks:

```yaml
models:
  embedding: qwen3-embedding-4b     # D15 incumbent for the source corpus until D22 says otherwise
  # Pinned by the D22 verdict (§8.6 asks for model *and* dimension *and* index type on
  # the record). These are documentation of the ratified choice; the authority at runtime
  # is still `provider_capabilities.yaml` for the dimension and `ensure_embedding_table`
  # for the index, and `bench-verdict --write` checks all three agree.
  embedding_dimensions: 2560
  index_type: hnsw-halfvec-cosine
  reranker: qwen3-reranker-4b
  rerank_default_on: true           # D15 ratified: reranker default-on
retrieval:
  # §8.6's variant axis, pinned by the D22 verdict: hybrid | vector | fts.
  mode: hybrid
  k: 5                              # §8.1
```

In `tools/ingest/src/langatlas_ingest/config.py`, add the three fields to the dataclass (after
`rerank_default_on` / `relevance_floor` respectively) and to `load()`:

```python
    retrieval_mode: str
    embedding_dimensions: int | None
    index_type: str
```
```python
            retrieval_mode=retrieval.get("mode", "hybrid"),
            embedding_dimensions=(int(models["embedding_dimensions"])
                                  if models.get("embedding_dimensions") else None),
            index_type=models.get("index_type", "hnsw-halfvec-cosine"),
```

In `tools/ingest/src/langatlas_ingest/cli.py`, thread the flag through `_cmd_search`
(`SourceSearch(conn, ctx, config=config, rerank=rerank, mode=args.mode)`) and register it:

```python
    search.add_argument("--mode", choices=list(SEARCH_MODES), default=None,
                        help="override `retrieval.mode`; the §8.6 variant axis")
```

with `from langatlas_ingest.search import SEARCH_MODES` imported inside `build_parser` (the
module keeps its heavy imports inside the command functions; `SEARCH_MODES` is a plain tuple, so
importing it at parser-build time costs a module load that `_cmd_search` would do anyway).

- [x] **Step 4: Run the tests to verify they pass**

Run: `docker compose up -d db && uv --directory tools/ingest run pytest tests/test_search.py -v -m db`
Expected: PASS — the new tests plus every existing search test (the hybrid path must be
byte-for-byte equivalent in behaviour; if an existing EXPLAIN assertion breaks, the emitted SQL
drifted and the branch text must be restored verbatim).

- [x] **Step 5: Run the whole ingest suite**

Run: `uv --directory tools/ingest run pytest && uv --directory tools/ingest run pytest -m db`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add tools/ingest/src/langatlas_ingest/search.py \
        tools/ingest/src/langatlas_ingest/errors.py \
        tools/ingest/src/langatlas_ingest/config.py \
        tools/ingest/src/langatlas_ingest/cli.py \
        tools/ingest/tests/test_search.py config/ingest.yaml \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): make the retrieval mode a configured axis"
```

---

## Task 5: `run_eval` — depth, Recall@50, corpus scoping, injectable relevance

`EvalResult` carries Recall@5, MRR, nDCG@10 and latency. §8.6 also asks for **Recall@50
pre-rerank**, and the benchmark needs three more things `run_eval` cannot do:

- **Recall@50 pre-rerank** is not a new retrieval path: it is a no-rerank run at `k=50`, which
  *is* the fused pool before the reranker sees it. So `depth` is all that is needed.
- **Corpus scoping.** The pilot holds 4 of the golden set's 12 sources; the other 15 queries
  cannot be answered from it. Scoring them as misses would measure the pilot's size, not the
  model. They are **skipped and counted**, never silently dropped and never counted as zero.
- **An injectable relevance predicate**, so Task 9's chunk-size arms can score against spans
  instead of chunk ids, and **an injectable `SourceSearch`**, so an arm builds one search object
  with its own model/mode instead of `run_eval` re-deriving it from config.

**Files:**
- Modify: `tools/ingest/src/langatlas_ingest/eval.py`
- Modify: `tools/ingest/src/langatlas_ingest/cli.py` (`eval` gets `--depth` and `--mode`)
- Test: `tools/ingest/tests/test_eval_metrics.py` and `tools/ingest/tests/test_eval.py` (extend)

**Interfaces:**
- Consumes: `SourceSearch`, `IngestConfig`, `GOLDEN_RETRIEVAL_DIR`, `GoldenEntryInvalid`.
- Produces:
  ```python
  @dataclass
  class EvalResult:
      queries: int = 0
      recall_at_5: float | None = None
      mrr: float | None = None
      ndcg_at_10: float | None = None
      recall_at_50: float | None = None        # None unless depth >= 50
      latency_p50_ms: float | None = None
      per_query: list[dict] = field(default_factory=list)
      golden_dir_missing: bool = False
      skipped_queries: int = 0
      def to_markdown(self) -> str
      def as_dict(self) -> dict                # the runner's JSON payload

  def expected_sources_of(entry: dict) -> set[str]
  def load_entries(golden_dir: Path) -> list[dict]      # renamed from `_load`, now public
  def run_eval(conn, ctx, *, golden_dir=None, config=None, rerank=None,
               depth: int = 10, mode: str | None = None,
               corpus_sources: Sequence[str] | None = None,
               relevance: Callable[[dict, SourceChunk], bool] | None = None,
               search: SourceSearch | None = None) -> EvalResult
  ```
  `per_query` entries gain `"skipped": bool` and keep `id`, `band`, `hit_rank`.

- [x] **Step 1: Write the failing tests**

Append to `tools/ingest/tests/test_eval_metrics.py`:

```python
from langatlas_ingest.eval import EvalResult, expected_sources_of, run_eval


def test_expected_sources_reads_both_expectation_kinds():
    assert expected_sources_of({"expected_chunks": ["scott-plp#c00417"]}) == {"scott-plp"}
    assert expected_sources_of({"expected_sources": ["a", "b"]}) == {"a", "b"}


class _StubSearch:
    """Returns a fixed ranked list, so the metric arithmetic is tested without a
    database or a provider — the same posture the existing metric tests take."""

    def __init__(self, hits):
        self.hits = hits
        self.queries = []

    def search(self, query, *, k=None, source_ids=None):
        self.queries.append((query, k))
        return self.hits[:k]


def _hit(chunk_id, source_id):
    from types import SimpleNamespace

    return SimpleNamespace(chunk=SimpleNamespace(chunk_id=chunk_id, source_id=source_id))


def test_recall_at_50_is_reported_only_at_depth_50(tmp_path, fake_ctx):
    (tmp_path / "queries-t.yaml").write_text(
        "queries:\n  - id: q1\n    band: exact-term\n    query: x\n"
        "    expected_chunks: ['s#c2']\n")
    hits = [_hit(f"s#c{i}", "s") for i in range(60)]

    shallow = run_eval(None, fake_ctx, golden_dir=tmp_path, depth=10,
                       search=_StubSearch(hits))
    assert shallow.recall_at_50 is None
    assert shallow.recall_at_5 == 1.0        # s#c2 is rank 3

    deep = run_eval(None, fake_ctx, golden_dir=tmp_path, depth=50,
                    search=_StubSearch(hits))
    assert deep.recall_at_50 == 1.0


def test_a_chunk_outside_the_top_5_but_inside_the_top_50_separates_the_two(tmp_path,
                                                                           fake_ctx):
    (tmp_path / "queries-t.yaml").write_text(
        "queries:\n  - id: q1\n    band: exact-term\n    query: x\n"
        "    expected_chunks: ['s#c40']\n")
    hits = [_hit(f"s#c{i}", "s") for i in range(60)]
    result = run_eval(None, fake_ctx, golden_dir=tmp_path, depth=50,
                      search=_StubSearch(hits))
    assert result.recall_at_5 == 0.0
    assert result.recall_at_50 == 1.0


def test_queries_outside_the_corpus_are_skipped_not_missed(tmp_path, fake_ctx):
    (tmp_path / "queries-t.yaml").write_text(
        "queries:\n"
        "  - id: in\n    band: exact-term\n    query: x\n"
        "    expected_chunks: ['s#c1']\n"
        "  - id: out\n    band: exact-term\n    query: y\n"
        "    expected_chunks: ['other#c1']\n")
    result = run_eval(None, fake_ctx, golden_dir=tmp_path, depth=10,
                      corpus_sources=["s"], search=_StubSearch([_hit("s#c1", "s")]))
    assert result.queries == 1               # only the scorable one counts
    assert result.skipped_queries == 1
    assert result.recall_at_5 == 1.0         # not dragged to 0.5 by an unanswerable query
    assert [entry["skipped"] for entry in result.per_query] == [False, True]


def test_a_survey_query_needs_every_listed_source_present(tmp_path, fake_ctx):
    (tmp_path / "queries-t.yaml").write_text(
        "queries:\n  - id: q\n    band: cross-source-survey\n    query: x\n"
        "    expected_sources: ['s', 'other']\n")
    result = run_eval(None, fake_ctx, golden_dir=tmp_path, depth=10,
                      corpus_sources=["s"], search=_StubSearch([_hit("s#c1", "s")]))
    # Scoring it against a corpus holding half its sources would report a hit rate for a
    # survey that cannot be surveyed.
    assert (result.queries, result.skipped_queries) == (0, 1)


def test_an_injected_relevance_predicate_overrides_chunk_id_matching(tmp_path, fake_ctx):
    (tmp_path / "queries-t.yaml").write_text(
        "queries:\n  - id: q\n    band: exact-term\n    query: x\n"
        "    expected_chunks: ['s#c1']\n")
    # Chunk ids do not match at all; the predicate says the first hit is relevant anyway,
    # which is exactly what a re-chunked corpus needs.
    result = run_eval(None, fake_ctx, golden_dir=tmp_path, depth=10,
                      search=_StubSearch([_hit("s#c999", "s")]),
                      relevance=lambda entry, chunk: chunk.chunk_id == "s#c999")
    assert result.recall_at_5 == 1.0


def test_as_dict_round_trips_every_reported_metric():
    payload = EvalResult(queries=3, recall_at_5=0.5, mrr=0.4, ndcg_at_10=0.6,
                         recall_at_50=0.9, latency_p50_ms=12.0,
                         skipped_queries=2).as_dict()
    assert payload["recall_at_50"] == 0.9
    assert payload["skipped_queries"] == 2
    assert payload["queries"] == 3
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/ingest run pytest tests/test_eval_metrics.py -v`
Expected: FAIL — `ImportError: cannot import name 'expected_sources_of'`.

- [x] **Step 3: Implement**

Rewrite the scoring and driver halves of `tools/ingest/src/langatlas_ingest/eval.py`. `_validate`
and `_relevant` are unchanged; `_load` is renamed `load_entries` (keep a module-level
`_load = load_entries` alias only if something outside this file imports it — check with
`grep -rn "_load" tools/ tests/` first and prefer updating the caller).

```python
# Recall@5 is §8.1's operating k. Recall@50 is §8.6's pre-rerank pool measurement — the
# same number, read at the depth the reranker actually receives.
_RECALL_CUTOFFS = (5, 50)


@dataclass
class EvalResult:
    """Section 8.6's metric set, minus the ones only a multi-model benchmark run needs
    (indexing throughput, storage) — Stage 2C's D22 harness adds those around this."""

    queries: int = 0
    recall_at_5: float | None = None
    mrr: float | None = None
    ndcg_at_10: float | None = None
    # §8.6's pre-rerank pool measurement. None (never 0.0) below depth 50: an unmeasured
    # metric and a measured zero are different findings, and a benchmark table that
    # conflated them would read as a catastrophic arm rather than a shallow run.
    recall_at_50: float | None = None
    latency_p50_ms: float | None = None
    per_query: list[dict] = field(default_factory=list)
    golden_dir_missing: bool = False
    # Queries whose expected sources are not all in the corpus under test. Counted, never
    # scored: a pilot corpus holding 4 of the golden set's 12 sources would otherwise
    # measure its own size instead of the model.
    skipped_queries: int = 0

    def to_markdown(self) -> str:
        if not self.queries:
            if self.golden_dir_missing:
                return ("# Retrieval eval\n\nWARNING: golden directory not found (not "
                        "just empty) — check the path; this looks like a typo or a "
                        "moved directory rather than the genuinely-empty pre-Stage-2 "
                        "state.\n")
            if self.skipped_queries:
                return (f"# Retrieval eval\n\nWARNING: all {self.skipped_queries} golden "
                        "queries were skipped — none of their expected sources are in "
                        "this corpus. Check `corpus_sources`.\n")
            return ("# Retrieval eval\n\nNo golden queries found. Stage 2 authors these "
                    "during the corpus QA skims (Section 8.6).\n")
        recall50 = "n/a" if self.recall_at_50 is None else f"{self.recall_at_50:.3f}"
        return ("# Retrieval eval\n\n"
                f"- queries: {self.queries} (skipped: {self.skipped_queries})\n"
                f"- Recall@5: {self.recall_at_5:.3f}\n"
                f"- Recall@50 (pre-rerank pool): {recall50}\n"
                f"- MRR: {self.mrr:.3f}\n"
                f"- nDCG@10: {self.ndcg_at_10:.3f}\n"
                f"- latency p50: {self.latency_p50_ms:.0f} ms\n")

    def as_dict(self) -> dict:
        """The arm-result payload. Plain JSON types only — a committed benchmark result
        has to stay readable in a diff five years from now."""
        return {"queries": self.queries, "skipped_queries": self.skipped_queries,
                "recall_at_5": self.recall_at_5, "recall_at_50": self.recall_at_50,
                "mrr": self.mrr, "ndcg_at_10": self.ndcg_at_10,
                "latency_p50_ms": self.latency_p50_ms, "per_query": self.per_query}


def load_entries(golden_dir: Path) -> list[dict]:
    entries: list[dict] = []
    for path in sorted(Path(golden_dir).glob("*.yaml")):
        if path.name == "queries.example.yaml":     # format documentation, not data
            continue
        entries.extend((_yaml.load(path.read_text()) or {}).get("queries") or [])
    return entries


def expected_sources_of(entry: dict) -> set[str]:
    """Which sources a query needs present to be answerable at all — the source half of
    every `expected_chunks` id, plus every `expected_sources` entry."""
    return ({chunk_id.split("#", 1)[0] for chunk_id in entry.get("expected_chunks") or []}
            | set(entry.get("expected_sources") or []))
```

`_score` gains the cutoff set and the injectable predicate. Its existing docstring stays; append
the paragraph about `relevant`:

```python
def _score(entry: dict, hits: list, *, relevant) -> tuple[dict, float, float, int | None]:
    """(existing docstring, unchanged)

    `relevant(entry, chunk) -> bool` is injected rather than hardcoded so the chunk-size
    axis can score a re-chunked corpus, where the golden set's chunk ids do not exist by
    construction, against document spans instead (see `benchmark/relevance.py`). The
    default is chunk-id/source-id equality — exactly what it always was.
    """
    flags = [relevant(entry, hit.chunk) for hit in hits]
    expected_chunks = entry.get("expected_chunks")
    recalls: dict[int, float] = {}

    for cutoff in _RECALL_CUTOFFS:
        if cutoff > len(hits) and cutoff != _RECALL_CUTOFFS[0]:
            # Not measured at a depth the run never retrieved to.
            continue
        if expected_chunks:
            found = sum(1 for flag in flags[:cutoff] if flag)
            recalls[cutoff] = min(1.0, found / len(set(expected_chunks)))
        else:
            recalls[cutoff] = 1.0 if any(flags[:cutoff]) else 0.0

    idcg_count = (min(len(set(expected_chunks)), 10) if expected_chunks
                  else min(sum(flags[:10]), 10))
    first = next((index for index, flag in enumerate(flags) if flag), None)
    reciprocal_rank = 1.0 / (first + 1) if first is not None else 0.0
    dcg = sum(1.0 / math.log2(index + 2) for index, flag in enumerate(flags[:10]) if flag)
    ideal = sum(1.0 / math.log2(index + 2) for index in range(idcg_count))
    ndcg = dcg / ideal if ideal else 0.0
    return recalls, reciprocal_rank, ndcg, first
```

> Note the deliberate change inside the `expected_chunks` branch: recall now counts
> *relevant flags* in the window rather than distinct found chunk ids, and clamps at 1.0. With an
> injected span predicate several retrieved chunks can map to one expected chunk, and the old
> `len(found_at_5) / len(relevant_ids)` form would report a fraction above 1.0. Chunk-id equality
> behaves identically to before, because there each flag is a distinct expected id.

```python
def run_eval(conn, ctx, *, golden_dir: Path | None = None,
             config: IngestConfig | None = None, rerank: bool | None = None,
             depth: int = 10, mode: str | None = None,
             corpus_sources: Sequence[str] | None = None,
             relevance=None, search=None) -> EvalResult:
    """`rerank`, `mode` and `depth` are the three §8.6 variant axes, threaded through to
    `SourceSearch` (rerank=None leaves the decision to `models.rerank_default_on`,
    exactly as the CLI's `--no-rerank` opt-out does; mode=None likewise defers to
    `retrieval.mode`). `depth` is the k requested per query: 10 for the ordinary eval,
    50 for §8.6's pre-rerank pool measurement.

    `search` is injectable so a benchmark arm builds one search object with its own
    model and mode instead of this function re-deriving it from config — and so a metric
    test can run with no database at all.
    """
    config = config or IngestConfig.load()
    golden_dir = golden_dir or GOLDEN_RETRIEVAL_DIR
    entries = load_entries(golden_dir)
    for entry in entries:
        _validate(entry)
    if not entries:
        return EvalResult(golden_dir_missing=not Path(golden_dir).is_dir())

    relevant = relevance or _relevant
    available = set(corpus_sources) if corpus_sources is not None else None
    if search is None:
        search = SourceSearch(conn, ctx, config=config, rerank=rerank, mode=mode)

    recalls: dict[int, list[float]] = {cutoff: [] for cutoff in _RECALL_CUTOFFS}
    reciprocals, gains, latencies, per_query = [], [], [], []
    skipped = 0
    for entry in entries:
        if available is not None and not expected_sources_of(entry) <= available:
            skipped += 1
            per_query.append({"id": entry.get("id"), "band": entry.get("band"),
                              "hit_rank": None, "skipped": True})
            continue
        began = time.monotonic()
        hits = search.search(entry["query"], k=depth)
        latencies.append((time.monotonic() - began) * 1000)
        scored, reciprocal_rank, ndcg, first = _score(entry, hits, relevant=relevant)
        for cutoff, value in scored.items():
            recalls[cutoff].append(value)
        reciprocals.append(reciprocal_rank)
        gains.append(ndcg)
        per_query.append({"id": entry.get("id"), "band": entry.get("band"),
                          "hit_rank": None if first is None else first + 1,
                          "skipped": False})

    if not reciprocals:
        return EvalResult(per_query=per_query, skipped_queries=skipped)

    mean = lambda values: sum(values) / len(values)
    return EvalResult(
        queries=len(reciprocals),
        recall_at_5=mean(recalls[5]),
        recall_at_50=mean(recalls[50]) if recalls[50] and depth >= 50 else None,
        mrr=mean(reciprocals), ndcg_at_10=mean(gains),
        latency_p50_ms=sorted(latencies)[len(latencies) // 2],
        per_query=per_query, skipped_queries=skipped)
```

Add `from typing import Sequence` to the imports.

In `tools/ingest/src/langatlas_ingest/cli.py`, extend `_cmd_eval` and its parser:

```python
            result = run_eval(conn, ctx, config=config, rerank=rerank,
                              depth=args.depth, mode=args.mode)
```
```python
    evaluate.add_argument("--depth", type=int, default=10,
                          help="hits requested per query; 50 measures §8.6's pre-rerank"
                               " pool (run it with --no-rerank)")
    evaluate.add_argument("--mode", choices=list(SEARCH_MODES), default=None,
                          help="override `retrieval.mode`")
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv --directory tools/ingest run pytest tests/test_eval_metrics.py tests/test_eval.py -v`
Expected: PASS — the 8 new tests plus every existing eval test. The existing tests pin the
Recall@5 / nDCG semantics; if one of them breaks, the recall rewrite changed behaviour for
chunk-id matching and must be corrected, not the test.

- [x] **Step 5: Score the committed golden set against the live corpus as a smoke check**

```bash
uv --directory tools/ingest run langatlas-sources eval --no-rerank --depth 50
```

Expected: a report over 52 queries with a non-`n/a` Recall@50. Record the numbers in the commit
message body — this is the full-corpus baseline the pilot arms are read against.

- [x] **Step 6: Commit**

```bash
git add tools/ingest/src/langatlas_ingest/eval.py \
        tools/ingest/src/langatlas_ingest/cli.py \
        tools/ingest/tests/test_eval_metrics.py tools/ingest/tests/test_eval.py \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): measure Recall@50 and scope the eval to a pilot corpus"
```

---

## Task 6: The committed run matrix

The benchmark's inputs are configuration, not code: candidates, modes, chunk sizes, margins and
the pilot are all things the developer ratifies and a reviewer reads in a diff. This task defines
the `Arm` type, mints deterministic arm ids (an arm id is a filename, so it must be stable across
runs), and expands the matrix from YAML.

**This task ends at the developer checkpoint that ratifies the four plan-level decisions listed
at the top of this document.**

**Files:**
- Create: `tools/ingest/src/langatlas_ingest/benchmark/__init__.py`
- Create: `tools/ingest/src/langatlas_ingest/benchmark/arms.py`
- Create: `tools/ingest/tests/test_benchmark_arms.py`
- Create: `config/benchmark/d22-source-corpus.yaml`
- Modify: `tools/ingest/src/langatlas_ingest/paths.py`

**Interfaces:**
- Consumes: `ruamel.yaml`, `paths.REPO_ROOT`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class Arm:
      embedding_model: str
      mode: str                      # "hybrid" | "vector" | "fts"
      rerank: bool
      chunk_target_tokens: int
      chunk_max_tokens: int
      truncate: bool
      depth: int = 50
      axis: str = "primary"          # "primary" | "chunk-size"
      @property
      def arm_id(self) -> str
      def result_path(self, root: Path) -> Path
      def as_dict(self) -> dict

  @dataclass(frozen=True)
  class Margins:
      beat_incumbent_recall5_pts: float = 5.0
      local_match_recall5_pts: float = 2.0
      rerank_min_ndcg_pts: float = 2.0
      hybrid_min_recall5_pts: float = 2.0
      chunk_size_min_recall5_pts: float = 2.0

  @dataclass(frozen=True)
  class Matrix:
      pilot_sources: tuple[str, ...]
      golden_dir: Path
      results_dir: Path
      incumbent: str
      local_models: tuple[str, ...]
      margins: Margins
      primary: tuple[Arm, ...]
      primary_chunk_size: tuple[int, int]
      chunk_sizes: tuple[tuple[int, int], ...]
      def chunk_size_arms(self, model: str, *, truncate: bool) -> tuple[Arm, ...]
      def all_primary_ids(self) -> tuple[str, ...]

  def load_matrix(path: Path | None = None) -> Matrix
  def slug(text: str) -> str
  ```

- [x] **Step 1: Write the failing tests**

Create `tools/ingest/tests/test_benchmark_arms.py`:

```python
import pytest
from pathlib import Path
from langatlas_ingest.benchmark.arms import Arm, Matrix, load_matrix, slug

MATRIX = """
pilot_sources: [scott-plp, sebesta-copl]
golden_dir: tests/golden/retrieval
results_dir: benchmarks/d22-source-corpus/results
incumbent: model-a
candidates:
  - model: model-a
  - model: model-b
    truncate: true
  - model: 'local:Vendor/tiny-v1.5'
    truncate: true
    local: true
modes: [vector, hybrid]
chunk_sizes:
  primary: {target_tokens: 600, max_tokens: 800}
  secondary:
    - {target_tokens: 400, max_tokens: 550}
    - {target_tokens: 800, max_tokens: 1050}
margins:
  beat_incumbent_recall5_pts: 5.0
  local_match_recall5_pts: 2.0
  rerank_min_ndcg_pts: 2.0
  hybrid_min_recall5_pts: 2.0
  chunk_size_min_recall5_pts: 2.0
"""


@pytest.fixture
def matrix_path(tmp_path: Path) -> Path:
    path = tmp_path / "d22.yaml"
    path.write_text(MATRIX)
    return path


def test_slug_is_filename_safe():
    assert slug("local:Vendor/tiny-v1.5") == "local-vendor-tiny-v1-5"
    assert slug("qwen3-embedding-4b") == "qwen3-embedding-4b"


def test_arm_id_is_deterministic_and_readable():
    arm = Arm(embedding_model="qwen3-embedding-4b", mode="hybrid", rerank=True,
              chunk_target_tokens=600, chunk_max_tokens=800, truncate=False)
    assert arm.arm_id == "qwen3-embedding-4b__hybrid-rerank__c600"
    assert Arm(embedding_model="m", mode="vector", rerank=False,
               chunk_target_tokens=400, chunk_max_tokens=550,
               truncate=True).arm_id == "m__vector__c400"


def test_result_path_is_the_arm_id(tmp_path: Path):
    arm = Arm(embedding_model="m", mode="hybrid", rerank=False,
              chunk_target_tokens=600, chunk_max_tokens=800, truncate=False)
    assert arm.result_path(tmp_path).name == "m__hybrid__c600.json"


def test_matrix_expands_three_arms_per_model(matrix_path: Path):
    matrix = load_matrix(matrix_path)
    assert len(matrix.primary) == 9        # 3 models x {vector, hybrid, hybrid+rerank}
    per_model = {}
    for arm in matrix.primary:
        per_model.setdefault(arm.embedding_model, []).append((arm.mode, arm.rerank))
    assert per_model["model-a"] == [("vector", False), ("hybrid", False),
                                    ("hybrid", True)]


def test_vector_arms_are_never_reranked(matrix_path: Path):
    matrix = load_matrix(matrix_path)
    assert not any(arm.rerank for arm in matrix.primary if arm.mode == "vector")


def test_truncate_rides_the_candidate_not_the_mode(matrix_path: Path):
    matrix = load_matrix(matrix_path)
    truncating = {arm.embedding_model for arm in matrix.primary if arm.truncate}
    assert truncating == {"model-b", "local:Vendor/tiny-v1.5"}


def test_local_models_are_declared_for_the_verdict_rule(matrix_path: Path):
    assert load_matrix(matrix_path).local_models == ("local:Vendor/tiny-v1.5",)


def test_primary_arms_all_use_the_primary_chunk_size(matrix_path: Path):
    matrix = load_matrix(matrix_path)
    assert {(a.chunk_target_tokens, a.chunk_max_tokens) for a in matrix.primary} \
        == {(600, 800)}


def test_chunk_size_arms_are_hybrid_rerank_only(matrix_path: Path):
    matrix = load_matrix(matrix_path)
    arms = matrix.chunk_size_arms("model-a", truncate=False)
    assert [(a.chunk_target_tokens, a.mode, a.rerank, a.axis) for a in arms] == [
        (400, "hybrid", True, "chunk-size"), (800, "hybrid", True, "chunk-size")]


def test_margins_load_from_the_file(matrix_path: Path):
    assert load_matrix(matrix_path).margins.beat_incumbent_recall5_pts == 5.0


def test_paths_are_resolved_against_the_repo_root(matrix_path: Path):
    matrix = load_matrix(matrix_path)
    assert matrix.golden_dir.is_absolute() and matrix.results_dir.is_absolute()
    assert matrix.golden_dir.name == "retrieval"


def test_the_committed_matrix_loads_and_is_shaped_as_ratified():
    matrix = load_matrix()
    assert matrix.incumbent == "qwen3-embedding-4b"
    assert len(matrix.pilot_sources) == 4
    assert len(matrix.primary) == 18       # 6 candidates x 3 arms
    assert matrix.chunk_sizes == ((400, 550), (800, 1050))
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_arms.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'langatlas_ingest.benchmark'`.

- [x] **Step 3: Implement `arms.py`**

Create `tools/ingest/src/langatlas_ingest/benchmark/__init__.py` (empty) and
`tools/ingest/src/langatlas_ingest/benchmark/arms.py`:

```python
import re
from dataclasses import dataclass
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_ingest.paths import BENCHMARK_CONFIG_PATH, REPO_ROOT

_yaml = YAML(typ="safe")
_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    """Arm ids become filenames, and a model id may carry a colon and a slash
    (`local:BAAI/bge-small-en-v1.5`). One collapsing rule, applied everywhere."""
    return _SLUG.sub("-", text.lower()).strip("-")


@dataclass(frozen=True)
class Arm:
    """One measured configuration. Frozen and fully self-describing: an arm's result
    JSON records the arm, so a committed result stays interpretable without the matrix
    file that produced it."""

    embedding_model: str
    mode: str
    rerank: bool
    chunk_target_tokens: int
    chunk_max_tokens: int
    truncate: bool
    depth: int = 50
    axis: str = "primary"

    @property
    def arm_id(self) -> str:
        variant = f"{self.mode}-rerank" if self.rerank else self.mode
        return f"{slug(self.embedding_model)}__{variant}__c{self.chunk_target_tokens}"

    def result_path(self, root: Path) -> Path:
        return Path(root) / f"{self.arm_id}.json"

    def as_dict(self) -> dict:
        return {"arm_id": self.arm_id, "embedding_model": self.embedding_model,
                "mode": self.mode, "rerank": self.rerank,
                "chunk_target_tokens": self.chunk_target_tokens,
                "chunk_max_tokens": self.chunk_max_tokens, "truncate": self.truncate,
                "depth": self.depth, "axis": self.axis}


@dataclass(frozen=True)
class Margins:
    """§8.6's decision rules as numbers. In percentage *points*, not fractions — the
    spec states them that way and the verdict prints them that way, so converting once
    at the boundary beats converting at every comparison."""

    beat_incumbent_recall5_pts: float = 5.0
    local_match_recall5_pts: float = 2.0
    rerank_min_ndcg_pts: float = 2.0
    hybrid_min_recall5_pts: float = 2.0
    # Not in §8.6 (it gives no chunk-size rule); adopted by this plan's decision 2 and
    # ratified at the Task 6 checkpoint.
    chunk_size_min_recall5_pts: float = 2.0


@dataclass(frozen=True)
class Matrix:
    pilot_sources: tuple[str, ...]
    golden_dir: Path
    results_dir: Path
    incumbent: str
    local_models: tuple[str, ...]
    margins: Margins
    primary: tuple[Arm, ...]
    primary_chunk_size: tuple[int, int]
    chunk_sizes: tuple[tuple[int, int], ...]

    def chunk_size_arms(self, model: str, *, truncate: bool) -> tuple[Arm, ...]:
        """§8.6's secondary axis, run only for the model the primary matrix chose:
        re-chunking is a corpus rebuild per size, and re-running it for five models that
        lost on the primary axis would buy nothing."""
        return tuple(
            Arm(embedding_model=model, mode="hybrid", rerank=True,
                chunk_target_tokens=target, chunk_max_tokens=maximum,
                truncate=truncate, axis="chunk-size")
            for target, maximum in self.chunk_sizes)

    def all_primary_ids(self) -> tuple[str, ...]:
        return tuple(arm.arm_id for arm in self.primary)


def load_matrix(path: Path | None = None) -> Matrix:
    raw = _yaml.load(Path(path or BENCHMARK_CONFIG_PATH).read_text())
    primary_size = raw["chunk_sizes"]["primary"]
    target, maximum = int(primary_size["target_tokens"]), int(primary_size["max_tokens"])

    arms: list[Arm] = []
    local: list[str] = []
    for candidate in raw["candidates"]:
        model, truncate = candidate["model"], bool(candidate.get("truncate", False))
        if candidate.get("local"):
            local.append(model)
        for mode in raw["modes"]:
            # Vector-only arms are never reranked: the reranker consumes the RRF-fused
            # pool, so a reranked vector arm answers a question §8.6 does not ask and
            # doubles the completion spend (plan decision 4).
            reranks = (False,) if mode != "hybrid" else (False, True)
            for rerank in reranks:
                arms.append(Arm(embedding_model=model, mode=mode, rerank=rerank,
                                chunk_target_tokens=target, chunk_max_tokens=maximum,
                                truncate=truncate))

    return Matrix(
        pilot_sources=tuple(raw["pilot_sources"]),
        golden_dir=REPO_ROOT / raw["golden_dir"],
        results_dir=REPO_ROOT / raw["results_dir"],
        incumbent=raw["incumbent"],
        local_models=tuple(local),
        margins=Margins(**{key: float(value)
                           for key, value in (raw.get("margins") or {}).items()}),
        primary=tuple(arms),
        primary_chunk_size=(target, maximum),
        chunk_sizes=tuple((int(size["target_tokens"]), int(size["max_tokens"]))
                          for size in raw["chunk_sizes"]["secondary"]),
    )
```

In `tools/ingest/src/langatlas_ingest/paths.py`, append:

```python
# §8.6's D22 benchmark. The matrix is committed configuration; the results and verdict
# are a committed research record justifying a pinned production setting — neither is a
# derived artifact in D1's sense, so both live in git while the vectors they measure do
# not.
BENCHMARK_CONFIG_PATH = REPO_ROOT / "config" / "benchmark" / "d22-source-corpus.yaml"
BENCHMARK_DIR = REPO_ROOT / "benchmarks" / "d22-source-corpus"
```

- [x] **Step 4: Write the committed matrix**

Create `config/benchmark/d22-source-corpus.yaml`:

```yaml
# §8.6's D22 source-corpus benchmark (R2). Model ids are configuration, never hardcoded:
# every candidate below must exist in config/provider_capabilities.yaml (probed for the
# gateway roster, model-card-sourced for the local one).
#
# Pilot: the coverage-maximising 4-source selection computed by `bench-pilot`, covering
# 37 of the golden set's 52 queries across all three bands. Recall numbers from a
# 4-source corpus are comparative, not absolute — the distractor pool is a quarter of
# production's. That is exactly what a model-selection benchmark needs, and the verdict
# record says so.
pilot_sources: [rust-fls, rust-reference, scott-plp, sebesta-copl]
golden_dir: tests/golden/retrieval
results_dir: benchmarks/d22-source-corpus/results
incumbent: qwen3-embedding-4b

candidates:
  - model: qwen3-embedding-4b                 # D15 incumbent, 2560-dim / 40960-token
  - model: nomic-embed-text-v1.5              # 768-dim / 8192-token
  - model: nomic-embed-text-v2-moe            # probed in Task 1
  - model: mxbai-embed-large                  # 1024-dim / 512-token
    truncate: true                            # §8.6: tested honestly at its real window
  - model: multilingual-e5-large-instruct     # 1024-dim / 512-token
    truncate: true
  - model: local:BAAI/bge-small-en-v1.5       # §8.6's free-and-local floor, 384/512
    truncate: true
    local: true

# `hybrid` expands to two arms (with and without the reranker); `vector` to one.
modes: [vector, hybrid]

chunk_sizes:
  # Production's chunking; the primary matrix's only chunking.
  primary: {target_tokens: 600, max_tokens: 800}
  # §8.6's "400 vs 800 chunk size as a secondary axis", keeping production's 1.33x
  # target-to-max ratio. Run for the chosen model only.
  secondary:
    - {target_tokens: 400, max_tokens: 550}
    - {target_tokens: 800, max_tokens: 1050}

# §8.6's decision rules, in percentage points.
margins:
  beat_incumbent_recall5_pts: 5.0     # a challenger must beat the incumbent by >= 5
  local_match_recall5_pts: 2.0        # a local model wins by matching within 2
  rerank_min_ndcg_pts: 2.0            # reranker stays default-on unless it adds < 2
  hybrid_min_recall5_pts: 2.0         # hybrid stays unless it adds < 2 over vector-only
  chunk_size_min_recall5_pts: 2.0     # plan decision 2 (not in §8.6); ratified 2026-09-05
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_arms.py -v`
Expected: PASS (12 tests), including `test_the_committed_matrix_loads_and_is_shaped_as_ratified`.

- [x] **Step 6: Verify every candidate resolves**

```bash
uv --directory tools/ingest run python -c "
from langatlas_ingest.benchmark.arms import load_matrix
from langatlas_pipeline.config import ProviderConfig
config, matrix = ProviderConfig.load(), load_matrix()
for model in sorted({a.embedding_model for a in matrix.primary}):
    cap = config.embedding(model)
    print(f'{model}: {cap.dimensions}-dim / {cap.max_input_tokens} tokens')"
```

Expected: six lines, no `UnknownAlias`. A failure here means Task 1 or Task 3 left a candidate
unregistered — fix that, do not edit the matrix.

- [x] **Step 7: Developer checkpoint — ratify the four plan-level decisions**

Present to the developer, and do not proceed until each is accepted or amended:

1. Chunk-size endpoints 400/550 and 800/1050 (production 600/800 is the third point).
2. The chunk-size decision rule: move only on ≥2.0 pts Recall@5 (§8.6 states no rule).
3. Local-model precedence: a local model matching within 2 pts *wins* over the incumbent.
4. Vector-only arms are never reranked.

Plus the pilot itself: `rust-fls`, `rust-reference`, `scott-plp`, `sebesta-copl` — 37/52 queries.
Task 7 recomputes this mechanically, so an amendment here is a matrix edit, not a code change.

- [x] **Step 8: Commit**

```bash
git add tools/ingest/src/langatlas_ingest/benchmark/ \
        tools/ingest/src/langatlas_ingest/paths.py \
        tools/ingest/tests/test_benchmark_arms.py \
        config/benchmark/d22-source-corpus.yaml \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): define the D22 benchmark run matrix"
```

---

## Task 7: Pilot selection

§8.6 says "on a pilot corpus" and the sequencing map says "3–4 sources". Which three or four is
not a matter of taste: the pilot has to be the set that lets the most golden queries be scored,
because every query it cannot answer is a query the benchmark does not get to use. This task
makes that selection a computation with a committed answer, so the choice is auditable and
re-derivable when the golden set grows.

**Files:**
- Create: `tools/ingest/src/langatlas_ingest/benchmark/pilot.py`
- Create: `tools/ingest/tests/test_benchmark_pilot.py`

**Interfaces:**
- Consumes: `eval.load_entries`, `eval.expected_sources_of`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class PilotSelection:
      sources: tuple[str, ...]
      covered: int
      total: int
      per_band: dict[str, int]
      def to_markdown(self) -> str

  def source_frequency(entries: list[dict]) -> dict[str, int]
  def select_pilot(entries: list[dict], *, size: int = 4,
                   available: Sequence[str] | None = None) -> PilotSelection
  ```

- [x] **Step 1: Write the failing tests**

Create `tools/ingest/tests/test_benchmark_pilot.py`:

```python
from langatlas_ingest.benchmark.pilot import (
    PilotSelection, select_pilot, source_frequency,
)

ENTRIES = [
    {"id": "a", "band": "exact-term", "expected_chunks": ["s1#c1"]},
    {"id": "b", "band": "exact-term", "expected_chunks": ["s1#c2"]},
    {"id": "c", "band": "paraphrase-concept", "expected_chunks": ["s2#c1"]},
    {"id": "d", "band": "cross-source-survey", "expected_sources": ["s1", "s2"]},
    {"id": "e", "band": "cross-source-survey", "expected_sources": ["s1", "s3"]},
    {"id": "f", "band": "exact-term", "expected_chunks": ["s4#c1"]},
]


def test_source_frequency_counts_both_expectation_kinds():
    assert source_frequency(ENTRIES) == {"s1": 4, "s2": 2, "s3": 1, "s4": 1}


def test_select_pilot_maximises_fully_covered_queries():
    selection = select_pilot(ENTRIES, size=2)
    assert selection.sources == ("s1", "s2")
    # a, b, c, d — e needs s3, f needs s4.
    assert (selection.covered, selection.total) == (4, 6)


def test_a_survey_query_counts_only_when_every_source_is_present():
    # s1 alone covers a and b but not d: a survey is not half-surveyable.
    assert select_pilot(ENTRIES, size=1).covered == 2


def test_per_band_breakdown_is_reported():
    assert select_pilot(ENTRIES, size=2).per_band == {
        "exact-term": 2, "paraphrase-concept": 1, "cross-source-survey": 1}


def test_available_restricts_the_candidate_pool():
    selection = select_pilot(ENTRIES, size=2, available=["s2", "s3", "s4"])
    assert "s1" not in selection.sources


def test_a_larger_size_than_the_source_pool_is_clamped():
    selection = select_pilot(ENTRIES, size=99)
    assert set(selection.sources) == {"s1", "s2", "s3", "s4"}
    assert selection.covered == 6


def test_ties_break_deterministically_on_the_sorted_source_names():
    entries = [{"id": "x", "band": "exact-term", "expected_chunks": ["b#c1"]},
               {"id": "y", "band": "exact-term", "expected_chunks": ["a#c1"]}]
    assert select_pilot(entries, size=1).sources == ("a",)


def test_markdown_names_the_coverage():
    text = PilotSelection(("s1",), 2, 6, {"exact-term": 2}).to_markdown()
    assert "s1" in text and "2/6" in text


def test_the_committed_golden_set_selects_the_ratified_pilot():
    from langatlas_ingest.eval import load_entries
    from langatlas_ingest.paths import GOLDEN_RETRIEVAL_DIR

    selection = select_pilot(load_entries(GOLDEN_RETRIEVAL_DIR), size=4)
    assert selection.sources == ("rust-fls", "rust-reference", "scott-plp",
                                 "sebesta-copl")
    assert (selection.covered, selection.total) == (37, 52)
    assert selection.per_band == {"exact-term": 16, "paraphrase-concept": 16,
                                  "cross-source-survey": 5}
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_pilot.py -v`
Expected: FAIL — `ModuleNotFoundError: ... benchmark.pilot`.

- [x] **Step 3: Implement `pilot.py`**

```python
import collections
import itertools
from dataclasses import dataclass
from typing import Sequence
from langatlas_ingest.eval import expected_sources_of


@dataclass(frozen=True)
class PilotSelection:
    sources: tuple[str, ...]
    covered: int
    total: int
    per_band: dict[str, int]

    def to_markdown(self) -> str:
        bands = ", ".join(f"{band}: {count}"
                          for band, count in sorted(self.per_band.items()))
        return (f"pilot: {', '.join(self.sources)}\n"
                f"covered: {self.covered}/{self.total} queries ({bands})\n")


def source_frequency(entries: list[dict]) -> dict[str, int]:
    counter: collections.Counter = collections.Counter()
    for entry in entries:
        counter.update(expected_sources_of(entry))
    return dict(counter)


def select_pilot(entries: list[dict], *, size: int = 4,
                 available: Sequence[str] | None = None) -> PilotSelection:
    """Exhaustive over the sources the golden set actually names — twelve of them today,
    so C(12,4)=495 candidate sets, which is nothing. A greedy set-cover would be faster
    and occasionally wrong, and 'occasionally wrong' is not a property the corpus the
    whole benchmark runs on should have.

    A query counts as covered only when *every* source it names is in the pilot. That is
    strict on purpose for the cross-source-survey band: a survey scored against half its
    sources is not a survey, and `run_eval`'s `corpus_sources` gate applies the identical
    rule, so this number is exactly what the arms will report.
    """
    needs = [(entry.get("band"), expected_sources_of(entry)) for entry in entries]
    pool = sorted(source_frequency(entries))
    if available is not None:
        allowed = set(available)
        pool = [source for source in pool if source in allowed]
    size = min(size, len(pool))

    best: tuple[int, tuple[str, ...]] | None = None
    for combination in itertools.combinations(pool, size):
        chosen = set(combination)
        covered = sum(1 for _, sources in needs if sources <= chosen)
        # `itertools.combinations` walks a sorted pool in lexicographic order, and a
        # strict `>` keeps the first of any tie — so the answer is stable across runs and
        # across machines, which matters because it is committed configuration.
        if best is None or covered > best[0]:
            best = (covered, combination)

    covered, combination = best if best else (0, ())
    chosen = set(combination)
    per_band: collections.Counter = collections.Counter(
        band for band, sources in needs if sources <= chosen)
    return PilotSelection(sources=tuple(combination), covered=covered,
                          total=len(needs), per_band=dict(per_band))
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_pilot.py -v`
Expected: PASS (9 tests). `test_the_committed_golden_set_selects_the_ratified_pilot` is the one
that matters: it pins the matrix's `pilot_sources` to a computation, so a later golden-set edit
that changes the best pilot fails a test instead of silently invalidating the benchmark.

- [x] **Step 5: Commit**

```bash
git add tools/ingest/src/langatlas_ingest/benchmark/pilot.py \
        tools/ingest/tests/test_benchmark_pilot.py \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): select the pilot corpus by golden-query coverage"
```

---

## Task 8: The bench corpus

Every arm needs a corpus, and two things must be true of it: **no arm may touch production**
(re-chunking `source_chunks` at 400 tokens would invalidate every committed golden chunk id, 2B's
whole output), and the 600-token arms must be measuring the *same* chunks the golden set was
authored against.

Both fall out of one design: a separate `langatlas_bench` database, rebuilt from the private
snapshot store — which already holds every pilot source's original — and a parity check that
asserts the 600-token rebuild reproduces production's chunk ids exactly.

**Files:**
- Create: `tools/ingest/src/langatlas_ingest/benchmark/corpus.py`
- Create: `tools/ingest/tests/test_benchmark_corpus.py`
- Modify: `tools/ingest/src/langatlas_ingest/errors.py`

**Interfaces:**
- Consumes: `db.connect`/`migrate`, `pipeline.ingest_source`, `snapshot.SnapshotStore`,
  `store.SourceChunksStore`, `IngestConfig.load(overrides=...)`.
- Produces:
  ```python
  BENCH_DB_NAME = "langatlas_bench"

  def bench_dsn(base_dsn: str, *, name: str = BENCH_DB_NAME) -> str
  def create_bench_db(base_dsn: str, *, name: str = BENCH_DB_NAME,
                      drop: bool = False) -> str
  def build_bench_corpus(conn, *, sources: Sequence[str], config: IngestConfig,
                         snapshots=None) -> dict[str, int]
  def chunk_ids(conn, source_id: str) -> list[str]
  def check_parity(bench_conn, prod_conn, sources: Sequence[str]) -> list[str]

  class BenchCorpusMismatch(IngestError):
      def __init__(self, differences: list[str])
  ```

- [x] **Step 1: Write the failing tests**

Create `tools/ingest/tests/test_benchmark_corpus.py`:

```python
import pytest
from langatlas_ingest.benchmark.corpus import (
    BENCH_DB_NAME, bench_dsn, check_parity, chunk_ids,
)
from langatlas_ingest.errors import BenchCorpusMismatch


def test_bench_dsn_swaps_only_the_database_name():
    dsn = "postgresql://u:p@localhost:55432/langatlas"
    assert bench_dsn(dsn) == f"postgresql://u:p@localhost:55432/{BENCH_DB_NAME}"
    assert bench_dsn(dsn, name="other").endswith("/other")


def test_bench_dsn_refuses_to_return_the_production_name():
    # The one mistake this module exists to prevent.
    with pytest.raises(ValueError):
        bench_dsn("postgresql://u:p@h/langatlas", name="langatlas")


def _chunk(chunk_id: str, ordinal: int):
    from langatlas_ingest.store import SourceChunk

    return SourceChunk(chunk_id=chunk_id, source_id="s1", ordinal=ordinal,
                       parent_section_id=None, section_path=["Ch"], breadcrumb="Ch",
                       locator=f"p. {ordinal}", locator_kind="book-page",
                       page_start=ordinal, page_end=ordinal, section_number=None,
                       anchor=None, line_start=None, line_end=None,
                       text=f"body {ordinal}", token_count=3, content_hash=f"h{ordinal}")


@pytest.fixture
def two_stores(db_conn, dsn):
    """Two independent databases, standing in for bench and production."""
    import psycopg
    from langatlas_ingest.db import migrate

    migrate(db_conn)
    second_dsn = dsn.rsplit("/", 1)[0] + "/langatlas_test_two"
    with psycopg.connect(dsn.rsplit("/", 1)[0] + "/postgres", autocommit=True) as admin:
        with admin.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS langatlas_test_two WITH (FORCE)")
            cur.execute("CREATE DATABASE langatlas_test_two")
    with psycopg.connect(second_dsn, autocommit=True) as other:
        migrate(other)
        yield db_conn, other


@pytest.mark.db
def test_chunk_ids_are_ordered_by_ordinal(two_stores):
    from langatlas_ingest.store import SourceChunksStore

    bench, _ = two_stores
    SourceChunksStore(bench).replace_source(
        "s1", [_chunk("s1#c00002", 2), _chunk("s1#c00001", 1)])
    assert chunk_ids(bench, "s1") == ["s1#c00001", "s1#c00002"]


@pytest.mark.db
def test_check_parity_is_silent_on_identical_corpora(two_stores):
    from langatlas_ingest.store import SourceChunksStore

    bench, production = two_stores
    for conn in (bench, production):
        SourceChunksStore(conn).replace_source("s1", [_chunk("s1#c00001", 1)])
    assert check_parity(bench, production, ["s1"]) == []


@pytest.mark.db
def test_check_parity_reports_a_differing_count(two_stores):
    from langatlas_ingest.store import SourceChunksStore

    bench, production = two_stores
    SourceChunksStore(bench).replace_source("s1", [_chunk("s1#c00001", 1)])
    SourceChunksStore(production).replace_source(
        "s1", [_chunk("s1#c00001", 1), _chunk("s1#c00002", 2)])
    differences = check_parity(bench, production, ["s1"])
    assert differences == ["s1: 1 chunks in bench, 2 in production"]


@pytest.mark.db
def test_check_parity_names_the_first_divergent_ordinal(two_stores):
    from langatlas_ingest.store import SourceChunksStore

    bench, production = two_stores
    SourceChunksStore(bench).replace_source(
        "s1", [_chunk("s1#c00001", 1), _chunk("s1#c00009", 2)])
    SourceChunksStore(production).replace_source(
        "s1", [_chunk("s1#c00001", 1), _chunk("s1#c00002", 2)])
    [difference] = check_parity(bench, production, ["s1"])
    assert "ordinal 1" in difference and "s1#c00009" in difference


def test_mismatch_error_lists_the_sources():
    error = BenchCorpusMismatch(["s1: 10 chunks in bench, 12 in production"])
    assert "s1" in str(error)
```

> The `two_stores` fixture creates a second throwaway database beside the session's
> `langatlas_test` one, using the same `dsn` fixture the module-level conftest already provides.
> It is torn down by the next run's `DROP DATABASE IF EXISTS`, matching how `dsn` itself handles
> `langatlas_test`.

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_corpus.py -v`
Expected: FAIL — `ModuleNotFoundError: ... benchmark.corpus`.

- [x] **Step 3: Implement `corpus.py`**

```python
from typing import Sequence
import psycopg
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import migrate
from langatlas_ingest.errors import BenchCorpusMismatch
from langatlas_ingest.pipeline import ingest_source
from langatlas_ingest.snapshot import SnapshotStore

# §8.6's arms re-chunk the corpus at 400 and 800 tokens. Doing that in the production
# database would rewrite every chunk id the 2B golden sets cite — the single most
# destructive thing this stage could do — so the benchmark gets its own database and the
# production one is never opened for writing here.
BENCH_DB_NAME = "langatlas_bench"


def bench_dsn(base_dsn: str, *, name: str = BENCH_DB_NAME) -> str:
    head, _, current = base_dsn.rpartition("/")
    if name == current:
        raise ValueError(f"refusing to use the production database {current!r} as the"
                         " benchmark database")
    return f"{head}/{name}"


def create_bench_db(base_dsn: str, *, name: str = BENCH_DB_NAME,
                    drop: bool = False) -> str:
    """Create (optionally recreate) the benchmark database and apply `db/*.sql`. Returns
    its DSN. `drop=True` is the chunk-size axis's reset: a re-chunk must not leave the
    previous size's rows behind, and per-source replacement would not catch a source
    that vanished from the pilot."""
    target = bench_dsn(base_dsn, name=name)
    with psycopg.connect(base_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            if drop:
                cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{name}"')
    with psycopg.connect(target, autocommit=True) as conn:
        migrate(conn)
    return target


def build_bench_corpus(conn, *, sources: Sequence[str], config: IngestConfig,
                       snapshots: SnapshotStore | None = None) -> dict[str, int]:
    """Re-ingest each pilot source from its stored snapshot at `config`'s chunk size.

    Nothing is fetched: `SnapshotStore` already holds every original 2A acquired, and
    re-fetching would make the benchmark depend on a publisher's uptime and could return
    a different document than the one the golden set was authored against.
    """
    snapshots = snapshots or SnapshotStore()
    counts: dict[str, int] = {}
    for source_id in sources:
        result = ingest_source(source_id, conn=conn, config=config, snapshots=snapshots)
        counts[source_id] = result.chunk_count
    return counts


def chunk_ids(conn, source_id: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT chunk_id FROM source_chunks WHERE source_id = %s"
                    " ORDER BY ordinal", (source_id,))
        return [row[0] for row in cur.fetchall()]


def check_parity(bench_conn, prod_conn, sources: Sequence[str]) -> list[str]:
    """Assert the 600-token rebuild reproduces production's chunk ids exactly.

    This is the load-bearing check of the whole benchmark: the golden set's
    `expected_chunks` are production chunk ids, so if the bench corpus's ids differ, every
    primary arm is scoring against ids that do not exist and would report a uniform zero
    that looks like a model failure. Chunking is deterministic given the same snapshot and
    the same config, so any difference is a real finding — a changed snapshot, a changed
    extractor, a changed config — and never something to work around.
    """
    differences: list[str] = []
    for source_id in sources:
        bench, production = chunk_ids(bench_conn, source_id), chunk_ids(prod_conn,
                                                                        source_id)
        if bench == production:
            continue
        if len(bench) != len(production):
            differences.append(f"{source_id}: {len(bench)} chunks in bench,"
                               f" {len(production)} in production")
        else:
            first = next(index for index, (a, b)
                         in enumerate(zip(bench, production)) if a != b)
            differences.append(f"{source_id}: same count, first divergence at ordinal"
                               f" {first}: {bench[first]!r} != {production[first]!r}")
    return differences
```

In `tools/ingest/src/langatlas_ingest/errors.py`:

```python
class BenchCorpusMismatch(IngestError):
    """The benchmark corpus rebuilt at production's chunk size does not reproduce
    production's chunk ids. Fatal rather than a warning: the golden set cites production
    ids, so every arm scored against a divergent corpus reports a uniform zero that reads
    as a model failure instead of a corpus failure."""

    def __init__(self, differences: list[str]):
        super().__init__("benchmark corpus does not match production:\n  "
                         + "\n  ".join(differences))
        self.differences = list(differences)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `docker compose up -d db && uv --directory tools/ingest run pytest tests/test_benchmark_corpus.py -v -m db`
Expected: PASS.

- [x] **Step 5: Build the real bench corpus and verify parity (developer checkpoint)**

Task 13 wires the CLI; until then, run it directly:

```bash
uv --directory tools/ingest run python -c "
import psycopg
from langatlas_ingest.benchmark.arms import load_matrix
from langatlas_ingest.benchmark.corpus import build_bench_corpus, check_parity, create_bench_db
from langatlas_ingest.config import IngestConfig
config, matrix = IngestConfig.load(), load_matrix()
target = create_bench_db(config.dsn, drop=True)
with psycopg.connect(target, autocommit=True) as bench, \
     psycopg.connect(config.dsn, autocommit=True) as prod:
    print(build_bench_corpus(bench, sources=matrix.pilot_sources, config=config))
    print('parity:', check_parity(bench, prod, matrix.pilot_sources) or 'OK')"
```

Expected: `{'rust-fls': 1188, 'rust-reference': 788, 'scott-plp': 845, 'sebesta-copl': 1005}`
and `parity: OK`. **Any parity difference stops the plan** — report it rather than adjusting the
golden set or the pilot; it means a snapshot, the extractor, or the chunking config moved since
2A, which is a finding about the corpus, not about the benchmark.

- [x] **Step 6: Commit**

```bash
git add tools/ingest/src/langatlas_ingest/benchmark/corpus.py \
        tools/ingest/src/langatlas_ingest/errors.py \
        tools/ingest/tests/test_benchmark_corpus.py \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): build the benchmark corpus in an isolated database"
```

---

## Task 9: Chunking-independent relevance

The 400- and 800-token arms re-chunk the corpus, so their chunk ids are new by construction and
every `expected_chunks` id in the golden set is absent from them. Scoring those arms by chunk-id
equality would report zero for every query — a measurement of the id scheme, not of the chunk
size.

The fix is to score the secondary axis against **document spans** instead: the golden chunk is
resolved once, in the production corpus, to the region of the document it occupies, and a
retrieved chunk from any chunking counts as relevant when it covers that region. Two facts about
the corpus make this exact rather than approximate: page-locator sources (`scott-plp`,
`rust-reference`, and 128 of `sebesta-copl`'s chunks) carry real `page_start`/`page_end` ranges,
and section-locator sources (`rust-fls`, most of `sebesta-copl`) carry a `section_path` that comes
from the document outline and is therefore identical under any chunk size.

Primary arms keep chunk-id equality: they run at production's chunking, where the golden ids are
the truth.

**Files:**
- Create: `tools/ingest/src/langatlas_ingest/benchmark/relevance.py`
- Create: `tools/ingest/tests/test_benchmark_relevance.py`

**Interfaces:**
- Consumes: `store.SourceChunk`, `store.SourceChunksStore`, `eval.expected_sources_of`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class Span:
      source_id: str
      section_path: tuple[str, ...]
      page_start: int | None
      page_end: int | None

  def span_of(chunk: SourceChunk) -> Span
  def overlaps(expected: Span, candidate: Span) -> bool
  def load_expected_spans(prod_conn, entries: list[dict]) -> dict[str, tuple[Span, ...]]
  def make_span_relevance(spans: dict[str, tuple[Span, ...]]) -> Callable[[dict, SourceChunk], bool]
  ```

- [x] **Step 1: Write the failing tests**

The db test below reuses `tests/test_search.py`'s existing `searchable` fixture, so **move it
first**: lift `searchable` and its `make_chunks` / `TEXTS` / `CONFIG` helpers from
`tools/ingest/tests/test_search.py` into `tools/ingest/tests/conftest.py`, and change
`test_search.py`'s module-level `CONFIG` reference to `from tests.conftest import CONFIG` (the
package already puts `tools/ingest` on `sys.path` via `pythonpath = ["."]`). `test_search.py`'s
own tests keep working untouched — pytest resolves fixtures from conftest. Run
`uv --directory tools/ingest run pytest -m "db or not db"` to confirm the move before adding
anything.

Then create `tools/ingest/tests/test_benchmark_relevance.py`:

```python
import pytest
from langatlas_ingest.benchmark.relevance import (
    Span, load_expected_spans, make_span_relevance, overlaps, span_of,
)
from langatlas_ingest.store import SourceChunk


def _chunk(chunk_id="s#c1", source_id="s", section_path=("3", "3.1"),
           page_start=None, page_end=None):
    return SourceChunk(chunk_id=chunk_id, source_id=source_id, ordinal=1,
                       parent_section_id=None, section_path=list(section_path),
                       breadcrumb=" > ".join(section_path), locator="x",
                       locator_kind="numbered-section", page_start=page_start,
                       page_end=page_end, section_number=None, anchor=None,
                       line_start=None, line_end=None, text="body", token_count=3)


def test_span_of_reads_both_coordinate_systems():
    span = span_of(_chunk(page_start=10, page_end=12))
    assert span == Span("s", ("3", "3.1"), 10, 12)


def test_a_different_source_never_overlaps():
    assert overlaps(Span("a", ("1",), 1, 2), Span("b", ("1",), 1, 2)) is False


def test_page_ranges_overlap_inclusively():
    expected = Span("s", ("3",), 10, 12)
    assert overlaps(expected, Span("s", ("9",), 12, 15)) is True    # touching at 12
    assert overlaps(expected, Span("s", ("9",), 13, 15)) is False
    assert overlaps(expected, Span("s", ("3",), 1, 2)) is False     # pages win when both


def test_section_path_decides_when_either_side_has_no_pages():
    expected = Span("s", ("3", "3.1"), None, None)
    assert overlaps(expected, Span("s", ("3", "3.1"), 1, 2)) is True
    assert overlaps(expected, Span("s", ("3", "3.2"), 1, 2)) is False


def test_an_ancestor_section_counts_as_covering_a_descendant():
    # A larger chunk size merges subsections upward; the merged chunk still contains the
    # passage the golden entry pointed at.
    expected = Span("s", ("3", "3.1", "3.1.2"), None, None)
    assert overlaps(expected, Span("s", ("3", "3.1"), None, None)) is True
    assert overlaps(expected, Span("s", ("4",), None, None)) is False


def test_span_relevance_falls_back_to_source_matching_for_survey_entries():
    relevant = make_span_relevance({})
    entry = {"id": "q", "expected_sources": ["s"]}
    assert relevant(entry, _chunk(source_id="s")) is True
    assert relevant(entry, _chunk(source_id="other")) is False


def test_span_relevance_uses_the_loaded_spans_for_chunk_entries():
    relevant = make_span_relevance({"q": (Span("s", ("3", "3.1"), None, None),)})
    entry = {"id": "q", "expected_chunks": ["s#c1"]}
    assert relevant(entry, _chunk(section_path=("3", "3.1"))) is True
    assert relevant(entry, _chunk(section_path=("7",))) is False


def test_an_entry_with_no_resolvable_span_matches_nothing():
    # Better a hard zero for one query than a silent fallback to source-level matching,
    # which would inflate an exact-term query into a hit-rate.
    relevant = make_span_relevance({})
    assert relevant({"id": "q", "expected_chunks": ["s#c1"]}, _chunk()) is False


@pytest.mark.db
def test_load_expected_spans_resolves_against_the_production_corpus(searchable):
    # `searchable` (from tests/test_search.py's pattern) seeds sources "s" and "t" with
    # book-page chunks; import the fixture into this module's conftest rather than
    # re-seeding, so the span rule is exercised against real stored rows.
    spans = load_expected_spans(searchable, [{"id": "q",
                                              "expected_chunks": ["s#c00000"]}])
    assert spans["q"][0].source_id == "s"
    assert spans["q"][0].page_start == 1


@pytest.mark.db
def test_an_unresolvable_chunk_id_is_simply_absent(searchable):
    assert load_expected_spans(searchable,
                               [{"id": "q", "expected_chunks": ["nope#c1"]}]) == {}
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_relevance.py -v`
Expected: FAIL — `ModuleNotFoundError: ... benchmark.relevance`.

- [x] **Step 3: Implement `relevance.py`**

```python
from dataclasses import dataclass
from typing import Callable
from langatlas_ingest.store import SourceChunk, SourceChunksStore


@dataclass(frozen=True)
class Span:
    """Where a chunk sits in its document, in the two coordinate systems the corpus
    actually carries and that survive a re-chunking: the page range (PDF-derived sources)
    and the outline path (HTML/section-derived sources). Chunk ids do not survive; these
    do, which is the whole reason this type exists."""

    source_id: str
    section_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None

    @property
    def paged(self) -> bool:
        return self.page_start is not None and self.page_end is not None


def span_of(chunk: SourceChunk) -> Span:
    return Span(source_id=chunk.source_id,
                section_path=tuple(chunk.section_path or ()),
                page_start=chunk.page_start, page_end=chunk.page_end)


def overlaps(expected: Span, candidate: Span) -> bool:
    """Does `candidate` cover the region `expected` occupies?

    Pages first when both sides have them — a page range is the finer and less ambiguous
    signal, and a differently-sized chunk of the same pages is exactly what the chunk-size
    axis is varying. Otherwise the outline path, where an *ancestor* counts: a larger
    chunk size merges subsections upward, and the merged chunk genuinely contains the
    passage the golden entry pointed at. A descendant does not count in the other
    direction by accident — `section_path` prefix containment is asymmetric on purpose.
    """
    if expected.source_id != candidate.source_id:
        return False
    if expected.paged and candidate.paged:
        return (candidate.page_start <= expected.page_end
                and expected.page_start <= candidate.page_end)
    if not expected.section_path or not candidate.section_path:
        return False
    return (expected.section_path[:len(candidate.section_path)]
            == candidate.section_path)


def load_expected_spans(prod_conn, entries: list[dict]) -> dict[str, tuple[Span, ...]]:
    """Resolve every `expected_chunks` id against the *production* corpus — the one
    chunking in which those ids exist. Entries whose ids resolve to nothing are simply
    absent from the result, and `make_span_relevance` then matches nothing for them:
    a query whose target cannot be located is unscorable, and pretending otherwise would
    move the arm's recall for a reason that has nothing to do with chunk size.
    """
    store = SourceChunksStore(prod_conn)
    spans: dict[str, tuple[Span, ...]] = {}
    for entry in entries:
        resolved = [span_of(chunk) for chunk
                    in (store.get(chunk_id)
                        for chunk_id in entry.get("expected_chunks") or [])
                    if chunk is not None]
        if resolved:
            spans[entry["id"]] = tuple(resolved)
    return spans


def make_span_relevance(spans: dict[str, tuple[Span, ...]]) \
        -> Callable[[dict, SourceChunk], bool]:
    """A `run_eval(relevance=...)` predicate for a re-chunked corpus.

    `expected_sources` entries keep source-level matching unchanged — a source id is
    chunking-independent already, so there is nothing to translate.
    """
    def relevant(entry: dict, chunk: SourceChunk) -> bool:
        if entry.get("expected_sources"):
            return chunk.source_id in entry["expected_sources"]
        candidate = span_of(chunk)
        return any(overlaps(expected, candidate)
                   for expected in spans.get(entry.get("id"), ()))

    return relevant
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_relevance.py -v -m "db or not db"`
Expected: PASS (9 tests; the last needs `-m db` and the compose Postgres).

- [x] **Step 5: Sanity-check the rule against production itself**

The span rule must be a *superset* of chunk-id equality when applied to the unchanged corpus —
if it is not, the secondary axis is scored on a looser rule than the primary one and the two
cannot be compared:

```bash
uv --directory tools/ingest run python -c "
from langatlas_ingest.benchmark.relevance import load_expected_spans, make_span_relevance
from langatlas_ingest.db import connect
from langatlas_ingest.eval import load_entries, _relevant
from langatlas_ingest.paths import GOLDEN_RETRIEVAL_DIR
from langatlas_ingest.store import SourceChunksStore
entries = load_entries(GOLDEN_RETRIEVAL_DIR)
with connect() as conn:
    spans = load_expected_spans(conn, entries)
    span_relevant, store = make_span_relevance(spans), SourceChunksStore(conn)
    bad = []
    for entry in entries:
        for chunk_id in entry.get('expected_chunks') or []:
            chunk = store.get(chunk_id)
            if chunk is None:
                bad.append(f'{entry[\"id\"]}: {chunk_id} missing'); continue
            if not span_relevant(entry, chunk):
                bad.append(f'{entry[\"id\"]}: span rule rejects its own target {chunk_id}')
    print('\n'.join(bad) or f'OK: span rule accepts all {len(spans)} resolved targets')"
```

Expected: `OK: span rule accepts all 40 resolved targets` (40 = the golden entries that use
`expected_chunks`). Any rejection is a bug in `overlaps`, not a corpus finding.

- [x] **Step 6: Commit**

```bash
git add tools/ingest/src/langatlas_ingest/benchmark/relevance.py \
        tools/ingest/tests/test_benchmark_relevance.py \
        tools/ingest/tests/conftest.py tools/ingest/tests/test_search.py \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): score re-chunked arms against document spans"
```

---

## Task 10: Indexing throughput and storage

§8.6 asks for two metrics `EvalResult` does not carry: **indexing throughput** and **storage**.
Both are properties of the embed pass, not of retrieval, so they are measured where the embedding
happens.

Throughput measured over a warm cache is not throughput — the content-addressed cache would
return every vector in milliseconds and report a fictional 10,000 chunks/second. So the cache-hit
count rides alongside, and the arm's result carries an explicit `throughput_honest` flag rather
than a number the reader has to second-guess.

**Files:**
- Create: `tools/ingest/src/langatlas_ingest/benchmark/metrics.py`
- Create: `tools/ingest/tests/test_benchmark_metrics.py`

**Interfaces:**
- Consumes: `embed.embed_source`, `db.embedding_table_name`, `ctx.embed`,
  `ctx.embedding_truncations`, `ctx.embedding_cache_hits`, `store.SourceChunksStore`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class IndexStats:
      model: str
      chunks: int
      tokens: int
      embed_seconds: float
      chunks_per_second: float | None
      tokens_per_second: float | None
      truncated_chunks: int
      cached_vectors: int
      throughput_honest: bool
      table_bytes: int
      bytes_per_chunk: float | None
      dimensions: int
      def as_dict(self) -> dict

  def table_bytes(conn, table: str) -> int
  def corpus_size(conn, sources: Sequence[str]) -> tuple[int, int]     # (chunks, tokens)
  def embed_and_measure(ctx, conn, *, model: str, sources: Sequence[str],
                        config: IngestConfig, batch_size: int = 32,
                        truncate: bool = False) -> IndexStats
  ```

- [x] **Step 1: Teach the shared `FakeCtx` the new embedding contract**

`embed_and_measure` reads the truncation and cache-hit counters off the context, so
`tools/ingest/tests/conftest.py`'s `FakeCtx` has to carry them (and accept Task 2's `truncate`
keyword, which `embed_source` now passes through):

```python
class FakeCtx:
    def __init__(self, dimensions: int = 4):
        ...                                   # existing body unchanged
        self.truncations = 0
        self.cache_hits = 0

    def embed(self, texts, *, model, truncate: bool = False,
              max_input_tokens: int | None = None):
        # `truncate` is accepted and ignored: this fake has no window, and the point of
        # the benchmark's counter plumbing is that the *stats* read the context, not that
        # the fake reimplements truncation.
        self.embed_calls.append(list(texts))
        return [[float(len(text) % 10) / 10] + [0.0] * (self.dimensions - 1)
                for text in texts]

    @property
    def embedding_truncations(self) -> int:
        return self.truncations

    @property
    def embedding_cache_hits(self) -> int:
        return self.cache_hits
```

Run `uv --directory tools/ingest run pytest -m "db or not db"` before writing anything new: the
whole existing suite must still pass.

- [x] **Step 2: Write the failing tests**

Create `tools/ingest/tests/test_benchmark_metrics.py`:

```python
import pytest
from langatlas_ingest.benchmark.metrics import IndexStats, corpus_size, table_bytes


def test_index_stats_derive_their_rates():
    stats = IndexStats(model="m", chunks=100, tokens=50_000, embed_seconds=10.0,
                       chunks_per_second=None, tokens_per_second=None,
                       truncated_chunks=7, cached_vectors=0, throughput_honest=True,
                       table_bytes=1_000_000, bytes_per_chunk=None, dimensions=384)
    payload = stats.as_dict()
    assert payload["truncated_chunks"] == 7
    assert payload["throughput_honest"] is True


def test_rates_are_none_when_nothing_was_embedded():
    from langatlas_ingest.benchmark.metrics import derive_rates

    stats = derive_rates(IndexStats(model="m", chunks=0, tokens=0, embed_seconds=0.0,
                                    chunks_per_second=None, tokens_per_second=None,
                                    truncated_chunks=0, cached_vectors=0,
                                    throughput_honest=True, table_bytes=0,
                                    bytes_per_chunk=None, dimensions=4))
    assert stats.chunks_per_second is None and stats.bytes_per_chunk is None


def test_rates_are_computed_when_work_happened():
    from langatlas_ingest.benchmark.metrics import derive_rates

    stats = derive_rates(IndexStats(model="m", chunks=100, tokens=1000,
                                    embed_seconds=4.0, chunks_per_second=None,
                                    tokens_per_second=None, truncated_chunks=0,
                                    cached_vectors=0, throughput_honest=True,
                                    table_bytes=800, bytes_per_chunk=None,
                                    dimensions=4))
    assert stats.chunks_per_second == 25.0
    assert stats.tokens_per_second == 250.0
    assert stats.bytes_per_chunk == 8.0


def test_throughput_is_marked_dishonest_when_the_cache_served_anything():
    from langatlas_ingest.benchmark.metrics import derive_rates

    stats = derive_rates(IndexStats(model="m", chunks=100, tokens=1000,
                                    embed_seconds=0.01, chunks_per_second=None,
                                    tokens_per_second=None, truncated_chunks=0,
                                    cached_vectors=40, throughput_honest=True,
                                    table_bytes=800, bytes_per_chunk=None,
                                    dimensions=4))
    assert stats.throughput_honest is False


@pytest.mark.db
def test_corpus_size_sums_chunks_and_tokens(searchable):
    chunks, tokens = corpus_size(searchable, ["s"])
    assert chunks > 0 and tokens > 0
    assert corpus_size(searchable, ["absent"]) == (0, 0)


@pytest.mark.db
def test_table_bytes_reports_zero_for_a_missing_table(db_conn):
    assert table_bytes(db_conn, "source_chunk_emb_nothing_here") == 0


@pytest.mark.db
def test_embed_and_measure_reads_the_counters_off_the_context(searchable, fake_ctx):
    # `fake_ctx` never truncates, so this pins the plumbing rather than the arithmetic:
    # the stats must read the counters off the context, not recompute them.
    from langatlas_ingest.benchmark.metrics import embed_and_measure
    from langatlas_ingest.config import IngestConfig

    fake_ctx.truncations = 3
    stats = embed_and_measure(fake_ctx, searchable, model="fake-model", sources=["s"],
                              config=IngestConfig.load(), truncate=True)
    assert stats.model == "fake-model"
    assert stats.chunks > 0
    assert stats.table_bytes > 0
    assert stats.truncated_chunks == 0     # nothing changed *during* the pass
    assert stats.dimensions == 4
```

- [x] **Step 3: Run the tests to verify they fail**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: ... benchmark.metrics`.

- [x] **Step 4: Implement `metrics.py`**

```python
import time
from dataclasses import dataclass, replace
from typing import Sequence
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import embedding_table_name
from langatlas_ingest.embed import embed_source


@dataclass(frozen=True)
class IndexStats:
    """§8.6's indexing-throughput and storage metrics, plus the two numbers that say
    whether they can be believed: how many chunks the model had to be fed truncated, and
    how many vectors came from the cache instead of the provider."""

    model: str
    chunks: int
    tokens: int
    embed_seconds: float
    chunks_per_second: float | None
    tokens_per_second: float | None
    truncated_chunks: int
    cached_vectors: int
    throughput_honest: bool
    table_bytes: int
    bytes_per_chunk: float | None
    dimensions: int

    def as_dict(self) -> dict:
        return {"model": self.model, "chunks": self.chunks, "tokens": self.tokens,
                "embed_seconds": round(self.embed_seconds, 3),
                "chunks_per_second": self.chunks_per_second,
                "tokens_per_second": self.tokens_per_second,
                "truncated_chunks": self.truncated_chunks,
                "truncated_share": (self.truncated_chunks / self.chunks
                                    if self.chunks else None),
                "cached_vectors": self.cached_vectors,
                "throughput_honest": self.throughput_honest,
                "table_bytes": self.table_bytes,
                "bytes_per_chunk": self.bytes_per_chunk,
                "dimensions": self.dimensions}


def derive_rates(stats: IndexStats) -> IndexStats:
    """Rates are `None`, never 0.0, when there is no denominator — an unmeasured
    throughput and a measured zero would otherwise be the same cell in the results table.

    `throughput_honest` goes false the moment *any* vector came from the cache: a partly
    warm run's wall time is a blend of provider latency and SQLite reads, and there is no
    principled way to unblend it. The number is still recorded; the flag says not to rank
    on it.
    """
    honest = stats.throughput_honest and stats.cached_vectors == 0
    return replace(
        stats,
        chunks_per_second=(stats.chunks / stats.embed_seconds
                           if stats.chunks and stats.embed_seconds > 0 else None),
        tokens_per_second=(stats.tokens / stats.embed_seconds
                           if stats.tokens and stats.embed_seconds > 0 else None),
        bytes_per_chunk=(stats.table_bytes / stats.chunks if stats.chunks else None),
        throughput_honest=honest)


def table_bytes(conn, table: str) -> int:
    """Heap + indexes + TOAST. §8.6 asks for 'storage', and a vector table's HNSW index
    is routinely larger than its heap — reporting the heap alone would understate a
    2560-dim model against a 384-dim one by exactly the amount that matters."""
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(pg_total_relation_size(to_regclass(%s)), 0)",
                    (table,))
        return int(cur.fetchone()[0])


def corpus_size(conn, sources: Sequence[str]) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), COALESCE(sum(token_count), 0) FROM source_chunks"
                    " WHERE source_id = ANY(%s)", (list(sources),))
        row = cur.fetchone()
    return int(row[0]), int(row[1])


def embed_and_measure(ctx, conn, *, model: str, sources: Sequence[str],
                      config: IngestConfig, batch_size: int = 32,
                      truncate: bool = False) -> IndexStats:
    """Embed the pilot on one candidate and time it.

    `embed_source` is reused rather than reimplemented: it is the code production runs,
    and a benchmark that measured a bespoke embed loop would be measuring the wrong thing.
    The model is threaded in through a config override for the same reason — a model id is
    configuration everywhere else too.
    """
    arm_config = replace(config, embedding_model=model)
    chunks, tokens = corpus_size(conn, sources)
    truncated_before = ctx.embedding_truncations
    cached_before = ctx.embedding_cache_hits

    began = time.monotonic()
    for source_id in sources:
        embed_source(ctx, conn, source_id=source_id, config=arm_config,
                     batch_size=batch_size, truncate=truncate)
    elapsed = time.monotonic() - began

    table = embedding_table_name(model)
    return derive_rates(IndexStats(
        model=model, chunks=chunks, tokens=tokens, embed_seconds=elapsed,
        chunks_per_second=None, tokens_per_second=None,
        truncated_chunks=ctx.embedding_truncations - truncated_before,
        cached_vectors=ctx.embedding_cache_hits - cached_before,
        throughput_honest=True, table_bytes=table_bytes(conn, table),
        bytes_per_chunk=None,
        dimensions=ctx.config.embedding(model).dimensions))
```

`embed_source` needs the `truncate` flag threaded through. In
`tools/ingest/src/langatlas_ingest/embed.py`, add the parameter and pass it on:

```python
def embed_source(ctx, conn, *, source_id: str | None = None,
                 config: IngestConfig | None = None, batch_size: int = 32,
                 truncate: bool = False) -> int:
```
```python
        vectors = ctx.embed([chunk.text for chunk in batch], model=model,
                            truncate=truncate)
```

and extend its docstring with:

```
    `truncate` is off by default and stays off in production: a chunk the model could
    only half-read produces a vector that misrepresents it. §8.6's benchmark turns it on
    for the short-context candidates, which is the only honest way to measure them at all
    (see `EmbeddingClient.embed`).
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_metrics.py -v -m "db or not db"`
Expected: PASS (7 tests).

- [x] **Step 6: Run the ingest suite for regressions**

Run: `uv --directory tools/ingest run pytest && uv --directory tools/ingest run pytest -m db`
Expected: PASS — `embed_source`'s new parameter is keyword-only with a default, so `_cmd_embed`
is unaffected.

- [x] **Step 7: Commit**

```bash
git add tools/ingest/src/langatlas_ingest/benchmark/metrics.py \
        tools/ingest/src/langatlas_ingest/embed.py \
        tools/ingest/tests/test_benchmark_metrics.py tools/ingest/tests/conftest.py \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): measure indexing throughput and index storage"
```

---

## Task 11: The arm runner

Eighteen primary arms against a slow university API, each embedding 3,826 chunks and running up
to 37 reranked queries. It will take hours, it will be interrupted, and a run that loses its work
on an interruption is a run nobody finishes. So the runner is resumable by construction: an arm's
result is a committed JSON file, and an arm whose file exists is skipped.

Each arm gets its own `RunContext` — one transcript per arm (D18), one budget per arm, and one
alias pinning per arm.

**Files:**
- Create: `tools/ingest/src/langatlas_ingest/benchmark/runner.py`
- Create: `tools/ingest/tests/test_benchmark_runner.py`

**Interfaces:**
- Consumes: `Arm`, `Matrix`, `IndexStats`, `embed_and_measure`, `run_eval`, `SourceSearch`,
  `make_span_relevance`, `load_expected_spans`, `load_entries`, `RunContext`, `Budget`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class ArmResult:
      arm: Arm
      index: IndexStats
      metrics: dict                 # EvalResult.as_dict()
      pilot_sources: tuple[str, ...]
      run_id: str
      finished: str                 # ISO-8601 UTC
      def as_dict(self) -> dict
      @classmethod
      def from_dict(cls, payload: dict) -> "ArmResult"
      @property
      def recall_at_5_pts(self) -> float | None
      @property
      def ndcg_at_10_pts(self) -> float | None

  def write_result(result: ArmResult, root: Path) -> Path
  def load_results(root: Path) -> dict[str, ArmResult]
  def run_arm(conn, arm: Arm, *, matrix: Matrix, config: IngestConfig,
              prod_conn=None, span_relevance: bool = False) -> ArmResult
  def run_matrix(conn, arms: Sequence[Arm], *, matrix: Matrix, config: IngestConfig,
                 prod_conn=None, resume: bool = True,
                 span_relevance: bool = False) -> list[ArmResult]
  ```

- [x] **Step 1: Write the failing tests**

Create `tools/ingest/tests/test_benchmark_runner.py`:

```python
import json
import pytest
from pathlib import Path
from langatlas_ingest.benchmark.arms import Arm
from langatlas_ingest.benchmark.metrics import IndexStats
from langatlas_ingest.benchmark.runner import (
    ArmResult, load_results, write_result,
)

ARM = Arm(embedding_model="m", mode="hybrid", rerank=True, chunk_target_tokens=600,
          chunk_max_tokens=800, truncate=False)
STATS = IndexStats(model="m", chunks=10, tokens=100, embed_seconds=2.0,
                   chunks_per_second=5.0, tokens_per_second=50.0, truncated_chunks=0,
                   cached_vectors=0, throughput_honest=True, table_bytes=80,
                   bytes_per_chunk=8.0, dimensions=4)


def _result(**overrides) -> ArmResult:
    payload = {"arm": ARM, "index": STATS,
               "metrics": {"queries": 5, "recall_at_5": 0.8, "recall_at_50": 0.95,
                           "mrr": 0.7, "ndcg_at_10": 0.6, "latency_p50_ms": 40.0,
                           "skipped_queries": 2, "per_query": []},
               "pilot_sources": ("s1",), "run_id": "r1", "finished": "2026-09-05T00:00:00Z"}
    payload.update(overrides)
    return ArmResult(**payload)


def test_points_properties_convert_fractions_once():
    result = _result()
    assert result.recall_at_5_pts == 80.0
    assert result.ndcg_at_10_pts == 60.0


def test_points_are_none_when_the_metric_is():
    result = _result(metrics={"recall_at_5": None, "ndcg_at_10": None})
    assert result.recall_at_5_pts is None and result.ndcg_at_10_pts is None


def test_result_round_trips_through_json(tmp_path: Path):
    path = write_result(_result(), tmp_path)
    assert path.name == f"{ARM.arm_id}.json"
    restored = ArmResult.from_dict(json.loads(path.read_text()))
    assert restored.arm == ARM
    assert restored.index.table_bytes == 80
    assert restored.metrics["recall_at_5"] == 0.8


def test_written_json_is_stable_and_readable(tmp_path: Path):
    first = write_result(_result(), tmp_path).read_text()
    second = write_result(_result(), tmp_path).read_text()
    assert first == second                # sorted keys, fixed indent: diffable
    assert first.endswith("\n")


def test_load_results_is_keyed_by_arm_id(tmp_path: Path):
    write_result(_result(), tmp_path)
    results = load_results(tmp_path)
    assert list(results) == [ARM.arm_id]


def test_load_results_ignores_non_json_files(tmp_path: Path):
    write_result(_result(), tmp_path)
    (tmp_path / "README.md").write_text("notes")
    assert list(load_results(tmp_path)) == [ARM.arm_id]


def test_run_matrix_skips_an_arm_that_already_has_a_result(tmp_path: Path,
                                                            monkeypatch):
    from langatlas_ingest.benchmark import runner

    write_result(_result(), tmp_path)
    calls = []
    monkeypatch.setattr(runner, "run_arm",
                        lambda *a, **k: calls.append(k) or _result())
    matrix = type("M", (), {"results_dir": tmp_path, "pilot_sources": ("s1",),
                            "golden_dir": tmp_path})()
    results = runner.run_matrix(None, [ARM], matrix=matrix, config=None, resume=True)
    assert calls == []                    # skipped
    assert len(results) == 1              # but still reported


def test_run_matrix_reruns_when_resume_is_off(tmp_path: Path, monkeypatch):
    from langatlas_ingest.benchmark import runner

    write_result(_result(), tmp_path)
    calls = []
    monkeypatch.setattr(runner, "run_arm",
                        lambda *a, **k: calls.append(k) or _result())
    matrix = type("M", (), {"results_dir": tmp_path, "pilot_sources": ("s1",),
                            "golden_dir": tmp_path})()
    runner.run_matrix(None, [ARM], matrix=matrix, config=None, resume=False)
    assert len(calls) == 1
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: ... benchmark.runner`.

- [x] **Step 3: Implement `runner.py`**

```python
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence
from langatlas_ingest.benchmark.arms import Arm, Matrix
from langatlas_ingest.benchmark.metrics import IndexStats, embed_and_measure
from langatlas_ingest.benchmark.relevance import (
    load_expected_spans, make_span_relevance,
)
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.eval import load_entries, run_eval
from langatlas_ingest.search import SourceSearch
from langatlas_pipeline.providers.core import Budget, RunContext
from langatlas_pipeline.transcripts.writer import utc_now


def _pts(value) -> float | None:
    """§8.6 states every margin in percentage points; the metrics are fractions. Convert
    at exactly one boundary — this one — so no comparison anywhere has to remember."""
    return None if value is None else float(value) * 100.0


@dataclass(frozen=True)
class ArmResult:
    arm: Arm
    index: IndexStats
    metrics: dict
    pilot_sources: tuple[str, ...]
    run_id: str
    finished: str

    @property
    def recall_at_5_pts(self) -> float | None:
        return _pts(self.metrics.get("recall_at_5"))

    @property
    def recall_at_50_pts(self) -> float | None:
        return _pts(self.metrics.get("recall_at_50"))

    @property
    def ndcg_at_10_pts(self) -> float | None:
        return _pts(self.metrics.get("ndcg_at_10"))

    def as_dict(self) -> dict:
        return {"arm": self.arm.as_dict(), "index": self.index.as_dict(),
                "metrics": self.metrics, "pilot_sources": list(self.pilot_sources),
                "run_id": self.run_id, "finished": self.finished}

    @classmethod
    def from_dict(cls, payload: dict) -> "ArmResult":
        arm = {key: value for key, value in payload["arm"].items() if key != "arm_id"}
        index = dict(payload["index"])
        index.pop("truncated_share", None)      # derived on write, not a constructor field
        return cls(arm=Arm(**arm), index=IndexStats(**index), metrics=payload["metrics"],
                   pilot_sources=tuple(payload["pilot_sources"]),
                   run_id=payload["run_id"], finished=payload["finished"])


def write_result(result: ArmResult, root: Path) -> Path:
    """One file per arm, sorted keys, trailing newline: these are committed, so they have
    to diff cleanly and re-serialise identically when an arm is re-run unchanged."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = result.arm.result_path(root)
    path.write_text(json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n")
    return path


def load_results(root: Path) -> dict[str, ArmResult]:
    results: dict[str, ArmResult] = {}
    for path in sorted(Path(root).glob("*.json")):
        result = ArmResult.from_dict(json.loads(path.read_text()))
        results[result.arm.arm_id] = result
    return results


def run_arm(conn, arm: Arm, *, matrix: Matrix, config: IngestConfig,
            prod_conn=None, span_relevance: bool = False) -> ArmResult:
    """Embed the pilot on this arm's model, then score the golden set through it.

    One `RunContext` per arm: one transcript (D18), one budget, one alias pinning. The
    budget is generous but finite — an arm that somehow starts re-embedding the whole
    corpus should stop rather than spend the night doing it.
    """
    entries = load_entries(matrix.golden_dir)
    relevance = None
    if span_relevance:
        if prod_conn is None:
            raise ValueError("span relevance needs a production connection to resolve"
                             " the golden set's chunk ids against")
        relevance = make_span_relevance(load_expected_spans(prod_conn, entries))

    # Only the model rides the config. The mode and the rerank flag vary per arm while
    # the config object is shared, so they reach `SourceSearch` as explicit arguments.
    arm_config = replace(config, embedding_model=arm.embedding_model)

    with RunContext.start(kind="benchmark", slug=arm.arm_id,
                          budget=Budget(max_calls=5000, max_wall_seconds=14400)) as ctx:
        index = embed_and_measure(ctx, conn, model=arm.embedding_model,
                                  sources=matrix.pilot_sources, config=arm_config,
                                  truncate=arm.truncate)
        search = SourceSearch(conn, ctx, config=arm_config, rerank=arm.rerank,
                              mode=arm.mode)
        evaluated = run_eval(conn, ctx, golden_dir=matrix.golden_dir, config=arm_config,
                             depth=arm.depth, corpus_sources=matrix.pilot_sources,
                             relevance=relevance, search=search)
        run_id = ctx.run_id

    return ArmResult(arm=arm, index=index, metrics=evaluated.as_dict(),
                     pilot_sources=tuple(matrix.pilot_sources), run_id=run_id,
                     finished=utc_now())


def run_matrix(conn, arms: Sequence[Arm], *, matrix: Matrix, config: IngestConfig,
               prod_conn=None, resume: bool = True,
               span_relevance: bool = False) -> list[ArmResult]:
    """Eighteen arms against a slow API is an overnight job that *will* be interrupted.
    An arm's committed result file is its checkpoint: re-invoking picks up where it
    stopped, which is the same resumption model `embed_source` and the orchestrator's
    `CheckpointStore` already use."""
    existing = load_results(matrix.results_dir) if resume else {}
    results: list[ArmResult] = []
    for arm in arms:
        cached = existing.get(arm.arm_id)
        if cached is not None:
            print(f"{arm.arm_id}: already scored, skipping")
            results.append(cached)
            continue
        print(f"{arm.arm_id}: running")
        result = run_arm(conn, arm, matrix=matrix, config=config, prod_conn=prod_conn,
                         span_relevance=span_relevance)
        write_result(result, matrix.results_dir)
        results.append(result)
    return results
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_runner.py -v`
Expected: PASS (8 tests).

- [x] **Step 5: Commit**

```bash
git add tools/ingest/src/langatlas_ingest/benchmark/runner.py \
        tools/ingest/tests/test_benchmark_runner.py \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): run and checkpoint the benchmark arms"
```

---

## Task 12: The verdict rules

§8.6's decision rules are stated precisely enough to be code, and code is what they should be:
a benchmark whose conclusion is drawn by eye is a benchmark whose conclusion is drawn by whoever
is looking. `decide()` reads the arm results and applies the rules mechanically; the developer's
job is to *adopt* the verdict, not to derive it.

The rules, in the order `decide` applies them:

1. **Model.** Compare models on their best `hybrid+rerank` Recall@5. A **local** model that comes
   within `local_match_recall5_pts` of the incumbent wins (free-and-local is the preferred floor,
   plan decision 3). Otherwise a challenger wins only by beating the incumbent by at least
   `beat_incumbent_recall5_pts`. Otherwise the incumbent stays.
2. **Reranker.** Default-on stays unless `ndcg@10(hybrid+rerank) − ndcg@10(hybrid)` is below
   `rerank_min_ndcg_pts` for the chosen model.
3. **Mode.** Hybrid stays unless `recall@5(hybrid, no rerank) − recall@5(vector)` is below
   `hybrid_min_recall5_pts` for the chosen model.
4. **Chunk size.** 600/800 stays unless a secondary arm beats the chosen model's primary
   `hybrid+rerank` Recall@5 by at least `chunk_size_min_recall5_pts` (plan decision 2).

A missing arm is never decided around: `decide` raises `IncompleteMatrix` naming exactly which
arm ids are absent.

**Files:**
- Create: `tools/ingest/src/langatlas_ingest/benchmark/verdict.py`
- Create: `tools/ingest/tests/test_benchmark_verdict.py`
- Modify: `tools/ingest/src/langatlas_ingest/errors.py`

**Interfaces:**
- Consumes: `Arm`, `Matrix`, `Margins`, `ArmResult`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class Verdict:
      table: str                    # "source-corpus"
      incumbent: str
      model: str
      dimensions: int
      index_type: str
      mode: str
      rerank: bool
      chunk_target_tokens: int
      chunk_max_tokens: int
      pilot_sources: tuple[str, ...]
      queries_scored: int
      moved: bool                   # does anything differ from the incumbent config?
      rationale: tuple[str, ...]
      def to_markdown(self) -> str
      def as_dict(self) -> dict

  def decide(results: dict[str, ArmResult], *, matrix: Matrix,
             index_type: str = "hnsw-halfvec-cosine") -> Verdict

  class IncompleteMatrix(IngestError):
      def __init__(self, missing: list[str])
  ```

- [ ] **Step 1: Write the failing tests**

Create `tools/ingest/tests/test_benchmark_verdict.py`:

```python
import pytest
from pathlib import Path
from langatlas_ingest.benchmark.arms import Arm, Margins, Matrix
from langatlas_ingest.benchmark.metrics import IndexStats
from langatlas_ingest.benchmark.runner import ArmResult
from langatlas_ingest.benchmark.verdict import decide
from langatlas_ingest.errors import IncompleteMatrix

INCUMBENT, CHALLENGER, LOCAL = "inc", "cha", "local:tiny"


def _matrix(**overrides) -> Matrix:
    arms = []
    for model in (INCUMBENT, CHALLENGER, LOCAL):
        for mode, rerank in (("vector", False), ("hybrid", False), ("hybrid", True)):
            arms.append(Arm(embedding_model=model, mode=mode, rerank=rerank,
                            chunk_target_tokens=600, chunk_max_tokens=800,
                            truncate=False))
    defaults = dict(pilot_sources=("s1",), golden_dir=Path("g"),
                    results_dir=Path("r"), incumbent=INCUMBENT,
                    local_models=(LOCAL,), margins=Margins(), primary=tuple(arms),
                    primary_chunk_size=(600, 800),
                    chunk_sizes=((400, 550), (800, 1050)))
    defaults.update(overrides)
    return Matrix(**defaults)


def _result(arm: Arm, *, recall5: float, ndcg: float = 0.5,
            dimensions: int = 8) -> ArmResult:
    return ArmResult(
        arm=arm,
        index=IndexStats(model=arm.embedding_model, chunks=10, tokens=100,
                         embed_seconds=1.0, chunks_per_second=10.0,
                         tokens_per_second=100.0, truncated_chunks=0, cached_vectors=0,
                         throughput_honest=True, table_bytes=80, bytes_per_chunk=8.0,
                         dimensions=dimensions),
        metrics={"queries": 30, "recall_at_5": recall5, "recall_at_50": 0.9, "mrr": 0.5,
                 "ndcg_at_10": ndcg, "latency_p50_ms": 10.0, "skipped_queries": 0,
                 "per_query": []},
        pilot_sources=("s1",), run_id="r", finished="2026-09-05T00:00:00Z")


def _results(matrix: Matrix, table: dict) -> dict:
    """`table` maps (model, mode, rerank) -> (recall5, ndcg)."""
    out = {}
    for arm in matrix.primary:
        recall5, ndcg = table[(arm.embedding_model, arm.mode, arm.rerank)]
        out[arm.arm_id] = _result(arm, recall5=recall5, ndcg=ndcg)
    return out


BASE = {
    (INCUMBENT, "vector", False): (0.60, 0.50),
    (INCUMBENT, "hybrid", False): (0.70, 0.55),
    (INCUMBENT, "hybrid", True): (0.75, 0.65),
    (CHALLENGER, "vector", False): (0.58, 0.48),
    (CHALLENGER, "hybrid", False): (0.68, 0.53),
    (CHALLENGER, "hybrid", True): (0.72, 0.62),
    (LOCAL, "vector", False): (0.40, 0.35),
    (LOCAL, "hybrid", False): (0.50, 0.42),
    (LOCAL, "hybrid", True): (0.55, 0.48),
}


def test_incumbent_stays_when_nobody_clears_the_margin():
    matrix = _matrix()
    verdict = decide(_results(matrix, BASE), matrix=matrix)
    assert verdict.model == INCUMBENT
    assert verdict.moved is False
    assert any("stays" in line for line in verdict.rationale)


def test_a_challenger_needs_five_points_not_four():
    matrix = _matrix()
    near = dict(BASE, **{(CHALLENGER, "hybrid", True): (0.79, 0.68)})   # +4 pts
    assert decide(_results(matrix, near), matrix=matrix).model == INCUMBENT
    far = dict(BASE, **{(CHALLENGER, "hybrid", True): (0.80, 0.68)})    # +5 pts exactly
    assert decide(_results(matrix, far), matrix=matrix).model == CHALLENGER


def test_a_local_model_within_two_points_wins_outright():
    matrix = _matrix()
    close = dict(BASE, **{(LOCAL, "hybrid", True): (0.73, 0.63)})       # -2 pts exactly
    verdict = decide(_results(matrix, close), matrix=matrix)
    assert verdict.model == LOCAL
    assert verdict.moved is True
    assert any("local" in line for line in verdict.rationale)


def test_a_local_model_three_points_behind_does_not_win():
    matrix = _matrix()
    far = dict(BASE, **{(LOCAL, "hybrid", True): (0.72, 0.62)})         # -3 pts
    assert decide(_results(matrix, far), matrix=matrix).model == INCUMBENT


def test_the_local_rule_is_checked_before_the_beat_by_five_rule():
    matrix = _matrix()
    both = dict(BASE, **{(CHALLENGER, "hybrid", True): (0.85, 0.70),
                         (LOCAL, "hybrid", True): (0.74, 0.64)})
    # The challenger beats the incumbent by 10 pts; the local model matches within 1.
    assert decide(_results(matrix, both), matrix=matrix).model == LOCAL


def test_the_reranker_is_turned_off_when_it_adds_under_two_ndcg_points():
    matrix = _matrix()
    weak = dict(BASE, **{(INCUMBENT, "hybrid", True): (0.75, 0.56)})    # +1 pt over 0.55
    verdict = decide(_results(matrix, weak), matrix=matrix)
    assert verdict.rerank is False
    assert verdict.moved is True


def test_the_reranker_stays_on_at_exactly_two_points():
    matrix = _matrix()
    exact = dict(BASE, **{(INCUMBENT, "hybrid", True): (0.75, 0.57)})   # +2 pts
    assert decide(_results(matrix, exact), matrix=matrix).rerank is True


def test_vector_only_wins_when_hybrid_adds_under_two_points():
    matrix = _matrix()
    flat = dict(BASE, **{(INCUMBENT, "hybrid", False): (0.61, 0.55)})   # +1 pt over 0.60
    verdict = decide(_results(matrix, flat), matrix=matrix)
    assert verdict.mode == "vector"


def test_a_missing_arm_raises_instead_of_deciding():
    matrix = _matrix()
    results = _results(matrix, BASE)
    results.pop(matrix.primary[0].arm_id)
    with pytest.raises(IncompleteMatrix) as caught:
        decide(results, matrix=matrix)
    assert matrix.primary[0].arm_id in str(caught.value)


def test_a_chunk_size_arm_moves_the_chunking_only_past_the_margin():
    matrix = _matrix()
    results = _results(matrix, BASE)
    for arm in matrix.chunk_size_arms(INCUMBENT, truncate=False):
        gain = 0.02 if arm.chunk_target_tokens == 400 else 0.00
        results[arm.arm_id] = _result(arm, recall5=0.75 + gain, ndcg=0.65)
    verdict = decide(results, matrix=matrix)
    assert verdict.chunk_target_tokens == 400
    assert verdict.chunk_max_tokens == 550


def test_chunk_size_arms_are_optional():
    matrix = _matrix()
    verdict = decide(_results(matrix, BASE), matrix=matrix)
    assert (verdict.chunk_target_tokens, verdict.chunk_max_tokens) == (600, 800)


def test_the_verdict_carries_the_pinned_index_identity():
    matrix = _matrix()
    verdict = decide(_results(matrix, BASE), matrix=matrix)
    assert verdict.dimensions == 8
    assert verdict.index_type == "hnsw-halfvec-cosine"
    assert verdict.table == "source-corpus"
    assert "queries scored" in verdict.to_markdown()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_verdict.py -v`
Expected: FAIL — `ModuleNotFoundError: ... benchmark.verdict`.

- [ ] **Step 3: Implement `verdict.py`**

```python
import json
from dataclasses import dataclass
from langatlas_ingest.benchmark.arms import Arm, Matrix
from langatlas_ingest.benchmark.runner import ArmResult
from langatlas_ingest.errors import IncompleteMatrix


@dataclass(frozen=True)
class Verdict:
    """§8.6's per-table verdict record. `table` is explicit because the rules are
    per-table by design: the fact index (§8.3/D62) runs its own benchmark at Stage 5 and
    may legitimately choose a different model."""

    table: str
    incumbent: str
    model: str
    dimensions: int
    index_type: str
    mode: str
    rerank: bool
    chunk_target_tokens: int
    chunk_max_tokens: int
    pilot_sources: tuple[str, ...]
    queries_scored: int
    moved: bool
    rationale: tuple[str, ...]

    def to_markdown(self) -> str:
        lines = [f"# D22 verdict — {self.table}", "",
                 f"- model: **{self.model}** ({self.dimensions}-dim)",
                 f"- index type: {self.index_type}",
                 f"- retrieval mode: {self.mode}",
                 f"- reranker default-on: {self.rerank}",
                 f"- chunking: target {self.chunk_target_tokens} /"
                 f" max {self.chunk_max_tokens} tokens",
                 f"- incumbent was: {self.incumbent}",
                 f"- configuration moved: {self.moved}",
                 f"- pilot: {', '.join(self.pilot_sources)}"
                 f" ({self.queries_scored} queries scored)", "",
                 "## Why", ""]
        lines += [f"- {line}" for line in self.rationale]
        lines += ["", "Recall figures come from a 4-source pilot: the distractor pool is "
                  "a fraction of production's, so they are comparative between arms, not "
                  "absolute predictions of production recall."]
        return "\n".join(lines) + "\n"

    def as_dict(self) -> dict:
        return {"table": self.table, "incumbent": self.incumbent, "model": self.model,
                "dimensions": self.dimensions, "index_type": self.index_type,
                "mode": self.mode, "rerank": self.rerank,
                "chunk_target_tokens": self.chunk_target_tokens,
                "chunk_max_tokens": self.chunk_max_tokens,
                "pilot_sources": list(self.pilot_sources),
                "queries_scored": self.queries_scored, "moved": self.moved,
                "rationale": list(self.rationale)}

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n"


def _require(results: dict[str, ArmResult], arms) -> None:
    missing = [arm.arm_id for arm in arms if arm.arm_id not in results]
    if missing:
        raise IncompleteMatrix(missing)


def _arm_for(matrix: Matrix, model: str, mode: str, rerank: bool) -> Arm:
    for arm in matrix.primary:
        if (arm.embedding_model, arm.mode, arm.rerank) == (model, mode, rerank):
            return arm
    raise IncompleteMatrix([f"{model}/{mode}/rerank={rerank} is not in the matrix"])


def decide(results: dict[str, ArmResult], *, matrix: Matrix,
           index_type: str = "hnsw-halfvec-cosine") -> Verdict:
    """§8.6's decision rules, applied mechanically.

    Mechanical on purpose: a benchmark whose conclusion is read off a table by eye is a
    benchmark whose conclusion depends on who is looking. The developer's checkpoint is
    *adopting* this verdict, not deriving it — and if a rule produces a result that feels
    wrong, the argument to have is about the rule, in the spec, not about this run.
    """
    _require(results, matrix.primary)
    margins = matrix.margins
    models = sorted({arm.embedding_model for arm in matrix.primary})
    rationale: list[str] = []

    def recall5(model: str, mode: str, rerank: bool) -> float:
        value = results[_arm_for(matrix, model, mode, rerank).arm_id].recall_at_5_pts
        if value is None:
            raise IncompleteMatrix([f"{model}/{mode}/rerank={rerank} scored no queries"])
        return value

    def ndcg(model: str, mode: str, rerank: bool) -> float:
        value = results[_arm_for(matrix, model, mode, rerank).arm_id].ndcg_at_10_pts
        if value is None:
            raise IncompleteMatrix([f"{model}/{mode}/rerank={rerank} scored no queries"])
        return value

    # --- rule 1: the model -----------------------------------------------------------
    incumbent_score = recall5(matrix.incumbent, "hybrid", True)
    locals_in_reach = sorted(
        ((recall5(model, "hybrid", True), model) for model in matrix.local_models
         if model in models
         and incumbent_score - recall5(model, "hybrid", True)
         <= margins.local_match_recall5_pts),
        reverse=True)
    challengers = sorted(
        ((recall5(model, "hybrid", True), model) for model in models
         if model != matrix.incumbent
         and recall5(model, "hybrid", True) - incumbent_score
         >= margins.beat_incumbent_recall5_pts),
        reverse=True)

    if locals_in_reach:
        score, chosen = locals_in_reach[0]
        rationale.append(
            f"local model {chosen} scored {score:.1f} pts Recall@5 against the"
            f" incumbent's {incumbent_score:.1f} — within the"
            f" {margins.local_match_recall5_pts:.0f}-point match rule, so free-and-local"
            " wins (§8.6)")
    elif challengers:
        score, chosen = challengers[0]
        rationale.append(
            f"{chosen} beat the incumbent {incumbent_score:.1f} -> {score:.1f} pts"
            f" Recall@5, clearing the {margins.beat_incumbent_recall5_pts:.0f}-point bar")
    else:
        chosen = matrix.incumbent
        best = max((recall5(model, "hybrid", True), model) for model in models
                   if model != matrix.incumbent)
        rationale.append(
            f"incumbent {chosen} stays at {incumbent_score:.1f} pts Recall@5; best"
            f" challenger {best[1]} reached {best[0]:.1f}, short of the"
            f" {margins.beat_incumbent_recall5_pts:.0f}-point bar, and no local model came"
            f" within {margins.local_match_recall5_pts:.0f}")

    # --- rule 2: the reranker --------------------------------------------------------
    rerank_gain = ndcg(chosen, "hybrid", True) - ndcg(chosen, "hybrid", False)
    rerank = rerank_gain >= margins.rerank_min_ndcg_pts
    rationale.append(
        f"reranker adds {rerank_gain:+.1f} pts nDCG@10 on {chosen} — "
        + ("stays default-on" if rerank
           else f"below the {margins.rerank_min_ndcg_pts:.0f}-point bar, so default-off"))

    # --- rule 3: hybrid vs vector ----------------------------------------------------
    hybrid_gain = recall5(chosen, "hybrid", False) - recall5(chosen, "vector", False)
    mode = "hybrid" if hybrid_gain >= margins.hybrid_min_recall5_pts else "vector"
    rationale.append(
        f"hybrid adds {hybrid_gain:+.1f} pts Recall@5 over vector-only on {chosen} — "
        + (f"stays hybrid" if mode == "hybrid"
           else f"below the {margins.hybrid_min_recall5_pts:.0f}-point bar, so"
                " vector-only"))

    # --- rule 4: chunk size ----------------------------------------------------------
    target, maximum = matrix.primary_chunk_size
    baseline = recall5(chosen, "hybrid", True)
    truncate = _arm_for(matrix, chosen, "hybrid", True).truncate
    for arm in matrix.chunk_size_arms(chosen, truncate=truncate):
        result = results.get(arm.arm_id)
        if result is None or result.recall_at_5_pts is None:
            continue
        gain = result.recall_at_5_pts - baseline
        if gain >= margins.chunk_size_min_recall5_pts and gain > 0:
            target, maximum, baseline = (arm.chunk_target_tokens, arm.chunk_max_tokens,
                                         result.recall_at_5_pts)
            rationale.append(
                f"chunking at {arm.chunk_target_tokens} tokens gained {gain:+.1f} pts"
                f" Recall@5, clearing the"
                f" {margins.chunk_size_min_recall5_pts:.0f}-point bar")
    if (target, maximum) == matrix.primary_chunk_size:
        rationale.append(
            f"chunking stays at {target}/{maximum} tokens — no secondary arm cleared the"
            f" {margins.chunk_size_min_recall5_pts:.0f}-point bar")

    chosen_result = results[_arm_for(matrix, chosen, "hybrid", True).arm_id]
    moved = (chosen != matrix.incumbent or not rerank or mode != "hybrid"
             or (target, maximum) != matrix.primary_chunk_size)
    return Verdict(
        table="source-corpus", incumbent=matrix.incumbent, model=chosen,
        dimensions=chosen_result.index.dimensions, index_type=index_type, mode=mode,
        rerank=rerank, chunk_target_tokens=target, chunk_max_tokens=maximum,
        pilot_sources=tuple(matrix.pilot_sources),
        queries_scored=int(chosen_result.metrics.get("queries") or 0), moved=moved,
        rationale=tuple(rationale))
```

In `tools/ingest/src/langatlas_ingest/errors.py`:

```python
class IncompleteMatrix(IngestError):
    """§8.6's decision rules were asked to conclude from a matrix with a hole in it.
    Raised rather than deciding on what is present: a rule comparing an arm against an
    absent one would silently become a different rule, and the verdict it produced would
    be indistinguishable from a real one."""

    def __init__(self, missing: list[str]):
        super().__init__("cannot decide with arms missing:\n  " + "\n  ".join(missing))
        self.missing = list(missing)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_verdict.py -v`
Expected: PASS (12 tests). The boundary tests (`+4` vs `+5`, `-2` vs `-3`, exactly `2` nDCG
points) are the ones that matter — every one of §8.6's rules is an inequality, and an off-by-one
in the comparison direction changes the project's retrieval stack.

- [ ] **Step 5: Commit**

```bash
git add tools/ingest/src/langatlas_ingest/benchmark/verdict.py \
        tools/ingest/src/langatlas_ingest/errors.py \
        tools/ingest/tests/test_benchmark_verdict.py \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): apply the D22 decision rules mechanically"
```

---

## Task 13: The report and the CLI

Four subcommands on the existing `langatlas-sources` CLI, plus the markdown table a human
actually reads. `bench-verdict --write` is the only command that touches `config/ingest.yaml`,
and it verifies the three pinned values agree with the capability table before writing them.

**Files:**
- Create: `tools/ingest/src/langatlas_ingest/benchmark/report.py`
- Create: `tools/ingest/tests/test_benchmark_report.py`
- Create: `benchmarks/d22-source-corpus/README.md`
- Modify: `tools/ingest/src/langatlas_ingest/cli.py`
- Modify: `tools/ingest/tests/test_cli.py`

**Interfaces:**
- Consumes: `ArmResult`, `Verdict`, `Matrix`, `PilotSelection`, `ProviderConfig`.
- Produces:
  ```python
  def matrix_markdown(results: dict[str, ArmResult], *, matrix: Matrix) -> str
  def write_verdict(verdict: Verdict, results: dict[str, ArmResult], *,
                    matrix: Matrix, root: Path) -> tuple[Path, Path]
  def pin_config(verdict: Verdict, *, config_path: Path,
                 provider_config=None) -> list[str]
  ```
  `pin_config` returns the list of lines it changed, and raises `ValueError` when the
  verdict's dimension disagrees with `provider_config.embedding(model).dimensions`.

- [ ] **Step 1: Write the failing tests**

Create `tools/ingest/tests/test_benchmark_report.py`:

```python
import pytest
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_ingest.benchmark.report import matrix_markdown, pin_config, write_verdict
from langatlas_ingest.benchmark.verdict import Verdict

VERDICT = Verdict(table="source-corpus", incumbent="inc", model="cha", dimensions=1024,
                  index_type="hnsw-halfvec-cosine", mode="vector", rerank=False,
                  chunk_target_tokens=400, chunk_max_tokens=550,
                  pilot_sources=("s1",), queries_scored=30, moved=True,
                  rationale=("because",))

CONFIG = """chunking:
  target_tokens: 600
  max_tokens: 800
  overlap_tokens: 60
models:
  embedding: inc
  embedding_dimensions: 2560
  index_type: hnsw-halfvec-cosine
  reranker: r
  rerank_default_on: true
retrieval:
  mode: hybrid
  k: 5
"""


class _FakeProviderConfig:
    def __init__(self, dimensions):
        self.dimensions = dimensions

    def embedding(self, model):
        return type("Cap", (), {"model": model, "dimensions": self.dimensions,
                                "max_input_tokens": 512})()


def test_pin_config_writes_every_decided_value(tmp_path: Path):
    path = tmp_path / "ingest.yaml"
    path.write_text(CONFIG)
    changed = pin_config(VERDICT, config_path=path,
                         provider_config=_FakeProviderConfig(1024))
    data = YAML(typ="safe").load(path.read_text())
    assert data["models"]["embedding"] == "cha"
    assert data["models"]["embedding_dimensions"] == 1024
    assert data["models"]["rerank_default_on"] is False
    assert data["retrieval"]["mode"] == "vector"
    assert data["chunking"]["target_tokens"] == 400
    assert data["chunking"]["max_tokens"] == 550
    assert len(changed) == 6


def test_pin_config_preserves_the_files_comments(tmp_path: Path):
    path = tmp_path / "ingest.yaml"
    path.write_text("# load-bearing comment\n" + CONFIG)
    pin_config(VERDICT, config_path=path, provider_config=_FakeProviderConfig(1024))
    assert "# load-bearing comment" in path.read_text()


def test_pin_config_refuses_a_dimension_the_capability_table_disagrees_with(
        tmp_path: Path):
    path = tmp_path / "ingest.yaml"
    path.write_text(CONFIG)
    with pytest.raises(ValueError) as caught:
        pin_config(VERDICT, config_path=path,
                   provider_config=_FakeProviderConfig(768))
    assert "768" in str(caught.value)
    assert YAML(typ="safe").load(path.read_text())["models"]["embedding"] == "inc"


def test_pin_config_reports_no_changes_for_an_unmoved_verdict(tmp_path: Path):
    path = tmp_path / "ingest.yaml"
    path.write_text(CONFIG)
    unmoved = Verdict(table="source-corpus", incumbent="inc", model="inc",
                      dimensions=2560, index_type="hnsw-halfvec-cosine", mode="hybrid",
                      rerank=True, chunk_target_tokens=600, chunk_max_tokens=800,
                      pilot_sources=("s1",), queries_scored=30, moved=False,
                      rationale=())
    assert pin_config(unmoved, config_path=path,
                      provider_config=_FakeProviderConfig(2560)) == []


def test_write_verdict_emits_both_forms(tmp_path: Path):
    matrix = type("M", (), {"primary": (), "incumbent": "inc",
                            "pilot_sources": ("s1",)})()
    json_path, md_path = write_verdict(VERDICT, {}, matrix=matrix, root=tmp_path)
    assert json_path.name == "verdict.json" and md_path.name == "verdict.md"
    assert "cha" in md_path.read_text()
    assert json_path.read_text().endswith("\n")


def test_matrix_markdown_has_a_row_per_result_and_marks_dishonest_throughput():
    from langatlas_ingest.benchmark.arms import Arm
    from langatlas_ingest.benchmark.metrics import IndexStats
    from langatlas_ingest.benchmark.runner import ArmResult

    arm = Arm(embedding_model="m", mode="hybrid", rerank=True, chunk_target_tokens=600,
              chunk_max_tokens=800, truncate=True)
    result = ArmResult(
        arm=arm,
        index=IndexStats(model="m", chunks=10, tokens=100, embed_seconds=1.0,
                         chunks_per_second=10.0, tokens_per_second=100.0,
                         truncated_chunks=9, cached_vectors=5, throughput_honest=False,
                         table_bytes=80, bytes_per_chunk=8.0, dimensions=4),
        metrics={"queries": 30, "recall_at_5": 0.8, "recall_at_50": 0.9, "mrr": 0.5,
                 "ndcg_at_10": 0.6, "latency_p50_ms": 10.0, "skipped_queries": 7,
                 "per_query": []},
        pilot_sources=("s1",), run_id="r", finished="2026-09-05T00:00:00Z")
    matrix = type("M", (), {"primary": (arm,), "incumbent": "m",
                            "pilot_sources": ("s1",)})()
    text = matrix_markdown({arm.arm_id: result}, matrix=matrix)
    assert arm.arm_id in text
    assert "90%" in text          # truncated share, visible in the table
    assert "cache-warm" in text   # the throughput caveat, not silently omitted
```

Append to `tools/ingest/tests/test_cli.py`:

```python
def test_bench_pilot_prints_the_selection(capsys):
    from langatlas_ingest.cli import main

    assert main(["bench-pilot", "--size", "4"]) == 0
    out = capsys.readouterr().out
    assert "sebesta-copl" in out and "37/52" in out


def test_bench_subcommands_are_registered():
    from langatlas_ingest.cli import build_parser

    actions = build_parser()._subparsers._group_actions[0].choices
    assert {"bench-pilot", "bench-build", "bench-run", "bench-verdict"} <= set(actions)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_report.py tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: ... benchmark.report`.

- [ ] **Step 3: Implement `report.py`**

```python
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_ingest.benchmark.arms import Matrix
from langatlas_ingest.benchmark.runner import ArmResult
from langatlas_ingest.benchmark.verdict import Verdict

# Round-trip loader: config/ingest.yaml's comments explain every knob, and a benchmark
# that pinned a model by deleting the documentation around it would be a bad trade.
_rt_yaml = YAML()
_rt_yaml.preserve_quotes = True


def _pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}"


def matrix_markdown(results: dict[str, ArmResult], *, matrix: Matrix) -> str:
    lines = ["# D22 source-corpus benchmark", "",
             f"Pilot: {', '.join(matrix.pilot_sources)}", "",
             "| arm | R@5 | R@50 | nDCG@10 | MRR | p50 ms | chunks/s | MB |"
             " truncated | notes |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for arm_id in sorted(results):
        result = results[arm_id]
        metrics, index = result.metrics, result.index
        notes = []
        if not index.throughput_honest:
            # Never quietly drop the number: report it and say why it cannot be ranked on.
            notes.append("cache-warm throughput")
        if metrics.get("skipped_queries"):
            notes.append(f"{metrics['skipped_queries']} queries out of corpus")
        truncated = (f"{index.truncated_chunks / index.chunks:.0%}"
                     if index.chunks else "n/a")
        rate = ("n/a" if index.chunks_per_second is None
                else f"{index.chunks_per_second:.1f}")
        lines.append(
            f"| {arm_id} | {_pct(metrics.get('recall_at_5'))} |"
            f" {_pct(metrics.get('recall_at_50'))} |"
            f" {_pct(metrics.get('ndcg_at_10'))} | {_pct(metrics.get('mrr'))} |"
            f" {metrics.get('latency_p50_ms') or 0:.0f} | {rate} |"
            f" {index.table_bytes / 1_048_576:.1f} | {truncated} |"
            f" {'; '.join(notes)} |")
    return "\n".join(lines) + "\n"


def write_verdict(verdict: Verdict, results: dict[str, ArmResult], *, matrix: Matrix,
                  root: Path) -> tuple[Path, Path]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    json_path, md_path = root / "verdict.json", root / "verdict.md"
    json_path.write_text(verdict.to_json())
    md_path.write_text(verdict.to_markdown() + "\n"
                       + matrix_markdown(results, matrix=matrix))
    return json_path, md_path


def pin_config(verdict: Verdict, *, config_path: Path, provider_config=None) -> list[str]:
    """Write the verdict's choices into config/ingest.yaml.

    The dimension is cross-checked against the capability table first and the write is
    refused on disagreement — a pinned dimension that does not match the model's real
    output would be caught later by `ensure_embedding_table`, but only after a full
    re-embed had already been attempted against the wrong table definition.
    """
    if provider_config is None:
        from langatlas_pipeline.config import ProviderConfig

        provider_config = ProviderConfig.load()
    measured = provider_config.embedding(verdict.model).dimensions
    if measured != verdict.dimensions:
        raise ValueError(
            f"{verdict.model}: the benchmark measured {verdict.dimensions} dimensions but"
            f" provider_capabilities.yaml records {measured}; re-probe before pinning")

    data = _rt_yaml.load(config_path.read_text())
    updates = [("models", "embedding", verdict.model),
               ("models", "embedding_dimensions", verdict.dimensions),
               ("models", "index_type", verdict.index_type),
               ("models", "rerank_default_on", verdict.rerank),
               ("retrieval", "mode", verdict.mode),
               ("chunking", "target_tokens", verdict.chunk_target_tokens),
               ("chunking", "max_tokens", verdict.chunk_max_tokens)]
    changed: list[str] = []
    for section, key, value in updates:
        if data[section].get(key) != value:
            changed.append(f"{section}.{key}: {data[section].get(key)!r} -> {value!r}")
            data[section][key] = value
    if changed:
        with config_path.open("w", encoding="utf-8") as fh:
            _rt_yaml.dump(data, fh)
    return changed
```

- [ ] **Step 4: Implement the four CLI subcommands**

Add to `tools/ingest/src/langatlas_ingest/cli.py` (each keeps the module's convention of heavy
imports inside the function):

```python
def _cmd_bench_pilot(args) -> int:
    from langatlas_ingest.benchmark.arms import load_matrix
    from langatlas_ingest.benchmark.pilot import select_pilot
    from langatlas_ingest.eval import load_entries

    matrix = load_matrix()
    selection = select_pilot(load_entries(matrix.golden_dir), size=args.size)
    print(selection.to_markdown())
    if tuple(matrix.pilot_sources) != selection.sources:
        print("NOTE: config/benchmark/d22-source-corpus.yaml pins a different pilot"
              f" ({', '.join(matrix.pilot_sources)}). The golden set has changed since"
              " the pilot was ratified — re-run the arms or re-ratify the pilot.")
        return 1
    return 0


def _cmd_bench_build(args) -> int:
    import psycopg
    from dataclasses import replace
    from langatlas_ingest.benchmark.arms import load_matrix
    from langatlas_ingest.benchmark.corpus import (
        build_bench_corpus, check_parity, create_bench_db,
    )
    from langatlas_ingest.errors import BenchCorpusMismatch

    config, matrix = IngestConfig.load(), load_matrix()
    target, maximum = args.chunk_target, args.chunk_max
    arm_config = replace(config, chunk_target_tokens=target, chunk_max_tokens=maximum)
    dsn = create_bench_db(config.dsn, drop=args.drop)
    with psycopg.connect(dsn, autocommit=True) as bench:
        counts = build_bench_corpus(bench, sources=matrix.pilot_sources,
                                    config=arm_config)
        for source_id, count in counts.items():
            print(f"{source_id}: {count} chunks")
        # Parity is only meaningful at production's chunking; the secondary axis is
        # *supposed* to produce different ids, which is why Task 9 exists.
        if (target, maximum) == matrix.primary_chunk_size:
            with psycopg.connect(config.dsn, autocommit=True) as prod:
                differences = check_parity(bench, prod, matrix.pilot_sources)
            if differences:
                raise BenchCorpusMismatch(differences)
            print("parity with production: OK")
    return 0


def _cmd_bench_run(args) -> int:
    import psycopg
    from langatlas_ingest.benchmark.arms import load_matrix
    from langatlas_ingest.benchmark.corpus import bench_dsn
    from langatlas_ingest.benchmark.report import matrix_markdown
    from langatlas_ingest.benchmark.runner import load_results, run_matrix

    config, matrix = IngestConfig.load(), load_matrix()
    if args.chunk_size_for:
        arms = matrix.chunk_size_arms(args.chunk_size_for, truncate=args.truncate)
        span = True
    else:
        arms = [arm for arm in matrix.primary
                if not args.arm or arm.arm_id in args.arm]
        span = False
    with psycopg.connect(bench_dsn(config.dsn), autocommit=True) as bench, \
            psycopg.connect(config.dsn, autocommit=True) as prod:
        run_matrix(bench, arms, matrix=matrix, config=config, prod_conn=prod,
                   resume=not args.force, span_relevance=span)
    print(matrix_markdown(load_results(matrix.results_dir), matrix=matrix))
    return 0


def _cmd_bench_verdict(args) -> int:
    from langatlas_ingest.benchmark.arms import load_matrix
    from langatlas_ingest.benchmark.report import pin_config, write_verdict
    from langatlas_ingest.benchmark.runner import load_results
    from langatlas_ingest.benchmark.verdict import decide
    from langatlas_ingest.paths import BENCHMARK_DIR, INGEST_CONFIG_PATH

    matrix = load_matrix()
    results = load_results(matrix.results_dir)
    verdict = decide(results, matrix=matrix)
    print(verdict.to_markdown())
    json_path, md_path = write_verdict(verdict, results, matrix=matrix,
                                       root=BENCHMARK_DIR)
    print(f"wrote {json_path} and {md_path}")
    if args.write:
        changed = pin_config(verdict, config_path=INGEST_CONFIG_PATH)
        for line in changed or ["config/ingest.yaml already matches the verdict"]:
            print(line)
        if changed and verdict.model != matrix.incumbent:
            print("\nThe model moved: the production corpus must be fully re-embedded"
                  " before this configuration is used.\n"
                  "  uv --directory tools/ingest run langatlas-sources embed")
    return 0
```

and register them in `build_parser`:

```python
    bench_pilot = sub.add_parser("bench-pilot",
                                 help="select the D22 pilot corpus by golden coverage")
    bench_pilot.add_argument("--size", type=int, default=4)
    bench_pilot.set_defaults(func=_cmd_bench_pilot)

    bench_build = sub.add_parser("bench-build",
                                 help="build the isolated benchmark corpus at one"
                                      " chunk size")
    bench_build.add_argument("--chunk-target", type=int, default=600)
    bench_build.add_argument("--chunk-max", type=int, default=800)
    bench_build.add_argument("--drop", action="store_true",
                             help="recreate the benchmark database first (required when"
                                  " changing chunk size)")
    bench_build.set_defaults(func=_cmd_bench_build)

    bench_run = sub.add_parser("bench-run", help="run the D22 arms (resumable)")
    bench_run.add_argument("--arm", nargs="*", default=[],
                           help="run only these arm ids; omit for the whole matrix")
    bench_run.add_argument("--chunk-size-for", default=None,
                           help="run §8.6's secondary chunk-size axis for this model"
                                " instead of the primary matrix")
    bench_run.add_argument("--truncate", action="store_true",
                           help="with --chunk-size-for: the chosen model is a"
                                " short-context candidate")
    bench_run.add_argument("--force", action="store_true",
                           help="re-run arms that already have a committed result")
    bench_run.set_defaults(func=_cmd_bench_run)

    bench_verdict = sub.add_parser("bench-verdict",
                                   help="apply §8.6's decision rules and record the"
                                        " verdict")
    bench_verdict.add_argument("--write", action="store_true",
                               help="also pin the verdict into config/ingest.yaml")
    bench_verdict.set_defaults(func=_cmd_bench_verdict)
```

- [ ] **Step 5: Write the benchmark directory README**

Create `benchmarks/d22-source-corpus/README.md`:

```markdown
# D22 source-corpus embedding benchmark

The committed record behind `config/ingest.yaml`'s pinned `models.embedding`,
`models.embedding_dimensions`, `models.index_type`, `models.rerank_default_on`,
`retrieval.mode` and `chunking` values (spec §8.6, Stage 2C).

- `../../config/benchmark/d22-source-corpus.yaml` — the run matrix: pilot, candidates,
  variant axes, decision margins. Configuration the developer ratifies.
- `results/<arm_id>.json` — one file per measured arm. Also the runner's checkpoint: an
  arm whose file exists is skipped on re-invocation.
- `verdict.json` / `verdict.md` — the per-table verdict and the full arm table.

Results are committed while the embeddings they measure are not: the vectors are derived
data (D1/D15), but the measurement justifying a production setting is a research record.

## Re-running

```bash
docker compose up -d db
uv --directory tools/ingest run langatlas-sources bench-pilot            # confirm the pilot
uv --directory tools/ingest run langatlas-sources bench-build --drop     # 600/800 + parity
uv --directory tools/ingest run langatlas-sources bench-run              # the 18 primary arms
uv --directory tools/ingest run langatlas-sources bench-verdict          # read the verdict
```

The secondary chunk-size axis runs after the model is chosen, one chunk size at a time,
because each size is a different corpus:

```bash
uv --directory tools/ingest run langatlas-sources bench-build --drop \
    --chunk-target 400 --chunk-max 550
uv --directory tools/ingest run langatlas-sources bench-run --chunk-size-for <model>
```

`bench-run` is resumable: delete an arm's JSON (or pass `--force`) to re-measure it.

Recall figures come from a four-source pilot. They are comparative between arms, not
predictions of production recall — the distractor pool is a quarter of production's.

## What this benchmark does *not* decide

The fact index (`knowledge_embeddings`, §8.3/D62) runs its own benchmark: a proxy run late
in Stage 3 and the real re-run at sweep start in Stage 5. Verdicts are per table, and the
two indexes may legitimately choose different models. Debate-history retrieval is deferred
to v2.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv --directory tools/ingest run pytest tests/test_benchmark_report.py tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 7: Run everything**

Run: `uv --directory tools/ingest run pytest && uv --directory tools/ingest run pytest -m db && uv --directory tools/pipeline run pytest`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add tools/ingest/src/langatlas_ingest/benchmark/report.py \
        tools/ingest/src/langatlas_ingest/cli.py \
        tools/ingest/tests/test_benchmark_report.py tools/ingest/tests/test_cli.py \
        benchmarks/d22-source-corpus/README.md \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): wire the D22 benchmark CLI and its report"
```

---

## Task 14: Run the primary matrix

Everything up to here is tooling. This task is the measurement §8.6 actually asks for: eighteen
arms — six candidates × {vector, hybrid, hybrid+rerank} — on the four-source pilot at production's
600/800 chunking.

**Expect this to take a night.** Six embed passes of 3,826 chunks each against a slow university
API, plus six reranked evaluation arms of ~37 queries × 3 rerank completions per query. It is
resumable; run it in pieces if that suits the machine better.

**Files:**
- Create: `benchmarks/d22-source-corpus/results/*.json` (18 files)

- [ ] **Step 1: Build the pilot corpus at production chunking**

```bash
docker compose up -d db
uv --directory tools/ingest run langatlas-sources bench-pilot
uv --directory tools/ingest run langatlas-sources bench-build --drop
```

Expected: the ratified pilot, `{rust-fls: 1188, rust-reference: 788, scott-plp: 845,
sebesta-copl: 1005}`, and `parity with production: OK`. A parity failure stops the task.

- [ ] **Step 2: Run the incumbent's three arms first**

```bash
uv --directory tools/ingest run langatlas-sources bench-run \
    --arm qwen3-embedding-4b__vector__c600 \
         qwen3-embedding-4b__hybrid__c600 \
         qwen3-embedding-4b__hybrid-rerank__c600
```

Expected: three result files. Read them before going further — the incumbent's numbers are the
baseline every other arm is judged against, and a nonsense baseline (Recall@5 near zero, or 37
queries skipped) means something upstream is wrong and eight more hours of arms would not fix it.
Sanity floor: `hybrid-rerank` should be the incumbent's best arm and should score above the
full-corpus baseline recorded in Task 5 Step 5, because the pilot has fewer distractors.

- [ ] **Step 3: Run the remaining fifteen arms**

```bash
uv --directory tools/ingest run langatlas-sources bench-run
```

Expected: eighteen files in `benchmarks/d22-source-corpus/results/`, and the printed matrix
table. Re-invoke after any interruption; completed arms are skipped.

- [ ] **Step 4: Check the honesty flags**

```bash
uv --directory tools/ingest run python -c "
from langatlas_ingest.benchmark.arms import load_matrix
from langatlas_ingest.benchmark.runner import load_results
for arm_id, r in sorted(load_results(load_matrix().results_dir).items()):
    print(f'{arm_id:55} truncated={r.index.truncated_chunks:5} '
          f'cached={r.index.cached_vectors:5} honest={r.index.throughput_honest} '
          f'skipped={r.metrics[\"skipped_queries\"]}')"
```

Expected, and each is a *finding to report*, not a thing to fix silently:
- The three 512-token candidates (`mxbai-embed-large`, `multilingual-e5-large-instruct`,
  `local:BAAI/bge-small-en-v1.5`) truncate most chunks. That is §8.6's honest test working, and
  the truncated share belongs in the verdict discussion.
- `skipped` is 15 on every arm (52 golden queries − 37 covered by the pilot), identical
  everywhere. A *differing* skip count between arms means `corpus_sources` is not being applied
  uniformly — stop and investigate.
- `honest=False` on the second and third arm of a model is expected: they share the model's
  cached vectors. Only the model's *first* arm measures real indexing throughput, which is the
  arm the verdict's throughput column should be read from.

- [ ] **Step 5: Commit the results**

```bash
git add benchmarks/d22-source-corpus/results/ \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): record the D22 primary-matrix arm results"
```

---

## Task 15: Run the secondary chunk-size axis

§8.6's secondary axis, run only for the model the primary matrix chose (re-chunking is a corpus
rebuild per size). Scored with Task 9's span-overlap rule, because these arms' chunk ids do not
exist in the golden set by construction.

**Files:**
- Create: `benchmarks/d22-source-corpus/results/<model>__hybrid-rerank__c400.json`
- Create: `benchmarks/d22-source-corpus/results/<model>__hybrid-rerank__c800.json`

- [ ] **Step 1: Read the primary verdict to learn which model to test**

```bash
uv --directory tools/ingest run langatlas-sources bench-verdict
```

Expected: a verdict naming a model. Note whether it is a short-context candidate — that decides
the `--truncate` flag below. (`bench-verdict` runs fine with the chunk-size arms absent; rule 4
simply reports that the chunking stays.)

- [ ] **Step 2: Measure the 400-token chunking**

```bash
uv --directory tools/ingest run langatlas-sources bench-build --drop \
    --chunk-target 400 --chunk-max 550
uv --directory tools/ingest run langatlas-sources bench-run \
    --chunk-size-for <model-from-step-1>   # add --truncate for a 512-token model
```

Expected: one new result file, `..._c400.json`. Recall@5 on it should be in the same
neighbourhood as the primary arm — a *collapse* to near zero means the span relevance rule is not
matching and must be debugged (Task 9 Step 5 is the check to re-run), not recorded as a chunk-size
finding.

- [ ] **Step 3: Measure the 800-token chunking**

```bash
uv --directory tools/ingest run langatlas-sources bench-build --drop \
    --chunk-target 800 --chunk-max 1050
uv --directory tools/ingest run langatlas-sources bench-run \
    --chunk-size-for <model-from-step-1>   # same --truncate decision
```

Expected: `..._c800.json`.

- [ ] **Step 4: Restore the bench corpus to production chunking**

```bash
uv --directory tools/ingest run langatlas-sources bench-build --drop
```

Expected: `parity with production: OK`. Leaving the bench database at 800 tokens would make any
later re-run of a primary arm silently score a different corpus.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/d22-source-corpus/results/ \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): record the D22 chunk-size axis results"
```

---

## Task 16: Record the verdict and pin the configuration

The last task, and the one Stage 3 and 2D actually consume. `decide()` has already done the
deciding; this is the developer adopting it, the record being committed, and — only if the model
moved — the production corpus being re-embedded.

**Files:**
- Create: `benchmarks/d22-source-corpus/verdict.json`, `benchmarks/d22-source-corpus/verdict.md`
- Modify: `config/ingest.yaml`

- [ ] **Step 1: Produce the verdict record**

```bash
uv --directory tools/ingest run langatlas-sources bench-verdict
```

Expected: the verdict markdown, the full 20-arm table, and both files written.

- [ ] **Step 2: Developer checkpoint — adopt the verdict**

Read `benchmarks/d22-source-corpus/verdict.md` with the developer. The rules are mechanical; the
adoption is not. Points to raise explicitly:

- Every rule's margin and which of them was close. A rule that decided on 0.2 points is worth
  saying out loud even though the rule is the rule.
- The truncated share for any short-context winner: a model that wins while reading 512 of every
  800 tokens is winning at a task production would not give it.
- That recall is pilot-relative (four sources), so the *ordering* is the finding and the absolute
  numbers are not a production forecast.
- Whether the verdict `moved` at all, and therefore whether a re-embed is coming.

**Do not proceed to Step 3 without the developer's explicit adoption.** If the developer rejects
the verdict, the disagreement is with a rule in §8.6 — amend the spec and the margins in
`config/benchmark/d22-source-corpus.yaml`, then re-run `bench-verdict`. Never hand-edit
`verdict.json`.

- [ ] **Step 3: Pin the configuration**

```bash
uv --directory tools/ingest run langatlas-sources bench-verdict --write
git diff config/ingest.yaml
```

Expected: either `config/ingest.yaml already matches the verdict` (the incumbent held on every
axis) or a listed set of changes. The command refuses to write if the verdict's dimension
disagrees with `config/provider_capabilities.yaml`.

- [ ] **Step 4: Re-embed the production corpus if the model moved (developer checkpoint)**

Only when Step 3 changed `models.embedding`:

```bash
uv --directory tools/ingest run langatlas-sources embed
```

Expected: every one of the ~14,391 production chunks embedded on the new model, into that model's
own table (the old table is left in place — `ensure_embedding_table` is per-model, and keeping the
previous vectors makes a rollback a config edit instead of another overnight run). This is hours
of API time and is the developer's go-ahead to give.

If Step 3 also changed `chunking`, the corpus must be **re-ingested** before it is re-embedded:

```bash
uv --directory tools/ingest run langatlas-sources reingest
uv --directory tools/ingest run langatlas-sources embed
```

**A chunking change invalidates every `expected_chunks` id in 2B's committed golden sets and every
`evidence_chunk_ids` entry in the verifier set.** They must be re-derived before 2D can use them:
run `langatlas-sources golden-validate --resolve` and expect failures, then re-run 2B's
`golden-derive-queries` for the derived band and repair the hand-authored entries against the new
ids. Raise this with the developer as a scope consequence *before* running `reingest` — it is
2B rework, and the 2-point margin exists precisely so it is not incurred lightly.

- [ ] **Step 5: Verify the pinned stack answers the golden set**

```bash
uv --directory tools/ingest run langatlas-sources eval --depth 50
```

Expected: 52 queries scored, with metrics in the same range as Task 5 Step 5's baseline (better
if the model moved, unchanged if it did not). This is the check that the *production* database —
not the bench one — retrieves correctly under the pinned configuration. 2D's stage-1
retrieval-rescue ladder and Stage 3's `search_sources` both run against exactly this.

- [ ] **Step 6: Commit the verdict and the pin**

```bash
git add benchmarks/d22-source-corpus/verdict.json \
        benchmarks/d22-source-corpus/verdict.md \
        config/ingest.yaml \
        docs/superpowers/plans/2026-09-05-stage-2c-d22-embedding-benchmark.md
git commit -m "feat(#stage-2c): pin the source-corpus retrieval stack from the D22 verdict"
```

- [ ] **Step 7: Update the Stage 2 checklist**

In [context/spec.md](../../../context/spec.md) §14, check off Stage 2's fourth item ("R2: run the
D22 embedding benchmark on a pilot corpus; record per-table verdicts"). Match the surrounding
entries' level of detail — a checked box, not a log entry.

```bash
git add context/spec.md
git commit -m "docs(#stage-2c): check off Stage 2's D22 benchmark item"
```

---

## Stage 2C exit condition

The sequencing map's third exit criterion: **"D22 source-corpus verdict recorded and the
model/dimension/index type pinned in `config/ingest.yaml`."** Concretely:

1. `benchmarks/d22-source-corpus/results/` holds 18 primary arm results plus the 2 chunk-size
   arms, each with its own transcript run id.
2. `benchmarks/d22-source-corpus/verdict.json` and `verdict.md` are committed and were produced
   by `decide()`, not by hand.
3. `config/ingest.yaml` pins `models.embedding`, `models.embedding_dimensions`,
   `models.index_type`, `models.rerank_default_on`, `retrieval.mode` and `chunking` to the
   adopted verdict, and `bench-verdict --write` reports no pending changes.
4. If the model moved, the production corpus is fully re-embedded on it, and
   `langatlas-sources eval --depth 50` scores all 52 golden queries against the production
   database.

2D consumes the pinned stack for its stage-1 retrieval-rescue ladder; Stage 3's `search_sources`
retrieves against exactly it. Neither re-derives it.

## Deliberately out of scope

- **The fact-index verdict** (`knowledge_embeddings`, §8.3/D62). §8.6 schedules a proxy run late
  in Stage 3 and the real re-run at sweep start in Stage 5. Per-table verdicts are independent.
- **Debate-history retrieval** — deferred to v2 (§8.6).
- **HNSW-vs-IVFFlat for the fact index** — deferred to that benchmark (§8.3). The source-corpus
  index type is not in question: `ensure_embedding_table` builds HNSW over `halfvec`, and the
  verdict records it rather than deciding it.
- **Growing the golden set from logged agent misses** (§8.1/§8.6). That is a standing Stage 3
  activity, not a 2C deliverable.
- **The public golden-set benchmark** — a stretch goal, explicitly out of scope (§6.4).
- **Rate-limit or cost tuning of the university API.** If an arm is unbearably slow, report it;
  do not lower `retrieval.candidates` or `rerank_candidates` to make the benchmark cheaper —
  those are the production values, and an arm measured at different values is not measuring
  production.
