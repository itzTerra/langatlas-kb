"""R5's run of the D24 gate: 3C's `verify_entry`, pointed at rendered FeatureInstance records.

There is no second claim-assembly path. A cell is rendered exactly as a sweep would commit it,
`derive_facts` turns it into facts — `#exists` carrying `since` (D65), and an absence carrying
its feature's names — and 3C's gate verifies every cited fact. `#exists` decides the cell; every
other anchor's result is recorded. Nothing is minted (D68).

A verdict about the *pipeline* rather than the claim — a source the corpus never ingested, a
machine-produced locator that no longer resolves — goes to the shakedown log, which is R5's
other job."""
from pathlib import Path

from langatlas_ingest.verify.pipeline import verify_pair
from langatlas_research.cycle import Cycle, require_sign_off
from langatlas_research.draft.gate import verify_entry
from langatlas_research.errors import InvalidDraft, UnsourcedNode
from langatlas_research.mint import render_draft
from langatlas_research.reality.cells import cell_draft
from langatlas_research.reality.record import add_shakedown, set_cell
from langatlas_validate.ids import compose_instance_id
from langatlas_validate.store import iter_store_records

# Pair verdicts about the pipeline, and the shakedown component that owns each. R5's locators
# are copied from `source_chunks`, so one that no longer resolves is a pipeline defect.
_PIPELINE_VERDICTS = {"source-unavailable": "sources", "locator-not-found": "verifier"}


def feature_records(repo_root) -> dict[str, tuple]:
    return {data["id"]: (path, kind, text, data)
            for path, kind, text, data in iter_store_records(Path(repo_root))
            if kind == "feature"}


def _unverified(detail: str, run_id: str | None) -> dict:
    return {"exists": {"fact_id": "", "verdict": "unrendered", "admissible": False},
            "facts": [], "pairs": 0, "detail": detail, "run_id": run_id}


def verify_cells(ctx, conn, record: dict, *, cycle: Cycle, repo_root, config, deps=None,
                 queue=None, verifier=verify_pair, features=None) -> tuple[dict, list]:
    """Gate every `proposed` cell; every other cell is left alone.

    @param features: `{feature id: store record tuple}`; None reads the store.
    @returns: `(updated record, one GateResult per cell that reached the verifier)`.
    @raises SignOffMissing / SignOffStale: before any verifier call."""
    require_sign_off(cycle, repo_root=repo_root)
    features = feature_records(repo_root) if features is None else features
    run_id = getattr(ctx, "run_id", None)
    updated = {**record, "runs": {**record["runs"], "verify": run_id}}
    results = []
    for cell in record["cells"]:
        if cell["status"] != "proposed":
            continue
        key = cell["key"]
        if cell["feature"] not in features:
            detail = f"{cell['feature']!r} is no longer a feature in the store"
            updated = set_cell(updated, key, status="refused",
                               verification=_unverified(detail, run_id))
            updated = add_shakedown(updated, component="questionnaire", detail=f"{key}: {detail}")
            continue
        try:
            minted = render_draft(cell_draft(cell, record=record))
        except (InvalidDraft, UnsourcedNode) as exc:
            updated = set_cell(updated, key, status="refused",
                               verification=_unverified(str(exc), run_id))
            updated = add_shakedown(updated, component="questionnaire", detail=f"{key}: {exc}")
            continue

        result = verify_entry(ctx, conn, minted, key=key, kind="feature-instance",
                              repo_root=repo_root, config=config, deps=deps, queue=queue,
                              verifier=verifier, context_records=(features[cell["feature"]],))
        results.append(result)
        for fact in result.per_fact:
            for verdict in fact["verdicts"]:
                if verdict in _PIPELINE_VERDICTS:
                    updated = add_shakedown(updated, component=_PIPELINE_VERDICTS[verdict],
                                            detail=f"{fact['anchor']}: {verdict}")

        instance_id = compose_instance_id(cell["language"], cell["feature"])
        exists = next((f for f in result.per_fact if f["anchor"] == f"{instance_id}#exists"),
                      None)
        if exists is None:
            updated = set_cell(updated, key, status="refused", verification=_unverified(
                result.detail or "no #exists fact reached the verifier", run_id))
            continue
        block = {"exists": {"fact_id": exists["fact_id"], "verdict": exists["verification"],
                            "admissible": exists["admissible"]},
                 "facts": [{"anchor": f["anchor"], "admissible": f["admissible"],
                            "verification": f["verification"]} for f in result.per_fact],
                 "pairs": result.pairs, "detail": result.detail, "run_id": run_id}
        updated = set_cell(updated, key, verification=block,
                           status="admitted" if exists["admissible"] else "refused")
    return updated, results
