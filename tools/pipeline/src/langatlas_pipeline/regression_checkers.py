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


RERUN_DIR = FIXTURES_DIR / "prompt-version-rerun"


def _prompt_version_rerun(fixture: dict) -> str | None:
    """D41: a new prompt version triggers a *soft* (log-only) check that a regression
    fixture exists for it. Never blocks CI — it is a nudge, not a gate.

    Two fixture shapes share this kind, distinguished by the `version` key:

    - a *tracker* (no `version`) — "prompt X should have rerun coverage for whatever its
      newest version is"; this is the check that warns.
    - a *coverage record* (`version: v-xxxxxxxx`) — the evidence that satisfies a
      tracker, named `<prompt_id>-<version>.yaml` in this same directory. Checking it
      only means confirming its version is still a registered one, so a coverage file
      left behind for a deleted version is visible rather than silently reassuring.
    """
    prompt_id = fixture["prompt_id"]
    versions = list_versions(prompt_id)
    if not versions:
        return f"{prompt_id}: no registered versions"
    declared = fixture.get("version")
    if declared is not None:
        if declared not in versions:
            return (f"{prompt_id}: rerun coverage recorded for {declared}, which is not a "
                    f"registered version (soft: log only)")
        return None
    latest = versions[-1]
    covered = {path.stem for path in RERUN_DIR.glob("*.yaml")} \
        if RERUN_DIR.exists() else set()
    if f"{prompt_id}-{latest}" not in covered:
        return (f"{prompt_id}: newest version {latest} has no rerun coverage — add "
                f"tests/fixtures/providers/prompt-version-rerun/{prompt_id}-{latest}.yaml "
                f"(soft: log only)")
    return None


CHECKERS = {
    "provider-record-replay": _provider_record_replay,
    "prompt-version-rerun": _prompt_version_rerun,
}
