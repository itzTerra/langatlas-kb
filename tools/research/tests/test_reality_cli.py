"""The offline `reality` commands, with no git, no database and no provider."""
import pytest

from langatlas_questionnaire.spec import write_spec
from langatlas_research.cli import main
from langatlas_research.paths import themes_path
from langatlas_research.reality.record import load_record, replace_language, save_record


@pytest.fixture
def opened(research_repo, r5_record, r5_spec):
    write_spec(r5_spec, research_repo)
    save_record(r5_record, repo_root=research_repo)
    return research_repo


def _cli(repo, *args):
    return main(["--repo-root", str(repo), "reality", *args])


def test_status_prints_the_cells_the_findings_and_the_open_log(opened, r5_record, r5_cell,
                                                               r5_run, capsys):
    scope = "No compile-time checking phase exists."
    record = replace_language(r5_record, "python", cells=[
        r5_cell("python", "dynamic-typing", answer="absent", status="admitted",
                absence_scope=scope),
        r5_cell("python", "static-typing", answer="absent", status="admitted",
                absence_scope=scope),
        r5_cell("python", "type-inference", mappable=False)], uncovered=[], run=r5_run)
    save_record(record, repo_root=opened)
    assert _cli(opened, "status", "1") == 0
    out = capsys.readouterr().out
    assert "python--type-inference" in out and "unmappable" in out
    assert "uninhabited type-checking-discipline=static-typing" in out
    assert "unfittable python--type-checking-discipline" in out
    assert "open shakedown entries: 0" in out


def test_shakedown_add_list_and_close(opened, capsys):
    assert _cli(opened, "shakedown", "1", "--add", "sources",
                "--detail", "erlang: no spec ingested") == 0
    key = load_record("01-typing", repo_root=opened)["shakedown"][0]["key"]
    assert _cli(opened, "shakedown", "1") == 0
    assert key in capsys.readouterr().out
    assert _cli(opened, "shakedown", "1", "--close", key,
                "--resolution", "accepted: Erlang is a phase-3 language") == 0
    assert load_record("01-typing", repo_root=opened)["shakedown"][0]["status"] == "closed"


def test_shakedown_edits_need_their_text(opened):
    assert _cli(opened, "shakedown", "1", "--add", "sources") == 1
    assert _cli(opened, "shakedown", "1", "--close", "s-sources-00000000",
                "--resolution", "x") == 1


def test_shakedown_is_gated_on_a_fresh_sign_off(opened, capsys):
    """`_GATED` includes "shakedown" because it can commit via `land_record` once the reality
    check is tracked — D27 requires sign-off before any such commit path. A stale sign-off
    (the theme list edited since) must block the command before it touches the record. `main()`
    catches `SignOffStale` (a `ResearchError`) and turns it into a nonzero exit, so that's the
    calling convention asserted here rather than a raised exception."""
    before = load_record("01-typing", repo_root=opened)
    themes_path(opened).write_text(
        themes_path(opened).read_text().replace("Type systems,", "Type systems (edited),"))
    assert _cli(opened, "shakedown", "1", "--add", "sources",
                "--detail", "erlang: no spec ingested") == 1
    assert "re-sign the cycle" in capsys.readouterr().err
    assert load_record("01-typing", repo_root=opened) == before


def test_finalize_reports_its_blockers_and_exits_nonzero(opened, capsys):
    assert _cli(opened, "finalize", "1") == 1
    assert "never classified" in capsys.readouterr().err
