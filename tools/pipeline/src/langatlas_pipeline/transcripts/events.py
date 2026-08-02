import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TranscriptEvent:
    """One line of transcript.jsonl (D18)."""

    seq: int
    ts: str
    role: str                                   # system | user | assistant | tool
    content: str
    agent: str | None = None                    # persona id
    model: str | None = None
    tool_call: dict[str, Any] | None = None     # {"name": ..., "args": {...}}
    tool_result_ref: dict[str, Any] | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cache_hit: bool = False
    flags: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=False)


@dataclass
class RunManifest:
    """manifest.yaml (D18) — small and greppable. `resulting_fact_ids` is filled in at
    close time by whatever stage commits facts, because a run ends before acceptance
    is known."""

    run_id: str
    kind: str                                   # sweep | debate | verification | reconcile
                                                # | research | challenge | probe | interactive
    started: str
    ended: str | None = None
    agents: list[dict[str, Any]] = field(default_factory=list)
    debate_id: str | None = None
    languages: list[str] = field(default_factory=list)
    budget: dict[str, Any] = field(default_factory=dict)
    prompts: list[str] = field(default_factory=list)          # "<prompt_id>@<version>"
    resulting_fact_ids: list[str] = field(default_factory=list)
    msg_anchors: dict[str, int] = field(default_factory=dict)  # claim/fact -> seq (§7.10 batches)
    wrapper_version: str = ""
    redaction: dict[str, Any] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
