import pytest


@pytest.fixture
def snapshot_root(tmp_path, monkeypatch):
    """Every test writes into a throwaway private tier — never the developer's real one.
    Any test that constructs a `SnapshotStore()` without an explicit root must request
    this fixture; `snapshot.py` reads `paths.SNAPSHOT_ROOT` through the module so the
    patch takes effect."""
    root = tmp_path / "snapshots"
    root.mkdir()
    monkeypatch.setenv("LANGATLAS_SNAPSHOT_ROOT", str(root))
    monkeypatch.setattr("langatlas_ingest.paths.SNAPSHOT_ROOT", root)
    return root
