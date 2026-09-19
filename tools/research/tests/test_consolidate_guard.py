import subprocess

import pytest

from langatlas_research.cli import main
from langatlas_research.consolidate.guard import check_settled, settled_ids_at
from langatlas_validate.compile import derive_facts
from langatlas_validate.ids import compose_edge_id
from langatlas_validate.normalize import normalize_record
from langatlas_validate.store import iter_store_records
from langatlas_validate.tombstones import render_tombstones

pytestmark = pytest.mark.git


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _commit(repo, files, message="change"):
    for rel, text in files.items():
        path = repo / rel
        if text is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", message], repo)
    return _git(["rev-parse", "HEAD"], repo).stdout.strip()


def _feature(node_id, *, layer=2, summary=None):
    return normalize_record(
        f"id: {node_id}\nslug: {node_id}\nname: {node_id.title()}\nlayer: {layer}\n"
        f"summary:\n  text: {summary or node_id + ' is a feature.'}\n"
        "  sources:\n    - source: s\n      locator: p. 1\n"
        "provenance:\n  claim_origin: source-derived\n", "feature")


EDGE_ID = compose_edge_id("requires", "alpha", "beta")
EDGE = normalize_record(
    f"id: {EDGE_ID}\ntype: requires\nfrom: alpha\nto: beta\n"
    "statement:\n  text: alpha requires beta.\n  sources:\n    - source: s\n      locator: p. 1\n"
    "provenance:\n  claim_origin: source-derived\n", "edge")


def _cycle(status):
    return (f"cycle: 1\ntheme: typing\ntheme_digest: {'a' * 16}\nstatus: {status}\n"
            f"languages: [python]\nnodes_minted: [alpha, beta, {EDGE_ID}]\nartifacts: {{}}\n")


@pytest.fixture
def settled_repo(store_repo):
    """alpha, beta and an edge, then a commit settling cycle 1 over all three."""
    base = _commit(store_repo, {"features/alpha.yaml": _feature("alpha"),
                                "features/beta.yaml": _feature("beta"),
                                "edges/alpha/requires--beta.yaml": EDGE}, "nodes")
    _commit(store_repo, {"research/cycles/01-typing.yaml": _cycle("settled")}, "settle")
    return store_repo, base


def test_settled_ids_are_read_at_a_ref(settled_repo):
    repo, base = settled_repo

    assert settled_ids_at(repo, base) == {}
    assert settled_ids_at(repo, "HEAD") == {"alpha": "typing", "beta": "typing",
                                            EDGE_ID: "typing"}


def test_removing_a_settled_record_without_a_manifest_fails(settled_repo):
    repo, base = settled_repo
    _commit(repo, {"edges/alpha/requires--beta.yaml": None})

    [error] = check_settled(repo, base)

    assert "removes a record of settled theme 'typing'" in error


def test_restructuring_a_settled_record_fails_but_adding_beside_it_does_not(settled_repo):
    repo, base = settled_repo
    _commit(repo, {"features/delta.yaml": _feature("delta")})
    assert check_settled(repo, base) == []

    _commit(repo, {"features/alpha.yaml": _feature("alpha", layer=1)})
    assert any("restructures" in e and "features/alpha.yaml" in e
               for e in check_settled(repo, base))


def test_a_vanished_settled_fact_needs_a_tombstone(settled_repo):
    repo, base = settled_repo
    old = next(f for f in derive_facts(list(iter_store_records(repo)))
               if f["anchor"] == "alpha#summary")
    reworded = _feature("alpha", summary="alpha checks something else entirely.")
    head = _commit(repo, {"features/alpha.yaml": reworded})

    assert any(old["fact_id"] in e and "tombstone" in e for e in check_settled(repo, base))

    _git(["reset", "-q", "--hard", f"{head}^"], repo)
    line = render_tombstones([{"fact_id": old["fact_id"], "anchor": "alpha#summary",
                               "action": "remap", "reason": "corrected-value",
                               "superseded_by": [], "migration_id": None,
                               "date": "2026-10-02"}])
    _commit(repo, {"features/alpha.yaml": reworded, "tombstones.yaml": line})
    assert check_settled(repo, base) == []


def test_a_manifest_commit_is_left_to_replay(settled_repo):
    repo, base = settled_repo
    _commit(repo, {"edges/alpha/requires--beta.yaml": None,
                   "ontology/migrations/0001-x/manifest.yaml": "migration_id: 0001-x\n"})

    assert check_settled(repo, base) == []


@pytest.mark.parametrize("path", ["ontology/migrations/0001-x/sub/manifest.yaml",
                                  "ontology/migrations/manifest.yaml",
                                  "ontology/migrations/notanid/manifest.yaml"])
def test_a_manifest_shaped_file_outside_the_replayed_path_is_not_exempt(settled_repo, path):
    repo, base = settled_repo
    _commit(repo, {"edges/alpha/requires--beta.yaml": None, path: "migration_id: 0001-x\n"})

    [error] = check_settled(repo, base)

    assert "removes a record of settled theme 'typing'" in error


def test_an_unsettled_theme_restructures_freely(store_repo):
    base = _commit(store_repo, {"features/alpha.yaml": _feature("alpha"),
                                "features/beta.yaml": _feature("beta"),
                                "edges/alpha/requires--beta.yaml": EDGE,
                                "research/cycles/01-typing.yaml": _cycle("r5-done")})
    _commit(store_repo, {"edges/alpha/requires--beta.yaml": None})

    assert check_settled(store_repo, base) == []


def test_the_cli_exits_nonzero_on_a_violation(settled_repo, capsys):
    repo, base = settled_repo
    _commit(repo, {"edges/alpha/requires--beta.yaml": None})

    assert main(["--repo-root", str(repo), "consolidate", "guard", "--since", base]) == 1
    assert "settled theme" in capsys.readouterr().out


def test_bad_yaml_and_the_root_commit_yield_errors_not_tracebacks(settled_repo):
    repo, base = settled_repo
    _commit(repo, {"features/alpha.yaml": "id: [unclosed\n"})
    [error] = check_settled(repo, base)
    assert "unparseable YAML" in error

    _commit(repo, {"features/alpha.yaml": _feature("alpha"),
                   "research/cycles/02-bad.yaml": "theme: [oops\n"})
    # whole history, root commit included (no parent: skipped), never raises
    assert any("unparseable YAML" in e for e in check_settled(repo, None))


def test_a_settled_cycle_without_a_theme_is_a_typed_error():
    from langatlas_research.cycle import settled_themes_by_record
    from langatlas_research.errors import ResearchError

    with pytest.raises(ResearchError, match="has no theme"):
        settled_themes_by_record([{"status": "settled", "nodes_minted": ["a"]}])


def test_the_guard_reports_a_themeless_settled_cycle_loudly(settled_repo):
    repo, base = settled_repo
    _commit(repo, {"research/cycles/02-x.yaml":
                   "cycle: 2\nstatus: settled\nnodes_minted: [zed]\n"})
    _commit(repo, {"features/delta.yaml": _feature("delta")})

    assert any("has no theme" in e for e in check_settled(repo, base))


def test_a_slug_rename_of_a_settled_record_passes(settled_repo):
    repo, base = settled_repo
    _commit(repo, {"features/alpha.yaml": None, "features/alpha-renamed.yaml": _feature("alpha")})

    assert check_settled(repo, base) == []


def test_a_rename_that_drops_a_fact_fails(settled_repo):
    repo, base = settled_repo
    _commit(repo, {"features/alpha.yaml": None, "features/alpha-renamed.yaml":
                   _feature("alpha", summary="alpha checks something else entirely.")})

    assert any("vanished without a tombstone" in e for e in check_settled(repo, base))


def test_a_rename_with_a_restructuring_change_fails(settled_repo):
    repo, base = settled_repo
    _commit(repo, {"features/alpha.yaml": None,
                   "features/alpha-renamed.yaml": _feature("alpha", layer=1)})

    assert any("restructures" in e and "moved to features/alpha-renamed.yaml" in e
               for e in check_settled(repo, base))


def test_a_same_id_kind_change_fails(settled_repo):
    repo, base = settled_repo
    _commit(repo, {"features/alpha.yaml": None, "concepts/alpha.yaml": _feature("alpha")})

    assert any("restructures" in e for e in check_settled(repo, base))


def test_an_aliases_only_edit_of_a_settled_record_passes(settled_repo):
    repo, base = settled_repo
    aliased = _feature("alpha").replace("provenance:", "aliases:\n  - first\nprovenance:", 1)
    _commit(repo, {"features/alpha.yaml": aliased})

    assert check_settled(repo, base) == []


def test_a_malformed_cycle_file_is_a_typed_error(tmp_path):
    from langatlas_research.cycle import settled_record_ids
    from langatlas_research.errors import ResearchError

    (tmp_path / "research" / "cycles").mkdir(parents=True)
    (tmp_path / "research" / "cycles" / "01-x.yaml").write_text("theme: [oops\n")

    with pytest.raises(ResearchError, match="malformed cycle file"):
        settled_record_ids(tmp_path)
