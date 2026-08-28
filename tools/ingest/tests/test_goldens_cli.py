from langatlas_ingest.cli import main
from langatlas_ingest.goldens.score import VerdictOutcome

ITEMS = """
version: 1
items:
  - id: v-cli-0001
    stratum: correct
    expected_verdict: supported
    claim:
      kind: instance-exists
      text: 'instance-exists(i-cli, status=present)'
      status: present
    citation:
      source: ctm
      locator: 'p. 1'
"""


def always_supported(item):
    return VerdictOutcome("supported")


def always_unsupported(item):
    return VerdictOutcome("unsupported")


def test_golden_validate_reports_a_clean_set(tmp_path, capsys):
    (tmp_path / "items-cli.yaml").write_text(ITEMS)
    code = main(["golden-validate", "--verifier-dir", str(tmp_path)])
    assert code == 0
    assert "0 errors" in capsys.readouterr().out


def test_golden_validate_exits_one_on_a_bad_item(tmp_path, capsys):
    (tmp_path / "items-cli.yaml").write_text(
        ITEMS.replace("expected_verdict: supported", "expected_verdict: unsupported"))
    assert main(["golden-validate", "--verifier-dir", str(tmp_path)]) == 1
    assert "cannot expect verdict" in capsys.readouterr().out


def test_golden_score_exits_three_when_no_verifier_is_registered(tmp_path, capsys):
    (tmp_path / "items-cli.yaml").write_text(ITEMS)
    assert main(["golden-score", "--verifier-dir", str(tmp_path)]) == 3
    assert "no verifier registered" in capsys.readouterr().out.lower()


def test_golden_score_runs_an_explicit_entry_point_and_gates_on_thresholds(tmp_path, capsys):
    (tmp_path / "items-cli.yaml").write_text(ITEMS)
    good = "tests.test_goldens_cli:always_supported"
    assert main(["golden-score", "--verifier-dir", str(tmp_path),
                 "--verifier", good]) == 0
    bad = "tests.test_goldens_cli:always_unsupported"
    assert main(["golden-score", "--verifier-dir", str(tmp_path),
                 "--verifier", bad]) == 2
    assert "false reject" in capsys.readouterr().out.lower()


def test_golden_score_writes_the_machine_readable_error_rates(tmp_path):
    import json
    (tmp_path / "items-cli.yaml").write_text(ITEMS)
    out = tmp_path / "error-rates.json"
    main(["golden-score", "--verifier-dir", str(tmp_path),
          "--verifier", "tests.test_goldens_cli:always_supported", "--json", str(out)])
    payload = json.loads(out.read_text())
    assert payload["items"] == 1 and "generated" in payload
