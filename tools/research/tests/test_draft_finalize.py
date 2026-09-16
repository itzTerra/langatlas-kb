import pytest

from langatlas_commit.land import BlockedRedMain, Landed
from langatlas_research.cycle import advance, load_cycle, save_cycle
from langatlas_research.draft.contested import waive
from langatlas_research.draft.debate import apply_resolution
from langatlas_research.draft.finalize import finalize_r4, r4_blockers
from langatlas_research.draft.plan import build_plan_record, find_entry, save_plan
from langatlas_research.errors import R4Incomplete


def _node(key="type-system", **over):
    return {"key": key, "from_candidates": [key], "kind": "concept", "id": key,
            "name": "Type system", "summary": "s",
            "evidence": [{"source": "a", "locator": "§1"}, {"source": "b", "locator": "§2"}],
            "contested": [], "debate_id": None, "status": "minted",
            "verification": {"fact_id": "f-1", "verdict": "verified", "admissible": True,
                             "pairs": 2}, "note": "", **over}


@pytest.fixture
def r3_done(research_repo, signed_cycle):
    cycle = advance(signed_cycle, "r3-done")
    save_cycle(cycle, repo_root=research_repo)
    return cycle


def _saved_plan(cycle, repo, nodes):
    plan = build_plan_record(cycle=cycle, ontologist_run_id="run-1",
                             generated_at="2026-09-20T10:00:00Z")
    plan["nodes"] = nodes
    save_plan(plan, repo_root=repo)
    return plan


def test_a_fully_minted_plan_has_no_blockers(research_repo, r3_done):
    plan = _saved_plan(r3_done, research_repo, [_node()])
    assert r4_blockers(r3_done, plan, repo_root=research_repo) == []


def test_an_undebated_contested_carve_blocks(research_repo, r3_done):
    plan = _saved_plan(r3_done, research_repo,
                       [_node(contested=["single-source"], status="proposed")])
    blockers = r4_blockers(r3_done, plan, repo_root=research_repo)
    assert any("no debate" in b for b in blockers)


def test_an_unverified_entry_blocks(research_repo, r3_done):
    plan = _saved_plan(r3_done, research_repo,
                       [_node(status="debated", verification=None)])
    assert any("never reached the verifier" in b
               for b in r4_blockers(r3_done, plan, repo_root=research_repo))


def test_a_refused_entry_blocks(research_repo, r3_done):
    refused = _node(status="verified",
                    verification={"fact_id": "f", "verdict": "unverified",
                                  "admissible": False, "pairs": 1})
    assert any("the gate refused" in b
               for b in r4_blockers(r3_done, _saved_plan(r3_done, research_repo, [refused]),
                                    repo_root=research_repo))


def test_a_verified_but_unlanded_entry_blocks(research_repo, r3_done):
    assert any("not landed" in b
               for b in r4_blockers(r3_done,
                                    _saved_plan(r3_done, research_repo,
                                                [_node(status="verified")]),
                                    repo_root=research_repo))


def test_a_dropped_entry_never_blocks(research_repo, r3_done):
    plan = _saved_plan(r3_done, research_repo,
                       [_node(status="dropped", verification=None, drop_reason="merged")])
    assert r4_blockers(r3_done, plan, repo_root=research_repo) == []


def test_a_plan_predating_the_current_sign_off_blocks(research_repo, r3_done):
    plan = _saved_plan(r3_done, research_repo, [_node()])
    plan["theme_digest"] = "0" * 16
    save_plan(plan, repo_root=research_repo)
    assert any("predates" in b for b in r4_blockers(r3_done, plan, repo_root=research_repo))


def test_finalize_lands_the_plan_and_advances_the_cycle(research_repo, r3_done):
    _saved_plan(r3_done, research_repo, [_node()])
    landed = []

    def _lander(repo_root, path, content, *, chat_run_id, validator, status_checker=None):
        landed.append(path)
        return Landed(commit_sha="abc1234")

    cycle, results = finalize_r4(r3_done.number, repo_root=research_repo, lander=_lander)
    assert landed == [f"research/drafts/{r3_done.slug}.yaml",
                      f"research/cycles/{r3_done.slug}.yaml"]
    assert cycle.status == "r4-done"
    assert cycle.artifacts["draft"] == f"research/drafts/{r3_done.slug}.yaml"
    assert len(results) == 2
    assert load_cycle(r3_done.number, repo_root=research_repo).status == "r4-done"


def test_finalize_records_every_debate_on_the_cycle(research_repo, r3_done):
    from langatlas_research.draft.debate_record import save_debate

    save_debate({"id": f"d-{r3_done.slug}-001", "cycle": r3_done.number,
                 "theme": r3_done.theme, "target": {"list": "nodes", "key": "type-system"},
                 "opened": "2026-09-20", "runs": {"debate": "r"}, "triggers": [],
                 "personas": {}, "pre_challenge": {}, "messages": [
                     {"seq": 1, "role": "proposer", "persona": "p", "text": "x"}],
                 "resolution": {"outcome": "resolved", "disposition": "keep",
                                "standing_dissent": False, "rounds": 0,
                                "upheld_challenges": [], "rationale": "sound"}},
                repo_root=research_repo)
    _saved_plan(r3_done, research_repo, [_node(debate_id=f"d-{r3_done.slug}-001")])

    cycle, _ = finalize_r4(r3_done.number, repo_root=research_repo,
                           lander=lambda *a, **k: Landed(commit_sha="abc"))
    assert cycle.artifacts["debates"] == [f"research/debates/d-{r3_done.slug}-001.yaml"]


def test_finalize_refuses_while_anything_is_open(research_repo, r3_done):
    _saved_plan(r3_done, research_repo, [_node(status="verified")])
    with pytest.raises(R4Incomplete):
        finalize_r4(r3_done.number, repo_root=research_repo,
                    lander=lambda *a, **k: Landed(commit_sha="abc"))


def test_an_escalated_debate_reports_a_distinct_blocker_and_waive_recovers_it(
        research_repo, r3_done):
    """`escalate` leaves `status: proposed` with a `debate_id` set — a shape that used to
    be misreported as "never reached the verifier" (running `draft verify` does nothing
    for it) and that `waive()` used to refuse outright ("already has debate ..."), leaving
    the developer with no way out short of hand-editing committed YAML."""
    entry = _node(contested=["single-source"], status="proposed", debate_id=None,
                 verification=None)
    plan = build_plan_record(cycle=r3_done, ontologist_run_id="run-1",
                             generated_at="2026-09-20T10:00:00Z")
    plan["nodes"] = [entry]

    debate = {"id": f"d-{r3_done.slug}-001", "target": {"list": "nodes", "key": entry["key"]},
              "resolution": {"outcome": "escalated", "disposition": "escalate",
                             "standing_dissent": False, "rounds": 1,
                             "upheld_challenges": [], "rationale": "the sources cannot"
                             " settle this without the developer"}}
    escalated = apply_resolution(plan, debate)
    stuck = find_entry(escalated, entry["key"])[1]
    assert stuck["status"] == "proposed" and stuck["debate_id"] == debate["id"]

    blockers = r4_blockers(r3_done, escalated, repo_root=research_repo)
    assert any("escalated" in b and debate["id"] in b for b in blockers)
    assert not any("never reached the verifier" in b for b in blockers)

    recovered = waive(escalated, entry["key"], "the developer rules: keep the carve as is")
    assert find_entry(recovered, entry["key"])[1]["status"] == "waived"
    recovered_blockers = r4_blockers(r3_done, recovered, repo_root=research_repo)
    assert not any("escalated" in b for b in recovered_blockers)


def test_a_failed_land_leaves_the_cycle_untouched(research_repo, r3_done):
    _saved_plan(r3_done, research_repo, [_node()])
    cycle, results = finalize_r4(
        r3_done.number, repo_root=research_repo,
        lander=lambda *a, **k: BlockedRedMain(since=0.0, last_checked=1.0))
    assert cycle.status == "r3-done"
    assert load_cycle(r3_done.number, repo_root=research_repo).status == "r3-done"


def test_an_unlanded_contradiction_ledger_blocks_finalize(research_repo, r3_done):
    """A debate's last act can be `mint_debate_contradiction`, which writes an uncommitted
    `contradictions.yaml` straight to disk. If the resolution left nothing else to mint
    (e.g. `drop`), the developer could run `draft finalize` without ever running `draft
    mint`, and `land_record`'s rebase would then hit that tracked-but-unstaged file and
    surface an opaque `UnsafeHalt`. `r4_blockers` must catch it first, in plain language."""
    import subprocess

    from langatlas_research.draft.contradictions import mint_debate_contradiction
    from langatlas_research.draft.debate_record import save_debate

    subprocess.run(["git", "init", "-q"], cwd=research_repo, check=True)

    debate = {"id": f"d-{r3_done.slug}-001", "cycle": r3_done.number, "theme": r3_done.theme,
             "target": {"list": "nodes", "key": "type-system"}, "opened": "2026-09-20",
             "runs": {"debate": "run-1", "moderator": "run-2"},
             "triggers": ["single-source"],
             "personas": {"proposer": "p", "moderator": "m"},
             "pre_challenge": {"key": "type-system"},
             "messages": [{"seq": 1, "role": "proposer", "persona": "p", "text": "x"}],
             "resolution": {"outcome": "resolved", "disposition": "keep",
                            "standing_dissent": True, "rounds": 1, "upheld_challenges": [],
                            "rationale": "the two texts disagree",
                            "contradiction": {"participants": ["citation:a:§1",
                                                                "citation:b:§2"],
                                              "detail": "conflicting claims"}}}
    save_debate(debate, repo_root=research_repo)
    assert mint_debate_contradiction(debate, repo_root=research_repo) is not None

    plan = _saved_plan(r3_done, research_repo, [_node()])
    blockers = r4_blockers(r3_done, plan, repo_root=research_repo)
    assert any("contradiction ledger" in b and "draft mint" in b for b in blockers)
