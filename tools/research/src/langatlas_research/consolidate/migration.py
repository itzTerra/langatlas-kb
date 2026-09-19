"""The settled-theme ceremony's working half (§7.4, §5.2, D38).

Drafting seeds a manifest from D16's casebook — one explicit `fact_remap` entry per affected
anchor — so the developer edits a filled form, never a blank one. `run_migration` then plans it
with the shared interpreter, validates the migrated store in a scratch copy, re-runs the D24
gate on every edge and rule it rewrites (a remapped edge is a new claim, and D4 admits no claim
without the gate), and lands manifest plus diff as one commit. Nothing lands unless all four
pass."""
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_commit.land import Landed, land_changeset
from langatlas_ingest.verify.pipeline import verify_pair
from langatlas_research.consolidate.record import add_migration, load_record, save_record
from langatlas_research.cycle import Cycle, require_sign_off, settled_record_ids
from langatlas_research.draft.gate import verify_entry
from langatlas_research.errors import MigrationRecordNotUpdated, MigrationRefused, ResearchError
from langatlas_research.land import store_validator
from langatlas_research.mint import MintedRecord
from langatlas_validate.compile import anchor_record_id
from langatlas_validate.migrate import (
    MIGRATIONS_REL, MigrationError, affected_facts, check_plan, disposition_nodes,
    load_manifest, manifest_rel, plan_migration, render_manifest,
)

# D38's default disposition per casebook row, for every fact a record-level op affects.
CASEBOOK = {"split": "requeue", "merge": "remap", "move": "untouched", "remove": "tombstone"}
_SLUG_MAX = 40

_safe = YAML(typ="safe")


def default_slug(disposition: dict) -> str:
    slug = "-".join([disposition["op"], *disposition_nodes(disposition)])
    return slug[:_SLUG_MAX].rstrip("-")


def next_migration_id(repo_root: Path, slug: str) -> str:
    directory = Path(repo_root) / MIGRATIONS_REL
    numbers = [int(path.name[:4]) for path in directory.glob("[0-9][0-9][0-9][0-9]-*")
               if path.is_dir()] if directory.exists() else []
    return f"{max(numbers, default=0) + 1:04d}-{slug}"


def _merged(disposition: dict) -> set[str]:
    sources = disposition["from"]
    return {*([sources] if isinstance(sources, str) else sources), disposition["to"]}


def _default_entry(disposition: dict, fact: dict) -> dict:
    op, anchor = disposition["op"], fact["anchor"]
    match = {"match": {"anchor": anchor}}
    if anchor.endswith("#summary"):
        if op == "split" and disposition.get("old_node", "demote-to-concept") == \
                "demote-to-concept":
            return {**match, "action": "untouched"}
        if op == "merge":
            return {**match, "action": "remap", "target": disposition["to"],
                    "reverify": "fast-path"}
        return {**match, "action": "tombstone", "reason": "node-removed"}
    if op == "merge":
        record_id = anchor_record_id(anchor)
        if record_id.startswith("edge."):
            parts = record_id.split(".")
            if len(parts) == 4 and {parts[2], parts[3]} <= {*_merged(disposition)}:
                return {**match, "action": "tombstone", "reason": "self-loop-after-merge"}
        return {**match, "action": "remap", "target": disposition["to"], "reverify": "fast-path"}
    if op == "split":
        return {**match, "action": "requeue", "reason": "ambiguous-subject"}
    return {**match, "action": CASEBOOK[op], "reason": "node-removed"}


def _settled_themes(repo_root: Path, record_ids) -> list[str]:
    settled = settled_record_ids(repo_root)
    return sorted({settled[record_id] for record_id in record_ids if record_id in settled})


def draft_manifest(repo_root: Path, disposition: dict, *, cycle: Cycle, date: str,
                   rationale: str, slug: str) -> dict:
    """@param disposition: one op without its `fact_remap` — drafting fills it.
    @raises MigrationRefused: the op names a node the store does not have, or touches a
        FeatureInstance.
    @raises SignOffMissing / SignOffStale"""
    require_sign_off(cycle, repo_root=repo_root)
    try:
        facts = affected_facts(repo_root, disposition)
    except MigrationError as exc:
        raise MigrationRefused(str(exc)) from exc
    if disposition["op"] == "move":
        # v0: a move touches no facts (no classification-asserting claim kind), and the
        # interpreter refuses a non-empty fact_remap.
        facts = []
    disposition = {key: value for key, value in disposition.items() if value is not None}
    filled = {**disposition, "fact_remap": [_default_entry(disposition, fact) for fact in facts]}
    touched = {*disposition_nodes(disposition), *(anchor_record_id(f["anchor"]) for f in facts)}
    return {"migration_id": next_migration_id(repo_root, slug), "date": date,
            "cycle": cycle.number, "settled_themes": _settled_themes(repo_root, touched),
            "ontology_version_before": (Path(repo_root) / "ontology" / "VERSION").read_text()
            .strip(),
            "rationale": rationale, "dispositions": [filled]}


def write_draft(repo_root: Path, manifest: dict) -> Path:
    path = Path(repo_root) / manifest_rel(manifest["migration_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_manifest(manifest))
    return path


def gate_plan(ctx, conn, plan, *, repo_root: Path, config, deps=None, queue=None,
              verifier=verify_pair) -> list:
    """3C's `verify_entry` over every record the plan rewrites — the same gate, the same fold,
    no second admissibility path."""
    results = []
    for rel in plan.gated:
        text = plan.changes[rel]
        data = _safe.load(text)
        kind = ("rule" if rel.startswith("rules/") else
                "affects-quality-edge" if data.get("type") == "affects-quality" else "edge")
        minted = MintedRecord(path=rel, text=text, kind=kind, node_ids=(data["id"],))
        results.append(verify_entry(ctx, conn, minted, key=data["id"], kind=kind,
                                    repo_root=repo_root, config=config, deps=deps, queue=queue,
                                    verifier=verifier))
    return results


def run_migration(ctx, conn, cycle: Cycle, migration_id: str, *, repo_root: Path, config,
                  deps=None, queue=None, verifier=verify_pair, lander=land_changeset,
                  status_checker=None):
    """@returns `(MigrationPlan, gate results, land outcome)`.
    @raises SignOffMissing / SignOffStale / MigrationRefused"""
    require_sign_off(cycle, repo_root=repo_root)
    root = Path(repo_root)
    load_record(cycle.slug, repo_root=root)   # fail typed BEFORE landing, not after
    rel = manifest_rel(migration_id)
    if not (root / rel).exists():
        raise MigrationRefused(f"no drafted manifest at {rel} — run `langatlas-research"
                               f" consolidate draft-migration` first")
    try:
        manifest = load_manifest(root / rel)
        plan = plan_migration(root, manifest)
    except MigrationError as exc:
        raise MigrationRefused(f"{migration_id}: {exc}") from exc
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        raise MigrationRefused(f"{migration_id}: malformed manifest {rel}: {exc!r}") from exc
    # Stamped against the store it lands on, not the one it was drafted against.
    manifest = {**manifest, "settled_themes": _settled_themes(root, plan.touched),
                "ontology_version_before": (root / "ontology" / "VERSION").read_text().strip()}
    manifest_text = render_manifest(manifest)
    errors = check_plan(root, plan, extra={rel: manifest_text})
    if errors:
        raise MigrationRefused(f"{migration_id}: the migrated store would not validate: "
                               + "; ".join(errors))
    results = gate_plan(ctx, conn, plan, repo_root=root, config=config, deps=deps, queue=queue,
                        verifier=verifier)
    refused = [result for result in results if not result.admissible]
    if refused:
        raise MigrationRefused(
            f"{migration_id}: the D24 gate refused "
            + "; ".join(f"{r.key} ({r.verdict}{': ' + r.detail if r.detail else ''})"
                        for r in refused)
            + " — requeue or tombstone those records instead of remapping them")
    outcome = lander(root, {**plan.changes, rel: manifest_text},
                     message=f"migrate {migration_id}", chat_run_id=ctx.run_id,
                     validator=store_validator, status_checker=status_checker)
    if isinstance(outcome, Landed):
        try:
            record = load_record(cycle.slug, repo_root=root)
            save_record(add_migration(record, migration_id), repo_root=root)
        except (ResearchError, OSError) as exc:
            raise MigrationRecordNotUpdated(
                f"landed {migration_id} (commit {outcome.commit_sha}), but the consolidation "
                f"record was not updated: {exc}. The migration itself is done — do not re-run "
                f"it; add {migration_id} to `migrations` in "
                f"research/consolidations/{cycle.slug}.yaml by hand") from exc
    return plan, results, outcome
