"""R3's corpus-tagging volume pass (§7.4, Stage 3B), driven through the generic loop.

One work item per pool batch: a batch is one completion call, so it is the grain at which an
interrupted pass can resume without re-paying for work already done. Hand-launched per cycle
with `--set cycle=N`, never cron — nothing in R3 runs before the developer's sign-off (D27),
and the enumerator enforces that gate rather than trusting the invocation."""
from pathlib import Path

import psycopg

from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import connect
from langatlas_pipeline.errors import CircuitOpen, ProviderTransportError, StructuredOutputError
from langatlas_research.config import ResearchConfig
from langatlas_research.cycle import load_cycle
from langatlas_research.errors import TaggerOutputInvalid
from langatlas_research.paths import research_config_path
from langatlas_research.survey.chunks import db_chunk_lookup
from langatlas_research.survey.pool import (
    batch_key, batches, parse_batch_key, require_current_pool,
)
from langatlas_research.survey.tagger import tag_batch
from langatlas_research.survey.tags import TagStore
from langatlas_research.themes import load_themes

from langatlas_orchestrator.registry import ItemOutcome, register_job_kind

KIND = "r3-corpus-tagging"


def _cycle_number(extra: dict) -> int:
    if extra.get("cycle") is None:
        raise ValueError(f"{KIND} needs a cycle: run it with `--set cycle=<N>`")
    return int(extra["cycle"])


def _tagger_config(repo_root: Path):
    return ResearchConfig.load(research_config_path(repo_root)).tagger


def _batch_size(extra: dict, repo_root: Path) -> int:
    return int(extra.get("batch_size") or _tagger_config(repo_root).batch_size)


def _enumerate(extra: dict, repo_root: Path) -> list[str]:
    """@raises SignOffMissing / SignOffStale / PoolMissing / PoolStale: before any work."""
    cycle = load_cycle(_cycle_number(extra), repo_root=repo_root)
    pool = require_current_pool(cycle, repo_root=repo_root)
    return [f"{batch_key(cycle.slug, index)}@{pool.digest}"
            for index in range(len(batches(pool, _batch_size(extra, repo_root))))]


def _tag(ctx, theme, cycle_slug, batch, alias):
    """The one provider- and database-touching call, isolated so tests can replace it."""
    with connect(IngestConfig.load().dsn) as conn, TagStore() as store:
        return tag_batch(ctx, theme, cycle_slug, batch, lookup=db_chunk_lookup(conn),
                         store=store, alias=alias)


def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
    key, _, digest = item_key.rpartition("@")
    cycle_slug, index = parse_batch_key(key)
    cycle = load_cycle(_cycle_number(extra), repo_root=repo_root)
    pool = require_current_pool(cycle, repo_root=repo_root)
    if pool.digest != digest:
        return ItemOutcome(status="done",
                           detail=f"superseded: pool rebuilt ({digest} -> {pool.digest})")
    batch = batches(pool, _batch_size(extra, repo_root))[index]
    alias = extra.get("alias") or _tagger_config(repo_root).alias
    theme = load_themes(repo_root)[cycle.theme]
    try:
        result = _tag(ctx, theme, cycle_slug, batch, alias)
    except psycopg.OperationalError as exc:
        return ItemOutcome(status="blocked", detail=f"database unavailable: {exc}")
    except (ProviderTransportError, CircuitOpen) as exc:
        # A timed-out or down completion channel is exactly as transient as a down database
        # (D43 §2.1): pause this item rather than let an unhandled exception crash the whole
        # batch — resume retries it, same as every other `blocked` item.
        return ItemOutcome(status="blocked", detail=f"provider unavailable: {exc}")
    except (TaggerOutputInvalid, StructuredOutputError) as exc:
        # Deterministic at temperature 0 and cached: a retry returns the same answer. The
        # batch completes with no tag rows, and the survey header's counts show the loss.
        return ItemOutcome(status="done", detail=f"unusable tagger response: {exc}")
    return ItemOutcome(status="done",
                       detail=f"tagged {result.tagged}, skipped {result.skipped},"
                              f" missing {result.missing}, stale {result.stale},"
                              f" dropped terms {result.dropped_terms}")


register_job_kind(KIND, _enumerate, _run_item)
