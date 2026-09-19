"""CI's determinism check for migrations (§5.2: "CI replays the script for determinism").

A manifest commit must be exactly what the interpreter produces from its parent: the same
files, the same bytes, nothing else. Replay runs `plan_migration` on the parent's tree
(extracted with `git archive`, so no working copy is touched) and compares. A hand-edited file
riding along with a manifest fails here. So does a migration rebased onto a store it no longer
fits. Either way the fix is to re-run `consolidate migrate`, never to edit the commit."""
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_validate.gitrefs import (
    changed_paths, commits_since, extract_tree, resolve_ref, show,
)
from langatlas_validate.migrate import (
    MigrationError, is_manifest_path, plan_migration,
)

_safe = YAML(typ="safe")


@dataclass(frozen=True)
class ReplayResult:
    migration_id: str
    commit: str
    errors: tuple[str, ...]


def added_manifests(repo_root: Path, since: str | None) -> list[tuple[str, str]]:
    """@param since: a resolved sha; None walks the whole history.
    @returns `(commit, manifest path)` for every manifest a commit after `since` added."""
    return [(commit, rel) for commit in commits_since(repo_root, since)
            for status, rel in changed_paths(repo_root, commit)
            if status == "A" and is_manifest_path(rel)]


def replay_commit(repo_root: Path, commit: str, manifest_rel: str) -> ReplayResult:
    root = Path(repo_root)
    try:
        manifest = _safe.load(show(root, commit, manifest_rel) or "")
    except Exception as exc:
        return ReplayResult(manifest_rel, commit,
                            (f"{manifest_rel}: not valid YAML ({type(exc).__name__}: {exc})",))
    if not isinstance(manifest, dict):
        return ReplayResult(manifest_rel, commit, (f"{manifest_rel}: a manifest must be a mapping",))
    migration_id = str(manifest.get("migration_id", manifest_rel))
    parent = resolve_ref(root, f"{commit}^")
    if parent is None:
        return ReplayResult(migration_id, commit,
                            ("a migration cannot be the repository's first commit",))
    with tempfile.TemporaryDirectory() as scratch:
        tree = Path(scratch) / "tree"
        extract_tree(root, parent, tree)
        try:
            plan = plan_migration(tree, manifest)
        except MigrationError as exc:
            return ReplayResult(migration_id, commit,
                                (f"replay against {parent[:10]} failed: {exc}",))
    errors = []
    for rel, text in sorted(plan.changes.items()):
        if show(root, commit, rel) != text:
            errors.append(f"{rel}: the commit's content differs from the manifest's replay"
                          if text is not None
                          else f"{rel}: the replay deletes it, but the commit keeps it")
    committed = {rel for _status, rel in changed_paths(root, commit)}
    for rel in sorted(committed - set(plan.changes) - {manifest_rel}):
        errors.append(f"{rel}: changed in the migration commit but not by its manifest")
    return ReplayResult(migration_id, commit, tuple(errors))


def replay_since(repo_root: Path, since: str | None) -> list[ReplayResult]:
    """@param since: any ref. An empty, all-zero or unknown one (a branch's first push)
        replays every manifest in history, which is cheap: migrations are rare."""
    base = resolve_ref(repo_root, since)
    return [replay_commit(repo_root, commit, rel)
            for commit, rel in added_manifests(repo_root, base)]
