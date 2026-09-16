"""Stage 3C's exit condition, end to end against a real git repo and the real commit protocol.

No provider: the ontologist, the debate roles and the edge drafter are driven through `FakeCtx`
with scripted structured output, and the verifier is injected. What this proves is the part that
has to be true regardless of what any model says — that a carve plan becomes committed records
only through the gate, in reference order, one commit per record, with the debate recorded."""
import subprocess

import pytest
from ruamel.yaml import YAML

from langatlas_ingest.verify.pipeline import VerifyDeps
from langatlas_ingest.verify.verdicts import PairVerdict
from langatlas_research.config import ResearchConfig
from langatlas_research.cycle import advance, load_cycle, new_cycle, save_cycle, sign_off
from langatlas_research.draft.contested import mark_contested, open_carves
from langatlas_research.draft.debate import DebatePrompts, run_debate
from langatlas_research.draft.debate_record import load_debate
from langatlas_research.draft.finalize import finalize_r4
from langatlas_research.draft.gate import verify_plan
from langatlas_research.draft.minting import mint_plan
from langatlas_research.draft.plan import find_entry, load_plan, save_plan
from langatlas_research.draft.ontologist import StoreView, run_ontologist
from langatlas_research.errors import NotAdmissible, UndebatedCarve
from langatlas_research.paths import research_config_path

_yaml = YAML(typ="safe")

pytestmark = pytest.mark.git

TIER_A = {"scott-plp": type("S", (), {"id": "scott-plp", "tier": "A", "grounding": "",
                                      "locator_kinds": (), "csl": {}})(),
          "pierce-tapl-2002": type("S", (), {"id": "pierce-tapl-2002", "tier": "A",
                                             "grounding": "", "locator_kinds": (),
                                             "csl": {}})()}


def _supported(ctx, conn, *, claim, citation, **kwargs):
    return PairVerdict(fact_id=claim.fact_id, source_id=citation.source_id,
                       locator=citation.locator, verdict="supported", date="2026-09-20")


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


def test_a_signed_cycle_carries_a_plan_through_debate_gate_and_mint(
        store_repo, fake_ctx, fake_lookup, monkeypatch, tmp_path):
    repo = store_repo
    (repo / "config").mkdir(exist_ok=True)
    (repo / "config" / "research.yaml").write_text(
        research_config_path().read_text())
    config = ResearchConfig.load(research_config_path(repo))

    cycle = sign_off(new_cycle(1, "typing", repo_root=repo, languages=("python",)),
                     by="dev", date="2026-09-20", repo_root=repo)
    cycle = advance(cycle, "r3-done")
    save_cycle(cycle, repo_root=repo)

    # --- R4: the ontologist -------------------------------------------------------
    from langatlas_pipeline.prompts import mint_prompt_version
    from langatlas_pipeline.providers.claude_runs import AgentRunResult

    def _result(structured):
        return AgentRunResult(session_id="s", result_text="", structured_output=structured,
                              num_turns=1, is_error=False, tokens_in=1, tokens_out=1,
                              cost_usd=None, terminal_reason="completed")

    ontologist_prompt = mint_prompt_version(
        "exit-ontologist",
        "---\nprompt_id: exit-ontologist\nvariables: [theme_label, theme_summary, layers,"
        " dimensions, committed_nodes, max_nodes, candidates]\n---\n"
        "# system\n{{theme_label}}{{theme_summary}}{{layers}}{{dimensions}}"
        "{{committed_nodes}}{{max_nodes}}\n\n# user\n{{candidates}}\n", root=tmp_path)

    survey = {"candidates": [
        {"key": "type-system", "name": "Type system", "gloss": "g", "kind_hint": "concept",
         "origin": "corpus", "aliases": [],
         "evidence": [{"chunk_id": "pierce-tapl-2002#c00022",
                       "source_id": "pierce-tapl-2002", "locator": "§1.1"}]},
        {"key": "static-typing", "name": "Static typing", "gloss": "g",
         "kind_hint": "feature", "origin": "corpus", "aliases": [],
         "evidence": [{"chunk_id": "scott-plp#c00310", "source_id": "scott-plp",
                       "locator": "§7.2"}]}]}

    fake_ctx.claude_results.append(_result({
        "nodes": [
            {"key": "type-system", "id": "type-system", "kind": "concept",
             "from_candidates": ["type-system"], "name": "Type system",
             "summary": "What types exist in a language.",
             # Two distinct sources, matching the single-source trigger convention already
             # used by tools/research/tests/test_draft_contested.py's `_node()` helper — a
             # concept carrying only one source would be flagged `single-source` and become
             # a third open carve this test never debates or waives (controller ruling,
             # 2026-09-16: contested.py's trigger makes no concept/feature distinction and
             # is correct as shipped; this fixture was under-specified).
             "evidence": [{"chunk_id": "pierce-tapl-2002#c00022"},
                          {"chunk_id": "scott-plp#c00310"}], "note": "parent"},
            {"key": "static-typing", "id": "static-typing", "kind": "feature",
             "from_candidates": ["static-typing", "type-checking"], "name": "Static typing",
             "layer": 3, "dimension": "type-checking-discipline",
             "realizes": ["type-system"],
             "summary": "Type checking happens before the program runs.",
             "evidence": [{"chunk_id": "scott-plp#c00310"},
                          {"chunk_id": "pierce-tapl-2002#c00022"}],
             "note": "one node per discipline"}],
        "dimensions": [{"key": "type-checking-discipline", "slug": "type-checking-discipline",
                        "label": "Type checking discipline",
                        "values": ["static", "dynamic", "gradual"],
                        "exclusivity": "exclusive", "applies_to": ["general-purpose"],
                        "note": "the axis"}],
        "findings": []}))

    plan, _ = run_ontologist(fake_ctx, cycle, repo_root=repo, survey=survey,
                             lookup=fake_lookup, config=config, prompt=ontologist_prompt)
    plan = mark_contested(plan, repo_root=repo)
    save_plan(plan, repo_root=repo)

    # Two triggers: the merged carve and the brand-new dimension.
    assert set(open_carves(plan)) == {"static-typing", "type-checking-discipline"}

    # --- the mint refuses to run over an undebated contested carve ------------------
    with pytest.raises(UndebatedCarve):
        mint_plan(plan, repo_root=repo, cycle=cycle, chat_run_id="x", prompt_version="")

    # --- the debates ---------------------------------------------------------------
    prompts = DebatePrompts(
        proposer=mint_prompt_version(
            "exit-proposer", "---\nprompt_id: exit-proposer\nvariables: [theme_label,"
            " entry_kind, entry, triggers, challenges]\n---\n# system\n{{theme_label}}"
            "{{entry_kind}}{{triggers}}\n\n# user\n{{entry}}{{challenges}}\n", root=tmp_path),
        challenger=mint_prompt_version(
            "exit-challenger", "---\nprompt_id: exit-challenger\nvariables: [theme_label,"
            " persona, entry_kind, entry, triggers, proposer_statement, challenge_types,"
            " max_challenges]\n---\n# system\n{{theme_label}}{{persona}}{{entry_kind}}"
            "{{challenge_types}}{{max_challenges}}\n\n# user\n{{entry}}{{triggers}}"
            "{{proposer_statement}}\n", root=tmp_path),
        moderator=mint_prompt_version(
            "exit-moderator", "---\nprompt_id: exit-moderator\nvariables: [theme_label,"
            " entry_kind, entry, triggers, transcript, dispositions]\n---\n"
            "# system\n{{theme_label}}{{entry_kind}}{{dispositions}}\n\n"
            "# user\n{{entry}}{{triggers}}{{transcript}}\n", root=tmp_path))

    for key in ("static-typing", "type-checking-discipline"):
        moderator_ctx = type(fake_ctx)(run_id=f"mod-{key}")
        moderator_ctx.claude_results.append(_result(
            {"disposition": "keep", "standing_dissent": False, "upheld_challenges": [],
             "rationale": "the carve is supported by the cited passages"}))
        fake_ctx.claude_results.extend([
            _result({"text": "my case"}), _result({"text": "no objection"}),
            _result({"text": "no objection"}), _result({"text": "nothing to add"})])
        plan, debate = run_debate(fake_ctx, cycle, plan, key, repo_root=repo, config=config,
                                  lookup=fake_lookup, moderator_ctx=moderator_ctx,
                                  prompts=prompts, today="2026-09-20")
        assert load_debate(debate["id"], repo_root=repo)["resolution"]["rounds"] == 0
    save_plan(plan, repo_root=repo)
    assert open_carves(plan) == []

    # --- the gate ------------------------------------------------------------------
    plan, results = verify_plan(fake_ctx, None, plan, repo_root=repo, config=config,
                                lookup=fake_lookup,
                                deps=VerifyDeps(source_facts=TIER_A), verifier=_supported)
    save_plan(plan, repo_root=repo)
    assert {r.key for r in results} == {"type-system", "static-typing"}
    assert all(r.admissible for r in results)

    # --- the mint ------------------------------------------------------------------
    plan, landed = mint_plan(plan, repo_root=repo, cycle=cycle, chat_run_id="run-mint",
                             prompt_version="v-test")
    save_plan(plan, repo_root=repo)

    assert [minted.path for minted, _ in landed] == [
        "ontology/taxonomy/dimensions.yaml", "concepts/type-system.yaml",
        "features/static-typing.yaml"]
    assert (repo / "features" / "static-typing.yaml").exists()
    feature = _yaml.load((repo / "features" / "static-typing.yaml").read_text())
    assert feature["dimension"] == "type-checking-discipline"
    assert feature["provenance"]["debate_id"].startswith("d-01-typing-")
    assert feature["summary"]["sources"][0]["source"] in TIER_A

    # one commit per record (D36)
    subjects = _git(["log", "--format=%s", "-4"], repo).splitlines()
    assert subjects[:3] == ["land features/static-typing.yaml",
                            "land concepts/type-system.yaml",
                            "land ontology/taxonomy/dimensions.yaml"]

    # --- finalize ------------------------------------------------------------------
    updated, _results = finalize_r4(1, repo_root=repo)
    assert updated.status == "r4-done"
    assert set(updated.nodes_minted) == {"type-system", "static-typing",
                                         "type-checking-discipline"}
    assert load_cycle(1, repo_root=repo).artifacts["draft"] == \
        "research/drafts/01-typing.yaml"
    assert len(load_cycle(1, repo_root=repo).artifacts["debates"]) == 2


def test_a_carve_the_gate_refuses_never_reaches_git(store_repo, fake_ctx, fake_lookup):
    (store_repo / "config").mkdir(exist_ok=True)
    (store_repo / "config" / "research.yaml").write_text(research_config_path().read_text())
    config = ResearchConfig.load(research_config_path(store_repo))
    cycle = sign_off(new_cycle(1, "typing", repo_root=store_repo, languages=("python",)),
                     by="dev", date="2026-09-20", repo_root=store_repo)

    from langatlas_research.draft.plan import build_plan_record

    plan = build_plan_record(cycle=cycle, ontologist_run_id="r", generated_at="t")
    plan["nodes"] = [{"key": "type-system", "from_candidates": ["type-system"],
                      "kind": "concept", "id": "type-system", "name": "Type system",
                      "summary": "Everything is a type.",
                      "evidence": [{"source": "scott-plp", "locator": "§7.2"},
                                   {"source": "pierce-tapl-2002", "locator": "§1.1"}],
                      "contested": [], "debate_id": None, "status": "proposed",
                      "verification": None, "note": ""}]

    def _unsupported(ctx, conn, *, claim, citation, **kwargs):
        return PairVerdict(fact_id=claim.fact_id, source_id=citation.source_id,
                           locator=citation.locator, verdict="unsupported",
                           date="2026-09-20")

    plan, _ = verify_plan(fake_ctx, None, plan, repo_root=store_repo, config=config,
                          lookup=fake_lookup, deps=VerifyDeps(source_facts=TIER_A),
                          verifier=_unsupported)
    assert find_entry(plan, "type-system")[1]["verification"]["admissible"] is False
    with pytest.raises(NotAdmissible):
        mint_plan(plan, repo_root=store_repo, cycle=cycle, chat_run_id="x",
                  prompt_version="")
    assert not (store_repo / "concepts" / "type-system.yaml").exists()
