import json
import pytest
from pathlib import Path
from langatlas_pipeline.providers.replay import ReplayClient, ReplayMiss, fixture_path


class RealishClient:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": self})()
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return type("R", (), {
            "model": "glm-5.2",
            "choices": [type("C", (), {"message": type("M", (), {"content": "pong"})(),
                                       "finish_reason": "stop"})()],
            "usage": type("U", (), {"prompt_tokens": 9, "completion_tokens": 1})(),
        })()


REQUEST = {"model": "glm", "messages": [{"role": "user", "content": "ping"}],
           "temperature": 0.0}


def test_record_writes_a_scrubbed_fixture(tmp_path: Path):
    inner = RealishClient()
    client = ReplayClient(inner, mode="record", fixtures_dir=tmp_path)
    client.chat.completions.create(**{**REQUEST,
                                      "messages": [{"role": "user",
                                                    "content": "key: Bearer sk-abcdefghijklmnopqrst"}]})
    written = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert "sk-abcdefghijklmnopqrst" not in json.dumps(written)
    assert written["response"]["text"] == "pong"


def test_replay_returns_the_recorded_response_without_calling_through(tmp_path: Path):
    inner = RealishClient()
    ReplayClient(inner, mode="record", fixtures_dir=tmp_path).chat.completions.create(**REQUEST)
    assert inner.calls == 1
    replayer = ReplayClient(RealishClient(), mode="replay", fixtures_dir=tmp_path)
    response = replayer.chat.completions.create(**REQUEST)
    assert response.choices[0].message.content == "pong"
    assert replayer.inner.calls == 0


def test_replay_miss_is_a_test_failure(tmp_path: Path):
    with pytest.raises(ReplayMiss):
        ReplayClient(RealishClient(), mode="replay",
                     fixtures_dir=tmp_path).chat.completions.create(**REQUEST)


def test_fixture_path_is_derived_from_the_request(tmp_path: Path):
    a = fixture_path(REQUEST, fixtures_dir=tmp_path)
    b = fixture_path({**REQUEST, "temperature": 0.7}, fixtures_dir=tmp_path)
    assert a != b
    assert a.suffix == ".json"
