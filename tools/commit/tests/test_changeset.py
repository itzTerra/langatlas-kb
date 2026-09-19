import subprocess

import pytest

from langatlas_commit.land import ContentionExhausted, Landed, land_changeset
from langatlas_commit.trailers import changeset_key


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture
def clone(tmp_path):
    """Origin + clone. `core.hooksPath` points at an empty directory so this machine's global
    pre-commit hook does not reject the commits `land_changeset` makes."""
    origin, clone, hooks = tmp_path / "origin.git", tmp_path / "clone", tmp_path / "no-hooks"
    hooks.mkdir()
    _git(["init", "-q", "--bare", "-b", "main", str(origin)], tmp_path)
    _git(["clone", "-q", str(origin), str(clone)], tmp_path)
    for key, value in (("user.email", "bot@example.com"), ("user.name", "bot"),
                       ("core.hooksPath", str(hooks)), ("commit.gpgsign", "false")):
        _git(["config", key, value], clone)
    (clone / "features").mkdir()
    (clone / "features" / "old.yaml").write_text("id: old\n")
    _git(["add", "-A"], clone)
    _git(["commit", "-q", "-m", "seed"], clone)
    _git(["push", "-q", "origin", "HEAD:main"], clone)
    return clone


def _ok(_root):
    return []


def test_the_key_is_order_free_and_distinguishes_deletion_from_empty():
    assert changeset_key({"a": "x", "b": None}) == changeset_key({"b": None, "a": "x"})
    assert changeset_key({"a": None}) != changeset_key({"a": ""})


def test_a_changeset_lands_as_one_commit_with_its_deletions(clone):
    changes = {"features/new.yaml": "id: new\n", "ontology/migrations/0001-x/manifest.yaml":
               "migration_id: 0001-x\n", "features/old.yaml": None}

    result = land_changeset(clone, changes, message="migrate 0001-x", chat_run_id="run-1",
                            validator=_ok)

    assert isinstance(result, Landed)
    files = _git(["show", "--name-status", "--format=", "origin/main"], clone).stdout
    assert "D\tfeatures/old.yaml" in files
    assert "A\tfeatures/new.yaml" in files
    assert "A\tontology/migrations/0001-x/manifest.yaml" in files
    assert _git(["log", "-1", "--format=%s", "origin/main"], clone).stdout.strip() == \
        "migrate 0001-x"


def test_relanding_the_same_changeset_is_a_no_op(clone):
    changes = {"features/new.yaml": "id: new\n"}
    first = land_changeset(clone, changes, message="m", chat_run_id="r", validator=_ok)
    second = land_changeset(clone, changes, message="m", chat_run_id="r", validator=_ok)

    assert second == first
    assert _git(["rev-list", "--count", "origin/main"], clone).stdout.strip() == "2"


def test_a_failing_validator_never_pushes(clone):
    result = land_changeset(clone, {"features/new.yaml": "id: new\n"}, message="m",
                            chat_run_id="r", validator=lambda _root: ["dangling edge"])

    assert isinstance(result, ContentionExhausted)
    assert "dangling edge" in result.last_conflict_summary
    assert _git(["rev-list", "--count", "origin/main"], clone).stdout.strip() == "1"


def test_empty_and_impossible_changesets_are_refused(clone):
    with pytest.raises(ValueError):
        land_changeset(clone, {}, message="m", chat_run_id="r", validator=_ok)
    with pytest.raises(ValueError):
        land_changeset(clone, {"features/missing.yaml": None}, message="m", chat_run_id="r",
                       validator=_ok)
