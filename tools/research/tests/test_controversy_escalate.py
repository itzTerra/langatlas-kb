"""Escalation has to do two things: let Claude overrule the thinker, and leave a hand-labelable
case behind. The second is what grows 2B's ~15-20 bootstrap cases toward §6.4's ~50."""
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_pipeline.providers.claude_runs import AgentRunResult
from langatlas_research.config import ClaudeRoleConfig
from langatlas_research.controversy.assessor import Assessment
from langatlas_research.controversy.escalate import candidates_path, capture_candidate, escalate
from langatlas_research.controversy.inputs import ControversyInputs

_yaml = YAML(typ="safe")

ROLE = ClaudeRoleConfig(model=None, max_turns=20, max_claude_messages=40, max_packet_terms=0,
                        max_candidates=1)
INPUTS = ControversyInputs.from_mapping({
    "debates": [{"id": "d-01-typing-003", "outcome": "escalated", "standing_dissent": True,
                 "rounds": 4}],
    "verdicts": [{"fact": "f-a", "citation": 1, "verdict": "contradicted", "field": "base",
                  "tier": "A"}]})
PROPOSED = Assessment(fact_id="f-a", level=3, signals=("verdict:contradicted:base",),
                      alternative=2, model="deepseek-v4-pro-thinking",
                      prompt="controversy-assessor@v-1a2b3c4d", run_id="r-1")


def _claude(fake_ctx, level, signals):
    fake_ctx.claude_results.append(AgentRunResult(
        session_id="s", result_text="", structured_output={"level": level, "signals": signals},
        num_turns=1, is_error=False, tokens_in=1, tokens_out=1, cost_usd=0.0))


def test_claude_overrules_the_thinker_and_the_result_records_who_decided(fake_ctx):
    _claude(fake_ctx, 2, ["verdict:contradicted:base"])
    final = escalate(fake_ctx, PROPOSED, INPUTS, role_config=ROLE)
    assert final.level == 2
    assert final.escalated_to == "claude"
    assert final.alternative is None            # the ambiguity was resolved, not carried forward


def test_claudes_invented_signals_are_dropped_too(fake_ctx):
    _claude(fake_ctx, 3, ["verdict:contradicted:base", "contradiction:ctr-000000000000:open"])
    final = escalate(fake_ctx, PROPOSED, INPUTS, role_config=ROLE)
    assert final.signals == ("verdict:contradicted:base",)


def test_a_captured_candidate_is_uncurated_and_carries_both_levels(tmp_path):
    path = capture_candidate(
        PROPOSED, Assessment(fact_id="f-a", level=2, signals=("verdict:contradicted:base",),
                             escalated_to="claude"),
        INPUTS, repo_root=tmp_path, today="2026-09-17")
    data = _yaml.load(path.read_text())
    case, = data["cases"]
    assert case["curated"] is False
    assert case["expected_level"] == 2              # Claude's answer, pending a human label
    assert case["first_pass_level"] == 3
    assert set(case["inputs"]) <= {"debates", "contradiction_records", "verdicts",
                                   "source_strength", "assessment_spread"}


def test_candidates_land_outside_the_globbed_golden_directory(tmp_path):
    path = candidates_path(repo_root=tmp_path, today="2026-09-17")
    assert path.parent.name == "candidates"
    assert path.parent.parent.name == "controversy"


def test_capturing_twice_in_a_month_appends_rather_than_overwrites(tmp_path):
    final = Assessment(fact_id="f-b", level=2, signals=(), escalated_to="claude")
    capture_candidate(PROPOSED, final, INPUTS, repo_root=tmp_path, today="2026-09-17")
    path = capture_candidate(PROPOSED, final, INPUTS, repo_root=tmp_path, today="2026-09-28")
    assert len(_yaml.load(path.read_text())["cases"]) == 2
