import subprocess
from dataclasses import replace

import pytest

from langatlas_commit.land import Landed
from langatlas_research.cli import main
from langatlas_research.consolidate.guard import check_settled
from langatlas_research.consolidate.lifecycle import r6_blockers, settle
from langatlas_research.consolidate.record import build_record, save_record
from langatlas_research.cycle import load_cycle, save_cycle
from langatlas_research.draft.plan import build_plan_record, save_plan
from langatlas_research.errors import ConsolidationMissing, DraftMissing, R6Incomplete, SignOffMissing
from langatlas_validate.migrate import render_manifest
from langatlas_validate.normalize import normalize_record


def _minted_node():
    return {"key": "static-typing", "from_candidates": ["static-typing"], "kind": "feature",
            "id": "static-typing", "name": "Static typing", "layer": 2, "dimension": None,
            "cross_cutting": False, "aliases": [], "realizes": [],
            "summary": "Type checking happens before the program runs.",
            "evidence": [{"source": "scott-plp", "locator": "§7.2"}], "contested": [],
            "debate_id": None, "status": "minted", "note": "",
            "verification": {"fact_id": "f-000000000001", "verdict": "verified",
                             "admissible": True}}


@pytest.fixture
def ready(research_repo, signed_cycle):
    cycle = replace(signed_cycle, status="r5-done", nodes_minted=("static-typing",))
    save_cycle(cycle, repo_root=research_repo)
    plan = build_plan_record(cycle=cycle, ontologist_run_id="run-o", generated_at="t")
    plan["nodes"] = [_minted_node()]
    save_plan(plan, repo_root=research_repo)
    record = {**build_record(cycle=cycle, opened_at="t"),
              "cross_theme": {"run": None, "skipped": "no other theme has committed features yet",
                              "edges": []}}
    save_record(record, repo_root=research_repo)
    return cycle, plan, record


class Lander:
    def __init__(self):
        self.calls = []

    def __call__(self, repo_root, rel, text, **kwargs):
        self.calls.append(rel)
        return Landed(commit_sha=f"sha{len(self.calls)}")


def test_settle_lands_three_files_and_marks_the_cycle(research_repo, ready):
    lander = Lander()

    settled, results = settle(1, repo_root=research_repo, by="Dev", date="2026-10-05",
                              lander=lander)

    assert lander.calls == ["research/drafts/01-typing.yaml",
                            "research/consolidations/01-typing.yaml",
                            "research/cycles/01-typing.yaml"]
    assert len(results) == 3
    stored = load_cycle(1, repo_root=research_repo)
    assert (stored.status, stored.settled) == ("settled", {"by": "Dev", "date": "2026-10-05"})
    assert stored.artifacts["consolidation"] == "research/consolidations/01-typing.yaml"
    assert settle(1, repo_root=research_repo, by="Dev", date="2026-10-06",
                  lander=lander) == (settled, [])


def test_every_blocker_is_reported_at_once(research_repo, ready):
    cycle, plan, record = ready
    for node_id in ("static-typing", "static-typing-2"):
        path = research_repo / "features" / f"{node_id}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(normalize_record(
            f"id: {node_id}\nslug: {node_id}\nname: Static typing\nlayer: 2\n"
            "summary:\n  text: x.\n  sources:\n    - source: s\n      locator: p. 1\n"
            "provenance:\n  claim_origin: source-derived\n", "feature"))
    record = {**record, "cross_theme": {"run": None, "skipped": None, "edges": []},
              "migrations": ["0001-x"]}
    plan = {**plan, "nodes": [{**_minted_node(), "status": "verified"}]}

    blockers = r6_blockers(cycle, plan, record, repo_root=research_repo)

    assert any("cross-theme" in b for b in blockers)
    assert any("static-typing" in b and "not landed" in b for b in blockers)
    assert any("unruled dedup candidate" in b for b in blockers)
    assert any("0001-x" in b for b in blockers)

    save_plan(plan, repo_root=research_repo)
    save_record(record, repo_root=research_repo)
    with pytest.raises(R6Incomplete, match="unruled dedup candidate"):
        settle(1, repo_root=research_repo, by="Dev", date="2026-10-05", lander=Lander())


def test_settle_refuses_a_cycle_that_has_not_finished_r5(research_repo, ready):
    cycle, plan, record = ready
    save_cycle(replace(cycle, status="r4-done"), repo_root=research_repo)

    with pytest.raises(R6Incomplete, match="r5-done"):
        settle(1, repo_root=research_repo, by="Dev", date="2026-10-05", lander=Lander())


def test_a_blocked_settle_lands_and_changes_nothing(research_repo, ready):
    cycle, plan, record = ready
    save_record({**record, "migrations": ["0001-x"]}, repo_root=research_repo)
    lander = Lander()

    with pytest.raises(R6Incomplete, match="0001-x"):
        settle(1, repo_root=research_repo, by="Dev", date="2026-10-05", lander=lander)

    assert lander.calls == []
    assert load_cycle(1, repo_root=research_repo).status == "r5-done"


def test_open_plan_entries_block(research_repo, ready):
    cycle, plan, record = ready
    save_plan({**plan, "nodes": [{**_minted_node(), "status": "verified"}]},
              repo_root=research_repo)

    with pytest.raises(R6Incomplete, match="static-typing.*not landed"):
        settle(1, repo_root=research_repo, by="Dev", date="d", lander=Lander())


@pytest.mark.parametrize("by", ["", "   ", None])
def test_settling_needs_a_named_developer(research_repo, ready, by):
    lander = Lander()

    with pytest.raises(R6Incomplete, match="--by"):
        settle(1, repo_root=research_repo, by=by, date="d", lander=lander)

    assert lander.calls == []


def test_settling_needs_the_sign_off(research_repo, ready):
    cycle, _plan, _record = ready
    save_cycle(replace(cycle, signed_off=None), repo_root=research_repo)

    with pytest.raises(SignOffMissing):
        settle(1, repo_root=research_repo, by="Dev", date="d", lander=Lander())


def test_a_missing_plan_or_record_is_a_typed_error(research_repo, ready):
    (research_repo / "research/consolidations/01-typing.yaml").unlink()
    with pytest.raises(ConsolidationMissing):
        settle(1, repo_root=research_repo, by="Dev", date="d", lander=Lander())
    (research_repo / "research/drafts/01-typing.yaml").unlink()
    with pytest.raises(DraftMissing):
        settle(1, repo_root=research_repo, by="Dev", date="d", lander=Lander())


def test_malformed_files_are_blockers_or_typed_errors_not_tracebacks(research_repo, ready,
                                                                     capsys):
    cycle, plan, record = ready
    blockers = r6_blockers(cycle, plan, {"cycle": 1}, repo_root=research_repo)
    assert any(b.startswith("consolidation record:") for b in blockers)

    (research_repo / "research/drafts/01-typing.yaml").write_text("a: [unclosed\n")
    assert main(["--repo-root", str(research_repo), "consolidate", "settle", "1",
                 "--by", "Dev"]) == 1
    assert "not valid YAML" in capsys.readouterr().err

    (research_repo / "research/drafts/01-typing.yaml").write_text("- just\n- a list\n")
    assert main(["--repo-root", str(research_repo), "consolidate", "settle", "1",
                 "--by", "Dev"]) == 1
    assert "mapping" in capsys.readouterr().err


def test_the_cli_requires_by(research_repo, ready, capsys):
    assert main(["--repo-root", str(research_repo), "consolidate", "settle", "1"]) == 1
    assert "--by" in capsys.readouterr().err
    assert load_cycle(1, repo_root=research_repo).status == "r5-done"


def test_an_interrupted_settle_says_what_landed_and_a_rerun_finishes(research_repo, ready):
    class FailsOnRecord(Lander):
        def __call__(self, repo_root, rel, text, **kwargs):
            if "consolidations" in rel:
                raise RuntimeError("push rejected")
            return super().__call__(repo_root, rel, text, **kwargs)

    with pytest.raises(R6Incomplete) as caught:
        settle(1, repo_root=research_repo, by="Dev", date="d", lander=FailsOnRecord())

    message = str(caught.value)
    assert "Landed before it: research/drafts/01-typing.yaml" in message
    assert "Not landed: research/consolidations/01-typing.yaml" in message
    assert load_cycle(1, repo_root=research_repo).status == "r5-done"

    settled, _ = settle(1, repo_root=research_repo, by="Dev", date="d", lander=Lander())
    assert settled.status == "settled"


def test_a_failed_cycle_landing_restores_the_unsettled_cycle(research_repo, ready):
    class RefusesCycle(Lander):
        def __call__(self, repo_root, rel, text, **kwargs):
            if "cycles" in rel:
                return "refused"
            return super().__call__(repo_root, rel, text, **kwargs)

    with pytest.raises(R6Incomplete, match="Landed before it: research/drafts.*consolidations"):
        settle(1, repo_root=research_repo, by="Dev", date="d", lander=RefusesCycle())

    stored = load_cycle(1, repo_root=research_repo)
    assert (stored.status, stored.settled) == ("r5-done", None)


# --- end to end against a real git repo with an origin --------------------------------------

def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout.strip()


FEATURE = normalize_record(
    "id: static-typing\nslug: static-typing\nname: Static typing\nlayer: 2\n"
    "summary:\n  text: Type checking happens before the program runs.\n"
    "  sources:\n    - source: scott-plp\n      locator: p. 1\n"
    "provenance:\n  claim_origin: source-derived\n", "feature")


@pytest.mark.git
def test_settle_lands_exactly_three_commits_and_the_guard_then_protects_the_theme(store_repo):
    from langatlas_research.cycle import new_cycle, sign_off
    repo = store_repo
    cycle = sign_off(new_cycle(1, "typing", repo_root=repo, languages=("python", "haskell")),
                     by="Dev", date="2026-09-20", repo_root=repo)
    cycle = replace(cycle, status="r5-done", nodes_minted=("static-typing",))
    save_cycle(cycle, repo_root=repo)
    (repo / "features" / "static-typing.yaml").write_text(FEATURE)
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "r5 done"], repo)
    _git(["push", "-q", "origin", "HEAD:main"], repo)
    base = _git(["rev-parse", "HEAD"], repo)

    plan = build_plan_record(cycle=cycle, ontologist_run_id="run-o", generated_at="t")
    plan["nodes"] = [_minted_node()]
    save_plan(plan, repo_root=repo)
    record = {**build_record(cycle=cycle, opened_at="t"),
              "cross_theme": {"run": None, "skipped": "no other theme", "edges": []}}
    save_record(record, repo_root=repo)
    # Task 8's run_migration leaves the record dirty: land it clean, then modify it as it does.
    manifest = "ontology/migrations/0001-x/manifest.yaml"
    (repo / manifest).parent.mkdir(parents=True)
    (repo / manifest).write_text(render_manifest(
        {"migration_id": "0001-x", "date": "2026-10-01", "cycle": 1,
         "ontology_version_before": "0.2.0", "rationale": "x",
         "dispositions": [{"op": "remove", "node": "ghost", "fact_remap": [
             {"match": {"anchor": "ghost#*"}, "action": "tombstone"}]}]}))
    _git(["add", manifest], repo)
    _git(["commit", "-q", "-m", "migration"], repo)
    _git(["push", "-q", "origin", "HEAD:main"], repo)
    base = _git(["rev-parse", "HEAD"], repo)
    save_record({**record, "migrations": ["0001-x"]}, repo_root=repo)

    settled, results = settle(1, repo_root=repo, by="Dev", date="2026-10-05")

    assert settled.status == "settled" and len(results) == 3
    commits = _git(["rev-list", "--reverse", f"{base}..HEAD"], repo).split()
    files = [_git(["show", "--name-only", "--format=", c], repo).split() for c in commits]
    assert files == [["research/drafts/01-typing.yaml"],
                     ["research/consolidations/01-typing.yaml"],
                     ["research/cycles/01-typing.yaml"]]
    assert _git(["rev-parse", "origin/main"], repo) == _git(["rev-parse", "HEAD"], repo)
    assert _git(["status", "--porcelain"], repo) == ""
    assert "0001-x" in _git(["show", "HEAD~1:research/consolidations/01-typing.yaml"], repo)
    assert load_cycle(1, repo_root=repo).status == "settled"

    # idempotent, no new commits
    assert settle(1, repo_root=repo, by="Dev", date="d")[1] == []
    assert _git(["rev-list", "--count", f"{base}..HEAD"], repo) == "3"

    # Task 9's guard now protects the theme
    (repo / "features" / "static-typing.yaml").unlink()
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "remove"], repo)
    [error] = check_settled(repo, base)
    assert "removes a record of settled theme 'typing'" in error
