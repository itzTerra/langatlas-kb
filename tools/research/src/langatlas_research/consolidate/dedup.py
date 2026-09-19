"""R6's dedup/alias audit (§7.4). R4's `merged-candidates` trigger catches duplicates inside
one theme's inventory; a node a later theme mints under another name is invisible to it. Here
every node this cycle minted is compared with every committed node, mechanically, and the
developer rules on each pair — `distinct` (never raised again), `merge` (a Task 8 manifest), or
`drop-alias` (the ambiguous synonym goes). No model: the signals are string facts, and the
ruling is an ontology decision the developer owns, like a waiver."""
import hashlib
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from langatlas_research.consolidate.record import iter_records
from langatlas_research.cycle import Cycle
from langatlas_research.errors import DedupRefused
from langatlas_research.mint import dump_yaml
from langatlas_validate.normalize import normalize_record, normalize_value
from langatlas_validate.store import iter_store_records

DEDUP_SIGNALS = ("same-name", "name-is-alias", "shared-alias", "id-token-overlap")
# Jaccard overlap of hyphen tokens at which two ids read as one phrase reordered:
# `tracing-garbage-collection` / `garbage-collection-tracing` share 3 of 3 (1.0) and are
# flagged; `static-type-checking` / `static-type-check` share 2 of 4 (0.5) and are not — the
# name and alias signals catch that kind.
TOKEN_OVERLAP_MIN = 0.75
_KEY_HEX = 12


def dedup_key(a: str, b: str) -> str:
    body = "\n".join(sorted((a, b)))
    return "d-" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:_KEY_HEX]


def _norm(text: str) -> str:
    return normalize_value(text, freetext=True)


def _alias_set(record: dict) -> set[str]:
    aliases = record.get("aliases") or []
    if not isinstance(aliases, list) or not all(isinstance(entry, str) for entry in aliases):
        raise DedupRefused(f"{record.get('id')!r} has a non-string alias entry")
    return {_norm(alias) for alias in aliases}


def _signals(a: dict, b: dict) -> list[str]:
    name_a, name_b = _norm(str(a.get("name") or "")), _norm(str(b.get("name") or ""))
    aliases_a, aliases_b = _alias_set(a), _alias_set(b)
    tokens_a, tokens_b = set(a["id"].split("-")), set(b["id"].split("-"))
    found = []
    if name_a and name_a == name_b:
        found.append("same-name")
    if (name_a and name_a in aliases_b) or (name_b and name_b in aliases_a):
        found.append("name-is-alias")
    if aliases_a & aliases_b:
        found.append("shared-alias")
    if len(tokens_a & tokens_b) / len(tokens_a | tokens_b) >= TOKEN_OVERLAP_MIN:
        found.append("id-token-overlap")
    return found


def _nodes(repo_root: Path) -> dict[str, dict]:
    return {data["id"]: data for _path, kind, _text, data in iter_store_records(Path(repo_root))
            if kind in ("feature", "concept")}


def candidates(repo_root: Path, *, cycle: Cycle) -> list[dict]:
    """Every pair of (a node this cycle minted, any other committed node) that a signal links,
    in key order."""
    nodes = _nodes(repo_root)
    found, seen = [], set()
    for mine in sorted(node for node in cycle.nodes_minted if node in nodes):
        for other in sorted(nodes):
            key = dedup_key(mine, other)
            if other == mine or key in seen:
                continue
            seen.add(key)
            signals = _signals(nodes[mine], nodes[other])
            if signals:
                found.append({"key": key, "nodes": sorted((mine, other)), "signals": signals})
    return sorted(found, key=lambda candidate: candidate["key"])


def rulings(repo_root: Path) -> dict[str, dict]:
    """Every committed ruling, keyed by pair; a later cycle's ruling on a pair wins."""
    ruled: dict[str, dict] = {}
    for record in iter_records(repo_root):
        for entry in record["dedup"]:
            ruled[entry["key"]] = entry
    return ruled


def open_candidates(repo_root: Path, *, cycle: Cycle, record: dict) -> list[dict]:
    ruled = {**rulings(repo_root), **{entry["key"]: entry for entry in record["dedup"]}}
    return [candidate for candidate in candidates(repo_root, cycle=cycle)
            if candidate["key"] not in ruled]


def make_ruling(candidate: dict, *, disposition: str, reason: str, migration: str | None = None,
                node: str | None = None, alias: str | None = None) -> dict:
    """@raises DedupRefused: no reason, or a merge/drop-alias naming a node outside the pair."""
    if not reason.strip():
        raise DedupRefused("a ruling needs a reason — it is the only record of why")
    ruling = {"key": candidate["key"], "nodes": candidate["nodes"],
              "signals": candidate["signals"], "disposition": disposition, "reason": reason}
    if disposition == "drop-alias" and not alias:
        raise DedupRefused("drop-alias names the alias to drop")
    if disposition in ("merge", "drop-alias"):
        if node not in candidate["nodes"]:
            raise DedupRefused(f"{node!r} is not one of {candidate['nodes']}")
        ruling["node"] = node
    if disposition == "merge":
        ruling["migration"] = migration
    if disposition == "drop-alias":
        ruling["alias"] = alias
    return ruling


def drop_alias(repo_root: Path, node_id: str, alias: str) -> tuple[str, str]:
    """@returns `(record path, normalized text)` without `alias` — cosmetic for `version-bump`,
        so it lands as an ordinary record even in a settled theme.
    @raises DedupRefused: not a feature, or the feature has no such alias."""
    rel = f"features/{node_id}.yaml"
    path = Path(repo_root) / rel
    if not path.exists():
        raise DedupRefused(f"{node_id!r} is not a committed feature (only features carry aliases)")
    try:
        data = YAML().load(path.read_text())
    except YAMLError as exc:
        raise DedupRefused(f"{rel} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise DedupRefused(f"{rel} is not a record mapping")
    if not isinstance(data.get("aliases") or [], list):
        raise DedupRefused(f"{node_id} has a malformed alias list")
    if not all(isinstance(entry, str) for entry in data.get("aliases") or []):
        raise DedupRefused(f"{node_id} has a non-string alias entry")
    aliases = list(data.get("aliases") or [])
    remaining = [entry for entry in aliases if _norm(entry) != _norm(alias)]
    if len(remaining) == len(aliases):
        raise DedupRefused(f"{node_id} has no alias {alias!r}")
    if remaining:
        data["aliases"] = remaining
    else:
        del data["aliases"]
    return rel, normalize_record(dump_yaml(data), "feature")
