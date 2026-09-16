"""R4's edge drafter (Claude, judgment lane): committed nodes in, edges out.

A separate role from the ontologist on purpose (§7.4): the session that decided what the nodes
are is the wrong one to decide how they connect, because it will connect them the way it carved
them. It runs after the nodes are committed and sees them as ids, not as proposals.

Endpoints are checked against the store rather than trusted: an edge to a node that does not
exist fails `validate_references` inside `land_record`, which is a far more expensive way to find
out. Feature-to-feature is enforced here too — §3.1's five edge types connect features, and a
concept endpoint is a category error the schema cannot catch (both are plain id strings)."""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from langatlas_pipeline.prompts import PromptRef, load_prompt
from langatlas_research.config import ResearchConfig
from langatlas_research.cycle import Cycle, require_sign_off
from langatlas_research.draft.contested import mark_contested
from langatlas_research.draft.evidence import EvidenceItem, bind_evidence
from langatlas_research.draft.minting import committed_qualities
from langatlas_research.errors import DraftOutputInvalid
from langatlas_research.survey.chunks import ChunkLookup
from langatlas_research.survey.claude import run_structured
from langatlas_research.themes import load_themes
from langatlas_validate.ids import canonical_endpoints, is_valid_slug

EDGE_DRAFTER_PROMPT_ID = "r4-edge-drafter"

_EDGE_TYPES = {
    "requires": "`from` cannot exist in a language without `to`",
    "enables": "`from` makes `to` possible or practical, without requiring it",
    "influences": "`from` shapes how `to` is designed or used; needs a polarity of + or -",
    "conflicts-with": "the two cannot sensibly coexist in one language",
    "alternative-to": "the two are competing answers to the same design question (symmetric)",
}


class EdgeOut(BaseModel):
    type: Literal["requires", "enables", "influences", "conflicts-with", "alternative-to"]
    frm: str = Field(alias="from")
    to: str
    polarity: Literal["+", "-"] | None = None
    statement: str
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=3)
    note: str = ""

    model_config = {"populate_by_name": True}


class AssessmentOut(BaseModel):
    key: str
    polarity: Literal["improves", "hurts"]
    strength: Literal["weak", "moderate", "strong"]
    statement: str
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=3)


class QualityEdgeOut(BaseModel):
    frm: str = Field(alias="from")
    to: str
    assessments: list[AssessmentOut] = Field(min_length=1)
    note: str = ""

    model_config = {"populate_by_name": True}


class QualityOut(BaseModel):
    key: str
    slug: str
    label: str
    summary: str
    note: str = ""


class EdgeFindingOut(BaseModel):
    kind: Literal["rule-candidate", "cross-theme-edge", "unmappable-candidate",
                  "missing-locator-backend"]
    detail: str
    keys: list[str] = Field(default_factory=list)


class EdgeDrafterOut(BaseModel):
    edges: list[EdgeOut] = Field(default_factory=list)
    quality_edges: list[QualityEdgeOut] = Field(default_factory=list)
    qualities: list[QualityOut] = Field(default_factory=list)
    findings: list[EdgeFindingOut] = Field(default_factory=list)


def edge_key(edge_type: str, frm: str, to: str) -> str:
    """The plan's key for an edge. Readable rather than the composed record id, because a
    developer reading a plan diff is the audience; the record id is composed at mint time."""
    return f"{frm}--{edge_type}--{to}"


def render_nodes(ctx, store, features_by_id: dict) -> str:
    lines = [f"- {node_id} — layer {features_by_id.get(node_id, {}).get('layer', '?')} —"
             f" {features_by_id.get(node_id, {}).get('name', node_id)}"
             for node_id in sorted(store.features)]
    lines += [f"- {node_id} — concept (not a legal edge endpoint) —"
              f" {features_by_id.get(node_id, {}).get('name', node_id)}"
              for node_id in sorted(store.concepts)]
    return ctx.tool_result(tool="ontology-store", text="\n".join(lines), kind="store-nodes")


def _check_shape(out: EdgeDrafterOut, store, known_qualities: set[str],
                 max_edges: int) -> None:
    errors: list[str] = []
    if len(out.edges) + len(out.quality_edges) > max_edges:
        errors.append(f"{len(out.edges) + len(out.quality_edges)} edges exceeds the"
                      f" configured cap of {max_edges}")
    qualities = known_qualities | {quality.slug for quality in out.qualities}

    for quality in out.qualities:
        if not is_valid_slug(quality.slug):
            errors.append(f"quality {quality.slug!r}: not a valid slug (§3.5)")
        if quality.slug in known_qualities:
            errors.append(f"quality {quality.slug!r} is already committed")

    for edge in out.edges:
        for endpoint in (edge.frm, edge.to):
            if endpoint in store.concepts:
                errors.append(f"{edge.type} {edge.frm}->{edge.to}: {endpoint!r} is a"
                              f" concept; §3.1's edge types connect features")
            elif endpoint not in store.features:
                errors.append(f"{edge.type} {edge.frm}->{edge.to}: {endpoint!r} is not a"
                              f" committed node")
        if edge.frm == edge.to:
            errors.append(f"{edge.type} {edge.frm}->{edge.to}: an edge to itself")
        if edge.type == "influences" and edge.polarity is None:
            errors.append(f"influences {edge.frm}->{edge.to}: needs a polarity of + or -")
        if edge.type != "influences" and edge.polarity is not None:
            errors.append(f"{edge.type} {edge.frm}->{edge.to}: only `influences` carries a"
                          f" polarity")

    for edge in out.quality_edges:
        if edge.frm not in store.features:
            errors.append(f"affects-quality {edge.frm}->{edge.to}: {edge.frm!r} is not a"
                          f" committed feature")
        if edge.to not in qualities:
            errors.append(f"affects-quality {edge.frm}->{edge.to}: quality {edge.to!r} is"
                          f" neither committed nor proposed in this run")
        for assessment in edge.assessments:
            if not is_valid_slug(assessment.key):
                errors.append(f"affects-quality {edge.frm}->{edge.to}: assessment key"
                              f" {assessment.key!r} is not a valid slug (§3.3: minted once,"
                              f" immutable)")
    if errors:
        raise DraftOutputInvalid(f"{EDGE_DRAFTER_PROMPT_ID}: " + "; ".join(errors))


def _tail(note: str) -> dict:
    return {"contested": [], "debate_id": None, "status": "proposed", "verification": None,
            "note": note}


def run_edge_drafter(ctx, cycle: Cycle, plan: dict, *, repo_root: Path | None,
                     lookup: ChunkLookup, config: ResearchConfig,
                     mcp_servers: dict | None = None, allowed_tools=(),
                     prompt: PromptRef | None = None,
                     store=None) -> tuple[dict, list[str]]:
    """@raises SignOffMissing / SignOffStale: before any Claude message.
    @raises DraftOutputInvalid: output whose endpoints, polarity or quality targets the store
        or the record schemas would reject.
    @raises EvidenceUnresolvable: an edge whose every evidence chunk id failed to resolve."""
    require_sign_off(cycle, repo_root=repo_root)
    if store is None:
        from langatlas_research.draft.ontologist import read_store

        store = read_store(repo_root)
    role = config.draft.edge_drafter
    known_qualities = committed_qualities(repo_root)
    theme = load_themes(repo_root)[cycle.theme]

    features_by_id = {entry["id"]: entry for entry in plan.get("nodes") or []}
    variables = {
        "theme_label": theme.label,
        "nodes": render_nodes(ctx, store, features_by_id),
        "qualities": ", ".join(sorted(known_qualities)) or "(empty — propose what you need)",
        "edge_types": "\n".join(f"- {name}: {help_text}"
                                for name, help_text in _EDGE_TYPES.items()),
        "max_edges": str(role.max_candidates),
    }
    out, _ = run_structured(ctx, prompt or load_prompt(EDGE_DRAFTER_PROMPT_ID), variables,
                            output_model=EdgeDrafterOut, role_config=role,
                            mcp_servers=mcp_servers, allowed_tools=allowed_tools)
    _check_shape(out, store, known_qualities, role.max_candidates)

    updated = dict(plan)
    updated["runs"] = {**plan["runs"], "edge_drafter": ctx.run_id}
    warnings: list[str] = []

    updated["qualities"] = [*(plan.get("qualities") or []),
                            *({"key": quality.key, "slug": quality.slug,
                               "label": quality.label, "summary": quality.summary,
                               **_tail(quality.note)} for quality in out.qualities)]

    new_edges = []
    for edge in out.edges:
        frm, to = edge.frm, edge.to
        if edge.type == "alternative-to":
            frm, to = canonical_endpoints(frm, to)
        key = edge_key(edge.type, frm, to)
        evidence, edge_warnings = bind_evidence(edge.evidence, lookup=lookup, what=key)
        warnings.extend(edge_warnings)
        new_edges.append({"key": key, "type": edge.type, "from": frm, "to": to,
                          "polarity": edge.polarity, "statement": edge.statement,
                          "evidence": evidence, **_tail(edge.note)})
    updated["edges"] = [*(plan.get("edges") or []), *new_edges]

    new_quality_edges = []
    for edge in out.quality_edges:
        key = edge_key("affects-quality", edge.frm, edge.to)
        assessments = []
        for assessment in edge.assessments:
            evidence, assessment_warnings = bind_evidence(
                assessment.evidence, lookup=lookup, what=f"{key}[{assessment.key}]")
            warnings.extend(assessment_warnings)
            assessments.append({"key": assessment.key, "polarity": assessment.polarity,
                                "strength": assessment.strength,
                                "statement": assessment.statement, "evidence": evidence})
        new_quality_edges.append({"key": key, "from": edge.frm, "to": edge.to,
                                  "assessments": assessments, **_tail(edge.note)})
    updated["quality_edges"] = [*(plan.get("quality_edges") or []), *new_quality_edges]

    updated["findings"] = [*(plan.get("findings") or []),
                           *(finding.model_dump() for finding in out.findings)]

    for warning in warnings:
        ctx.writer.append(role="system", content=warning, flags=["r4:draft-warning"])
    return mark_contested(updated, repo_root=repo_root, store=store), warnings
