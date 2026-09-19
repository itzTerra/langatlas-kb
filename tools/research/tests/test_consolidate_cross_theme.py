import pytest

from langatlas_pipeline.prompts import mint_prompt_version
from langatlas_pipeline.providers.claude_runs import AgentRunResult
from langatlas_research.config import ResearchConfig
from langatlas_research.consolidate.cross_theme import (
    cross_theme_leads, run_cross_theme, skip_reason, theme_membership,
)
from langatlas_research.consolidate.record import build_record
from langatlas_research.cycle import new_cycle, record_minted, sign_off
from langatlas_research.draft.minting import mint_items
from langatlas_research.draft.ontologist import StoreView
from langatlas_research.draft.plan import build_plan_record, save_plan
from langatlas_research.errors import DraftOutputInvalid
from langatlas_research.paths import research_config_path
from langatlas_research.schema import validate_research_record
from langatlas_validate.migrate import manifest_rel, render_manifest
from langatlas_validate.tombstones import render_tombstones

PROMPT_TEXT = ("---\nprompt_id: r6-cross-theme-test\nvariables: [theme_label, nodes, other_nodes,"
               " existing_edges, leads, edge_types, max_edges]\n---\n"
               "# system\n{{theme_label}} {{edge_types}} {{max_edges}}\n\n"
               "# user\n{{nodes}}\n{{other_nodes}}\n{{existing_edges}}\n{{leads}}\n")
STORE = StoreView(concepts=frozenset(),
                  features=frozenset({"static-typing", "type-inference", "ownership",
                                      "garbage-collection"}),
                  dimensions=frozenset())
NAMES = {"static-typing": "Static typing", "type-inference": "Type inference",
         "ownership": "Ownership", "garbage-collection": "Garbage collection"}


def _edge(frm, to, edge_type="influences", polarity="+"):
    return {"type": edge_type, "from": frm, "to": to, "polarity": polarity,
            "statement": f"{frm} shapes {to}.", "evidence": [{"chunk_id": "scott-plp#c00310"}]}


def _result(structured):
    return AgentRunResult(session_id="s", result_text="", structured_output=structured,
                          num_turns=3, is_error=False, tokens_in=1, tokens_out=1,
                          cost_usd=None, terminal_reason="completed")


@pytest.fixture
def config(research_repo):
    return ResearchConfig.load(research_config_path(research_repo))


@pytest.fixture
def prompt(tmp_path):
    return mint_prompt_version("r6-cross-theme-test", PROMPT_TEXT, root=tmp_path)


@pytest.fixture
def two_themes(research_repo, signed_cycle):
    cycle = record_minted(signed_cycle, ["static-typing", "type-inference"],
                          repo_root=research_repo)
    other = sign_off(new_cycle(2, "memory-management", repo_root=research_repo,
                               languages=("c",)), by="Dev", date="2026-10-01",
                     repo_root=research_repo)
    record_minted(other, ["ownership", "garbage-collection"], repo_root=research_repo)
    return cycle, build_plan_record(cycle=cycle, ontologist_run_id="r", generated_at="t"), \
        build_record(cycle=cycle, opened_at="t")


def _run(fake_ctx, research_repo, cycle, plan, record, fake_lookup, config, prompt):
    return run_cross_theme(fake_ctx, cycle, plan, record, repo_root=research_repo,
                           lookup=fake_lookup, config=config, prompt=prompt, store=STORE,
                           names=NAMES)


def test_membership_comes_from_the_cycles(research_repo, two_themes):
    assert theme_membership(research_repo) == {
        "static-typing": "typing", "type-inference": "typing",
        "ownership": "memory-management", "garbage-collection": "memory-management"}


def test_the_pass_appends_r6_edges_and_records_its_run(fake_ctx, research_repo, two_themes,
                                                       fake_lookup, config, prompt):
    cycle, plan, record = two_themes
    fake_ctx.claude_results.append(_result({"edges": [_edge("ownership", "static-typing")],
                                            "findings": []}))

    updated, record, _warnings = _run(fake_ctx, research_repo, cycle, plan, record,
                                      fake_lookup, config, prompt)

    [entry] = updated["edges"]
    assert (entry["key"], entry["pass"], entry["status"]) == (
        "ownership--influences--static-typing", "r6", "proposed")
    assert record["cross_theme"] == {"run": fake_ctx.run_id, "skipped": None,
                                     "edges": [entry["key"]]}
    assert validate_research_record(updated, "draft", repo_root=research_repo) == []
    user_prompt = fake_ctx.claude_calls[0][0]
    assert "garbage-collection" in user_prompt and "Memory management" in user_prompt


def test_an_edge_inside_one_theme_is_refused(fake_ctx, research_repo, two_themes, fake_lookup,
                                             config, prompt):
    cycle, plan, record = two_themes
    fake_ctx.claude_results.append(_result(
        {"edges": [_edge("type-inference", "static-typing", "requires", None)], "findings": []}))

    with pytest.raises(DraftOutputInvalid, match="does not cross"):
        _run(fake_ctx, research_repo, cycle, plan, record, fake_lookup, config, prompt)


def test_without_another_theme_the_pass_is_skipped_without_claude(fake_ctx, research_repo,
                                                                  signed_cycle, fake_lookup,
                                                                  config, prompt):
    cycle = record_minted(signed_cycle, ["static-typing"], repo_root=research_repo)
    plan = build_plan_record(cycle=cycle, ontologist_run_id="r", generated_at="t")

    _plan, record, _warnings = run_cross_theme(
        fake_ctx, cycle, plan, build_record(cycle=cycle, opened_at="t"),
        repo_root=research_repo, lookup=fake_lookup, config=config, prompt=prompt, store=STORE,
        names=NAMES)

    assert record["cross_theme"]["skipped"] == "no other theme has committed features yet"
    assert skip_reason(research_repo, cycle, store=STORE) is not None
    assert fake_ctx.claude_calls == []


def test_leads_gather_findings_and_requeued_edges(research_repo, two_themes):
    cycle, _plan, _record = two_themes
    other_plan = build_plan_record(
        cycle=sign_off(new_cycle(3, "concurrency", repo_root=research_repo, languages=("go",)),
                       by="Dev", date="2026-10-01", repo_root=research_repo),
        ontologist_run_id="r", generated_at="t")
    other_plan["findings"] = [{"kind": "cross-theme-edge",
                               "detail": "ownership enables data-race freedom", "keys": []}]
    save_plan(other_plan, repo_root=research_repo)
    manifest = {"migration_id": "0001-x", "date": "2026-10-01", "cycle": cycle.number,
                "ontology_version_before": "0.4.0", "rationale": "r",
                "dispositions": [{"op": "remove", "node": "a", "fact_remap": []}]}
    (research_repo / manifest_rel("0001-x")).parent.mkdir(parents=True)
    (research_repo / manifest_rel("0001-x")).write_text(render_manifest(manifest))
    (research_repo / "tombstones.yaml").write_text(render_tombstones([
        {"fact_id": "f-000000000001", "anchor": "edge.requires.a.b#exists", "action": "requeue",
         "reason": "removal", "superseded_by": [], "migration_id": "0001-x",
         "date": "2026-10-01"}]))

    leads = cross_theme_leads(research_repo, cycle=cycle)

    assert any("data-race freedom" in lead for lead in leads)
    assert any("edge.requires.a.b#exists" in lead and "0001-x" in lead for lead in leads)


def test_an_r6_edge_mints_under_its_own_prompt(research_repo, two_themes):
    cycle, plan, _record = two_themes
    entry = {"key": "ownership--influences--static-typing", "type": "influences",
             "from": "ownership", "to": "static-typing", "polarity": "+",
             "statement": "Ownership shapes static typing.",
             "evidence": [{"source": "scott-plp", "locator": "§7.2"}], "contested": [],
             "debate_id": None, "status": "verified", "note": "", "pass": "r6",
             "verification": {"fact_id": "f-000000000001", "verdict": "verified",
                              "admissible": True}}

    [draft] = mint_items({**plan, "edges": [entry]}, repo_root=research_repo, ctx_run_id="run",
                         prompt_version="", prompt_versions={"edges": "v-r4", "edges:r6": "v-r6"})

    assert (draft.proposer.agent, draft.proposer.prompt_version) == (
        "r6-cross-theme-edge-drafter", "v-r6")


def test_the_r4_edge_path_is_unchanged_by_the_refactor(fake_ctx, research_repo, two_themes,
                                                       fake_lookup):
    """`append_edges` without a pass writes the exact pre-refactor R4 entry: no `pass` key."""
    from langatlas_research.draft.edges import EdgeDrafterOut, append_edges

    _cycle, plan, _record = two_themes
    out = EdgeDrafterOut.model_validate({"edges": [_edge("ownership", "static-typing")]})

    updated, warnings = append_edges(fake_ctx, plan, out.edges, lookup=fake_lookup)

    [entry] = updated["edges"]
    assert "pass" not in entry and warnings == []
    assert list(entry) == ["key", "type", "from", "to", "polarity", "statement", "evidence",
                           "contested", "debate_id", "status", "verification", "note"]
    assert plan["edges"] == []


def test_malformed_model_output_is_a_typed_error(fake_ctx, research_repo, two_themes,
                                                 fake_lookup, config, prompt):
    from langatlas_research.errors import ResearchError

    cycle, plan, record = two_themes
    fake_ctx.claude_results.append(_result({"edges": "not a list"}))

    with pytest.raises(ResearchError):
        _run(fake_ctx, research_repo, cycle, plan, record, fake_lookup, config, prompt)


def test_an_edge_already_in_the_plan_is_refused(fake_ctx, research_repo, two_themes,
                                                fake_lookup, config, prompt):
    cycle, plan, record = two_themes
    fake_ctx.claude_results.append(_result({"edges": [_edge("ownership", "static-typing")]}))
    plan, record, _ = _run(fake_ctx, research_repo, cycle, plan, record, fake_lookup, config,
                           prompt)
    fake_ctx.claude_results.append(_result({"edges": [_edge("ownership", "static-typing")]}))

    with pytest.raises(DraftOutputInvalid, match="already in the carve plan"):
        _run(fake_ctx, research_repo, cycle, plan, record, fake_lookup, config, prompt)


def test_the_role_reads_its_model_from_config(config):
    assert config.consolidation.cross_theme_drafter.max_candidates == 40


def test_the_edges_command_skips_without_another_theme(research_repo, signed_cycle, capsys,
                                                       monkeypatch):
    from langatlas_research.cli import main
    from langatlas_research.consolidate.record import load_record, save_record

    monkeypatch.setattr("langatlas_research.consolidate.cross_theme.read_store",
                        lambda repo_root=None: STORE)
    cycle = record_minted(signed_cycle, ["static-typing"], repo_root=research_repo)
    save_plan(build_plan_record(cycle=cycle, ontologist_run_id="r", generated_at="t"),
              repo_root=research_repo)
    save_record(build_record(cycle=cycle, opened_at="t"), repo_root=research_repo)

    assert main(["--repo-root", str(research_repo), "consolidate", "edges", "1"]) == 0

    assert "skipped: no other theme has committed features yet" in capsys.readouterr().out
    assert load_record(cycle.slug, repo_root=research_repo)["cross_theme"]["skipped"]


def test_the_edges_command_writes_the_plan_and_the_record(fake_ctx, research_repo, two_themes,
                                                          fake_lookup, monkeypatch, capsys):
    from contextlib import contextmanager

    from langatlas_research.cli import main
    from langatlas_research.consolidate.record import load_record, save_record
    from langatlas_research.draft.plan import load_plan

    cycle, plan, record = two_themes
    save_plan(plan, repo_root=research_repo)
    save_record(record, repo_root=research_repo)
    fake_ctx.claude_results.append(_result({"edges": [_edge("ownership", "static-typing")],
                                            "findings": []}))

    @contextmanager
    def _connect(_dsn):
        yield object()

    @contextmanager
    def _start(**_kwargs):
        yield fake_ctx

    monkeypatch.setattr("langatlas_ingest.db.connect", _connect)
    monkeypatch.setattr("langatlas_ingest.config.IngestConfig.load",
                        classmethod(lambda cls: type("C", (), {"dsn": "x"})()))
    monkeypatch.setattr("langatlas_pipeline.providers.core.RunContext.start", _start)
    monkeypatch.setattr("langatlas_research.draft.ontologist.ontologist_tools",
                        lambda ctx, conn: ({}, ()))
    monkeypatch.setattr("langatlas_research.survey.chunks.db_chunk_lookup",
                        lambda conn: fake_lookup)
    monkeypatch.setattr("langatlas_research.consolidate.cross_theme.read_store",
                        lambda repo_root=None: STORE)

    assert main(["--repo-root", str(research_repo), "consolidate", "edges", "1"]) == 0

    [entry] = load_plan(cycle.slug, repo_root=research_repo)["edges"]
    assert (entry["key"], entry["pass"]) == ("ownership--influences--static-typing", "r6")
    assert load_record(cycle.slug, repo_root=research_repo)["cross_theme"]["edges"] == [
        entry["key"]]
    assert "1 cross-theme edge(s) proposed" in capsys.readouterr().out
