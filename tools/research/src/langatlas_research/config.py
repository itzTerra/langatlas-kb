"""`config/research.yaml` — the research phase's knobs. Frozen dataclasses so a run can log
exactly what it ran with, and so a typo'd key fails at load rather than mid-run."""
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.paths import research_config_path

_yaml = YAML(typ="safe")


@dataclass(frozen=True)
class PoolConfig:
    k_per_query: int
    max_chunks: int


@dataclass(frozen=True)
class TaggerConfig:
    alias: str
    batch_size: int
    min_relevance: int


@dataclass(frozen=True)
class ClaudeRoleConfig:
    model: str | None
    max_turns: int
    max_claude_messages: int
    max_packet_terms: int
    max_candidates: int


@dataclass(frozen=True)
class DebateConfig:
    proposer: ClaudeRoleConfig
    challenger: ClaudeRoleConfig
    moderator: ClaudeRoleConfig
    max_messages: int
    max_debates_per_cycle: int
    personas: dict


@dataclass(frozen=True)
class DraftConfig:
    ontologist: ClaudeRoleConfig
    edge_drafter: ClaudeRoleConfig
    debate: DebateConfig
    bounce_budget: int


@dataclass(frozen=True)
class ResearchConfig:
    pool: PoolConfig
    tagger: TaggerConfig
    surveyor: ClaudeRoleConfig
    scout: ClaudeRoleConfig
    draft: DraftConfig

    @classmethod
    def load(cls, path: Path | None = None) -> "ResearchConfig":
        """@raises KeyError / TypeError: on a missing or unknown key."""
        data = _yaml.load((path or research_config_path()).read_text()) or {}
        survey, draft = data["survey"], data["draft"]
        debate = draft["debate"]
        return cls(pool=PoolConfig(**survey["pool"]),
                   tagger=TaggerConfig(**survey["tagger"]),
                   surveyor=ClaudeRoleConfig(**survey["surveyor"]),
                   scout=ClaudeRoleConfig(**survey["scout"]),
                   draft=DraftConfig(
                       ontologist=ClaudeRoleConfig(**draft["ontologist"]),
                       edge_drafter=ClaudeRoleConfig(**draft["edge_drafter"]),
                       debate=DebateConfig(
                           proposer=ClaudeRoleConfig(**debate["proposer"]),
                           challenger=ClaudeRoleConfig(**debate["challenger"]),
                           moderator=ClaudeRoleConfig(**debate["moderator"]),
                           max_messages=debate["max_messages"],
                           max_debates_per_cycle=debate["max_debates_per_cycle"],
                           personas=dict(debate["personas"])),
                       bounce_budget=draft["verification"]["bounce_budget"]))
