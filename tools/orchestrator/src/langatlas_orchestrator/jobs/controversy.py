"""D21/D25's nightly controversy batch (§6.4/§7.11), driven through the generic loop.

One work item per canonical record: that is the commit grain (D36), so it is the grain at which
an interrupted batch can resume without risking a half-written block. Event-driven in the sense
§6.4 means it — the run walks the whole store, but a fact whose structured inputs have not
changed costs nothing, so a quiet night is a cheap night.

Unlike R3's tagging job this one *is* cron-driven: nothing here is gated on a cycle sign-off,
because the assessor reads what is already committed and proposes no content."""
from pathlib import Path

import psycopg

from langatlas_ingest.verify.ledger import VerdictLedger
from langatlas_pipeline.errors import CircuitOpen, ProviderTransportError, StructuredOutputError
from langatlas_research.config import ResearchConfig
from langatlas_research.controversy.assemble import load_deps
from langatlas_research.controversy.assessor import assess_inputs
from langatlas_research.controversy.ledger import AssessmentLedger
from langatlas_research.controversy.run import Deps, assess_record, default_land, store_record_paths
from langatlas_research.errors import AssessorOutputInvalid
from langatlas_research.paths import research_config_path

from langatlas_orchestrator.registry import ItemOutcome, register_job_kind

KIND = "nightly-controversy"


def _enumerate(extra: dict, repo_root: Path) -> list[str]:
    """@param extra: `records: [...]` narrows a manual run to specific files; omit it for the
        whole store."""
    return sorted(extra.get("records") or store_record_paths(repo_root))


def _config(repo_root: Path):
    return ResearchConfig.load(research_config_path(repo_root)).controversy


def _assess(ctx, record_path: str, repo_root: Path, extra: dict):
    """The one provider-, database- and git-touching call, isolated so tests can replace it."""
    from datetime import date

    config = _config(repo_root)
    with VerdictLedger() as verdicts, AssessmentLedger() as ledger:
        shared = load_deps(repo_root, verdicts)
        deps = Deps(assess=assess_inputs, escalate=_escalator(repo_root, config),
                    ledger=ledger, land=default_land(repo_root, getattr(ctx, "run_id", "")),
                    alias=extra.get("alias") or config.alias, today=date.today().isoformat(),
                    source_facts=shared.source_facts, contradictions=shared.contradictions,
                    debates=shared.debates, verdict_ledger=verdicts,
                    spread_min_assessments=config.spread_min_assessments)
        return assess_record(ctx, record_path, repo_root=repo_root, deps=deps)


def _escalator(repo_root: Path, config):
    from datetime import date

    from langatlas_pipeline.providers.core import RunContext
    from langatlas_research.controversy.escalate import capture_candidate, escalate

    def _escalate(assessment, inputs):
        with RunContext.start(kind="controversy-escalation", slug=assessment.fact_id) as ctx:
            final = escalate(ctx, assessment, inputs, role_config=config.escalation)
        capture_candidate(assessment, final, inputs, repo_root=repo_root,
                          today=date.today().isoformat())
        return final

    return _escalate


def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
    try:
        outcome = _assess(ctx, item_key, repo_root, extra)
    except FileNotFoundError as exc:
        # The store moved under the enumerator (a tombstone, a migration). Finished work, not
        # a failure: re-attempting it forever would wedge the batch on a file that is gone.
        return ItemOutcome(status="done", detail=f"no longer in the store: {exc}")
    except psycopg.OperationalError as exc:
        return ItemOutcome(status="blocked", detail=f"database unavailable: {exc}")
    except (ProviderTransportError, CircuitOpen) as exc:
        return ItemOutcome(status="blocked", detail=f"provider unavailable: {exc}")
    except (AssessorOutputInvalid, StructuredOutputError) as exc:
        # Deterministic at temperature 0 and cached: a retry returns the same answer. The
        # record keeps whatever level it already had, and the run's log says which one failed.
        return ItemOutcome(status="done", detail=f"unusable assessor response: {exc}")
    return ItemOutcome(status="done", record_key=item_key,
                       detail=f"assessed {outcome.assessed}, unchanged {outcome.skipped},"
                              f" escalated {outcome.escalated},"
                              f" {'landed' if outcome.changed else 'no change'}")


register_job_kind(KIND, _enumerate, _run_item)
