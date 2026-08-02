import os
from pathlib import Path

# src layout: .../tools/validate/src/langatlas_validate/paths.py -> parents[4] == repo root.
# Overridable via LANGATLAS_ROOT for the case where this package is installed as a real
# wheel into site-packages, where parents[4] would resolve to something arbitrary.
REPO_ROOT = Path(os.environ.get("LANGATLAS_ROOT", Path(__file__).resolve().parents[4]))
SCHEMA_DIR = REPO_ROOT / "ontology" / "schema"
CLAIM_TEMPLATE_DIR = REPO_ROOT / "ontology" / "claim-templates"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "providers"
