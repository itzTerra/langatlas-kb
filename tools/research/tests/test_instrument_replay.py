import pytest

from langatlas_ingest.verify.pipeline import VerifyDeps
from langatlas_ingest.verify.verdicts import PairVerdict
from langatlas_research.config import ResearchConfig
from langatlas_research.draft.debate_record import save_debate
from langatlas_research.draft.plan import build_plan_record, save_plan
from langatlas_research.instrument.replay import render_replay, replay_counterfactual
from langatlas_research.paths import research_config_path

TIER_A = {"scott-plp": type("S", (), {"tier": "A", "grounding": "", "locator_kinds": (),
                                      "csl": {}})()}


def _entry(summary, **over):
    return {"key": "static-typing", "from_candidates": ["static-typing"], "kind": "feature",
            "id": "static-typing", "name": "Static typing", "summary": summary, "layer": 2,
            "dimension": None, "cross_cutting": False, "aliases": [], "realizes": [],
            "evidence": [{"source": "scott-plp", "locator": "§7.2"}],
            "contested": ["merged-candidates"], "debate_id": "d-01-typing-001",
            "status": "minted", "note": "", "verification": None, **over}


def _verifier(by_summary):
    # `replay_counterfactual` only ever calls this to re-score the pre-challenge entry — the
    # post-challenge verdict comes straight from the plan's stored `verification` block, never
    # from a second call here. So there is exactly one claim to answer for, and no need (or
    # means — `claim.claim` for a node-definition fact is a sha256 of the text, never the
    # literal text) to distinguish it from another by inspecting the claim string.
    def _verify(ctx, conn, *, claim, citation, **kwargs):
        verdict = by_summary["overstated"]
        return PairVerdict(fact_id=claim.fact_id, source_id=citation.source_id,
                           locator=citation.locator, verdict=verdict, date="2026-09-20")
    return _verify


@pytest.fixture
def scenario(research_repo, signed_cycle):
    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="r", generated_at="t")
    plan["nodes"] = [_entry("Type checking happens before the program runs.",
                            verification={"fact_id": "f-post", "verdict": "verified",
                                          "admissible": True, "pairs": 1})]
    save_plan(plan, repo_root=research_repo)
    save_debate({"id": "d-01-typing-001", "cycle": 1, "theme": "typing",
                 "target": {"list": "nodes", "key": "static-typing"},
                 "opened": "2026-09-20", "runs": {"debate": "r1", "moderator": "r2"},
                 "triggers": ["merged-candidates"], "personas": {},
                 "pre_challenge": _entry("Static typing always prevents runtime errors."),
                 "messages": [{"seq": 1, "role": "proposer", "persona": "p", "text": "x"}],
                 "resolution": {"outcome": "converged-after-revision",
                                "disposition": "revise", "standing_dissent": False,
                                "rounds": 1, "upheld_challenges": ["scope"],
                                "rationale": "narrowed"}},
                repo_root=research_repo)
    return research_repo, signed_cycle


def test_the_counterfactual_shows_a_challenge_round_that_changed_the_verdict(fake_ctx,
                                                                            scenario):
    repo, cycle = scenario
    config = ResearchConfig.load(research_config_path(repo))
    rows = replay_counterfactual(fake_ctx, None, repo, cycle=cycle.number, config=config,
                                 deps=VerifyDeps(source_facts=TIER_A),
                                 verifier=_verifier({"overstated": "partial",
                                                     "narrow": "supported"}))
    assert len(rows) == 1
    row = rows[0]
    assert row.debate_id == "d-01-typing-001" and row.disposition == "revise"
    assert row.pre_verdict != row.post_verdict
    assert row.pre_admissible is False and row.post_admissible is True
    assert row.changed is True


def test_a_debate_the_verifier_cannot_tell_apart_is_reported_as_unchanged(fake_ctx,
                                                                          scenario):
    repo, cycle = scenario
    config = ResearchConfig.load(research_config_path(repo))
    rows = replay_counterfactual(fake_ctx, None, repo, cycle=cycle.number, config=config,
                                 deps=VerifyDeps(source_facts=TIER_A),
                                 verifier=_verifier({"overstated": "supported",
                                                     "narrow": "supported"}))
    assert rows[0].changed is False


def test_a_keep_debate_is_skipped_because_there_is_nothing_to_compare(fake_ctx, scenario):
    repo, cycle = scenario
    from langatlas_research.draft.debate_record import load_debate, save_debate as save

    debate = load_debate("d-01-typing-001", repo_root=repo)
    debate["resolution"].update(disposition="keep", outcome="resolved")
    save(debate, repo_root=repo)
    config = ResearchConfig.load(research_config_path(repo))
    assert replay_counterfactual(fake_ctx, None, repo, cycle=cycle.number, config=config,
                                 deps=VerifyDeps(source_facts=TIER_A),
                                 verifier=_verifier({"overstated": "partial",
                                                     "narrow": "supported"})) == []


def test_the_report_renders_a_markdown_table(fake_ctx, scenario):
    repo, cycle = scenario
    config = ResearchConfig.load(research_config_path(repo))
    rows = replay_counterfactual(fake_ctx, None, repo, cycle=cycle.number, config=config,
                                 deps=VerifyDeps(source_facts=TIER_A),
                                 verifier=_verifier({"overstated": "partial",
                                                     "narrow": "supported"}))
    report = render_replay(rows)
    assert "| debate |" in report and "d-01-typing-001" in report
    assert "1 of 1" in report
