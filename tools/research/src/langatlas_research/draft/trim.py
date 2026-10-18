"""Cut a role's over-cap output down to the cap by asking an agent which items to keep (D71).

A cap is a cost bound on one run's output, not a reason to throw the run away: refusing 74 edges
because the cap is 60 loses all 74. The trimmer only *selects* — it never edits an item, so the
evidence binding and the D24 gate downstream see exactly what the proposing role wrote. What was
cut is returned to the caller, which records it in the plan so the cut stays visible in git."""
from dataclasses import dataclass

from pydantic import BaseModel, Field

from langatlas_pipeline.prompts import PromptRef, load_prompt
from langatlas_research.config import ClaudeRoleConfig
from langatlas_research.errors import DraftOutputInvalid
from langatlas_research.survey.chunks import ChunkLookup
from langatlas_research.survey.claude import run_structured

TRIMMER_PROMPT_ID = "r4-trimmer"

# A cited passage can be thousands of characters; the trimmer needs enough to judge whether the
# passage states the claim, and a packet of 70+ candidates with three passages each must stay
# small enough for one cheap call.
PASSAGE_EXCERPT_CHARS = 500


@dataclass(frozen=True)
class TrimCandidate:
    """One item a role proposed: its key, its claim in a sentence, and the chunks it cites."""

    key: str
    claim: str
    chunk_ids: tuple[str, ...]


class TrimOut(BaseModel):
    keep: list[str] = Field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class TrimResult:
    kept: tuple[str, ...]
    dropped: tuple[str, ...]
    reason: str


def unique_keys(keys: list[str]) -> list[str]:
    """Make a list of keys distinct so the trimmer can name each candidate unambiguously.

    @param keys: item keys, possibly repeated
    @returns: the keys in order, with a repeat suffixed by `~<index>`"""
    seen: set[str] = set()
    distinct = []
    for index, key in enumerate(keys):
        distinct.append(key if key not in seen else f"{key}~{index}")
        seen.add(key)
    return distinct


def _render_candidate(candidate: TrimCandidate, lookup: ChunkLookup) -> str:
    lines = [f"- key: {candidate.key}", f"  claim: {candidate.claim}"]
    for chunk_id in candidate.chunk_ids:
        ref = lookup(chunk_id)
        if ref is None:
            lines.append(f"  cites: {chunk_id} (unresolved)")
            continue
        excerpt = " ".join(ref.text.split())[:PASSAGE_EXCERPT_CHARS]
        lines.append(f"  cites: {chunk_id} ({ref.source_id} {ref.locator}): {excerpt}")
    return "\n".join(lines)


def trim_to_cap(ctx, candidates: list[TrimCandidate], cap: int, *, what: str,
                role: ClaudeRoleConfig, lookup: ChunkLookup,
                prompt: PromptRef | None = None) -> TrimResult:
    """Ask the trimmer which `cap` of the candidates to keep.

    @param candidates: every item the role proposed, keys distinct
    @param cap: how many may be kept
    @param what: the plural noun for the prompt ("edges", "nodes")
    @param role: the trimmer's Claude role configuration
    @returns: the kept and dropped keys, each in candidate order, and the trimmer's reason
    @raises DraftOutputInvalid: the trimmer named a key it was not offered, repeated one, or
        did not return exactly `cap` keys"""
    variables = {
        "what": what, "cap": str(cap),
        "candidates": ctx.tool_result(
            tool="r4-trim", kind="trim-candidates",
            text="\n".join(_render_candidate(c, lookup) for c in candidates)),
    }
    out, _ = run_structured(ctx, prompt or load_prompt(TRIMMER_PROMPT_ID), variables,
                            output_model=TrimOut, role_config=role)
    offered = {candidate.key for candidate in candidates}
    problems = []
    if len(set(out.keep)) != len(out.keep):
        problems.append("repeated a key")
    if unknown := sorted(set(out.keep) - offered):
        problems.append(f"named keys it was not offered: {', '.join(unknown)}")
    if len(out.keep) != cap:
        problems.append(f"returned {len(out.keep)} keys, not {cap}")
    if problems:
        raise DraftOutputInvalid(f"{TRIMMER_PROMPT_ID}: " + "; ".join(problems))
    kept = set(out.keep)
    return TrimResult(
        kept=tuple(c.key for c in candidates if c.key in kept),
        dropped=tuple(c.key for c in candidates if c.key not in kept),
        reason=out.reason)


def trimmed_finding(what: str, result: TrimResult) -> dict:
    """The plan finding that records a cut.

    @param what: the plural noun of the trimmed items
    @returns: a `trimmed` finding naming every dropped key"""
    return {"kind": "trimmed",
            "detail": f"Trimmed {len(result.dropped)} {what} over the cap: {result.reason}",
            "keys": list(result.dropped)}
