# tools/research/tests/test_exit_3a.py
"""Stage 3A's exit condition, end to end: a signed-off cycle mints a dimension, a concept,
a feature and an edge; every record validates, lands, and is bookkept on the cycle; and the
0.x ceremony turns the additive change into a MINOR bump."""
import subprocess
from functools import partial

import pytest
from langatlas_commit.land import Landed

from langatlas_research.cycle import load_cycle, new_cycle, sign_off
from langatlas_research.drafts import ConceptDraft, EdgeDraft, Evidence, FeatureDraft, Proposer
from langatlas_research.land import land_drafts, store_validator
from langatlas_research.taxonomy import mint_dimension
from langatlas_validate.version import bump, classify_change, read_version, snapshot_at, store_snapshot

pytestmark = pytest.mark.git

PROPOSER = Proposer(agent="ontologist", model="claude-opus-5", prompt_version="v1")
EVIDENCE = (Evidence(source="vanroy-haridi-2003", locator="p. 142"),)


def test_a_signed_off_cycle_mints_a_theme_subtree_and_bumps_the_version(store_repo):
    baseline = subprocess.run(["git", "rev-parse", "HEAD"], cwd=store_repo,
                              capture_output=True, text=True, check=True).stdout.strip()
    cycle = sign_off(new_cycle(1, "typing", repo_root=store_repo, languages=("python", "haskell")),
                     by="Michal Dolezel", date="2026-09-20", repo_root=store_repo)

    items = [
        partial(mint_dimension, "typing-discipline", label="Typing discipline",
                values=("static", "dynamic"), repo_root=store_repo),
        ConceptDraft(id="type", name="Type", summary="A classification of values.",
                     evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0001"),
        FeatureDraft(id="static-typing", name="Static typing", layer=3,
                     dimension="typing-discipline", realizes=("type",),
                     summary="Type checking performed before execution.",
                     evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0001"),
        FeatureDraft(id="type-inference", name="Type inference", layer=2,
                     summary="Types reconstructed without annotation.",
                     evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0001"),
        EdgeDraft(type="requires", frm="type-inference", to="static-typing",
                  statement="Inference presupposes a static discipline to infer within.",
                  evidence=EVIDENCE, proposer=PROPOSER, chat_run_id="r4-typing-0001"),
    ]

    results = land_drafts(items, repo_root=store_repo, chat_run_id="r4-typing-0001",
                          cycle=cycle)

    assert all(isinstance(outcome, Landed) for _, outcome in results)
    assert store_validator(store_repo) == []
    assert set(load_cycle(1, repo_root=store_repo).nodes_minted) == {
        "typing-discipline", "type", "static-typing", "type-inference",
        "edge.requires.type-inference.static-typing"}

    change = classify_change(snapshot_at(store_repo, baseline), store_snapshot(store_repo))
    assert change == "additive"
    assert bump(read_version(store_repo), change) == (0, 3, 0)
