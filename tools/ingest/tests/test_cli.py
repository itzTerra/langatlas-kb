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
