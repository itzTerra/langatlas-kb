from langatlas_ingest.paths import DB_DIR, REPO_ROOT, snapshot_dir


def test_repo_root_holds_the_canonical_store():
    assert (REPO_ROOT / "ontology" / "VERSION").exists()
    assert DB_DIR == REPO_ROOT / "db"


def test_snapshot_dir_is_per_source(monkeypatch, tmp_path):
    monkeypatch.setattr("langatlas_ingest.paths.SNAPSHOT_ROOT", tmp_path)
    import langatlas_ingest.paths as paths

    assert paths.snapshot_dir("vanroy-haridi-2003") == tmp_path / "vanroy-haridi-2003"
