# tools/ingest/tests/test_cli.py
import pytest
from langatlas_ingest.cli import main


def test_version_exits_zero():
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0


def test_qa_without_a_report_is_a_nonzero_exit(snapshot_root, capsys):
    assert main(["qa", "never-ingested"]) == 1
    assert "no QA report" in capsys.readouterr().out


def test_unknown_command_is_rejected():
    with pytest.raises(SystemExit):
        main(["frobnicate"])
