import os
from pathlib import Path

from langatlas_pipeline.paths import PRIVATE_DIR
from langatlas_validate.paths import REPO_ROOT

FINDING_AIDS_CONFIG_PATH = REPO_ROOT / "config" / "finding-aids.yaml"

# D1/§2.2: mirrors and generated checklists are derived — private tier, never git. A
# checklist records the mirror version it was built from, so it is reproducible without
# being committed (plan decision 4).
MIRROR_ROOT = Path(os.environ.get("LANGATLAS_FINDING_AID_MIRRORS",
                                  PRIVATE_DIR / "finding-aids" / "mirrors"))
CHECKLIST_DIR = Path(os.environ.get("LANGATLAS_FINDING_AID_CHECKLISTS",
                                    PRIVATE_DIR / "finding-aids" / "checklists"))


def mirror_dir(source: str) -> Path:
    return MIRROR_ROOT / source
