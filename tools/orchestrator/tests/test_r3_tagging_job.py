import psycopg
import pytest

import langatlas_orchestrator.jobs  # noqa: F401 — registers every built-in kind
from langatlas_orchestrator.registry import get_job_kind, registered_kinds
from langatlas_research.cycle import new_cycle, sign_off
from langatlas_research.errors import SignOffMissing
from langatlas_research.paths import REPO_ROOT, ensure_layout, themes_path
from langatlas_research.survey.chunks import ChunkRef
from langatlas_research.survey.pool import Pool, save_pool
from langatlas_research.survey.tagger import TagBatchResult


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr("langatlas_pipeline.paths.PRIVATE_DIR", tmp_path / "private")
    root = tmp_path / "repo"
    ensure_layout(root)
    for schema in (REPO_ROOT / "research" / "schema").glob("*.schema.json"):
        (root / "research" / "schema" / schema.name).write_text(schema.read_text())
    themes_path(root).write_text(themes_path(REPO_ROOT).read_text())
    (root / "config").mkdir()
    (root / "config" / "research.yaml").write_text(
        (REPO_ROOT / "config" / "research.yaml").read_text())
    return root


def _signed(repo):
    cycle = new_cycle(1, "typing", repo_root=repo, languages=("python",))
    return sign_off(cycle, by="Michal Dolezel", date="2026-09-20", repo_root=repo)


def _pool(cycle, n):
    return Pool(cycle_slug=cycle.slug, theme_digest=cycle.signed_off["theme_digest"],
                queries=("Typing",),
                entries=tuple(ChunkRef(chunk_id=f"s#c{i:05d}", source_id="s", locator="p. 1",
                                       breadcrumb="Ch", content_hash=f"h{i}")
                              for i in range(n)))


def test_the_kind_is_registered():
    assert "r3-corpus-tagging" in registered_kinds()


def test_enumeration_yields_one_digest_bound_key_per_batch(repo):
    cycle = _signed(repo)
    pool = _pool(cycle, 7)
    save_pool(pool)
    enumerate_fn, _ = get_job_kind("r3-corpus-tagging")

    keys = enumerate_fn({"cycle": 1, "batch_size": 3}, repo)

    assert keys == [f"01-typing:batch-000{i}@{pool.digest}" for i in range(3)]


def test_enumeration_refuses_an_unsigned_cycle(repo):
    new_cycle(1, "typing", repo_root=repo, languages=("python",))
    enumerate_fn, _ = get_job_kind("r3-corpus-tagging")
    with pytest.raises(SignOffMissing):
        enumerate_fn({"cycle": 1}, repo)


def test_enumeration_requires_a_cycle(repo):
    enumerate_fn, _ = get_job_kind("r3-corpus-tagging")
    with pytest.raises(ValueError, match="--set cycle="):
        enumerate_fn({}, repo)


def test_an_item_tags_its_batch(repo, monkeypatch):
    import langatlas_orchestrator.jobs.r3_tagging as job

    cycle = _signed(repo)
    pool = _pool(cycle, 7)
    save_pool(pool)
    calls = []
    monkeypatch.setattr(job, "_tag", lambda ctx, theme, slug, batch, alias:
                        calls.append((slug, [r.chunk_id for r in batch], alias))
                        or TagBatchResult(tagged=len(batch)))

    outcome = job._run_item(object(), f"01-typing:batch-0002@{pool.digest}",
                            {"cycle": 1, "batch_size": 3}, repo)

    assert outcome.status == "done" and "tagged 1" in outcome.detail
    assert calls == [("01-typing", ["s#c00006"], "deepseek")]


def test_an_item_from_a_rebuilt_pool_is_superseded_not_retagged(repo, monkeypatch):
    import langatlas_orchestrator.jobs.r3_tagging as job

    save_pool(_pool(_signed(repo), 4))
    monkeypatch.setattr(job, "_tag", lambda *a: pytest.fail("must not tag"))

    outcome = job._run_item(object(), "01-typing:batch-0000@0000000000000000",
                            {"cycle": 1}, repo)

    assert outcome.status == "done" and "superseded" in outcome.detail


def test_an_unreachable_database_blocks(repo, monkeypatch):
    import langatlas_orchestrator.jobs.r3_tagging as job

    pool = _pool(_signed(repo), 2)
    save_pool(pool)

    def _down(*args):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(job, "_tag", _down)
    outcome = job._run_item(object(), f"01-typing:batch-0000@{pool.digest}", {"cycle": 1},
                            repo)
    assert outcome.status == "blocked"
