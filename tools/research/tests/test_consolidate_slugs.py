import subprocess

import pytest

from langatlas_research.cli import main
from langatlas_research.consolidate.guard import check_commit
from langatlas_research.consolidate.record import build_record, save_record
from langatlas_research.consolidate.slugs import rename_slug, slug_candidates, slugify
from langatlas_research.cycle import new_cycle, record_minted, sign_off
from langatlas_research.errors import SlugRefused
from langatlas_validate.normalize import normalize_record
from langatlas_validate.redirects import parse_redirects


def _feature(repo, node_id, *, name, slug=None):
    path = repo / "features" / f"{node_id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalize_record(
        f"id: {node_id}\nslug: {slug or node_id}\nname: {name}\nlayer: 2\n"
        "summary:\n  text: x.\n  sources:\n    - source: s\n      locator: p. 1\n"
        "provenance:\n  claim_origin: source-derived\n", "feature"))


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.mark.parametrize("name, slug", [
    ("Garbage collection (tracing)", "garbage-collection-tracing"),
    ("2-phase locking", "phase-locking"),
    ("Café à la carte", "cafe-a-la-carte"),
])
def test_slugify_obeys_the_slug_grammar(name, slug):
    assert slugify(name) == slug


def test_candidates_flag_drift_from_the_name_and_language_tokens(research_repo):
    _feature(research_repo, "rust-ownership", name="Ownership")
    _feature(research_repo, "pattern-matching", name="Pattern matching")

    assert slug_candidates(research_repo) == [
        {"node": "rust-ownership", "slug": "rust-ownership", "suggested": "ownership",
         "signals": ["slug-differs-from-name", "language-specific"]}]


def test_a_rename_rewrites_the_slug_and_redirects_the_old_one(research_repo):
    _feature(research_repo, "rust-ownership", name="Ownership")

    changes = rename_slug(research_repo, "rust-ownership", "ownership")

    assert "slug: ownership" in changes["features/rust-ownership.yaml"]
    assert "id: rust-ownership" in changes["features/rust-ownership.yaml"]
    assert parse_redirects(changes["ontology/redirects.yaml"]) == {
        "rust-ownership": "rust-ownership"}


def test_renaming_back_retires_the_redirect(research_repo):
    _feature(research_repo, "rust-ownership", name="Ownership", slug="ownership")
    (research_repo / "ontology" / "redirects.yaml").write_text(
        "redirects:\n  rust-ownership: rust-ownership\n")

    changes = rename_slug(research_repo, "rust-ownership", "rust-ownership")

    assert parse_redirects(changes["ontology/redirects.yaml"]) == {
        "ownership": "rust-ownership"}


@pytest.mark.parametrize("new_slug, message", [
    ("pattern-matching", "already the slug"),
    ("Bad Slug", "not a valid slug"),
    ("taken-url", "already redirects"),
])
def test_a_rename_that_would_break_a_url_is_refused(research_repo, new_slug, message):
    _feature(research_repo, "rust-ownership", name="Ownership")
    _feature(research_repo, "pattern-matching", name="Pattern matching")
    (research_repo / "ontology" / "redirects.yaml").write_text(
        "redirects:\n  taken-url: pattern-matching\n")

    with pytest.raises(SlugRefused, match=message):
        rename_slug(research_repo, "rust-ownership", new_slug)


def test_malformed_input_is_a_typed_refusal(research_repo):
    _feature(research_repo, "rust-ownership", name="Ownership")
    with pytest.raises(SlugRefused, match="not a committed"):
        rename_slug(research_repo, "nope", "ownership")
    with pytest.raises(SlugRefused, match="already has slug"):
        rename_slug(research_repo, "rust-ownership", "rust-ownership")

    (research_repo / "ontology" / "redirects.yaml").write_text("redirects: [unclosed\n")
    with pytest.raises(SlugRefused, match="redirects.yaml"):
        rename_slug(research_repo, "rust-ownership", "ownership")
    (research_repo / "ontology" / "redirects.yaml").write_text("- a\n- b\n")
    with pytest.raises(SlugRefused, match="redirects.yaml"):
        rename_slug(research_repo, "rust-ownership", "ownership")

    (research_repo / "features" / "broken.yaml").write_text("id: [unclosed\n")
    with pytest.raises(SlugRefused, match="broken.yaml"):
        rename_slug(research_repo, "rust-ownership", "ownership")
    with pytest.raises(SlugRefused, match="broken.yaml"):
        slug_candidates(research_repo)
    (research_repo / "features" / "broken.yaml").write_text("- just\n- a list\n")
    with pytest.raises(SlugRefused, match="broken.yaml"):
        slug_candidates(research_repo)


def test_cli_reports_malformed_input_without_a_traceback(research_repo, signed_cycle, capsys):
    _feature(research_repo, "rust-ownership", name="Ownership")
    root = ["--repo-root", str(research_repo), "consolidate"]

    assert main([*root, "rename-slug", "1", "nope", "ownership"]) == 1
    assert "not a committed" in capsys.readouterr().err
    assert main([*root, "rename-slug", "1", "rust-ownership", "Bad Slug"]) == 1
    assert "not a valid slug" in capsys.readouterr().err
    (research_repo / "features" / "broken.yaml").write_text("id: [unclosed\n")
    assert main([*root, "slugs", "1"]) == 1
    assert "broken.yaml" in capsys.readouterr().err


def test_slugs_lists_candidates(research_repo, signed_cycle, capsys):
    _feature(research_repo, "rust-ownership", name="Ownership")

    assert main(["--repo-root", str(research_repo), "consolidate", "slugs", "1"]) == 0

    out = capsys.readouterr().out
    assert "rust-ownership" in out and "-> ownership" in out and "1 candidate(s)" in out


def test_rename_requires_sign_off(research_repo, capsys):
    _feature(research_repo, "rust-ownership", name="Ownership")
    new_cycle(1, "typing", repo_root=research_repo, languages=("python",))

    assert main(["--repo-root", str(research_repo), "consolidate", "rename-slug", "1",
                 "rust-ownership", "ownership"]) == 1
    assert "sign-off" in capsys.readouterr().err
    assert (research_repo / "features" / "rust-ownership.yaml").read_text().count(
        "slug: rust-ownership") == 1


def _seed(repo, *, settle):
    _feature(repo, "rust-ownership", name="Ownership")
    cycle = sign_off(new_cycle(1, "typing", repo_root=repo, languages=("python",)),
                     by="Dev", date="2026-10-01", repo_root=repo)
    cycle = record_minted(cycle, ["rust-ownership"], repo_root=repo)
    save_record(build_record(cycle=cycle, opened_at="t"), repo_root=repo)
    if settle:
        path = repo / "research" / "cycles" / f"{cycle.slug}.yaml"
        path.write_text(path.read_text().replace(f"status: {cycle.status}", "status: settled"))
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "node"], repo)
    _git(["push", "-q", "origin", "HEAD:main"], repo)


def _rename(repo):
    return main(["--repo-root", str(repo), "consolidate", "rename-slug", "1",
                 "rust-ownership", "ownership"])


@pytest.mark.git
def test_rename_slug_lands_record_and_redirect_together(store_repo):
    _seed(store_repo, settle=False)

    assert _rename(store_repo) == 0

    _git(["fetch", "-q", "origin"], store_repo)
    files = _git(["show", "--name-only", "--format=", "origin/main"], store_repo).stdout
    assert set(files.split()) == {"features/rust-ownership.yaml", "ontology/redirects.yaml"}
    assert _git(["rev-list", "--count", "origin/main"], store_repo).stdout.strip() != "0"
    record = (store_repo / "features" / "rust-ownership.yaml").read_text()
    assert "slug: ownership" in record and "id: rust-ownership" in record
    assert parse_redirects((store_repo / "ontology" / "redirects.yaml").read_text()) == {
        "rust-ownership": "rust-ownership"}


@pytest.mark.git
def test_a_rename_in_a_settled_theme_passes_the_guard(store_repo):
    _seed(store_repo, settle=True)

    assert _rename(store_repo) == 0

    _git(["fetch", "-q", "origin"], store_repo)
    assert check_commit(store_repo, "origin/main") == []
