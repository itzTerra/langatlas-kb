import pytest

from langatlas_pipeline.prompts import mint_prompt_version
from langatlas_pipeline.providers.claude_runs import AgentRunResult
from langatlas_research.config import ResearchConfig
from langatlas_research.draft.debate import DebatePrompts, apply_resolution, run_debate
from langatlas_research.draft.debate_record import load_debate
from langatlas_research.draft.plan import build_plan_record, find_entry, save_plan
from langatlas_research.errors import DebateIncomplete
from langatlas_research.paths import research_config_path
from langatlas_research.schema import validate_research_record

P_TEXT = ("---\nprompt_id: r4-proposer-test\n"
          "variables: [theme_label, entry_kind, entry, triggers, challenges]\n---\n"
          "# system\n{{theme_label}} {{entry_kind}} {{triggers}}\n\n"
          "# user\n{{entry}}\n{{challenges}}\n")
C_TEXT = ("---\nprompt_id: r4-challenger-test\n"
          "variables: [theme_label, persona, entry_kind, entry, triggers,"
          " proposer_statement, challenge_types, max_challenges]\n---\n"
          "# system\n{{theme_label}} {{persona}} {{entry_kind}} {{challenge_types}}"
          " {{max_challenges}}\n\n# user\n{{entry}} {{triggers}} {{proposer_statement}}\n")
M_TEXT = ("---\nprompt_id: r4-moderator-test\n"
          "variables: [theme_label, entry_kind, entry, triggers, transcript,"
          " dispositions]\n---\n"
          "# system\n{{theme_label}} {{entry_kind}} {{dispositions}}\n\n"
          "# user\n{{entry}} {{triggers}} {{transcript}}\n")


def _result(structured):
    return AgentRunResult(session_id="s", result_text="", structured_output=structured,
                          num_turns=2, is_error=False, tokens_in=1, tokens_out=1,
                          cost_usd=None, terminal_reason="completed")


def _node(**over):
    return {"key": "static-typing", "from_candidates": ["static-typing", "type-checking"],
            "kind": "feature", "id": "static-typing", "name": "Static typing",
            "summary": "Type checking happens before the program runs.", "layer": 2,
            "dimension": None, "cross_cutting": False, "aliases": [], "realizes": [],
            "evidence": [{"source": "scott-plp", "locator": "§7.2",
                          "chunk_id": "scott-plp#c00310"}],
            "contested": ["merged-candidates"], "debate_id": None, "status": "proposed",
            "verification": None, "note": "", **over}


@pytest.fixture
def prompts(tmp_path):
    return DebatePrompts(
        proposer=mint_prompt_version("r4-proposer-test", P_TEXT, root=tmp_path),
        challenger=mint_prompt_version("r4-challenger-test", C_TEXT, root=tmp_path),
        moderator=mint_prompt_version("r4-moderator-test", M_TEXT, root=tmp_path))


@pytest.fixture
def config(research_repo):
    return ResearchConfig.load(research_config_path(research_repo))


@pytest.fixture
def plan(signed_cycle, research_repo):
    record = build_plan_record(cycle=signed_cycle, ontologist_run_id="r",
                              generated_at="2026-09-20T10:00:00Z")
    record["nodes"].append(_node())
    save_plan(record, repo_root=research_repo)
    return record


def _script(ctx, *, challenges_a, challenges_b, moderator):
    ctx.claude_results.extend([
        _result({"text": "I carve one node per checking discipline."}),
        _result({"text": "Objection.", "challenges": challenges_a}),
        _result({"text": "Concur.", "challenges": challenges_b}),
        _result({"text": "Conceded."}),
    ])
    return moderator


def test_a_debate_runs_five_messages_and_writes_a_schema_valid_record(
        fake_ctx, research_repo, signed_cycle, plan, config, prompts, fake_lookup):
    moderator_ctx = type(fake_ctx)(run_id="2026-09-20-r4-moderator-01-typing-01")
    moderator_ctx.claude_results.append(_result(
        {"disposition": "revise", "standing_dissent": False,
         "upheld_challenges": ["wrong-atomization"],
         "rationale": "the cited passage supports narrowing the carve",
         "revision": {"summary": "Type checking happens wholly before the program runs."}}))
    _script(fake_ctx,
            challenges_a=[{"type": "wrong-atomization", "text": "two ideas merged",
                           "evidence": [{"chunk_id": "pierce-tapl-2002#c00022"}]}],
            challenges_b=[], moderator=None)

    updated, debate = run_debate(fake_ctx, signed_cycle, plan, "static-typing",
                                 repo_root=research_repo, config=config, lookup=fake_lookup,
                                 moderator_ctx=moderator_ctx, prompts=prompts,
                                 today="2026-09-20")

    assert validate_research_record(debate, "debate", repo_root=research_repo) == []
    assert [m["role"] for m in debate["messages"]] == [
        "proposer", "challenger-a", "challenger-b", "proposer", "moderator"]
    assert debate["resolution"]["outcome"] == "converged-after-revision"
    assert debate["resolution"]["rounds"] == 1
    assert debate["pre_challenge"]["summary"] == ("Type checking happens before the program"
                                                  " runs.")
    assert debate["runs"] == {"debate": fake_ctx.run_id, "moderator": moderator_ctx.run_id}
    assert load_debate(debate["id"], repo_root=research_repo) == debate


def test_the_resolution_is_written_back_onto_the_carve(
        fake_ctx, research_repo, signed_cycle, plan, config, prompts, fake_lookup):
    moderator_ctx = type(fake_ctx)(run_id="mod-1")
    moderator_ctx.claude_results.append(_result(
        {"disposition": "revise", "standing_dissent": False, "upheld_challenges": [],
         "rationale": "narrowed", "revision": {"summary": "Narrower.", "layer": 3,
                                               "dimension": "type-checking-discipline"}}))
    _script(fake_ctx, challenges_a=[], challenges_b=[], moderator=None)

    updated, debate = run_debate(fake_ctx, signed_cycle, plan, "static-typing",
                                 repo_root=research_repo, config=config, lookup=fake_lookup,
                                 moderator_ctx=moderator_ctx, prompts=prompts)

    entry = find_entry(updated, "static-typing")[1]
    assert entry["status"] == "debated" and entry["debate_id"] == debate["id"]
    assert entry["summary"] == "Narrower." and entry["layer"] == 3


def test_a_revision_may_not_change_a_carves_identity(
        fake_ctx, research_repo, signed_cycle, plan, config, prompts, fake_lookup):
    moderator_ctx = type(fake_ctx)(run_id="mod-1")
    moderator_ctx.claude_results.append(_result(
        {"disposition": "revise", "standing_dissent": False, "upheld_challenges": [],
         "rationale": "r", "revision": {"id": "something-else"}}))
    _script(fake_ctx, challenges_a=[], challenges_b=[], moderator=None)
    with pytest.raises(DebateIncomplete):
        run_debate(fake_ctx, signed_cycle, plan, "static-typing", repo_root=research_repo,
                   config=config, lookup=fake_lookup, moderator_ctx=moderator_ctx,
                   prompts=prompts)


def test_a_drop_disposition_drops_the_carve(
        fake_ctx, research_repo, signed_cycle, plan, config, prompts, fake_lookup):
    moderator_ctx = type(fake_ctx)(run_id="mod-1")
    moderator_ctx.claude_results.append(_result(
        {"disposition": "drop", "standing_dissent": False,
         "upheld_challenges": ["redundant-with"], "rationale": "already covered",
         "drop_reason": "duplicates the committed type-system concept"}))
    _script(fake_ctx, challenges_a=[], challenges_b=[], moderator=None)

    updated, _debate = run_debate(fake_ctx, signed_cycle, plan, "static-typing",
                                  repo_root=research_repo, config=config,
                                  lookup=fake_lookup, moderator_ctx=moderator_ctx,
                                  prompts=prompts)
    entry = find_entry(updated, "static-typing")[1]
    assert entry["status"] == "dropped" and "duplicates" in entry["drop_reason"]


def test_a_split_adds_the_replacement_carves_and_drops_the_original(
        fake_ctx, research_repo, signed_cycle, plan, config, prompts, fake_lookup):
    moderator_ctx = type(fake_ctx)(run_id="mod-1")
    moderator_ctx.claude_results.append(_result(
        {"disposition": "split", "standing_dissent": True,
         "upheld_challenges": ["wrong-atomization"], "rationale": "two ideas",
         "split_into": [
             {"key": "static-checking", "id": "static-checking", "kind": "feature",
              "name": "Static checking", "summary": "Checked before the run.", "layer": 2,
              "from_candidates": ["static-typing"],
              "evidence": [{"chunk_id": "scott-plp#c00310"}]},
             {"key": "type-checking", "id": "type-checking", "kind": "concept",
              "name": "Type checking", "summary": "Deciding whether a program is well typed.",
              "from_candidates": ["type-checking"],
              "evidence": [{"chunk_id": "pierce-tapl-2002#c00022"}]}]}))
    _script(fake_ctx, challenges_a=[], challenges_b=[], moderator=None)

    updated, debate = run_debate(fake_ctx, signed_cycle, plan, "static-typing",
                                 repo_root=research_repo, config=config, lookup=fake_lookup,
                                 moderator_ctx=moderator_ctx, prompts=prompts)

    keys = [n["key"] for n in updated["nodes"]]
    assert keys == ["static-typing", "static-checking", "type-checking"]
    assert find_entry(updated, "static-typing")[1]["status"] == "dropped"
    assert find_entry(updated, "static-checking")[1]["debate_id"] == debate["id"]
    assert debate["resolution"]["outcome"] == "converged-after-revision"
    assert debate["resolution"]["standing_dissent"] is True


def test_the_moderator_never_sees_the_debates_own_session(
        fake_ctx, research_repo, signed_cycle, plan, config, prompts, fake_lookup):
    moderator_ctx = type(fake_ctx)(run_id="mod-1")
    moderator_ctx.claude_results.append(_result(
        {"disposition": "keep", "standing_dissent": False, "upheld_challenges": [],
         "rationale": "sound"}))
    _script(fake_ctx, challenges_a=[], challenges_b=[], moderator=None)

    run_debate(fake_ctx, signed_cycle, plan, "static-typing", repo_root=research_repo,
               config=config, lookup=fake_lookup, moderator_ctx=moderator_ctx,
               prompts=prompts)

    assert len(fake_ctx.claude_calls) == 4        # proposer, A, B, proposer reply
    assert len(moderator_ctx.claude_calls) == 1   # the moderator, in its own context
    _user, options = moderator_ctx.claude_calls[0]
    assert options.mcp_servers is None            # no corpus tools: it judges the record


def test_a_debate_never_exceeds_the_configured_message_cap(
        fake_ctx, research_repo, signed_cycle, plan, config, prompts, fake_lookup):
    moderator_ctx = type(fake_ctx)(run_id="mod-1")
    moderator_ctx.claude_results.append(_result(
        {"disposition": "keep", "standing_dissent": False, "upheld_challenges": [],
         "rationale": "sound"}))
    _script(fake_ctx, challenges_a=[], challenges_b=[], moderator=None)
    _updated, debate = run_debate(fake_ctx, signed_cycle, plan, "static-typing",
                                  repo_root=research_repo, config=config,
                                  lookup=fake_lookup, moderator_ctx=moderator_ctx,
                                  prompts=prompts)
    assert len(debate["messages"]) <= config.draft.debate.max_messages


def test_debating_an_uncontested_carve_is_refused(
        fake_ctx, research_repo, signed_cycle, config, prompts, fake_lookup):
    record = build_plan_record(cycle=signed_cycle, ontologist_run_id="r", generated_at="t")
    record["nodes"].append(_node(contested=[]))
    with pytest.raises(ValueError):
        run_debate(fake_ctx, signed_cycle, record, "static-typing", repo_root=research_repo,
                   config=config, lookup=fake_lookup, moderator_ctx=fake_ctx,
                   prompts=prompts)


def test_splitting_anything_but_a_node_is_refused(signed_cycle, plan):
    """`split_into` is node-shaped, so applying one to an edge would drop the edge and
    inject concept/feature entries into `nodes`."""
    edge = {"key": "static-typing--requires--type-system", "type": "requires",
            "from": "static-typing", "to": "type-system", "polarity": None,
            "statement": "Static typing presupposes a type system.",
            "evidence": [{"source": "scott-plp", "locator": "§7.2"}],
            "contested": ["single-source"], "debate_id": None, "status": "proposed",
            "verification": None, "note": ""}
    record = {**plan, "edges": [edge]}
    debate = {"id": "d-01-typing-002",
              "target": {"list": "edges", "key": edge["key"]},
              "resolution": {"outcome": "converged-after-revision", "disposition": "split",
                             "standing_dissent": False, "rounds": 1,
                             "upheld_challenges": [], "rationale": "two claims",
                             "split_into": [
                                 {"key": "a", "id": "a", "kind": "feature", "name": "A",
                                  "summary": "s", "evidence": []},
                                 {"key": "b", "id": "b", "kind": "feature", "name": "B",
                                  "summary": "s", "evidence": []}]}}
    with pytest.raises(DebateIncomplete):
        apply_resolution(record, debate)
    assert [entry["key"] for entry in record["nodes"]] == ["static-typing"]


def test_apply_resolution_is_pure(signed_cycle, plan):
    debate = {"id": "d-01-typing-001", "target": {"list": "nodes", "key": "static-typing"},
              "resolution": {"outcome": "resolved", "disposition": "keep",
                             "standing_dissent": False, "rounds": 0,
                             "upheld_challenges": [], "rationale": "sound"}}
    updated = apply_resolution(plan, debate)
    assert find_entry(updated, "static-typing")[1]["status"] == "debated"
    assert find_entry(plan, "static-typing")[1]["status"] == "proposed"
