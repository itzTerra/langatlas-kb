import pytest

from langatlas_finding_aids.checklist import Checklist, ChecklistRow
from langatlas_finding_aids.config import FindingAidsConfig
from langatlas_pipeline.injection import is_delimited
from langatlas_research.cycle import new_cycle
from langatlas_research.errors import SignOffMissing
from langatlas_research.survey.checklist import (
    build_cycle_checklist, checklist_config_for, gap_terms, render_checklist,
)
from langatlas_research.themes import load_themes


def _checklist():
    return Checklist(theme="typing", label="Typing", generated_at="2026-09-20T00:00:00Z",
                     mirror_versions={"pldb": "abc1234"},
                     rows=(ChecklistRow(term="generics", language="python", aids=("pldb",),
                                        leads=({"source": "pldb", "label": "Python",
                                                "url": "https://pldb.io/python"},),
                                        covered_by=()),
                           ChecklistRow(term="subtyping", language="python", aids=(),
                                        leads=(), covered_by=("subtyping",)),
                           ChecklistRow(term="generics", language="haskell", aids=(),
                                        leads=(), covered_by=())))


def test_the_checklist_theme_comes_from_the_research_theme_and_cycle(research_repo,
                                                                     signed_cycle):
    theme = load_themes(research_repo)["typing"]
    config = checklist_config_for(theme, signed_cycle, FindingAidsConfig.load())
    assert config.theme("typing") == {"label": "Typing",
                                      "languages": ["python", "haskell"],
                                      "terms": list(theme.seed_terms),
                                      "wikipedia_titles": []}


def test_build_passes_the_derived_config_and_is_gated(fake_ctx, research_repo, signed_cycle):
    seen = {}

    def fake_build(ctx, slug, *, config, repo_root):
        seen.update(slug=slug, languages=config.theme(slug)["languages"], root=repo_root)
        return _checklist()

    result = build_cycle_checklist(fake_ctx, signed_cycle, repo_root=research_repo,
                                   base_config=FindingAidsConfig.load(), build=fake_build)
    assert result.theme == "typing"
    assert seen == {"slug": "typing", "languages": ["python", "haskell"],
                    "root": research_repo}

    unsigned = new_cycle(2, "modules", repo_root=research_repo, languages=("c",))
    with pytest.raises(SignOffMissing):
        build_cycle_checklist(fake_ctx, unsigned, repo_root=research_repo, build=fake_build)


def test_gap_terms_are_uncovered_terms_deduped():
    assert gap_terms(_checklist()) == ["generics"]


def test_the_rendered_checklist_leads_with_the_caveat_and_is_delimited(fake_ctx):
    rendered = render_checklist(fake_ctx, _checklist())
    assert rendered.startswith("Finding-aid results are LEADS")
    assert is_delimited(rendered)
