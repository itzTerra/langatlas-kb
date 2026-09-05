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
