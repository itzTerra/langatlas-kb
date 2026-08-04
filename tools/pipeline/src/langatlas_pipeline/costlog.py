import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CostRow:
    """One row per provider call (D6/D26). There is no cash meter on the university API,
    so the budgets this feeds are tokens, wall-clock and Claude usage — plus the
    cost-per-accepted-fact join against manifests' resulting_fact_ids."""

    ts: str
    run_id: str
    seq: int
    endpoint: str                 # chat | embeddings | rerank | claude
    alias: str
    resolved_model: str | None
    prompt_id: str | None
    prompt_version: str | None
    tokens_in: int
    tokens_out: int
    tokens_if_uncached: int | None
    latency_ms: int
    cache_hit: bool
    outcome: str                  # ok | repaired | parse_failure | transport_error | budget_stop
    cost_usd: float | None = None  # only the Claude channel reports real currency


def append_cost_row(path: Path, row: CostRow) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")


def read_cost_rows(path: Path) -> list[CostRow]:
    if not path.exists():
        return []
    return [CostRow(**json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
