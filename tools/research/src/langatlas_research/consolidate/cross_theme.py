"""R6's cross-theme edge pass (§7.4: per-theme work "systematically under-collects
boundary-crossing edges").

R4's edge drafter sees every committed node but is asked about one theme, so an edge into
another theme is exactly what it drops — at best it files a `cross-theme-edge` finding. This
pass asks the other question. Its entries join the cycle's own carve plan marked `pass: r6`,
so 3C's debate, gate and mint steps treat them exactly like R4's: one admissibility path.

Theme membership is the cycles' `nodes_minted` (3A)."""
from pathlib import Path

from pydantic import BaseModel, Field

from langatlas_pipeline.prompts import PromptRef, load_prompt
from langatlas_research.config import ResearchConfig
from langatlas_research.cycle import Cycle, load_cycle, require_sign_off
from langatlas_research.draft.contested import mark_contested
from langatlas_research.draft.edges import (
    EDGE_TYPES, EdgeDrafterOut, EdgeFindingOut, EdgeOut, append_edges, check_shape, edge_key,
)
from langatlas_research.draft.ontologist import read_store
from langatlas_research.draft.plan import load_plan
from langatlas_research.errors import DraftOutputInvalid
from langatlas_research.paths import REPO_ROOT, cycles_dir, drafts_dir
from langatlas_research.survey.chunks import ChunkLookup
from langatlas_research.survey.claude import run_structured
from langatlas_research.themes import load_themes
from langatlas_validate.ids import canonical_endpoints, compose_edge_id
from langatlas_validate.migrate import iter_manifests
from langatlas_validate.store import iter_store_records
from langatlas_validate.tombstones import load_tombstones

CROSS_THEME_PROMPT_ID = "r6-cross-theme-edge-drafter"


class CrossThemeOut(BaseModel):
    edges: list[EdgeOut] = Field(default_factory=list)
    findings: list[EdgeFindingOut] = Field(default_factory=list)


def theme_membership(repo_root: Path | None = None) -> dict[str, str]:
    """@returns: record id -> theme slug; the first cycle to mint an id owns it."""
    membership: dict[str, str] = {}
    for path in sorted(cycles_dir(repo_root).glob("*.yaml")):
        cycle = load_cycle(int(path.name[:2]), repo_root=repo_root)
        for record_id in cycle.nodes_minted:
            membership.setdefault(record_id, cycle.theme)
    return membership


def _split(store, membership: dict[str, str], theme: str) -> tuple[list[str], list[str]]:
    mine = sorted(f for f in store.features if membership.get(f) == theme)
    others = sorted(f for f in store.features if membership.get(f) not in (None, theme))
    return mine, others


def skip_reason(repo_root: Path | None, cycle: Cycle, *, store=None) -> str | None:
    """Why the pass has nothing to do — so the CLI never opens a Claude session for it."""
    store = store or read_store(repo_root)
    mine, others = _split(store, theme_membership(repo_root), cycle.theme)
    if not mine:
        return f"theme {cycle.theme!r} has no committed features"
    if not others:
        return "no other theme has committed features yet"
    return None


def cross_theme_leads(repo_root: Path | None, *, cycle: Cycle) -> list[str]:
    """Earlier drafters' `cross-theme-edge` findings, from every cycle, plus the edges this
    cycle's migrations requeued for redrafting. Hints, never evidence."""
    root = Path(repo_root) if repo_root else REPO_ROOT
    leads = []
    directory = drafts_dir(root)
    for path in sorted(directory.glob("*.yaml")) if directory.exists() else []:
        for finding in load_plan(path.stem, repo_root=root).get("findings") or []:
            if finding["kind"] == "cross-theme-edge":
                keys = f" ({', '.join(finding['keys'])})" if finding.get("keys") else ""
                leads.append(f"{path.stem}: {finding['detail']}{keys}")
    migrations = {manifest["migration_id"] for _rel, manifest in iter_manifests(root)
                  if manifest.get("cycle") == cycle.number}
    for entry in load_tombstones(root):
        if entry.get("migration_id") in migrations and entry["action"] == "requeue":
            leads.append(f"requeued by {entry['migration_id']}: {entry['anchor']} — redraft it"
                         f" against the migrated nodes")
    return leads


def _records(repo_root: Path | None, kind: str) -> list[dict]:
    root = Path(repo_root) if repo_root else REPO_ROOT
    return [data for _path, record_kind, _text, data in iter_store_records(root)
            if record_kind == kind]


def _check_crossing(out: CrossThemeOut, *, cycle: Cycle, membership: dict, plan: dict,
                    committed: set[str], store, max_edges: int) -> None:
    check_shape(EdgeDrafterOut(edges=out.edges), store, set(), max_edges)
    plan_keys = {entry["key"] for entry in plan.get("edges") or []}
    errors = []
    for edge in out.edges:
        frm, to = edge.frm, edge.to
        if edge.type == "alternative-to":
            frm, to = canonical_endpoints(frm, to)
        themes = {membership.get(frm), membership.get(to)}
        if cycle.theme not in themes or None in themes or len(themes) != 2:
            errors.append(f"{edge.type} {frm}->{to}: does not cross from {cycle.theme!r} into"
                          f" another theme")
        if compose_edge_id(edge.type, frm, to) in committed:
            errors.append(f"{edge.type} {frm}->{to}: already committed")
        if edge_key(edge.type, frm, to) in plan_keys:
            errors.append(f"{edge.type} {frm}->{to}: already in the carve plan")
    if errors:
        raise DraftOutputInvalid(f"{CROSS_THEME_PROMPT_ID}: " + "; ".join(errors))


def run_cross_theme(ctx, cycle: Cycle, plan: dict, record: dict, *, repo_root: Path | None,
                    lookup: ChunkLookup, config: ResearchConfig, mcp_servers: dict | None = None,
                    allowed_tools=(), prompt: PromptRef | None = None, store=None,
                    names: dict | None = None) -> tuple[dict, dict, list[str]]:
    """@param names: feature id -> name; None reads the store (tests inject it).
    @returns: `(updated carve plan, updated consolidation record, evidence warnings)`.
    @raises SignOffMissing / SignOffStale: before any Claude message.
    @raises DraftOutputInvalid: an edge that does not cross themes, duplicates a committed edge
        or a plan entry, or breaks R4's shape rules."""
    require_sign_off(cycle, repo_root=repo_root)
    store = store or read_store(repo_root)
    reason = skip_reason(repo_root, cycle, store=store)
    if reason:
        return plan, {**record, "cross_theme": {"run": None, "skipped": reason, "edges": []}}, []

    membership = theme_membership(repo_root)
    if names is None:
        names = {data["id"]: data["name"] for data in _records(repo_root, "feature")}
    themes = load_themes(repo_root)
    role = config.consolidation.cross_theme_drafter
    mine, others = _split(store, membership, cycle.theme)
    committed = {data["id"]: data for data in _records(repo_root, "edge")}
    touching = sorted(f"{e['from']} {e['type']} {e['to']}" for e in committed.values()
                      if e["from"] in mine or e["to"] in mine)

    def label(theme: str) -> str:
        return themes[theme].label if theme in themes else theme

    def store_data(text: str, kind: str) -> str:
        return ctx.tool_result(tool="ontology-store", text=text, kind=kind)

    variables = {
        "theme_label": label(cycle.theme),
        "nodes": store_data("\n".join(f"- {f} — {names.get(f, f)}" for f in mine),
                            "store-nodes"),
        "other_nodes": store_data("\n".join(f"- {f} — {names.get(f, f)} ({label(membership[f])})"
                                            for f in others[:role.max_packet_terms]),
                                  "store-nodes"),
        "existing_edges": store_data("\n".join(touching) or "(none yet)", "store-edges"),
        "leads": ctx.tool_result(tool="r6-leads", kind="r6-leads",
                                 text="\n".join(cross_theme_leads(repo_root, cycle=cycle))
                                 or "(none)"),
        "edge_types": "\n".join(f"- {name}: {text}" for name, text in EDGE_TYPES.items()),
        "max_edges": str(role.max_candidates),
    }
    out, _ = run_structured(ctx, prompt or load_prompt(CROSS_THEME_PROMPT_ID), variables,
                            output_model=CrossThemeOut, role_config=role,
                            mcp_servers=mcp_servers, allowed_tools=allowed_tools)
    _check_crossing(out, cycle=cycle, membership=membership, plan=plan,
                    committed=set(committed), store=store, max_edges=role.max_candidates)

    updated, warnings = append_edges(ctx, plan, out.edges, lookup=lookup, pass_="r6")
    updated["findings"] = [*(plan.get("findings") or []),
                           *(finding.as_entry() for finding in out.findings)]
    for warning in warnings:
        ctx.writer.append(role="system", content=warning, flags=["r6:draft-warning"])
    new_keys = [entry["key"] for entry in updated["edges"][len(plan.get("edges") or []):]]
    record = {**record, "cross_theme": {"run": ctx.run_id, "skipped": None,
                                        "edges": [*record["cross_theme"]["edges"], *new_keys]}}
    return mark_contested(updated, repo_root=repo_root, store=store), record, warnings
