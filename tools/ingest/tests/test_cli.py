# tools/ingest/tests/test_cli.py
import pytest
from langatlas_ingest.cli import build_parser, main


def test_version_exits_zero():
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0


def test_qa_without_a_report_is_a_nonzero_exit(snapshot_root, capsys):
    assert main(["qa", "never-ingested"]) == 1
    assert "no QA report" in capsys.readouterr().out


def test_search_subcommand_parses_its_flags():
    args = build_parser().parse_args(
        ["search", "lazy evaluation", "-k", "3", "--source", "s", "t", "--no-rerank"])
    assert args.query == "lazy evaluation" and args.k == 3
    assert args.source == ["s", "t"] and args.no_rerank is True


def test_search_defaults_leave_reranking_to_the_config():
    """`--no-rerank` is the only override; without it the CLI must not force a value
    that contradicts `models.rerank_default_on`."""
    args = build_parser().parse_args(["search", "types"])
    assert args.no_rerank is False and args.k is None and args.source == []


def test_ingest_subcommand_parses_its_stored_source_settings():
    """Both flags are per-source settings the snapshot remembers; absent, they must parse
    as "unset" so the stored value wins rather than an accidental default overriding it."""
    args = build_parser().parse_args(
        ["ingest", "rfc-2119", "--file", "/tmp/x.pdf", "--locator-kinds", "book-page",
         "--min-chars", "120"])
    assert args.locator_kinds == ["book-page"] and args.min_chars == 120

    bare = build_parser().parse_args(["ingest", "rfc-2119"])
    assert bare.locator_kinds == [] and bare.min_chars is None


def test_unknown_command_is_rejected():
    with pytest.raises(SystemExit):
        main(["frobnicate"])


def test_new_source_writes_a_normalized_validating_record(tmp_path):
    from langatlas_ingest.cli import main

    out_dir = tmp_path / "sources"
    rc = main(["new-source", "kaijanaho-2015", "thesis", "Empirical Evaluation in PL Design",
              "--tier", "B", "--grounding", "third-party-reference",
              "--canonical", "--out-dir", str(out_dir)])
    assert rc == 0
    written = (out_dir / "kaijanaho-2015.yaml").read_text()
    from ruamel.yaml import YAML
    from langatlas_validate.schema import validate_record
    from langatlas_validate.normalize import normalize_record
    data = YAML(typ="safe").load(written)
    assert validate_record(data, "source") == []
    assert normalize_record(written, "source") == written


def test_new_source_refuses_to_overwrite(tmp_path, capsys):
    from langatlas_ingest.cli import main

    out_dir = tmp_path / "sources"
    args = ["new-source", "dup-2026", "book", "Dup", "--tier", "B",
           "--grounding", "third-party-reference", "--no-canonical",
           "--acquisition-note", "test", "--out-dir", str(out_dir)]
    assert main(args) == 0
    assert main(args) == 1
    assert "already exists" in capsys.readouterr().out


def test_file_acquisitions_files_every_entry(tmp_path, monkeypatch):
    from langatlas_ingest.cli import main

    monkeypatch.setattr("langatlas_ingest.paths.REPO_ROOT", tmp_path)
    manifest = tmp_path / "acquisitions.yaml"
    manifest.write_text(
        "- source_id: harper-pfpl\n  reason: access-pending\n"
        "  detail: 'free PDF; download and drop into snapshot store'\n")
    filed: list[tuple[str, str, str, str]] = []

    class FakeQueue:
        def __init__(self, conn):
            pass

        def file(self, *, kind, source_id, reason, detail=""):
            filed.append((kind, source_id, reason, detail))
            return len(filed)

    monkeypatch.setattr("langatlas_ingest.store.SourcingQueue", FakeQueue)
    monkeypatch.setattr("langatlas_ingest.db.connect",
                        lambda dsn=None: __import__("contextlib").nullcontext(object()))
    rc = main(["file-acquisitions", "--file", str(manifest)])
    assert rc == 0
    assert filed == [("pending-source", "harper-pfpl", "access-pending",
                      "free PDF; download and drop into snapshot store")]


def test_file_acquisitions_skips_already_scaffolded_source_ids(tmp_path, monkeypatch):
    """A manifest entry whose sources/<id>.yaml already exists (e.g. a stale manifest
    re-listing a book that's since been ingested) must be skipped, not re-filed into the
    sourcing queue — otherwise it would silently reopen a pending-source entry for a
    book that's already in the corpus."""
    from langatlas_ingest.cli import main

    monkeypatch.setattr("langatlas_ingest.paths.REPO_ROOT", tmp_path)
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    (sources_dir / "harper-pfpl.yaml").write_text("id: harper-pfpl\n")

    manifest = tmp_path / "acquisitions.yaml"
    manifest.write_text(
        "- source_id: harper-pfpl\n  reason: access-pending\n"
        "  detail: 'free PDF; download and drop into snapshot store'\n")
    filed: list[tuple[str, str, str, str]] = []

    class FakeQueue:
        def __init__(self, conn):
            pass

        def file(self, *, kind, source_id, reason, detail=""):
            filed.append((kind, source_id, reason, detail))
            return len(filed)

    monkeypatch.setattr("langatlas_ingest.store.SourcingQueue", FakeQueue)
    monkeypatch.setattr("langatlas_ingest.db.connect",
                        lambda dsn=None: __import__("contextlib").nullcontext(object()))
    rc = main(["file-acquisitions", "--file", str(manifest)])
    assert rc == 0
    assert filed == []
