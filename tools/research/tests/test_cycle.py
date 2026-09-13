import pytest

from langatlas_research.cycle import (
    Cycle, advance, load_cycle, new_cycle, record_minted, require_sign_off, save_cycle, sign_off,
)
from langatlas_research.errors import (
    InvalidTransition, SignOffMissing, SignOffStale, UnknownTheme,
)
from langatlas_research.paths import REPO_ROOT, cycles_dir, ensure_layout, themes_path


@pytest.fixture
def repo(tmp_path):
    ensure_layout(tmp_path)
    (tmp_path / "research" / "schema").mkdir(parents=True, exist_ok=True)
    for name in ("theme-registry", "cycle"):
        (tmp_path / "research" / "schema" / f"{name}.schema.json").write_text(
            (REPO_ROOT / "research" / "schema" / f"{name}.schema.json").read_text())
    themes_path(tmp_path).write_text(themes_path(REPO_ROOT).read_text())
    return tmp_path


def test_new_cycle_writes_a_valid_file_named_by_number_and_theme(repo):
    cycle = new_cycle(1, "typing", repo_root=repo, languages=("python", "haskell"))

    assert cycle.slug == "01-typing"
    assert (cycles_dir(repo) / "01-typing.yaml").exists()
    assert cycle.status == "drafted"
    assert load_cycle(1, repo_root=repo) == cycle


def test_a_cycle_for_an_unknown_theme_is_refused(repo):
    with pytest.raises(UnknownTheme):
        new_cycle(1, "quantum-typing", repo_root=repo, languages=("python",))


def test_an_unsigned_cycle_fails_the_gate(repo):
    cycle = new_cycle(1, "typing", repo_root=repo, languages=("python",))

    with pytest.raises(SignOffMissing):
        require_sign_off(cycle, repo_root=repo)


def test_signing_off_passes_the_gate_and_advances_the_status(repo):
    cycle = new_cycle(1, "typing", repo_root=repo, languages=("python",))

    signed = sign_off(cycle, by="Michal Dolezel", date="2026-09-20", repo_root=repo)

    assert signed.status == "signed-off"
    require_sign_off(signed, repo_root=repo)


def test_editing_the_theme_after_sign_off_re_opens_the_gate(repo):
    cycle = sign_off(new_cycle(1, "typing", repo_root=repo, languages=("python",)),
                     by="Michal Dolezel", date="2026-09-20", repo_root=repo)
    text = themes_path(repo).read_text().replace(
        "Type systems, checking discipline", "Only nominal type systems")
    themes_path(repo).write_text(text)

    with pytest.raises(SignOffStale):
        require_sign_off(cycle, repo_root=repo)


def test_status_only_moves_forward(repo):
    cycle = advance(new_cycle(1, "typing", repo_root=repo, languages=("python",)), "signed-off")
    cycle = advance(cycle, "r3-done")

    with pytest.raises(InvalidTransition):
        advance(cycle, "signed-off")


def test_recording_minted_nodes_is_append_only_and_deduped(repo):
    cycle = new_cycle(1, "typing", repo_root=repo, languages=("python",))

    cycle = record_minted(cycle, ["pattern-matching", "type-inference"], repo_root=repo)
    cycle = record_minted(cycle, ["type-inference", "row-polymorphism"], repo_root=repo)

    assert cycle.nodes_minted == ("pattern-matching", "row-polymorphism", "type-inference")
    assert load_cycle(1, repo_root=repo).nodes_minted == cycle.nodes_minted
