import pytest

from langatlas_pipeline.injection import is_delimited
from langatlas_pipeline.prompts import mint_prompt_version
from langatlas_pipeline.providers.claude_runs import AgentRunResult
from langatlas_research.config import ResearchConfig
from langatlas_research.draft.ontologist import (
    OntologistOut, render_candidates, run_ontologist,
)
from langatlas_research.errors import SignOffStale
from langatlas_research.paths import research_config_path
from langatlas_research.schema import validate_research_record

PROMPT_TEXT = ("---\nprompt_id: r4-ontologist-test\n"
               "variables: [theme_label, theme_summary, layers, dimensions,"
               " committed_nodes, max_nodes, candidates]\n---\n"
               "# system\nCarve {{theme_label}}: {{theme_summary}} {{layers}} {{dimensions}}"
               " {{committed_nodes}} {{max_nodes}}\n\n# user\n{{candidates}}\n")

SURVEY = {
    "cycle": 1, "theme": "typing",
    "candidates": [
        {"key": "static-typing", "name": "Static typing", "gloss": "checked before running",
         "kind_hint": "feature", "origin": "corpus",
         "evidence": [{"chunk_id": "scott-plp#c00310", "source_id": "scott-plp",
                       "locator": "§7.2"}],
         "aliases": [{"label": "compile-time typing"}]},
        {"key": "type-system", "name": "Type system", "gloss": "what types exist",
         "kind_hint": "concept", "origin": "corpus",
         "evidence": [{"chunk_id": "pierce-tapl-2002#c00022",
                       "source_id": "pierce-tapl-2002", "locator": "§1.1"}],
         "aliases": []},
    ],
}

OUT = {
    "nodes": [
        {"key": "type-system", "id": "type-system", "kind": "concept",
         "from_candidates": ["type-system"], "name": "Type system",
         "summary": "The part of a language that defines what types exist.",
         "evidence": [{"chunk_id": "pierce-tapl-2002#c00022"}],
         "note": "the parent concept the discipline features realise"},
        {"key": "static-typing", "id": "static-typing", "kind": "feature",
         "from_candidates": ["static-typing"], "name": "Static typing", "layer": 3,
         "dimension": "type-checking-discipline", "realizes": ["type-system"],
         "aliases": ["compile-time typing"],
         "summary": "Type checking happens before the program runs.",
         "evidence": [{"chunk_id": "scott-plp#c00310",
                       "quote": "Static typing checks types before the program runs."}],
         "note": "one node per checking discipline"},
    ],
    "dimensions": [
        {"key": "type-checking-discipline", "slug": "type-checking-discipline",
         "label": "Type checking discipline",
         "exclusivity": "exclusive", "applies_to": ["general-purpose"],
         "note": "the axis TAPL and PLP both organise the chapter around"},
    ],
    "findings": [{"kind": "rule-candidate",
                  "detail": "static typing + type inference together warrant a Rule",
                  "keys": ["static-typing"]}],
}


def _result(structured, *, is_error=False):
    return AgentRunResult(session_id="s", result_text="", structured_output=structured,
                          num_turns=4, is_error=is_error, tokens_in=10, tokens_out=5,
                          cost_usd=None, terminal_reason="completed")


@pytest.fixture
def config(research_repo):
    return ResearchConfig.load(research_config_path(research_repo))


def test_the_candidate_packet_is_delimited_untrusted_content(fake_ctx):
    packet = render_candidates(fake_ctx, SURVEY, limit=10)
    assert is_delimited(packet)
    assert "static-typing" in packet and "compile-time typing" in packet


def test_the_packet_is_capped(fake_ctx):
    assert render_candidates(fake_ctx, SURVEY, limit=1).count("- key:") == 1


def test_the_ontologist_writes_a_schema_valid_plan(fake_ctx, research_repo, signed_cycle,
                                                   fake_lookup, config, tmp_path):
    fake_ctx.claude_results.append(_result(OUT))
    prompt = mint_prompt_version("r4-ontologist-test", PROMPT_TEXT, root=tmp_path)

    plan, warnings = run_ontologist(fake_ctx, signed_cycle, repo_root=research_repo,
                                    survey=SURVEY, lookup=fake_lookup, config=config,
                                    prompt=prompt, now="2026-09-20T10:00:00Z")

    assert validate_research_record(plan, "draft", repo_root=research_repo) == []
    assert warnings == []
    assert [n["key"] for n in plan["nodes"]] == ["type-system", "static-typing"]
    assert plan["nodes"][1]["evidence"] == [
        {"source": "scott-plp", "locator": "§7.2", "chunk_id": "scott-plp#c00310",
         "quote": "Static typing checks types before the program runs."}]
    assert plan["dimensions"][0]["status"] == "proposed"
    assert plan["findings"][0]["kind"] == "rule-candidate"
    assert plan["runs"]["ontologist"] == fake_ctx.run_id


def test_every_entry_starts_proposed_with_no_debate_and_no_verdict(
        fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path):
    fake_ctx.claude_results.append(_result(OUT))
    plan, _ = run_ontologist(fake_ctx, signed_cycle, repo_root=research_repo, survey=SURVEY,
                             lookup=fake_lookup, config=config,
                             prompt=mint_prompt_version("r4-ontologist-test", PROMPT_TEXT,
                                                        root=tmp_path))
    for entry in plan["nodes"] + plan["dimensions"]:
        assert entry["status"] == "proposed"
        assert entry["debate_id"] is None and entry["verification"] is None


def _run(fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path, out):
    fake_ctx.claude_results.append(_result(out))
    return run_ontologist(fake_ctx, signed_cycle, repo_root=research_repo, survey=SURVEY,
                          lookup=fake_lookup, config=config,
                          prompt=mint_prompt_version("r4-ontologist-test", PROMPT_TEXT,
                                                     root=tmp_path))


def test_realizing_a_feature_blocks_the_carve_instead_of_failing_the_run(
        fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path):
    child = {**OUT["nodes"][1], "key": "child", "id": "child", "name": "Child",
             "from_candidates": [], "realizes": ["static-typing"]}
    plan, _ = _run(fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path,
                   {**OUT, "nodes": [*OUT["nodes"], child]})
    by_key = {node["key"]: node for node in plan["nodes"]}
    assert by_key["child"]["blocked"] == "structure"
    assert "a feature" in by_key["child"]["block_reason"]
    assert "blocked" not in by_key["static-typing"]
    friction = [f for f in plan["findings"] if f["kind"] == "structure-friction"]
    assert friction == [{"kind": "structure-friction", "keys": ["child"],
                         "detail": by_key["child"]["block_reason"],
                         "area": "ontology", "element": "realizes"}]
    assert validate_research_record(plan, "draft", repo_root=research_repo) == []


def test_an_unknown_realizes_target_blocks_the_carve(
        fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path):
    bad = {**OUT, "nodes": [{**OUT["nodes"][1], "realizes": ["no-such-concept"]}]}
    plan, _ = _run(fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path, bad)
    assert plan["nodes"][0]["blocked"] == "structure"
    assert "not a node" in plan["nodes"][0]["block_reason"]


def test_a_layer_3_node_without_a_dimension_blocks_the_carve(
        fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path):
    bad = {**OUT, "nodes": [{**OUT["nodes"][1], "dimension": None}], "dimensions": []}
    plan, _ = _run(fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path, bad)
    node = plan["nodes"][0]
    assert node["blocked"] == "structure"
    assert "dimension-model" in [f.get("element") for f in plan["findings"]]
    assert validate_research_record(plan, "draft", repo_root=research_repo) == []


def test_a_layer_outside_the_three_is_stored_without_a_layer_and_blocked(
        fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path):
    bad = {**OUT, "nodes": [{**OUT["nodes"][1], "layer": 4}]}
    plan, _ = _run(fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path, bad)
    assert "layer" not in plan["nodes"][0] and plan["nodes"][0]["blocked"] == "structure"
    assert "layers" in [f.get("element") for f in plan["findings"]]
    assert validate_research_record(plan, "draft", repo_root=research_repo) == []


def test_a_model_reported_friction_finding_is_not_duplicated(
        fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path):
    child = {**OUT["nodes"][1], "key": "child", "id": "child", "from_candidates": [],
             "realizes": ["static-typing"]}
    reported = {"kind": "structure-friction", "detail": "features specialise features",
                "keys": ["child"], "area": "ontology", "element": "realizes"}
    plan, _ = _run(fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path,
                   {**OUT, "nodes": [*OUT["nodes"], child],
                    "findings": [*OUT["findings"], reported]})
    assert [f["kind"] for f in plan["findings"]].count("structure-friction") == 1


def test_a_hygiene_error_still_fails_the_run(
        fake_ctx, research_repo, signed_cycle, fake_lookup, config, tmp_path):
    from langatlas_research.errors import DraftOutputInvalid

    twice = {**OUT, "nodes": [OUT["nodes"][0], OUT["nodes"][0]]}
    fake_ctx.claude_results.append(_result(twice))
    with pytest.raises(DraftOutputInvalid, match="appears twice"):
        run_ontologist(fake_ctx, signed_cycle, repo_root=research_repo, survey=SURVEY,
                       lookup=fake_lookup, config=config,
                       prompt=mint_prompt_version("r4-ontologist-test", PROMPT_TEXT,
                                                  root=tmp_path))


def test_a_stale_sign_off_stops_the_run_before_any_claude_message(
        research_repo, signed_cycle, fake_ctx, fake_lookup, config, tmp_path):
    from langatlas_research.paths import themes_path

    themes_path(research_repo).write_text(
        themes_path(research_repo).read_text().replace("Typing", "Typing and effects"))
    with pytest.raises(SignOffStale):
        run_ontologist(fake_ctx, signed_cycle, repo_root=research_repo, survey=SURVEY,
                       lookup=fake_lookup, config=config,
                       prompt=mint_prompt_version("r4-ontologist-test", PROMPT_TEXT,
                                                  root=tmp_path))
    assert fake_ctx.claude_calls == []
