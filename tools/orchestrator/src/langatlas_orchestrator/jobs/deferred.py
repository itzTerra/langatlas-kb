"""D43's periodic-job inventory (context/spec.md §14, decisions.md D43's 2026-07-20
follow-up) names ten jobs total; six are real by this stage (`r0-exit-test`,
`monthly-capability-probe`, `nightly-verification`, `monthly-link-checker`) or don't
need driver wiring. The four below all depend on data or infrastructure a *later*
stage produces — ingested finding-aid/spec sources (Stage 2), real verified facts
(Stage 5), or the public site's self-hosted Umami install (Stage 6).
Registering them now with a loud, specific `NotImplementedError` (rather than leaving
`config/jobs/*.yaml` reference an unregistered `kind`, or silently no-op-ing) keeps
`config/jobs/crontab.example` honest today: a cron invocation against one of these
fails immediately and says exactly which stage will replace this stub, instead of
either crashing on an import error or quietly doing nothing."""
from pathlib import Path

from langatlas_orchestrator.registry import ItemOutcome, register_job_kind


def _deferred(kind: str, stage: str, needs: str):
    def _enumerate(extra: dict, repo_root: Path) -> list[str]:
        raise NotImplementedError(
            f"{kind} is deferred to {stage}: needs {needs} (context/spec.md §14)")

    def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
        raise NotImplementedError(f"{kind} is deferred to {stage}: needs {needs}")

    register_job_kind(kind, _enumerate, _run_item)


_deferred("monthly-finding-aid-mirror-refresh", "Stage 2",
         "ingested finding-aid sources to mirror")
_deferred("monthly-demand-export", "Stage 6",
         "the self-hosted Umami instance (D33/D52)")
_deferred("quarterly-edition-check", "Stage 2",
         "ingested spec sources with edition metadata")
_deferred("backstop-sweep-18mo", "Stage 5",
         "real facts old enough to need 18-month re-verification")
