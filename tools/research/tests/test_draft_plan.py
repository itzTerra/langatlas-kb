import pytest

from langatlas_research.config import ResearchConfig
from langatlas_research.draft.plan import (
    ENTRY_LISTS, PLAN_STATUSES, build_plan_record, entries, find_entry, load_plan,
    plan_path, save_plan, set_entry,
)
from langatlas_research.errors import DraftMissing
from langatlas_research.paths import drafts_dir, research_config_path
from langatlas_research.schema import validate_research_record, validate_research_tree


def _node(key="static-typing", **over):
    return {"key": key, "from_candidates": [key], "kind": "feature", "id": key,
            "name": "Static typing", "summary": "Type checking happens before the run.",
            "layer": 3, "dimension": "type-checking-discipline", "cross_cutting": False,
            "aliases": [], "realizes": ["type-system"],
            "evidence": [{"source": "pierce-tapl-2002", "locator": "§1.1"}],
            "note": "one node per checking discipline", "contested": [], "debate_id": None,
            "status": "proposed", "verification": None, **over}


def test_the_drafts_directory_is_part_of_the_research_layout(research_repo):
    assert (drafts_dir(research_repo) / "README.md").exists()


def test_a_fresh_plan_is_schema_valid_and_round_trips(research_repo, signed_cycle):
    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="run-1",
                             generated_at="2026-09-20T10:00:00Z")
    plan["nodes"].append(_node())
    assert validate_research_record(plan, "draft", repo_root=research_repo) == []
    save_plan(plan, repo_root=research_repo)
    assert plan_path(signed_cycle.slug, research_repo).exists()
    assert load_plan(signed_cycle.slug, repo_root=research_repo) == plan


def test_a_committed_plan_is_validated_by_the_research_tree_gate(research_repo, signed_cycle):
    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="run-1",
                             generated_at="2026-09-20T10:00:00Z")
    save_plan(plan, repo_root=research_repo)
    assert validate_research_tree(research_repo) == []


def test_a_missing_plan_raises_a_typed_error(research_repo):
    with pytest.raises(DraftMissing):
        load_plan("09-nothing", repo_root=research_repo)


def test_entries_walks_every_entry_list_and_tags_its_list_name(research_repo, signed_cycle):
    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="r",
                             generated_at="t")
    plan["nodes"].append(_node())
    plan["edges"].append({"key": "e1", "type": "requires", "from": "a", "to": "b",
                          "statement": "s", "evidence": [], "contested": [],
                          "debate_id": None, "status": "proposed", "verification": None,
                          "note": ""})
    assert {name for name, _ in entries(plan)} == {"nodes", "edges"}
    assert find_entry(plan, "static-typing")[0] == "nodes"


def test_set_entry_is_pure_and_only_accepts_known_statuses(research_repo, signed_cycle):
    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="r", generated_at="t")
    plan["nodes"].append(_node())
    updated = set_entry(plan, "static-typing", status="minted")
    assert updated["nodes"][0]["status"] == "minted"
    assert plan["nodes"][0]["status"] == "proposed"      # the input is untouched
    with pytest.raises(ValueError):
        set_entry(plan, "static-typing", status="nonsense")
    with pytest.raises(KeyError):
        set_entry(plan, "no-such-key", status="minted")


def test_every_entry_list_name_is_a_plan_field(research_repo, signed_cycle):
    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="r", generated_at="t")
    assert all(name in plan for name in ENTRY_LISTS)
    assert set(PLAN_STATUSES) >= {"proposed", "debated", "verified", "minted", "dropped"}


def test_the_draft_config_section_loads(research_repo):
    config = ResearchConfig.load(research_config_path(research_repo))
    assert config.draft.debate.max_messages == 6
    assert set(config.draft.debate.personas) == {"challenger_a", "challenger_b"}
    assert config.draft.ontologist.max_candidates > 0
