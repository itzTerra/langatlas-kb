import subprocess
from dataclasses import replace

import pytest
from ruamel.yaml import YAML

from langatlas_commit.land import land_changeset
from langatlas_ingest.verify.pipeline import VerifyDeps
from langatlas_ingest.verify.verdicts import PairVerdict
from langatlas_research.config import ResearchConfig
from langatlas_research.consolidate.lifecycle import open_r6
from langatlas_research.consolidate.migration import (
    draft_manifest, next_migration_id, run_migration, write_draft,
)
from langatlas_research.consolidate.record import load_record
from langatlas_research.cycle import new_cycle, save_cycle, sign_off
from langatlas_research.errors import ConsolidationInvalid, MigrationRecordNotUpdated, MigrationRefused
from langatlas_research.paths import REPO_ROOT, research_config_path
from langatlas_validate.ids import compose_edge_id
from langatlas_validate.migrate import (
    check_plan, load_manifest, manifest_rel, plan_migration,
)
from langatlas_validate.normalize import normalize_record

pytestmark = pytest.mark.git
_safe = YAML(typ="safe")
SOURCE_FACTS = {"scott-plp": type("S", (), {"id": "scott-plp", "tier": "A",
                                            "grounding": "third-party-reference",
                                            "locator_kinds": (), "csl": {},
                                            "language_version": ""})()}


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _write(repo, rel, text, kind):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalize_record(text, kind))


def _cite(indent):
    return f"{indent}sources:\n{indent}  - source: scott-plp\n{indent}    locator: p. 1\n"


def feature(repo, node_id):
    _write(repo, f"features/{node_id}.yaml",
           f"id: {node_id}\nslug: {node_id}\nname: {node_id.title()}\nlayer: 2\n"
           f"summary:\n  text: {node_id} is a feature.\n" + _cite("  ")
           + "provenance:\n  claim_origin: source-derived\n", "feature")


def edge(repo, edge_type, frm, to):
    _write(repo, f"edges/{frm}/{edge_type}--{to}.yaml",
           f"id: {compose_edge_id(edge_type, frm, to)}\ntype: {edge_type}\nfrom: {frm}\nto: {to}\n"
           f"statement:\n  text: {frm} {edge_type} {to}.\n" + _cite("  ")
           + "provenance:\n  claim_origin: source-derived\n", "edge")


@pytest.fixture
def seeded(store_repo):
    """alpha, beta, gamma, delta and two edges out of alpha, pushed; cycle 1 at r5-done with
    its consolidation record open."""
    (store_repo / "config").mkdir(exist_ok=True)
    (store_repo / "config" / "research.yaml").write_text(
        (REPO_ROOT / "config" / "research.yaml").read_text())
    for node_id in ("alpha", "beta", "gamma", "delta"):
        feature(store_repo, node_id)
    edge(store_repo, "requires", "alpha", "beta")
    edge(store_repo, "enables", "alpha", "gamma")
    _git(["add", "-A"], store_repo)
    _git(["commit", "-q", "-m", "nodes"], store_repo)
    _git(["push", "-q", "origin", "HEAD:main"], store_repo)
    cycle = sign_off(new_cycle(1, "typing", repo_root=store_repo, languages=("python",)),
                     by="Dev", date="2026-10-01", repo_root=store_repo)
    cycle = replace(cycle, status="r5-done", nodes_minted=("alpha", "beta", "gamma", "delta"))
    save_cycle(cycle, repo_root=store_repo)
    open_r6(1, repo_root=store_repo, opened_at="2026-10-01T10:00:00Z")
    return store_repo, cycle


class Ctx:
    run_id = "2026-10-01-r6-migrate-01-typing-01"


def _verifier(verdict):
    def _verify(ctx, conn, *, claim, citation, **kwargs):
        return PairVerdict(fact_id=claim.fact_id, source_id=citation.source_id,
                           locator=citation.locator, verdict=verdict, run_id=ctx.run_id,
                           date="2026-10-01")
    return _verify


def _config(repo):
    return ResearchConfig.load(research_config_path(repo))


def _remap(manifest):
    return {entry["match"]["anchor"]: entry for entry in manifest["dispositions"][0]["fact_remap"]}


def test_a_merge_draft_is_seeded_from_the_casebook(seeded):
    repo, cycle = seeded
    edge(repo, "requires", "alpha", "delta")

    manifest = draft_manifest(repo, {"op": "merge", "from": ["alpha"], "to": "delta"},
                              cycle=cycle, date="2026-10-02", rationale="duplicates",
                              slug="merge-alpha")

    remap = _remap(manifest)
    assert manifest["migration_id"] == "0001-merge-alpha"
    assert manifest["cycle"] == 1
    assert manifest["ontology_version_before"] == (repo / "ontology" / "VERSION").read_text().strip()
    assert remap["alpha#summary"] == {"match": {"anchor": "alpha#summary"}, "action": "remap",
                                      "target": "delta", "reverify": "fast-path"}
    assert remap["edge.requires.alpha.beta#exists"]["action"] == "remap"
    assert remap["edge.requires.alpha.delta#exists"]["action"] == "tombstone"   # would loop
    assert manifest["settled_themes"] == []


def test_split_and_remove_drafts_use_their_casebook_rows(seeded):
    repo, cycle = seeded

    split = draft_manifest(repo, {"op": "split", "from": "alpha", "to": ["gamma", "delta"]},
                           cycle=cycle, date="2026-10-02", rationale="r", slug="split-alpha")
    remove = draft_manifest(repo, {"op": "remove", "node": "alpha"}, cycle=cycle,
                            date="2026-10-02", rationale="r", slug="remove-alpha")

    assert _remap(split)["alpha#summary"]["action"] == "untouched"
    assert _remap(split)["edge.requires.alpha.beta#exists"]["action"] == "requeue"
    assert {entry["action"] for entry in _remap(remove).values()} == {"tombstone"}


def test_migration_ids_count_up_from_the_committed_ones(seeded):
    repo, _cycle = seeded
    (repo / "ontology" / "migrations" / "0007-older").mkdir(parents=True)

    assert next_migration_id(repo, "next") == "0008-next"


def test_a_migration_is_planned_gated_and_landed_as_one_commit(seeded):
    repo, cycle = seeded
    manifest = draft_manifest(repo, {"op": "merge", "from": ["alpha"], "to": "delta"},
                              cycle=cycle, date="2026-10-02", rationale="duplicates",
                              slug="merge-alpha")
    write_draft(repo, manifest)

    plan, results, outcome = run_migration(
        Ctx(), None, cycle, manifest["migration_id"], repo_root=repo, config=_config(repo),
        deps=VerifyDeps(source_facts=SOURCE_FACTS), verifier=_verifier("supported"))

    assert type(outcome).__name__ == "Landed"
    assert {result.key for result in results} == {"edge.requires.delta.beta",
                                                  "edge.enables.delta.gamma"}
    files = _git(["show", "--name-status", "--format=", "origin/main"], repo).stdout
    assert "D\tfeatures/alpha.yaml" in files
    assert f"A\t{manifest_rel('0001-merge-alpha')}" in files
    assert "A\ttombstones.yaml" in files and "A\tontology/redirects.yaml" in files
    assert load_record(cycle.slug, repo_root=repo)["migrations"] == ["0001-merge-alpha"]
    landed = load_manifest(repo / manifest_rel("0001-merge-alpha"))
    assert landed["settled_themes"] == []
    assert plan.gated == ("edges/delta/enables--gamma.yaml", "edges/delta/requires--beta.yaml")


def test_the_gate_can_refuse_a_remap_and_nothing_lands(seeded):
    repo, cycle = seeded
    manifest = draft_manifest(repo, {"op": "merge", "from": ["alpha"], "to": "delta"},
                              cycle=cycle, date="2026-10-02", rationale="r", slug="merge-alpha")
    write_draft(repo, manifest)
    head = _git(["rev-parse", "origin/main"], repo).stdout

    with pytest.raises(MigrationRefused, match="D24 gate refused"):
        run_migration(Ctx(), None, cycle, manifest["migration_id"], repo_root=repo,
                      config=_config(repo), deps=VerifyDeps(source_facts=SOURCE_FACTS),
                      verifier=_verifier("unsupported"))

    assert _git(["rev-parse", "origin/main"], repo).stdout == head


def test_an_edited_manifest_the_interpreter_refuses_never_reaches_the_gate(seeded):
    repo, cycle = seeded
    manifest = draft_manifest(repo, {"op": "remove", "node": "alpha"}, cycle=cycle,
                              date="2026-10-02", rationale="r", slug="remove-alpha")
    manifest["dispositions"][0]["fact_remap"] = [
        entry for entry in manifest["dispositions"][0]["fact_remap"]
        if not entry["match"]["anchor"].startswith("edge.requires")]
    write_draft(repo, manifest)

    with pytest.raises(MigrationRefused, match="still points at"):
        run_migration(Ctx(), None, cycle, manifest["migration_id"], repo_root=repo,
                      config=_config(repo), deps=VerifyDeps(source_facts=SOURCE_FACTS),
                      verifier=_verifier("supported"))


def test_an_undrafted_migration_is_refused(seeded):
    repo, cycle = seeded

    with pytest.raises(MigrationRefused, match="draft-migration"):
        run_migration(Ctx(), None, cycle, "0009-nothing", repo_root=repo, config=_config(repo))


def test_a_move_draft_seeds_nothing_and_passes_the_interpreter(seeded):
    repo, cycle = seeded

    manifest = draft_manifest(repo, {"op": "move", "node": "alpha", "to_layer": 1,
                                     "to_dimension": None}, cycle=cycle, date="2026-10-02",
                              rationale="r", slug="move-alpha")

    disposition = manifest["dispositions"][0]
    assert disposition["fact_remap"] == []
    assert "to_dimension" not in disposition
    plan = plan_migration(repo, manifest)
    assert check_plan(repo, plan) == []


def _record_path(repo, cycle):
    return repo / "research" / "consolidations" / f"{cycle.slug}.yaml"


def _draft_merge(repo, cycle, source, slug):
    manifest = draft_manifest(repo, {"op": "merge", "from": [source], "to": "delta"},
                              cycle=cycle, date="2026-10-02", rationale="r", slug=slug)
    write_draft(repo, manifest)
    return manifest["migration_id"]


def test_a_corrupt_record_after_landing_is_not_reported_as_a_failed_migration(seeded):
    repo, cycle = seeded
    migration_id = _draft_merge(repo, cycle, "alpha", "merge-alpha")

    def corrupting_lander(*args, **kwargs):
        outcome = land_changeset(*args, **kwargs)
        _record_path(repo, cycle).write_text("migrations: [unclosed\n")
        return outcome

    with pytest.raises(MigrationRecordNotUpdated, match=f"landed {migration_id} .*commit"):
        run_migration(Ctx(), None, cycle, migration_id, repo_root=repo, config=_config(repo),
                      deps=VerifyDeps(source_facts=SOURCE_FACTS), verifier=_verifier("supported"),
                      lander=corrupting_lander)

    assert "D\tfeatures/alpha.yaml" in _git(
        ["show", "--name-status", "--format=", "origin/main"], repo).stdout


def test_a_refused_gate_leaves_the_record_untouched(seeded):
    repo, cycle = seeded
    migration_id = _draft_merge(repo, cycle, "alpha", "merge-alpha")
    before = _record_path(repo, cycle).read_text()

    with pytest.raises(MigrationRefused):
        run_migration(Ctx(), None, cycle, migration_id, repo_root=repo, config=_config(repo),
                      deps=VerifyDeps(source_facts=SOURCE_FACTS), verifier=_verifier("unsupported"))

    assert _record_path(repo, cycle).read_text() == before


def test_a_non_landed_outcome_leaves_the_record_untouched(seeded):
    repo, cycle = seeded
    migration_id = _draft_merge(repo, cycle, "alpha", "merge-alpha")
    before = _record_path(repo, cycle).read_text()

    _plan, _results, outcome = run_migration(
        Ctx(), None, cycle, migration_id, repo_root=repo, config=_config(repo),
        deps=VerifyDeps(source_facts=SOURCE_FACTS), verifier=_verifier("supported"),
        lander=lambda *args, **kwargs: "blocked")

    assert outcome == "blocked"
    assert _record_path(repo, cycle).read_text() == before


def test_two_migrations_in_one_cycle_each_commit_only_their_own_files(seeded):
    repo, cycle = seeded
    first = _draft_merge(repo, cycle, "alpha", "merge-alpha")
    run_migration(Ctx(), None, cycle, first, repo_root=repo, config=_config(repo),
                  deps=VerifyDeps(source_facts=SOURCE_FACTS), verifier=_verifier("supported"))
    second = _draft_merge(repo, cycle, "gamma", "merge-gamma")
    _git(["add", "research"], repo)
    _git(["commit", "-q", "-m", "the developer commits the record"], repo)
    _git(["push", "-q", "origin", "HEAD:main"], repo)

    _plan, _results, outcome = run_migration(
        Ctx(), None, cycle, second, repo_root=repo, config=_config(repo),
        deps=VerifyDeps(source_facts=SOURCE_FACTS), verifier=_verifier("supported"))

    assert type(outcome).__name__ == "Landed"
    files = _git(["show", "--name-only", "--format=", "origin/main"], repo).stdout.split()
    assert not any(name.startswith("research/") for name in files)
    assert manifest_rel(second) in files
    assert load_record(cycle.slug, repo_root=repo)["migrations"] == [first, second]
    assert _git(["status", "--porcelain", "--untracked-files=no"], repo).stdout.split() == [
        "M", f"research/consolidations/{cycle.slug}.yaml"]


def test_a_corrupt_record_is_refused_before_anything_lands(seeded):
    repo, cycle = seeded
    migration_id = _draft_merge(repo, cycle, "alpha", "merge-alpha")
    _record_path(repo, cycle).write_text("migrations: [unclosed\n")
    head = _git(["rev-parse", "origin/main"], repo).stdout

    with pytest.raises(ConsolidationInvalid):
        run_migration(Ctx(), None, cycle, migration_id, repo_root=repo, config=_config(repo),
                      deps=VerifyDeps(source_facts=SOURCE_FACTS), verifier=_verifier("supported"))

    assert _git(["rev-parse", "origin/main"], repo).stdout == head
