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
class ResearchConfig:
    pool: PoolConfig
    tagger: TaggerConfig
    surveyor: ClaudeRoleConfig
    scout: ClaudeRoleConfig

    @classmethod
    def load(cls, path: Path | None = None) -> "ResearchConfig":
        """@raises KeyError / TypeError: on a missing or unknown key."""
        survey = (_yaml.load((path or research_config_path()).read_text()) or {})["survey"]
        return cls(pool=PoolConfig(**survey["pool"]),
                   tagger=TaggerConfig(**survey["tagger"]),
                   surveyor=ClaudeRoleConfig(**survey["surveyor"]),
                   scout=ClaudeRoleConfig(**survey["scout"]))
