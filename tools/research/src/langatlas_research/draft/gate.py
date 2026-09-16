"""The D24 verifier as R4's admissibility gate.

This module assembles no claims of its own. It renders the entry exactly as it will be committed,
runs Stage 1D's `derive_facts` over that record, and hands the resulting (claim, citation) pairs
to `verify_pair` and `decide_fact`. A second claim-assembly path inside 3C would be a second
thing that can drift from §6.2's rules, and the drift would be invisible: the gate would still
say "admissible", about a slightly different claim than the one git holds.

A derived fact with no citations of its own — `edge-polarity` is the only one in 3C's range — is
not independently verifiable and is not a gate. Every fact that *does* carry citations must pass:
a record admitted on one of its facts while another is unsupported is a record that says
something the store cannot back."""
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_ingest.config import IngestConfig
from langatlas_ingest.verify.admissibility import decide_fact
from langatlas_ingest.verify.job_support import work_for_fact
from langatlas_ingest.verify.pipeline import VerifyDeps, verify_pair
from langatlas_research.config import ResearchConfig
from langatlas_research.draft.plan import entries, set_entry
from langatlas_research.mint import MintedRecord, render_draft
from langatlas_validate.compile import derive_facts

_yaml = YAML(typ="safe")

# Which plan lists carry entries the gate can verify. Dimensions and qualities are taxonomy
# entries, not facts: `ontology/taxonomy/*.yaml` has no `sources:` list and no claim template,
# so there is nothing for the verifier to check. Their evidence lives on the layer-3 features
# that use them, which are gated.
GATED_LISTS = ("nodes", "edges", "quality_edges")


@dataclass(frozen=True)
class GateResult:
    key: str
    fact_id: str
    verdict: str
    admissible: bool
    pairs: int
    detail: str = ""
    contradiction_ids: tuple[str, ...] = ()
    run_id: str | None = None

    def as_block(self) -> dict:
        """The plan's `verification:` block."""
        block = {"fact_id": self.fact_id, "verdict": self.verdict,
                 "admissible": self.admissible, "pairs": self.pairs}
        if self.detail:
            block["detail"] = self.detail
        if self.contradiction_ids:
            block["contradiction_ids"] = list(self.contradiction_ids)
        if self.run_id:
            block["run_id"] = self.run_id
        return block


def verify_entry(ctx, conn, minted: MintedRecord, *, key: str, kind: str,
                 repo_root: Path | None, config: ResearchConfig,
                 deps: VerifyDeps | None = None, queue=None,
                 verifier=verify_pair) -> GateResult:
    """Run §6.2 over one rendered record.

    @param minted: the record as it would be committed — rendered, normalized, schema-valid.
    @param kind: its `RECORD_KINDS` value (`concept` | `feature` | `edge` |
        `affects-quality-edge`).
    @param verifier: injected for tests; production passes `verify_pair` unchanged.
    @returns: one `GateResult` folding every verifiable fact on the record."""
    deps = deps or VerifyDeps.build(conn, ctx, config=IngestConfig.load())
    data = _yaml.load(minted.text)
    facts = [fact for fact in derive_facts([(Path(minted.path), kind, minted.text, data)])
             if fact.get("sources")]
    if not facts:
        return GateResult(key=key, fact_id="", verdict="unverified", admissible=False,
                          pairs=0, detail="the record carries no citations at all (D4)",
                          run_id=getattr(ctx, "run_id", None))

    outcomes, total_pairs, details, contradictions = [], 0, [], []
    for fact in facts:
        pairs = [verifier(ctx, conn, claim=claim, citation=citation, deps=deps, queue=queue)
                 for claim, citation in work_for_fact(fact)]
        total_pairs += len(pairs)
        outcome = decide_fact(fact["fact_id"], pairs, deps.source_facts,
                              queue=queue, bounce_budget=config.draft.bounce_budget,
                              contradictions_path=(Path(repo_root) / "contradictions.yaml")
                              if repo_root else None,
                              chat_run_id=getattr(ctx, "run_id", None))
        outcomes.append(outcome)
        contradictions.extend(outcome.contradiction_ids)
        if outcome.bounce_reason:
            details.append(f"{fact['claim'].split('(')[0]}: {outcome.bounce_reason}")

    primary = outcomes[0]
    return GateResult(key=key, fact_id=primary.fact_id, verdict=primary.verification,
                      admissible=all(outcome.admissible for outcome in outcomes),
                      pairs=total_pairs, detail="; ".join(details),
                      contradiction_ids=tuple(dict.fromkeys(contradictions)),
                      run_id=getattr(ctx, "run_id", None))


def verify_plan(ctx, conn, plan: dict, *, repo_root: Path | None, config: ResearchConfig,
                lookup=None, deps: VerifyDeps | None = None, queue=None,
                verifier=verify_pair) -> tuple[dict, list[GateResult]]:
    """Gate every entry that is ready for it — `status: debated`, or `proposed` with no
    contested triggers. An entry that is still waiting on a debate is not a gate failure; it
    is simply not ready, and stamping a verdict on it would hide that.

    @returns: `(updated plan, results in plan order)`."""
    from langatlas_research.draft.minting import RECORD_KINDS_BY_LIST, entry_draft

    deps = deps or VerifyDeps.build(conn, ctx, config=IngestConfig.load())
    updated, results = plan, []
    for name, entry in entries(plan):
        if name not in GATED_LISTS:
            continue
        ready = entry["status"] == "debated" or (entry["status"] == "proposed"
                                                 and not entry.get("contested"))
        if not ready:
            continue
        minted = render_draft(entry_draft(entry, plan=plan, ctx_run_id=ctx.run_id,
                                          prompt_version=""))
        result = verify_entry(ctx, conn, minted, key=entry["key"],
                              kind=RECORD_KINDS_BY_LIST[name](entry), repo_root=repo_root,
                              config=config, deps=deps, queue=queue, verifier=verifier)
        results.append(result)
        updated = set_entry(updated, entry["key"], verification=result.as_block(),
                            **({"status": "verified"} if result.admissible else {}))
    return updated, results
