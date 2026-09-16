"""Which carves are contested — a function of the plan and the store, never a mood.

§7.2's rule is "contested carves only; a debate is never free chat". If the model decided what
counts as contested, the debate budget would be unbounded and the rule unenforceable, so the
triggers are mechanical and the vocabulary is closed. The ontologist's own flag is *one* of the
seven triggers, not the definition.

A developer who disagrees with a trigger waives it by hand with a reason — the same escape-hatch
shape 3B gives an unclosable sourcing gap. An agent never waives anything."""
from pathlib import Path

from langatlas_research.draft.plan import ENTRY_LISTS, entries, find_entry, set_entry

TRIGGERS = ("merged-candidates", "split-candidate", "new-dimension", "new-quality",
            "single-source", "id-collision", "ontologist-flagged")

_ORDER = {trigger: index for index, trigger in enumerate(TRIGGERS)}

# An entry in one of these states is settled: it is in git, or it will never be. Recomputing
# its triggers against the store it has just joined would fire `id-collision` on every node
# this cycle minted — and every later `mark_contested` (the edge drafter runs one) would then
# hand `finalize` a carve that is "contested with no debate" forever.
_TERMINAL = ("minted", "dropped")


def _sources(entry: dict) -> set[str]:
    """Every distinct source id an entry leans on, across whichever evidence shape it has."""
    found = {citation["source"] for citation in entry.get("evidence") or []}
    for assessment in entry.get("assessments") or []:
        found |= {citation["source"] for citation in assessment.get("evidence") or []}
    return found


def contested_triggers(plan: dict, *, repo_root: Path | None = None,
                       store=None) -> dict[str, tuple[str, ...]]:
    """@param store: a `StoreView`; None reads the store at `repo_root`.
    @returns: `{entry key: triggers}` for every contested entry, triggers in `TRIGGERS` order.
        An entry with no triggers is absent from the mapping, and so is every entry whose
        status is terminal — a minted or dropped carve's trigger history is settled."""
    if store is None:
        from langatlas_research.draft.ontologist import read_store

        store = read_store(repo_root)

    proposed_dimensions = {d["slug"] for d in plan.get("dimensions") or []}
    proposed_qualities = {q["slug"] for q in plan.get("qualities") or []}

    candidate_users: dict[str, list[str]] = {}
    for _name, entry in entries(plan):
        for candidate in entry.get("from_candidates") or []:
            candidate_users.setdefault(candidate, []).append(entry["key"])
    split = {key for users in candidate_users.values() if len(users) > 1 for key in users}

    found: dict[str, set[str]] = {}

    def flag(key: str, trigger: str) -> None:
        found.setdefault(key, set()).add(trigger)

    for name, entry in entries(plan):
        key = entry["key"]
        if entry.get("status") in _TERMINAL:
            continue
        if "ontologist-flagged" in (entry.get("contested") or []):
            flag(key, "ontologist-flagged")
        if len(entry.get("from_candidates") or []) > 1:
            flag(key, "merged-candidates")
        if key in split:
            flag(key, "split-candidate")
        if name in ("nodes", "edges", "quality_edges") and len(_sources(entry)) < 2:
            flag(key, "single-source")
        if name == "nodes" and entry["id"] in store.nodes:
            flag(key, "id-collision")
        if name == "dimensions":
            flag(key, "new-dimension")
        if name == "qualities":
            flag(key, "new-quality")
        if entry.get("dimension") in proposed_dimensions and entry.get("dimension"):
            flag(key, "new-dimension")
        if name == "quality_edges" and entry.get("to") in proposed_qualities:
            flag(key, "new-quality")

    return {key: tuple(sorted(triggers, key=_ORDER.__getitem__))
            for key, triggers in sorted(found.items())}


def mark_contested(plan: dict, *, repo_root: Path | None = None, store=None) -> dict:
    """Returns a copy of `plan` with every entry's `contested` list recomputed. Idempotent —
    it is re-run after every step that adds entries (the edge drafter, a debate's split).

    A terminal entry keeps the triggers it was debated over: its `contested` list is debate
    history by then, not a question still open."""
    triggers = contested_triggers(plan, repo_root=repo_root, store=store)
    updated = dict(plan)
    for name in ENTRY_LISTS:
        updated[name] = [dict(entry) if entry.get("status") in _TERMINAL
                         else {**entry, "contested": list(triggers.get(entry["key"], ()))}
                         for entry in plan.get(name) or []]
    return updated


def open_carves(plan: dict) -> list[str]:
    """Contested entries that have neither been debated nor waived — what `draft debate`
    works through and what `draft finalize` refuses to close over. A minted entry is not
    open: git already holds it, so there is nothing left to debate."""
    return [entry["key"] for _name, entry in entries(plan)
            if entry.get("contested") and entry.get("debate_id") is None
            and entry.get("status") not in ("waived", *_TERMINAL)]


def waive(plan: dict, key: str, reason: str) -> dict:
    """The developer's escape hatch: this carve is contested, and the developer says it does
    not need a debate. Never called by an agent.

    An `escalate` disposition (see `debate.apply_resolution`) is the one case where a debate
    and a waiver can coexist: `escalate` sets `status: proposed` and leaves `debate_id` set,
    because the debate could not settle the question and handed it back to the developer. That
    exact shape — a debate id with `status: proposed` — is otherwise unreachable (every other
    disposition moves the entry to `debated`, `dropped`, or a fresh `debated` split), so it is
    safe to read as "the developer is manually ruling on an escalation" and let the waiver
    through rather than treating it as a second, competing debate.

    @raises KeyError: no entry with this key.
    @raises ValueError: the entry is not contested, or already has a settled debate."""
    _name, entry = find_entry(plan, key)
    if not entry.get("contested"):
        raise ValueError(f"{key} is not contested; there is nothing to waive")
    if entry.get("debate_id") and entry["status"] != "proposed":
        raise ValueError(f"{key} already has debate {entry['debate_id']}")
    return set_entry(plan, key, status="waived", waiver=reason)
