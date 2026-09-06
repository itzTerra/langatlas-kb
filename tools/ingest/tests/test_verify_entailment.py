import pytest
from langatlas_ingest.verify.entailment import (
    AssertionOut, EntailmentOut, fold_assertions, is_inconsistent, run_entailment,
)
from langatlas_pipeline.injection import is_delimited


def a(kind, status):
    return AssertionOut(kind=kind, text="t", status=status, grounding_span="g")


def test_all_supported_folds_to_supported():
    assert fold_assertions([a("presence", "supported"), a("qualifier", "supported")]) \
        == "supported"


def test_any_contradiction_folds_to_contradicted():
    assert fold_assertions([a("presence", "supported"), a("since", "contradicted")]) \
        == "contradicted"


def test_an_unsupported_presence_folds_to_unsupported():
    assert fold_assertions([a("presence", "not-supported"), a("qualifier", "supported")]) \
        == "unsupported"


def test_a_supported_core_with_an_unsupported_qualifier_folds_to_partial():
    # This is the overstated-claim stratum: the K1 laundering pattern the whole stage
    # exists to catch, and the only case `partial` is meant to describe.
    assert fold_assertions([a("presence", "supported"), a("qualifier", "not-supported")]) \
        == "partial"


def test_a_supported_core_with_an_unsupported_since_folds_to_partial():
    assert fold_assertions([a("presence", "supported"), a("since", "not-supported")]) \
        == "partial"


def test_no_assertions_at_all_is_unsupported():
    assert fold_assertions([]) == "unsupported"


def test_a_set_with_no_presence_assertion_still_folds():
    assert fold_assertions([a("qualifier", "supported")]) == "supported"
    assert fold_assertions([a("qualifier", "not-supported")]) == "partial"


def test_a_since_claim_with_no_since_status_is_inconsistent():
    out = EntailmentOut(assertions=[a("presence", "supported"), a("since", "supported")],
                        since_status=None)
    assert is_inconsistent(out, has_since=True) is True


def test_a_since_claim_with_a_status_is_consistent():
    out = EntailmentOut(assertions=[a("presence", "supported"), a("since", "supported")],
                        since_status="since-supported")
    assert is_inconsistent(out, has_since=True) is False


def test_an_empty_decomposition_is_inconsistent():
    assert is_inconsistent(EntailmentOut(assertions=[]), has_since=False) is True


def test_a_since_status_on_a_claim_with_no_version_is_inconsistent():
    out = EntailmentOut(assertions=[a("presence", "supported")],
                        since_status="since-supported")
    assert is_inconsistent(out, has_since=False) is True


class FakeCompletion:
    def __init__(self, parsed):
        self.parsed = parsed
        self.resolved_model = "deepseek-v4"


class RecordingCtx:
    def __init__(self, out):
        self.out = out
        self.messages = None
        self.alias = None

    def tool_result(self, *, tool, text, source_id=None, kind="source-chunk"):
        from langatlas_pipeline.injection import delimit_untrusted
        return delimit_untrusted(text, source_id=source_id, kind=kind)

    def complete(self, alias, messages, *, prompt, schema=None, sampling=None):
        self.alias, self.messages, self.sampling = alias, messages, sampling
        return FakeCompletion(self.out)


def test_run_entailment_returns_the_parsed_output_and_the_resolved_model():
    out = EntailmentOut(assertions=[a("presence", "supported")])
    ctx = RecordingCtx(out)
    payload = {"fact_id": "f-1", "claim": "c", "since": None, "source_id": "s",
               "locator": "p. 1", "quote": None}
    got, model = run_entailment(ctx, payload=payload, evidence_text="body",
                                source_id="s", alias="deepseek")
    assert got is out
    assert model == "deepseek-v4"
    assert ctx.sampling.temperature == 0.0


def test_run_entailment_never_puts_the_payloads_extra_keys_in_the_prompt():
    # The prompt declares exactly four variables. A payload key that is not one of them
    # must not reach the model — `PromptRef.render` is strict in both directions, so a
    # leak here is a KeyError, not a silent context-blindness breach.
    out = EntailmentOut(assertions=[a("presence", "supported")])
    ctx = RecordingCtx(out)
    payload = {"fact_id": "f-1", "claim": "c", "since": None, "source_id": "s",
               "locator": "p. 1", "quote": "q"}
    run_entailment(ctx, payload=payload, evidence_text="body", source_id="s",
                   alias="deepseek")
    rendered = "\n".join(m["content"] for m in ctx.messages)
    assert "f-1" not in rendered


def test_the_evidence_is_delimited_and_stays_out_of_the_system_role():
    ctx = RecordingCtx(EntailmentOut(assertions=[a("presence", "supported")]))
    payload = {"fact_id": "f-1", "claim": "c", "since": None, "source_id": "s",
               "locator": "p. 1", "quote": None}
    run_entailment(ctx, payload=payload, evidence_text="untrusted", source_id="s",
                   alias="deepseek")
    user = [m for m in ctx.messages if m["role"] == "user"][0]
    assert is_delimited(user["content"])
    for message in ctx.messages:
        if message["role"] in ("system", "developer"):
            assert not is_delimited(message["content"])
