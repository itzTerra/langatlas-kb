from langatlas_research.cli import main
from langatlas_research.survey.inventory import load_survey, save_survey


def _survey_with_amendment(cycle):
    return {"cycle": 1, "theme": "typing", "theme_digest": cycle.signed_off["theme_digest"],
            "generated_at": "2026-09-20T10:00:00Z",
            "runs": {"surveyor": "2026-09-20-r3-survey-01-typing-01"},
            "tagging": {"prompt": "p", "models": [], "chunks_tagged": 0, "chunks_relevant": 0},
            "pool": {"digest": "0123456789abcdef", "chunk_count": 0, "queries": []},
            "checklist": {"mirror_versions": {}, "gap_terms": []},
            "candidates": [], "unevidenced": [],
            "theme_amendments": [{"op": "edit", "slug": "typing",
                                  "seed_terms": ["gradual typing"], "rationale": "r",
                                  "status": "proposed"},
                                 {"op": "add", "slug": "interop", "label": "Interop",
                                  "summary": "FFI.", "rationale": "r",
                                  "status": "proposed"}],
            "scouting": []}


def test_amend_applies_marks_and_reports_the_reopened_gate(research_repo, signed_cycle,
                                                           capsys):
    save_survey(_survey_with_amendment(signed_cycle), repo_root=research_repo)

    assert main(["--repo-root", str(research_repo), "themes", "amend", "1", "0"]) == 0

    out = capsys.readouterr().out
    assert "01-typing" in out and "sign-off" in out
    assert load_survey("01-typing", repo_root=research_repo)[
        "theme_amendments"][0]["status"] == "applied"


def test_amend_reject_changes_nothing_but_the_status(research_repo, signed_cycle):
    save_survey(_survey_with_amendment(signed_cycle), repo_root=research_repo)

    assert main(["--repo-root", str(research_repo), "themes", "amend", "1", "1",
                 "--reject"]) == 0

    survey = load_survey("01-typing", repo_root=research_repo)
    assert survey["theme_amendments"][1]["status"] == "rejected"
    assert main(["--repo-root", str(research_repo), "themes", "amend", "1", "1"]) == 1


def test_cycle_status_flags_a_stale_sign_off(research_repo, signed_cycle, capsys):
    save_survey(_survey_with_amendment(signed_cycle), repo_root=research_repo)
    main(["--repo-root", str(research_repo), "themes", "amend", "1", "0"])
    capsys.readouterr()

    assert main(["--repo-root", str(research_repo), "cycle", "status", "1"]) == 0
    assert "STALE" in capsys.readouterr().out
