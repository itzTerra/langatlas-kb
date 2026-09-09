"""§4.4's monthly link-checker, driven through the generic orchestrator loop.

One work item per URL-bearing source, because one source is what a finding is *about* and
what a resumed run should re-check. The job's entire authority is: write a private row,
file a queue entry. It never touches a fact, a verdict, or a snapshot — a dead live link
does not retroactively unverify a fact verified against the archived copy (§4.4)."""
from pathlib import Path

import psycopg

from langatlas_ingest.config import IngestConfig
from langatlas_ingest.currency.links import FetchedPage, check_link
from langatlas_ingest.currency.store import (
    file_link_findings, previous_link_hash, record_link_check,
)
from langatlas_ingest.db import connect
from langatlas_ingest.store import SourcingQueue
from langatlas_ingest.verify.sources import load_source_facts

from langatlas_orchestrator.registry import ItemOutcome, register_job_kind

# Long enough for a slow docs host, short enough that a hung request cannot eat a night.
_TIMEOUT_SECONDS = 30


def _url_for(facts, source_id: str) -> str | None:
    entry = facts.get(source_id)
    return (entry.csl.get("URL") if entry else None) or None


def _enumerate(extra: dict, repo_root: Path) -> list[str]:
    """Every committed source record carrying a `URL`.

    Plan decision 1: that is what "URL-locator sources only" means mechanically. A record
    with only a DOI has no live link, and enumerating it would burn a checkpoint row every
    month to conclude nothing."""
    facts = load_source_facts(repo_root / "sources")
    wanted = set(extra.get("source_ids") or ())
    return [source_id for source_id in sorted(facts)
            if _url_for(facts, source_id) and (not wanted or source_id in wanted)]


def _http_fetch(ctx):
    """Build the fetcher. Patched wholesale in tests — no test in this package makes a
    real request."""
    import httpx

    client = httpx.Client(timeout=_TIMEOUT_SECONDS, follow_redirects=True,
                          headers={"user-agent": _user_agent(ctx)})

    def fetch(url: str) -> FetchedPage:
        response = client.get(url)
        return FetchedPage(status=response.status_code, text=response.text)

    return fetch


def _user_agent(ctx) -> str:
    return "LangAtlas-link-checker/0.1 (+https://langatlas.dev; corpus maintenance)"


def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
    facts = load_source_facts(repo_root / "sources")
    url = _url_for(facts, item_key)
    if url is None:
        # The store changed between enumeration and this item. Not a human's problem:
        # next month enumerates the store as it then is.
        return ItemOutcome(status="done", detail=f"{item_key} no longer carries a URL")
    config = IngestConfig.load()
    try:
        with connect(config.dsn) as conn:
            result = check_link(item_key, url, fetch=_http_fetch(ctx),
                                previous_hash=previous_link_hash(conn, item_key))
            record_link_check(conn, result)
            filed = file_link_findings(SourcingQueue(conn), result)
    except psycopg.OperationalError as exc:
        # Infrastructure, not a verdict about this source: `blocked` pauses the run for a
        # plain re-invocation, exactly as verification.py does.
        return ItemOutcome(status="blocked", detail=f"database unavailable: {exc}")
    # The fetched page never reaches a model, so it never goes through `ctx.tool_result`.
    # What *is* logged is the check's own conclusion — our text, about their page.
    ctx.writer.append(role="assistant",
                      content=f"{item_key}: {url} -> resolves={result.resolves} "
                              f"anchor_present={result.anchor_present} "
                              f"drifted={result.drifted}",
                      flags=["link-check"])
    return ItemOutcome(status="done",
                       detail=", ".join(filed) if filed else "ok")


register_job_kind("monthly-link-checker", _enumerate, _run_item)
