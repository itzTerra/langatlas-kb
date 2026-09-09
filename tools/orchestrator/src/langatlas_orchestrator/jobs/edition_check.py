"""§4.4's edition check, made due-driven so §4.2's flat shorter interval for every
non-`formal-spec` grounding can actually fire (plan decision 2, Stage 2E).

The kind keeps its `quarterly-` name — it is the name in `crontab.example`, in the batch
spec, and in the D43 inventory — but the cron line runs monthly and the job no-ops for
sources whose interval has not elapsed. `formal-spec` sources therefore keep exactly the
quarterly cadence §4.4 specified, and everything else gets checked three times as often,
which is the whole point of §4.2's hook.

This job **never re-ingests**. A mismatch opens a triage entry naming
`langatlas-sources supersede`; adopting an edition stays a developer act."""
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from langatlas_ingest.config import IngestConfig
from langatlas_ingest.currency.editions import check_edition, check_url_for, is_due
from langatlas_ingest.currency.store import last_edition_check, record_edition_check
from langatlas_ingest.db import connect
from langatlas_ingest.store import SourcingQueue
from langatlas_ingest.verify.sources import load_source_facts

from langatlas_orchestrator.jobs.link_checker import _http_fetch  # noqa: F401
from langatlas_orchestrator.registry import ItemOutcome, register_job_kind


def _checkable(facts) -> dict:
    """source_id -> SourceFacts, for records that pin an edition and expose a page."""
    return {source_id: entry for source_id, entry in facts.items()
            if (entry.csl.get("custom") or {}).get("edition")
            and check_url_for(entry) is not None}


def _enumerate(extra: dict, repo_root: Path) -> list[str]:
    facts = _checkable(load_source_facts(repo_root / "sources"))
    wanted = set(extra.get("source_ids") or ())
    now = datetime.now(timezone.utc)
    config = IngestConfig.load()
    with connect(config.dsn) as conn:
        due = [source_id for source_id, entry in sorted(facts.items())
               if (not wanted or source_id in wanted)
               and is_due(entry.grounding, last_edition_check(conn, source_id), now=now)]
    return due


def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
    facts = load_source_facts(repo_root / "sources")
    entry = facts.get(item_key)
    if entry is None or not (entry.csl.get("custom") or {}).get("edition"):
        return ItemOutcome(status="done",
                           detail=f"{item_key} no longer pins an edition")
    config = IngestConfig.load()
    try:
        with connect(config.dsn) as conn:
            result = check_edition(item_key, entry, fetch=_http_fetch(ctx))
            record_edition_check(conn, result)
            if not result.matched:
                SourcingQueue(conn).file(kind="edition-check", source_id=item_key,
                                         reason="edition-mismatch", detail=result.detail)
    except psycopg.OperationalError as exc:
        return ItemOutcome(status="blocked", detail=f"database unavailable: {exc}")
    ctx.writer.append(role="assistant",
                      content=f"{item_key}: edition {result.edition} at {result.url} -> "
                              f"matched={result.matched} fetched={result.fetched}",
                      flags=["edition-check"])
    if not result.matched:
        return ItemOutcome(status="done", detail=f"edition-mismatch: {result.detail}")
    return ItemOutcome(status="done", detail="ok" if result.fetched else result.detail)


register_job_kind("quarterly-edition-check", _enumerate, _run_item)
