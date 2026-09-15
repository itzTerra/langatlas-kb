"""The candidate inventory: what the surveyor said, bound to what the corpus actually holds.

The surveyor names evidence by chunk id only. Source ids and locators are copied from
`source_chunks` here (§4.3: machine-produced, never re-derived), so a survey can never carry a
locator the model typed. A hallucinated chunk id costs its candidate the evidence, not the
whole run: a candidate left with none is demoted to `unevidenced`, which is exactly the list
the source scout works from."""
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from langatlas_research.cycle import Cycle
from langatlas_research.errors import SurveyOutputInvalid
from langatlas_research.paths import surveys_dir
from langatlas_research.schema import validate_research_record
from langatlas_research.survey.chunks import ChunkLookup
from langatlas_research.survey.tagger import normalize_term
from langatlas_validate.ids import is_valid_slug

Origin = Literal["corpus", "seed-term", "finding-aid-gap", "prior"]
_yaml = YAML(typ="safe")


class AliasOut(BaseModel):
    label: str
    chunk_id: str | None = None


class CandidateOut(BaseModel):
    key: str
    name: str
    gloss: str
    kind_hint: Literal["concept", "feature", "unsure"]
    origin: Origin
    evidence_chunk_ids: list[str] = Field(min_length=1, max_length=3)
    aliases: list[AliasOut] = Field(default_factory=list)


class UnevidencedOut(BaseModel):
    key: str
    name: str
    gloss: str
    origin: Origin
    search_hint: str


class AmendmentOut(BaseModel):
    op: Literal["add", "edit", "remove"]
    slug: str
    label: str | None = None
    summary: str | None = None
    seed_terms: list[str] | None = None
    rationale: str


class SurveyOut(BaseModel):
    candidates: list[CandidateOut]
    unevidenced: list[UnevidencedOut] = Field(default_factory=list)
    theme_amendments: list[AmendmentOut] = Field(default_factory=list)


@dataclass
class BindReport:
    candidates: list[dict] = field(default_factory=list)
    unevidenced: list[dict] = field(default_factory=list)
    theme_amendments: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _check_keys(out: SurveyOut, max_candidates: int) -> None:
    if len(out.candidates) > max_candidates:
        raise SurveyOutputInvalid(
            f"{len(out.candidates)} candidates exceeds the configured cap of {max_candidates}")
    seen: set[str] = set()
    for entry in [*out.candidates, *out.unevidenced]:
        if not is_valid_slug(entry.key):
            raise SurveyOutputInvalid(f"candidate key {entry.key!r} is not a valid slug")
        if entry.key in seen:
            raise SurveyOutputInvalid(f"candidate key {entry.key!r} appears twice")
        seen.add(entry.key)


def _aliases(candidate: CandidateOut, lookup: ChunkLookup, warnings: list[str]) -> list[dict]:
    seen = {normalize_term(candidate.name)}
    aliases = []
    for alias in candidate.aliases:
        label = " ".join(alias.label.split())
        if not label or normalize_term(label) in seen:
            continue
        seen.add(normalize_term(label))
        entry = {"label": label}
        if alias.chunk_id:
            if lookup(alias.chunk_id) is not None:
                entry["chunk_id"] = alias.chunk_id
            else:
                warnings.append(f"{candidate.key}: alias {label!r} cites unresolvable"
                                f" chunk {alias.chunk_id}; kept the label only")
        aliases.append(entry)
    return aliases


def bind_inventory(out: SurveyOut, *, lookup: ChunkLookup, max_candidates: int) -> BindReport:
    """@raises SurveyOutputInvalid: bad slug, duplicate key, or over the candidate cap."""
    _check_keys(out, max_candidates)
    report = BindReport()
    for candidate in out.candidates:
        evidence, unresolved = [], []
        for chunk_id in dict.fromkeys(candidate.evidence_chunk_ids):
            ref = lookup(chunk_id)
            if ref is None:
                unresolved.append(chunk_id)
            else:
                evidence.append(ref.as_evidence())
        if unresolved:
            report.warnings.append(f"{candidate.key}: evidence chunk ids did not resolve:"
                                   f" {', '.join(unresolved)}")
        if not evidence:
            report.unevidenced.append({
                "key": candidate.key, "name": candidate.name, "gloss": candidate.gloss,
                "origin": candidate.origin, "disposition": "open",
                "search_hint": f"surveyor cited evidence chunk ids that did not resolve:"
                               f" {', '.join(unresolved)}"})
            continue
        report.candidates.append({
            "key": candidate.key, "name": candidate.name, "gloss": candidate.gloss,
            "kind_hint": candidate.kind_hint, "origin": candidate.origin,
            "evidence": evidence, "aliases": _aliases(candidate, lookup, report.warnings)})
    for entry in out.unevidenced:
        report.unevidenced.append({**entry.model_dump(), "disposition": "open"})
    for amendment in out.theme_amendments:
        report.theme_amendments.append(
            {**amendment.model_dump(exclude_none=True), "status": "proposed"})
    return report


def survey_path(cycle_slug: str, repo_root: Path | None = None) -> Path:
    return surveys_dir(repo_root) / f"{cycle_slug}.yaml"


def build_survey_record(*, cycle: Cycle, surveyor_run_id: str, generated_at: str,
                        tagging: dict, pool: dict, checklist: dict,
                        report: BindReport) -> dict:
    return {"cycle": cycle.number, "theme": cycle.theme,
            "theme_digest": cycle.signed_off["theme_digest"], "generated_at": generated_at,
            "runs": {"surveyor": surveyor_run_id}, "tagging": dict(tagging),
            "pool": dict(pool), "checklist": dict(checklist),
            "candidates": report.candidates, "unevidenced": report.unevidenced,
            "theme_amendments": report.theme_amendments, "scouting": []}


def render_survey(data: dict) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def save_survey(data: dict, *, repo_root: Path | None = None) -> Path:
    """@raises SurveyOutputInvalid: when the record does not satisfy survey.schema.json."""
    errors = validate_research_record(data, "survey", repo_root=repo_root)
    if errors:
        raise SurveyOutputInvalid("survey record is invalid: " + "; ".join(errors))
    path = survey_path(f"{data['cycle']:02d}-{data['theme']}", repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_survey(data))
    return path


def load_survey(cycle_slug: str, *, repo_root: Path | None = None) -> dict:
    """@raises FileNotFoundError: no survey for this cycle yet."""
    return _yaml.load(survey_path(cycle_slug, repo_root).read_text())


def drop_gap(survey: dict, key: str, reason: str) -> dict:
    """Developer-only escape hatch for a gap the scout could never close (every proposal it
    tried was screened out, or the model never volunteered a `dropped` entry) — the only other
    way `unevidenced[*].disposition` leaves `open` is `apply_scouting`, which needs a scout run
    to have actually filed or dropped something. Mirrors `mark_amendment`: a pure function over
    a copy, no I/O.

    @raises KeyError: no unevidenced entry with this key."""
    entries = []
    found = False
    for gap in survey["unevidenced"]:
        gap = dict(gap)
        if gap["key"] == key:
            found = True
            gap["disposition"] = "dropped"
            gap["search_hint"] = f"{gap['search_hint']} [developer drop: {reason}]"
        entries.append(gap)
    if not found:
        raise KeyError(f"no unevidenced candidate {key!r} in this survey")
    return {**survey, "unevidenced": entries}
