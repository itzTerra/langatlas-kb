"""R5's reality checker, against a scripted Claude channel."""
from dataclasses import replace

import pytest

from langatlas_ingest.verify.sources import SourceFacts
from langatlas_pipeline.prompts import load_prompt, mint_prompt_version
from langatlas_pipeline.providers.claude_runs import AgentRunResult
from langatlas_research.config import ResearchConfig
from langatlas_research.errors import RealityOutputInvalid, SignOffStale
from langatlas_research.paths import research_config_path, themes_path
from langatlas_research.reality.classifier import (
    CLASSIFIER_PROMPT_ID, CLASSIFIER_VARIABLES, run_classifier,
)
from langatlas_research.reality.record import find_cell

EVIDENCE = [{"chunk_id": "scott-plp#c00310"}]
BOUND = [{"source": "scott-plp", "locator": "§7.2", "chunk_id": "scott-plp#c00310"}]
SOURCE_FACTS = {"python-langref-3": SourceFacts("python-langref-3", "B",
                                                "reference-implementation-docs", (), {},
                                                language_version="3.14")}


def _result(structured):
    return AgentRunResult(session_id="s", result_text="", structured_output=structured,
                          num_turns=1, is_error=False, tokens_in=1, tokens_out=1,
                          cost_usd=None, terminal_reason="completed")


def _out(**over):
    out = {
        "cells": [
            {"feature": "dynamic-typing", "answer": "present", "since": "3.14",
             "evidence": list(EVIDENCE), "note": "Checks at run time.",
             "characteristics": [{"key": "c-runtime-checks",
                                  "text": "Type errors surface at run time.",
                                  "evidence": list(EVIDENCE)}]},
            {"feature": "static-typing", "answer": "absent", "evidence": list(EVIDENCE),
             "absence_scope": "The reference defines no compile-time checking phase."},
            {"feature": "type-inference", "mappable": False,
             "note": "Inference presupposes static types."}],
        "uncovered": [{"key": "duck-typing", "name": "Duck typing",
                       "note": "Typing by behaviour.", "evidence": list(EVIDENCE)}]}
    out.update(over)
    return out


@pytest.fixture
def config(research_repo):
    return ResearchConfig.load(research_config_path(research_repo))


@pytest.fixture
def prompt(tmp_path):
    placeholders = " ".join("{{" + v + "}}" for v in CLASSIFIER_VARIABLES
                            if v not in ("dimensions", "items"))
    text = ("---\nprompt_id: test-reality\nvariables: [" + ", ".join(CLASSIFIER_VARIABLES)
            + "]\n---\n# system\n" + placeholders + "\n\n# user\n{{dimensions}}\n{{items}}\n")
    return mint_prompt_version("test-reality", text, root=tmp_path)


@pytest.fixture
def classify(fake_ctx, signed_cycle, r5_record, r5_spec, research_repo, fake_lookup, config,
             prompt):
    def _run(output, *, language="python", record=None, config=config):
        fake_ctx.claude_results.append(_result(output))
        return run_classifier(fake_ctx, signed_cycle, record or r5_record, r5_spec,
                              language=language, language_kind="general-purpose",
                              repo_root=research_repo, lookup=fake_lookup, config=config,
                              source_facts=SOURCE_FACTS, prompt=prompt)
    return _run


def test_a_language_is_answered_cell_by_cell_with_bound_evidence(classify, fake_ctx, prompt):
    record, _warnings = classify(_out())
    dynamic = find_cell(record, "python--dynamic-typing")
    assert dynamic["status"] == "proposed"
    assert dynamic["proposal"]["sources"] == BOUND
    assert dynamic["proposal"]["since"] == "3.14"
    assert dynamic["proposal"]["characteristics"] == [
        {"key": "c-runtime-checks", "text": "Type errors surface at run time.",
         "sources": BOUND}]
    absent = find_cell(record, "python--static-typing")
    assert absent["answer"] == "absent" and "since" not in absent["proposal"]
    assert absent["proposal"]["absence_scope"] == ("The reference defines no compile-time"
                                                   " checking phase.")
    unmappable = find_cell(record, "python--type-inference")
    assert (unmappable["status"], unmappable["proposal"]) == ("unmappable", None)
    assert [u["key"] for u in record["uncovered"]] == ["python--duck-typing"]
    assert record["runs"]["classify"]["python"] == {
        "run_id": fake_ctx.run_id, "prompt_version": prompt.version, "model": "claude"}


def test_the_checker_is_told_which_version_an_as_of_since_must_be(classify, fake_ctx):
    classify(_out())
    _prompt_text, options = fake_ctx.claude_calls[0]
    assert "python-langref-3 (documents version 3.14)" in options.system_prompt


def test_the_questionnaire_reaches_the_model_only_as_delimited_data(classify, fake_ctx):
    classify(_out())
    kinds = {result["kind"] for result in fake_ctx.tool_results}
    assert {"questionnaire-items", "questionnaire-dimensions"} <= kinds
    _prompt_text, options = fake_ctx.claude_calls[0]
    assert "dynamic-typing" not in options.system_prompt


def test_a_present_answer_needs_a_since(classify):
    out = _out()
    del out["cells"][0]["since"]
    with pytest.raises(RealityOutputInvalid, match="since"):
        classify(out)


def test_an_absent_answer_has_no_since_and_needs_its_scope(classify):
    out = _out()
    out["cells"][1] = {"feature": "static-typing", "answer": "absent", "since": "3.0",
                       "evidence": list(EVIDENCE)}
    with pytest.raises(RealityOutputInvalid, match="absence_scope") as info:
        classify(out)
    assert "describes nothing present" in str(info.value)


def test_every_item_must_be_answered_exactly_once(classify):
    out = _out()
    out["cells"] = out["cells"][:2]
    with pytest.raises(RealityOutputInvalid, match="type-inference: answered 0 times"):
        classify(out)


def test_an_answer_outside_the_questionnaire_is_refused(classify):
    out = _out()
    out["cells"].append({"feature": "gradual-typing", "answer": "present", "since": "3.14",
                         "evidence": list(EVIDENCE)})
    with pytest.raises(RealityOutputInvalid, match="gradual-typing: not a questionnaire item"):
        classify(out)


def test_an_answer_the_corpus_cannot_back_is_unsourced_not_a_failure(classify):
    out = _out()
    out["cells"][0]["evidence"] = [{"chunk_id": "nowhere#c00001"}]
    record, _ = classify(out)
    assert find_cell(record, "python--dynamic-typing")["status"] == "unsourced"
    assert [entry["component"] for entry in record["shakedown"]] == ["classifier"]


def test_an_unresolvable_optional_field_is_dropped_and_logged(classify):
    out = _out()
    out["cells"][0]["characteristics"][0]["evidence"] = [{"chunk_id": "nowhere#c00001"}]
    record, _ = classify(out)
    cell = find_cell(record, "python--dynamic-typing")
    assert cell["status"] == "proposed"
    assert "characteristics" not in cell["proposal"]
    assert "#characteristics[c-runtime-checks]" in record["shakedown"][0]["detail"]


def test_a_language_without_a_configured_reference_is_logged(classify, config):
    bare = replace(config, reality=replace(config.reality, language_sources={}))
    record, _ = classify(_out(), config=bare)
    assert any(entry["component"] == "sources" and entry["detail"].startswith("python:")
               for entry in record["shakedown"])


def test_re_running_a_language_replaces_its_answers(classify):
    first, _ = classify(_out())
    out = _out()
    out["cells"][2] = {"feature": "type-inference", "answer": "absent",
                       "evidence": list(EVIDENCE), "absence_scope": "No inference phase."}
    second, _ = classify(out, record=first)
    assert find_cell(second, "python--type-inference")["status"] == "proposed"
    assert len(second["cells"]) == 3


def test_a_language_outside_the_cycle_sample_is_refused(classify):
    with pytest.raises(RealityOutputInvalid, match="not in cycle"):
        classify(_out(), language="erlang")


def test_a_stale_sign_off_stops_the_run_before_any_claude_message(classify, fake_ctx,
                                                                   research_repo):
    path = themes_path(research_repo)
    path.write_text(path.read_text().replace("Type systems,", "Type systems (edited),"))
    with pytest.raises(SignOffStale):
        classify(_out())
    assert fake_ctx.claude_calls == []


def test_the_registered_prompt_declares_exactly_the_variables_the_role_supplies():
    messages = load_prompt(CLASSIFIER_PROMPT_ID).render(**{v: "x" for v in CLASSIFIER_VARIABLES})
    assert [message["role"] for message in messages] == ["system", "user"]
