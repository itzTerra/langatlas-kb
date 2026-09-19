from langatlas_research.cli import main
from langatlas_research.draft.plan import build_plan_record, load_plan, save_plan


def _node(**over):
    return {"key": "type-system", "from_candidates": ["type-system"], "kind": "concept",
            "id": "type-system", "name": "Type system", "summary": "s",
            "evidence": [{"source": "a", "locator": "§1"}],
            "contested": ["single-source"], "debate_id": None, "status": "proposed",
            "verification": None, "note": "", **over}


def _plan(cycle, repo, nodes):
    plan = build_plan_record(cycle=cycle, ontologist_run_id="r", generated_at="t")
    plan["nodes"] = nodes
    save_plan(plan, repo_root=repo)
    return plan


def test_draft_contested_lists_triggers(research_repo, signed_cycle, capsys):
    _plan(signed_cycle, research_repo, [_node()])
    assert main(["--repo-root", str(research_repo), "draft", "contested", "1"]) == 0
    out = capsys.readouterr().out
    assert "type-system" in out and "single-source" in out


def test_draft_waive_records_the_reason(research_repo, signed_cycle, capsys):
    _plan(signed_cycle, research_repo, [_node()])
    assert main(["--repo-root", str(research_repo), "draft", "waive", "1", "type-system",
                 "--reason", "Pierce is the only definition and that is fine"]) == 0
    entry = load_plan(signed_cycle.slug, repo_root=research_repo)["nodes"][0]
    assert entry["status"] == "waived" and "Pierce" in entry["waiver"]


def test_draft_waive_refuses_an_uncontested_carve(research_repo, signed_cycle, capsys):
    _plan(signed_cycle, research_repo, [_node(contested=[])])
    assert main(["--repo-root", str(research_repo), "draft", "waive", "1", "type-system",
                 "--reason", "why not"]) == 1
    assert "not contested" in capsys.readouterr().err


def test_draft_status_summarizes_the_plan(research_repo, signed_cycle, capsys):
    _plan(signed_cycle, research_repo, [_node(), _node(key="other", id="other",
                                                       status="minted", contested=[])])
    assert main(["--repo-root", str(research_repo), "draft", "status", "1"]) == 0
    out = capsys.readouterr().out
    assert "proposed" in out and "minted" in out


def test_draft_drop_records_the_reason(research_repo, signed_cycle, capsys):
    _plan(signed_cycle, research_repo, [_node()])
    assert main(["--repo-root", str(research_repo), "draft", "drop", "1", "type-system",
                 "--reason", "no slot in the revised structure"]) == 0
    entry = load_plan(signed_cycle.slug, repo_root=research_repo)["nodes"][0]
    assert entry["status"] == "dropped" and "no slot" in entry["drop_reason"]
