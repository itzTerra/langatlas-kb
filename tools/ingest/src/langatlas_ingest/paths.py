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

# §8.6's D22 benchmark. The matrix is committed configuration; the results and verdict
# are a committed research record justifying a pinned production setting — neither is a
# derived artifact in D1's sense, so both live in git while the vectors they measure do
# not.
BENCHMARK_CONFIG_PATH = REPO_ROOT / "config" / "benchmark" / "d22-source-corpus.yaml"
BENCHMARK_DIR = REPO_ROOT / "benchmarks" / "d22-source-corpus"

# D23: verdicts are build-side and private — never written into authored YAML. The ledger
# sits beside 1B's call cache and cost log so one tarball backs up the whole private tier.
VERDICT_LEDGER_PATH = Path(os.environ.get("LANGATLAS_VERDICT_LEDGER",
                                          PRIVATE_DIR / "verdicts.sqlite"))
# D45's root-level content-keyed register. In git: it is canonical, not derived.
CONTRADICTIONS_PATH = REPO_ROOT / "contradictions.yaml"
# Section 6.2's per-batch known-bad canaries: golden item ids that must never come back
# admitting. A pass halts the batch.
GOLDEN_CANARIES_PATH = GOLDEN_VERIFIER_DIR / "canaries.yaml"
# The published calibration record — the measured error rates are an honesty feature
# (Section 6.2), so they live in git next to the D22 benchmark's verdict record.
VERIFIER_CALIBRATION_DIR = REPO_ROOT / "benchmarks" / "d24-verifier"
