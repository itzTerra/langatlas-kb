import json
from dataclasses import dataclass
from langatlas_ingest.benchmark.arms import Arm, Matrix
from langatlas_ingest.benchmark.runner import ArmResult
from langatlas_ingest.errors import IncompleteMatrix


@dataclass(frozen=True)
class Verdict:
    """§8.6's per-table verdict record. `table` is explicit because the rules are
    per-table by design: the fact index (§8.3/D62) runs its own benchmark at Stage 5 and
    may legitimately choose a different model."""

    table: str
    incumbent: str
    model: str
    dimensions: int
    index_type: str
    mode: str
    rerank: bool
    chunk_target_tokens: int
    chunk_max_tokens: int
    pilot_sources: tuple[str, ...]
    queries_scored: int
    moved: bool
    rationale: tuple[str, ...]

    def to_markdown(self) -> str:
        lines = [f"# D22 verdict — {self.table}", "",
                 f"- model: **{self.model}** ({self.dimensions}-dim)",
                 f"- index type: {self.index_type}",
                 f"- retrieval mode: {self.mode}",
                 f"- reranker default-on: {self.rerank}",
                 f"- chunking: target {self.chunk_target_tokens} /"
                 f" max {self.chunk_max_tokens} tokens",
                 f"- incumbent was: {self.incumbent}",
                 f"- configuration moved: {self.moved}",
                 f"- pilot: {', '.join(self.pilot_sources)}"
                 f" ({self.queries_scored} queries scored)", "",
                 "## Why", ""]
        lines += [f"- {line}" for line in self.rationale]
        lines += ["", "Recall figures come from a 4-source pilot: the distractor pool is "
                  "a fraction of production's, so they are comparative between arms, not "
                  "absolute predictions of production recall."]
        return "\n".join(lines) + "\n"

    def as_dict(self) -> dict:
        return {"table": self.table, "incumbent": self.incumbent, "model": self.model,
                "dimensions": self.dimensions, "index_type": self.index_type,
                "mode": self.mode, "rerank": self.rerank,
                "chunk_target_tokens": self.chunk_target_tokens,
                "chunk_max_tokens": self.chunk_max_tokens,
                "pilot_sources": list(self.pilot_sources),
                "queries_scored": self.queries_scored, "moved": self.moved,
                "rationale": list(self.rationale)}

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n"


def _require(results: dict[str, ArmResult], arms) -> None:
    missing = [arm.arm_id for arm in arms if arm.arm_id not in results]
    if missing:
        raise IncompleteMatrix(missing)


def _diff(a: float, b: float) -> float:
    """`a - b` for two percentage-point figures, rounded to kill float noise.

    Both operands started life as fractions (0.57) multiplied by 100 (`_pts` in
    runner.py), which is exactly the kind of arithmetic that leaves a difference like
    `0.57*100 - 0.55*100 == 1.9999999999999858` instead of `2.0`. §8.6's margins are
    stated to one decimal place at most, so rounding to 9 decimals discards only
    representation noise, never a real distinction the rules could depend on — and an
    unrounded diff would make an "exactly at the margin" boundary fail unpredictably
    depending on which two floats happened to be subtracted.
    """
    return round(a - b, 9)


def _arm_for(matrix: Matrix, model: str, mode: str, rerank: bool) -> Arm:
    for arm in matrix.primary:
        if (arm.embedding_model, arm.mode, arm.rerank) == (model, mode, rerank):
            return arm
    raise IncompleteMatrix([f"{model}/{mode}/rerank={rerank} is not in the matrix"])


def decide(results: dict[str, ArmResult], *, matrix: Matrix,
           index_type: str = "hnsw-halfvec-cosine") -> Verdict:
    """§8.6's decision rules, applied mechanically.

    Mechanical on purpose: a benchmark whose conclusion is read off a table by eye is a
    benchmark whose conclusion depends on who is looking. The developer's checkpoint is
    *adopting* this verdict, not deriving it — and if a rule produces a result that feels
    wrong, the argument to have is about the rule, in the spec, not about this run.
    """
    _require(results, matrix.primary)
    margins = matrix.margins
    models = sorted({arm.embedding_model for arm in matrix.primary})
    rationale: list[str] = []

    def recall5(model: str, mode: str, rerank: bool) -> float:
        value = results[_arm_for(matrix, model, mode, rerank).arm_id].recall_at_5_pts
        if value is None:
            raise IncompleteMatrix([f"{model}/{mode}/rerank={rerank} scored no queries"])
        return value

    def ndcg(model: str, mode: str, rerank: bool) -> float:
        value = results[_arm_for(matrix, model, mode, rerank).arm_id].ndcg_at_10_pts
        if value is None:
            raise IncompleteMatrix([f"{model}/{mode}/rerank={rerank} scored no queries"])
        return value

    # --- rule 1: the model -----------------------------------------------------------
    # Local-model precedence runs first (plan decision 3): a local model within
    # `local_match_recall5_pts` of the incumbent wins outright, even if some other
    # challenger would otherwise clear the `beat_incumbent_recall5_pts` bar by more.
    # Free-and-local is the preferred floor when close, so this check must not be
    # reordered after the beat-incumbent check below.
    incumbent_score = recall5(matrix.incumbent, "hybrid", True)
    locals_in_reach = sorted(
        ((recall5(model, "hybrid", True), model) for model in matrix.local_models
         if model in models
         and _diff(incumbent_score, recall5(model, "hybrid", True))
         <= margins.local_match_recall5_pts),
        reverse=True)
    challengers = sorted(
        ((recall5(model, "hybrid", True), model) for model in models
         if model != matrix.incumbent
         and _diff(recall5(model, "hybrid", True), incumbent_score)
         >= margins.beat_incumbent_recall5_pts),
        reverse=True)

    if locals_in_reach:
        score, chosen = locals_in_reach[0]
        rationale.append(
            f"local model {chosen} scored {score:.1f} pts Recall@5 against the"
            f" incumbent's {incumbent_score:.1f} — within the"
            f" {margins.local_match_recall5_pts:.0f}-point match rule, so free-and-local"
            " wins (§8.6)")
    elif challengers:
        score, chosen = challengers[0]
        rationale.append(
            f"{chosen} beat the incumbent {incumbent_score:.1f} -> {score:.1f} pts"
            f" Recall@5, clearing the {margins.beat_incumbent_recall5_pts:.0f}-point bar")
    else:
        chosen = matrix.incumbent
        best = max((recall5(model, "hybrid", True), model) for model in models
                   if model != matrix.incumbent)
        rationale.append(
            f"incumbent {chosen} stays at {incumbent_score:.1f} pts Recall@5; best"
            f" challenger {best[1]} reached {best[0]:.1f}, short of the"
            f" {margins.beat_incumbent_recall5_pts:.0f}-point bar, and no local model came"
            f" within {margins.local_match_recall5_pts:.0f}")

    # --- rule 2: the reranker --------------------------------------------------------
    rerank_gain = _diff(ndcg(chosen, "hybrid", True), ndcg(chosen, "hybrid", False))
    rerank = rerank_gain >= margins.rerank_min_ndcg_pts
    rationale.append(
        f"reranker adds {rerank_gain:+.1f} pts nDCG@10 on {chosen} — "
        + ("stays default-on" if rerank
           else f"below the {margins.rerank_min_ndcg_pts:.0f}-point bar, so default-off"))

    # --- rule 3: hybrid vs vector ----------------------------------------------------
    hybrid_gain = _diff(recall5(chosen, "hybrid", False), recall5(chosen, "vector", False))
    mode = "hybrid" if hybrid_gain >= margins.hybrid_min_recall5_pts else "vector"
    rationale.append(
        f"hybrid adds {hybrid_gain:+.1f} pts Recall@5 over vector-only on {chosen} — "
        + ("stays hybrid" if mode == "hybrid"
           else f"below the {margins.hybrid_min_recall5_pts:.0f}-point bar, so"
                " vector-only"))

    # --- rule 4: chunk size ----------------------------------------------------------
    # Scoped to the model this decide() run just chose, running hybrid+rerank — the
    # plan's decision 1 states the chunk-size comparison only against "the chosen
    # model, hybrid+rerank". Each secondary arm's gain is measured against the
    # primary's original hybrid+rerank Recall@5 (`baseline`, fixed before the loop),
    # not against a size that has already displaced it, so two secondary arms are
    # compared on the same footing rather than against each other.
    target, maximum = matrix.primary_chunk_size
    baseline = recall5(chosen, "hybrid", True)
    truncate = _arm_for(matrix, chosen, "hybrid", True).truncate
    best_gain = 0.0
    for arm in matrix.chunk_size_arms(chosen, truncate=truncate):
        result = results.get(arm.arm_id)
        if result is None or result.recall_at_5_pts is None:
            continue
        gain = _diff(result.recall_at_5_pts, baseline)
        if gain >= margins.chunk_size_min_recall5_pts and gain > best_gain:
            best_gain = gain
            target, maximum = arm.chunk_target_tokens, arm.chunk_max_tokens
            rationale.append(
                f"chunking at {arm.chunk_target_tokens} tokens gained {gain:+.1f} pts"
                f" Recall@5, clearing the"
                f" {margins.chunk_size_min_recall5_pts:.0f}-point bar")
    if (target, maximum) == matrix.primary_chunk_size:
        rationale.append(
            f"chunking stays at {target}/{maximum} tokens — no secondary arm cleared the"
            f" {margins.chunk_size_min_recall5_pts:.0f}-point bar")

    chosen_result = results[_arm_for(matrix, chosen, "hybrid", True).arm_id]
    moved = (chosen != matrix.incumbent or not rerank or mode != "hybrid"
             or (target, maximum) != matrix.primary_chunk_size)
    return Verdict(
        table="source-corpus", incumbent=matrix.incumbent, model=chosen,
        dimensions=chosen_result.index.dimensions, index_type=index_type, mode=mode,
        rerank=rerank, chunk_target_tokens=target, chunk_max_tokens=maximum,
        pilot_sources=tuple(matrix.pilot_sources),
        queries_scored=int(chosen_result.metrics.get("queries") or 0), moved=moved,
        rationale=tuple(rationale))
