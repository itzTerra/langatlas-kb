"""R5's two ends against a real git repo: the committed questionnaire, and the committed
findings."""
import subprocess

import pytest
from ruamel.yaml import YAML

from langatlas_commit.land import Landed
from langatlas_questionnaire.spec import load_spec, validate_spec
from langatlas_research.cycle import load_cycle, new_cycle, sign_off
from langatlas_research.errors import R5Incomplete, R5NotReady
from langatlas_research.reality.lifecycle import finalize_r5, open_r5
from langatlas_research.reality.record import load_record, replace_language, save_record

pytestmark = pytest.mark.git
_yaml = YAML(typ="safe")
COMPILE_RUN = "2026-09-20-r5-compile-01-typing-01"


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


def _open(repo, **kwargs):
    return open_r5(1, repo_root=repo, chat_run_id=COMPILE_RUN, now="2026-09-20T10:00:00Z",
                   **kwargs)


def test_open_r5_commits_the_questionnaire_and_opens_the_record(ontology_repo):
    record, outcome = _open(ontology_repo)
    assert isinstance(outcome, Landed)
    version = (ontology_repo / "ontology" / "VERSION").read_text().strip()
    assert record["questionnaire"] == f"questionnaire/spec-{version}.yaml"
    assert record["questionnaire"] in _git(["show", "--name-only", "--format=", "origin/main"],
                                           ontology_repo)
    assert validate_spec(load_spec(ontology_repo / record["questionnaire"])) == []
    assert record["scope"] == {"features": ["dynamic-typing", "static-typing",
                                            "type-inference"],
                               "dimensions": ["type-checking-discipline"]}
    assert load_record("01-typing", repo_root=ontology_repo) == record


def test_open_r5_refuses_a_cycle_that_has_not_finished_r4(store_repo):
    sign_off(new_cycle(1, "typing", repo_root=store_repo, languages=("python",)),
             by="dev", date="2026-09-20", repo_root=store_repo)
    with pytest.raises(R5NotReady, match="r4-done"):
        _open(store_repo)


def test_open_r5_never_silently_discards_classifier_runs(ontology_repo, r5_run):
    record, _ = _open(ontology_repo)
    save_record(replace_language(record, "python", cells=[], uncovered=[], run=r5_run),
                repo_root=ontology_repo)
    with pytest.raises(R5NotReady, match="--restart"):
        _open(ontology_repo)
    fresh, _ = _open(ontology_repo, restart=True)
    assert fresh["runs"]["classify"] == {}


def test_finalize_names_every_open_blocker_at_once(ontology_repo, r5_cell, r5_run):
    record, _ = _open(ontology_repo)
    save_record(replace_language(record, "python", cells=[r5_cell("python", "dynamic-typing")],
                                 uncovered=[], run=r5_run), repo_root=ontology_repo)
    with pytest.raises(R5Incomplete) as info:
        finalize_r5(1, repo_root=ontology_repo)
    message = str(info.value)
    assert "haskell: never classified" in message
    assert "python--dynamic-typing: never reached the gate" in message


def test_finalize_lands_the_findings_and_closes_the_cycle(ontology_repo, r5_cell, r5_run):
    record, _ = _open(ontology_repo)
    for language in ("python", "haskell"):
        record = replace_language(record, language,
                                  cells=[r5_cell(language, "type-inference", mappable=False)],
                                  uncovered=[], run={**r5_run, "run_id": f"{language}-run"})
    save_record(record, repo_root=ontology_repo)

    cycle, results = finalize_r5(1, repo_root=ontology_repo)
    assert all(isinstance(result, Landed) for result in results)
    assert cycle.status == "r5-done"
    assert cycle.artifacts["reality_check"] == "research/reality-checks/01-typing.yaml"
    assert load_cycle(1, repo_root=ontology_repo).status == "r5-done"
    landed = _yaml.load(_git(["show", "origin/main:research/reality-checks/01-typing.yaml"],
                             ontology_repo))
    assert landed["findings"]["unmappable"] == ["haskell--type-inference",
                                                "python--type-inference"]
    assert landed["summary"]["languages"] == 2
    assert not (ontology_repo / "languages" / "python").exists()      # D68: nothing minted
