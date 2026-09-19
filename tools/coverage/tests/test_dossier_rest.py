from langatlas_coverage.dossier import (
    build_dossier, churn, gather, graph_health, pipeline_readiness,
)
import pytest

from langatlas_coverage.metrics import load_store
from langatlas_coverage.report import main


def _manifest(number, *, settled=(), nodes=("alpha",)):
    return {"migration_id": f"000{number}-x", "cycle": number, "settled_themes": list(settled),
            "dispositions": [{"op": "remove", "node": node, "fact_remap": []} for node in nodes]}


def test_churn_counts_settled_restructures_in_the_last_two_cycles(make_inputs, make_cycle):
    cycles = (make_cycle(1, "typing"), make_cycle(2, "memory-management"),
              make_cycle(3, "concurrency"))
    plan = {"nodes": [{"id": "alpha", "debate_id": "d-01-typing-001", "status": "minted",
                       "key": "alpha"}], "edges": [], "quality_edges": [], "dimensions": [],
            "qualities": []}

    quiet = churn(make_inputs(cycles=cycles, manifests=(_manifest(1, settled=("typing",)),)))
    noisy = churn(make_inputs(cycles=cycles, plans={"01-typing": plan},
                              manifests=(_manifest(3, settled=("typing",)),)))

    assert quiet.status == "met"
    assert noisy.status == "not-met"
    assert "Debated R4 carves later migrated (D30): alpha" in noisy.lines
    assert churn(make_inputs(cycles=cycles[:1])).status == "no-data"


def test_graph_health_reports_orphans_degrees_and_crossings(coverage_store, make_inputs):
    for node in ("static-typing", "type-inference", "ownership", "lonely"):
        coverage_store.feature(node)
    coverage_store.concept("type-system")
    coverage_store.edge("requires", "type-inference", "static-typing")
    coverage_store.edge("influences", "ownership", "static-typing")
    membership = {"static-typing": "typing", "type-inference": "typing",
                  "ownership": "memory-management", "lonely": "typing"}

    item = graph_health(make_inputs(store=load_store(coverage_store.root), membership=membership))

    assert item.status == "info"
    assert "Orphan features (no edge, quality edge or rule): 1 — lonely" in item.lines
    assert "Concepts no feature realizes: 1 — type-system" in item.lines
    assert "Feature-edge degree distribution: 0: 1, 1: 2, 2–3: 1, 4–7: 0, 8+: 0" in item.lines
    assert "Cross-theme edges: 1/2 (50.0%); theme pairs connected: 1/1" in item.lines
    assert "Nodes no cycle minted: 1 — type-system" in item.lines


def test_pipeline_readiness_needs_green_eval_closed_shakedown_and_a_valid_spec(make_inputs):
    green = {"thresholds_met": True, "false_accept_rate": 0.01, "false_reject_rate": 0.05,
             "generated": "2026-10-01"}
    shaken = {"01-typing": {"shakedown": [{"key": "s-sources-1", "component": "sources",
                                           "detail": "erlang: no spec", "status": "open"}]}}

    assert pipeline_readiness(make_inputs(calibration=green)).status == "met"
    assert pipeline_readiness(make_inputs(calibration={**green, "thresholds_met": False})) \
        .status == "not-met"
    assert pipeline_readiness(make_inputs(calibration=green, reality=shaken)).status == "not-met"
    failed = pipeline_readiness(make_inputs(calibration=green, compile_errors=None,
                                            compile_failure="CompileError: boom"))
    assert failed.status == "not-met"
    assert "Questionnaire compiler: FAILED — CompileError: boom" in failed.lines


def test_gather_reads_the_repository(coverage_store, tmp_path):
    coverage_store.feature("static-typing")
    (coverage_store.root / "benchmarks" / "d24-verifier").mkdir(parents=True)
    (coverage_store.root / "benchmarks" / "d24-verifier" / "calibration.json").write_text(
        '{"thresholds_met": false, "false_accept_rate": 0.037, "false_reject_rate": 0.07}')

    inputs = gather(coverage_store.root, ledger_path=tmp_path / "none.sqlite",
                    cost_log=tmp_path / "none.jsonl")
    items = build_dossier(inputs)

    assert inputs.verification is None and inputs.calibration["thresholds_met"] is False
    assert [item.key for item in items] == ["sourcing-integrity", "reality-checks", "churn",
                                            "graph-health", "pipeline-readiness"]


def test_the_dossier_command_prints_the_five_items(coverage_store, tmp_path, capsys):
    coverage_store.feature("static-typing")

    assert main(["--repo-root", str(coverage_store.root), "dossier",
                 "--ledger", str(tmp_path / "none.sqlite"),
                 "--cost-log", str(tmp_path / "none.jsonl")]) == 0

    out = capsys.readouterr().out
    for title in ("Sourcing integrity", "Reality-check results", "Churn trend", "Graph health",
                  "Pipeline readiness"):
        assert f"| {title} |" in out


def test_churn_boundary_only_the_last_two_cycles_count(make_inputs, make_cycle):
    cycles = (make_cycle(1, "typing"), make_cycle(2, "memory-management"),
              make_cycle(3, "concurrency"))
    old = churn(make_inputs(cycles=cycles, manifests=(_manifest(1, settled=("typing",)),)))
    edge = churn(make_inputs(cycles=cycles, manifests=(_manifest(2, settled=("typing",)),)))
    two = churn(make_inputs(cycles=cycles[:2], manifests=(_manifest(2, settled=("typing",)),)))

    assert (old.status, edge.status, two.status) == ("met", "not-met", "not-met")
    assert "  cycle 02: 1 settled-theme restructure(s)" in edge.lines
    assert "Debated R4 carves later migrated (D30): none" in old.lines


def test_the_per_cycle_gate_lines_follow_cycle_number_not_input_order(make_inputs, make_cycle):
    from langatlas_coverage.dossier import sourcing_integrity
    from langatlas_coverage.metrics import Store

    store = Store(features={"alpha": {}}, concepts={}, edges={}, quality_edges={}, rules={},
                  instances={}, dimensions={},
                  facts=({"anchor": "alpha#summary", "fact_id": "f1", "claim": "x"},))
    cycles = (make_cycle(2, "memory-management"), make_cycle(1, "typing"))

    item = sourcing_integrity(make_inputs(store=store, cycles=cycles,
                                          verification={"f1": "verified"}))

    gate = [line for line in item.lines if "R4/R6 gate" in line]
    assert [line.split(":")[0].strip() for line in gate] == ["01-typing", "02-memory-management"]


@pytest.mark.parametrize("degree,hub_bucket", [(1, "1"), (2, "2–3"), (3, "2–3"), (4, "4–7"),
                                                (7, "4–7"), (8, "8+")])
def test_graph_health_degree_bucket_boundaries(coverage_store, make_inputs, degree, hub_bucket):
    coverage_store.feature("hub")
    for index in range(degree):
        coverage_store.feature(f"leaf-{index}")
        coverage_store.edge("requires", "hub", f"leaf-{index}")

    item = graph_health(make_inputs(store=load_store(coverage_store.root)))

    counts = {"0": 0, "1": degree, "2–3": 0, "4–7": 0, "8+": 0}
    counts[hub_bucket] += 1
    if hub_bucket == "1":
        counts["1"] = degree + 1
    expected = "Feature-edge degree distribution: " + ", ".join(
        f"{label}: {counts[label]}" for label in ("0", "1", "2–3", "4–7", "8+"))
    assert expected in item.lines


def test_pipeline_readiness_never_reads_missing_or_malformed_inputs_as_met(make_inputs):
    assert pipeline_readiness(make_inputs()).status == "not-met"
    missing = pipeline_readiness(make_inputs(calibration=None))
    assert "Verifier calibration: missing (benchmarks/d24-verifier/calibration.json)" \
        in missing.lines
    assert pipeline_readiness(make_inputs(calibration=[1])).status == "not-met"
    assert pipeline_readiness(make_inputs(calibration={"thresholds_met": "yes"})).status \
        == "not-met"


def test_pipeline_readiness_closed_shakedown_and_usage_lines(make_inputs):
    green = {"thresholds_met": True}
    closed = {"01-typing": {"shakedown": [{"key": "k", "component": "c", "detail": "d",
                                           "status": "closed"}]}}
    item = pipeline_readiness(make_inputs(calibration=green, reality=closed,
                                          claude_by_cycle={"01-typing": (2, 9)}))

    assert item.status == "met"
    assert "Open R5 shakedown entries: 0" in item.lines
    assert "  01-typing: 2 session(s), 9 message(s)" in item.lines


def test_gather_sorts_cycles_and_reads_usage_and_manifests(coverage_store, tmp_path):
    coverage_store.feature("static-typing")
    for number, theme in ((2, "memory-management"), (1, "typing")):
        coverage_store.write(
            f"research/cycles/{number:02d}-{theme}.yaml",
            f"cycle: {number}\ntheme: {theme}\ntheme_digest: aaaaaaaaaaaaaaaa\n"
            "status: r5-done\nlanguages: [python]\nnodes_minted: []\n")
    (tmp_path / "cost.jsonl").write_text("")

    inputs = gather(coverage_store.root, ledger_path=tmp_path / "none.sqlite",
                    cost_log=tmp_path / "cost.jsonl")

    assert [cycle.number for cycle in inputs.cycles] == [1, 2]
    assert inputs.calibration is None and inputs.claude_by_cycle == {}
    assert isinstance(inputs.manifests, tuple)


def test_a_corrupt_calibration_file_is_a_typed_error_with_exit_2(coverage_store, tmp_path,
                                                                 capsys):
    coverage_store.feature("static-typing")
    directory = coverage_store.root / "benchmarks" / "d24-verifier"
    directory.mkdir(parents=True)
    (directory / "calibration.json").write_text("{not json")

    code = main(["--repo-root", str(coverage_store.root), "dossier",
                 "--ledger", str(tmp_path / "none.sqlite"), "--cost-log", str(tmp_path / "c")])

    assert code == 2 and "calibration.json" in capsys.readouterr().err


def test_a_corrupt_ledger_is_a_typed_error_with_exit_2(coverage_store, tmp_path, capsys):
    coverage_store.feature("static-typing")
    (tmp_path / "bad.sqlite").write_text("this is not sqlite")

    code = main(["--repo-root", str(coverage_store.root), "dossier",
                 "--ledger", str(tmp_path / "bad.sqlite"), "--cost-log", str(tmp_path / "c")])

    assert code == 2 and "bad.sqlite" in capsys.readouterr().err


def test_a_corrupt_migration_manifest_is_a_typed_error_with_exit_2(coverage_store, tmp_path,
                                                                   capsys):
    from langatlas_validate.migrate import MANIFEST_NAME, MIGRATIONS_REL

    coverage_store.feature("static-typing")
    coverage_store.write(f"{MIGRATIONS_REL}/0001-x/{MANIFEST_NAME}", "a: [unclosed")

    code = main(["--repo-root", str(coverage_store.root), "dossier",
                 "--ledger", str(tmp_path / "none.sqlite"), "--cost-log", str(tmp_path / "c")])

    assert code == 2 and "manifest" in capsys.readouterr().err


def test_a_corrupt_cycle_file_is_a_typed_error_with_exit_2(coverage_store, tmp_path, capsys):
    coverage_store.feature("static-typing")
    coverage_store.write("research/cycles/01-typing.yaml", "cycle: [unclosed")

    code = main(["--repo-root", str(coverage_store.root), "dossier",
                 "--ledger", str(tmp_path / "none.sqlite"), "--cost-log", str(tmp_path / "c")])

    assert code == 2 and "cycles" in capsys.readouterr().err


def test_an_empty_store_gives_no_data_and_never_met(tmp_path, capsys):
    root = tmp_path / "empty"
    root.mkdir()

    assert main(["--repo-root", str(root), "dossier", "--ledger", str(tmp_path / "n.sqlite"),
                 "--cost-log", str(tmp_path / "c")]) == 0

    out = capsys.readouterr().out
    assert "| Sourcing integrity | no-data |" in out
    assert "| Reality-check results | no-data |" in out
    assert "| Churn trend | no-data |" in out
    assert "| Graph health | info |" in out
    assert "| Pipeline readiness | not-met |" in out
    assert "Verifier calibration: missing" in out


def test_the_dossier_snapshot_is_written_under_reports(coverage_store, tmp_path, capsys):
    coverage_store.feature("static-typing")

    assert main(["--repo-root", str(coverage_store.root), "dossier", "--snapshot",
                 "--ledger", str(tmp_path / "n.sqlite"), "--cost-log", str(tmp_path / "c")]) == 0

    written = list((coverage_store.root / "reports").glob("coverage-dossier-*.md"))
    assert len(written) == 1
    assert written[0].read_text() == capsys.readouterr().out
