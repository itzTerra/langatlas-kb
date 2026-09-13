from functools import partial

import pytest
from langatlas_commit.land import Landed

from langatlas_research.cycle import load_cycle, new_cycle
from langatlas_research.drafts import Evidence, FeatureDraft, Proposer
from langatlas_research.land import land_drafts, store_validator
from langatlas_research.taxonomy import mint_dimension

pytestmark = pytest.mark.git

PROPOSER = Proposer(agent="ontologist", model="claude-opus-5", prompt_version="v1")
EVIDENCE = (Evidence(source="vanroy-haridi-2003", locator="p. 142"),)


def _draft(node_id="pattern-matching", **overrides):
    base = dict(id=node_id, name="Pattern matching", layer=2,
                summary="Selection of a branch by the structural shape of a value.",
                evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0001")
    return FeatureDraft(**(base | overrides))


def test_the_seed_store_validates(store_repo):
    assert store_validator(store_repo) == []


def test_landing_a_feature_commits_it_and_records_it_on_the_cycle(store_repo):
    cycle = new_cycle(1, "typing", repo_root=store_repo, languages=("python",))

    results = land_drafts([_draft()], repo_root=store_repo, chat_run_id="r4-typing-0001",
                          cycle=cycle)

    minted, outcome = results[0]
    assert isinstance(outcome, Landed)
    assert (store_repo / "features" / "pattern-matching.yaml").exists()
    assert load_cycle(1, repo_root=store_repo).nodes_minted == ("pattern-matching",)


def test_landing_is_idempotent(store_repo):
    land_drafts([_draft()], repo_root=store_repo, chat_run_id="r")
    first = (store_repo / "features" / "pattern-matching.yaml").read_text()

    land_drafts([_draft()], repo_root=store_repo, chat_run_id="r")

    assert (store_repo / "features" / "pattern-matching.yaml").read_text() == first


def test_a_shared_file_mint_re_renders_against_whatever_is_on_disk(store_repo):
    land_drafts([partial(mint_dimension, "typing-discipline", label="Typing discipline",
                         values=("static", "dynamic"), repo_root=store_repo)],
                repo_root=store_repo, chat_run_id="r")

    land_drafts([partial(mint_dimension, "memory-reclamation", label="Memory reclamation",
                         values=("manual", "traced-gc"), repo_root=store_repo)],
                repo_root=store_repo, chat_run_id="r")

    text = (store_repo / "ontology" / "taxonomy" / "dimensions.yaml").read_text()
    assert "typing-discipline" in text and "memory-reclamation" in text


def test_an_invalid_draft_never_reaches_git(store_repo):
    from langatlas_research.errors import UnsourcedNode

    with pytest.raises(UnsourcedNode):
        land_drafts([_draft(evidence=())], repo_root=store_repo, chat_run_id="r")

    assert not (store_repo / "features" / "pattern-matching.yaml").exists()


def test_losing_every_race_raises_instead_of_returning_a_silent_none_outcome(
        store_repo, monkeypatch):
    """Finding 6's regression test: if a shared-file mint finds the file stale on every
    attempt, `land_record` never even runs — the loop must not exit with a silent
    `(minted, None)` result."""
    import langatlas_research.land as land

    monkeypatch.setattr(land, "_is_stale", lambda minted, repo_root: True)

    with pytest.raises(land.RaceExhausted):
        land_drafts([partial(mint_dimension, "typing-discipline",
                             label="Typing discipline", values=("static",),
                             repo_root=store_repo)],
                    repo_root=store_repo, chat_run_id="r", attempts=3)
