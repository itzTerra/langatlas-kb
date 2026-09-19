"""The settled-theme guard (§7.4): once a theme is settled, a restructure of its records needs
a migration manifest, and a fact of it that vanishes needs a tombstone (§3.2).

Per commit, against the commit's parent — so settledness is judged as it stood when the change
was made. A commit that adds a manifest is skipped here on purpose: replay (Task 6) proves it
is exactly the interpreter's output, which is a stronger check than this one. Additive changes
(a new edge to a settled node) and cosmetic ones (a slug rename, an alias fix) are always free.

Theme membership is the cycle's `nodes_minted` (3A): node schemas have no theme field."""
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from langatlas_research.cycle import settled_themes_by_record
from langatlas_research.errors import ResearchError
from langatlas_validate.cli import infer_kind_from_path
from langatlas_validate.compile import derive_facts
from langatlas_validate.gitrefs import (
    changed_paths, commits_since, list_files, resolve_ref, show,
)
from langatlas_validate.migrate import is_manifest_path
from langatlas_validate.tombstones import TOMBSTONES_REL, parse_tombstones
from langatlas_validate.version import diff_class

_STORE_PREFIXES = ("concepts/", "features/", "edges/", "rules/")
_safe = YAML(typ="safe")


class GuardInputError(ResearchError):
    """A file at some commit is not parseable; `check_commit` reports it as an error string."""


def _load(text: str | None, where: str) -> dict:
    try:
        data = _safe.load(text or "")
    except YAMLError as exc:
        raise GuardInputError(f"{where}: unparseable YAML: {str(exc).splitlines()[0]}") from exc
    return data if isinstance(data, dict) else {}


def settled_ids_at(repo_root: Path, ref: str) -> dict[str, str]:
    """@returns record id -> theme for every theme settled at `ref`."""
    cycles = []
    for rel in list_files(repo_root, ref, "research/cycles"):
        if rel.endswith(".yaml"):
            cycles.append(_load(show(repo_root, ref, rel), f"{ref[:10]}:{rel}"))
    return settled_themes_by_record(cycles)


def _kind(rel: str, data: dict) -> str:
    kind = infer_kind_from_path(Path(rel))
    if kind == "edge" and data.get("type") == "affects-quality":
        return "affects-quality-edge"
    return kind


def _fact_anchors(rel: str, text: str, data: dict) -> dict[str, str]:
    facts = derive_facts([(Path(rel), _kind(rel, data), text, data)])
    return {fact["fact_id"]: fact["anchor"] for fact in facts}


def _is_store_file(rel: str) -> bool:
    return rel.startswith(_STORE_PREFIXES) and rel.endswith(".yaml")


def check_commit(repo_root: Path, commit: str) -> list[str]:
    """@returns error strings; unparseable files at either side of the commit are reported as
        errors too, never raised. A root commit has no parent, so nothing was settled: []."""
    try:
        return _check_commit(Path(repo_root), commit)
    except ResearchError as exc:               # GuardInputError, or a malformed settled cycle
        return [f"{commit[:10]} {exc}"]


def _check_commit(repo_root: Path, commit: str) -> list[str]:
    root = Path(repo_root)
    parent = resolve_ref(root, f"{commit}^")
    if parent is None:
        return []
    changes = changed_paths(root, commit)
    if any(status == "A" and is_manifest_path(rel) for status, rel in changes):
        return []
    settled = settled_ids_at(root, parent)
    if not settled:
        return []
    try:
        tombstoned = {entry["fact_id"] for entry in
                      parse_tombstones(show(root, commit, TOMBSTONES_REL))}
    except (YAMLError, KeyError, TypeError) as exc:
        raise GuardInputError(f"{TOMBSTONES_REL}: malformed tombstone ledger ({exc!r})") from exc
    added = {}                                  # id -> (path, text) of each new store file:
    for status, rel in changes:                 # a move or rename is a delete plus an add
        if status == "A" and _is_store_file(rel):
            text = show(root, commit, rel)
            added.setdefault(_load(text, f"{commit[:10]}:{rel}").get("id"), (rel, text))
    errors = []
    for _status, rel in changes:
        if not _is_store_file(rel):
            continue
        before_text = show(root, parent, rel)
        if before_text is None:
            continue                            # a new record: additive (or a rename target,
                                                # judged from its old path)
        before = _load(before_text, f"{parent[:10]}:{rel}")
        theme = settled.get(before.get("id"))
        if theme is None:
            continue
        where = f"{commit[:10]} {rel}"
        after_text = show(root, commit, rel)
        after_rel = rel
        if after_text is None:
            after_rel, after_text = added.get(before.get("id"), (None, None))
        if after_text is None:
            errors.append(f"{where}: removes a record of settled theme {theme!r} without a"
                          f" migration manifest (§7.4) — use `consolidate draft-migration`")
            continue
        after = _load(after_text, f"{commit[:10]}:{after_rel}")
        if (infer_kind_from_path(Path(rel)) != infer_kind_from_path(Path(after_rel))
                or diff_class(before, after) == "restructuring"):
            errors.append(f"{where}: restructures a record of settled theme {theme!r} without a"
                          f" migration manifest (§7.4) — use `consolidate draft-migration`"
                          + (f" (moved to {after_rel})" if after_rel != rel else ""))
            continue
        after_ids = set(_fact_anchors(after_rel, after_text, after))
        for fact_id, anchor in sorted(_fact_anchors(rel, before_text, before).items()):
            if fact_id not in after_ids and fact_id not in tombstoned:
                errors.append(f"{where}: fact {fact_id} ({anchor}) of settled theme {theme!r}"
                              f" vanished without a tombstone line (§3.2)")
    return errors


def check_settled(repo_root: Path, since: str | None) -> list[str]:
    """@param since: any ref; an empty, all-zero or unknown one checks the whole history."""
    base = resolve_ref(repo_root, since)
    return [error for commit in commits_since(repo_root, base)
            for error in check_commit(repo_root, commit)]
