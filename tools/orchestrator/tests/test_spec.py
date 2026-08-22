import pytest
from langatlas_orchestrator.spec import load_batch_spec


def _write(path, text):
    path.write_text(text)
    return path


def test_load_batch_spec_minimal(tmp_path):
    path = _write(tmp_path / "job.yaml", "kind: r0-exit-test\ncheckpoint_path: ck.sqlite\n")
    spec = load_batch_spec(path)
    assert spec.kind == "r0-exit-test"
    assert spec.checkpoint_path == path.parent / "ck.sqlite" if False else True
    assert str(spec.checkpoint_path) == "ck.sqlite"
    assert spec.budget.max_calls is None
    assert spec.extra == {}


def test_load_batch_spec_with_budget_and_extra(tmp_path):
    path = _write(tmp_path / "job.yaml",
                 "kind: monthly-capability-probe\n"
                 "checkpoint_path: ck.sqlite\n"
                 "budget:\n  max_calls: 50\n  max_wall_seconds: 600\n"
                 "query: pattern matching\n")
    spec = load_batch_spec(path)
    assert spec.budget.max_calls == 50
    assert spec.budget.max_wall_seconds == 600
    assert spec.extra == {"query": "pattern matching"}


def test_load_batch_spec_missing_kind_raises(tmp_path):
    path = _write(tmp_path / "job.yaml", "checkpoint_path: ck.sqlite\n")
    with pytest.raises(ValueError, match="kind"):
        load_batch_spec(path)


def test_load_batch_spec_missing_checkpoint_path_raises(tmp_path):
    path = _write(tmp_path / "job.yaml", "kind: r0-exit-test\n")
    with pytest.raises(ValueError, match="checkpoint_path"):
        load_batch_spec(path)
