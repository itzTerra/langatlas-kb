import os
from pathlib import Path
from langatlas_pipeline.paths import PRIVATE_DIR

# src layout: .../tools/ingest/src/langatlas_ingest/paths.py -> parents[4] == repo root.
REPO_ROOT = Path(os.environ.get("LANGATLAS_ROOT", Path(__file__).resolve().parents[4]))
DB_DIR = REPO_ROOT / "db"
INGEST_CONFIG_PATH = REPO_ROOT / "config" / "ingest.yaml"
GOLDEN_RETRIEVAL_DIR = REPO_ROOT / "tests" / "golden" / "retrieval"

# D15/§2.2: extracted text and originals live in the private tier, beside 1B's call cache
# and cost log, so one tarball backs up the whole private side.
SNAPSHOT_ROOT = Path(os.environ.get("LANGATLAS_SNAPSHOT_ROOT", PRIVATE_DIR / "snapshots"))


def snapshot_dir(source_id: str) -> Path:
    return SNAPSHOT_ROOT / source_id

GOLDEN_VERIFIER_DIR = REPO_ROOT / "tests" / "golden" / "verifier"
# The D44 audit slice: developer-authored, no LLM in the loop, and never a tuning signal.
# A separate directory rather than a per-item flag, so "include it" is an explicit act at
# every call site instead of a filter someone can forget.
GOLDEN_VERIFIER_HELD_OUT_DIR = GOLDEN_VERIFIER_DIR / "held-out"
GOLDEN_CONTROVERSY_DIR = REPO_ROOT / "tests" / "golden" / "controversy"
GOLDEN_DEBATES_DIR = REPO_ROOT / "tests" / "golden" / "debates"
