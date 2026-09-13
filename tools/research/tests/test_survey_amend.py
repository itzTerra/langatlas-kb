import pytest

from langatlas_research.cycle import new_cycle
from langatlas_research.errors import AmendmentRefused
from langatlas_research.paths import themes_path
from langatlas_research.survey.amend import apply_amendment, mark_amendment, stale_cycles
from langatlas_research.themes import load_themes


def test_adding_a_theme_appends_it_and_keeps_comments(research_repo):
    stale = apply_amendment({"op": "add", "slug": "interop", "label": "Interoperability",
                             "summary": "Foreign-function interfaces and embedding.",
                             "seed_terms": ["foreign function interface"],
                             "rationale": "r", "status": "proposed"},
                            repo_root=research_repo)
    themes = load_themes(research_repo)
    assert list(themes)[-1] == "interop"
    assert themes["interop"].seed_terms == ("foreign function interface",)
    assert themes_path(research_repo).read_text().startswith("# The R3 theme list")
    assert stale == []


def test_editing_a_signed_theme_reopens_that_cycle_s_gate(research_repo, signed_cycle):
    assert stale_cycles(research_repo) == []
    stale = apply_amendment({"op": "edit", "slug": "typing",
                             "seed_terms": ["type system", "gradual typing"],
                             "rationale": "r", "status": "proposed"},
                            repo_root=research_repo)
    assert stale == ["01-typing"]
    assert [c.slug for c in stale_cycles(research_repo)] == ["01-typing"]
    assert load_themes(research_repo)["typing"].label == "Typing"


@pytest.mark.parametrize("amendment", [
    {"op": "add", "slug": "typing", "label": "T", "summary": "S"},
    {"op": "add", "slug": "interop", "label": "Interop"},
    {"op": "edit", "slug": "no-such-theme", "label": "X"},
    {"op": "remove", "slug": "no-such-theme"},
])
def test_malformed_amendments_are_refused_without_writing(research_repo, amendment):
    before = themes_path(research_repo).read_text()
    with pytest.raises(AmendmentRefused):
        apply_amendment({**amendment, "rationale": "r", "status": "proposed"},
                        repo_root=research_repo)
    assert themes_path(research_repo).read_text() == before


def test_a_theme_with_a_cycle_cannot_be_removed(research_repo):
    new_cycle(3, "modules", repo_root=research_repo, languages=("c",))
    with pytest.raises(AmendmentRefused, match="cycle"):
        apply_amendment({"op": "remove", "slug": "modules", "rationale": "r",
                         "status": "proposed"}, repo_root=research_repo)
    apply_amendment({"op": "remove", "slug": "metaprogramming", "rationale": "r",
                     "status": "proposed"}, repo_root=research_repo)
    assert "metaprogramming" not in load_themes(research_repo)


def test_an_already_decided_amendment_is_refused(research_repo):
    with pytest.raises(AmendmentRefused, match="proposed"):
        apply_amendment({"op": "edit", "slug": "typing", "label": "X", "rationale": "r",
                         "status": "applied"}, repo_root=research_repo)


def test_mark_amendment_returns_a_new_survey():
    survey = {"theme_amendments": [{"op": "edit", "slug": "typing", "rationale": "r",
                                    "status": "proposed"}]}
    marked = mark_amendment(survey, 0, "rejected")
    assert marked["theme_amendments"][0]["status"] == "rejected"
    assert survey["theme_amendments"][0]["status"] == "proposed"
