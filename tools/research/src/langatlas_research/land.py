"""Landing: the one place Stage 3 touches the commit protocol.

Everything is rendered fresh on each attempt. That costs nothing for a one-file-per-record
mint and is the whole mechanism for a shared-file mint: after `land_record` rebases onto
someone else's taxonomy addition, re-rendering reads their entry and adds ours on top,
instead of pushing a file that silently drops it."""
from pathlib import Path

from langatlas_commit.land import ContentionExhausted, Landed, land_record

from langatlas_research.cycle import record_minted
from langatlas_research.errors import RaceExhausted
from langatlas_research.mint import MintedRecord, content_digest, render_draft
from langatlas_research.schema import validate_research_tree
from langatlas_validate.store import validate_store


def store_validator(repo_root: Path) -> list[str]:
    """What `land_record` re-runs after every rebase: the canonical store's own gate plus
    the research tree's, so a commit can never leave either invalid on `main`."""
    return validate_store(repo_root) + validate_research_tree(repo_root)


def _render(item, repo_root: Path) -> MintedRecord:
    return item() if callable(item) else render_draft(item, repo_root=repo_root)


def _is_stale(minted: MintedRecord, repo_root: Path) -> bool:
    """True when a shared file changed under us between render and land."""
    if minted.base_digest is None:
        return False
    path = repo_root / minted.path
    return path.exists() and content_digest(path.read_text()) != minted.base_digest


def land_drafts(items, *, repo_root: Path, chat_run_id: str, cycle=None,
                status_checker=None, attempts: int = 3):
    """Renders and lands each item, one commit per record (D36).

    @param items: draft objects, or zero-argument callables returning a `MintedRecord`.
    @param cycle: when given, every landed record's node ids are appended to it.
    @returns: one `(MintedRecord, LandResult)` per item, in input order.
    @raises ResearchError: from rendering — an invalid draft never reaches git.
    @raises RaceExhausted: a shared-file mint found the file stale on every attempt, so
        `land_record` never even got to try landing it."""
    results = []
    for item in items:
        outcome = None
        minted = None
        for _ in range(attempts):
            minted = _render(item, repo_root)
            if _is_stale(minted, repo_root):
                continue
            outcome = land_record(repo_root, minted.path, minted.text,
                                  chat_run_id=chat_run_id, validator=store_validator,
                                  status_checker=status_checker)
            if isinstance(outcome, Landed):
                if cycle is not None:
                    cycle = record_minted(cycle, minted.node_ids, repo_root=repo_root)
                break
            if not isinstance(outcome, ContentionExhausted):
                break
        if outcome is None:
            raise RaceExhausted(
                f"{minted.path}: lost the shared-file race on every one of {attempts}"
                f" attempts — land_record never got a chance to try landing it")
        results.append((minted, outcome))
    return results
