import pytest

from langatlas_research.config import PoolConfig
from langatlas_research.cycle import new_cycle, sign_off
from langatlas_research.errors import PoolMissing, PoolStale, SignOffMissing, SignOffStale
from langatlas_research.paths import themes_path
from langatlas_research.survey.chunks import ChunkRef
from langatlas_research.survey.pool import (
    batch_key, batches, build_pool, load_pool, parse_batch_key, pool_queries,
    require_current_pool, save_pool,
)
from langatlas_research.themes import load_themes


def _hit(chunk_id):
    source = chunk_id.split("#")[0]
    return {"chunk_id": chunk_id, "source_id": source, "locator": "p. 1",
            "breadcrumb": "Ch", "text": "body", "score": 0.1}


def _lookup(chunk_id):
    source = chunk_id.split("#")[0]
    return ChunkRef(chunk_id=chunk_id, source_id=source, locator="p. 1", breadcrumb="Ch",
                    content_hash=f"h-{chunk_id}", text="body")


def test_queries_are_label_summary_then_seed_terms_deduped(research_repo):
    theme = load_themes(research_repo)["typing"]
    queries = pool_queries(theme)
    assert queries[0] == "Typing"
    assert queries[2:] == tuple(theme.seed_terms)
    assert len(set(q.lower() for q in queries)) == len(queries)


def test_the_pool_takes_every_query_s_top_hits_before_any_deep_hit(
        fake_ctx, research_repo, signed_cycle, private_dir):
    queries = pool_queries(load_themes(research_repo)["typing"])
    index = {query: i for i, query in enumerate(queries)}

    def search(query, k):
        return [_hit(f"q{index[query]}#c{i:05d}") for i in range(k)]

    cap = len(queries)
    pool = build_pool(fake_ctx, signed_cycle, repo_root=research_repo, search_fn=search,
                      lookup=_lookup, config=PoolConfig(k_per_query=5, max_chunks=cap))

    assert len(pool.entries) == cap
    ids = {entry.chunk_id for entry in pool.entries}
    # a cap equal to the query count admits exactly every query's rank-0 hit
    assert ids == {f"q{i}#c00000" for i in range(cap)}
    assert all(entry.text == "" for entry in pool.entries), "no chunk text in the pool file"
    assert [e.chunk_id for e in pool.entries] == sorted(ids)


def test_a_chunk_the_lookup_cannot_find_is_left_out(fake_ctx, research_repo, signed_cycle,
                                                    private_dir):
    pool = build_pool(fake_ctx, signed_cycle, repo_root=research_repo,
                      search_fn=lambda q, k: [_hit("gone#c00001"), _hit("tapl#c00001")],
                      lookup=lambda cid: None if cid.startswith("gone") else _lookup(cid),
                      config=PoolConfig(k_per_query=5, max_chunks=50))
    assert [e.chunk_id for e in pool.entries] == ["tapl#c00001"]


def test_an_unsigned_cycle_cannot_build_a_pool(fake_ctx, research_repo, private_dir):
    cycle = new_cycle(2, "modules", repo_root=research_repo, languages=("c",))
    with pytest.raises(SignOffMissing):
        build_pool(fake_ctx, cycle, repo_root=research_repo, search_fn=lambda q, k: [],
                   lookup=_lookup, config=PoolConfig(k_per_query=1, max_chunks=1))


def test_save_load_round_trip_and_digest_is_order_free(fake_ctx, research_repo,
                                                       signed_cycle, private_dir):
    pool = build_pool(fake_ctx, signed_cycle, repo_root=research_repo,
                      search_fn=lambda q, k: [_hit("b#c1"), _hit("a#c2")], lookup=_lookup,
                      config=PoolConfig(k_per_query=5, max_chunks=50))
    save_pool(pool)
    loaded = load_pool(signed_cycle.slug)
    assert loaded == pool
    assert len(loaded.digest) == 16


def test_a_missing_pool_is_a_typed_error(private_dir):
    with pytest.raises(PoolMissing):
        load_pool("09-nothing")


def test_editing_the_theme_after_pooling_makes_the_pool_stale(
        fake_ctx, research_repo, signed_cycle, private_dir):
    save_pool(build_pool(fake_ctx, signed_cycle, repo_root=research_repo,
                         search_fn=lambda q, k: [_hit("a#c1")], lookup=_lookup,
                         config=PoolConfig(k_per_query=5, max_chunks=50)))
    path = themes_path(research_repo)
    path.write_text(path.read_text().replace("Type systems, checking", "Type systems, and"))
    # Un-re-signed: the D27 gate itself fires first.
    with pytest.raises(SignOffStale):
        require_current_pool(signed_cycle, repo_root=research_repo)

    # Re-signed: the gate passes, but the pool still answers the old theme text.
    resigned = sign_off(signed_cycle, by="Michal Dolezel", date="2026-09-21",
                        repo_root=research_repo)
    with pytest.raises(PoolStale):
        require_current_pool(resigned, repo_root=research_repo)


def test_batches_and_keys(fake_ctx, research_repo, signed_cycle, private_dir):
    pool = build_pool(fake_ctx, signed_cycle, repo_root=research_repo,
                      search_fn=lambda q, k: [_hit(f"s#c{i}") for i in range(7)],
                      lookup=_lookup, config=PoolConfig(k_per_query=7, max_chunks=50))
    groups = batches(pool, 3)
    assert [len(g) for g in groups] == [3, 3, 1]
    assert batch_key("01-typing", 3) == "01-typing:batch-0003"
    assert parse_batch_key("01-typing:batch-0003") == ("01-typing", 3)
