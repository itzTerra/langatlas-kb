import pytest

from langatlas_orchestrator import driver
from langatlas_orchestrator.registry import ItemOutcome, register_job_kind


def test_overrides_parse_as_yaml_scalars():
    assert driver.parse_overrides(["cycle=1", "alias=deepseek", "dry=true"]) == {
        "cycle": 1, "alias": "deepseek", "dry": True}


def test_an_override_without_an_equals_sign_is_refused():
    with pytest.raises(ValueError):
        driver.parse_overrides(["cycle"])


def test_run_merges_overrides_into_the_spec_extra(tmp_path):
    seen = {}
    register_job_kind("override-probe",
                      lambda extra, root: seen.update(extra) or [],
                      lambda ctx, key, extra, root: ItemOutcome(status="done"))
    spec = tmp_path / "spec.yaml"
    spec.write_text(f"kind: override-probe\ncheckpoint_path: {tmp_path / 'cp.sqlite'}\n"
                    "cycle: 9\nkeep: true\n")

    code = driver.run(spec, repo_root=tmp_path, status_path=tmp_path / "status.json",
                      transcripts_root=tmp_path / "transcripts",
                      private_dir=tmp_path / "private", extra_overrides={"cycle": 2})

    assert code == driver.EXIT_OK
    assert seen == {"cycle": 2, "keep": True}
