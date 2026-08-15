import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.errors import GoldenEntryInvalid
from langatlas_ingest.paths import GOLDEN_RETRIEVAL_DIR
from langatlas_ingest.search import SourceSearch

_yaml = YAML(typ="safe")


@dataclass
class EvalResult:
    """Section 8.6's metric set, minus the ones only a multi-model benchmark run needs
    (indexing throughput, storage) — Stage 2's D22 harness adds those around this."""

    queries: int = 0
    recall_at_5: float | None = None
    mrr: float | None = None
    ndcg_at_10: float | None = None
    latency_p50_ms: float | None = None
    per_query: list[dict] = field(default_factory=list)
    # A missing golden directory (typo'd --golden-dir, moved directory) must not read the
    # same as `GOLDEN_RETRIEVAL_DIR` legitimately being empty pre-Stage-2 — see run_eval.
    golden_dir_missing: bool = False

    def to_markdown(self) -> str:
        if not self.queries:
            if self.golden_dir_missing:
                return ("# Retrieval eval\n\nWARNING: golden directory not found (not "
                        "just empty) — check the path; this looks like a typo or a "
                        "moved directory rather than the genuinely-empty pre-Stage-2 "
                        "state.\n")
            return ("# Retrieval eval\n\nNo golden queries found. Stage 2 authors these "
                    "during the corpus QA skims (Section 8.6).\n")
        return ("# Retrieval eval\n\n"
                f"- queries: {self.queries}\n"
                f"- Recall@5: {self.recall_at_5:.3f}\n"
                f"- MRR: {self.mrr:.3f}\n"
                f"- nDCG@10: {self.ndcg_at_10:.3f}\n"
                f"- latency p50: {self.latency_p50_ms:.0f} ms\n")


def _load(golden_dir: Path) -> list[dict]:
    entries: list[dict] = []
    for path in sorted(Path(golden_dir).glob("*.yaml")):
        if path.name == "queries.example.yaml":     # format documentation, not data
            continue
        entries.extend((_yaml.load(path.read_text()) or {}).get("queries") or [])
    return entries


def _validate(entry: dict) -> None:
    has_chunks = bool(entry.get("expected_chunks"))
    has_sources = bool(entry.get("expected_sources"))
    if not has_chunks and not has_sources:
        raise GoldenEntryInvalid(entry.get("id"), "has neither `expected_chunks` nor"
                                 " `expected_sources` set; every entry needs exactly one")
    if has_chunks and has_sources:
        # `_score` builds recall@5/nDCG's denominator from `expected_chunks` alone, but
        # `_relevant` (used to build ranking flags) also matches on `expected_sources` —
        # so a dual-key entry lets source-only hits inflate a chunk-denominator fraction
        # above 1.0. Rather than invent a union semantics nobody asked for ("this chunk,
        # or anything from this source"), an entry declares exactly one expectation kind.
        raise GoldenEntryInvalid(entry.get("id"), "sets both `expected_chunks` and"
                                 " `expected_sources`; each entry may declare exactly one"
                                 " expectation kind, not both")


def _relevant(entry: dict, chunk) -> bool:
    return (chunk.chunk_id in (entry.get("expected_chunks") or [])
            or chunk.source_id in (entry.get("expected_sources") or []))


def _score(entry: dict, hits: list) -> tuple[float, float, float, int | None]:
    """Score one query's ranked hits against its golden entry.

    `expected_chunks` gets true set recall — |relevant found in top-5| / |relevant
    total| — because the entry declares exactly which chunks count and how many there
    are, so both halves of the fraction are known. `expected_sources` keeps hit-rate
    semantics (did *any* top-5 hit come from a listed source) because a source-level
    entry never declares how many of that source's chunks are "relevant" — there is no
    trustworthy denominator to divide by, so the honest choice is a fraction that never
    claims more precision than the golden entry actually encodes.

    nDCG@10's ideal ranking (IDCG) mirrors the same split: for `expected_chunks` it is
    built from the *declared* relevant count (capped at 10, the standard nDCG@10
    convention), so a query that finds only 1 of 5 relevant chunks cannot score a false
    1.000 the way an IDCG built from what-was-found would. For `expected_sources` there
    is still no declared count, so IDCG falls back to what was retrieved — the same
    approximation, but now scoped to the one case with no better option instead of
    silently applied everywhere.
    """
    flags = [_relevant(entry, hit.chunk) for hit in hits]
    expected_chunks = entry.get("expected_chunks")

    if expected_chunks:
        relevant_ids = set(expected_chunks)
        found_at_5 = {hit.chunk.chunk_id for hit, flag in zip(hits[:5], flags[:5]) if flag}
        recall5 = len(found_at_5) / len(relevant_ids)
        idcg_count = min(len(relevant_ids), 10)
    else:
        recall5 = 1.0 if any(flags[:5]) else 0.0
        idcg_count = min(sum(flags[:10]), 10)

    first = next((index for index, flag in enumerate(flags) if flag), None)
    reciprocal_rank = 1.0 / (first + 1) if first is not None else 0.0
    dcg = sum(1.0 / math.log2(index + 2) for index, flag in enumerate(flags[:10]) if flag)
    ideal = sum(1.0 / math.log2(index + 2) for index in range(idcg_count))
    ndcg = dcg / ideal if ideal else 0.0
    return recall5, reciprocal_rank, ndcg, first


def run_eval(conn, ctx, *, golden_dir: Path | None = None,
             config: IngestConfig | None = None, rerank: bool | None = None) -> EvalResult:
    """`rerank` is threaded through to `SourceSearch` (None leaves the decision to
    `models.rerank_default_on`, exactly as the CLI's `--no-rerank` opt-out does).
    §8.6 asks for a rerank-vs-no-rerank comparison, which this harness could not perform
    at all while it always constructed the search with the configured default — and the
    no-rerank arm is also the cheap one: with reranking on, a 60-query golden set spends
    a completion round-trip per 8 candidates per query."""
    config = config or IngestConfig.load()
    golden_dir = golden_dir or GOLDEN_RETRIEVAL_DIR
    entries = _load(golden_dir)
    for entry in entries:
        _validate(entry)
    if not entries:
        return EvalResult(golden_dir_missing=not Path(golden_dir).is_dir())

    search = SourceSearch(conn, ctx, config=config, rerank=rerank)
    recalls, reciprocals, gains, latencies, per_query = [], [], [], [], []
    for entry in entries:
        began = time.monotonic()
        hits = search.search(entry["query"], k=10)
        latencies.append((time.monotonic() - began) * 1000)
        recall5, reciprocal_rank, ndcg, first = _score(entry, hits)
        recalls.append(recall5)
        reciprocals.append(reciprocal_rank)
        gains.append(ndcg)
        per_query.append({"id": entry.get("id"), "band": entry.get("band"),
                          "hit_rank": None if first is None else first + 1})

    mean = lambda values: sum(values) / len(values)
    return EvalResult(queries=len(entries), recall_at_5=mean(recalls), mrr=mean(reciprocals),
                      ndcg_at_10=mean(gains),
                      latency_p50_ms=sorted(latencies)[len(latencies) // 2],
                      per_query=per_query)
