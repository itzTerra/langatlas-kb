import pytest
from pydantic import BaseModel

from langatlas_pipeline.errors import UntrustedContentInSystemRole
from langatlas_pipeline.injection import delimit_untrusted
from langatlas_pipeline.prompts import mint_prompt_version
from langatlas_pipeline.providers.claude_runs import AgentRunResult
from langatlas_research.config import ClaudeRoleConfig
from langatlas_research.errors import SurveyOutputInvalid
from langatlas_research.survey.claude import role_budget, run_structured, split_for_claude

ROLE = ClaudeRoleConfig(model="claude-opus-5", max_turns=12, max_claude_messages=30,
                        max_packet_terms=10, max_candidates=5)
PROMPT_TEXT = ("---\nprompt_id: probe\nvariables: [topic, packet]\n---\n"
               "# system\nYou survey {{topic}}.\n\n# user\nPacket:\n{{packet}}\n")


class Out(BaseModel):
    names: list[str]


def _result(structured, *, is_error=False):
    return AgentRunResult(session_id="s", result_text="", structured_output=structured,
                          num_turns=3, is_error=is_error, tokens_in=10, tokens_out=5,
                          cost_usd=None, terminal_reason="completed")


@pytest.fixture
def prompt(tmp_path):
    return mint_prompt_version("probe", PROMPT_TEXT, root=tmp_path)


def test_split_joins_system_and_user_messages():
    assert split_for_claude([{"role": "system", "content": "a"},
                             {"role": "user", "content": "b"},
                             {"role": "user", "content": "c"}]) == ("a", "b\n\nc")


def test_split_refuses_delimited_content_in_the_system_role():
    with pytest.raises(UntrustedContentInSystemRole):
        split_for_claude([{"role": "system",
                           "content": delimit_untrusted("x", source_id="s")},
                          {"role": "user", "content": "b"}])


def test_split_refuses_a_prompt_without_a_user_message():
    with pytest.raises(ValueError):
        split_for_claude([{"role": "system", "content": "a"}])


def test_a_structured_run_sets_options_and_parses_output(fake_ctx, prompt):
    fake_ctx.claude_results.append(_result({"names": ["closure"]}))

    parsed, result = run_structured(
        fake_ctx, prompt, {"topic": "typing", "packet": "P"}, output_model=Out,
        role_config=ROLE, mcp_servers={"srv": object()}, allowed_tools=("mcp__srv__t",),
        builtin_tools=("WebSearch",))

    assert parsed == Out(names=["closure"]) and result.num_turns == 3
    user, options = fake_ctx.claude_calls[0]
    assert user == "Packet:\nP"
    assert options.system_prompt == "You survey typing."
    assert options.tools == ["WebSearch"]
    assert list(options.allowed_tools) == ["mcp__srv__t"]
    assert options.max_turns == 12 and options.model == "claude-opus-5"
    assert options.output_format == {"type": "json_schema",
                                     "schema": Out.model_json_schema()}


@pytest.mark.parametrize("result", [_result(None), _result({"names": "nope"}),
                                    _result({"names": []}, is_error=True)])
def test_missing_invalid_or_errored_output_is_a_typed_failure(fake_ctx, prompt, result):
    fake_ctx.claude_results.append(result)
    with pytest.raises(SurveyOutputInvalid):
        run_structured(fake_ctx, prompt, {"topic": "t", "packet": "p"}, output_model=Out,
                       role_config=ROLE)


def test_role_budget_caps_claude_messages():
    assert role_budget(ROLE).max_claude_messages == 30
