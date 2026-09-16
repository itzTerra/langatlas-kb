"""§5.1's one semver, defined by fact blast radius, and §7.4's graduated 0.x ceremony.

During `0.x` a restructure is an ordinary MINOR: the research phase is *supposed* to
restructure, and gating it would make the ontology unwritable before it exists. At `1.0.0`
the same classification stops being auto-appliable and raises instead — the RFC-gated D16
process (Stage 4) is what resolves it. Defining the `>= 1.0.0` branch now, as a refusal,
is deliberate: the alternative is discovering at the flip that CI silently auto-bumped a
MAJOR."""
import subprocess
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_validate.store import _LEDGERS, iter_store_records

_yaml = YAML(typ="safe")

# Fields whose edit changes only wording, never a fact's meaning or identity (§3.5's
# copyedit-tolerant hashing applies the same idea to fact ids).
_COSMETIC_FIELDS = {"name", "slug", "message"}
_COSMETIC_SUBFIELDS = {("summary", "text"), ("statement", "text")}
# Fields whose edit moves or re-anchors an existing fact.
_STRUCTURAL_FIELDS = {"id", "layer", "dimension", "type", "from", "to", "when_all",
                      "language", "feature", "effect", "polarity"}

# Machine-written annotations. They are measurements about the corpus, not ontology content, so
# an edit that only touches one is not a version event at all — otherwise the nightly
# controversy batch would bump MINOR every time it found its first contested fact.
_MACHINE_FIELDS = {"controversy"}


def _without_machine_fields(record: dict) -> dict:
    return {k: v for k, v in record.items() if k not in _MACHINE_FIELDS}

STORE_DIRS = ("concepts", "features", "edges", "rules", "languages", "sources")


class MajorRequiresGovernance(Exception):
    """A restructuring change at >= 1.0.0 is an RFC-gated MAJOR (D16/§5.3) — never an
    automatic bump."""


def read_version(repo_root: Path) -> tuple[int, int, int]:
    major, minor, patch = (repo_root / "ontology" / "VERSION").read_text().strip().split(".")
    return int(major), int(minor), int(patch)


def write_version(repo_root: Path, version: tuple[int, int, int]) -> None:
    (repo_root / "ontology" / "VERSION").write_text(".".join(str(p) for p in version) + "\n")


def store_snapshot(repo_root: Path) -> dict[str, dict]:
    return {str(path.relative_to(repo_root)): data
            for path, _kind, _text, data in iter_store_records(repo_root)}


def snapshot_at(repo_root: Path, ref: str) -> dict[str, dict]:
    """The same mapping for a git ref, read through `git show` so no worktree or
    checkout is needed.

    Mirrors `iter_store_records`'s exact walk-and-exclude rules so the two never disagree
    on what "the store" is: a ledger name (`_LEDGERS`) is skipped, EXCEPT
    `languages/_registry.yaml`, which `iter_store_records` walks back in explicitly as its
    own `language-registry` record."""
    listing = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref, "--", *STORE_DIRS],
                             cwd=repo_root, capture_output=True, text=True, check=True)
    snapshot: dict[str, dict] = {}
    for rel in listing.stdout.splitlines():
        if not rel.endswith(".yaml"):
            continue
        name = rel.rsplit("/", 1)[-1]
        if name in _LEDGERS and rel != "languages/_registry.yaml":
            continue
        blob = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=repo_root,
                              capture_output=True, text=True, check=True)
        data = _yaml.load(blob.stdout)
        if isinstance(data, dict):
            snapshot[rel] = data
    return snapshot


def _diff_class(before: dict, after: dict) -> str:
    """The strongest class of change between two versions of one record."""
    before, after = _without_machine_fields(before), _without_machine_fields(after)
    if before == after:
        return "none"
    for field in _STRUCTURAL_FIELDS:
        if before.get(field) != after.get(field):
            return "restructuring"
    added = set(after) - set(before)
    removed = set(before) - set(after)
    if removed:
        return "restructuring"
    if added:
        return "additive"
    for field in set(before) | set(after):
        if before.get(field) == after.get(field):
            continue
        if field in _COSMETIC_FIELDS:
            continue
        if isinstance(before.get(field), dict) and isinstance(after.get(field), dict):
            changed = {k for k in set(before[field]) | set(after[field])
                       if before[field].get(k) != after[field].get(k)}
            if changed and all((field, k) in _COSMETIC_SUBFIELDS for k in changed):
                continue
        if isinstance(before.get(field), list) and isinstance(after.get(field), list):
            if len(after[field]) > len(before[field]):
                return "additive"
        return "restructuring"
    return "cosmetic"


_RANK = ("none", "cosmetic", "additive", "restructuring")


def classify_change(before: dict[str, dict], after: dict[str, dict]) -> str:
    """@returns: the strongest change class across the whole store."""
    strongest = "none"
    if set(before) - set(after):
        strongest = "restructuring"
    for path in set(after) - set(before):
        strongest = max(strongest, "additive", key=_RANK.index)
    for path in set(before) & set(after):
        strongest = max(strongest, _diff_class(before[path], after[path]), key=_RANK.index)
    return strongest


def bump(version: tuple[int, int, int], change: str) -> tuple[int, int, int]:
    """@raises MajorRequiresGovernance: restructuring change at >= 1.0.0."""
    major, minor, patch = version
    if change == "none":
        return version
    if change == "cosmetic":
        return major, minor, patch + 1
    if change == "restructuring" and major >= 1:
        raise MajorRequiresGovernance(
            "a restructuring change at >= 1.0.0 is an RFC-gated MAJOR (D16/§5.3):"
            " open the RFC instead of bumping")
    return major, minor + 1, 0
