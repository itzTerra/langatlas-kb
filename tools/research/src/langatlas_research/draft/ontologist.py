"""R4's ontologist (Claude, judgment lane): a candidate inventory in, a carve plan out.

Kept a separate role from 3B's surveyor on purpose (§7.4) — a session that both harvests and
carves will carve to match its own harvest. It gets the corpus as live pipeline-mediated tools
and no finding aids: a finding aid is a coverage lead for R3, and it is never a citation
(D29/D53), so it has no business in a step whose output must be sourced.

Nothing the model types about *identity* is trusted: evidence is bound from chunk ids, layer-3
nodes must name a dimension that exists or that this same output proposes, and every `realizes`
target must be a node this output mints or one already committed. A model that gets those wrong
fails the run — the plan is a store proposal, and a proposal that cannot validate is not worth
carrying forward."""
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from langatlas_pipeline.prompts import PromptRef, load_prompt
from langatlas_pipeline.transcripts.writer import utc_now
from langatlas_research.config import ResearchConfig
from langatlas_research.cycle import Cycle, require_sign_off
from langatlas_research.draft.evidence import EvidenceItem, bind_evidence
from langatlas_research.draft.plan import build_plan_record
from langatlas_research.errors import DraftOutputInvalid
from langatlas_research.survey.chunks import ChunkLookup
from langatlas_research.survey.claude import run_structured
from langatlas_research.themes import load_themes
from langatlas_validate.ids import is_valid_slug
from langatlas_validate.store import iter_store_records

ONTOLOGIST_PROMPT_ID = "r4-ontologist"

_LAYERS = ("1 syntax — surface constructs a programmer writes",
           "2 semantic — meaning and behaviour, independent of surface form",
           "3 design-choice — a position on an axis other languages take differently"
           " (requires a dimension)")


class NodeOut(BaseModel):
    key: str
    id: str
    kind: Literal["concept", "feature"]
    from_candidates: list[str] = Field(default_factory=list)
    name: str
    summary: str
    layer: int | None = None
    dimension: str | None = None
    cross_cutting: bool = False
    aliases: list[str] = Field(default_factory=list)
    realizes: list[str] = Field(default_factory=list)
    excluded_rationale: str | None = None
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=3)
    note: str = ""
    contested_note: str | None = None


class DimensionOut(BaseModel):
    key: str
    slug: str
    label: str
    values: list[str] = Field(min_length=2)
    exclusivity: Literal["exclusive", "multi"] = "exclusive"
    applies_to: list[str] = Field(default_factory=lambda: ["general-purpose"])
    note: str = ""
    contested_note: str | None = None


class FindingOut(BaseModel):
    kind: Literal["rule-candidate", "cross-theme-edge", "unmappable-candidate",
                  "missing-locator-backend"]
    detail: str
    keys: list[str] = Field(default_factory=list)


class OntologistOut(BaseModel):
    nodes: list[NodeOut]
    dimensions: list[DimensionOut] = Field(default_factory=list)
    findings: list[FindingOut] = Field(default_factory=list)


@dataclass(frozen=True)
class StoreView:
    """What the store already holds, so the ontologist neither re-mints a committed node nor
    proposes a dimension that exists."""

    concepts: frozenset[str]
    features: frozenset[str]
    dimensions: frozenset[str]

    @property
    def nodes(self) -> frozenset[str]:
        return self.concepts | self.features


def read_store(repo_root: Path | None) -> StoreView:
    from langatlas_research.draft.minting import committed_dimensions

    root = Path(repo_root) if repo_root else Path(".")
    concepts, features = set(), set()
    for _path, kind, _text, data in iter_store_records(root):
        if kind == "concept":
            concepts.add(data["id"])
        elif kind == "feature":
            features.add(data["id"])
    return StoreView(concepts=frozenset(concepts), features=frozenset(features),
                     dimensions=frozenset(committed_dimensions(root)))


def ontologist_tools(ctx, conn) -> tuple[dict, tuple[str, ...]]:
    """Corpus tools only — no finding aids, no built-ins (no filesystem, shell or web)."""
    from langatlas_ingest.tools import SERVER_NAME, TOOL_NAMES, sdk_source_tools

    return {SERVER_NAME: sdk_source_tools(ctx, conn)}, tuple(TOOL_NAMES)


def render_candidates(ctx, survey: dict, *, limit: int) -> str:
    """The candidate packet, through D31's door: a survey is machine-written but its glosses
    and aliases are model text derived from documents, so it is data, never instructions."""
    lines = []
    for candidate in (survey.get("candidates") or [])[:limit]:
        aliases = ", ".join(a["label"] for a in candidate.get("aliases") or [])
        lines.append(f"- key: {candidate['key']}")
        lines.append(f"  name: {candidate['name']}  [hint: {candidate['kind_hint']}]")
        lines.append(f"  gloss: {candidate['gloss']}")
        if aliases:
            lines.append(f"  aliases: {aliases}")
        for evidence in candidate["evidence"]:
            lines.append(f"  evidence: {evidence['chunk_id']}  ({evidence['source_id']}"
                         f" {evidence['locator']})")
    return ctx.tool_result(tool="r3-survey", text="\n".join(lines), kind="survey-inventory")


def _check_shape(out: OntologistOut, store: StoreView, max_nodes: int) -> None:
    """Every structural rule the record schemas would reject later, checked here so the
    developer reads one message naming all of them instead of one per mint attempt."""
    errors: list[str] = []
    if len(out.nodes) > max_nodes:
        errors.append(f"{len(out.nodes)} nodes exceeds the configured cap of {max_nodes}")

    proposed_dimensions = {d.slug for d in out.dimensions}
    known_dimensions = proposed_dimensions | store.dimensions
    concept_ids = {n.id for n in out.nodes if n.kind == "concept"} | store.concepts
    keys: set[str] = set()

    for dimension in out.dimensions:
        for slug in (dimension.key, dimension.slug, *dimension.values):
            if not is_valid_slug(slug):
                errors.append(f"dimension {dimension.slug}: {slug!r} is not a valid slug")
        if dimension.slug in store.dimensions:
            errors.append(f"dimension {dimension.slug!r} is already committed; changing an"
                          f" existing dimension is a restructure, not a mint")
        if dimension.key in keys:
            errors.append(f"key {dimension.key!r} appears twice")
        keys.add(dimension.key)

    for node in out.nodes:
        if not is_valid_slug(node.key) or not is_valid_slug(node.id):
            errors.append(f"node {node.key!r}/{node.id!r}: not a valid slug (§3.5)")
        if node.key in keys:
            errors.append(f"key {node.key!r} appears twice")
        keys.add(node.key)
        if node.id in store.nodes:
            errors.append(f"node {node.id!r} is already committed; extend or point at it"
                          f" instead of re-minting it")
        if node.kind == "feature":
            if node.layer not in (1, 2, 3):
                errors.append(f"node {node.key}: feature layer must be 1, 2 or 3")
            if node.layer == 3 and not node.dimension:
                errors.append(f"node {node.key}: a layer-3 feature must name a dimension")
            if node.dimension and node.dimension not in known_dimensions:
                errors.append(f"node {node.key}: dimension {node.dimension!r} is neither"
                              f" committed nor proposed in this run")
            for concept_id in node.realizes:
                if concept_id not in concept_ids:
                    errors.append(f"node {node.key}: realizes {concept_id!r}, which is"
                                  f" neither a concept in this run nor a committed one")
        elif node.layer is not None or node.dimension:
            errors.append(f"node {node.key}: a concept has no layer or dimension")
    if errors:
        raise DraftOutputInvalid(f"{ONTOLOGIST_PROMPT_ID}: " + "; ".join(errors))


def _tail(contested_note: str | None, note: str) -> dict:
    entry = {"contested": ["ontologist-flagged"] if contested_note else [],
             "debate_id": None, "status": "proposed", "verification": None,
             "note": " ".join(part for part in (note, contested_note) if part)}
    return entry


def run_ontologist(ctx, cycle: Cycle, *, repo_root: Path | None, survey: dict,
                   lookup: ChunkLookup, config: ResearchConfig, mcp_servers: dict | None = None,
                   allowed_tools=(), prompt: PromptRef | None = None,
                   now: str | None = None) -> tuple[dict, list[str]]:
    """@raises SignOffMissing / SignOffStale: before any Claude message.
    @raises DraftOutputInvalid: the run produced no usable output, or output whose shape the
        record schemas would reject.
    @raises EvidenceUnresolvable: a carve's every evidence chunk id failed to resolve."""
    require_sign_off(cycle, repo_root=repo_root)
    role = config.draft.ontologist
    store = read_store(repo_root)
    theme = load_themes(repo_root)[cycle.theme]

    variables = {
        "theme_label": theme.label, "theme_summary": theme.summary,
        "layers": "\n".join(f"- {line}" for line in _LAYERS),
        "dimensions": ", ".join(sorted(store.dimensions)) or "(none yet)",
        "committed_nodes": ", ".join(sorted(store.nodes)) or "(none yet)",
        "max_nodes": str(role.max_candidates),
        "candidates": render_candidates(ctx, survey, limit=role.max_packet_terms),
    }
    out, _ = run_structured(ctx, prompt or load_prompt(ONTOLOGIST_PROMPT_ID), variables,
                            output_model=OntologistOut, role_config=role,
                            mcp_servers=mcp_servers, allowed_tools=allowed_tools)
    _check_shape(out, store, role.max_candidates)

    plan = build_plan_record(cycle=cycle, ontologist_run_id=ctx.run_id,
                             generated_at=now or utc_now())
    warnings: list[str] = []
    for dimension in out.dimensions:
        plan["dimensions"].append({
            "key": dimension.key, "slug": dimension.slug, "label": dimension.label,
            "values": list(dimension.values), "exclusivity": dimension.exclusivity,
            "applies_to": list(dimension.applies_to),
            **_tail(dimension.contested_note, dimension.note)})
    for node in out.nodes:
        evidence, node_warnings = bind_evidence(node.evidence, lookup=lookup, what=node.key)
        warnings.extend(node_warnings)
        entry = {"key": node.key, "from_candidates": list(node.from_candidates or [node.key]),
                 "kind": node.kind, "id": node.id, "name": node.name,
                 "summary": node.summary, "evidence": evidence,
                 **_tail(node.contested_note, node.note)}
        if node.kind == "feature":
            entry.update({"layer": node.layer, "dimension": node.dimension,
                          "cross_cutting": node.cross_cutting,
                          "aliases": list(node.aliases), "realizes": list(node.realizes)})
        elif node.excluded_rationale:
            entry["excluded_rationale"] = node.excluded_rationale
        plan["nodes"].append(entry)
    plan["findings"] = [finding.model_dump() for finding in out.findings]

    for warning in warnings:
        ctx.writer.append(role="system", content=warning, flags=["r4:draft-warning"])
    return plan, warnings
