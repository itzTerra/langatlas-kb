"""R3's surveyor (Claude, judgment lane): the tagged term index plus the finding-aid
checklist in, an evidenced candidate inventory out.

The surveyor is kept a separate role from 3C's ontologist on purpose (§7.4): a session that
both harvests and carves will carve to match its own harvest. It gets the corpus and finding
aids as live pipeline-only tools and no built-in tools at all — no filesystem, no shell, no
web; gap-filling on the open web is the source scout's job, not this one's."""
from dataclasses import dataclass
from pathlib import Path

from langatlas_finding_aids.checklist import Checklist
from langatlas_pipeline.prompts import PromptRef, load_prompt
from langatlas_pipeline.transcripts.writer import utc_now
from langatlas_research.config import ResearchConfig
from langatlas_research.cycle import Cycle, require_sign_off
from langatlas_research.errors import PoolStale
from langatlas_research.survey.checklist import gap_terms, render_checklist
from langatlas_research.survey.chunks import ChunkLookup
from langatlas_research.survey.claude import run_structured
from langatlas_research.survey.index import (
    build_term_index, render_term_index, tagging_summary,
)
from langatlas_research.survey.inventory import BindReport, SurveyOut, bind_inventory, build_survey_record
from langatlas_research.survey.pool import Pool
from langatlas_research.themes import load_themes

SURVEYOR_PROMPT_ID = "r3-surveyor"


@dataclass(frozen=True)
class SurveyInputs:
    pool: Pool | None
    tags: list
    checklist: Checklist


def surveyor_tools(ctx, conn) -> tuple[dict, tuple[str, ...]]:
    from langatlas_finding_aids.tools import SERVER_NAME as AIDS_SERVER
    from langatlas_finding_aids.tools import TOOL_NAMES as AIDS_TOOLS
    from langatlas_finding_aids.tools import sdk_finding_aid_tools
    from langatlas_ingest.tools import SERVER_NAME as SOURCES_SERVER
    from langatlas_ingest.tools import TOOL_NAMES as SOURCE_TOOLS
    from langatlas_ingest.tools import sdk_source_tools

    servers = {SOURCES_SERVER: sdk_source_tools(ctx, conn), AIDS_SERVER: sdk_finding_aid_tools(ctx)}
    return servers, (*SOURCE_TOOLS, *AIDS_TOOLS)


def run_surveyor(ctx, cycle: Cycle, *, repo_root: Path | None, inputs: SurveyInputs,
                 lookup: ChunkLookup, config: ResearchConfig, mcp_servers: dict | None = None,
                 allowed_tools=(), prompt: PromptRef | None = None,
                 now: str | None = None) -> tuple[dict, BindReport]:
    """@raises SignOffMissing / SignOffStale / PoolStale: before any Claude message.
    @raises SurveyOutputInvalid: from the run or from binding."""
    require_sign_off(cycle, repo_root=repo_root)
    if inputs.pool is None or inputs.pool.theme_digest != cycle.signed_off["theme_digest"]:
        raise PoolStale(f"{cycle.slug}: the survey's pool does not match the signed-off theme"
                        f" digest {cycle.signed_off['theme_digest']}")
    themes = load_themes(repo_root)
    theme = themes[cycle.theme]
    min_relevance = config.tagger.min_relevance

    entries = build_term_index(inputs.tags, inputs.pool, min_relevance=min_relevance,
                               seed_terms=theme.seed_terms)
    variables = {
        "theme_label": theme.label, "theme_summary": theme.summary,
        "seed_terms": ", ".join(theme.seed_terms), "languages": ", ".join(cycle.languages),
        "other_themes": ", ".join(slug for slug in themes if slug != cycle.theme),
        "max_candidates": str(config.surveyor.max_candidates),
        "term_index": (render_term_index(ctx, entries, limit=config.surveyor.max_packet_terms)
                       or "(the tagging pass found no theme terms)"),
        "checklist": render_checklist(ctx, inputs.checklist),
    }
    out, _ = run_structured(ctx, prompt or load_prompt(SURVEYOR_PROMPT_ID), variables,
                            output_model=SurveyOut, role_config=config.surveyor,
                            mcp_servers=mcp_servers, allowed_tools=allowed_tools)
    report = bind_inventory(out, lookup=lookup, max_candidates=config.surveyor.max_candidates)
    for warning in report.warnings:
        ctx.writer.append(role="system", content=warning, flags=["r3:survey-warning"])

    data = build_survey_record(
        cycle=cycle, surveyor_run_id=ctx.run_id, generated_at=now or utc_now(),
        tagging=tagging_summary(inputs.tags, min_relevance=min_relevance),
        pool={"digest": inputs.pool.digest, "chunk_count": len(inputs.pool.entries),
              "queries": list(inputs.pool.queries)},
        checklist={"mirror_versions": dict(inputs.checklist.mirror_versions),
                   "gap_terms": gap_terms(inputs.checklist)},
        report=report)
    return data, report
