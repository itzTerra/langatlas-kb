"""FeatureInstance rendering (§3.3, §3.4, D65). Split from `mint.py` the way `mint_edges.py` is:
an instance's refusals are about what a status may say, not about ids.

The schema catches most shapes. These are the ones worth naming all at once for an agent: a
present or partial instance needs a `since` (D65 — its existence is cited through it), an absent
instance describes nothing present (no `since`, characteristics, syntax or notes), typed notes
belong to `partial` only, and every citation list is non-empty (D4)."""
import re

from langatlas_research.drafts import InstanceDraft
from langatlas_research.errors import InvalidDraft, UnsourcedNode
from langatlas_research.mint import MintedRecord, finish, provenance_block
from langatlas_validate.ids import compose_instance_id, is_valid_slug

STATUSES = ("present", "partial", "absent")
_CHARACTERISTIC_KEY = re.compile(r"^c-[a-z]([a-z0-9]*(-[a-z0-9]+)*)?$")
_NOTE_KEY = re.compile(r"^n-[a-z]([a-z0-9]*(-[a-z0-9]+)*)?$")


def instance_path(language: str, feature: str) -> str:
    return f"languages/{language}/instances/{feature}.yaml"


def _cited(evidence, *, what: str) -> list[dict]:
    if not evidence:
        raise UnsourcedNode(f"{what}: needs at least one (source, locator) (D4/§6.1)")
    return [e.as_entry() for e in evidence]


def _duplicates(keys) -> list[str]:
    seen, dupes = set(), []
    for key in keys:
        if key in seen:
            dupes.append(key)
        seen.add(key)
    return dupes


def _shape_errors(draft: InstanceDraft) -> list[str]:
    errors = []
    if draft.status not in STATUSES:
        errors.append(f"status {draft.status!r} is not one of {list(STATUSES)}")
    if draft.status == "absent":
        if not (draft.absence_scope or "").strip():
            errors.append("an absent instance needs an absence_scope (D49)")
        if draft.since or draft.characteristics or draft.syntax or draft.notes:
            errors.append("an absent instance describes nothing present: no since,"
                          " characteristics, syntax or notes")
    else:
        if not (draft.since or "").strip():
            errors.append("since is required on a present or partial instance (D65)")
        if draft.absence_scope:
            errors.append("absence_scope belongs to an absent instance only")
    if draft.notes and draft.status != "partial":
        errors.append("typed notes describe a partial instance only (§3.4)")
    for c in draft.characteristics:
        if not _CHARACTERISTIC_KEY.match(c.key):
            errors.append(f"characteristic key {c.key!r} must be c-<slug>")
    for n in draft.notes:
        if not _NOTE_KEY.match(n.key):
            errors.append(f"note key {n.key!r} must be n-<slug>")
    for s in draft.syntax:
        if not is_valid_slug(s.key):
            errors.append(f"syntax key {s.key!r} must be a slug (it becomes part of the"
                          f" syntax example's id)")
    for field, entries in (("characteristic", draft.characteristics), ("note", draft.notes),
                           ("syntax", draft.syntax)):
        for key in _duplicates(entry.key for entry in entries):
            errors.append(f"{field} key {key!r} appears twice")
    return errors


def render_instance(draft: InstanceDraft) -> MintedRecord:
    """@raises UnsourcedNode: a citation list is empty.
    @raises InvalidDraft: an invalid id, or a shape the status cannot carry."""
    try:
        instance_id = compose_instance_id(draft.language, draft.feature)
    except ValueError as exc:
        raise InvalidDraft(f"{draft.language!r} x {draft.feature!r}: {exc}") from exc
    errors = _shape_errors(draft)
    if errors:
        raise InvalidDraft(f"{instance_id}: " + "; ".join(errors))

    existence = _cited(draft.evidence, what=f"{instance_id}#exists")
    data = {"feature": draft.feature, "language": draft.language, "status": draft.status}
    if draft.status == "absent":
        data["absence_scope"] = draft.absence_scope
        data["sources"] = existence
    else:
        data["since"] = {"value": draft.since, "sources": existence}
    if draft.characteristics:
        data["characteristics"] = [
            {"key": c.key, "text": c.text,
             "sources": _cited(c.evidence, what=f"{instance_id}#characteristics[{c.key}]")}
            for c in draft.characteristics]
    if draft.notes:
        data["notes"] = [
            {"key": n.key, "type": n.type, "text": n.text,
             "sources": _cited(n.evidence, what=f"{instance_id}#notes[{n.key}]")}
            for n in draft.notes]
    if draft.syntax:
        data["syntax"] = [
            {"key": s.key, "title": s.title, "origin": s.origin, "code": s.code,
             "sources": _cited(s.evidence, what=f"{instance_id}#syntax[{s.key}]")}
            for s in draft.syntax]
    data["provenance"] = provenance_block(draft)
    return finish(data, path=instance_path(draft.language, draft.feature),
                  kind="feature-instance", node_ids=(instance_id,))
