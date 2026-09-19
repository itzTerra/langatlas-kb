"""Stage 3F's exit path on a throwaway repository: settle, refuse, migrate, replay, resolve,
report — every 3F piece touching the next, with the real commit protocol and no provider."""
import shutil
import subprocess
from dataclasses import replace

import pytest

from langatlas_commit.land import Landed
from langatlas_coverage.dossier import build_dossier, gather, render_dossier
from langatlas_coverage.gaps import gaps, render_gaps
from langatlas_coverage.metrics import load_store
from langatlas_coverage.report import main as coverage_main
from langatlas_ingest.verify.pipeline import VerifyDeps
from langatlas_ingest.verify.sources import SourceFacts
from langatlas_ingest.verify.verdicts import PairVerdict
from langatlas_research.cli import main as research_main
from langatlas_research.config import ResearchConfig
from langatlas_research.consolidate.guard import check_settled
from langatlas_research.consolidate.lifecycle import open_r6
from langatlas_research.consolidate.migration import draft_manifest, run_migration, write_draft
from langatlas_research.consolidate.record import load_record, save_record
from langatlas_research.cycle import load_cycle, new_cycle, save_cycle, settle_cycle, sign_off
from langatlas_research.draft.plan import build_plan_record, save_plan
from langatlas_research.paths import REPO_ROOT, ensure_layout, research_config_path
from langatlas_validate.compile import derive_facts
from langatlas_validate.gitrefs import show
from langatlas_validate.ids import compose_edge_id
from langatlas_validate.normalize import normalize_record
from langatlas_validate.redirects import load_redirects
from langatlas_validate.replay import replay_since
from langatlas_validate.store import iter_store_records, validate_store
from langatlas_validate.tombstones import (
    TOMBSTONES_REL, check_append_only, load_tombstones, parse_tombstones, resolve_fact,
)

pytestmark = pytest.mark.git

_CITE = "  sources:\n    - source: s\n      locator: p. 1\n"
_PROVENANCE = "provenance:\n  claim_origin: source-derived\n"


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _commit_push(repo, message):
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", message], repo)
    _git(["push", "-q", "origin", "HEAD:main"], repo)
    return _git(["rev-parse", "HEAD"], repo).stdout.strip()


def _write(repo, rel, text, kind=None):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalize_record(text, kind) if kind else text)


@pytest.fixture
def repo(tmp_path):
    origin, clone, hooks = tmp_path / "origin.git", tmp_path / "clone", tmp_path / "no-hooks"
    hooks.mkdir()
    _git(["init", "-q", "--bare", "-b", "main", str(origin)], tmp_path)
    _git(["clone", "-q", str(origin), str(clone)], tmp_path)
    for key, value in (("user.email", "bot@example.com"), ("user.name", "bot"),
                       ("core.hooksPath", str(hooks)), ("commit.gpgsign", "false")):
        _git(["config", key, value], clone)
    for rel in ("research/themes.yaml", "config/research.yaml", "ontology/VERSION",
                "ontology/taxonomy/dimensions.yaml", "ontology/taxonomy/qualities.yaml",
                "ontology/taxonomy/layers.yaml", "ontology/taxonomy/edge-types.yaml",
                "languages/_registry.yaml"):
        _write(clone, rel, (REPO_ROOT / rel).read_text())
    shutil.copytree(REPO_ROOT / "research" / "schema", clone / "research" / "schema")
    _write(clone, "contradictions.yaml", "contradictions: []\n")
    ensure_layout(clone)
    for node in ("alpha", "beta", "gamma"):
        _write(clone, f"features/{node}.yaml",
               f"id: {node}\nslug: {node}\nname: {node.title()}\nlayer: 2\n"
               f"summary:\n  text: {node} is a feature.\n" + _CITE + _PROVENANCE, "feature")
    _write(clone, "edges/alpha/requires--beta.yaml",
           f"id: {compose_edge_id('requires', 'alpha', 'beta')}\ntype: requires\nfrom: alpha\n"
           "to: beta\nstatement:\n  text: alpha requires beta.\n" + _CITE + _PROVENANCE, "edge")
    _commit_push(clone, "seed")
    return clone


_MINTED_NODE = {
    "key": "pooling", "from_candidates": ["pooling"], "kind": "feature", "id": "pooling",
    "name": "Pooling", "layer": 2, "dimension": None, "cross_cutting": False, "aliases": [],
    "realizes": [], "summary": "Objects are reused.",
    "evidence": [{"source": "s", "locator": "p. 1"}], "contested": [], "debate_id": None,
    "status": "minted", "note": "",
    "verification": {"fact_id": "f-000000000001", "verdict": "verified", "admissible": True}}


class Ctx:
    run_id = "2026-10-03-r6-migrate-02-memory-management-01"


def _supported(ctx, conn, *, claim, citation, **kwargs):
    return PairVerdict(fact_id=claim.fact_id, source_id=citation.source_id,
                       locator=citation.locator, verdict="supported", run_id=ctx.run_id,
                       date="2026-10-03")


def _live(repo):
    return {fact["anchor"]: fact["fact_id"]
            for fact in derive_facts(list(iter_store_records(repo)))}


def test_the_3f_exit_path(repo, tmp_path):
    # 1. Cycle 1 settles over alpha, beta, gamma and their edge.
    typing = sign_off(new_cycle(1, "typing", repo_root=repo, languages=("python",)),
                      by="Dev", date="2026-10-01", repo_root=repo)
    typing = replace(typing, status="r5-done",
                     nodes_minted=("alpha", "beta", "gamma", "edge.requires.alpha.beta"))
    save_cycle(settle_cycle(typing, by="Dev", date="2026-10-02"), repo_root=repo)
    settled_at = _commit_push(repo, "settle typing")

    # 2. A hand restructure of the settled theme is refused by the guard.
    (repo / "edges" / "alpha" / "requires--beta.yaml").unlink()
    _git(["commit", "-q", "-am", "hand edit"], repo)
    assert any("settled theme 'typing'" in e for e in check_settled(repo, settled_at))
    _git(["reset", "-q", "--hard", settled_at], repo)

    # 3. The ceremony: cycle 2's R6 merges settled alpha into gamma through a manifest.
    memory = sign_off(new_cycle(2, "memory-management", repo_root=repo, languages=("c",)),
                      by="Dev", date="2026-10-03", repo_root=repo)
    save_cycle(replace(memory, status="r5-done"), repo_root=repo)
    open_r6(2, repo_root=repo, opened_at="2026-10-03T09:00:00Z")
    old_definition = _live(repo)["alpha#summary"]
    manifest = draft_manifest(repo, {"op": "merge", "from": ["alpha"], "to": "gamma"},
                              cycle=memory, date="2026-10-03", rationale="alpha duplicates gamma",
                              slug="merge-alpha")
    assert manifest["settled_themes"] == ["typing"]
    write_draft(repo, manifest)
    deps = VerifyDeps(source_facts={"s": SourceFacts(id="s", tier="A", grounding="spec",
                                                     locator_kinds=(), csl={})})
    _plan, results, outcome = run_migration(
        Ctx(), None, memory, manifest["migration_id"], repo_root=repo,
        config=ResearchConfig.load(research_config_path(repo)), deps=deps, verifier=_supported)
    assert isinstance(outcome, Landed)
    assert [result.key for result in results] == ["edge.requires.gamma.beta"]

    # 4. CI's three history checks and the store gate all pass on the migration commit.
    assert [result.errors for result in replay_since(repo, settled_at)] == [()]
    assert check_settled(repo, settled_at) == []
    live = _live(repo)
    assert check_append_only(parse_tombstones(show(repo, settled_at, TOMBSTONES_REL)),
                             load_tombstones(repo), live_after=set(live.values())) == []
    assert validate_store(repo) == []

    # 5. The dead definition resolves to gamma's; alpha's old URL redirects to gamma.
    resolution = resolve_fact(old_definition, entries=load_tombstones(repo),
                              live=set(live.values()))
    assert (resolution.status, resolution.successors) == ("superseded", (live["gamma#summary"],))
    assert load_redirects(repo) == {"alpha": "gamma"}

    # 6. The dossier renders its five items and counts the settled-theme migration.
    items = build_dossier(gather(repo, ledger_path=tmp_path / "no-ledger.sqlite",
                                 cost_log=tmp_path / "no-cost.jsonl"))
    assert [item.key for item in items] == ["sourcing-integrity", "reality-checks", "churn",
                                            "graph-health", "pipeline-readiness"]
    assert "Migrations: 1 total, 1 touching a settled theme" in items[2].lines
    assert "All bars are advisory" in render_dossier(items)
    assert "near-meaningless" in render_gaps(gaps(load_store(repo)), min_instances=2,
                                             instances_total=0)


def test_settle_after_a_migration_lands_the_record_and_needs_by(repo, capsys):
    """The R6 tail: the migration leaves the consolidation record modified (uncommitted);
    `consolidate settle --by` lands plan, record and cycle, and refuses to run without --by."""
    typing = sign_off(new_cycle(1, "typing", repo_root=repo, languages=("python",)),
                      by="Dev", date="2026-10-01", repo_root=repo)
    typing = replace(typing, status="r5-done",
                     nodes_minted=("alpha", "beta", "gamma", "edge.requires.alpha.beta"))
    save_cycle(settle_cycle(typing, by="Dev", date="2026-10-02"), repo_root=repo)
    settled_at = _commit_push(repo, "settle typing")
    memory = sign_off(new_cycle(2, "memory-management", repo_root=repo, languages=("c",)),
                      by="Dev", date="2026-10-03", repo_root=repo)
    memory = replace(memory, status="r5-done")
    save_cycle(memory, repo_root=repo)
    plan = build_plan_record(cycle=memory, ontologist_run_id="run-o", generated_at="t")
    plan["nodes"] = [_MINTED_NODE]
    save_plan(plan, repo_root=repo)
    _cycle, record = open_r6(2, repo_root=repo, opened_at="2026-10-03T09:00:00Z")
    save_record({**record, "cross_theme": {"run": None, "skipped": "test", "edges": []}},
                repo_root=repo)
    manifest = draft_manifest(repo, {"op": "merge", "from": ["alpha"], "to": "gamma"},
                              cycle=memory, date="2026-10-03", rationale="alpha duplicates gamma",
                              slug="merge-alpha")
    # A drafted merge touches no facts at draft time; the interpreter derives the remap.
    write_draft(repo, manifest)
    deps = VerifyDeps(source_facts={"s": SourceFacts(id="s", tier="A", grounding="spec",
                                                     locator_kinds=(), csl={})})
    _plan, _results, outcome = run_migration(
        Ctx(), None, memory, manifest["migration_id"], repo_root=repo,
        config=ResearchConfig.load(research_config_path(repo)), deps=deps, verifier=_supported)
    assert isinstance(outcome, Landed)
    assert "research/consolidations/02-memory-management.yaml" in _git(
        ["status", "--porcelain"], repo).stdout          # left for the developer to land

    argv = ["--repo-root", str(repo), "consolidate", "settle", "2"]
    assert research_main(argv) != 0                       # no --by: the developer's act
    assert load_cycle(2, repo_root=repo).status == "r5-done"
    capsys.readouterr()
    assert research_main([*argv, "--by", "Dev", "--date", "2026-10-04"]) == 0
    assert load_cycle(2, repo_root=repo).settled == {"by": "Dev", "date": "2026-10-04"}
    assert load_record("02-memory-management", repo_root=repo)["migrations"] == [
        manifest["migration_id"]]
    assert _git(["status", "--porcelain"], repo).stdout == ""      # everything landed
    assert check_settled(repo, settled_at) == []
    assert [result.errors for result in replay_since(repo, settled_at)] == [()]


def test_dossier_and_gaps_never_traceback_on_missing_or_corrupt_inputs(repo, tmp_path, capsys):
    """Missing inputs read as no-data; a corrupt one is exit 2 with a message, not a trace."""
    args = ["--repo-root", str(repo)]
    dossier = [*args, "dossier", "--ledger", str(tmp_path / "no-ledger.sqlite"),
               "--cost-log", str(tmp_path / "no-cost.jsonl")]
    assert coverage_main(dossier) == 0
    out = capsys.readouterr().out
    assert "| Sourcing integrity | no-data |" in out
    assert "| Pipeline readiness | not-met |" in out
    assert "Verifier calibration: missing" in out

    calibration = repo / "benchmarks" / "d24-verifier" / "calibration.json"
    calibration.parent.mkdir(parents=True)
    calibration.write_text("{not json")
    assert coverage_main(dossier) == 2
    captured = capsys.readouterr()
    assert "error:" in captured.err and "Traceback" not in captured.err

    calibration.write_text('{"thresholds_met": false}')
    assert coverage_main(dossier) == 0
    out = capsys.readouterr().out
    assert "thresholds NOT met" in out and "| Pipeline readiness | not-met |" in out

    (repo / "features" / "alpha.yaml").write_text("id: [unterminated\n")
    assert coverage_main([*args, "gaps"]) == 2
    assert "Traceback" not in capsys.readouterr().err
