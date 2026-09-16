import pytest

from langatlas_commit.land import Landed
from langatlas_research.draft.minting import (
    RECORD_KINDS_BY_LIST, entry_draft, mint_items, mint_plan,
)
from langatlas_research.draft.plan import build_plan_record, find_entry
from langatlas_research.drafts import ConceptDraft, EdgeDraft, FeatureDraft, QualityEdgeDraft
from langatlas_research.errors import NotAdmissible, UndebatedCarve
from langatlas_research.mint import render_draft

VERIFIED = {"fact_id": "f-abc", "verdict": "verified", "admissible": True, "pairs": 2}


def _tail(**over):
    return {"contested": [], "debate_id": None, "status": "verified",
            "verification": dict(VERIFIED), "note": "", **over}


def _concept(key="type-system", **over):
    return {"key": key, "from_candidates": [key], "kind": "concept", "id": key,
            "name": "Type system", "summary": "What types exist in a language.",
            "evidence": [{"source": "pierce-tapl-2002", "locator": "§1.1"}],
            **_tail(), **over}


def _feature(key="static-typing", **over):
    return {"key": key, "from_candidates": [key], "kind": "feature", "id": key,
            "name": "Static typing", "layer": 3, "dimension": "type-checking-discipline",
            "cross_cutting": False, "aliases": ["compile-time typing"],
            "realizes": ["type-system"],
            "summary": "Type checking happens before the program runs.",
            "evidence": [{"source": "scott-plp", "locator": "§7.2"}], **_tail(), **over}


def _dimension(**over):
    return {"key": "type-checking-discipline", "slug": "type-checking-discipline",
            "label": "Type checking discipline", "values": ["static", "dynamic", "gradual"],
            "exclusivity": "exclusive", "applies_to": ["general-purpose"],
            "contested": [], "debate_id": None, "status": "debated", "verification": None,
            "note": "", **over}


def _plan(cycle, **over):
    plan = build_plan_record(cycle=cycle, ontologist_run_id="r", generated_at="t")
    return {**plan, **over}


def test_each_plan_list_maps_to_a_record_kind():
    assert RECORD_KINDS_BY_LIST["nodes"](_concept()) == "concept"
    assert RECORD_KINDS_BY_LIST["nodes"](_feature()) == "feature"
    assert RECORD_KINDS_BY_LIST["edges"]({}) == "edge"
    assert RECORD_KINDS_BY_LIST["quality_edges"]({}) == "affects-quality-edge"


def test_a_concept_entry_becomes_a_concept_draft():
    draft = entry_draft(_concept(), plan={}, ctx_run_id="run-1", prompt_version="v-1")
    assert isinstance(draft, ConceptDraft)
    assert draft.id == "type-system" and draft.chat_run_id == "run-1"
    assert draft.proposer.prompt_version == "v-1"
    assert draft.claim_origin == "source-derived"
    assert draft.candidate_source == "internal-survey"


def test_a_feature_entry_carries_layer_dimension_aliases_and_realizes():
    draft = entry_draft(_feature(), plan={}, ctx_run_id="r", prompt_version="v")
    assert isinstance(draft, FeatureDraft)
    assert (draft.layer, draft.dimension) == (3, "type-checking-discipline")
    assert draft.realizes == ("type-system",) and draft.aliases == ("compile-time typing",)


def test_a_debate_id_reaches_the_records_provenance():
    draft = entry_draft(_feature(debate_id="d-01-typing-004"), plan={}, ctx_run_id="r",
                        prompt_version="v")
    assert draft.debate_id == "d-01-typing-004"
    assert "debate_id: d-01-typing-004" in render_draft(draft).text


def test_an_edge_entry_becomes_an_edge_draft():
    entry = {"key": "e", "type": "influences", "from": "static-typing", "to": "type-system",
             "polarity": "+", "statement": "Static typing shapes the type system.",
             "evidence": [{"source": "scott-plp", "locator": "§7.2"}], **_tail()}
    draft = entry_draft(entry, plan={}, ctx_run_id="r", prompt_version="v")
    assert isinstance(draft, EdgeDraft) and draft.polarity == "+"


def test_a_quality_edge_entry_becomes_a_quality_edge_draft():
    entry = {"key": "q", "from": "static-typing", "to": "type-safety",
             "assessments": [{"key": "kaijanaho-2015-defects", "polarity": "improves",
                              "strength": "moderate", "statement": "fewer type defects",
                              "evidence": [{"source": "kaijanaho-2015", "locator": "§2.4"}]}],
             **_tail()}
    draft = entry_draft(entry, plan={}, ctx_run_id="r", prompt_version="v")
    assert isinstance(draft, QualityEdgeDraft)
    assert draft.assessments[0].key == "kaijanaho-2015-defects"


def test_mint_items_orders_dimensions_then_concepts_then_features_then_edges(signed_cycle,
                                                                            research_repo):
    edge = {"key": "e", "type": "requires", "from": "static-typing", "to": "type-system",
            "polarity": None, "statement": "s",
            "evidence": [{"source": "scott-plp", "locator": "§7.2"}], **_tail()}
    plan = _plan(signed_cycle, dimensions=[_dimension()],
                 nodes=[_feature(), _concept()], edges=[edge])
    items = mint_items(plan, repo_root=research_repo, ctx_run_id="r", prompt_version="v")
    kinds = [type(item).__name__ if not callable(item) else "shared-file" for item in items]
    assert kinds == ["shared-file", "ConceptDraft", "FeatureDraft", "EdgeDraft"]


def test_only_admitted_entries_are_minted(signed_cycle, research_repo):
    plan = _plan(signed_cycle, nodes=[_concept(), _feature(status="debated",
                                                           verification=None)])
    items = mint_items(plan, repo_root=research_repo, ctx_run_id="r", prompt_version="v")
    assert [item.id for item in items] == ["type-system"]


def test_an_entry_the_gate_refused_is_never_minted(signed_cycle, research_repo):
    refused = _concept(status="verified",
                       verification={"fact_id": "f-x", "verdict": "unverified",
                                     "admissible": False, "pairs": 1})
    with pytest.raises(NotAdmissible):
        mint_items(_plan(signed_cycle, nodes=[refused]), repo_root=research_repo,
                   ctx_run_id="r", prompt_version="v")


def test_a_contested_undebated_carve_stops_the_mint(signed_cycle, research_repo):
    carve = _concept(contested=["merged-candidates"], debate_id=None)
    with pytest.raises(UndebatedCarve):
        mint_items(_plan(signed_cycle, nodes=[carve]), repo_root=research_repo,
                   ctx_run_id="r", prompt_version="v")


def test_a_waived_carve_does_not_stop_the_mint(signed_cycle, research_repo):
    carve = _concept(contested=["single-source"], status="verified", waiver="developer call")
    items = mint_items(_plan(signed_cycle, nodes=[carve]), repo_root=research_repo,
                       ctx_run_id="r", prompt_version="v")
    assert [item.id for item in items] == ["type-system"]


def test_mint_plan_marks_every_landed_entry_minted(signed_cycle, research_repo):
    landed = []

    def _lander(items, *, repo_root, chat_run_id, cycle=None, status_checker=None,
                attempts=3):
        results = []
        for item in items:
            minted = item() if callable(item) else render_draft(item)
            landed.append(minted.path)
            results.append((minted, Landed(commit_sha="abc1234")))
        return results

    plan = _plan(signed_cycle, dimensions=[_dimension()], nodes=[_concept(), _feature()])
    updated, results = mint_plan(plan, repo_root=research_repo, cycle=signed_cycle,
                                 chat_run_id="run-1", prompt_version="v", lander=_lander)

    assert landed == ["ontology/taxonomy/dimensions.yaml", "concepts/type-system.yaml",
                      "features/static-typing.yaml"]
    assert find_entry(updated, "type-system")[1]["status"] == "minted"
    assert find_entry(updated, "type-checking-discipline")[1]["status"] == "minted"
    assert len(results) == 3


def test_an_unlanded_entry_keeps_its_previous_status(signed_cycle, research_repo):
    from langatlas_commit.land import BlockedRedMain

    def _lander(items, *, repo_root, chat_run_id, cycle=None, status_checker=None,
                attempts=3):
        return [(render_draft(item), BlockedRedMain(since=0.0, last_checked=1.0))
                for item in items]

    plan = _plan(signed_cycle, nodes=[_concept()])
    updated, _results = mint_plan(plan, repo_root=research_repo, cycle=signed_cycle,
                                  chat_run_id="r", prompt_version="v", lander=_lander)
    assert find_entry(updated, "type-system")[1]["status"] == "verified"
