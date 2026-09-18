from conftest import typing_store
from langatlas_questionnaire.cli import main


def test_compile_writes_the_versioned_spec_and_check_guards_it(mini_store, capsys):
    root = typing_store(mini_store).root
    assert main(["--repo-root", str(root), "compile"]) == 0
    assert (root / "questionnaire" / "spec-0.4.0.yaml").exists()
    assert main(["--repo-root", str(root), "compile", "--check"]) == 0

    mini_store.feature("gradual-typing", layer=3, dimension="type-checking-discipline")
    assert main(["--repo-root", str(root), "compile", "--check"]) == 1
    assert "differs" in capsys.readouterr().out


def test_compile_on_an_invalid_store_exits_nonzero(mini_store, capsys):
    mini_store.feature("static-typing", layer=3, dimension="undeclared")
    assert main(["--repo-root", str(mini_store.root), "compile"]) == 1
    assert "cannot be compiled" in capsys.readouterr().err


def test_validate_flags_a_broken_committed_spec(mini_store):
    root = typing_store(mini_store).root
    assert main(["--repo-root", str(root), "compile"]) == 0
    assert main(["--repo-root", str(root), "validate"]) == 0
    path = root / "questionnaire" / "spec-0.4.0.yaml"
    path.write_text(path.read_text().replace("compiler_version", "compiler"))
    assert main(["--repo-root", str(root), "validate"]) == 1


def test_diff_prints_the_requeue_set(mini_store, capsys):
    store = typing_store(mini_store)
    assert main(["--repo-root", str(store.root), "compile"]) == 0
    old = store.root / "questionnaire" / "spec-0.4.0.yaml"
    store.version("0.5.0")
    store.feature("gradual-typing", layer=3, dimension="type-checking-discipline")
    assert main(["--repo-root", str(store.root), "compile"]) == 0
    new = store.root / "questionnaire" / "spec-0.5.0.yaml"
    capsys.readouterr()
    assert main(["diff", str(old), str(new)]) == 0
    out = capsys.readouterr().out
    assert "requeue (added + changed): 1" in out
    assert "fi.<lang>.gradual-typing" in out
