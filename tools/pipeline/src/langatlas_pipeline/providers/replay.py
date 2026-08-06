import hashlib
import json
import os
from pathlib import Path
from langatlas_pipeline.paths import FIXTURES_DIR
from langatlas_pipeline.transcripts.redaction import scrub_secrets

RECORD_REPLAY_DIR = FIXTURES_DIR / "record-replay"


class ReplayMiss(Exception):
    """In replay mode a cache miss is a test failure, never a live call."""


def fixture_path(request: dict, *, fixtures_dir: Path | None = None) -> Path:
    payload = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return (fixtures_dir or RECORD_REPLAY_DIR) / f"{digest}.json"


def _fake_response(text: str, model: str, tokens_in: int, tokens_out: int):
    return type("R", (), {
        "model": model,
        "choices": [type("C", (), {"message": type("M", (), {"content": text})(),
                                   "finish_reason": "stop"})()],
        "usage": type("U", (), {"prompt_tokens": tokens_in,
                                "completion_tokens": tokens_out})(),
    })()


class _Completions:
    def __init__(self, owner):
        self.owner = owner

    def create(self, **kwargs):
        return self.owner._create(**kwargs)


class ReplayClient:
    """Record/replay at the wrapper interface (D26) — simpler than HTTP taping and it
    survives transport-library upgrades. Fixture scrubbing reuses the D18 secret rules.

    mode: "off" (pass through) | "record" (call through, write fixture) | "replay"
    (fixture or bust). `LANGATLAS_REPLAY` sets the default."""

    def __init__(self, inner, *, mode: str | None = None,
                 fixtures_dir: Path | None = None):
        self.inner = inner
        self.mode = mode or os.environ.get("LANGATLAS_REPLAY", "off")
        self.fixtures_dir = fixtures_dir or RECORD_REPLAY_DIR
        self.chat = type("Chat", (), {"completions": _Completions(self)})()

    def _create(self, **kwargs):
        path = fixture_path(kwargs, fixtures_dir=self.fixtures_dir)
        if self.mode == "replay":
            if not path.exists():
                raise ReplayMiss(f"no fixture for this request: {path.name}")
            data = json.loads(path.read_text())
            return _fake_response(data["response"]["text"], data["response"]["model"],
                                  data["response"]["tokens_in"],
                                  data["response"]["tokens_out"])
        response = self.inner.chat.completions.create(**kwargs)
        if self.mode == "record":
            scrubbed, _ = scrub_secrets(json.dumps(kwargs, ensure_ascii=False))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "request": json.loads(scrubbed),
                "response": {
                    "text": response.choices[0].message.content,
                    "model": response.model,
                    "tokens_in": response.usage.prompt_tokens,
                    "tokens_out": response.usage.completion_tokens,
                },
            }, indent=2, ensure_ascii=False) + "\n")
        return response
