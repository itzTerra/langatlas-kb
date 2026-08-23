import subprocess

import pytest

from langatlas_orchestrator.jobs.exit_test import _mint_concept_record
from langatlas_validate.normalize import normalize_record
from langatlas_validate.schema import validate_record


def test_mint_concept_record_is_schema_valid_and_normalized():
    hit = {"source_id": "van-roy-haridi-2003", "locator": "p. 42"}
    record_path, content = _mint_concept_record("pattern matching", hit)

    assert record_path == "concepts/orchestrator-exit-test-probe.yaml"
    from ruamel.yaml import YAML
    data = YAML(typ="safe").load(content)
    assert validate_record(data, "concept") == []
    assert normalize_record(content, "concept") == content


def test_mint_concept_record_cites_the_hit_locator_verbatim():
    hit = {"source_id": "sebesta-2019", "locator": "ch. 3 s. 2"}
    _record_path, content = _mint_concept_record("closures", hit)
    from ruamel.yaml import YAML
    data = YAML(typ="safe").load(content)
    sources = data["summary"]["sources"]
    assert sources == [{"source": "sebesta-2019", "locator": "ch. 3 s. 2"}]


from langatlas_orchestrator.driver import EXIT_OK, run as driver_run
from langatlas_orchestrator.checkpoint import CheckpointStore

pytestmark_db = pytest.mark.db


def test_run_item_maps_blocked_red_main_to_blocked_outcome(monkeypatch, tmp_path):
    """`land_record` returning `BlockedRedMain` is a transient, re-attemptable outcome
    (Finding 4c) — `_run_item` must map it to `ItemOutcome(status="blocked")`, not the
    old blanket `halted` (which the driver treats as needing a human)."""
    from langatlas_commit.land import BlockedRedMain
    from langatlas_orchestrator.jobs import exit_test as exit_test_module

    monkeypatch.setattr(
        exit_test_module, "search_sources",
        lambda ctx, query, k, conn: [{"source_id": "van-roy-haridi-2003", "locator": "p. 42"}])
    monkeypatch.setattr(exit_test_module, "land_record",
                        lambda *a, **kw: BlockedRedMain(since=0.0, last_checked=0.0))

    class _FakeConn:
        def close(self):
            pass

    monkeypatch.setattr("langatlas_ingest.db.connect", lambda dsn=None: _FakeConn())

    class _FakeCtx:
        run_id = "fake-run-id"

    outcome = exit_test_module._run_item(ctx=_FakeCtx(), item_key="mint-search-and-commit",
                                         extra={}, repo_root=tmp_path)

    assert outcome.status == "blocked"


def test_run_item_maps_contention_exhausted_to_contention_outcome(monkeypatch, tmp_path):
    from langatlas_commit.land import ContentionExhausted
    from langatlas_orchestrator.jobs import exit_test as exit_test_module

    monkeypatch.setattr(
        exit_test_module, "search_sources",
        lambda ctx, query, k, conn: [{"source_id": "van-roy-haridi-2003", "locator": "p. 42"}])
    monkeypatch.setattr(
        exit_test_module, "land_record",
        lambda *a, **kw: ContentionExhausted(retries=5, last_conflict_summary="conflict"))

    class _FakeConn:
        def close(self):
            pass

    monkeypatch.setattr("langatlas_ingest.db.connect", lambda dsn=None: _FakeConn())

    class _FakeCtx:
        run_id = "fake-run-id"

    outcome = exit_test_module._run_item(ctx=_FakeCtx(), item_key="mint-search-and-commit",
                                         extra={}, repo_root=tmp_path)

    assert outcome.status == "contention"


def _git(args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


@pytest.fixture
def bare_and_clone(tmp_path):
    bare = tmp_path / "bare.git"
    _git(["init", "-q", "--bare", "-b", "main", str(bare)], tmp_path)
    clone = tmp_path / "clone"
    _git(["clone", "-q", str(bare), str(clone)], tmp_path)
    _git(["config", "user.email", "bot@example.com"], clone)
    _git(["config", "user.name", "bot"], clone)
    (clone / "README.md").write_text("seed\n")
    _git(["add", "README.md"], clone)
    _git(["commit", "-q", "-m", "seed"], clone)
    _git(["push", "-q", "origin", "main"], clone)
    return clone


@pytest.mark.db
def test_r0_exit_test_end_to_end(db_conn, bare_and_clone, tmp_path, monkeypatch):
    """The literal Stage 1 exit gate: search_sources runs against real ingested
    source_chunks, the driver mints and lands a validating concept record through the
    real commit protocol, and the run's transcript is written to disk (D18's logging
    requirement) — all driven through `langatlas_orchestrator.driver.run`, the same
    entrypoint cron/the developer would invoke for any other job kind."""
    from langatlas_ingest.chunker import Chunk
    from langatlas_ingest.db import migrate
    from langatlas_ingest.embed import embed_source
    from langatlas_ingest.store import SourceChunksStore
    from langatlas_ingest.config import IngestConfig
    from langatlas_pipeline.providers.core import Budget, RunContext

    migrate(db_conn)
    chunk = Chunk(chunk_id="vrh#c00000", source_id="van-roy-haridi-2003", ordinal=0,
                 parent_section_id="vrh#s0000", section_path=["Ch 1"], breadcrumb="Ch 1",
                 locator="p. 42", locator_kind="book-page",
                 text="Pattern matching destructures a value against a sequence of patterns.",
                 token_count=12, content_hash="h0", page_start=42, page_end=42)
    SourceChunksStore(db_conn).replace_source("van-roy-haridi-2003", [chunk])

    ingest_config = IngestConfig.load(overrides={"retrieval_k": 3, "retrieval_candidates": 10})

    class _FakeEmbeddingConfig:
        def embedding(self, model):
            from dataclasses import dataclass

            @dataclass
            class Cap:
                model: str
                dimensions: int
                max_input_tokens: int = 8192

            return Cap(model=model, dimensions=4)

    class _FakeEmbedCtx:
        def __init__(self):
            self.config = _FakeEmbeddingConfig()

        def embed(self, texts, *, model):
            return [[float(len(t) % 10) / 10, 0.0, 0.0, 0.0] for t in texts]

    embed_source(_FakeEmbedCtx(), db_conn, config=ingest_config)

    # RunContext.embed/rerank would otherwise call the real university API — this exit
    # test only has to prove the orchestrator's own control flow, not exercise a live
    # network embedding provider (the embedding table above already stands in for it).
    monkeypatch.setattr(RunContext, "embed",
                        lambda self, texts, *, model: [[float(len(t) % 10) / 10, 0.0, 0.0,
                                                        0.0] for t in texts])
    monkeypatch.setattr(RunContext, "rerank",
                        lambda self, query, docs, *, model: [1.0 / (i + 1)
                                                             for i in range(len(docs))])
    monkeypatch.setattr("langatlas_ingest.db.connect", lambda dsn=None: db_conn)
    monkeypatch.setenv("LANGATLAS_INGEST_DSN", "unused-fake-monkeypatched-connect")

    spec_path = tmp_path / "job.yaml"
    spec_path.write_text(f"kind: r0-exit-test\ncheckpoint_path: {tmp_path / 'ck.sqlite'}\n"
                         f"query: pattern matching\n")

    rc = driver_run(spec_path, repo_root=bare_and_clone, status_path=tmp_path / "status.json",
                    transcripts_root=tmp_path / "transcripts", private_dir=tmp_path / "private")

    assert rc == EXIT_OK
    log = _git(["log", "-1", "--format=%B", "origin/main"], bare_and_clone)
    assert "LangAtlas-Record-Key" in log.stdout
    assert "LangAtlas-Chat-Run-Id" in log.stdout
    committed = _git(["show", "origin/main:concepts/orchestrator-exit-test-probe.yaml"],
                     bare_and_clone)
    assert "pattern matching" in committed.stdout.lower() or "van-roy-haridi" in committed.stdout

    row = CheckpointStore(tmp_path / "ck.sqlite").get(spec_kind="r0-exit-test",
                                                      item_key="mint-search-and-commit")
    assert row.status == "done"
