"""R5's gate: 3C's `verify_entry` over rendered instance records."""
from pathlib import Path

import pytest
from ruamel.yaml import YAML

import langatlas_research.draft.gate as draft_gate
from langatlas_ingest.verify.pipeline import VerifyDeps
from langatlas_ingest.verify.sources import SourceFacts
from langatlas_ingest.verify.verdicts import PairVerdict
from langatlas_research.config import ResearchConfig
from langatlas_research.drafts import Evidence, FeatureDraft, Proposer
from langatlas_research.mint import render_draft
from langatlas_research.paths import research_config_path
from langatlas_research.reality.cells import cell_draft
from langatlas_research.reality.gate import verify_cells
from langatlas_research.reality.record import find_cell, replace_language

_yaml = YAML(typ="safe")
REF = {"source": "python-langref-3", "locator": "§3.1", "chunk_id": "python-langref-3#c00012"}
CHAR = {"key": "c-runtime-checks", "text": "Type errors surface at run time.",
        "sources": [REF]}
SOURCE_FACTS = {
    "python-langref-3": SourceFacts("python-langref-3", "A", "reference-implementation-docs",
                                    (), {}, language_version="3.14"),
    "scott-plp": SourceFacts("scott-plp", "C", "third-party-reference", (), {}),
}


def _feature(fid, name, aliases=()):
    minted = render_draft(FeatureDraft(
        id=fid, name=name, summary=f"{name} is a typing discipline.",
        evidence=(Evidence(source="pierce-tapl-2002", locator="§1.1"),),
        proposer=Proposer(agent="r4-ontologist", model="claude", prompt_version="v"),
        chat_run_id="r4", layer=3, dimension="type-checking-discipline",
        aliases=tuple(aliases)))
    return fid, (Path(minted.path), "feature", minted.text, _yaml.load(minted.text))


FEATURES = dict([_feature("dynamic-typing", "Dynamic typing", ("dynamic type checking",)),
                 _feature("static-typing", "Static typing")])


def _verifier(verdicts, seen):
    """A stand-in for `verify_pair`. The verdict is chosen by claim kind; a pair for a claim
    carrying a `since` gets a `since_status` as the real entailment stage reports one —
    `since-supported` unless the test says otherwise."""
    def _verify(ctx, conn, *, claim, citation, **kwargs):
        seen.append(claim)
        kind = claim.claim.split("(")[0]
        verdict = verdicts.get(kind, verdicts.get("default", "supported"))
        since_status = None
        if claim.since and verdict in ("supported", "partial"):
            since_status = verdicts.get("since_status", "since-supported")
        return PairVerdict(fact_id=claim.fact_id, source_id=citation.source_id,
                           locator=citation.locator, verdict=verdict,
                           since_status=since_status, date="2026-09-20")
    return _verify


@pytest.fixture
def config(research_repo):
    return ResearchConfig.load(research_config_path(research_repo))


@pytest.fixture
def gate(fake_ctx, signed_cycle, research_repo, config):
    def _run(record, verdicts, seen=None):
        return verify_cells(fake_ctx, None, record, cycle=signed_cycle, repo_root=research_repo,
                            config=config, deps=VerifyDeps(source_facts=SOURCE_FACTS),
                            verifier=_verifier(verdicts, [] if seen is None else seen),
                            features=FEATURES)
    return _run


@pytest.fixture
def with_cells(r5_record, r5_run):
    def _with(*cells):
        return replace_language(r5_record, "python", cells=list(cells), uncovered=[],
                                run=r5_run)
    return _with


def test_a_supported_cell_is_admitted_and_every_anchor_is_recorded(gate, with_cells, r5_cell,
                                                                   fake_ctx):
    updated, results = gate(with_cells(r5_cell("python", "dynamic-typing",
                                               characteristics=[CHAR])),
                            {"default": "supported"})
    cell = find_cell(updated, "python--dynamic-typing")
    assert cell["status"] == "admitted"
    assert cell["verification"]["exists"]["admissible"] is True
    assert [f["anchor"] for f in cell["verification"]["facts"]] == [
        "fi.python.dynamic-typing#exists",
        "fi.python.dynamic-typing#characteristics[c-runtime-checks]"]
    assert updated["runs"]["verify"] == fake_ctx.run_id
    assert [result.pairs for result in results] == [2]


def test_since_is_verified_inside_exists_and_never_on_its_own(gate, with_cells, r5_cell):
    seen = []
    gate(with_cells(r5_cell("python", "dynamic-typing")), {"default": "supported"}, seen)
    assert [claim.claim for claim in seen] == [
        "instance-exists(fi.python.dynamic-typing, status=present)"]
    assert seen[0].since == "3.14"


def test_since_is_decided_as_a_load_bearing_field(monkeypatch, gate, with_cells, r5_cell):
    calls = []
    real = draft_gate.decide_fact

    def _spy(fact_id, pairs, source_facts, **kwargs):
        calls.append(kwargs)
        return real(fact_id, pairs, source_facts, **kwargs)

    monkeypatch.setattr(draft_gate, "decide_fact", _spy)
    gate(with_cells(r5_cell("python", "dynamic-typing")), {"default": "supported"})
    assert [(c["has_since"], c["since"], c["absent"]) for c in calls] == [(True, "3.14", False)]


def test_an_as_of_since_equal_to_the_documented_version_is_admitted(gate, with_cells, r5_cell):
    updated, _ = gate(with_cells(r5_cell("python", "dynamic-typing")),
                      {"default": "supported", "since_status": "as-of-supported"})
    cell = find_cell(updated, "python--dynamic-typing")
    assert cell["status"] == "admitted"
    assert cell["verification"]["exists"]["verdict"] == "partially-verified"


def test_an_as_of_since_earlier_than_the_documented_version_is_refused(gate, with_cells,
                                                                       r5_cell):
    """D66: back-dating only moves earlier, so a too-early as-of since could never be fixed."""
    updated, _ = gate(with_cells(r5_cell("python", "dynamic-typing", since="3.0")),
                      {"default": "supported", "since_status": "as-of-supported"})
    cell = find_cell(updated, "python--dynamic-typing")
    assert cell["status"] == "refused"
    assert "D66" in cell["verification"]["detail"]


def test_an_unsupported_existence_claim_refuses_the_cell(gate, with_cells, r5_cell):
    updated, _ = gate(with_cells(r5_cell("python", "dynamic-typing")),
                      {"instance-exists": "unsupported"})
    assert find_cell(updated, "python--dynamic-typing")["status"] == "refused"


def test_a_refused_characteristic_does_not_refuse_its_cell(gate, with_cells, r5_cell):
    updated, _ = gate(with_cells(r5_cell("python", "dynamic-typing", characteristics=[CHAR])),
                      {"default": "supported", "characteristic": "unsupported"})
    cell = find_cell(updated, "python--dynamic-typing")
    assert cell["status"] == "admitted"
    assert [f["admissible"] for f in cell["verification"]["facts"]] == [True, False]


def test_a_tier_c_citation_alone_never_admits(gate, with_cells, r5_cell):
    record = with_cells(r5_cell("python", "dynamic-typing",
                                sources=[{"source": "scott-plp", "locator": "§7.2",
                                          "chunk_id": "scott-plp#c00310"}]))
    updated, _ = gate(record, {"default": "supported"})
    assert find_cell(updated, "python--dynamic-typing")["status"] == "refused"


def test_an_absent_cell_reaches_the_verifier_with_its_scope_and_the_features_names(
        gate, with_cells, r5_cell):
    record = with_cells(r5_cell("python", "dynamic-typing", answer="absent",
                                absence_scope="The reference enumerates every checking phase."))
    seen = []
    gate(record, {"default": "supported"}, seen)
    (claim,) = seen
    assert claim.status == "absent" and claim.since is None
    assert claim.absence_scope == "The reference enumerates every checking phase."
    assert claim.feature_aliases == ("Dynamic typing", "dynamic type checking")


def test_a_pipeline_verdict_files_a_shakedown_entry(gate, with_cells, r5_cell):
    updated, _ = gate(with_cells(r5_cell("python", "dynamic-typing")),
                      {"instance-exists": "locator-not-found"})
    assert [(e["component"], e["detail"]) for e in updated["shakedown"]] == [
        ("verifier", "fi.python.dynamic-typing#exists: locator-not-found")]


def test_a_cell_that_cannot_render_is_refused_and_logged(gate, with_cells, r5_cell):
    updated, results = gate(with_cells(r5_cell("python", "dynamic-typing", since=None)),
                            {"default": "supported"})
    cell = find_cell(updated, "python--dynamic-typing")
    assert cell["status"] == "refused"
    assert cell["verification"]["exists"]["verdict"] == "unrendered"
    assert [e["component"] for e in updated["shakedown"]] == ["questionnaire"]
    assert results == []


def test_only_proposed_cells_are_gated(gate, with_cells, r5_cell):
    record = with_cells(r5_cell("python", "dynamic-typing", status="admitted"),
                        r5_cell("python", "static-typing", mappable=False))
    updated, results = gate(record, {"default": "supported"})
    assert results == []
    assert updated["cells"] == record["cells"]


def test_cell_draft_carries_the_classifier_run_as_provenance(with_cells, r5_cell, r5_run):
    record = with_cells(r5_cell("python", "dynamic-typing"))
    draft = cell_draft(find_cell(record, "python--dynamic-typing"), record=record)
    assert draft.chat_run_id == r5_run["run_id"]
    assert (draft.proposer.agent, draft.proposer.prompt_version) == ("r5-reality-checker",
                                                                     "v-test")
    assert draft.since == "3.14"
    assert draft.evidence[0].source == "python-langref-3"
