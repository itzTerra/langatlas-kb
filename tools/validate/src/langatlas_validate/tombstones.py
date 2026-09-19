"""The append-only fact-supersession ledger (§3.2, D23/D38) and the one chain walker.

A fact id is content-keyed, so any claim change mints a new id, and the old id must keep
resolving: challenge links, chat logs and (Stage 6) static pages all cite ids. Each entry says
what became of one dead id. `resolve_fact` is deliberately the only routine that follows
`superseded_by` — the Astro build and the MCP server both call it (§5.4), so they can never
disagree about where an id leads.

`derived_from` is not stored. It is exactly the inverse of `superseded_by`; storing both would
give one relation two copies that could drift."""
import io
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_validate.schema import validate_record

TOMBSTONES_REL = "tombstones.yaml"
# D38: "depth-capped … with a loud error". A real history is a fact remapped once or twice;
# a chain of five is already a data bug.
MAX_CHAIN_DEPTH = 5
TOMBSTONE_ACTIONS = ("remap", "requeue", "tombstone")
TOMBSTONE_REASONS = ("split", "merge", "move", "removal", "corrected-value")
_KEY_ORDER = ("fact_id", "anchor", "action", "reason", "superseded_by", "migration_id", "date")

_safe = YAML(typ="safe")


class ChainTooDeep(Exception):
    """A tombstone chain longer than MAX_CHAIN_DEPTH hops — a data bug, never a history."""


class ChainCycle(ChainTooDeep):
    """A tombstone chain that leads back to an id already on its own path — a data bug."""


def _successors(entry: dict) -> list:
    value = entry.get("superseded_by")
    return value if isinstance(value, list) else []


@dataclass(frozen=True)
class Resolution:
    """@param status: `live` | `superseded` (live successors) | `retired` (the chain ends in
        an empty successor list) | `unknown` (neither live nor tombstoned).
    @param successors: the live fact ids the chain ends at, in walk order.
    @param chain: every tombstone entry walked, in walk order."""
    fact_id: str
    status: str
    successors: tuple[str, ...]
    chain: tuple[dict, ...]


def parse_tombstones(text: str | None) -> list[dict]:
    if not text:
        return []
    return list((_safe.load(text) or {}).get("tombstones") or [])


def load_tombstones(repo_root: Path) -> list[dict]:
    path = Path(repo_root) / TOMBSTONES_REL
    return parse_tombstones(path.read_text() if path.exists() else None)


def render_tombstones(entries: list[dict]) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    ordered = [{key: entry[key] for key in _KEY_ORDER if key in entry} for entry in entries]
    buf = io.StringIO()
    yaml.dump({"tombstones": ordered}, buf)
    return buf.getvalue()


def resolve_fact(fact_id: str, *, entries, live: set[str],
                 max_depth: int = MAX_CHAIN_DEPTH) -> Resolution:
    """Follows `superseded_by` breadth-first until every branch ends in a live fact or an
    empty successor list.

    @raises ChainTooDeep: a branch needs more than `max_depth` tombstone hops."""
    if fact_id in live:
        return Resolution(fact_id, "live", (fact_id,), ())
    index = {entry["fact_id"]: entry for entry in entries
             if isinstance(entry, dict) and isinstance(entry.get("fact_id"), str)}
    if fact_id not in index:
        return Resolution(fact_id, "unknown", (), ())
    chain, terminal = [], []

    def walk(current: str, path: tuple[str, ...]) -> None:
        if current in live:
            if current not in terminal:
                terminal.append(current)
            return
        entry = index.get(current)
        if entry is None:
            return                      # dangling: validate_tombstones reports it
        if current in path:
            raise ChainCycle(f"{fact_id}: the tombstone chain loops back to {current}"
                             f" — a data bug, not a migration history")
        if len(path) >= max_depth:
            raise ChainTooDeep(f"{fact_id}: the tombstone chain is longer than {max_depth}"
                               f" hops — a data bug, not a migration history")
        if entry not in chain:
            chain.append(entry)
        for successor in _successors(entry):
            walk(successor, (*path, current))

    walk(fact_id, ())
    return Resolution(fact_id, "superseded" if terminal else "retired", tuple(terminal),
                      tuple(chain))


def derived_from(fact_id: str, entries) -> tuple[str, ...]:
    """The dead ids whose entries name `fact_id` as a successor, in ledger order."""
    return tuple(entry["fact_id"] for entry in entries
                 if isinstance(entry, dict) and fact_id in _successors(entry))


def validate_tombstones(entries, *, live: set[str]) -> list[str]:
    """Schema, one entry per dead id, every successor resolvable, every chain within the cap.

    A tombstoned id that is live again (an identical claim re-minted later) is not an error:
    `resolve_fact` checks liveness first, so the entry is simply history."""
    errors: list[str] = []
    seen: set[str] = set()
    tombstoned = {entry.get("fact_id") for entry in entries if isinstance(entry, dict)}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"[{index}]: entry is not a mapping")
            continue
        where = f"[{index}] {entry.get('fact_id', '<no fact_id>')}"
        schema_errors = validate_record(entry, "tombstone")
        errors.extend(f"{where}: {error}" for error in schema_errors)
        if entry.get("fact_id") in seen:
            errors.append(f"{where}: duplicate entry — a fact is superseded once")
        seen.add(entry.get("fact_id"))
        for successor in _successors(entry):
            if successor not in live and successor not in tombstoned:
                errors.append(f"{where}: successor {successor} is neither a live fact nor"
                              f" tombstoned")
        if schema_errors:
            continue                    # a malformed entry cannot be walked
        try:
            resolve_fact(entry["fact_id"], entries=entries, live=live)
        except ChainTooDeep as exc:     # includes ChainCycle
            errors.append(f"{where}: {exc}")
    return errors


def check_append_only(before, after, *, live_after: set[str]) -> list[str]:
    """§3.3: the ledger is append-only. The one legal removal is a `git revert` of the
    migration that wrote the line, which brings the fact itself back to life (§5.2: rollback =
    `git revert`)."""
    def keyed(entries):
        return {entry["fact_id"]: entry for entry in entries
                if isinstance(entry, dict) and isinstance(entry.get("fact_id"), str)}

    current = keyed(after)
    errors = []
    for fact_id, entry in keyed(before).items():
        if fact_id in current:
            if current[fact_id] != entry:
                errors.append(f"{fact_id}: a tombstone entry was edited; the ledger is"
                              f" append-only")
        elif fact_id not in live_after:
            errors.append(f"{fact_id}: a tombstone entry was removed while its fact is still"
                          f" dead — only a revert that brings the fact back may remove it")
    return errors
