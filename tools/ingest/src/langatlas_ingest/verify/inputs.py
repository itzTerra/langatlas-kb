from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimInput:
    """The claim half of a (claim, citation) pair, in exactly the shape Section 6.2's
    whitelist permits. Deliberately *not* the record: a record carries notes, provenance
    and a proposer, and the way to keep those out of the verifier's context is to never
    assemble them, not to strip them later."""

    fact_id: str
    claim: str
    since: str | None = None
    status: str | None = None                  # present | partial | absent
    absence_scope: str | None = None           # D49; only meaningful when status == absent
    feature_aliases: tuple[str, ...] = ()      # D49's negative-grep vocabulary
    # Section 6.2's one escape hatch: a citation whose claim *is* the source's existence
    # (identification metadata, Section 3.4) needs no evidence resolution at all.
    registry_existence: bool = False


@dataclass(frozen=True)
class CitationInput:
    source_id: str
    locator: str
    quote: str | None = None


def whitelist_payload(claim: ClaimInput, citation: CitationInput) -> dict:
    """Build the verifier's model-facing input by allow-list construction.

    Context blindness is structural (Section 6.2): notes, `claim_origin`, proposer
    identity/persona, debate or chat context, the item's own provenance and every other
    citation's verdict are simply never assembled here. D49's inverted-framing stage
    verifies the agent's own absence argument, so an `absent` claim widens the whitelist
    by exactly `absence_scope` and `feature_aliases` — nothing else.

    @returns the dict the entailment stage renders into its prompt
    """
    payload = {"fact_id": claim.fact_id, "claim": claim.claim, "since": claim.since,
               "source_id": citation.source_id, "locator": citation.locator,
               "quote": citation.quote}
    if claim.status == "absent":
        payload["absence_scope"] = claim.absence_scope
        payload["feature_aliases"] = list(claim.feature_aliases)
    return payload


def delimit_agent_text(ctx, text, field: str) -> str:
    """Send one agent-authored field to the model through D31's untrusted-content door.

    The claim, its version and its locator are written by the proposing agent — they are
    the very content this gate exists to check, so they get the same delimiting,
    injection scan and transcript entry the evidence does. `source_id` is deliberately
    None: naming the fact's own source inside the block would hand the model the
    identifying context `whitelist_payload` withholds.

    @param ctx - a `RunContext` (or test double exposing `tool_result`)
    @param text - the field's value; None/empty renders the literal "none", which is our
        own text and needs no block
    @param field - what the value is, rendered as the block's `kind` attribute

    @returns the delimited block, or "none"
    """
    if not text:
        return "none"
    return ctx.tool_result(tool="agent-authored", text=str(text), source_id=None,
                           kind=f"agent-authored-{field}")
