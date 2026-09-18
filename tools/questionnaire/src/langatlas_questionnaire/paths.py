import os
from pathlib import Path

# src layout: .../tools/questionnaire/src/langatlas_questionnaire/paths.py -> parents[4] == repo.
REPO_ROOT = Path(os.environ.get("LANGATLAS_ROOT", Path(__file__).resolve().parents[4]))
