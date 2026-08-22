from langatlas_orchestrator.checkpoint import CheckpointStore


def test_get_returns_none_for_unknown_item(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoint.sqlite")
    assert store.get(spec_kind="k", item_key="i") is None


def test_upsert_then_get_round_trips(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoint.sqlite")
    store.upsert(run_id="run-1", spec_kind="k", item_key="i", status="done",
                record_key="abc123", detail="landed as deadbeef")
    row = store.get(spec_kind="k", item_key="i")
    assert row.status == "done"
    assert row.record_key == "abc123"
    assert row.detail == "landed as deadbeef"
    assert row.run_id == "run-1"


def test_upsert_updates_in_place_not_stacking_rows(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoint.sqlite")
    store.upsert(run_id="run-1", spec_kind="k", item_key="i", status="in_progress")
    store.upsert(run_id="run-1", spec_kind="k", item_key="i", status="done",
                record_key="xyz")
    rows = store.rows_for_spec("k")
    assert len(rows) == 1
    assert rows[0].status == "done"


def test_rows_for_spec_is_ordered_and_scoped_to_kind(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoint.sqlite")
    store.upsert(run_id="r", spec_kind="a", item_key="z", status="pending")
    store.upsert(run_id="r", spec_kind="a", item_key="a", status="pending")
    store.upsert(run_id="r", spec_kind="b", item_key="a", status="pending")
    rows = store.rows_for_spec("a")
    assert [row.item_key for row in rows] == ["a", "z"]


def test_store_persists_across_reopen(tmp_path):
    path = tmp_path / "checkpoint.sqlite"
    CheckpointStore(path).upsert(run_id="r", spec_kind="k", item_key="i", status="done")
    reopened = CheckpointStore(path)
    assert reopened.get(spec_kind="k", item_key="i").status == "done"
