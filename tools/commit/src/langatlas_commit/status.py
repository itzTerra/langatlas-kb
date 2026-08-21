from pathlib import Path
from typing import Literal

import httpx


def github_status_checker(ctx, owner: str, repo: str, *, http_client: httpx.Client | None = None):
    """D36 §2.4: 'no status' is treated as 'not confirmed green', never as an implicit
    pass. Combines the Checks API (GitHub Actions) and the legacy Statuses API (any
    external status poster) since either can be the source of truth for a given repo."""
    http = http_client or httpx.Client(base_url="https://api.github.com")

    def checker(repo_root: Path, sha: str) -> Literal["green", "red", "unknown"]:
        headers = {"Authorization": f"Bearer {ctx.github_token()}",
                  "Accept": "application/vnd.github+json"}
        checks = http.get(f"/repos/{owner}/{repo}/commits/{sha}/check-runs", headers=headers)
        checks.raise_for_status()
        runs = checks.json().get("check_runs", [])
        if any(r["status"] == "completed" and r["conclusion"] != "success" for r in runs):
            return "red"

        statuses = http.get(f"/repos/{owner}/{repo}/commits/{sha}/status", headers=headers)
        statuses.raise_for_status()
        state = statuses.json().get("state")
        if state == "failure" or state == "error":
            return "red"

        has_signal = bool(runs) or state in ("success", "pending")
        if not has_signal:
            return "unknown"
        if runs and not all(r["status"] == "completed" and r["conclusion"] == "success"
                            for r in runs):
            return "unknown"
        if state not in (None, "success"):
            return "unknown"
        return "green"

    return checker
