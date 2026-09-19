import pytest
from ruamel.yaml import YAML

from langatlas_research.cli import main
from langatlas_research.consolidate.dedup import (
    candidates, dedup_key, drop_alias, make_ruling, open_candidates,
)
from langatlas_research.consolidate.record import add_ruling, build_record, load_record, save_record
from langatlas_research.cycle import record_minted
from langatlas_research.errors import DedupRefused
from langatlas_validate.normalize import normalize_record

_safe = YAML(typ="safe")


def _feature(repo, node_id, *, name, aliases=()):
    body = f"id: {node_id}\nslug: {node_id}\nname: {name}\nlayer: 2\n"
    if aliases:
        body += "aliases:\n" + "".join(f"  - {alias}\n" for alias in aliases)
    body += ("summary:\n  text: x.\n  sources:\n    - source: s\n      locator: p. 1\n"
             "provenance:\n  claim_origin: source-derived\n")
    path = repo / "features" / f"{node_id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalize_record(body, "feature"))


@pytest.fixture
def audited(research_repo, signed_cycle):
    _feature(research_repo, "static-typing", name="Static typing",
             aliases=("static type checking",))
    _feature(research_repo, "static-type-checking", name="Static type checking")
    _feature(research_repo, "tracing-garbage-collection", name="Tracing GC")
    _feature(research_repo, "garbage-collection-tracing", name="Tracing GC")
    _feature(research_repo, "type-inference", name="Type inference")
    cycle = record_minted(signed_cycle, ["static-typing", "tracing-garbage-collection",
                                         "type-inference", "edge.requires.a.b"],
                          repo_root=research_repo)
    record = build_record(cycle=cycle, opened_at="t")
    save_record(record, repo_root=research_repo)
    return cycle, record


def test_the_signals_link_names_aliases_and_ids(research_repo, audited):
    cycle, _record = audited

    found = {tuple(c["nodes"]): c["signals"] for c in candidates(research_repo, cycle=cycle)}

    assert found == {
        ("static-type-checking", "static-typing"): ["name-is-alias"],
        ("garbage-collection-tracing", "tracing-garbage-collection"):
            ["same-name", "id-token-overlap"],
    }
    assert dedup_key("a", "b") == dedup_key("b", "a")


def test_a_ruled_pair_is_never_raised_again(research_repo, audited):
    cycle, record = audited
    candidate = next(c for c in candidates(research_repo, cycle=cycle)
                     if "static-typing" in c["nodes"])
    save_record(add_ruling(record, make_ruling(candidate, disposition="distinct",
                                               reason="different literatures")),
                repo_root=research_repo)

    remaining = open_candidates(research_repo, cycle=cycle,
                                record=build_record(cycle=cycle, opened_at="t"))

    assert [c["nodes"] for c in remaining] == [["garbage-collection-tracing",
                                                "tracing-garbage-collection"]]


def test_rulings_carry_what_their_disposition_needs(research_repo, audited):
    cycle, _record = audited
    candidate = candidates(research_repo, cycle=cycle)[0]

    with pytest.raises(DedupRefused, match="reason"):
        make_ruling(candidate, disposition="distinct", reason=" ")
    with pytest.raises(DedupRefused, match="not one of"):
        make_ruling(candidate, disposition="drop-alias", reason="r", node="elsewhere", alias="x")
    ruling = make_ruling(candidate, disposition="merge", reason="r", node=candidate["nodes"][0],
                         migration="0001-merge-x")
    assert (ruling["node"], ruling["migration"]) == (candidate["nodes"][0], "0001-merge-x")


def test_drop_alias_rewrites_only_the_alias_list(research_repo, audited):
    rel, text = drop_alias(research_repo, "static-typing", "Static Type Checking")

    assert rel == "features/static-typing.yaml"
    assert "aliases" not in _safe.load(text)
    with pytest.raises(DedupRefused, match="no alias"):
        drop_alias(research_repo, "type-inference", "anything")


def test_rule_distinct_from_the_cli(research_repo, audited, capsys):
    cycle, _record = audited
    key = next(c["key"] for c in candidates(research_repo, cycle=cycle)
               if "static-typing" in c["nodes"])
    root = ["--repo-root", str(research_repo), "consolidate"]

    assert main([*root, "dedup", "1"]) == 0
    assert "2 open candidate(s)" in capsys.readouterr().out
    assert main([*root, "rule", "1", key, "--distinct", "--reason", "different axes"]) == 0
    assert load_record(cycle.slug, repo_root=research_repo)["dedup"][0]["disposition"] == \
        "distinct"


def test_rule_merge_drafts_a_manifest(research_repo, audited):
    cycle, _record = audited
    (research_repo / "ontology" / "VERSION").write_text("0.4.0\n")
    key = next(c["key"] for c in candidates(research_repo, cycle=cycle)
               if "static-typing" in c["nodes"])

    assert main(["--repo-root", str(research_repo), "consolidate", "rule", "1", key,
                 "--merge-into", "static-typing", "--reason", "same thing"]) == 0

    [ruling] = load_record(cycle.slug, repo_root=research_repo)["dedup"]
    assert ruling["migration"] == "0001-merge-static-type-checking"
    assert (research_repo / "ontology" / "migrations" / ruling["migration"]
            / "manifest.yaml").exists()


def test_malformed_input_is_a_typed_refusal(research_repo, audited):
    (research_repo / "features" / "type-inference.yaml").write_text("id: [unclosed\n")

    with pytest.raises(DedupRefused, match="not valid YAML"):
        drop_alias(research_repo, "type-inference", "x")
    with pytest.raises(DedupRefused, match="not a committed feature"):
        drop_alias(research_repo, "nope", "x")


def test_rule_drop_alias_needs_a_node_in_the_pair(research_repo, audited, capsys):
    cycle, _record = audited
    key = next(c["key"] for c in candidates(research_repo, cycle=cycle)
               if "static-typing" in c["nodes"])
    root = ["--repo-root", str(research_repo), "consolidate", "rule", "1", key]

    assert main([*root, "--drop-alias", "x", "--reason", "r"]) == 1
    assert main([*root, "--drop-alias", "x", "--node", "type-inference", "--reason", "r"]) == 1
    assert "not one of" in capsys.readouterr().err
    assert main(["--repo-root", str(research_repo), "consolidate", "rule", "1", "d-nope",
                 "--distinct", "--reason", "r"]) == 1


# ---- the CLI's --drop-alias path against a real repo with an origin -------------------------

import subprocess

from langatlas_research.consolidate.guard import check_commit
from langatlas_research.cycle import new_cycle, sign_off


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


_TYPING = ("id: static-typing\nslug: static-typing\nname: Static typing\nlayer: 2\n"
           "aliases:\n  - static type checking\n  - compile-time typing\n"
           "summary:\n  text: x.\n  sources:\n    - source: s\n      locator: p. 1\n"
           "provenance:\n  claim_origin: source-derived\n")


def _commit_all(repo, message):
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", message], repo)
    _git(["push", "-q", "origin", "HEAD:main"], repo)


@pytest.fixture
def landed_repo(store_repo):
    """static-typing (two aliases) and static-type-checking, minted by a signed cycle 1."""
    _feature(store_repo, "static-type-checking", name="Static type checking")
    (store_repo / "features" / "static-typing.yaml").write_text(
        normalize_record(_TYPING, "feature"))
    cycle = sign_off(new_cycle(1, "typing", repo_root=store_repo, languages=("python",)),
                     by="Michal Dolezel", date="2026-09-20", repo_root=store_repo)
    cycle = record_minted(cycle, ["static-typing"], repo_root=store_repo)
    save_record(build_record(cycle=cycle, opened_at="t"), repo_root=store_repo)
    _commit_all(store_repo, "seed nodes")
    return store_repo, cycle


def _drop(repo):
    key = next(c["key"] for c in candidates(repo, cycle=_cycle_of(repo))
               if "static-typing" in c["nodes"])
    return main(["--repo-root", str(repo), "consolidate", "rule", "1", key, "--drop-alias",
                 "compile-time typing", "--node", "static-typing", "--reason", "ambiguous"])


def _cycle_of(repo):
    from langatlas_research.cycle import load_cycle
    return load_cycle(1, repo_root=repo)


def _assert_landed_alone(repo):
    files = _git(["show", "--name-status", "--format=", "origin/main"], repo).stdout.split()
    assert files == ["M", "features/static-typing.yaml"]


@pytest.mark.git
def test_drop_alias_lands_one_record_and_records_the_ruling(landed_repo, capsys):
    repo, cycle = landed_repo
    before = (repo / "features" / "static-typing.yaml").read_text()

    assert _drop(repo) == 0

    _git(["fetch", "-q", "origin"], repo)
    _assert_landed_alone(repo)
    [ruling] = load_record(cycle.slug, repo_root=repo)["dedup"]
    assert (ruling["disposition"], ruling["node"], ruling["alias"]) == \
        ("drop-alias", "static-typing", "compile-time typing")
    # formatting: the only difference is the dropped alias line
    after = (repo / "features" / "static-typing.yaml").read_text()
    assert [line for line in before.splitlines() if line not in after.splitlines()] == \
        ["  - compile-time typing"]
    assert [line for line in after.splitlines() if line not in before.splitlines()] == []
    assert before.replace("  - compile-time typing\n", "") == after


@pytest.mark.git
def test_drop_alias_in_a_settled_theme_lands_and_passes_the_guard(landed_repo):
    repo, cycle = landed_repo
    path = repo / "research" / "cycles" / f"{cycle.slug}.yaml"
    text = path.read_text().replace(f"status: {cycle.status}", "status: settled")
    assert "status: settled" in text
    path.write_text(text)
    _commit_all(repo, "settle")

    assert _drop(repo) == 0

    _git(["fetch", "-q", "origin"], repo)
    _assert_landed_alone(repo)
    assert check_commit(repo, "origin/main") == []


def test_a_non_string_alias_is_a_typed_refusal(research_repo):
    (research_repo / "features").mkdir()
    (research_repo / "features" / "odd.yaml").write_text(
        "id: odd\nname: Odd\naliases:\n  - 3\n  - x\n")

    with pytest.raises(DedupRefused, match="non-string alias"):
        drop_alias(research_repo, "odd", "x")
