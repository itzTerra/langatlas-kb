from langatlas_validate.gitrefs import (
    changed_paths, commits_since, extract_tree, list_files, resolve_ref, show,
)


def test_resolve_ref_treats_empty_zero_and_unknown_refs_as_absent(git_repo):
    first = git_repo.commit({"a.yaml": "a: 1\n"})

    assert resolve_ref(git_repo.root, "HEAD") == first
    assert resolve_ref(git_repo.root, None) is None
    assert resolve_ref(git_repo.root, "") is None
    assert resolve_ref(git_repo.root, "0" * 40) is None
    assert resolve_ref(git_repo.root, "no-such-branch") is None


def test_show_returns_none_for_a_path_the_ref_lacks(git_repo):
    first = git_repo.commit({"a.yaml": "a: 1\n"})

    assert show(git_repo.root, first, "a.yaml") == "a: 1\n"
    assert show(git_repo.root, first, "b.yaml") is None


def test_commits_since_is_oldest_first_and_none_means_all(git_repo):
    first = git_repo.commit({"a.yaml": "a: 1\n"})
    second = git_repo.commit({"a.yaml": "a: 2\n"})
    third = git_repo.commit({"b.yaml": "b: 1\n"})

    assert commits_since(git_repo.root, first) == [second, third]
    assert commits_since(git_repo.root, None) == [first, second, third]


def test_changed_paths_reports_status_letters(git_repo):
    git_repo.commit({"a.yaml": "a: 1\n", "b.yaml": "b: 1\n"})
    commit = git_repo.commit({"a.yaml": "a: 2\n", "b.yaml": None, "c.yaml": "c: 1\n"})

    assert sorted(changed_paths(git_repo.root, commit)) == [
        ("A", "c.yaml"), ("D", "b.yaml"), ("M", "a.yaml")]


def test_list_files_and_extract_tree_read_a_past_commit(git_repo, tmp_path):
    first = git_repo.commit({"dir/a.yaml": "a: 1\n", "dir/b.md": "x\n"})
    git_repo.commit({"dir/a.yaml": "a: 2\n"})

    assert list_files(git_repo.root, first, "dir") == ["dir/a.yaml", "dir/b.md"]
    extract_tree(git_repo.root, first, tmp_path / "old")
    assert (tmp_path / "old" / "dir" / "a.yaml").read_text() == "a: 1\n"
