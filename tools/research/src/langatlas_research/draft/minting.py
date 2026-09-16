"""Turning an admitted carve plan into committed records.

Order is the whole content of this file. `validate_references` runs inside `land_record` after
every rebase, so a record whose references are not yet committed does not "land and get fixed
later" — it fails the commit. D45's contradiction ledger goes first of all: it is a *tracked*
file a debate may already have written, and an unlanded change to a tracked file makes
`land_record`'s rebase refuse, so nothing else in the batch could land behind it. Dimensions
and qualities are shared-file mints too, so they go next and go through `land_drafts`'
re-render path; then concepts, because a feature may `realize` one; then features; then edges,
whose endpoints must already exist.

Two refusals live here rather than in the CLI, so no caller can route around them: an entry the
gate did not admit is never minted (D1/D4 — the gate is the admissibility authority), and a
contested carve with neither a debate nor a waiver is never minted (§7.2)."""
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.draft.contradictions import contradictions_mint, contradictions_pending
from langatlas_research.draft.evidence import as_drafts
from langatlas_research.draft.plan import ENTRY_LISTS, entries, set_entry
from langatlas_research.drafts import (
    Assessment, ConceptDraft, EdgeDraft, FeatureDraft, Proposer, QualityEdgeDraft,
)
from langatlas_research.errors import NotAdmissible, UndebatedCarve
from langatlas_research.land import land_drafts
from langatlas_research.taxonomy import (
    DIMENSIONS_PATH, QUALITIES_PATH, mint_dimension, mint_quality,
)

_yaml = YAML(typ="safe")

RECORD_KINDS_BY_LIST = {
    "nodes": lambda entry: entry["kind"],
    "edges": lambda _entry: "edge",
    "quality_edges": lambda _entry: "affects-quality-edge",
}

# Which agent proposed each list's records, for `provenance.proposer.agent`. An agent's name
# is also its prompt id, which is what lets `plan_prompt_versions` resolve the version that
# produced each list without the plan having to carry one.
_AGENT_BY_LIST = {"nodes": "r4-ontologist", "edges": "r4-edge-drafter",
                  "quality_edges": "r4-edge-drafter"}


def plan_prompt_versions(*, loader=None) -> dict[str, str]:
    """`{plan list: the version of the prompt that drafts it}`, for `mint_items`.

    A mint batch mixes roles — the nodes came from the ontologist, the edges from the edge
    drafter — so `provenance.proposer.prompt_version` is resolved per list rather than once
    per batch. The agent name is not repeated here: the record already carries it.

    @param loader: injected for tests; production resolves the registry's latest version."""
    if loader is None:
        from langatlas_pipeline.prompts import load_prompt

        loader = load_prompt
    return {name: loader(agent).version for name, agent in _AGENT_BY_LIST.items()}


def _slugs(repo_root: Path | None, rel: str, key: str) -> set[str]:
    path = (Path(repo_root) if repo_root else Path(".")) / rel
    if not path.exists():
        return set()
    data = _yaml.load(path.read_text()) or {}
    return {entry["slug"] for entry in (data.get(key) or [])}


def committed_dimensions(repo_root: Path | None = None) -> set[str]:
    return _slugs(repo_root, DIMENSIONS_PATH, "dimensions")


def committed_qualities(repo_root: Path | None = None) -> set[str]:
    return _slugs(repo_root, QUALITIES_PATH, "qualities")


def entry_draft(entry: dict, *, plan: dict, ctx_run_id: str, prompt_version: str,
                agent: str | None = None, model: str = "claude"):
    """One plan entry -> the 3A draft object that renders it.

    @raises KeyError: the entry's shape matches no draft type."""
    proposer = Proposer(agent=agent or ("r4-ontologist" if "kind" in entry
                                        else "r4-edge-drafter"),
                        model=model, prompt_version=prompt_version)
    common = {"evidence": as_drafts(entry.get("evidence") or []), "proposer": proposer,
              "chat_run_id": ctx_run_id, "debate_id": entry.get("debate_id")}

    if "assessments" in entry:
        return QualityEdgeDraft(
            frm=entry["from"], to=entry["to"],
            assessments=tuple(
                Assessment(key=assessment["key"], assessor=proposer,
                           polarity=assessment["polarity"], strength=assessment["strength"],
                           statement=assessment["statement"],
                           evidence=as_drafts(assessment["evidence"]))
                for assessment in entry["assessments"]),
            proposer=proposer, chat_run_id=ctx_run_id, debate_id=entry.get("debate_id"))
    if "statement" in entry:
        return EdgeDraft(type=entry["type"], frm=entry["from"], to=entry["to"],
                         statement=entry["statement"], polarity=entry.get("polarity"),
                         **common)
    if entry["kind"] == "concept":
        draft = ConceptDraft(id=entry["id"], name=entry["name"], summary=entry["summary"],
                             **common)
        if entry.get("excluded_rationale"):
            from dataclasses import replace

            draft = replace(draft, excluded_rationale=entry["excluded_rationale"])
        return draft
    return FeatureDraft(id=entry["id"], name=entry["name"], summary=entry["summary"],
                        layer=entry["layer"], dimension=entry.get("dimension"),
                        cross_cutting=bool(entry.get("cross_cutting")),
                        aliases=tuple(entry.get("aliases") or ()),
                        realizes=tuple(entry.get("realizes") or ()), **common)


def _mintable(name: str, entry: dict) -> bool:
    """@raises UndebatedCarve / NotAdmissible: for an entry that must not be minted at all —
    as opposed to one that is simply not ready yet, which returns False."""
    if entry["status"] in ("dropped", "minted"):
        return False
    if entry.get("contested") and not entry.get("debate_id") and not entry.get("waiver"):
        raise UndebatedCarve(
            f"{entry['key']} is contested ({', '.join(entry['contested'])}) with no debate"
            f" and no developer waiver — run `draft debate` or `draft waive` (§7.2)")
    if name in RECORD_KINDS_BY_LIST:
        verification = entry.get("verification")
        if verification is None:
            return False
        if not verification["admissible"]:
            raise NotAdmissible(
                f"{entry['key']}: the D24 gate refused it ({verification['verdict']}"
                f"{': ' + verification['detail'] if verification.get('detail') else ''})."
                f" The gate is the admissibility authority (D1/D4); fix the claim or its"
                f" citations and re-run `draft verify`.")
        return True
    return entry["status"] in ("debated", "verified", "waived", "proposed")


def mint_items(plan: dict, *, repo_root: Path | None, ctx_run_id: str, prompt_version: str,
               prompt_versions: dict[str, str] | None = None,
               mint_contradictions: bool = False) -> list:
    """Every mintable entry, as a draft object or a zero-argument callable, in mint order.

    @param prompt_version: the fallback version, for a list `prompt_versions` does not name.
    @param prompt_versions: `{list name: prompt version}` — see `plan_prompt_versions`.
    @param mint_contradictions: prepend D45's ledger, for a cycle whose debate wrote one.
        `mint_plan` decides this; see `contradictions_pending`.
    @raises UndebatedCarve: a contested carve with no debate and no waiver.
    @raises NotAdmissible: an entry the gate refused."""
    items: list = []
    if mint_contradictions:
        items.append(lambda: contradictions_mint(repo_root))
    for name in ENTRY_LISTS:
        # Within "nodes", a concept must mint before any feature that realizes it — the
        # plan carries both kinds in one list, so ordering is stable-sorted here rather
        # than relying on carve order.
        list_entries = plan.get(name) or []
        if name == "nodes":
            list_entries = sorted(list_entries, key=lambda entry: entry["kind"] != "concept")
        for entry in list_entries:
            if not _mintable(name, entry):
                continue
            if name == "dimensions":
                items.append(lambda entry=entry: mint_dimension(
                    entry["slug"], label=entry["label"], values=entry["values"],
                    exclusivity=entry["exclusivity"], applies_to=entry["applies_to"],
                    repo_root=repo_root))
            elif name == "qualities":
                items.append(lambda entry=entry: mint_quality(
                    entry["slug"], label=entry["label"], summary=entry["summary"],
                    repo_root=repo_root))
            else:
                items.append(entry_draft(entry, plan=plan, ctx_run_id=ctx_run_id,
                                         prompt_version=(prompt_versions or {}).get(
                                             name, prompt_version),
                                         agent=_AGENT_BY_LIST[name]))
    return items


def _minted_keys(plan: dict, *, mint_contradictions: bool = False) -> list[str | None]:
    """The keys `mint_items` produced items for, in the same order — so a result list can be
    zipped back onto the plan without re-deriving the filter. An item that is not a plan
    entry at all (D45's ledger) is a `None`, so the two lists stay the same length."""
    keys: list[str | None] = [None] if mint_contradictions else []
    for name in ENTRY_LISTS:
        list_entries = plan.get(name) or []
        if name == "nodes":
            list_entries = sorted(list_entries, key=lambda entry: entry["kind"] != "concept")
        for entry in list_entries:
            try:
                ready = _mintable(name, entry)
            except (UndebatedCarve, NotAdmissible):
                raise
            if ready:
                keys.append(entry["key"])
    return keys


def mint_plan(plan: dict, *, repo_root: Path, cycle, chat_run_id: str, prompt_version: str,
              prompt_versions: dict[str, str] | None = None,
              status_checker=None, lander=land_drafts) -> tuple[dict, list]:
    """Land every mintable entry, one commit per record (D36), and mark what landed.

    An entry whose land did not succeed keeps its previous status: a plan that claimed
    `minted` for a record git does not hold would make 3F's dossier count fiction.

    D45's ledger joins the batch whenever it differs from what git holds, which is the only
    moment a debate's contradiction can reach a commit: nothing else lands it, and while it
    sits unlanded it blocks every other record's rebase.

    @returns: `(updated plan, the lander's (MintedRecord, LandResult) pairs)`."""
    from langatlas_commit.land import Landed

    pending = contradictions_pending(repo_root)
    items = mint_items(plan, repo_root=repo_root, ctx_run_id=chat_run_id,
                       prompt_version=prompt_version, prompt_versions=prompt_versions,
                       mint_contradictions=pending)
    keys = _minted_keys(plan, mint_contradictions=pending)
    results = lander(items, repo_root=repo_root, chat_run_id=chat_run_id, cycle=cycle,
                     status_checker=status_checker)

    updated = plan
    for key, (_minted, outcome) in zip(keys, results):
        if key is not None and isinstance(outcome, Landed):
            updated = set_entry(updated, key, status="minted")
    return updated, results
