"""The finding-aid coverage checklist for one cycle, built from the research theme itself.

`research/themes.yaml` is the only theme list (plan design decision 1): the checklist's theme
entry is derived in memory from the signed-off theme and the cycle's language sample, rather
than kept as a second, drifting copy in `config/finding-aids.yaml`. The checklist stays
uncommitted (2E's decision); the survey records only its mirror versions and GAP terms."""
from dataclasses import replace
from pathlib import Path

from langatlas_finding_aids.checklist import Checklist, build_checklist
from langatlas_finding_aids.config import FindingAidsConfig
from langatlas_finding_aids.results import NON_CITABLE_CAVEAT
from langatlas_research.cycle import Cycle, require_sign_off
from langatlas_research.themes import Theme, load_themes


def checklist_config_for(theme: Theme, cycle: Cycle,
                         base: FindingAidsConfig) -> FindingAidsConfig:
    return replace(base, themes={theme.slug: {"label": theme.label,
                                              "languages": list(cycle.languages),
                                              "terms": list(theme.seed_terms),
                                              "wikipedia_titles": []}})


def build_cycle_checklist(ctx, cycle: Cycle, *, repo_root: Path | None,
                          base_config: FindingAidsConfig | None = None,
                          build=build_checklist) -> Checklist:
    """@raises SignOffMissing / SignOffStale: before any finding-aid query."""
    require_sign_off(cycle, repo_root=repo_root)
    theme = load_themes(repo_root)[cycle.theme]
    config = checklist_config_for(theme, cycle, base_config or FindingAidsConfig.load())
    return build(ctx, theme.slug, config=config, repo_root=repo_root)


def gap_terms(checklist: Checklist) -> list[str]:
    return sorted({row.term for row in checklist.rows if not row.covered_by})


def render_checklist(ctx, checklist: Checklist) -> str:
    """The caveat leads, outside the block (it is ours); the table is finding-aid content
    and goes through the D31 door."""
    block = ctx.tool_result(tool="r3-checklist", text=checklist.to_markdown(),
                            source_id="finding-aid:checklist", kind="finding-aid")
    return f"{NON_CITABLE_CAVEAT}\n\n{block}"
