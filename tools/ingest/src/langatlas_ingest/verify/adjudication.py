from typing import Literal
from pydantic import BaseModel
from langatlas_ingest.verify.inputs import delimit_agent_text
from langatlas_pipeline.prompts import load_prompt
from langatlas_pipeline.providers.completion import Sampling

PROMPT_ID = "verify-quote-adjudication"


class QuoteAdjudication(BaseModel):
    """Section 6.2's stage-2 tiebreak result."""

    outcome: Literal["ocr-noise", "fabrication"]
    reason: str = ""


def adjudicate_quote(ctx, *, quote: str, evidence_text: str, source_id: str,
                     ratio: float, alias: str = "deepseek") -> QuoteAdjudication:
    """Decide whether a near-miss quote is extraction damage or a fabrication.

    Only called for the band between `QUOTE_FAIL_RATIO` and `QUOTE_PASS_RATIO` — the
    mechanical matcher has already decided every other case, and this call is the reason
    an OCR-noisy corpus does not produce a wall of false rejects.

    Both sides of the comparison go through `ctx.tool_result` (the D31 door) — the
    passage as untrusted external text, the claimed quote as agent-authored text — so
    each is scanned, logged and delimited before it reaches the model, in a user-role
    message only.

    D6: `alias` resolves through the model-alias/config machinery (`config/
    provider_capabilities.yaml`) like every other pipeline call — Claude is never in the
    verification loop, so this default names a university-API alias, never a literal
    Claude/Anthropic model id.

    @param ctx - a `RunContext` (or test double exposing `tool_result`/`complete`)
    @param quote - the claimed quote
    @param evidence_text - the cited passage to compare it against
    @param source_id - the source the evidence came from, for the D31 audit trail
    @param ratio - the token-level similarity `check_quote` computed for this pair
    @param alias - a model alias from `config/provider_capabilities.yaml`, never a
        hardcoded model id
    @returns the parsed adjudication
    """
    prompt = load_prompt(PROMPT_ID)
    evidence = ctx.tool_result(tool=PROMPT_ID, text=evidence_text, source_id=source_id)
    # The claimed quote is agent-authored — the half of this comparison that might be
    # fabricated — so it goes through the same door as the passage rather than being
    # rendered raw.
    messages = prompt.render(quote=delimit_agent_text(ctx, quote, "quote"),
                             evidence=evidence, ratio=f"{ratio:.3f}")
    completion = ctx.complete(alias, messages, prompt=prompt,
                              schema=QuoteAdjudication, sampling=Sampling(temperature=0.0))
    return completion.parsed
