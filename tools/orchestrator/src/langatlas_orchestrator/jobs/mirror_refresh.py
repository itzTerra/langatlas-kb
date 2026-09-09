"""D53's monthly finding-aid mirror refresh (ratified cadence: monthly, not per-theme).

One work item per mirrored source, so a Hyperpolyglot refusal never costs the PLDB refresh
and a resumed run redoes only the half that failed. This is the only job in the project
that fetches from small community-run sites, which is why it is the only one that treats a
robots/TDM refusal as a halt: everything else in the orchestrator retries."""
from pathlib import Path

from langatlas_finding_aids.config import MIRRORED_SOURCES
from langatlas_finding_aids.mirror import MirrorRefusedByRobots, refresh

from langatlas_orchestrator.registry import ItemOutcome, register_job_kind


def _enumerate(extra: dict, repo_root: Path) -> list[str]:
    wanted = set(extra.get("sources") or ())
    return [source for source in sorted(MIRRORED_SOURCES)
            if not wanted or source in wanted]


def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
    try:
        state = refresh(item_key, ctx)
    except MirrorRefusedByRobots as exc:
        # Not transient and not ours to retry: a publisher said no. A human decides
        # whether to drop the page from the configured list or the source entirely.
        return ItemOutcome(status="halted", detail=f"refused: {exc}")
    except Exception as exc:
        return ItemOutcome(status="blocked", detail=f"refresh failed: {exc!r}")
    return ItemOutcome(status="done",
                       detail=f"{state.version} ({state.item_count} items)")


register_job_kind("monthly-finding-aid-mirror-refresh", _enumerate, _run_item)
