"""R3's exit: the inventory 3C atomizes is committed, and the cycle says so.

Every blocker is reported at once rather than one per invocation, because each one is a
developer decision (re-sign, scout, apply or reject an amendment) and a one-at-a-time error is
a slow way to find out there were four. Evidence is re-resolved at finalize time: a source
re-ingested since the survey ran can have removed the very chunk a candidate cites."""
from dataclasses import replace
from pathlib import Path

from langatlas_commit.land import Landed, land_record

from langatlas_research.cycle import Cycle, advance, load_cycle, require_sign_off, save_cycle
from langatlas_research.errors import R3Incomplete
from langatlas_research.land import store_validator
from langatlas_research.schema import validate_research_record
from langatlas_research.survey.chunks import ChunkLookup
from langatlas_research.survey.inventory import load_survey, render_survey


def r3_blockers(cycle: Cycle, survey: dict, *, repo_root: Path | None,
                lookup: ChunkLookup) -> list[str]:
    blockers = [f"schema: {error}" for error in
                validate_research_record(survey, "survey", repo_root=repo_root)]
    if survey.get("theme_digest") != cycle.signed_off["theme_digest"]:
        blockers.append("the survey predates the current sign-off: re-run `survey run`")
    if not survey.get("candidates"):
        blockers.append("the inventory has no evidenced candidates")
    open_gaps = [gap["key"] for gap in survey.get("unevidenced", [])
                 if gap["disposition"] == "open"]
    if open_gaps:
        blockers.append(f"{len(open_gaps)} unevidenced candidate(s) not yet scouted or"
                        f" dropped: {', '.join(open_gaps)}")
    pending = [str(i) for i, item in enumerate(survey.get("theme_amendments", []))
               if item["status"] == "proposed"]
    if pending:
        blockers.append(f"{len(pending)} theme amendment(s) awaiting a developer decision"
                        f" (indexes {', '.join(pending)}): `themes amend`")
    for candidate in survey.get("candidates", []):
        for evidence in candidate["evidence"]:
            ref = lookup(evidence["chunk_id"])
            if ref is None or (ref.source_id, ref.locator) != (evidence["source_id"],
                                                               evidence["locator"]):
                blockers.append(f"{candidate['key']}: evidence chunk {evidence['chunk_id']}"
                                f" no longer resolves as recorded")
    return blockers


def finalize_r3(cycle_number: int, *, repo_root: Path, lookup: ChunkLookup,
                status_checker=None, lander=land_record) -> tuple[Cycle, list]:
    """@raises SignOffMissing / SignOffStale / R3Incomplete / FileNotFoundError"""
    cycle = load_cycle(cycle_number, repo_root=repo_root)
    require_sign_off(cycle, repo_root=repo_root)
    survey = load_survey(cycle.slug, repo_root=repo_root)
    blockers = r3_blockers(cycle, survey, repo_root=repo_root, lookup=lookup)
    if blockers:
        raise R3Incomplete(f"{cycle.slug} cannot close R3: " + "; ".join(blockers))

    run_id = survey["runs"]["surveyor"]
    survey_rel = f"research/surveys/{cycle.slug}.yaml"
    survey_result = lander(repo_root, survey_rel, render_survey(survey), chat_run_id=run_id,
                           validator=store_validator, status_checker=status_checker)
    if not isinstance(survey_result, Landed):
        return cycle, [survey_result]

    updated = cycle if cycle.status == "r3-done" else advance(cycle, "r3-done")
    updated = replace(updated, artifacts={**(cycle.artifacts or {}), "survey": survey_rel})
    cycle_file = save_cycle(updated, repo_root=repo_root)
    cycle_result = lander(repo_root, str(cycle_file.relative_to(repo_root)),
                          cycle_file.read_text(), chat_run_id=run_id,
                          validator=store_validator, status_checker=status_checker)
    if not isinstance(cycle_result, Landed):
        save_cycle(cycle, repo_root=repo_root)
        return cycle, [survey_result, cycle_result]
    return updated, [survey_result, cycle_result]
