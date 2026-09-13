"""R3's source scout (§7.4, brainstorm 25 §O5): Claude for the judgment of what literature
would evidence a gap, code for everything mechanical — dedup against committed sources and
the open sourcing queue, the finding-aid ban, and filing.

Nothing the scout finds is citable (§4.4): it files `pending-source` entries and records its
proposals in the survey; a human ingests a proposal as a real `sources/*.yaml` record through
`langatlas-sources new-source` + `ingest`, and only then can a claim cite it. The scout is the
one role with web built-ins; its fetched pages are scanned and logged by the Claude channel's
tool-result handling (D31's ratified "retrofit before relied on heavily" posture)."""
import json
import shlex
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from langatlas_pipeline.prompts import PromptRef, load_prompt
from langatlas_research.config import ResearchConfig
from langatlas_research.cycle import Cycle, require_sign_off
from langatlas_research.errors import R3Incomplete, SurveyOutputInvalid
from langatlas_research.survey.claude import run_structured
from langatlas_research.themes import load_themes
from langatlas_validate.ids import is_valid_slug

SCOUT_PROMPT_ID = "r3-scout"
WEB_TOOLS = ("WebSearch", "WebFetch")
FINDING_AID_HOSTS = ("wikipedia.org", "wikidata.org", "pldb.io", "pldb.info",
                     "hyperpolyglot.org")
QUEUE_REASONS = {"open": "not-ingested", "paywalled": "paywalled",
                 "access-pending": "access-pending"}
_yaml = YAML(typ="safe")


class ProposalOut(BaseModel):
    source_id: str
    title: str
    csl_type: str
    url: str | None = None
    doi: str | None = None
    issued_year: int | None = None
    authors: list[str] = Field(default_factory=list)
    tier: Literal["A", "B", "C"]
    grounding: Literal["formal-spec", "reference-implementation-docs", "design-doc",
                       "third-party-reference"]
    access: Literal["open", "paywalled", "access-pending"]
    candidate_keys: list[str] = Field(min_length=1)
    rationale: str


class DroppedOut(BaseModel):
    key: str
    reason: str


class ScoutOut(BaseModel):
    proposals: list[ProposalOut]
    dropped: list[DroppedOut] = Field(default_factory=list)


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}"


def _host(url: str | None) -> str:
    """Extract the bare hostname from a URL, hardened against D29 finding-aid bypasses:
    schemeless URLs, a trailing DNS dot (plain or percent-encoded), userinfo, and port
    suffixes. `.hostname` (unlike `.netloc`) already strips userinfo/port and lowercases;
    `unquote` collapses percent-encoding (e.g. a trailing '%2e') before the dot is stripped.
    """
    if not url:
        return ""
    parsed = urlsplit(url if "//" in url else "https://" + url)
    return unquote(parsed.hostname or "").rstrip(".")


def existing_source_index(repo_root: Path | None) -> dict:
    index = {"ids": set(), "urls": {}, "dois": {}}
    directory = Path(repo_root) / "sources" if repo_root else None
    if directory is None or not directory.exists():
        return index
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        data = _yaml.load(path.read_text()) or {}
        source_id = data.get("id", path.stem)
        index["ids"].add(source_id)
        if data.get("URL"):
            index["urls"][normalize_url(data["URL"])] = source_id
        if data.get("DOI"):
            index["dois"][data["DOI"].strip().lower()] = source_id
    return index


def _entry(proposal: ProposalOut, status: str, rejection: str | None = None) -> dict:
    entry = {key: value for key, value in proposal.model_dump().items()
             if value not in (None, [])}
    entry["candidate_keys"] = list(proposal.candidate_keys)
    entry["status"] = status
    if rejection:
        entry["rejection"] = rejection
    return entry


def screen_proposals(proposals, *, repo_root: Path | None, open_queue_ids: set[str],
                     candidate_keys: set[str], max_proposals: int) -> list[dict]:
    """@raises SurveyOutputInvalid: more proposals than the configured cap."""
    if len(proposals) > max_proposals:
        raise SurveyOutputInvalid(
            f"{len(proposals)} source proposals exceeds the configured cap of {max_proposals}")
    index = existing_source_index(repo_root)
    batch_ids: dict[str, str] = {}
    entries = []
    for proposal in proposals:
        url_key = normalize_url(proposal.url) if proposal.url else None
        doi_key = proposal.doi.strip().lower() if proposal.doi else None
        if not url_key and not doi_key:
            entries.append(_entry(proposal, "rejected",
                                  "no resolvable bibliographic identifier (url or doi)"))
        elif (host := _host(proposal.url)) and any(
                host == aid or host.endswith("." + aid) for aid in FINDING_AID_HOSTS):
            entries.append(_entry(proposal, "rejected",
                                  "finding aids are never citations (D29/D53)"))
        elif not is_valid_slug(proposal.source_id):
            entries.append(_entry(proposal, "rejected",
                                  f"source_id {proposal.source_id!r} is not a valid slug"))
        elif not set(proposal.candidate_keys) <= candidate_keys:
            unknown = sorted(set(proposal.candidate_keys) - candidate_keys)
            entries.append(_entry(proposal, "rejected",
                                  f"names no unevidenced candidate: {', '.join(unknown)}"))
        elif (existing := (proposal.source_id if proposal.source_id in index["ids"] else None)
              or index["dois"].get(doi_key) or index["urls"].get(url_key)):
            entries.append(_entry(proposal, "duplicate", f"already a source: {existing}"))
        elif proposal.source_id in open_queue_ids:
            entries.append(_entry(proposal, "duplicate", "already pending in sourcing_queue"))
        elif (earlier := batch_ids.get(proposal.source_id) or batch_ids.get(url_key or "")
              or batch_ids.get(doi_key or "")):
            entries.append(_entry(proposal, "duplicate", f"repeats proposal {earlier}"))
        else:
            entries.append(_entry(proposal, "filed"))
        if entries[-1]["status"] == "filed":
            for key in (proposal.source_id, url_key, doi_key):
                if key:
                    batch_ids[key] = proposal.source_id
    return entries


def file_proposals(entries: list[dict], *, queue, cycle_slug: str) -> list[dict]:
    filed = []
    for entry in entries:
        entry = dict(entry)
        if entry["status"] == "filed":
            detail = json.dumps({"cycle": cycle_slug, "title": entry["title"],
                                 "url": entry.get("url"), "doi": entry.get("doi"),
                                 "candidate_keys": entry["candidate_keys"]}, sort_keys=True)
            entry["queue_entry_id"] = queue.file(kind="pending-source",
                                                 source_id=entry["source_id"],
                                                 reason=QUEUE_REASONS[entry["access"]],
                                                 detail=detail)
        filed.append(entry)
    return filed


def apply_scouting(survey: dict, entries: list[dict], dropped, scout_run_id: str) -> dict:
    scouted = {key for entry in entries if entry["status"] in ("filed", "duplicate")
               for key in entry["candidate_keys"]}
    dropped_keys = {item.key for item in dropped}
    unevidenced = []
    for gap in survey["unevidenced"]:
        gap = dict(gap)
        if gap["disposition"] == "open" and gap["key"] in dropped_keys:
            gap["disposition"] = "dropped"
        elif gap["disposition"] == "open" and gap["key"] in scouted:
            gap["disposition"] = "scouted"
        unevidenced.append(gap)
    return {**survey, "runs": {**survey["runs"], "scout": scout_run_id},
            "unevidenced": unevidenced, "scouting": [*survey["scouting"], *entries]}


def _existing_sources_text(repo_root: Path | None) -> str:
    directory = Path(repo_root) / "sources" if repo_root else None
    if directory is None or not directory.exists():
        return "(none)"
    lines = []
    for path in sorted(directory.glob("*.yaml")):
        if not path.name.startswith("_"):
            data = _yaml.load(path.read_text()) or {}
            lines.append(f"- {data.get('id', path.stem)} — {data.get('title', '')}")
    return "\n".join(lines) or "(none)"


def run_scout(ctx, cycle: Cycle, survey: dict, *, repo_root: Path | None,
              config: ResearchConfig, queue, mcp_servers: dict | None = None,
              allowed_tools=(), prompt: PromptRef | None = None) -> dict:
    """@raises SignOffMissing / SignOffStale: D27, before any Claude message.
    @raises R3Incomplete: the survey was produced under an earlier sign-off.
    @returns: the updated survey record (unsaved); unchanged when nothing is open."""
    require_sign_off(cycle, repo_root=repo_root)
    if survey["theme_digest"] != cycle.signed_off["theme_digest"]:
        raise R3Incomplete(f"{cycle.slug}: the survey predates the current sign-off —"
                           f" re-run `langatlas-research survey run {cycle.number}` first")
    gaps = [gap for gap in survey["unevidenced"]
            if gap["disposition"] == "open"][:config.scout.max_packet_terms]
    if not gaps:
        ctx.writer.append(role="system", content=f"{cycle.slug}: no open gaps to scout",
                          flags=["r3:scout-noop"])
        return survey

    gap_text = "\n".join(f"- {gap['key']}: {gap['name']} — {gap['gloss']}"
                         f" (hint: {gap['search_hint']})" for gap in gaps)
    variables = {
        "theme_label": load_themes(repo_root)[cycle.theme].label,
        # Surveyor output quoting document-derived hints: delimited like any other.
        "gaps": ctx.tool_result(tool="r3-survey-gaps", text=gap_text, kind="survey-gaps"),
        "existing_sources": _existing_sources_text(repo_root),
        "max_proposals": str(config.scout.max_candidates),
    }
    out, _ = run_structured(ctx, prompt or load_prompt(SCOUT_PROMPT_ID), variables,
                            output_model=ScoutOut, role_config=config.scout,
                            mcp_servers=mcp_servers,
                            allowed_tools=(*allowed_tools, *WEB_TOOLS),
                            builtin_tools=WEB_TOOLS)
    open_ids = {entry["source_id"] for entry in queue.open_entries(kind="pending-source")}
    entries = screen_proposals(out.proposals, repo_root=repo_root, open_queue_ids=open_ids,
                               candidate_keys={gap["key"] for gap in gaps},
                               max_proposals=config.scout.max_candidates)
    for entry in entries:
        if entry["status"] != "filed":
            ctx.writer.append(role="system", flags=["r3:scout-not-filed"],
                              content=f"{entry['source_id']}: {entry['status']} —"
                                      f" {entry.get('rejection', '')}")
    entries = file_proposals(entries, queue=queue, cycle_slug=cycle.slug)
    return apply_scouting(survey, entries, out.dropped, ctx.run_id)


def new_source_command(entry: dict) -> str:
    parts = ["uv", "--directory", "tools/ingest", "run", "langatlas-sources", "new-source",
             entry["source_id"], entry["csl_type"], entry["title"],
             "--tier", entry["tier"], "--grounding", entry["grounding"]]
    if entry.get("url"):
        parts += ["--url", entry["url"]]
    if entry.get("doi"):
        parts += ["--doi", entry["doi"]]
    if entry.get("issued_year"):
        parts += ["--issued-year", str(entry["issued_year"])]
    if entry.get("authors"):
        parts += ["--author", *entry["authors"]]
    return shlex.join(parts)
