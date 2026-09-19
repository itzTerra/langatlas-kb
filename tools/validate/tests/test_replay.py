from langatlas_validate.cli import main
from langatlas_validate.migrate import manifest_rel, plan_migration, render_manifest
from langatlas_validate.replay import added_manifests, replay_since

MANIFEST = {"migration_id": "0001-remove-alpha", "date": "2026-10-01", "cycle": 2,
            "ontology_version_before": "0.4.0", "rationale": "alpha was a duplicate",
            "dispositions": [{"op": "remove", "node": "alpha", "fact_remap": [
                {"match": {"anchor": "edge.requires.alpha.beta#*"}, "action": "tombstone"}]}]}


def _seed(store, repo):
    for node_id in ("alpha", "beta"):
        store.feature(node_id)
    store.edge("requires", "alpha", "beta")
    return repo.commit(message="nodes")


def _migration_files(store, **extra):
    plan = plan_migration(store.root, MANIFEST)
    return {**plan.changes, manifest_rel("0001-remove-alpha"): render_manifest(MANIFEST), **extra}


def test_a_manifest_commit_replays_exactly(store_git):
    store, repo = store_git
    base = _seed(store, repo)
    commit = repo.commit(_migration_files(store), message="migrate")

    results = replay_since(store.root, base)

    assert added_manifests(store.root, base) == [(commit, manifest_rel("0001-remove-alpha"))]
    assert [(result.migration_id, result.errors) for result in results] == [
        ("0001-remove-alpha", ())]


def test_a_file_riding_along_with_a_manifest_fails_replay(store_git):
    store, repo = store_git
    base = _seed(store, repo)
    beta = (store.root / "features" / "beta.yaml").read_text()
    repo.commit(_migration_files(store, **{"features/beta.yaml": beta.replace("Beta", "Bēta")}))

    [result] = replay_since(store.root, base)

    assert any("features/beta.yaml" in e and "not by its manifest" in e for e in result.errors)


def test_a_hand_edited_migrated_file_fails_replay(store_git):
    store, repo = store_git
    base = _seed(store, repo)
    files = _migration_files(store)
    files["tombstones.yaml"] += "# edited by hand\n"
    repo.commit(files)

    [result] = replay_since(store.root, base)

    assert any("tombstones.yaml" in e and "differs" in e for e in result.errors)


def test_without_a_usable_base_the_whole_history_is_replayed(store_git):
    store, repo = store_git
    _seed(store, repo)
    repo.commit(_migration_files(store))

    assert len(replay_since(store.root, None)) == 1
    assert len(replay_since(store.root, "0" * 40)) == 1


def test_the_cli_reports_and_exits_on_the_replay(store_git, capsys, tmp_path):
    store, repo = store_git
    base = _seed(store, repo)
    draft = tmp_path / "manifest.yaml"
    draft.write_text(render_manifest(MANIFEST))

    assert main(["migrations", "plan", str(draft), "--repo-root", str(store.root)]) == 0
    assert "delete features/alpha.yaml" in capsys.readouterr().out

    repo.commit(_migration_files(store))
    assert main(["migrations", "replay", "--since", base, "--repo-root", str(store.root)]) == 0
    assert "ok 0001-remove-alpha" in capsys.readouterr().out


def test_a_malformed_manifest_commit_is_an_error_not_a_traceback(store_git):
    store, repo = store_git
    base = _seed(store, repo)
    bad = "ontology/migrations/0001-x/manifest.yaml"
    repo.commit({bad: "[unclosed"})
    repo.commit({"ontology/migrations/0002-y/manifest.yaml": "- a list\n"})

    results = replay_since(store.root, base)

    assert [bool(result.errors) for result in results] == [True, True]


def test_the_cli_refuses_bad_input_without_a_traceback(store_git, capsys, tmp_path):
    store, _repo = store_git
    draft = tmp_path / "bad.yaml"
    draft.write_text("[unclosed")

    assert main(["migrations", "plan", str(draft), "--repo-root", str(store.root)]) == 1
    assert main(["migrations", "plan", str(tmp_path / "missing.yaml"),
                 "--repo-root", str(store.root)]) == 1
    assert main(["migrations", "replay", "--since", "nope", "--repo-root", str(store.root)]) == 0
    assert main(["migrations", "replay", "--repo-root", str(tmp_path / "nowhere")]) == 1
