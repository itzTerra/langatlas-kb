"""One record in, at most one commit out.

Why the record rather than the fact is the unit of work: §6.4 scores facts, but D36 commits
record files. Assessing a record's facts together means a record's block is never half-updated,
and a budget stop (D43) pauses at a record boundary where the next run can resume cleanly.

Why `Deps`: every collaborator here is either expensive (the university API, Claude, git) or
run-wide (source tiers, the contradiction ledger, debates). Passing them in makes the loop
testable with no provider and no database, and makes the nightly job build them exactly once."""
import re
from dataclasses import dataclass, field
from pathlib import Path

from langatlas_research.controversy.assemble import assemble_inputs
from langatlas_research.controversy.assessor import needs_escalation
from langatlas_research.controversy.block import controversy_mint, merge_block, unchanged
from langatlas_research.controversy.inputs import inputs_digest

_CHARACTERISTIC = re.compile(r"^characteristic\([^,]+,\s*(c-[a-z0-9-]+)")
_SYNTAX = re.compile(r"^syntax-valid\([^,]+\.sx\.([a-z0-9-]+)")
_QUALITY = re.compile(r"^quality-assessment\([^,]+,\s*([a-z0-9-]+)")


@dataclass(frozen=True)
class Deps:
    """Everything `assess_record` needs that it must not construct itself."""

    assess: object                 # (ctx, fact_id, inputs, *, alias, prompt) -> Assessment
    escalate: object | None        # (Assessment, ControversyInputs) -> Assessment
    ledger: object                 # AssessmentLedger
    land: object                   # (MintedRecord) -> bool  (True when it landed)
    alias: str
    today: str
    source_facts: dict
    contradictions: list
    debates: dict
    verdict_ledger: object
    spread_min_assessments: int = 2


@dataclass(frozen=True)
class RecordOutcome:
    record_path: str
    assessed: int = 0
    skipped: int = 0
    escalated: int = 0
    changed: bool = False
    levels: dict = field(default_factory=dict)


def anchor_key(claim: str) -> str:
    """§3.2's anchor suffix for a derived fact, recovered from its canonical claim.

    The block is keyed by anchor rather than by fact id because the anchor survives a claim
    correction (which mints a new fact id) — so a re-assessment replaces the entry it should
    replace instead of accumulating one per historical claim."""
    kind = claim.split("(", 1)[0]
    if kind == "node-definition":
        return "summary"
    if kind in ("instance-exists", "edge-exists", "rule-exists"):
        return "exists"
    if kind == "edge-polarity":
        return "polarity"
    if (match := _CHARACTERISTIC.match(claim)):
        return f"characteristics[{match.group(1)}]"
    if (match := _SYNTAX.match(claim)):
        return f"syntax[{match.group(1)}]"
    if (match := _QUALITY.match(claim)):
        return f"assessments[{match.group(1)}]"
    return kind


def store_record_paths(repo_root: Path) -> list[str]:
    """Every canonical record file, repo-relative and in a stable order — the nightly job's
    work-item list.

    Relative, because that is what `land_record` commits and what a checkpoint row has to
    survive a repo being cloned somewhere else. `iter_store_records` yields absolute paths."""
    from langatlas_validate.store import iter_store_records

    return sorted(str(path.relative_to(repo_root))
                  for path, _kind, _text, _data in iter_store_records(repo_root))


def _load(repo_root: Path, record_path: str):
    """@raises FileNotFoundError: the path is not (or is no longer) a canonical store record —
        which the nightly job reads as finished work, not as an error to retry."""
    from langatlas_validate.store import iter_store_records

    for path, kind, text, data in iter_store_records(repo_root):
        if str(path.relative_to(repo_root)) == record_path:
            return kind, text, data
    raise FileNotFoundError(f"{record_path} is not a canonical store record")


def assess_record(ctx, record_path: str, *, repo_root: Path, deps: Deps) -> RecordOutcome:
    """Assess every fact this record derives, then land the record if its block changed.

    @raises BudgetExceeded: straight through from the assessor — the caller (the job) turns it
        into a `blocked` item, and this record is simply re-attempted on resume. Nothing is
        landed on the way out, so a half-assessed record never reaches git.
    @returns counts plus fact_id -> final level."""
    from langatlas_research.controversy.assemble import record_facts

    kind, text, data = _load(repo_root, record_path)
    facts = record_facts(Path(record_path), kind, text, data)

    assessments, levels = {}, {}
    # Buffered rather than written straight to the ledger: a row must not outlive the git
    # commit it describes. `land` can come back falsy (red main, a validator error, push
    # contention, a rebase conflict — `default_land` collapses all of those to `False`), and a
    # later fact in this same loop can raise `BudgetExceeded` before the record ever reaches
    # `deps.land`. Either way, nothing here may reach the ledger — a written-but-unlanded row
    # would look like "already assessed" forever and the assessment would be lost from the
    # canonical record while still reading as done.
    pending_ledger_rows = []
    assessed = skipped = escalated = 0
    for fact in facts:
        inputs = assemble_inputs(fact, record=data, ledger=deps.verdict_ledger,
                                 source_facts=deps.source_facts,
                                 contradictions=deps.contradictions, debates=deps.debates,
                                 spread_min_assessments=deps.spread_min_assessments)
        digest = inputs_digest(inputs)
        previous = deps.ledger.previous(fact["fact_id"])
        if previous is not None and previous[0] == digest:
            # §6.4: unchanged inputs => unchanged level, so a re-run is free. The record's
            # existing block already says what this fact's level is; nothing to do.
            skipped += 1
            levels[fact["fact_id"]] = previous[1]
            continue

        assessment = deps.assess(ctx, fact["fact_id"], inputs, alias=deps.alias)
        assessed += 1
        if deps.escalate is not None and needs_escalation(assessment):
            assessment = deps.escalate(assessment, inputs)
            escalated += 1
        assessments[anchor_key(fact["claim"])] = assessment
        levels[fact["fact_id"]] = assessment.level
        pending_ledger_rows.append((assessment, digest))

    def _flush():
        for assessment, digest in pending_ledger_rows:
            deps.ledger.record(assessment, digest=digest)

    if not assessments:
        return RecordOutcome(record_path=record_path, assessed=assessed, skipped=skipped,
                             escalated=escalated, levels=levels)

    merged = merge_block(data, assessments, date=deps.today)
    minted = controversy_mint(record_path, merged, kind=kind, base_text=text)
    if unchanged(minted, text):
        # Nothing changed, but the record was already correctly landed — a legitimate no-op,
        # so the buffered rows are as good as landed and may flush.
        _flush()
        return RecordOutcome(record_path=record_path, assessed=assessed, skipped=skipped,
                             escalated=escalated, levels=levels)
    changed = bool(deps.land(minted))
    if changed:
        _flush()
    return RecordOutcome(record_path=record_path, assessed=assessed, skipped=skipped,
                         escalated=escalated, changed=changed, levels=levels)


def default_land(repo_root: Path, chat_run_id: str):
    """The production lander: 3A's `land_drafts`, one commit per record file (D36)."""
    from langatlas_commit.land import Landed
    from langatlas_research.land import land_drafts

    def _land(minted) -> bool:
        (_rendered, outcome), = land_drafts([lambda: minted], repo_root=repo_root,
                                            chat_run_id=chat_run_id)
        return isinstance(outcome, Landed)

    return _land
