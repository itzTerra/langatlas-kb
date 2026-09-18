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


def test_golden_score_exits_three_when_no_verifier_is_registered(tmp_path, capsys,
                                                                  monkeypatch):
    # 2D's calibration entry point is now the config default (`verify/calibration.py`),
    # so the "unregistered" guard is exercised here by clearing it, not by the config's
    # ambient state — a config with neither entry point set is still a real, reachable
    # condition (a fresh checkout before `config/ingest.yaml` names one).
    from dataclasses import replace
    from langatlas_ingest import cli as cli_module
    from langatlas_ingest.config import IngestConfig

    unset = replace(IngestConfig.load(), verifier_entry_point=None,
                    controversy_assessor_entry_point=None)
    monkeypatch.setattr(cli_module.IngestConfig, "load", staticmethod(lambda *a, **k: unset))
    (tmp_path / "items-cli.yaml").write_text(ITEMS)
    assert main(["golden-score", "--verifier-dir", str(tmp_path)]) == 3
    assert "no verifier registered" in capsys.readouterr().out.lower()


def test_golden_score_runs_an_explicit_entry_point_and_gates_on_thresholds(tmp_path, capsys,
                                                                            monkeypatch):
    # Stage 3D's `controversy_assessor_entry_point` now names a real callable that lives in
    # `langatlas_research`, which is not importable from this package's own environment (it is
    # the other way around — `langatlas_ingest` is a path dependency of `langatlas_research`).
    # These tests exercise the verifier path only, so the ambient config default is cleared the
    # same way `test_golden_score_exits_three_when_no_verifier_is_registered` clears it.
    from dataclasses import replace
    from langatlas_ingest import cli as cli_module
    from langatlas_ingest.config import IngestConfig

    unset = replace(IngestConfig.load(), controversy_assessor_entry_point=None)
    monkeypatch.setattr(cli_module.IngestConfig, "load", staticmethod(lambda *a, **k: unset))
    (tmp_path / "items-cli.yaml").write_text(ITEMS)
    good = "tests.test_goldens_cli:always_supported"
    assert main(["golden-score", "--verifier-dir", str(tmp_path),
                 "--verifier", good]) == 0
    bad = "tests.test_goldens_cli:always_unsupported"
    assert main(["golden-score", "--verifier-dir", str(tmp_path),
                 "--verifier", bad]) == 2
    assert "false reject" in capsys.readouterr().out.lower()


def test_golden_score_with_only_verifier_flag_never_touches_the_configured_assessor(
        tmp_path, capsys, monkeypatch):
    # Finding 6: passing only `--verifier` must not also run the (expensive,
    # live-provider-calling) controversy score just because a config default happens to be
    # populated. Proven here by pointing the config default at a dotted path that does not
    # exist — if the assessor branch were reached at all, `load_entry_point` would blow up
    # trying to import it.
    from dataclasses import replace
    from langatlas_ingest import cli as cli_module
    from langatlas_ingest.config import IngestConfig

    poisoned = replace(IngestConfig.load(),
                       controversy_assessor_entry_point="nonexistent.module:not_a_thing")
    monkeypatch.setattr(cli_module.IngestConfig, "load", staticmethod(lambda *a, **k: poisoned))
    (tmp_path / "items-cli.yaml").write_text(ITEMS)
    good = "tests.test_goldens_cli:always_supported"
    assert main(["golden-score", "--verifier-dir", str(tmp_path), "--verifier", good]) == 0
    assert "false reject" in capsys.readouterr().out.lower()


def test_golden_score_writes_the_machine_readable_error_rates(tmp_path, monkeypatch):
    import json
    from dataclasses import replace
    from langatlas_ingest import cli as cli_module
    from langatlas_ingest.config import IngestConfig

    # Same reasoning as above: this test only exercises the verifier path.
    unset = replace(IngestConfig.load(), controversy_assessor_entry_point=None)
    monkeypatch.setattr(cli_module.IngestConfig, "load", staticmethod(lambda *a, **k: unset))
    (tmp_path / "items-cli.yaml").write_text(ITEMS)
    out = tmp_path / "error-rates.json"
    main(["golden-score", "--verifier-dir", str(tmp_path),
          "--verifier", "tests.test_goldens_cli:always_supported", "--json", str(out)])
    payload = json.loads(out.read_text())
    assert payload["items"] == 1 and "generated" in payload
