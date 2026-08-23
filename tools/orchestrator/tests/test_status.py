from langatlas_orchestrator.status import read_status, write_status


def test_read_status_corrupted_file_returns_empty_dict(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("{not valid json")
    assert read_status(path) == {}


def test_write_status_leaves_no_stray_tmp_file_behind(tmp_path):
    path = tmp_path / "status.json"
    write_status("kind-a", state="running", path=path)
    assert path.exists()
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_read_status_missing_file_returns_empty_dict(tmp_path):
    assert read_status(tmp_path / "nope" / "status.json") == {}


def test_write_then_read_round_trips(tmp_path):
    path = tmp_path / "status.json"
    write_status("r0-exit-test", state="done", reason=None, path=path)
    status = read_status(path)
    assert status["r0-exit-test"]["state"] == "done"
    assert status["r0-exit-test"]["reason"] is None


def test_write_status_preserves_other_kinds(tmp_path):
    path = tmp_path / "status.json"
    write_status("kind-a", state="running", path=path)
    write_status("kind-b", state="paused", reason="claude_limit", paused_until=999.0,
                path=path)
    status = read_status(path)
    assert status["kind-a"]["state"] == "running"
    assert status["kind-b"]["reason"] == "claude_limit"
    assert status["kind-b"]["paused_until"] == 999.0


def test_write_status_overwrites_same_kind(tmp_path):
    path = tmp_path / "status.json"
    write_status("kind-a", state="running", path=path)
    write_status("kind-a", state="done", path=path)
    status = read_status(path)
    assert status["kind-a"]["state"] == "done"
