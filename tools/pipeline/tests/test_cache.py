from pathlib import Path
from langatlas_pipeline.cache import CallCache, cache_key

BASE = dict(endpoint="chat", resolved_model="glm-5.2",
            messages=[{"role": "user", "content": "hi"}],
            sampling={"temperature": 0.0}, schema_name="Verdict",
            prompt_ref="verifier@v-0a1b2c3d")


def test_same_inputs_same_key():
    assert cache_key(**BASE) == cache_key(**BASE)


def test_alias_drift_is_a_miss():
    assert cache_key(**{**BASE, "resolved_model": "glm-5.3"}) != cache_key(**BASE)


def test_every_component_participates_in_the_key():
    for field, value in [("messages", [{"role": "user", "content": "bye"}]),
                         ("sampling", {"temperature": 0.7}),
                         ("schema_name", "Other"),
                         ("prompt_ref", "verifier@v-ffffffff"),
                         ("endpoint", "embeddings")]:
        assert cache_key(**{**BASE, field: value}) != cache_key(**BASE), field


def test_key_is_order_insensitive_for_sampling_dicts():
    a = cache_key(**{**BASE, "sampling": {"temperature": 0.0, "seed": 7}})
    b = cache_key(**{**BASE, "sampling": {"seed": 7, "temperature": 0.0}})
    assert a == b


def test_put_get_round_trip_and_miss(tmp_path: Path):
    cache = CallCache(tmp_path / "call-cache.sqlite")
    key = cache_key(**BASE)
    assert cache.get(key) is None
    cache.put(key, {"text": "supported", "tokens_in": 10, "tokens_out": 2})
    assert cache.get(key)["text"] == "supported"


def test_cache_survives_reopen(tmp_path: Path):
    path = tmp_path / "call-cache.sqlite"
    key = cache_key(**BASE)
    CallCache(path).put(key, {"text": "x"})
    assert CallCache(path).get(key) == {"text": "x"}
