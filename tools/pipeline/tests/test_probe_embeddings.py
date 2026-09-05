import pytest
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_pipeline.observability.probe import (
    EmbeddingProbe, apply_embedding_probe, diff_embeddings, probe_embedding,
    probe_embeddings,
)


class _FakeEmbeddings:
    def __init__(self, dimensions, fail=False):
        self.dimensions = dimensions
        self.fail = fail
        self.calls = []

    def create(self, *, model, input):
        self.calls.append((model, list(input)))
        if self.fail:
            raise RuntimeError("model not found")

        class Item:
            embedding = [0.0] * self.dimensions

        class Response:
            data = [Item()]
            usage = type("U", (), {"prompt_tokens": 3})()

        return Response()


class _FakeClient:
    def __init__(self, dimensions, fail=False):
        self.embeddings = _FakeEmbeddings(dimensions, fail)


class _FakeConfig:
    def __init__(self, entries):
        self.capabilities = {"embeddings": entries}
        self.providers = {}

    def completion_settings(self):
        return {"min_interval_seconds": {"embedding": 0.0}, "max_attempts": 1}


class _FakeRecorder:
    def __init__(self):
        self.calls = []

    def record_call(self, **kwargs):
        self.calls.append(kwargs)


class _FakeCtx:
    def __init__(self, entries):
        self.config = _FakeConfig(entries)
        self.recorder = _FakeRecorder()
        self.cache = None

    def check_budget(self, **kwargs):
        pass

    def note_usage(self, **kwargs):
        pass


def test_probe_measures_dimensions_from_the_returned_vector():
    ctx = _FakeCtx({"m": {"dimensions": 99, "max_input_tokens": 512}})
    probe = probe_embedding(ctx, "m", client=_FakeClient(768))
    assert probe.reachable is True
    # The *measured* length wins over the recorded 99 — that is the whole point.
    assert probe.dimensions == 768
    assert probe.max_input_tokens == 512


def test_probe_records_an_unreachable_model_instead_of_raising():
    ctx = _FakeCtx({"m": {"dimensions": 768, "max_input_tokens": 512}})
    probe = probe_embedding(ctx, "m", client=_FakeClient(768, fail=True))
    assert probe.reachable is False
    assert probe.dimensions is None
    assert "model not found" in probe.error


def test_probe_leaves_max_input_tokens_none_for_an_unknown_model():
    ctx = _FakeCtx({})
    probe = probe_embedding(ctx, "brand-new", client=_FakeClient(1024))
    assert probe.dimensions == 1024
    assert probe.max_input_tokens is None


def test_probe_embeddings_defaults_to_the_recorded_roster():
    ctx = _FakeCtx({"a": {"dimensions": 4, "max_input_tokens": 512},
                    "b": {"dimensions": 4, "max_input_tokens": 512}})
    probed = probe_embeddings(ctx, client=_FakeClient(4))
    assert sorted(probed) == ["a", "b"]


def test_diff_reports_a_dimension_change():
    current = {"embeddings": {"a": {"dimensions": 768, "max_input_tokens": 512}}}
    probed = {"a": EmbeddingProbe("a", 1024, 512, True)}
    assert diff_embeddings(current, probed) == [
        "a.dimensions: 768 -> 1024"]


def test_apply_refuses_an_entry_with_no_max_input_tokens(tmp_path: Path):
    path = tmp_path / "provider_capabilities.yaml"
    path.write_text("version: 1\nembeddings:\n  a: {dimensions: 4, max_input_tokens: 8}\n")
    refused = apply_embedding_probe(path, {"new": EmbeddingProbe("new", 1024, None, True)})
    assert refused == ["new"]
    data = YAML(typ="safe").load(path.read_text())
    assert "new" not in data["embeddings"]


def test_apply_writes_a_complete_entry_and_keeps_the_others(tmp_path: Path):
    path = tmp_path / "provider_capabilities.yaml"
    path.write_text("version: 1\nembeddings:\n  a: {dimensions: 4, max_input_tokens: 8}\n")
    refused = apply_embedding_probe(path, {"new": EmbeddingProbe("new", 1024, 512, True)})
    assert refused == []
    data = YAML(typ="safe").load(path.read_text())
    assert data["embeddings"]["new"] == {"dimensions": 1024, "max_input_tokens": 512}
    assert data["embeddings"]["a"] == {"dimensions": 4, "max_input_tokens": 8}


def test_apply_skips_an_unreachable_model(tmp_path: Path):
    path = tmp_path / "provider_capabilities.yaml"
    path.write_text("version: 1\nembeddings: {}\n")
    refused = apply_embedding_probe(
        path, {"gone": EmbeddingProbe("gone", None, None, False, "404")})
    assert refused == ["gone"]
