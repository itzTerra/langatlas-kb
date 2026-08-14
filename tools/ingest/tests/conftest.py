import os
import pytest
from dataclasses import dataclass
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


class FakeEmbeddingConfig:
    """Stands in for 1B's ProviderConfig: only `embedding()` is exercised here."""

    def __init__(self, dimensions: int = 4):
        self.dimensions = dimensions

    def embedding(self, model: str):
        @dataclass
        class Cap:
            model: str
            dimensions: int
            max_input_tokens: int = 8192

        return Cap(model=model, dimensions=self.dimensions)


class FakeCtx:
    """A RunContext stand-in. Deliberately records every call: the point of routing
    embeddings through `ctx` is that nothing reaches a provider unobserved (D26/D18)."""

    def __init__(self, dimensions: int = 4):
        self.config = FakeEmbeddingConfig(dimensions)
        self.dimensions = dimensions
        self.embed_calls: list[list[str]] = []
        self.rerank_calls: list[tuple[str, list[str]]] = []
        self.tool_results: list[tuple[str, str]] = []
        self.rerank_scores: list[float] | None = None

    def embed(self, texts, *, model):
        self.embed_calls.append(list(texts))
        return [[float(len(text) % 10) / 10] + [0.0] * (self.dimensions - 1)
                for text in texts]

    def rerank(self, query, docs, *, model):
        self.rerank_calls.append((query, list(docs)))
        if self.rerank_scores is not None:
            return self.rerank_scores[:len(docs)]
        return [1.0 / (index + 1) for index in range(len(docs))]

    def tool_result(self, *, tool, text, source_id=None, kind="source-chunk"):
        self.tool_results.append((tool, text))
        return f"<untrusted source={source_id}>\n{text}\n</untrusted>"


@pytest.fixture
def fake_ctx():
    return FakeCtx()
