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


@dataclass(frozen=True)
class EdgeDraft:
    """`frm` rather than `from`, which is a Python keyword; the rendered field is `from`."""
    type: str
    frm: str
    to: str
    statement: str
    evidence: tuple[Evidence, ...]
    proposer: Proposer
    chat_run_id: str
    polarity: str | None = None
    debate_id: str | None = None
    claim_origin: str = "source-derived"
    candidate_source: str = "internal-survey"


@dataclass(frozen=True)
class Assessment:
    """One entry in an `affects-quality` edge. `key` is minted once and immutable (§3.3):
    renaming it is a supersession, never an edit."""
    key: str
    assessor: Proposer
    polarity: str
    strength: str
    statement: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class QualityEdgeDraft:
    frm: str
    to: str
    assessments: tuple[Assessment, ...]
    proposer: Proposer
    chat_run_id: str
    debate_id: str | None = None
    claim_origin: str = "source-derived"
    candidate_source: str = "internal-survey"


@dataclass(frozen=True)
class RuleDraft:
    slug: str
    when_all: tuple[str, ...]
    effect: str
    then: tuple[str, ...]
    message: str
    evidence: tuple[Evidence, ...]
    proposer: Proposer
    chat_run_id: str
    debate_id: str | None = None
    claim_origin: str = "source-derived"
    candidate_source: str = "internal-survey"


@dataclass(frozen=True)
class Characteristic:
    """One `characteristics[c-…]` entry (§3.4): an observable property of the feature in one
    language. `key` is minted once and immutable (§3.3)."""
    key: str
    text: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class InstanceNote:
    """One typed note on a `partial` instance (§3.4): what is missing (`limitation`), added
    (`extra`), or done another way (`alternative`)."""
    key: str
    type: str
    text: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class SyntaxExample:
    """One `syntax[…]` entry. `origin` is `original` for anything an agent writes — D14 bars
    copying examples from SA-licensed comparison sites."""
    key: str
    title: str
    code: str
    evidence: tuple[Evidence, ...]
    origin: str = "original"


@dataclass(frozen=True)
class InstanceDraft:
    """A FeatureInstance (§3.4): one language x one feature, D20's authoring unit.

    `evidence` is the existence citations (D65): rendered as `since.sources` for a present or
    partial instance — which therefore requires `since` — and as status-level `sources` for an
    absent one, which has no `since`."""
    language: str
    feature: str
    status: str
    evidence: tuple[Evidence, ...]
    proposer: Proposer
    chat_run_id: str
    absence_scope: str | None = None
    since: str | None = None
    notes: tuple[InstanceNote, ...] = ()
    characteristics: tuple[Characteristic, ...] = ()
    syntax: tuple[SyntaxExample, ...] = ()
    debate_id: str | None = None
    claim_origin: str = "source-derived"
    candidate_source: str = "sweep-questionnaire"
