"""D30(a): the verifier-replay counterfactual (§7.13).

The question is narrow and honest: *did the challenger round change anything a machine can
detect?* Re-score the carve as it stood when the debate opened — which is why the debate record
keeps `pre_challenge` — and compare that verdict with the one the post-resolution carve actually
got. A debate that ends in `keep` has no counterfactual to compute: the pre- and post-challenge
carves are the same record, and reporting them as "unchanged" would dilute the measurement with
cases that could not have changed.

This is not a quality judgment on the debate. A debate that improved a carve in ways the verifier
cannot see reports as unchanged, and that is the known limit of the measurement — §7.13 accepts it
and defers the downstream dispute-rate comparison until there is enough volume to control for
selection effects."""
from dataclasses import dataclass
from pathlib import Path

from langatlas_ingest.verify.pipeline import verify_pair
from langatlas_research.config import ResearchConfig
from langatlas_research.draft.debate_record import iter_debates
from langatlas_research.draft.gate import verify_entry
from langatlas_research.draft.minting import RECORD_KINDS_BY_LIST, entry_draft
from langatlas_research.draft.plan import find_entry, load_plan
from langatlas_research.mint import render_draft

# Dispositions whose post-resolution carve differs from the pre-challenge one. `keep` and
# `escalate` leave the record identical, so there is nothing to compare.
_COMPARABLE = ("revise", "split", "merge", "drop")


@dataclass(frozen=True)
class ReplayRow:
    debate_id: str
    key: str
    disposition: str
    pre_verdict: str
    post_verdict: str
    pre_admissible: bool
    post_admissible: bool

    @property
    def changed(self) -> bool:
        return (self.pre_verdict != self.post_verdict
                or self.pre_admissible != self.post_admissible)


def replay_counterfactual(ctx, conn, repo_root: Path, *, cycle: int | None,
                          config: ResearchConfig, deps=None, queue=None,
                          verifier=verify_pair) -> list[ReplayRow]:
    """@param cycle: restrict to one cycle; None replays every committed debate.
    @param queue: deliberately defaulted to None — a replay must not file sourcing-queue
        entries or bounce anything. It is a measurement, not a pipeline step."""
    rows = []
    plans: dict[str, dict] = {}
    for debate in iter_debates(repo_root):
        if cycle is not None and debate["cycle"] != cycle:
            continue
        resolution = debate["resolution"]
        if resolution["disposition"] not in _COMPARABLE:
            continue

        slug = f"{debate['cycle']:02d}-{debate['theme']}"
        plan = plans.setdefault(slug, load_plan(slug, repo_root=repo_root))
        key = debate["target"]["key"]
        try:
            list_name, post = find_entry(plan, key)
        except KeyError:
            continue
        post_verification = post.get("verification") or {}

        pre = debate["pre_challenge"]
        minted = render_draft(entry_draft(pre, plan=plan, ctx_run_id=ctx.run_id,
                                          prompt_version=""))
        result = verify_entry(ctx, conn, minted, key=key,
                              kind=RECORD_KINDS_BY_LIST[list_name](pre),
                              repo_root=None,          # never mints into the real register
                              config=config, deps=deps, queue=queue, verifier=verifier)
        rows.append(ReplayRow(
            debate_id=debate["id"], key=key, disposition=resolution["disposition"],
            pre_verdict=result.verdict, post_verdict=post_verification.get("verdict", "-"),
            pre_admissible=result.admissible,
            post_admissible=bool(post_verification.get("admissible"))))
    return rows


def render_replay(rows: list[ReplayRow]) -> str:
    changed = sum(1 for row in rows if row.changed)
    lines = ["# D30(a) verifier-replay counterfactual", "",
             f"Challenger rounds that changed a machine-detectable verdict:"
             f" **{changed} of {len(rows)}** comparable debate(s).", "",
             "| debate | carve | disposition | pre | post | changed |",
             "|---|---|---|---|---|---|"]
    for row in rows:
        pre = f"{row.pre_verdict}{'' if row.pre_admissible else ' (refused)'}"
        post = f"{row.post_verdict}{'' if row.post_admissible else ' (refused)'}"
        lines.append(f"| {row.debate_id} | {row.key} | {row.disposition} | {pre} | {post} |"
                     f" {'yes' if row.changed else 'no'} |")
    if not rows:
        lines.append("| — | — | — | — | — | — |")
    return "\n".join(lines) + "\n"
