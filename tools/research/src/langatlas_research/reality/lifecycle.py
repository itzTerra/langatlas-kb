"""R5's two ends: opening a cycle's reality check against a freshly compiled, committed
questionnaire, and closing it once every sampled language is answered and gated.

The questionnaire is committed *before* anyone answers it, so the file the findings name is a
file git already holds — never a recompile that might differ. Every blocker is reported at once,
like 3C's `r4_blockers`: each one is a developer decision. R5 lands exactly three kinds of file —
the spec, the reality check and the cycle record (plus the D45 ledger when the gate touched it)
— and never a FeatureInstance (D68)."""
from dataclasses import replace
from pathlib import Path

from langatlas_commit.land import Landed, land_record
from langatlas_pipeline.transcripts.writer import utc_now
from langatlas_questionnaire.compiler import CompileError, compile_spec
from langatlas_questionnaire.spec import load_spec, render_spec, spec_rel, validate_spec
from langatlas_research.cycle import Cycle, advance, load_cycle, require_sign_off, save_cycle
from langatlas_research.draft.contradictions import contradictions_mint, contradictions_pending
from langatlas_research.errors import R5Incomplete, R5NotReady
from langatlas_research.land import store_validator
from langatlas_research.reality.findings import refresh
from langatlas_research.reality.record import (
    add_shakedown, build_record, load_record, reality_path, reality_rel, render_record,
    save_record,
)
from langatlas_research.schema import validate_research_record
from langatlas_validate.store import iter_store_records


def theme_features(cycle: Cycle, repo_root) -> list[str]:
    """The feature ids this cycle minted. Concepts are never swept (§7.3), so they are not in
    R5's scope either."""
    minted = set(cycle.nodes_minted)
    return sorted(data["id"] for _p, kind, _t, data in iter_store_records(Path(repo_root))
                  if kind == "feature" and data["id"] in minted)


def open_r5(cycle_number: int, *, repo_root: Path, chat_run_id: str, restart: bool = False,
            now: str | None = None, status_checker=None,
            lander=land_record) -> tuple[dict | None, object]:
    """Compile, commit the spec, and open the reality check.

    @returns: `(record, the spec's LandResult)`; record is None when the spec did not land.
    @raises SignOffMissing / SignOffStale / R5NotReady"""
    repo_root = Path(repo_root)
    cycle = load_cycle(cycle_number, repo_root=repo_root)
    require_sign_off(cycle, repo_root=repo_root)
    if cycle.status != "r4-done":
        raise R5NotReady(f"cycle {cycle.slug} is at {cycle.status!r}; R5 starts once"
                         f" `draft finalize` has put it at r4-done")
    if reality_path(cycle.slug, repo_root).exists() and not restart:
        classified = sorted(load_record(cycle.slug, repo_root=repo_root)["runs"]["classify"])
        if classified:
            raise R5NotReady(f"{cycle.slug} already has classifier runs for {classified};"
                             f" pass --restart to discard them and compile afresh")
    features = theme_features(cycle, repo_root)
    if not features:
        raise R5NotReady(f"cycle {cycle.slug} minted no features, so there is nothing to"
                         f" reality-check")
    try:
        spec = compile_spec(repo_root)
    except CompileError as exc:
        raise R5NotReady(str(exc)) from exc
    spec_errors = validate_spec(spec)
    if spec_errors:
        raise R5NotReady(f"compiled spec fails schema validation: {'; '.join(spec_errors)}")

    rel = spec_rel(spec["ontology_version"])
    outcome = lander(repo_root, rel, render_spec(spec), chat_run_id=chat_run_id,
                     validator=store_validator, status_checker=status_checker)
    if not isinstance(outcome, Landed):
        return None, outcome
    record = build_record(cycle=cycle, spec_rel=rel, spec=spec, scope_features=features,
                          generated_at=now or utc_now())
    for diagnostic in spec["diagnostics"]:
        record = add_shakedown(record, component="compiler",
                               detail=f"{diagnostic['kind']}: {diagnostic['dimension']}")
    save_record(record, repo_root=repo_root)
    return record, outcome


def r5_blockers(cycle: Cycle, record: dict, *, repo_root: Path) -> list[str]:
    blockers = [f"schema: {error}" for error in
                validate_research_record(record, "reality-check", repo_root=repo_root)]
    if record["theme_digest"] != cycle.signed_off["theme_digest"]:
        blockers.append("the reality check predates the current sign-off: re-run"
                        " `reality compile --restart`")
    if not (Path(repo_root) / record["questionnaire"]).exists():
        blockers.append(f"{record['questionnaire']} is missing: re-run `reality compile`")
    for language in sorted(set(cycle.languages) - set(record["runs"]["classify"])):
        blockers.append(f"{language}: never classified — run `reality classify"
                        f" {cycle.number} --language {language}`")
    for cell in record["cells"]:
        if cell["status"] == "proposed":
            blockers.append(f"{cell['key']}: never reached the gate — run `reality verify`")
    return blockers


def finalize_r5(cycle_number: int, *, repo_root: Path, status_checker=None,
                lander=land_record) -> tuple[Cycle, list]:
    """@raises SignOffMissing / SignOffStale / RealityCheckMissing / R5Incomplete"""
    repo_root = Path(repo_root)
    cycle = load_cycle(cycle_number, repo_root=repo_root)
    require_sign_off(cycle, repo_root=repo_root)
    record = load_record(cycle.slug, repo_root=repo_root)
    blockers = r5_blockers(cycle, record, repo_root=repo_root)
    if blockers:
        raise R5Incomplete(f"{cycle.slug} cannot close R5: " + "; ".join(blockers))

    record = refresh(record, load_spec(repo_root / record["questionnaire"]))
    save_record(record, repo_root=repo_root)
    runs = record["runs"]
    run_id = runs["verify"] or runs["classify"][sorted(runs["classify"])[0]]["run_id"]

    def land(rel: str, text: str):
        return lander(repo_root, rel, text, chat_run_id=run_id, validator=store_validator,
                      status_checker=status_checker)

    results = []
    if contradictions_pending(repo_root):
        # A tracked file the gate rewrote: until it lands, every later rebase refuses.
        ledger = contradictions_mint(repo_root)
        results.append(land(ledger.path, ledger.text))
        if not isinstance(results[-1], Landed):
            return cycle, results
    rel = reality_rel(cycle.slug)
    results.append(land(rel, render_record(record)))
    if not isinstance(results[-1], Landed):
        return cycle, results

    updated = cycle if cycle.status == "r5-done" else advance(cycle, "r5-done")
    updated = replace(updated, artifacts={**(cycle.artifacts or {}), "reality_check": rel})
    cycle_file = save_cycle(updated, repo_root=repo_root)
    results.append(land(str(cycle_file.relative_to(repo_root)), cycle_file.read_text()))
    if not isinstance(results[-1], Landed):
        save_cycle(cycle, repo_root=repo_root)
        return cycle, results
    return updated, results
