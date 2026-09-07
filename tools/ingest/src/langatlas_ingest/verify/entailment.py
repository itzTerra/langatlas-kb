from typing import Literal
from pydantic import BaseModel, Field
from langatlas_ingest.verify.inputs import delimit_agent_text
from langatlas_pipeline.prompts import load_prompt
from langatlas_pipeline.providers.completion import Sampling

PROMPT_ID = "verify-entailment"

# Which assertion kind carries the claim's core. Section 6.2's fold turns on it: a
# not-supported core is `unsupported`, a supported core with a not-supported qualifier is
# `partial` — the overstated-claim case.
CORE_KIND = "presence"


class AssertionOut(BaseModel):
    kind: Literal["presence", "syntax-form", "since", "qualifier"]
    text: str
    status: Literal["supported", "not-supported", "contradicted"]
    grounding_span: str = ""


class EntailmentOut(BaseModel):
    """Section 6.2's structured entailment output. Deliberately carries **no overall
    verdict field**: the overall verdict is a fixed rule (`fold_assertions`) applied in
    code, so a model cannot talk its way past the decomposition it just produced."""

    assertions: list[AssertionOut] = Field(default_factory=list)
    since_status: Literal["since-supported", "as-of-supported"] | None = None


def fold_assertions(assertions) -> str:
    """Section 6.2's fixed rule from per-assertion statuses to one of the six verdicts.

    @param assertions - an iterable of `AssertionOut`
    @returns "contradicted" | "unsupported" | "partial" | "supported"
    """
    assertions = list(assertions)
    if not assertions:
        # A decomposition that produced nothing has not shown support for anything. It is
        # also caught by `is_inconsistent` and escalated, but the verdict must be safe
        # even if escalation is disabled.
        return "unsupported"
    if any(a.status == "contradicted" for a in assertions):
        return "contradicted"
    core = [a for a in assertions if a.kind == CORE_KIND]
    if not core or any(a.status != "supported" for a in core):
        # No `presence` assertion at all means the claim's core was never judged — the
        # same standing as a decomposition that produced nothing, and treated the same
        # way: `unsupported` here (fail closed even with escalation disabled) *and*
        # inconsistent in `is_inconsistent` (so the escalated pass gets to produce a real
        # decomposition). Folding a lone supported `qualifier` to `supported` would admit
        # a fact whose presence claim no model ever checked.
        return "unsupported"
    if all(a.status == "supported" for a in assertions):
        return "supported"
    return "partial"


def is_inconsistent(out: EntailmentOut, *, has_since: bool) -> bool:
    """Section 6.2's third escalation trigger: per-assertion output that does not hang
    together. Cheap to check and worth escalating — an inconsistent decomposition is the
    shape a model produces when it did not actually read the passage.

    @param out - the parsed `EntailmentOut`
    @param has_since - whether the claim being checked carries a version (`since`)
    @returns True when the decomposition is internally inconsistent
    """
    if not out.assertions:
        return True
    if not any(a.kind == CORE_KIND for a in out.assertions):
        # Every prompt in this stage asks for the core assertion by name, so its absence
        # is a decomposition that did not do the work — worth the reasoning pass, exactly
        # like an empty one.
        return True
    since_assertions = [a for a in out.assertions if a.kind == "since"]
    if has_since:
        if not since_assertions:
            return True
        contradicted = any(a.status == "contradicted" for a in since_assertions)
        # A contradicted version is neither since-supported nor as-of-supported; anything
        # else must land on one side of the split.
        if not contradicted and out.since_status is None:
            return True
    else:
        if out.since_status is not None or since_assertions:
            return True
    return False


def run_entailment(ctx, *, payload: dict, evidence_text: str, source_id: str,
                   alias: str) -> tuple[EntailmentOut, str]:
    """Section 6.2's stage 3: context-blind entailment on the university API.

    The verifier has **no tools** — retrieval already happened in the runner, and the
    passage arrives as delimited data. Only four of the payload's keys are rendered:
    `fact_id` and `source_id` are bookkeeping the model has no use for, and feeding them
    in would hand it identifying context the whitelist exists to withhold.

    @param ctx - a `RunContext` (or test double exposing `tool_result`/`complete`)
    @param payload - the output of `whitelist_payload`
    @param evidence_text - the resolved passage text for this citation
    @param source_id - the source the evidence came from, for the D31 audit trail
    @param alias - a model alias from `config/provider_capabilities.yaml`, never a
        hardcoded Claude/Anthropic model id (D6: Claude is never in the verification loop)
    @returns (parsed output, the resolved model id the provider actually answered with)
    """
    prompt = load_prompt(PROMPT_ID)
    evidence = ctx.tool_result(tool=PROMPT_ID, text=evidence_text, source_id=source_id)
    # The claim, its version and its locator are agent-authored, so they go through the
    # same D31 door as the evidence rather than being rendered raw into the prompt.
    messages = prompt.render(
        claim=delimit_agent_text(ctx, payload["claim"], "claim"),
        since=delimit_agent_text(ctx, payload.get("since"), "version"),
        locator=delimit_agent_text(ctx, payload["locator"], "locator"),
        evidence=evidence)
    completion = ctx.complete(alias, messages, prompt=prompt, schema=EntailmentOut,
                              sampling=Sampling(temperature=0.0))
    return completion.parsed, completion.resolved_model
