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


def test_draft_mint_is_held_until_a_structure_review(research_repo, signed_cycle, capsys):
    from langatlas_research.paths import structure_review_path

    structure_review_path(research_repo).unlink()
    _plan(signed_cycle, research_repo, [_node()])
    assert main(["--repo-root", str(research_repo), "draft", "mint", "1"]) == 1
    assert "structure review" in capsys.readouterr().err


def test_draft_mint_is_held_before_any_database_connection(
        research_repo, signed_cycle, monkeypatch, capsys):
    import langatlas_ingest.db
    from langatlas_research.paths import structure_review_path

    def _no_connect(*_args, **_kwargs):
        raise AssertionError("the mint gate must fire before a database connection")

    monkeypatch.setattr(langatlas_ingest.db, "connect", _no_connect)
    structure_review_path(research_repo).unlink()
    _plan(signed_cycle, research_repo, [_node()])
    assert main(["--repo-root", str(research_repo), "draft", "mint", "1"]) == 1
    assert "structure review" in capsys.readouterr().err


def _fake_debate_environment(monkeypatch, minted):
    """Stubs everything `draft debate` reaches for except the branch under test."""
    import contextlib
    from types import SimpleNamespace

    import langatlas_ingest.config
    import langatlas_ingest.db
    import langatlas_pipeline.providers.core
    import langatlas_research.config
    import langatlas_research.draft.contradictions
    import langatlas_research.draft.debate
    import langatlas_research.draft.ontologist
    import langatlas_research.survey.chunks
    import langatlas_research.survey.claude

    @contextlib.contextmanager
    def _connect(_dsn):
        yield object()

    @contextlib.contextmanager
    def _start(**_kwargs):
        yield SimpleNamespace(manifest=SimpleNamespace())

    debate = {"id": "d-01-typing-001",
              "resolution": {"disposition": "resolved", "outcome": "kept",
                             "standing_dissent": False}}
    debate_config = SimpleNamespace(max_debates_per_cycle=5, proposer=None, moderator=None)
    monkeypatch.setattr(langatlas_ingest.db, "connect", _connect)
    monkeypatch.setattr(langatlas_ingest.config.IngestConfig, "load",
                        staticmethod(lambda *_a, **_k: SimpleNamespace(dsn="x")))
    monkeypatch.setattr(langatlas_research.config.ResearchConfig, "load",
                        staticmethod(lambda *_a, **_k: SimpleNamespace(
                            draft=SimpleNamespace(debate=debate_config))))
    monkeypatch.setattr(langatlas_research.survey.chunks, "db_chunk_lookup", lambda _c: None)
    monkeypatch.setattr(langatlas_research.survey.claude, "role_budget", lambda _r: None)
    monkeypatch.setattr(langatlas_pipeline.providers.core.RunContext, "start",
                        staticmethod(_start))
    monkeypatch.setattr(langatlas_research.draft.ontologist, "ontologist_tools",
                        lambda _ctx, _conn: (None, None))
    monkeypatch.setattr(langatlas_research.draft.debate, "run_debate",
                        lambda _ctx, _cycle, plan, _key, **_kw: (plan, debate))

    def _mint(_debate, *, repo_root):
        minted.append(_debate["id"])
        return "c-1"

    monkeypatch.setattr(langatlas_research.draft.contradictions,
                        "mint_debate_contradiction", _mint)


def test_draft_debate_skips_the_contradiction_mint_while_the_gate_is_closed(
        research_repo, signed_cycle, monkeypatch):
    from langatlas_research.paths import structure_review_path

    minted = []
    _fake_debate_environment(monkeypatch, minted)
    structure_review_path(research_repo).unlink()
    _plan(signed_cycle, research_repo, [_node()])
    assert main(["--repo-root", str(research_repo), "draft", "debate", "1",
                 "--key", "type-system"]) == 0
    assert minted == []


def test_draft_debate_mints_the_contradiction_once_the_gate_is_open(
        research_repo, signed_cycle, monkeypatch):
    minted = []
    _fake_debate_environment(monkeypatch, minted)
    _plan(signed_cycle, research_repo, [_node()])
    assert main(["--repo-root", str(research_repo), "draft", "debate", "1",
                 "--key", "type-system"]) == 0
    assert minted == ["d-01-typing-001"]


def test_draft_status_shows_why_a_carve_is_blocked(research_repo, signed_cycle, capsys):
    _plan(signed_cycle, research_repo,
          [_node(blocked="structure", block_reason="no edge type fits", contested=[]),
           _node(key="fine", id="fine", contested=[])])
    assert main(["--repo-root", str(research_repo), "draft", "status", "1"]) == 0
    lines = capsys.readouterr().out.splitlines()
    blocked = next(line for line in lines if "type-system" in line)
    assert "blocked (no edge type fits)" in blocked
    assert "blocked" not in next(line for line in lines if "fine" in line)
