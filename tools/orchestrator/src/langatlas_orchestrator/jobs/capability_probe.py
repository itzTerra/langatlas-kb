"""D43's 'monthly capability probe' periodic job (context/spec.md §14), reusing 1B's
already-shipped `probe_all`/`apply_probe` unchanged — this module only gives the
existing capability probe an enumerator/item-runner shape the driver can schedule
through `config/jobs/monthly-capability-probe.yaml` + cron, instead of it only being
reachable via its own standalone `langatlas-probe` CLI."""
from pathlib import Path

from langatlas_pipeline.observability.probe import apply_probe, probe_all
from langatlas_pipeline.paths import CONFIG_DIR

from langatlas_orchestrator.registry import ItemOutcome, register_job_kind

_ITEM_KEY = "probe-all-aliases"


def _enumerate(extra: dict, repo_root: Path) -> list[str]:
    return [_ITEM_KEY]


def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
    probed = probe_all(ctx)
    apply_probe(CONFIG_DIR / "provider_capabilities.yaml", probed)
    plural = "" if len(probed) == 1 else "s"
    return ItemOutcome(status="done", detail=f"probed {len(probed)} alias{plural}")


register_job_kind("monthly-capability-probe", _enumerate, _run_item)
