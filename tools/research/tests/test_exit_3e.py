"""Stage 3E's exit condition, end to end against a real git repo and the real commit protocol.

No provider and no database: the reality checker runs on `FakeCtx` with scripted structured
output, evidence resolves through a fixed chunk lookup, and the verifier is injected. What this
proves is what must hold whatever a model says — the questionnaire is committed before anyone
answers it, every answer goes through the D24 gate with `since` inside the existence claim
(D65) and bounded when only as-of (D66), and the cycle closes with its findings committed and
nothing minted (D68)."""
import subprocess

import pytest
from ruamel.yaml import YAML

from langatlas_commit.land import Landed
from langatlas_ingest.verify.pipeline import VerifyDeps
from langatlas_ingest.verify.sources import SourceFacts
from langatlas_ingest.verify.verdicts import PairVerdict
from langatlas_pipeline.prompts import mint_prompt_version
from langatlas_pipeline.providers.claude_runs import AgentRunResult
from langatlas_questionnaire.spec import load_spec, validate_spec
from langatlas_research.config import ResearchConfig
from langatlas_research.cycle import load_cycle
from langatlas_research.paths import research_config_path
from langatlas_research.reality.classifier import CLASSIFIER_VARIABLES, run_classifier
from langatlas_research.reality.gate import verify_cells
from langatlas_research.reality.lifecycle import finalize_r5, open_r5
from langatlas_research.reality.record import find_cell, save_record
from langatlas_research.schema import validate_research_tree
from langatlas_research.survey.chunks import ChunkRef
from langatlas_validate.store import validate_store

pytestmark = pytest.mark.git
_yaml = YAML(typ="safe")

PY, HS = "python-langref-3#c00012", "haskell-2010-report#c00140"
CHUNKS = {
    PY: ChunkRef(chunk_id=PY, source_id="python-langref-3", locator="§3.1",
                 breadcrumb="3 Data model", content_hash="p1",
                 text="Every object has an identity, a type and a value. The type of an object"
                      " is determined when the program runs."),
    HS: ChunkRef(chunk_id=HS, source_id="haskell-2010-report", locator="§4.1.4",
                 breadcrumb="4 Declarations and Bindings", content_hash="h1",
                 text="Haskell uses a Hindley-Milner polymorphic type system; types are"
                      " inferred and checked statically."),
}
SOURCE_FACTS = {
    "python-langref-3": SourceFacts("python-langref-3", "B", "reference-implementation-docs",
                                    (), {}, language_version="3.14"),
    "haskell-2010-report": SourceFacts("haskell-2010-report", "A", "formal-spec", (), {},
                                       language_version="Haskell 2010"),
}


def _cited(chunk_id):
    return [{"chunk_id": chunk_id}]


ANSWERS = {
    "python": {
        "cells": [
            {"feature": "dynamic-typing", "answer": "present", "since": "3.14",
             "evidence": _cited(PY),
             "characteristics": [{"key": "c-runtime-types",
                                  "text": "An object's type is fixed when the program runs.",
                                  "evidence": _cited(PY)}]},
            {"feature": "static-typing", "answer": "absent", "evidence": _cited(PY),
             "absence_scope": "The data model chapter defines every point at which types are"
                              " determined; none precedes execution."},
            {"feature": "type-inference", "mappable": False,
             "note": "There is nothing to infer without static types."}]},
    "haskell": {
        "cells": [
            {"feature": "static-typing", "answer": "present", "since": "Haskell 2010",
             "evidence": _cited(HS)},
            {"feature": "dynamic-typing", "answer": "absent", "evidence": _cited(HS),
             "absence_scope": "The report's type system chapter covers every type check; all"
                              " are static."},
            # Too early for an as-of citation of the 2010 report (D66): refused.
            {"feature": "type-inference", "answer": "present", "since": "Haskell 98",
             "evidence": _cited(HS)}],
        "uncovered": [{"key": "type-classes", "name": "Type classes",
                       "note": "Ad-hoc polymorphism no questionnaire item covers.",
                       "evidence": _cited(HS)}]},
}


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


def _result(structured):
    return AgentRunResult(session_id="s", result_text="", structured_output=structured,
                          num_turns=1, is_error=False, tokens_in=1, tokens_out=1,
                          cost_usd=None, terminal_reason="completed")


def _verifier(seen):
    """Everything supported, every `since` only as-of (no passage states an origin), and every
    characteristic unsupported — so D66's bound and per-anchor recording are both exercised."""
    def _verify(ctx, conn, *, claim, citation, **kwargs):
        seen.append(claim)
        verdict = "unsupported" if claim.claim.startswith("characteristic(") else "supported"
        return PairVerdict(fact_id=claim.fact_id, source_id=citation.source_id,
                           locator=citation.locator, verdict=verdict,
                           since_status="as-of-supported" if claim.since else None,
                           date="2026-09-20")
    return _verify


def test_a_signed_cycle_runs_r5_from_compile_to_committed_findings(ontology_repo, fake_ctx,
                                                                   tmp_path):
    repo = ontology_repo
    base = _git(["rev-parse", "origin/main"], repo).strip()
    registry_before = (repo / "languages" / "_registry.yaml").read_text()
    config = ResearchConfig.load(research_config_path())

    # --- compile: the questionnaire is committed before anyone answers it ------------------
    record, outcome = open_r5(1, repo_root=repo,
                              chat_run_id="2026-09-20-r5-compile-01-typing-01",
                              now="2026-09-20T10:00:00Z")
    assert isinstance(outcome, Landed)
    spec = load_spec(repo / record["questionnaire"])
    assert validate_spec(spec) == []

    # --- classify: one scripted session per sampled language ----------------------------
    placeholders = " ".join("{{" + v + "}}" for v in CLASSIFIER_VARIABLES
                            if v not in ("dimensions", "items"))
    prompt = mint_prompt_version(
        "exit-reality",
        "---\nprompt_id: exit-reality\nvariables: [" + ", ".join(CLASSIFIER_VARIABLES)
        + "]\n---\n# system\n" + placeholders + "\n\n# user\n{{dimensions}}\n{{items}}\n",
        root=tmp_path)
    cycle = load_cycle(1, repo_root=repo)
    for language in cycle.languages:
        fake_ctx.claude_results.append(_result(ANSWERS[language]))
        record, _ = run_classifier(fake_ctx, cycle, record, spec, language=language,
                                   language_kind="general-purpose", repo_root=repo,
                                   lookup=CHUNKS.get, config=config,
                                   source_facts=SOURCE_FACTS, prompt=prompt)
    save_record(record, repo_root=repo)

    # --- verify: the D24 gate -----------------------------------------------------------
    seen = []
    record, results = verify_cells(fake_ctx, None, record, cycle=cycle, repo_root=repo,
                                   config=config, deps=VerifyDeps(source_facts=SOURCE_FACTS),
                                   verifier=_verifier(seen))
    assert len(results) == 5
    assert not any(claim.claim.startswith("instance-field(") for claim in seen)   # D65
    python_dynamic = find_cell(record, "python--dynamic-typing")
    assert python_dynamic["status"] == "admitted"
    assert [f["admissible"] for f in python_dynamic["verification"]["facts"]] == [True, False]
    too_early = find_cell(record, "haskell--type-inference")
    assert too_early["status"] == "refused" and "D66" in too_early["verification"]["detail"]
    absence = next(claim for claim in seen if claim.claim
                   == "instance-exists(fi.haskell.dynamic-typing, status=absent)")
    assert "dynamic type checking" in absence.feature_aliases
    save_record(record, repo_root=repo)

    # --- finalize: findings and the cycle land; nothing is minted -----------------------
    closed, final = finalize_r5(1, repo_root=repo)
    assert all(isinstance(result, Landed) for result in final)
    assert closed.status == "r5-done"

    touched = set(_git(["diff", "--name-only", base, "origin/main"], repo).split())
    assert touched == {record["questionnaire"], "research/reality-checks/01-typing.yaml",
                       "research/cycles/01-typing.yaml"}
    assert int(_git(["rev-list", "--count", f"{base}..origin/main"], repo)) == 3
    assert not (repo / "languages" / "python").exists()
    assert not (repo / "languages" / "haskell").exists()
    assert (repo / "languages" / "_registry.yaml").read_text() == registry_before

    committed = _yaml.load(_git(["show", "origin/main:research/reality-checks/01-typing.yaml"],
                                repo))
    assert committed["findings"] == {"unmappable": ["python--type-inference"],
                                     "uninhabited_values": [], "unfittable": [],
                                     "exclusivity_violations": []}
    assert committed["summary"] == {"languages": 2, "cells": 6, "mappable": 5,
                                    "unmappable": 1, "admitted": 4, "refused": 1,
                                    "unsourced": 0, "uncovered": 1}
    assert [entry["key"] for entry in committed["uncovered"]] == ["haskell--type-classes"]
    assert validate_store(repo) == []
    assert validate_research_tree(repo) == []
