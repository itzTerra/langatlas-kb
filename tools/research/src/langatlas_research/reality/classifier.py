"""R5's reality checker (Claude, judgment lane): one sampled language against one theme's
compiled questionnaire slice.

A separate role from every R4 role on purpose: the ontologist drew the carves, so the session
testing whether a real language fits them must not be the one that drew them (§7.4 — no agent
grades its own harvest). It gets the corpus as live tools and no finding aids (D29/D53): every
answer here is a claim the D24 verifier will check, and a finding aid is never a citation.

Nothing the model types about identity is trusted. The cells it may answer are exactly the
instantiated items, and evidence is bound from chunk ids (3C's `bind_evidence`). A structurally
wrong output fails the session. An answer the corpus cannot back does not: that is an `unsourced`
cell, which is itself a finding. A present or partial answer must carry a `since` (D65), and the
checker is told which version each reference documents, because an as-of `since` must be that
version (D66)."""
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from langatlas_pipeline.prompts import PromptRef, load_prompt
from langatlas_questionnaire.spec import instantiate, select
from langatlas_research.config import ResearchConfig
from langatlas_research.cycle import Cycle, require_sign_off
from langatlas_research.draft.evidence import EvidenceItem, bind_evidence
from langatlas_research.errors import EvidenceUnresolvable, RealityOutputInvalid
from langatlas_research.reality.record import add_shakedown, cell_key, replace_language
from langatlas_research.rotation import LANGUAGE_NAMES
from langatlas_research.survey.chunks import ChunkLookup
from langatlas_research.survey.claude import run_structured
from langatlas_research.themes import load_themes
from langatlas_validate.ids import is_valid_slug

CLASSIFIER_PROMPT_ID = "r5-reality-checker"
CLASSIFIER_VARIABLES = ("language_id", "language_name", "theme_label", "references",
                        "max_characteristics", "max_syntax", "max_uncovered", "dimensions",
                        "items")

_CHARACTERISTIC_KEY = re.compile(r"^c-[a-z]([a-z0-9]*(-[a-z0-9]+)*)?$")
_NOTE_KEY = re.compile(r"^n-[a-z]([a-z0-9]*(-[a-z0-9]+)*)?$")


class CharacteristicOut(BaseModel):
    key: str
    text: str
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=3)


class NoteOut(BaseModel):
    key: str
    type: Literal["limitation", "extra", "alternative"]
    text: str
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=3)


class SyntaxOut(BaseModel):
    key: str
    title: str
    code: str
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=3)


class CellOut(BaseModel):
    feature: str
    mappable: bool = True
    answer: Literal["present", "absent", "partial"] | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=3)
    since: str | None = None
    absence_scope: str | None = None
    notes: list[NoteOut] = Field(default_factory=list)
    characteristics: list[CharacteristicOut] = Field(default_factory=list)
    syntax: list[SyntaxOut] = Field(default_factory=list)
    note: str = ""


class UncoveredOut(BaseModel):
    key: str
    name: str
    note: str
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=3)


class RealityOut(BaseModel):
    cells: list[CellOut]
    uncovered: list[UncoveredOut] = Field(default_factory=list)


def render_items(ctx, items: list[dict]) -> str:
    """The questionnaire, through D31's door: feature summaries are committed store text, but
    that text was model-written from documents, so it is data, never instructions."""
    lines = []
    for item in items:
        where = f", dimension {item['dimension']}" if item["dimension"] else ""
        lines.append(f"- feature: {item['feature']}  ({item['name']}, layer {item['layer']}"
                     f"{where})")
        lines.append(f"  definition: {item['summary']}")
        if item["aliases"]:
            lines.append(f"  also called: {', '.join(item['aliases'])}")
    return ctx.tool_result(tool="questionnaire", text="\n".join(lines),
                           kind="questionnaire-items")


def render_dimensions(ctx, groups: list[dict]) -> str:
    if not groups:
        return "(this theme has no layer-3 dimensions)"
    lines = [f"- {g['dimension']} ({g['label']}; {g['exclusivity']}): members"
             f" {', '.join(item['feature'] for item in g['items'])}" for g in groups]
    return ctx.tool_result(tool="questionnaire", text="\n".join(lines),
                           kind="questionnaire-dimensions")


def render_references(source_ids, source_facts: dict) -> str:
    """Plain text of our own making (source ids and versions from committed records), so it may
    sit in the system prompt."""
    if not source_ids:
        return "- none configured — search the whole corpus"
    lines = []
    for source_id in source_ids:
        facts = source_facts.get(source_id)
        version = getattr(facts, "language_version", "")
        lines.append(f"- {source_id} (documents version {version})" if version
                     else f"- {source_id} (unversioned: it cannot bound an as-of since)")
    return "\n".join(lines)


def _check_cell(cell: CellOut, config: ResearchConfig, errors: list[str]) -> None:
    where = f"cell {cell.feature}"
    if not cell.mappable:
        if cell.answer is not None or cell.evidence or cell.since:
            errors.append(f"{where}: an unmappable cell carries no answer, since or evidence")
        return
    if cell.answer is None:
        errors.append(f"{where}: a mappable cell needs an answer")
    if cell.answer == "absent":
        if not (cell.absence_scope or "").strip():
            errors.append(f"{where}: an absent answer needs an absence_scope (D49)")
        if cell.since or cell.characteristics or cell.syntax or cell.notes:
            errors.append(f"{where}: an absent answer describes nothing present")
    elif cell.answer is not None:
        if not (cell.since or "").strip():
            errors.append(f"{where}: a present or partial answer needs a since (D65)")
        if cell.absence_scope:
            errors.append(f"{where}: absence_scope belongs to absent answers only")
    if cell.notes and cell.answer != "partial":
        errors.append(f"{where}: typed notes belong to partial answers only")
    if len(cell.characteristics) > config.reality.max_characteristics:
        errors.append(f"{where}: more than {config.reality.max_characteristics}"
                      f" characteristic(s)")
    if len(cell.syntax) > config.reality.max_syntax:
        errors.append(f"{where}: more than {config.reality.max_syntax} syntax example(s)")
    for c in cell.characteristics:
        if not _CHARACTERISTIC_KEY.match(c.key):
            errors.append(f"{where}: characteristic key {c.key!r} must be c-<slug>")
    for n in cell.notes:
        if not _NOTE_KEY.match(n.key):
            errors.append(f"{where}: note key {n.key!r} must be n-<slug>")
    for s in cell.syntax:
        if not is_valid_slug(s.key):
            errors.append(f"{where}: syntax key {s.key!r} must be a slug")


def _check_shape(out: RealityOut, *, items: list[dict], config: ResearchConfig) -> None:
    """Every structural rule, checked at once so the developer reads one message naming all of
    them. Two members of an exclusive dimension both present is deliberately NOT here: that is a
    finding (Task 11), not a malformed answer."""
    errors: list[str] = []
    wanted = {item["feature"] for item in items}
    answered: dict[str, int] = {}
    for cell in out.cells:
        answered[cell.feature] = answered.get(cell.feature, 0) + 1
        if cell.feature not in wanted:
            errors.append(f"cell {cell.feature}: not a questionnaire item")
            continue
        _check_cell(cell, config, errors)
    for feature in sorted(wanted):
        if answered.get(feature, 0) != 1:
            errors.append(f"cell {feature}: answered {answered.get(feature, 0)} times; every"
                          f" item is answered exactly once")
    if len(out.uncovered) > config.reality.classifier.max_candidates:
        errors.append(f"{len(out.uncovered)} uncovered constructs exceed the cap of"
                      f" {config.reality.classifier.max_candidates}")
    for u in out.uncovered:
        if not is_valid_slug(u.key):
            errors.append(f"uncovered {u.key!r}: not a valid slug")
    if errors:
        raise RealityOutputInvalid(f"{CLASSIFIER_PROMPT_ID}: " + "; ".join(errors))


def _bind(items, *, lookup: ChunkLookup, what: str, warnings: list[str]) -> list[dict] | None:
    """Evidence entries, or None when not one lead resolves."""
    if not items:
        return None
    try:
        entries, notes = bind_evidence(items, lookup=lookup, what=what)
    except EvidenceUnresolvable:
        return None
    warnings.extend(notes)
    return entries


def _bind_cell(cell: CellOut, *, language: str, lookup: ChunkLookup, warnings: list[str],
               shakedown: list[tuple[str, str]]) -> dict:
    key = cell_key(language, cell.feature)
    entry = {"key": key, "language": language, "feature": cell.feature,
             "mappable": cell.mappable, "answer": cell.answer, "note": cell.note,
             "proposal": None, "status": "unmappable", "verification": None}
    if not cell.mappable:
        return entry
    sources = _bind(cell.evidence, lookup=lookup, what=f"{key}#exists", warnings=warnings)
    if sources is None:
        shakedown.append(("classifier", f"{key}: no existence evidence resolved to a corpus"
                                        f" chunk; the cell is unsourced"))
        return {**entry, "status": "unsourced"}

    proposal: dict = {"sources": sources}
    if cell.since:
        proposal["since"] = cell.since.strip()
    if cell.absence_scope:
        proposal["absence_scope"] = cell.absence_scope.strip()
    for field, rows, keep in (
            ("notes", cell.notes, lambda n: {"key": n.key, "type": n.type, "text": n.text}),
            ("characteristics", cell.characteristics,
             lambda c: {"key": c.key, "text": c.text}),
            ("syntax", cell.syntax, lambda s: {"key": s.key, "title": s.title, "code": s.code})):
        kept = []
        for row in rows:
            anchor = f"{key}#{field}[{row.key}]"
            row_sources = _bind(row.evidence, lookup=lookup, what=anchor, warnings=warnings)
            if row_sources is None:
                shakedown.append(("classifier", f"{anchor}: evidence did not resolve; dropped"))
                continue
            kept.append({**keep(row), "sources": row_sources})
        if kept:
            proposal[field] = kept
    return {**entry, "proposal": proposal, "status": "proposed"}


def run_classifier(ctx, cycle: Cycle, record: dict, spec: dict, *, language: str,
                   language_kind: str, repo_root: Path | None, lookup: ChunkLookup,
                   config: ResearchConfig, source_facts: dict | None = None,
                   mcp_servers: dict | None = None, allowed_tools=(),
                   prompt: PromptRef | None = None) -> tuple[dict, list[str]]:
    """Answer one sampled language's questionnaire and swap its answers into the record.

    @param source_facts: `{source id: SourceFacts}`; None loads the committed source records.
    @returns: `(updated record, binding warnings)`. The record is not saved.
    @raises SignOffMissing / SignOffStale: before any Claude message.
    @raises RealityOutputInvalid: a language outside the sample, an over-cap questionnaire, or
        output whose structure the rules above reject."""
    require_sign_off(cycle, repo_root=repo_root)
    if language not in cycle.languages:
        raise RealityOutputInvalid(f"{language!r} is not in cycle {cycle.slug}'s R5 sample"
                                   f" {list(cycle.languages)}")
    role = config.reality.classifier
    scoped = select(spec, record["scope"]["features"])
    items = instantiate(scoped, language, language_kind=language_kind)
    groups = [g for g in scoped["groups"]
              if g["kind"] == "dimension" and language_kind in g["applies_to"]]
    if len(items) > role.max_packet_terms:
        raise RealityOutputInvalid(
            f"{len(items)} questionnaire items exceed reality_check.classifier.max_packet_terms"
            f" ({role.max_packet_terms}); raise the cap or split the theme")
    if source_facts is None:
        from langatlas_ingest.verify.sources import load_source_facts

        source_facts = load_source_facts()

    prompt = prompt or load_prompt(CLASSIFIER_PROMPT_ID)
    sources = config.reality.language_sources.get(language, ())
    variables = {
        "language_id": language, "language_name": LANGUAGE_NAMES.get(language, language),
        "theme_label": load_themes(repo_root)[cycle.theme].label,
        "references": render_references(sources, source_facts),
        "max_characteristics": str(config.reality.max_characteristics),
        "max_syntax": str(config.reality.max_syntax),
        "max_uncovered": str(role.max_candidates),
        "dimensions": render_dimensions(ctx, groups),
        "items": render_items(ctx, items),
    }
    out, _ = run_structured(ctx, prompt, variables, output_model=RealityOut, role_config=role,
                            mcp_servers=mcp_servers, allowed_tools=allowed_tools)
    _check_shape(out, items=items, config=config)

    warnings: list[str] = []
    shakedown: list[tuple[str, str]] = []
    cells = [_bind_cell(cell, language=language, lookup=lookup, warnings=warnings,
                        shakedown=shakedown) for cell in out.cells]
    uncovered = []
    for u in out.uncovered:
        key = cell_key(language, u.key)
        evidence = _bind(u.evidence, lookup=lookup, what=f"{key}#uncovered", warnings=warnings)
        if evidence is None:
            shakedown.append(("classifier", f"{key}: uncovered construct with no resolvable"
                                            f" evidence; dropped"))
            continue
        uncovered.append({"key": key, "language": language, "name": u.name, "note": u.note,
                          "evidence": evidence})

    run = {"run_id": ctx.run_id, "prompt_version": prompt.version, "model": role.model or "claude"}
    updated = replace_language(record, language, cells=cells, uncovered=uncovered, run=run)
    if not sources:
        shakedown.append(("sources", f"{language}: no reference source is configured in"
                                     f" reality_check.language_sources, so every cell cites the"
                                     f" general corpus and no as-of since can be bounded"))
    for component, detail in shakedown:
        updated = add_shakedown(updated, component=component, detail=detail)
    for warning in warnings:
        ctx.writer.append(role="system", content=warning, flags=["r5:warning"])
    return updated, warnings
