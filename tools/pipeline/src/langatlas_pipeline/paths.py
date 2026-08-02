import os
from pathlib import Path

# src layout: .../tools/pipeline/src/langatlas_pipeline/paths.py -> parents[4] == repo root.
# Same LANGATLAS_ROOT override convention as langatlas_validate.paths, for wheel installs.
REPO_ROOT = Path(os.environ.get("LANGATLAS_ROOT", Path(__file__).resolve().parents[4]))
CONFIG_DIR = REPO_ROOT / "config"
PROMPTS_DIR = REPO_ROOT / "prompts"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "providers"

# Private tier (§2.2): never in git, tarball-backed. 1C's snapshot store joins it here.
PRIVATE_DIR = Path(os.environ.get("LANGATLAS_PRIVATE_DIR",
                                  Path.home() / ".local" / "share" / "langatlas"))
CACHE_PATH = PRIVATE_DIR / "call-cache.sqlite"
COST_LOG_PATH = PRIVATE_DIR / "cost-log.jsonl"

# Stage 0 cloned this as a sibling of langatlas-kb.
TRANSCRIPTS_ROOT = Path(os.environ.get("LANGATLAS_TRANSCRIPTS_REPO",
                                       REPO_ROOT.parent / "langatlas-transcripts"))
