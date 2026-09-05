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
