import pytest

from langatlas_pipeline.injection import is_delimited
from langatlas_pipeline.prompts import mint_prompt_version
from langatlas_pipeline.providers.claude_runs import AgentRunResult
from langatlas_research.config import ResearchConfig
from langatlas_research.draft.edges import edge_key, run_edge_drafter
from langatlas_research.draft.ontologist import StoreView
from langatlas_research.draft.plan import build_plan_record, find_entry
from langatlas_research.errors import DraftOutputInvalid
from langatlas_research.paths import research_config_path
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


def test_a_concept_endpoint_is_refused(fake_ctx, research_repo, signed_cycle, plan,
                                       fake_lookup, config, prompt):
    bad = {**OUT, "edges": [{**OUT["edges"][0], "to": "type-system"}],
           "quality_edges": [], "qualities": []}
    fake_ctx.claude_results.append(_result(bad))
    with pytest.raises(DraftOutputInvalid):
        run_edge_drafter(fake_ctx, signed_cycle, plan, repo_root=research_repo,
                         lookup=fake_lookup, config=config, prompt=prompt, store=STORE)


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
