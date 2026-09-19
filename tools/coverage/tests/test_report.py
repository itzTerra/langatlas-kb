import subprocess
import sys
from pathlib import Path

from langatlas_coverage.report import main


def test_gaps_prints_and_optionally_snapshots(coverage_store, capsys):
    coverage_store.feature("static-typing", layer=3, dimension="typing-discipline")
    root = str(coverage_store.root)

    assert main(["--repo-root", root, "gaps", "--min-instances", "3"]) == 0
    assert "--min-instances 3" in capsys.readouterr().out

    assert main(["--repo-root", root, "gaps", "--snapshot"]) == 0
    [snapshot] = (coverage_store.root / "reports").glob("coverage-gaps-*.md")
    assert "static-typing" in snapshot.read_text()


def test_the_rendered_report_is_the_actual_table(coverage_store, capsys):
    coverage_store.feature("static-typing", layer=3, dimension="typing-discipline")
    coverage_store.instance("haskell", "static-typing")

    assert main(["--repo-root", str(coverage_store.root), "gaps"]) == 0

    out = capsys.readouterr().out
    assert "| typing-discipline | static-typing | 1 | 0 | 1 | thin |" in out
    assert "1 of 1 dimension value(s) below 2." in out
    assert "near-meaningless before D28 phase 1" in out
    assert "No FeatureInstance records yet" not in out


def test_an_empty_store_renders_a_report(tmp_path, capsys):
    assert main(["--repo-root", str(tmp_path), "gaps"]) == 0

    out = capsys.readouterr().out
    assert "No FeatureInstance records yet" in out
    assert "0 of 0 dimension value(s) below 2." in out


def test_a_missing_repo_root_is_a_typed_error(tmp_path, capsys):
    assert main(["--repo-root", str(tmp_path / "nope"), "gaps"]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_a_malformed_record_is_a_typed_error(coverage_store, capsys):
    coverage_store.write("features/broken.yaml", "id: [unclosed\n")

    assert main(["--repo-root", str(coverage_store.root), "gaps"]) == 2
    assert capsys.readouterr().err.startswith("error:")


def test_a_record_with_an_unexpected_shape_is_a_typed_error(coverage_store, capsys):
    coverage_store.write("features/odd.yaml", "- just\n- a list\n")

    assert main(["--repo-root", str(coverage_store.root), "gaps"]) == 2
    assert capsys.readouterr().err.startswith("error:")


def test_a_malformed_taxonomy_is_a_typed_error(coverage_store, capsys):
    coverage_store.write("ontology/taxonomy/dimensions.yaml", "dimensions:\n  - notaslug: x\n")

    assert main(["--repo-root", str(coverage_store.root), "gaps"]) == 2
    assert "dimensions.yaml" in capsys.readouterr().err


def test_the_spec_path_shim_works_from_the_repo_root(coverage_store):
    repo_root = Path(__file__).resolve().parents[3]
    coverage_store.feature("static-typing", layer=3, dimension="typing-discipline")

    result = subprocess.run(
        [sys.executable, "tools/coverage/report.py", "--repo-root", str(coverage_store.root),
         "gaps"], cwd=repo_root, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert "| typing-discipline | static-typing | 0 | 0 | 0 | thin |" in result.stdout
