"""Regression-fixture checkers owned by 1B, discovered by langatlas_validate.

Kept in this package (not in langatlas_validate) so the pre-commit validator never
grows an openai/claude-agent-sdk dependency. langatlas_validate soft-imports this
module; when it is absent, these fixtures report as skipped."""

from langatlas_pipeline.prompts import list_versions
from langatlas_pipeline.providers.replay import ReplayClient, ReplayMiss
from langatlas_pipeline.paths import FIXTURES_DIR


class _NoLiveCalls:
    """Any attempt to reach a provider during a regression run is itself the failure."""

    def __init__(self):
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kwargs):
        raise AssertionError("regression fixtures must never make a live call")


def _provider_record_replay(fixture: dict) -> str | None:
    """Replays a recorded wrapper-interface call and compares the response text.
    Catches drift in the request-shaping code (sampling defaults, response_format
    negotiation, message assembly) without any network."""
    client = ReplayClient(_NoLiveCalls(), mode="replay")
    try:
        response = client.chat.completions.create(**fixture["request"])
    except ReplayMiss as exc:
        return f"{fixture['fixture_id']}: {exc}"
    actual = response.choices[0].message.content
    expected = fixture["expect"]["text"]
    if actual != expected:
        return (f"{fixture['fixture_id']}: expected {expected!r}, got {actual!r} "
                f"(request shaping changed?)")
    return None


def _prompt_version_rerun(fixture: dict) -> str | None:
    """D41: a new prompt version triggers a *soft* (log-only) check that a regression
    fixture exists for it. Never blocks CI — it is a nudge, not a gate."""
    prompt_id = fixture["prompt_id"]
    versions = list_versions(prompt_id)
    if not versions:
        return f"{prompt_id}: no registered versions"
    latest = versions[-1]
    covered = {path.stem for path in (FIXTURES_DIR / "prompt-rerun").glob("*")} \
        if (FIXTURES_DIR / "prompt-rerun").exists() else set()
    if f"{prompt_id}-{latest}" not in covered:
        return (f"{prompt_id}: newest version {latest} has no regression fixture under "
                f"tests/fixtures/providers/prompt-rerun/ (soft: log only)")
    return None


CHECKERS = {
    "provider-record-replay": _provider_record_replay,
    "prompt-version-rerun": _prompt_version_rerun,
}
