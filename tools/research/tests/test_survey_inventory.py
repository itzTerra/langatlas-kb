import pytest

from langatlas_research.errors import SurveyOutputInvalid
from langatlas_research.survey.chunks import ChunkRef
from langatlas_research.survey.inventory import (
    SurveyOut, bind_inventory, build_survey_record, drop_gap, load_survey, save_survey,
    survey_path,
)

REAL = {"tapl#c00012": ChunkRef(chunk_id="tapl#c00012", source_id="tapl", locator="p. 317",
                                breadcrumb="Ch 22", content_hash="h", text="..."),
        "ctm#c00400": ChunkRef(chunk_id="ctm#c00400", source_id="vanroy-haridi-2003",
                               locator="pp. 44–45", breadcrumb="Ch 2", content_hash="h",
                               text="...")}


def _out(**overrides):
    candidate = {"key": "type-inference", "name": "Type inference",
                 "gloss": "Reconstructing types without annotations.", "kind_hint": "feature",
                 "origin": "corpus", "evidence_chunk_ids": ["tapl#c00012"],
                 "aliases": [{"label": "type reconstruction", "chunk_id": "ctm#c00400"}]}
    data = {"candidates": [{**candidate, **overrides}], "unevidenced": [],
            "theme_amendments": []}
    return SurveyOut.model_validate(data)


def test_evidence_locators_come_from_the_database_not_the_model():
    report = bind_inventory(_out(), lookup=REAL.get, max_candidates=10)
    assert report.candidates[0]["evidence"] == [
        {"chunk_id": "tapl#c00012", "source_id": "tapl", "locator": "p. 317"}]
    assert report.warnings == []


def test_unresolvable_ids_are_dropped_and_a_fully_unresolved_candidate_is_demoted():
    partial = bind_inventory(_out(evidence_chunk_ids=["tapl#c00012", "made#up"]),
                             lookup=REAL.get, max_candidates=10)
    assert [e["chunk_id"] for e in partial.candidates[0]["evidence"]] == ["tapl#c00012"]
    assert any("made#up" in w for w in partial.warnings)

    demoted = bind_inventory(_out(evidence_chunk_ids=["made#up"]), lookup=REAL.get,
                             max_candidates=10)
    assert demoted.candidates == []
    assert demoted.unevidenced[0]["key"] == "type-inference"
    assert demoted.unevidenced[0]["disposition"] == "open"
    assert "made#up" in demoted.unevidenced[0]["search_hint"]


def test_aliases_equal_to_the_name_or_repeated_are_dropped():
    report = bind_inventory(_out(aliases=[{"label": "TYPE  inference"},
                                          {"label": "type reconstruction"},
                                          {"label": "Type Reconstruction"},
                                          {"label": "HM inference", "chunk_id": "made#up"}]),
                            lookup=REAL.get, max_candidates=10)
    assert report.candidates[0]["aliases"] == [{"label": "type reconstruction"},
                                               {"label": "HM inference"}]


def test_a_bad_slug_a_duplicate_key_or_too_many_candidates_is_refused():
    with pytest.raises(SurveyOutputInvalid):
        bind_inventory(_out(key="Type_Inference"), lookup=REAL.get, max_candidates=10)
    duplicated = SurveyOut.model_validate({
        "candidates": [_out().candidates[0].model_dump()],
        "unevidenced": [{"key": "type-inference", "name": "x", "gloss": "y",
                         "origin": "prior", "search_hint": "z"}],
        "theme_amendments": []})
    with pytest.raises(SurveyOutputInvalid):
        bind_inventory(duplicated, lookup=REAL.get, max_candidates=10)
    with pytest.raises(SurveyOutputInvalid):
        bind_inventory(_out(), lookup=REAL.get, max_candidates=0)


def test_amendments_are_recorded_as_proposed_without_empty_fields():
    out = SurveyOut.model_validate({
        "candidates": [], "unevidenced": [],
        "theme_amendments": [{"op": "edit", "slug": "typing",
                              "seed_terms": ["gradual typing"], "rationale": "r"}]})
    report = bind_inventory(out, lookup=REAL.get, max_candidates=10)
    assert report.theme_amendments == [{"op": "edit", "slug": "typing",
                                        "seed_terms": ["gradual typing"], "rationale": "r",
                                        "status": "proposed"}]


def test_a_survey_record_round_trips_through_its_schema(research_repo, signed_cycle):
    report = bind_inventory(_out(), lookup=REAL.get, max_candidates=10)
    data = build_survey_record(
        cycle=signed_cycle, surveyor_run_id="2026-09-20-r3-survey-01-typing-01",
        generated_at="2026-09-20T10:00:00Z",
        tagging={"prompt": "r3-tagger@v-00000001", "models": ["deepseek-v4-pro"],
                 "chunks_tagged": 1, "chunks_relevant": 1},
        pool={"digest": "0123456789abcdef", "chunk_count": 1, "queries": ["Typing"]},
        checklist={"mirror_versions": {}, "gap_terms": []}, report=report)

    path = save_survey(data, repo_root=research_repo)

    assert path == survey_path("01-typing", research_repo)
    assert load_survey("01-typing", repo_root=research_repo) == data
    assert data["theme_digest"] == signed_cycle.signed_off["theme_digest"]


def test_saving_an_invalid_survey_is_refused(research_repo):
    with pytest.raises(SurveyOutputInvalid):
        save_survey({"cycle": 1, "theme": "typing"}, repo_root=research_repo)


def test_drop_gap_marks_the_named_gap_dropped_and_notes_the_reason():
    survey = {"unevidenced": [
        {"key": "gradual-typing", "name": "Gradual typing", "gloss": "g", "origin": "prior",
         "search_hint": "Siek & Taha 2006", "disposition": "open"},
        {"key": "soft-typing", "name": "Soft typing", "gloss": "s", "origin": "prior",
         "search_hint": "h", "disposition": "open"}]}

    updated = drop_gap(survey, "gradual-typing", "no tier-A/B source found after two scout runs")

    assert updated["unevidenced"][0]["disposition"] == "dropped"
    assert "no tier-A/B source found" in updated["unevidenced"][0]["search_hint"]
    assert updated["unevidenced"][1]["disposition"] == "open"
    # pure function: the original is untouched
    assert survey["unevidenced"][0]["disposition"] == "open"


def test_drop_gap_refuses_an_unknown_key():
    with pytest.raises(KeyError):
        drop_gap({"unevidenced": []}, "no-such-key", "reason")
