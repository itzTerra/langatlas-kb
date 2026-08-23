"""Stage 1's hard exit gate (cross-stage plan, Stage 1): 'an agent can run
search_sources, mint a node file that validates, and the run is logged.' Registered as
an ordinary job kind so the exit test is driven through the same generic loop every
other job uses — proving the orchestrator itself, not a bespoke script, is what closes
out Stage 1."""
import io
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_commit.land import BlockedRedMain, ContentionExhausted, Landed, land_record
from langatlas_commit.trailers import record_key
from langatlas_ingest.tools import search_sources
from langatlas_validate.normalize import normalize_record
from langatlas_validate.schema import validate_record

from langatlas_orchestrator.registry import ItemOutcome, register_job_kind

_ITEM_KEY = "mint-search-and-commit"
_SLUG = "orchestrator-exit-test-probe"


def _mint_concept_record(query: str, hit: dict) -> tuple[str, str]:
    """The smallest valid `concept` record, citing the top `search_sources` hit's
    `source_id`/`locator` verbatim — copied from retrieval, never re-derived (Section
    4.3's own rule), which is exactly the property this exit test proves."""
    data = {
        "id": _SLUG,
        "slug": _SLUG,
        "name": "Orchestrator exit-test probe",
        "summary": {
            "text": f"Synthetic concept minted by the R0 exit test to prove the "
                   f"search_sources -> mint -> commit -> log path, retrieved for "
                   f"query {query!r}.",
            "sources": [{"source": hit["source_id"], "locator": hit["locator"]}],
        },
        "provenance": {"claim_origin": "prior"},
    }
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    buf = io.StringIO()
    yaml.dump(data, buf)
    raw = buf.getvalue()
    return f"concepts/{_SLUG}.yaml", normalize_record(raw, "concept")


def _enumerate(extra: dict, repo_root: Path) -> list[str]:
    return [_ITEM_KEY]


def _validator_for(record_path: str, content: str):
    def _validator(worktree: Path) -> list[str]:
        yaml = YAML(typ="safe")
        text = (worktree / record_path).read_text()
        errors = validate_record(yaml.load(text), "concept")
        if normalize_record(text, "concept") != text:
            errors.append("not normalized (re-run the normalizer to fix)")
        return errors
    return _validator


def _run_item(ctx, item_key: str, extra: dict, repo_root: Path) -> ItemOutcome:
    query = extra.get("query", "pattern matching")

    from langatlas_ingest.db import connect

    conn = connect()
    try:
        hits = search_sources(ctx, query, k=1, conn=conn)
    finally:
        conn.close()

    if not hits:
        return ItemOutcome(status="halted",
                           detail=f"no search_sources hit for query {query!r} — has "
                                  f"`langatlas-sources ingest` run against this corpus?")

    record_path, content = _mint_concept_record(query, hits[0])
    key = record_key(record_path, content)

    result = land_record(repo_root, record_path, content, chat_run_id=f"{ctx.run_id}#msg-1",
                         validator=_validator_for(record_path, content))
    if isinstance(result, Landed):
        return ItemOutcome(status="done", record_key=key,
                           detail=f"landed as {result.commit_sha}")
    # `BlockedRedMain`/`ContentionExhausted` are transient, re-attemptable outcomes in
    # `LandResult`'s own model (analogous to the driver's `blocked`/`contention`
    # statuses) — only the remaining variants (`Reverted`, `UnsafeHalt`, and anything
    # else unhandled) genuinely need a human, so those alone map to `halted`.
    if isinstance(result, BlockedRedMain):
        return ItemOutcome(status="blocked", detail=f"main is red: {result!r}")
    if isinstance(result, ContentionExhausted):
        return ItemOutcome(status="contention", detail=f"contention exhausted: {result!r}")
    return ItemOutcome(status="halted", detail=f"land_record did not land: {result!r}")


register_job_kind("r0-exit-test", _enumerate, _run_item)
