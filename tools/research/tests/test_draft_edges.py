import pytest

from langatlas_pipeline.injection import is_delimited
from langatlas_pipeline.prompts import mint_prompt_version
from langatlas_pipeline.providers.claude_runs import AgentRunResult
from langatlas_research.config import ResearchConfig
from langatlas_research.draft.edges import edge_key, run_edge_drafter
from langatlas_research.draft.ontologist import StoreView
from langatlas_research.draft.plan import build_plan_record, find_entry
from langatlas_research.errors import DraftOutputInvalid
from langatlas_research.paths import research_config_path, structure_review_path
from langatlas_research.schema import validate_research_record

PROMPT_TEXT = ("---\nprompt_id: r4-edge-drafter-test\n"
               "variables: [theme_label, nodes, qualities, edge_types, max_edges]\n---\n"
               "# system\n{{theme_label}} {{qualities}} {{edge_types}} {{max_edges}}\n\n"
               "# user\n{{nodes}}\n")

STORE = StoreView(concepts=frozenset({"type-system"}),
                  features=frozenset({"static-typing", "type-inference"}),
                  dimensions=frozenset({"type-checking-discipline"}))

OUT = {
    "edges": [
        {"type": "requires", "from": "type-inference", "to": "static-typing",
         "statement": "Type inference presupposes static checking.",
         "evidence": [{"chunk_id": "scott-plp#c00310"}]},
        {"type": "alternative-to", "from": "type-inference", "to": "static-typing",
         "statement": "Sources treat the two as alternatives in some designs.",
         "evidence": [{"chunk_id": "pierce-tapl-2002#c00022"}]},
    ],
    "quality_edges": [
        {"from": "static-typing", "to": "type-safety",
         "assessments": [{"key": "kaijanaho-2015-defects", "polarity": "improves",
                          "strength": "moderate",
                          "statement": "fewer type-related defects in the studies surveyed",
                          "evidence": [{"chunk_id": "kaijanaho-2015#c00071"}]}]},
    ],
    "qualities": [{"key": "type-safety", "slug": "type-safety", "label": "Type safety",
                   "summary": "How reliably the language prevents type errors at runtime.",
                   "note": "needed by the assessment above"}],
    "findings": [{"kind": "rule-candidate",
                  "detail": "static typing plus inference together warrant a Rule",
                  "keys": []}],
}


def _result(structured, *, is_error=False):
    return AgentRunResult(session_id="s", result_text="", structured_output=structured,
                          num_turns=3, is_error=is_error, tokens_in=1, tokens_out=1,
                          cost_usd=None, terminal_reason="completed")


@pytest.fixture
def config(research_repo):
    return ResearchConfig.load(research_config_path(research_repo))


@pytest.fixture
def plan(signed_cycle):
    return build_plan_record(cycle=signed_cycle, ontologist_run_id="r",
                             generated_at="2026-09-20T10:00:00Z")


@pytest.fixture
def prompt(tmp_path):
    return mint_prompt_version("r4-edge-drafter-test", PROMPT_TEXT, root=tmp_path)


def test_edge_keys_are_readable_and_unique():
    assert edge_key("requires", "a", "b") == "a--requires--b"
    assert edge_key("affects-quality", "a", "q") == "a--affects-quality--q"


def test_the_edge_drafter_appends_schema_valid_entries(fake_ctx, research_repo, signed_cycle,
                                                       plan, fake_lookup, config, prompt):
    fake_ctx.claude_results.append(_result(OUT))
    updated, warnings = run_edge_drafter(fake_ctx, signed_cycle, plan,
                                         repo_root=research_repo, lookup=fake_lookup,
                                         config=config, prompt=prompt, store=STORE)
    assert validate_research_record(updated, "draft", repo_root=research_repo) == []
    assert warnings == []
    assert updated["runs"]["edge_drafter"] == fake_ctx.run_id
    assert [e["key"] for e in updated["edges"]] == [
        "type-inference--requires--static-typing",
        "static-typing--alternative-to--type-inference"]
    assert updated["quality_edges"][0]["key"] == "static-typing--affects-quality--type-safety"


def test_alternative_to_endpoints_are_canonicalized(fake_ctx, research_repo, signed_cycle,
                                                    plan, fake_lookup, config, prompt):
    fake_ctx.claude_results.append(_result(OUT))
    updated, _ = run_edge_drafter(fake_ctx, signed_cycle, plan, repo_root=research_repo,
                                  lookup=fake_lookup, config=config, prompt=prompt,
                                  store=STORE)
    alternative = updated["edges"][1]
    assert (alternative["from"], alternative["to"]) == ("static-typing", "type-inference")


def test_a_new_quality_is_proposed_and_automatically_contested(
        fake_ctx, research_repo, signed_cycle, plan, fake_lookup, config, prompt):
    fake_ctx.claude_results.append(_result(OUT))
    updated, _ = run_edge_drafter(fake_ctx, signed_cycle, plan, repo_root=research_repo,
                                  lookup=fake_lookup, config=config, prompt=prompt,
                                  store=STORE)
    quality = find_entry(updated, "type-safety")[1]
    assert quality["status"] == "proposed" and "new-quality" in quality["contested"]
    assert "new-quality" in find_entry(
        updated, "static-typing--affects-quality--type-safety")[1]["contested"]


def test_an_endpoint_that_is_not_a_committed_node_is_refused(
        fake_ctx, research_repo, signed_cycle, plan, fake_lookup, config, prompt):
    bad = {**OUT, "edges": [{**OUT["edges"][0], "to": "made-up-feature"}],
           "quality_edges": [], "qualities": []}
    fake_ctx.claude_results.append(_result(bad))
    with pytest.raises(DraftOutputInvalid):
        run_edge_drafter(fake_ctx, signed_cycle, plan, repo_root=research_repo,
                         lookup=fake_lookup, config=config, prompt=prompt, store=STORE)


def test_a_concept_endpoint_is_kept_as_a_blocked_edge_with_friction(
        fake_ctx, research_repo, signed_cycle, plan, fake_lookup, config, prompt):
    bad = {**OUT, "edges": [{**OUT["edges"][0], "to": "type-system"}],
           "quality_edges": [], "qualities": []}
    fake_ctx.claude_results.append(_result(bad))
    updated, _ = run_edge_drafter(fake_ctx, signed_cycle, plan, repo_root=research_repo,
                                  lookup=fake_lookup, config=config, prompt=prompt,
                                  store=STORE)
    edge = updated["edges"][-1]
    assert edge["blocked"] == "structure" and "is a concept" in edge["block_reason"]
    friction = [f for f in updated["findings"] if f.get("kind") == "structure-friction"]
    assert friction and edge["key"] in friction[-1]["keys"]


def test_an_influences_edge_without_a_polarity_is_refused(
        fake_ctx, research_repo, signed_cycle, plan, fake_lookup, config, prompt):
    bad = {**OUT, "edges": [{**OUT["edges"][0], "type": "influences"}],
           "quality_edges": [], "qualities": []}
    fake_ctx.claude_results.append(_result(bad))
    with pytest.raises(DraftOutputInvalid):
        run_edge_drafter(fake_ctx, signed_cycle, plan, repo_root=research_repo,
                         lookup=fake_lookup, config=config, prompt=prompt, store=STORE)


def test_a_quality_edge_pointing_at_an_unproposed_quality_is_refused(
        fake_ctx, research_repo, signed_cycle, plan, fake_lookup, config, prompt):
    bad = {**OUT, "edges": [], "qualities": []}
    fake_ctx.claude_results.append(_result(bad))
    with pytest.raises(DraftOutputInvalid):
        run_edge_drafter(fake_ctx, signed_cycle, plan, repo_root=research_repo,
                         lookup=fake_lookup, config=config, prompt=prompt, store=STORE)


def test_the_node_packet_is_delimited(fake_ctx, research_repo, signed_cycle, plan,
                                      fake_lookup, config, prompt):
    fake_ctx.claude_results.append(_result(OUT))
    run_edge_drafter(fake_ctx, signed_cycle, plan, repo_root=research_repo,
                     lookup=fake_lookup, config=config, prompt=prompt, store=STORE)
    user, _options = fake_ctx.claude_calls[0]
    assert is_delimited(user)


def test_findings_are_appended_not_replaced(fake_ctx, research_repo, signed_cycle, plan,
                                            fake_lookup, config, prompt):
    plan["findings"].append({"kind": "unmappable-candidate", "detail": "from the ontologist"})
    fake_ctx.claude_results.append(_result(OUT))
    updated, _ = run_edge_drafter(fake_ctx, signed_cycle, plan, repo_root=research_repo,
                                  lookup=fake_lookup, config=config, prompt=prompt,
                                  store=STORE)
    assert [f["kind"] for f in updated["findings"]] == ["unmappable-candidate",
                                                        "rule-candidate"]


import pytest as _pytest

from langatlas_research.draft.edges import EdgeDrafterOut, check_shape
from langatlas_research.draft.ontologist import plan_store_view
from langatlas_research.errors import DraftOutputInvalid as _Invalid


def _edges(*pairs):
    return EdgeDrafterOut.model_validate({"edges": [
        {"type": "requires", "from": frm, "to": to, "statement": "s",
         "evidence": [{"chunk_id": "x#c1"}]} for frm, to in pairs]})


def _view(concepts=(), features=()):
    return StoreView(concepts=frozenset(concepts), features=frozenset(features),
                     dimensions=frozenset())


def test_a_concept_endpoint_still_raises_by_default():
    with _pytest.raises(_Invalid, match="is a concept"):
        check_shape(_edges(("a", "c")), _view(concepts=["c"], features=["a"]), set(), 10)


def test_a_concept_endpoint_is_a_misfit_when_collecting():
    misfits = check_shape(_edges(("a", "b"), ("a", "c")),
                          _view(concepts=["c"], features=["a", "b"]), set(), 10,
                          collect_misfits=True)
    assert list(misfits) == [1] and "is a concept" in misfits[1]


def test_an_endpoint_that_exists_nowhere_is_a_hygiene_error_even_when_collecting():
    with _pytest.raises(_Invalid, match="not a committed node"):
        check_shape(_edges(("a", "ghost")), _view(features=["a"]), set(), 10,
                    collect_misfits=True)


def test_the_plan_store_view_adds_unblocked_undropped_plan_nodes():
    plan = {"nodes": [
        {"key": "c1", "id": "c1", "kind": "concept", "status": "verified"},
        {"key": "f1", "id": "f1", "kind": "feature", "status": "proposed"},
        {"key": "f2", "id": "f2", "kind": "feature", "status": "dropped"},
        {"key": "f3", "id": "f3", "kind": "feature", "status": "proposed",
         "blocked": "structure", "block_reason": "r"}]}
    view = plan_store_view(_view(features=["old"]), plan)
    assert view.concepts == {"c1"} and view.features == {"old", "f1"}


# --- D70 draft-only batch: the committed store holds none of the theme's nodes ---------------

def _plan_node(node_id, kind="feature"):
    return {"key": node_id, "from_candidates": [node_id], "kind": kind, "id": node_id,
            "name": node_id, "summary": "s", "layer": 2, "evidence": [], "contested": [],
            "debate_id": None, "status": "proposed", "verification": None, "note": ""}


@pytest.fixture
def gate_closed(research_repo):
    structure_review_path(research_repo).unlink()


@pytest.fixture
def carve_plan(plan):
    plan["nodes"] = [_plan_node("static-typing"), _plan_node("type-inference"),
                     _plan_node("type-system", kind="concept")]
    return plan


def test_edges_are_drafted_against_the_carve_plan_while_the_gate_is_closed(
        fake_ctx, research_repo, signed_cycle, carve_plan, fake_lookup, config, prompt,
        gate_closed):
    fake_ctx.claude_results.append(_result({**OUT, "quality_edges": [], "qualities": []}))
    updated, _ = run_edge_drafter(fake_ctx, signed_cycle, carve_plan, repo_root=research_repo,
                                  lookup=fake_lookup, config=config, prompt=prompt)
    assert [e["key"] for e in updated["edges"]] == [
        "type-inference--requires--static-typing",
        "static-typing--alternative-to--type-inference"]
    user, _options = fake_ctx.claude_calls[0]
    assert "static-typing" in user and "type-inference" in user
    # The plan view is only for drafting: committed-store id-collision must not fire.
    assert all("id-collision" not in e["contested"] for e in updated["edges"])


def test_a_blocked_edge_among_clean_ones_is_indexed_from_the_base_while_the_gate_is_closed(
        fake_ctx, research_repo, signed_cycle, carve_plan, fake_lookup, config, prompt,
        gate_closed):
    carve_plan["edges"] = [{"key": "old", "type": "requires", "from": "a", "to": "b",
                            "polarity": None, "statement": "s", "evidence": [],
                            "contested": [], "debate_id": None, "status": "proposed",
                            "verification": None, "note": ""}]
    mixed = {**OUT, "quality_edges": [], "qualities": [],
             "edges": [OUT["edges"][0], {**OUT["edges"][1], "to": "type-system"}]}
    fake_ctx.claude_results.append(_result(mixed))
    updated, _ = run_edge_drafter(fake_ctx, signed_cycle, carve_plan, repo_root=research_repo,
                                  lookup=fake_lookup, config=config, prompt=prompt)
    old, clean, blocked = updated["edges"]
    assert "blocked" not in old and "blocked" not in clean
    assert blocked["blocked"] == "structure" and "is a concept" in blocked["block_reason"]
