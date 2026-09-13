"""The shape every Stage 3 agent role produces. Deliberately dumb data: no I/O, no
provider, no validation — so a role's output can be logged, replayed and diffed before
anything touches the store."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Evidence:
    """One entry in a record's `sources:` list (§3.4). `locator` is REQUIRED — D4's
    source-first rule has no exception, and a quote is optional and capped at ~50 words
    (D14)."""
    source: str
    locator: str
    quote: str | None = None

    def as_entry(self) -> dict:
        entry = {"source": self.source, "locator": self.locator}
        if self.quote:
            entry["quote"] = self.quote
        return entry


@dataclass(frozen=True)
class Proposer:
    agent: str
    model: str
    prompt_version: str

    def as_dict(self) -> dict:
        return {"agent": self.agent, "model": self.model,
                "prompt_version": self.prompt_version}


@dataclass(frozen=True)
class _NodeDraft:
    id: str
    name: str
    summary: str
    evidence: tuple[Evidence, ...]
    proposer: Proposer
    chat_run_id: str
    slug: str | None = None
    debate_id: str | None = None
    claim_origin: str = "source-derived"
    candidate_source: str = "internal-survey"


@dataclass(frozen=True)
class ConceptDraft(_NodeDraft):
    excluded_rationale: str | None = None


@dataclass(frozen=True)
class FeatureDraft(_NodeDraft):
    layer: int = 2
    dimension: str | None = None
    cross_cutting: bool = False
    aliases: tuple[str, ...] = ()
    realizes: tuple[str, ...] = ()
