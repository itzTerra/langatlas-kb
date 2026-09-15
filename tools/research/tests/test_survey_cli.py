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


def _survey_with_gap(cycle):
    return {"cycle": 1, "theme": "typing", "theme_digest": cycle.signed_off["theme_digest"],
            "generated_at": "2026-09-20T10:00:00Z",
            "runs": {"surveyor": "2026-09-20-r3-survey-01-typing-01"},
            "tagging": {"prompt": "p", "models": [], "chunks_tagged": 0, "chunks_relevant": 0},
            "pool": {"digest": "0123456789abcdef", "chunk_count": 0, "queries": []},
            "checklist": {"mirror_versions": {}, "gap_terms": []},
            "candidates": [], "unevidenced": [
                {"key": "gradual-typing", "name": "Gradual typing", "gloss": "g",
                 "origin": "prior", "search_hint": "h", "disposition": "open"}],
            "theme_amendments": [], "scouting": []}


def test_drop_gap_marks_it_dropped_with_the_given_reason(research_repo, signed_cycle, capsys):
    save_survey(_survey_with_gap(signed_cycle), repo_root=research_repo)

    code = main(["--repo-root", str(research_repo), "survey", "drop-gap", "1", "gradual-typing",
                "--reason", "no tier-A/B source after two scout runs"])

    assert code == 0
    out = capsys.readouterr().out
    assert "gradual-typing" in out and "01-typing" in out
    survey = load_survey("01-typing", repo_root=research_repo)
    assert survey["unevidenced"][0]["disposition"] == "dropped"
    assert "no tier-A/B source" in survey["unevidenced"][0]["search_hint"]


def test_drop_gap_refuses_an_unknown_or_already_decided_key(research_repo, signed_cycle):
    save_survey(_survey_with_gap(signed_cycle), repo_root=research_repo)

    assert main(["--repo-root", str(research_repo), "survey", "drop-gap", "1", "no-such-key",
                "--reason", "r"]) == 1
    assert main(["--repo-root", str(research_repo), "survey", "drop-gap", "1", "gradual-typing",
                "--reason", "r"]) == 0
    # already dropped now — a second attempt is refused, not silently re-applied
    assert main(["--repo-root", str(research_repo), "survey", "drop-gap", "1", "gradual-typing",
                "--reason", "r"]) == 1
