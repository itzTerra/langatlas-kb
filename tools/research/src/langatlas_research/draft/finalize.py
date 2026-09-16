"""R4's exit: the carve plan is committed, and the cycle says so.

Every blocker is reported at once rather than one per invocation, because each one is a
developer decision — debate it, waive it, fix the claim, re-run the mint — and a one-at-a-time
error is a slow way to find out there were six.

What "done" means here is deliberately narrow: every entry is minted, dropped, or explicitly
accounted for. A plan that still carries a verified-but-unlanded entry is not done, because the
store and the plan would then disagree about what R4 produced, and 3F's dossier reads both."""
from dataclasses import replace
from pathlib import Path

from langatlas_commit.land import Landed, land_record

from langatlas_research.cycle import Cycle, advance, load_cycle, require_sign_off, save_cycle
from langatlas_research.draft.contested import open_carves
from langatlas_research.draft.plan import entries, load_plan, render_plan
from langatlas_research.errors import R4Incomplete
from langatlas_research.land import store_validator
from langatlas_research.schema import validate_research_record

_TERMINAL = ("minted", "dropped")


def r4_blockers(cycle: Cycle, plan: dict, *, repo_root: Path | None) -> list[str]:
    blockers = [f"schema: {error}" for error in
                validate_research_record(plan, "draft", repo_root=repo_root)]
    if plan.get("theme_digest") != cycle.signed_off["theme_digest"]:
        blockers.append("the carve plan predates the current sign-off: re-run"
                        " `draft atomize`")
    if not any(True for _name, _entry in entries(plan)):
        blockers.append("the carve plan has no entries at all")

    for key in open_carves(plan):
        blockers.append(f"{key}: contested with no debate and no waiver — run"
                        f" `draft debate` or `draft waive`")

    for name, entry in entries(plan):
        if entry["status"] in _TERMINAL:
            continue
        verification = entry.get("verification")
        if name in ("nodes", "edges", "quality_edges"):
            if verification is None:
                blockers.append(f"{entry['key']}: never reached the verifier — run"
                                f" `draft verify`")
                continue
            if not verification["admissible"]:
                blockers.append(f"{entry['key']}: the gate refused it"
                                f" ({verification['verdict']}) — fix the claim or its"
                                f" citations, or drop the carve")
                continue
        blockers.append(f"{entry['key']}: {entry['status']}, not landed — run `draft mint`")
    return blockers


def _debate_artifacts(plan: dict) -> list[str]:
    ids = sorted({entry["debate_id"] for _name, entry in entries(plan)
                  if entry.get("debate_id")})
    return [f"research/debates/{debate_id}.yaml" for debate_id in ids]


def finalize_r4(cycle_number: int, *, repo_root: Path, status_checker=None,
                lander=land_record) -> tuple[Cycle, list]:
    """@raises SignOffMissing / SignOffStale / R4Incomplete / DraftMissing"""
    cycle = load_cycle(cycle_number, repo_root=repo_root)
    require_sign_off(cycle, repo_root=repo_root)
    plan = load_plan(cycle.slug, repo_root=repo_root)
    blockers = r4_blockers(cycle, plan, repo_root=repo_root)
    if blockers:
        raise R4Incomplete(f"{cycle.slug} cannot close R4: " + "; ".join(blockers))

    run_id = plan["runs"]["ontologist"]
    plan_rel = f"research/drafts/{cycle.slug}.yaml"
    plan_result = lander(repo_root, plan_rel, render_plan(plan), chat_run_id=run_id,
                         validator=store_validator, status_checker=status_checker)
    if not isinstance(plan_result, Landed):
        return cycle, [plan_result]

    updated = cycle if cycle.status == "r4-done" else advance(cycle, "r4-done")
    artifacts = {**(cycle.artifacts or {}), "draft": plan_rel}
    debates = _debate_artifacts(plan)
    if debates:
        artifacts["debates"] = debates
    updated = replace(updated, artifacts=artifacts)
    cycle_file = save_cycle(updated, repo_root=repo_root)
    cycle_result = lander(repo_root, str(cycle_file.relative_to(repo_root)),
                          cycle_file.read_text(), chat_run_id=run_id,
                          validator=store_validator, status_checker=status_checker)
    if not isinstance(cycle_result, Landed):
        save_cycle(cycle, repo_root=repo_root)
        return cycle, [plan_result, cycle_result]
    return updated, [plan_result, cycle_result]
