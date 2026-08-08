import os
import pytest
from langatlas_ingest.config import IngestConfig


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


@pytest.fixture(scope="session")
def dsn() -> str:
    """Tests run against a throwaway database inside the compose Postgres. They are
    marked `db` and are skipped — never silently passed — when it is not running."""
    import psycopg

    base = os.environ.get("LANGATLAS_TEST_DSN") or IngestConfig.load().dsn
    try:
        with psycopg.connect(base, connect_timeout=3, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP DATABASE IF EXISTS langatlas_test")
                cur.execute("CREATE DATABASE langatlas_test")
    except psycopg.OperationalError as exc:
        pytest.skip(f"compose Postgres unreachable ({exc}); run `docker compose up -d db`")
    return base.rsplit("/", 1)[0] + "/langatlas_test"


@pytest.fixture
def db_conn(dsn):
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        yield conn
