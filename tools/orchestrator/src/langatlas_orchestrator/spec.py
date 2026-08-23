from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_pipeline.paths import PRIVATE_DIR
from langatlas_pipeline.providers.core import Budget

_yaml = YAML(typ="safe")
_REQUIRED = ("kind", "checkpoint_path")
_KNOWN_TOP_LEVEL = ("kind", "checkpoint_path", "budget")


@dataclass(frozen=True)
class BatchSpec:
    """D43 §2.1: `kind` dispatches into the job-kind registry; `extra` is whatever
    job-specific config the spec's own YAML carries beyond the three fields every
    job kind shares (e.g. a search query, a language slug). A relative
    `checkpoint_path` is resolved against `PRIVATE_DIR` (the same private, non-git tier
    as D26's cache/cost log), not against the process's current working directory —
    an absolute path is kept as-is."""

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
    checkpoint_path = Path(data["checkpoint_path"])
    if not checkpoint_path.is_absolute():
        checkpoint_path = PRIVATE_DIR / checkpoint_path
    return BatchSpec(kind=data["kind"], checkpoint_path=checkpoint_path,
                     budget=budget, extra=extra)
