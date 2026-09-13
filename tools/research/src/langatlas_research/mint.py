"""Drafts -> validated, normalized record text at its §3.3 path.

Pure: nothing here writes a file or runs git. `land.py` owns landing, so a render can be
re-run after a rebase — which is how a shared-file mint (taxonomy.py) survives losing a
race without clobbering the winner."""
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.drafts import ConceptDraft, FeatureDraft
from langatlas_research.errors import InvalidDraft, UnsourcedNode
from langatlas_validate.ids import is_valid_slug
from langatlas_validate.normalize import normalize_record
from langatlas_validate.schema import validate_record


@dataclass(frozen=True)
class MintedRecord:
    """@param path: repo-relative record path (what `land_record` commits).
    @param text: normalized YAML, already schema-valid.
    @param kind: the `RECORD_KINDS` value this validated against.
    @param node_ids: the node ids this record introduces, for cycle bookkeeping.
    @param base_digest: for a shared-file mint, the SHA-256 of the file content this
        render was based on — `land_drafts` re-renders when it no longer matches. `None`
        for one-file-per-record mints, which have no read-modify-write hazard."""
    path: str
    text: str
    kind: str
    node_ids: tuple[str, ...]
    base_digest: str | None = None


def dump_yaml(data: dict) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def content_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def finish(data: dict, *, path: str, kind: str, node_ids: tuple[str, ...],
           base_digest: str | None = None) -> MintedRecord:
    """Shared tail of every record mint: validate, normalize, wrap.

    @raises InvalidDraft: with every schema and slug error the record has, at once —
        an agent fixing one error at a time burns a session per error."""
    errors = validate_record(data, kind)
    if errors:
        raise InvalidDraft(f"{path}: " + "; ".join(errors))
    text = normalize_record(dump_yaml(data), kind)
    return MintedRecord(path=path, text=text, kind=kind, node_ids=node_ids,
                        base_digest=base_digest)


def provenance_block(draft) -> dict:
    provenance = {"proposer": draft.proposer.as_dict(),
                  "claim_origin": draft.claim_origin,
                  "chat_run_id": draft.chat_run_id,
                  "candidate_source": draft.candidate_source}
    if draft.debate_id is not None:
        provenance["debate_id"] = draft.debate_id
    return provenance


def _fact_block(draft) -> dict:
    if not draft.evidence:
        raise UnsourcedNode(
            f"{draft.id}: a node needs at least one (source, locator) (D4/§6.1) — priors"
            f" steer where to look, they never make a fact")
    return {"text": draft.summary,
            "sources": [e.as_entry() for e in draft.evidence]}


def _require_id(draft) -> str:
    if not is_valid_slug(draft.id):
        raise InvalidDraft(f"{draft.id!r}: invalid slug/id (§3.5: [a-z0-9]+(-[a-z0-9]+)*,"
                           f" <=48 chars, no leading digit)")
    return draft.id


def render_draft(draft, *, repo_root: Path | None = None) -> MintedRecord:
    """@raises UnsourcedNode, InvalidDraft, DegenerateRule: per the draft's own rules.
    @raises TypeError: for an unknown draft type."""
    if isinstance(draft, FeatureDraft):
        return _render_feature(draft)
    if isinstance(draft, ConceptDraft):
        return _render_concept(draft)
    from langatlas_research.mint_edges import render_edge_like  # Task 7

    return render_edge_like(draft)


def _render_concept(draft: ConceptDraft) -> MintedRecord:
    node_id = _require_id(draft)
    data = {"id": node_id, "slug": draft.slug or node_id, "name": draft.name,
            "summary": _fact_block(draft), "provenance": provenance_block(draft)}
    if draft.excluded_rationale:
        data["excluded_rationale"] = draft.excluded_rationale
    return finish(data, path=f"concepts/{node_id}.yaml", kind="concept",
                  node_ids=(node_id,))


def _render_feature(draft: FeatureDraft) -> MintedRecord:
    node_id = _require_id(draft)
    data = {"id": node_id, "slug": draft.slug or node_id, "name": draft.name,
            "layer": draft.layer, "summary": _fact_block(draft),
            "provenance": provenance_block(draft)}
    if draft.dimension:
        data["dimension"] = draft.dimension
    if draft.cross_cutting:
        data["cross_cutting"] = True
    if draft.aliases:
        data["aliases"] = list(draft.aliases)
    if draft.realizes:
        data["realizes"] = list(draft.realizes)
    return finish(data, path=f"features/{node_id}.yaml", kind="feature",
                  node_ids=(node_id,))
