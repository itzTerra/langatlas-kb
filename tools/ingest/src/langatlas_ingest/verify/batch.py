from dataclasses import dataclass
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.goldens.items import ADMITTING_VERDICTS
from langatlas_ingest.paths import GOLDEN_CANARIES_PATH
from langatlas_ingest.verify.inputs import CitationInput, ClaimInput
from langatlas_ingest.verify.pipeline import verify_pair
from langatlas_ingest.verify.verdicts import PairVerdict

_yaml = YAML(typ="safe")


@dataclass(frozen=True)
class BatchResult:
    """The outcome of one `verify_batch` run (D18/Section 6.2).

    A halted result deliberately carries no verdicts: once a canary has answered
    `supported`, nothing the batch would have produced is trustworthy, so there is
    nothing to report but the halt itself."""

    verdicts: tuple[PairVerdict, ...] = ()
    halted: bool = False
    halt_reason: str = ""
    canaries_run: int = 0

    def to_markdown(self) -> str:
        counts: dict[str, int] = {}
        for verdict in self.verdicts:
            counts[verdict.verdict] = counts.get(verdict.verdict, 0) + 1
        lines = ["# Verification batch", "",
                 f"- pairs: {len(self.verdicts)}",
                 f"- canaries run: {self.canaries_run}",
                 f"- halted: {self.halted}"]
        if self.halt_reason:
            lines.append(f"- halt reason: {self.halt_reason}")
        lines += ["", "| verdict | pairs |", "|---|---|"]
        lines += [f"| {name} | {count} |" for name, count in sorted(counts.items())]
        return "\n".join(lines) + "\n"


def load_canary_ids(path: Path | None = None) -> list[str]:
    """Load Section 6.2's per-batch canary list.

    @param path - defaults to the committed `GOLDEN_CANARIES_PATH`

    @returns the canary item ids; empty (not an error) when the file is missing or its
        list is still empty, e.g. before Task 18 fills it in
    """
    path = Path(path or GOLDEN_CANARIES_PATH)
    if not path.exists():
        return []
    return list((_yaml.load(path.read_text()) or {}).get("canaries") or [])


def run_canaries(ctx, conn, *, config, deps, canary_ids, items=None) -> list[str]:
    """Ask the verifier a handful of known-bad questions before the batch starts.

    @param items - loaded `VerifierItem`s; None loads the committed golden set

    @returns the ids of canaries that wrongly came back admitting (empty is the good case)
    """
    if not canary_ids:
        return []
    if items is None:
        from langatlas_ingest.goldens.loader import load_verifier_items

        items = load_verifier_items()
    by_id = {item.id: item for item in items}

    passed = []
    for item_id in canary_ids:
        item = by_id.get(item_id)
        if item is None:
            # A canary naming an item that no longer exists is a configuration error, not
            # a silent skip: the batch would otherwise run with fewer guards than it says.
            raise KeyError(f"canary {item_id!r} is not in the committed golden set")
        claim = ClaimInput(fact_id=item.claim.fact_id, claim=item.claim.text,
                           since=item.claim.since, status=item.claim.status,
                           absence_scope=item.claim.absence_scope,
                           feature_aliases=item.claim.feature_aliases)
        citation = CitationInput(item.citation.source, item.citation.locator,
                                 item.citation.quote)
        verdict = verify_pair(ctx, conn, claim=claim, citation=citation, config=config,
                              deps=deps)
        if verdict.verdict in ADMITTING_VERDICTS:
            passed.append(item_id)
    return passed


def verify_batch(ctx, conn, work, *, config: IngestConfig | None = None, deps=None,
                 queue=None, canary_ids=None) -> BatchResult:
    """Verify many (claim, citation) pairs under one transcript (D18).

    One transcript per batch, per-claim `#msg-N` anchors in the manifest, so each fact's
    "AI chat" link lands on its own exchange rather than the top of a 4,000-pair run.

    A pair whose verification raises is recorded as `source-unavailable` rather than
    aborting: a provider outage mid-batch must leave a legible partial result and an
    honest false reject, not lose every verdict computed so far. A **canary** passing is
    the one thing that does halt.

    @param work - a sequence of (ClaimInput, CitationInput)
    @param canary_ids - None loads the committed canary list; [] disables the stage

    @returns the batch's verdicts, or an empty halted result when a canary passed
    """
    config = config or IngestConfig.load()
    canary_ids = load_canary_ids() if canary_ids is None else list(canary_ids)

    passed = run_canaries(ctx, conn, config=config, deps=deps, canary_ids=canary_ids)
    if passed:
        result = BatchResult(halted=True, canaries_run=len(canary_ids),
                             halt_reason=f"canaries passed: {', '.join(passed)}")
        ctx.writer.append(role="assistant", content=result.to_markdown(),
                          flags=["verification:halted"])
        return result

    verdicts = []
    for claim, citation in work:
        # Mint this pair's transcript slot up front: appending first is what actually
        # advances `ctx.writer.seq`, unlike reading `ctx.writer.seq + 1` before anything
        # has been written, which stays pinned to the same value for every pair in the
        # batch. `verify_pair`'s stage-3 calls (via `ctx.complete`/`CallRecorder`) do
        # write the real exchange to this same writer, but *after* this placeholder —
        # so the anchor below points one entry before the actual exchange, and can't
        # disambiguate among multiple completions on an escalated/second-opinion pair;
        # closing that needs Task 14's `anchor` parameter to be derived from the
        # completion's own seq instead of supplied in, which is out of this task's scope.
        entry = ctx.writer.append(
            role="user",
            content=f"Verifying {claim.fact_id} against {citation.source_id}"
                    f" {citation.locator}",
            flags=["verification:pair"])
        anchor = f"{ctx.run_id}#msg-{entry.seq}"
        try:
            verdict = verify_pair(ctx, conn, claim=claim, citation=citation,
                                  config=config, deps=deps, queue=queue, anchor=anchor)
        except Exception as exc:                     # noqa: BLE001 — see docstring
            verdict = PairVerdict(fact_id=claim.fact_id, source_id=citation.source_id,
                                  locator=citation.locator, verdict="source-unavailable",
                                  run_id=ctx.run_id, anchor=anchor,
                                  detail=f"error:{type(exc).__name__}: {exc}")
        verdicts.append(verdict)
        ctx.manifest.msg_anchors[claim.fact_id] = entry.seq

    result = BatchResult(verdicts=tuple(verdicts), canaries_run=len(canary_ids))
    ctx.writer.append(role="assistant", content=result.to_markdown(),
                      flags=["verification:batch"])
    return result
