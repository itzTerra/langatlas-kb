import json
import time
from pathlib import Path

from langatlas_pipeline.paths import PRIVATE_DIR

# D43 §2.4: "alerting" in a solo-dev, no-new-infra project is the run halting plus this
# glanceable file, surfaced by `langatlas-report orchestrator-status` — no cron mail, no
# notification service.
STATUS_PATH = PRIVATE_DIR / "orchestrator" / "status.json"


def read_status(path: Path | None = None) -> dict:
    path = path or STATUS_PATH
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def write_status(kind: str, *, state: str, reason: str | None = None,
                 paused_at: float | None = None, paused_until: float | None = None,
                 items_remaining: int | None = None, path: Path | None = None) -> None:
    path = path or STATUS_PATH
    status = read_status(path)
    status[kind] = {
        "state": state, "reason": reason, "paused_at": paused_at,
        "paused_until": paused_until, "items_remaining": items_remaining,
        "updated_at": time.time(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
