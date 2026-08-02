import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_version_flag(capsys):
    from langatlas_validate.cli import main
    with pytest_raises_systemexit() as code:
        main(["--version"])
    assert code.value == 0


def test_version_string():
    import langatlas_validate
    assert langatlas_validate.__version__ == "0.1.0"


def test_version_file_matches_package():
    version_file = (REPO_ROOT / "ontology" / "VERSION").read_text().strip()
    assert version_file == "0.1.0"


class pytest_raises_systemexit:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        assert exc_type is SystemExit, f"expected SystemExit, got {exc_type}"
        self.value = exc.code
        return True
