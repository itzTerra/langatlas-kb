from pathlib import Path

import pytest

from langatlas_ingest.verify.verdicts import PairVerdict
from langatlas_research.config import ResearchConfig
from langatlas_research.draft.gate import verify_entry, verify_plan
from langatlas_research.draft.minting import entry_draft
from langatlas_research.draft.plan import build_plan_record, find_entry
from langatlas_research.mint import render_draft
from langatlas_research.paths import research_config_path

SOURCE_FACTS = {"scott-plp": type("S", (), {"id": "scott-plp", "tier": "A",
                                            "grounding": "third-party-reference",
                                            "locator_kinds": (), "csl": {}})(),
                "pierce-tapl-2002": type("S", (), {"id": "pierce-tapl-2002", "tier": "B",
                                                   "grounding": "third-party-reference",
                                                   "locator_kinds": (), "csl": {}})()}


def _node(**over):
    return {"key": "static-typing", "from_candidates": ["static-typing"], "kind": "feature",
            "id": "static-typing", "name": "Static typing", "layer": 2, "dimension": None,
            "cross_cutting": False, "aliases": [], "realizes": [],
            "summary": "Type checking happens before the program runs.",
            "evidence": [{"source": "scott-plp", "locator": "§7.2",
                          "chunk_id": "scott-plp#c00310"},
                         {"source": "pierce-tapl-2002", "locator": "§1.1",
                          "chunk_id": "pierce-tapl-2002#c00022"}],
            "contested": [], "debate_id": None, "status": "debated", "verification": None,
            "note": "", **over}


def _verifier(verdicts):
    """A stand-in for `verify_pair`, keyed by (source_id, locator)."""
    def _verify(ctx, conn, *, claim, citation, **kwargs):
        return PairVerdict(fact_id=claim.fact_id, source_id=citation.source_id,
                           locator=citation.locator,
                           verdict=verdicts[(citation.source_id, citation.locator)],
                           run_id=getattr(ctx, "run_id", None), date="2026-09-20")
    return _verify


@pytest.fixture
def config(research_repo):
    return ResearchConfig.load(research_config_path(research_repo))


@pytest.fixture
def deps():
    from langatlas_ingest.verify.pipeline import VerifyDeps

    return VerifyDeps(source_facts=SOURCE_FACTS)


def test_a_tier_a_supported_citation_admits_the_node(fake_ctx, research_repo, config, deps):
    minted = render_draft(entry_draft(_node(), plan={}, ctx_run_id="r", prompt_version="v"))
    result = verify_entry(fake_ctx, None, minted, key="static-typing", kind="feature",
                          repo_root=research_repo, config=config, deps=deps,
                          verifier=_verifier({("scott-plp", "§7.2"): "supported",
                                              ("pierce-tapl-2002", "§1.1"): "unsupported"}))
    assert result.admissible is True
    assert result.verdict == "verified"
    assert result.pairs == 2
    assert result.fact_id.startswith("f-")


def test_partial_only_never_admits(fake_ctx, research_repo, config, deps):
    minted = render_draft(entry_draft(_node(), plan={}, ctx_run_id="r", prompt_version="v"))
    result = verify_entry(fake_ctx, None, minted, key="static-typing", kind="feature",
                          repo_root=research_repo, config=config, deps=deps,
                          verifier=_verifier({("scott-plp", "§7.2"): "partial",
                                              ("pierce-tapl-2002", "§1.1"): "partial"}))
    assert result.admissible is False
    assert "narrow the claim" in result.detail


def test_a_supported_citation_from_a_tier_c_source_does_not_admit(
        fake_ctx, research_repo, config):
    from langatlas_ingest.verify.pipeline import VerifyDeps

    weak = VerifyDeps(source_facts={
        "scott-plp": type("S", (), {"tier": "C", "grounding": "", "locator_kinds": (),
                                    "csl": {}})()})
    node = _node(evidence=[{"source": "scott-plp", "locator": "§7.2"}])
    minted = render_draft(entry_draft(node, plan={}, ctx_run_id="r", prompt_version="v"))
    result = verify_entry(fake_ctx, None, minted, key="static-typing", kind="feature",
                          repo_root=research_repo, config=config, deps=weak,
                          verifier=_verifier({("scott-plp", "§7.2"): "supported"}))
    assert result.admissible is False


def test_an_edge_is_gated_on_its_statements_own_citations(fake_ctx, research_repo, config,
                                                          deps):
    edge = {"key": "static-typing--requires--type-system", "type": "requires",
            "from": "static-typing", "to": "type-system", "polarity": None,
            "statement": "Static typing presupposes a type system.",
            "evidence": [{"source": "scott-plp", "locator": "§7.2"}],
            "contested": [], "debate_id": None, "status": "debated", "verification": None,
            "note": ""}
    minted = render_draft(entry_draft(edge, plan={}, ctx_run_id="r", prompt_version="v"))
    result = verify_entry(fake_ctx, None, minted, key=edge["key"], kind="edge",
                          repo_root=research_repo, config=config, deps=deps,
                          verifier=_verifier({("scott-plp", "§7.2"): "supported"}))
    assert result.admissible is True
    assert result.pairs == 1        # edge-polarity carries no citations and is not a gate


def test_verify_plan_stamps_every_debated_entry_and_leaves_the_rest_alone(
        fake_ctx, research_repo, signed_cycle, config, deps, fake_lookup):
    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="r", generated_at="t")
    plan["nodes"] = [_node(), _node(key="other", id="other", status="proposed",
                                    contested=["single-source"])]

    updated, results = verify_plan(
        fake_ctx, None, plan, cycle=signed_cycle, repo_root=research_repo, config=config,
        lookup=fake_lookup,
        deps=deps, verifier=_verifier({("scott-plp", "§7.2"): "supported",
                                       ("pierce-tapl-2002", "§1.1"): "supported"}))

    assert [r.key for r in results] == ["static-typing"]
    assert find_entry(updated, "static-typing")[1]["status"] == "verified"
    assert find_entry(updated, "static-typing")[1]["verification"]["admissible"] is True
    assert find_entry(updated, "other")[1]["status"] == "proposed"


def test_a_stale_sign_off_stops_the_gate_before_any_verifier_call(
        fake_ctx, research_repo, signed_cycle, config, deps, fake_lookup):
    from langatlas_research.errors import SignOffStale
    from langatlas_research.paths import themes_path

    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="r", generated_at="t")
    plan["nodes"] = [_node()]
    themes_path(research_repo).write_text(
        themes_path(research_repo).read_text().replace("Typing", "Typing and effects"))

    def _never(*args, **kwargs):
        raise AssertionError("the verifier ran against a stale sign-off")

    with pytest.raises(SignOffStale):
        verify_plan(fake_ctx, None, plan, cycle=signed_cycle, repo_root=research_repo,
                    config=config, lookup=fake_lookup, deps=deps, verifier=_never)


def test_a_refused_entry_keeps_its_verdict_and_is_not_verified(
        fake_ctx, research_repo, signed_cycle, config, deps, fake_lookup):
    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="r", generated_at="t")
    plan["nodes"] = [_node()]
    updated, _results = verify_plan(
        fake_ctx, None, plan, cycle=signed_cycle, repo_root=research_repo, config=config,
        lookup=fake_lookup,
        deps=deps, verifier=_verifier({("scott-plp", "§7.2"): "unsupported",
                                       ("pierce-tapl-2002", "§1.1"): "unsupported"}))
    entry = find_entry(updated, "static-typing")[1]
    assert entry["status"] == "debated"
    assert entry["verification"]["admissible"] is False
