"""Edge, quality-edge and rule rendering. Split from `mint.py` so neither file has to hold
both the node shapes and the id-canonicalization rules in one head."""
from langatlas_research.drafts import EdgeDraft, QualityEdgeDraft, RuleDraft
from langatlas_research.errors import DegenerateRule, InvalidDraft, UnsourcedNode
from langatlas_research.mint import MintedRecord, finish, provenance_block
from langatlas_validate.ids import (
    canonical_endpoints, canonical_when_all, compose_edge_id, compose_rule_id,
)

# D64: a 1-antecedent candidate is a degenerate case belonging in an edge type instead.
_DEGENERATE_TO_EDGE = {"requires": "requires", "forbids": "conflicts-with",
                       "warn": "influences"}


def render_edge_like(draft) -> MintedRecord:
    if isinstance(draft, EdgeDraft):
        return _render_edge(draft)
    if isinstance(draft, QualityEdgeDraft):
        return _render_quality_edge(draft)
    if isinstance(draft, RuleDraft):
        return _render_rule(draft)
    raise TypeError(f"not a draft this package knows how to render: {type(draft).__name__}")


def _sources(evidence, *, what: str) -> list[dict]:
    if not evidence:
        raise UnsourcedNode(f"{what}: an edge or rule needs at least one (source, locator)"
                            f" (D4/§6.1)")
    return [e.as_entry() for e in evidence]


def _render_edge(draft: EdgeDraft) -> MintedRecord:
    frm, to = draft.frm, draft.to
    try:
        if draft.type == "alternative-to":
            frm, to = canonical_endpoints(frm, to)
        edge_id = compose_edge_id(draft.type, frm, to)
    except ValueError as e:
        raise InvalidDraft(f"{draft.type} edge {frm!r}->{to!r}: {e}") from e
    data = {"id": edge_id, "type": draft.type, "from": frm, "to": to,
            "statement": {"text": draft.statement,
                          "sources": _sources(draft.evidence, what=edge_id)},
            "provenance": provenance_block(draft)}
    if draft.polarity is not None:
        data["polarity"] = draft.polarity
    return finish(data, path=f"edges/{frm}/{draft.type}--{to}.yaml", kind="edge",
                  node_ids=(edge_id,))


def _render_quality_edge(draft: QualityEdgeDraft) -> MintedRecord:
    try:
        edge_id = compose_edge_id("affects-quality", draft.frm, draft.to)
    except ValueError as e:
        raise InvalidDraft(f"affects-quality edge {draft.frm!r}->{draft.to!r}: {e}") from e
    if not draft.assessments:
        raise UnsourcedNode(f"{edge_id}: an affects-quality edge needs at least one"
                            f" assessment with evidence (D4/§6.1)")
    data = {"id": edge_id, "type": "affects-quality", "from": draft.frm, "to": draft.to,
            "assessments": [
                {"key": a.key, "assessor": a.assessor.as_dict(), "polarity": a.polarity,
                 "strength": a.strength, "statement": a.statement,
                 "sources": _sources(a.evidence, what=f"{edge_id}[{a.key}]")}
                for a in draft.assessments],
            "provenance": provenance_block(draft)}
    return finish(data, path=f"edges/{draft.frm}/affects-quality--{draft.to}.yaml",
                  kind="affects-quality-edge", node_ids=(edge_id,))


def _render_rule(draft: RuleDraft) -> MintedRecord:
    try:
        rule_id = compose_rule_id(draft.slug)
    except ValueError as e:
        raise InvalidDraft(f"rule slug {draft.slug!r}: {e}") from e
    if len(draft.when_all) < 2:
        raise DegenerateRule(
            f"{rule_id}: a Rule needs >=2 antecedents (D64). A 1-antecedent"
            f" `{draft.effect}` interaction belongs in a"
            f" `{_DEGENERATE_TO_EDGE.get(draft.effect, 'matching')}` edge instead.")
    try:
        when_all = canonical_when_all(list(draft.when_all))
    except ValueError as e:
        raise InvalidDraft(f"{rule_id}: {e}") from e
    data = {"id": rule_id, "when_all": when_all,
            "effect": draft.effect, "then": list(draft.then), "message": draft.message,
            "sources": _sources(draft.evidence, what=rule_id),
            "provenance": provenance_block(draft)}
    return finish(data, path=f"rules/{rule_id}.yaml", kind="rule", node_ids=(rule_id,))
