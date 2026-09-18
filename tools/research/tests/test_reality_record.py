"""The reality-check file: shape, scope, per-language replacement, and the shakedown log."""
import pytest

from langatlas_research.config import ResearchConfig
from langatlas_research.errors import RealityCheckMissing, RealityOutputInvalid
from langatlas_research.paths import research_config_path
from langatlas_research.reality.record import (
    add_shakedown, cell_key, close_shakedown, find_cell, load_record, open_shakedown,
    reality_rel, replace_language, save_record, set_cell,
)
from langatlas_research.schema import validate_research_tree


def test_a_new_record_is_scoped_to_the_themes_slice(r5_record, signed_cycle):
    assert r5_record["scope"] == {
        "features": ["dynamic-typing", "static-typing", "type-inference"],
        "dimensions": ["type-checking-discipline"]}
    assert r5_record["theme_digest"] == signed_cycle.signed_off["theme_digest"]
    assert r5_record["ontology_version"] == "0.4.0"
    assert r5_record["runs"] == {"classify": {}, "verify": None}
    assert r5_record["summary"]["cells"] == 0


def test_a_record_saves_at_its_path_and_validates_as_research_bookkeeping(r5_record,
                                                                          research_repo):
    path = save_record(r5_record, repo_root=research_repo)
    assert path == research_repo / reality_rel("01-typing")
    assert load_record("01-typing", repo_root=research_repo) == r5_record
    assert validate_research_tree(research_repo) == []


def test_loading_before_compile_says_what_to_run(research_repo):
    with pytest.raises(RealityCheckMissing, match="reality compile"):
        load_record("01-typing", repo_root=research_repo)


def test_an_invalid_record_is_refused_on_save(r5_record, research_repo):
    with pytest.raises(RealityOutputInvalid, match="summary"):
        save_record({**r5_record, "summary": {}}, repo_root=research_repo)


def test_a_proposal_for_a_present_answer_saves_with_its_since(r5_record, r5_cell, r5_run,
                                                              research_repo):
    record = replace_language(r5_record, "python", cells=[r5_cell("python", "dynamic-typing")],
                              uncovered=[], run=r5_run)
    save_record(record, repo_root=research_repo)
    assert find_cell(record, "python--dynamic-typing")["proposal"]["since"] == "3.14"


def test_replace_language_swaps_one_languages_answers_wholesale(r5_record, r5_cell, r5_run):
    first = replace_language(r5_record, "python",
                             cells=[r5_cell("python", "static-typing"),
                                    r5_cell("python", "dynamic-typing")],
                             uncovered=[], run=r5_run)
    both = replace_language(first, "haskell", cells=[r5_cell("haskell", "static-typing")],
                            uncovered=[], run={**r5_run, "run_id": "haskell-run"})
    again = replace_language(both, "python",
                             cells=[r5_cell("python", "dynamic-typing", mappable=False)],
                             uncovered=[], run=r5_run)
    assert [c["key"] for c in again["cells"]] == ["haskell--static-typing",
                                                  "python--dynamic-typing"]
    assert find_cell(again, "python--dynamic-typing")["status"] == "unmappable"
    assert again["runs"]["classify"]["haskell"]["run_id"] == "haskell-run"


def test_set_cell_updates_one_cell_and_refuses_an_unknown_status(r5_record, r5_cell, r5_run):
    record = replace_language(r5_record, "python", cells=[r5_cell("python", "static-typing")],
                              uncovered=[], run=r5_run)
    assert find_cell(set_cell(record, "python--static-typing", status="admitted"),
                     "python--static-typing")["status"] == "admitted"
    with pytest.raises(ValueError, match="minted"):
        set_cell(record, "python--static-typing", status="minted")
    with pytest.raises(KeyError):
        set_cell(record, "python--nothing", status="admitted")


def test_shakedown_entries_are_keyed_by_content_and_never_duplicated(r5_record):
    record = add_shakedown(r5_record, component="sources", detail="erlang: no spec")
    record = add_shakedown(record, component="sources", detail="erlang: no spec")
    record = add_shakedown(record, component="verifier", detail="x#exists: locator-not-found")
    assert len(record["shakedown"]) == 2
    assert all(entry["status"] == "open" for entry in record["shakedown"])


def test_closing_needs_a_resolution_and_redetection_does_not_reopen(r5_record):
    record = add_shakedown(r5_record, component="sources", detail="erlang: no spec")
    key = record["shakedown"][0]["key"]
    with pytest.raises(ValueError, match="resolution"):
        close_shakedown(record, key, resolution=" ")
    closed = close_shakedown(record, key, resolution="accepted: Erlang is a phase-3 language")
    assert open_shakedown(closed) == []
    again = add_shakedown(closed, component="sources", detail="erlang: no spec")
    assert again["shakedown"][0]["status"] == "closed"
    with pytest.raises(KeyError):
        close_shakedown(closed, "s-sources-00000000", resolution="x")


def test_an_unknown_shakedown_component_is_refused(r5_record):
    with pytest.raises(ValueError, match="component"):
        add_shakedown(r5_record, component="vibes", detail="x")


def test_cell_keys_split_unambiguously():
    assert cell_key("python", "dynamic-typing") == "python--dynamic-typing"


def test_the_reality_config_loads(research_repo):
    config = ResearchConfig.load(research_config_path(research_repo))
    assert config.reality.max_characteristics == 1
    assert config.reality.max_syntax == 1
    assert config.reality.classifier.max_packet_terms == 60
    assert config.reality.language_sources["haskell"] == ("haskell-2010-report",
                                                          "ghc-users-guide")
    assert "erlang" not in config.reality.language_sources
