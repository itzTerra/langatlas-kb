"""D5's debate machinery, repurposed for R4's schema disputes (§7.2/§7.4).

Shape: proposer opening → challenger A → challenger B → proposer reply → moderator resolution.
Five messages, under §7.2's cap of six. The moderator runs in its **own** `RunContext` and sees
only the rendered transcript — "fresh-context" is a property of the session, not a promise in a
prompt, so it is implemented as a separate context and tested as one.

Nothing the moderator writes in prose changes anything. It returns a `disposition` and, for a
revision or a split, the replacement fields; `apply_resolution` applies them mechanically. A
revision may not touch a carve's identity: an id is immutable from the moment it is minted
(§5.1), and a debate that wants a different id wants a different carve — which is a `split` with
one replacement, not a rename."""
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from langatlas_pipeline.prompts import PromptRef, load_prompt
from langatlas_research.config import ResearchConfig
from langatlas_research.cycle import Cycle, require_sign_off
from langatlas_research.draft.debate_record import (
    CHALLENGE_TYPES, DISPOSITIONS, next_debate_id, resolution_outcome, rounds, save_debate,
)
from langatlas_research.draft.evidence import EvidenceItem, bind_evidence
from langatlas_research.draft.plan import find_entry, set_entry
from langatlas_research.errors import DebateIncomplete
from langatlas_research.survey.chunks import ChunkLookup
from langatlas_research.survey.claude import run_structured

PROPOSER_PROMPT_ID = "r4-proposer"
CHALLENGER_PROMPT_ID = "r4-challenger"
MODERATOR_PROMPT_ID = "r4-moderator"

# The only fields a revision may touch. Everything else is either identity (minted once,
# §5.1), pipeline bookkeeping the moderator has no business editing, or `evidence` — which
# must always be bound from a `chunk_id` via `bind_evidence` (source/locator copied verbatim
# from `source_chunks`), never typed directly by a model. `draft.schema.json`'s evidence
# shape only requires `source`+`locator`, so a blacklist here would let a moderator's
# structured `revision` smuggle in a model-typed citation that never touched a chunk id; a
# whitelist keeps that structurally impossible instead of relying on downstream re-checks.
_REVISABLE = frozenset({"name", "summary", "layer", "dimension", "cross_cutting", "aliases",
                        "realizes", "statement", "polarity", "note"})

_DISPOSITION_HELP = {
    "keep": "the carve stands as drafted",
    "revise": "the carve stands with changed fields (supply them in `revision`)",
    "split": "the carve becomes two or more carves (supply them in `split_into`)",
    "merge": "the carve folds into another carve in this plan (name it in `merge_into`)",
    "drop": "the carve should not exist (say why in `drop_reason`)",
    "escalate": "the evidence on the table cannot settle this; the developer must rule",
}


@dataclass(frozen=True)
class DebatePrompts:
    proposer: PromptRef
    challenger: PromptRef
    moderator: PromptRef

    @classmethod
    def load(cls) -> "DebatePrompts":
        return cls(proposer=load_prompt(PROPOSER_PROMPT_ID),
                   challenger=load_prompt(CHALLENGER_PROMPT_ID),
                   moderator=load_prompt(MODERATOR_PROMPT_ID))


class ProposerOut(BaseModel):
    text: str


class ChallengeOut(BaseModel):
    type: Literal[CHALLENGE_TYPES]          # type: ignore[valid-type]
    text: str
    evidence: list[EvidenceItem] = Field(default_factory=list)


class ChallengerOut(BaseModel):
    text: str
    challenges: list[ChallengeOut] = Field(default_factory=list)


class SplitOut(BaseModel):
    key: str
    id: str
    kind: Literal["concept", "feature"]
    name: str
    summary: str
    layer: int | None = None
    dimension: str | None = None
    cross_cutting: bool = False
    aliases: list[str] = Field(default_factory=list)
    realizes: list[str] = Field(default_factory=list)
    from_candidates: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=3)
    note: str = ""


class ContradictionOut(BaseModel):
    participants: list[str] = Field(min_length=2)
    detail: str


class ModeratorOut(BaseModel):
    disposition: Literal[DISPOSITIONS]      # type: ignore[valid-type]
    standing_dissent: bool
    upheld_challenges: list[str] = Field(default_factory=list)
    rationale: str
    revision: dict | None = None
    split_into: list[SplitOut] = Field(default_factory=list)
    merge_into: str | None = None
    drop_reason: str = ""
    contradiction: ContradictionOut | None = None


def render_entry(entry: dict) -> str:
    """The carve as every debate role sees it. Plain, ordered text rather than YAML: a
    participant that is shown a plan record starts arguing about plan bookkeeping."""
    lines = []
    for field, value in entry.items():
        if field in ("contested", "debate_id", "status", "verification", "waiver"):
            continue
        if value in (None, [], ""):
            continue
        if field == "evidence":
            for citation in value:
                quote = f' "{citation["quote"]}"' if citation.get("quote") else ""
                lines.append(f"  evidence: {citation['source']} {citation['locator']}"
                             f"  [{citation.get('chunk_id', '')}]{quote}")
            continue
        lines.append(f"  {field}: {value}")
    return "\n".join(lines)


def _render_challenges(messages: list[dict]) -> str:
    blocks = []
    for message in messages:
        for challenge in message.get("challenges") or []:
            cited = "; ".join(f"{c['source']} {c['locator']}"
                              for c in challenge.get("evidence") or []) or "(no citation)"
            blocks.append(f"[{message['persona']}] {challenge['type']}: {challenge['text']}"
                          f"\n  cites: {cited}")
    return "\n\n".join(blocks) or "(no challenges were raised)"


def _render_transcript(messages: list[dict]) -> str:
    blocks = []
    for message in messages:
        head = f"{message['seq']}. {message['role']} ({message['persona']}): {message['text']}"
        blocks.append("\n".join([head, *[
            f"   challenge [{c['type']}]: {c['text']}"
            + (f"\n     cites: " + "; ".join(f"{e['source']} {e['locator']}"
                                             for e in c.get('evidence') or []))
            for c in message.get("challenges") or []]]))
    return "\n\n".join(blocks)


def _bind_challenges(out: ChallengerOut, *, lookup: ChunkLookup, key: str) -> list[dict]:
    """A challenge with no resolvable citation keeps its text and loses its evidence — the
    moderator is told to weigh an uncited challenge accordingly, and that is a judgment the
    record should preserve rather than one this code should make."""
    bound = []
    for challenge in out.challenges:
        entry = {"type": challenge.type, "text": challenge.text}
        if challenge.evidence:
            try:
                citations, _warnings = bind_evidence(challenge.evidence, lookup=lookup,
                                                     what=f"{key}/{challenge.type}")
                entry["evidence"] = citations
            except Exception:                      # EvidenceUnresolvable and nothing else
                entry["evidence"] = []
        bound.append(entry)
    return bound


def _check_revision(revision: dict, entry: dict) -> None:
    unknown = sorted(set(revision) - set(entry))
    if unknown:
        raise DebateIncomplete(f"{entry['key']}: revision names fields the carve does not"
                               f" have: {', '.join(unknown)}")
    bad = sorted(set(revision) - _REVISABLE)
    if bad:
        raise DebateIncomplete(
            f"{entry['key']}: a revision may not change {', '.join(bad)} — only"
            f" {', '.join(sorted(_REVISABLE))} may be revised. An id is minted once (§5.1;"
            f" split the carve instead of renaming it), and evidence is always bound from a"
            f" chunk id, never typed directly in a revision.")


def apply_resolution(plan: dict, debate: dict, *, lookup: ChunkLookup | None = None) -> dict:
    """The one place a resolution changes the plan. Pure.

    @raises DebateIncomplete: a revision that touches identity, a split of anything but a
        node, or a disposition whose required payload is missing."""
    target = debate["target"]["key"]
    resolution = debate["resolution"]
    disposition = resolution["disposition"]
    _list_name, entry = find_entry(plan, target)

    common = {"debate_id": debate["id"]}
    if disposition == "keep":
        return set_entry(plan, target, status="debated", **common)
    if disposition == "escalate":
        return set_entry(plan, target, status="proposed", **common)
    if disposition == "drop":
        return set_entry(plan, target, status="dropped", **common,
                         drop_reason=resolution.get("drop_reason")
                         or resolution["rationale"])
    if disposition == "merge":
        survivor = resolution.get("merge_into")
        if not survivor:
            raise DebateIncomplete(f"{target}: a merge needs `merge_into`")
        find_entry(plan, survivor)              # raises KeyError if it is not in the plan
        return set_entry(plan, target, status="dropped", **common,
                         drop_reason=f"merged into {survivor}: {resolution['rationale']}")
    if disposition == "revise":
        revision = resolution.get("revision") or {}
        if not revision:
            raise DebateIncomplete(f"{target}: a revision needs `revision`")
        _check_revision(revision, entry)
        return set_entry(plan, target, status="debated", **common, **revision)

    replacements = resolution.get("split_into") or []
    if debate["target"]["list"] != "nodes":
        raise DebateIncomplete(
            f"{target}: a split may only replace a node carve — a replacement is node-shaped"
            f" (`kind: concept|feature`) and this debate targets"
            f" {debate['target']['list']}. To change an edge, revise or drop it.")
    if len(replacements) < 2:
        raise DebateIncomplete(f"{target}: a split needs at least two replacement carves")
    updated = set_entry(plan, target, status="dropped", **common,
                        drop_reason=f"split into"
                                    f" {', '.join(r['key'] for r in replacements)}:"
                                    f" {resolution['rationale']}")
    updated["nodes"] = [*updated["nodes"], *replacements]
    return updated


def run_debate(ctx, cycle: Cycle, plan: dict, key: str, *, repo_root: Path | None,
               config: ResearchConfig, lookup: ChunkLookup, moderator_ctx,
               mcp_servers: dict | None = None, allowed_tools=(),
               prompts: DebatePrompts | None = None,
               today: str | None = None) -> tuple[dict, dict]:
    """One structured debate over one contested carve.

    @param ctx: the debate's `RunContext` — opened by the caller with `debate_id=` so the
        transcript is greppable by debate (D18).
    @param moderator_ctx: a **separate** `RunContext`. §7.2's fresh-context moderator is a
        property of the session, not a sentence in a prompt.
    @returns: `(updated plan, debate record)`; the record is already saved.
    @raises ValueError: the carve is not contested, or already has a debate.
    @raises SignOffMissing / SignOffStale: before any Claude message.
    @raises DebateIncomplete: the moderator returned a resolution this plan cannot apply."""
    import datetime as _dt

    require_sign_off(cycle, repo_root=repo_root)
    list_name, entry = find_entry(plan, key)
    if not entry.get("contested"):
        raise ValueError(f"{key} is not contested; §7.2 has no debate for it")
    if entry.get("debate_id"):
        raise ValueError(f"{key} already has debate {entry['debate_id']}")

    prompts = prompts or DebatePrompts.load()
    debate_config = config.draft.debate
    personas = {"proposer": "the ontologist", "moderator": "the moderator",
                **debate_config.personas}
    entry_kind = {"nodes": "node carve", "edges": "feature-to-feature edge",
                  "quality_edges": "quality assessment", "dimensions": "layer-3 dimension",
                  "qualities": "quality-vocabulary entry"}[list_name]
    rendered = render_entry(entry)
    triggers = ", ".join(entry["contested"])
    messages: list[dict] = []

    def add(role: str, persona: str, text: str, challenges=None) -> None:
        message = {"seq": len(messages) + 1, "role": role, "persona": persona, "text": text}
        if challenges:
            message["challenges"] = challenges
        messages.append(message)

    opening, _ = run_structured(
        ctx, prompts.proposer,
        {"theme_label": cycle.theme, "entry_kind": entry_kind, "entry": rendered,
         "triggers": triggers, "challenges": "(open with your case for this carve)"},
        output_model=ProposerOut, role_config=debate_config.proposer,
        mcp_servers=mcp_servers, allowed_tools=allowed_tools)
    add("proposer", personas["proposer"], opening.text)

    for role, persona_key in (("challenger-a", "challenger_a"), ("challenger-b",
                                                                 "challenger_b")):
        out, _ = run_structured(
            ctx, prompts.challenger,
            {"theme_label": cycle.theme, "persona": personas[persona_key],
             "entry_kind": entry_kind, "entry": rendered, "triggers": triggers,
             "proposer_statement": opening.text,
             "challenge_types": "\n".join(f"- {name}" for name in CHALLENGE_TYPES),
             "max_challenges": str(debate_config.challenger.max_candidates)},
            output_model=ChallengerOut, role_config=debate_config.challenger,
            mcp_servers=mcp_servers, allowed_tools=allowed_tools)
        add(role, personas[persona_key], out.text,
            _bind_challenges(out, lookup=lookup, key=key))

    reply, _ = run_structured(
        ctx, prompts.proposer,
        {"theme_label": cycle.theme, "entry_kind": entry_kind, "entry": rendered,
         "triggers": triggers,
         "challenges": "The challenges raised against your carve:\n\n"
                       + _render_challenges(messages)},
        output_model=ProposerOut, role_config=debate_config.proposer,
        mcp_servers=mcp_servers, allowed_tools=allowed_tools)
    add("proposer", personas["proposer"], reply.text)

    # The moderator: its own context, no corpus tools, only the rendered record.
    verdict, _ = run_structured(
        moderator_ctx, prompts.moderator,
        {"theme_label": cycle.theme, "entry_kind": entry_kind, "entry": rendered,
         "triggers": triggers, "transcript": _render_transcript(messages),
         "dispositions": "\n".join(f"- {name}: {help_text}"
                                   for name, help_text in _DISPOSITION_HELP.items())},
        output_model=ModeratorOut, role_config=debate_config.moderator)
    add("moderator", personas["moderator"], verdict.rationale)

    if len(messages) > debate_config.max_messages:
        raise DebateIncomplete(f"{key}: {len(messages)} messages exceeds the configured cap"
                               f" of {debate_config.max_messages} (§7.2)")

    record = {
        "id": next_debate_id(cycle.slug, repo_root=repo_root), "cycle": cycle.number,
        "theme": cycle.theme, "target": {"list": list_name, "key": key},
        "opened": today or _dt.date.today().isoformat(),
        "runs": {"debate": ctx.run_id, "moderator": moderator_ctx.run_id},
        "triggers": list(entry["contested"]), "personas": personas,
        "pre_challenge": dict(entry), "messages": messages,
        "resolution": {
            "outcome": resolution_outcome(verdict.disposition),
            "disposition": verdict.disposition,
            "standing_dissent": verdict.standing_dissent,
            "rounds": 0,                      # filled below, from the messages themselves
            "upheld_challenges": [c for c in verdict.upheld_challenges
                                  if c in CHALLENGE_TYPES],
            "rationale": verdict.rationale},
    }
    record["resolution"]["rounds"] = rounds(record)
    for field, value in (("revision", verdict.revision),
                         ("merge_into", verdict.merge_into),
                         ("drop_reason", verdict.drop_reason)):
        if value:
            record["resolution"][field] = value
    if verdict.split_into:
        record["resolution"]["split_into"] = [
            _split_entry(item, lookup=lookup, debate_id=record["id"])
            for item in verdict.split_into]
    if verdict.contradiction:
        record["resolution"]["contradiction"] = verdict.contradiction.model_dump()

    updated = apply_resolution(plan, record, lookup=lookup)
    save_debate(record, repo_root=repo_root)
    return updated, record


def _split_entry(item: SplitOut, *, lookup: ChunkLookup, debate_id: str) -> dict:
    """A replacement carve, in plan shape. It arrives already debated: the debate that
    produced it is the one that scrutinised it."""
    evidence, _warnings = bind_evidence(item.evidence, lookup=lookup, what=item.key)
    entry = {"key": item.key, "from_candidates": list(item.from_candidates or [item.key]),
             "kind": item.kind, "id": item.id, "name": item.name, "summary": item.summary,
             "evidence": evidence, "contested": [], "debate_id": debate_id,
             "status": "debated", "verification": None, "note": item.note}
    if item.kind == "feature":
        entry.update({"layer": item.layer, "dimension": item.dimension,
                      "cross_cutting": item.cross_cutting, "aliases": list(item.aliases),
                      "realizes": list(item.realizes)})
    return entry
