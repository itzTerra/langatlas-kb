import json

import pytest

from langatlas_research.draft.debate_record import save_debate
from langatlas_research.draft.plan import build_plan_record, save_plan
from langatlas_research.instrument.costjoin import cost_join, render_cost


def _row(run_id, endpoint="claude", tokens_in=100, tokens_out=50):
    return {"ts": "2026-09-20T10:00:00Z", "run_id": run_id, "seq": 1, "endpoint": endpoint,
            "alias": "claude", "resolved_model": "claude-opus-5", "prompt_id": "r4-proposer",
            "prompt_version": "v-1", "tokens_in": tokens_in, "tokens_out": tokens_out,
            "tokens_if_uncached": None, "latency_ms": 10, "cache_hit": False,
            "outcome": "ok", "cost_usd": None}


def _node(key, **over):
    return {"key": key, "from_candidates": [key], "kind": "concept", "id": key,
            "name": key, "summary": "s", "evidence": [{"source": "a", "locator": "§1"}],
            "contested": [], "debate_id": None, "status": "minted",
            "verification": {"fact_id": "f", "verdict": "verified", "admissible": True,
                             "pairs": 1}, "note": "", **over}


@pytest.fixture
def scenario(research_repo, signed_cycle, tmp_path):
    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="r", generated_at="t")
    plan["nodes"] = [_node("a", debate_id="d-01-typing-001"),
                     _node("b", debate_id="d-01-typing-001"),
                     _node("c", debate_id="d-01-typing-002", status="dropped")]
    save_plan(plan, repo_root=research_repo)
    for debate_id, runs in (("d-01-typing-001", {"debate": "run-a", "moderator": "run-m"}),
                            ("d-01-typing-002", {"debate": "run-b"})):
        save_debate({"id": debate_id, "cycle": 1, "theme": "typing",
                     "target": {"list": "nodes", "key": "a"}, "opened": "2026-09-20",
                     "runs": runs, "triggers": [], "personas": {}, "pre_challenge": {},
                     "messages": [{"seq": 1, "role": "proposer", "persona": "p",
                                   "text": "x"}],
                     "resolution": {"outcome": "resolved", "disposition": "keep",
                                    "standing_dissent": False, "rounds": 0,
                                    "upheld_challenges": [], "rationale": "r"}},
                    repo_root=research_repo)
    log = tmp_path / "cost-log.jsonl"
    log.write_text("\n".join(json.dumps(row) for row in [
        _row("run-a"), _row("run-a"), _row("run-m"),
        _row("run-b"), _row("run-b"), _row("run-b"),
        _row("run-a", endpoint="chat"),           # a university-API call, not Claude
        _row("unrelated-run"),
    ]) + "\n")
    return research_repo, log


def test_claude_messages_are_joined_to_their_debate(scenario):
    repo, log = scenario
    rows = {row.debate_id: row for row in cost_join(repo, cost_log=log)}
    assert rows["d-01-typing-001"].claude_messages == 3     # run-a x2 + run-m; chat excluded
    assert rows["d-01-typing-002"].claude_messages == 3


def test_accepted_nodes_are_counted_per_debate(scenario):
    repo, log = scenario
    rows = {row.debate_id: row for row in cost_join(repo, cost_log=log)}
    assert rows["d-01-typing-001"].accepted_nodes == 2
    assert rows["d-01-typing-002"].accepted_nodes == 0      # its carve was dropped


def test_messages_per_accepted_node_is_none_when_nothing_was_accepted(scenario):
    repo, log = scenario
    rows = {row.debate_id: row for row in cost_join(repo, cost_log=log)}
    assert rows["d-01-typing-001"].messages_per_accepted == 1.5
    assert rows["d-01-typing-002"].messages_per_accepted is None


def test_tokens_are_summed_across_a_debates_runs(scenario):
    repo, log = scenario
    rows = {row.debate_id: row for row in cost_join(repo, cost_log=log)}
    assert rows["d-01-typing-001"].tokens == 3 * 150


def test_a_missing_cost_log_is_an_empty_report_not_a_crash(research_repo, tmp_path):
    assert cost_join(research_repo, cost_log=tmp_path / "nope.jsonl") == []


def test_the_report_renders_a_markdown_table_with_a_total(scenario):
    repo, log = scenario
    report = render_cost(cost_join(repo, cost_log=log))
    assert "| debate |" in report and "d-01-typing-001" in report
    assert "**total**" in report
