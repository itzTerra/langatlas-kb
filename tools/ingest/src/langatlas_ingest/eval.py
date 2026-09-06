import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence
from ruamel.yaml import YAML
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.errors import GoldenEntryInvalid
from langatlas_ingest.paths import GOLDEN_RETRIEVAL_DIR
from langatlas_ingest.search import SourceSearch

_yaml = YAML(typ="safe")

# Recall@5 is §8.1's operating k. Recall@50 is §8.6's pre-rerank pool measurement — the
# same number, read at the depth the reranker actually receives.
_RECALL_CUTOFFS = (5, 50)


@dataclass
class EvalResult:
    """Section 8.6's metric set, minus the ones only a multi-model benchmark run needs
    (indexing throughput, storage) — Stage 2C's D22 harness adds those around this."""

    queries: int = 0
    recall_at_5: float | None = None
    mrr: float | None = None
    ndcg_at_10: float | None = None
    # §8.6's pre-rerank pool measurement. None (never 0.0) below depth 50: an unmeasured
    # metric and a measured zero are different findings, and a benchmark table that
    # conflated them would read as a catastrophic arm rather than a shallow run.
    recall_at_50: float | None = None
    latency_p50_ms: float | None = None
    per_query: list[dict] = field(default_factory=list)
    # A missing golden directory (typo'd --golden-dir, moved directory) must not read the
    # same as `GOLDEN_RETRIEVAL_DIR` legitimately being empty pre-Stage-2 — see run_eval.
    golden_dir_missing: bool = False
    # Queries whose expected sources are not all in the corpus under test. Counted, never
    # scored: a pilot corpus holding 4 of the golden set's 12 sources would otherwise
    # measure its own size instead of the model.
    skipped_queries: int = 0

    def to_markdown(self) -> str:
        if not self.queries:
            if self.golden_dir_missing:
                return ("# Retrieval eval\n\nWARNING: golden directory not found (not "
                        "just empty) — check the path; this looks like a typo or a "
                        "moved directory rather than the genuinely-empty pre-Stage-2 "
                        "state.\n")
            if self.skipped_queries:
                return (f"# Retrieval eval\n\nWARNING: all {self.skipped_queries} golden "
                        "queries were skipped — none of their expected sources are in "
                        "this corpus. Check `corpus_sources`.\n")
            return ("# Retrieval eval\n\nNo golden queries found. Stage 2 authors these "
                    "during the corpus QA skims (Section 8.6).\n")
        recall50 = "n/a" if self.recall_at_50 is None else f"{self.recall_at_50:.3f}"
        return ("# Retrieval eval\n\n"
                f"- queries: {self.queries} (skipped: {self.skipped_queries})\n"
                f"- Recall@5: {self.recall_at_5:.3f}\n"
                f"- Recall@50 (pre-rerank pool): {recall50}\n"
                f"- MRR: {self.mrr:.3f}\n"
                f"- nDCG@10: {self.ndcg_at_10:.3f}\n"
                f"- latency p50: {self.latency_p50_ms:.0f} ms\n")

    def as_dict(self) -> dict:
        """The arm-result payload. Plain JSON types only — a committed benchmark result
        has to stay readable in a diff five years from now."""
        return {"queries": self.queries, "skipped_queries": self.skipped_queries,
                "recall_at_5": self.recall_at_5, "recall_at_50": self.recall_at_50,
                "mrr": self.mrr, "ndcg_at_10": self.ndcg_at_10,
                "latency_p50_ms": self.latency_p50_ms, "per_query": self.per_query}


def load_entries(golden_dir: Path) -> list[dict]:
    entries: list[dict] = []
    for path in sorted(Path(golden_dir).glob("*.yaml")):
        if path.name == "queries.example.yaml":     # format documentation, not data
            continue
        entries.extend((_yaml.load(path.read_text()) or {}).get("queries") or [])
    return entries


def expected_sources_of(entry: dict) -> set[str]:
    """Which sources a query needs present to be answerable at all — the source half of
    every `expected_chunks` id, plus every `expected_sources` entry."""
    return ({chunk_id.split("#", 1)[0] for chunk_id in entry.get("expected_chunks") or []}
            | set(entry.get("expected_sources") or []))


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


def _score(entry: dict, hits: list, *, relevant=_relevant
          ) -> tuple[dict, float, float, int | None]:
    """Score one query's ranked hits against its golden entry.

    `expected_chunks` gets true set recall — |relevant found in top-k| / |relevant
    total| — because the entry declares exactly which chunks count and how many there
    are, so both halves of the fraction are known. `expected_sources` keeps hit-rate
    semantics (did *any* top-k hit come from a listed source) because a source-level
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

    `relevant(entry, chunk) -> bool` is injected rather than hardcoded so the chunk-size
    axis can score a re-chunked corpus, where the golden set's chunk ids do not exist by
    construction, against document spans instead (see `benchmark/relevance.py`). The
    default is chunk-id/source-id equality — exactly what it always was.

    For `expected_chunks`, recall's numerator is the number of *distinct* expected
    chunks covered by at least one hit, not the number of relevant hits — under the
    span-overlap relevance the chunk-size axis injects, several differently-chunked
    retrieved candidates can all overlap the same one golden span, and counting each as
    a separate "found" would inflate recall past what distinct coverage actually shows
    (it would still happen to land <= 1.0 for the common single-expected-chunk case,
    which is why this was invisible until an entry declares more than one). Coverage per
    expected id is checked by re-asking `relevant` with that one id substituted in for
    the entry's `expected_chunks` — the default equality predicate already keys off
    exactly that field, and `make_span_relevance` resolves spans by chunk id for the
    same reason.
    """
    flags = [relevant(entry, hit.chunk) for hit in hits]
    expected_chunks = entry.get("expected_chunks")
    expected_ids = list(dict.fromkeys(expected_chunks)) if expected_chunks else []
    recalls: dict[int, float] = {}

    for cutoff in _RECALL_CUTOFFS:
        if cutoff > len(hits) and cutoff != _RECALL_CUTOFFS[0]:
            # Not measured at a depth the run never retrieved to.
            continue
        if expected_chunks:
            window = hits[:cutoff]
            covered = sum(
                1 for expected_id in expected_ids
                if any(relevant({**entry, "expected_chunks": [expected_id]}, hit.chunk)
                      for hit in window))
            recalls[cutoff] = min(1.0, covered / len(expected_ids))
        else:
            recalls[cutoff] = 1.0 if any(flags[:cutoff]) else 0.0

    idcg_count = (min(len(set(expected_chunks)), 10) if expected_chunks
                  else min(sum(flags[:10]), 10))
    first = next((index for index, flag in enumerate(flags) if flag), None)
    reciprocal_rank = 1.0 / (first + 1) if first is not None else 0.0
    dcg = sum(1.0 / math.log2(index + 2) for index, flag in enumerate(flags[:10]) if flag)
    ideal = sum(1.0 / math.log2(index + 2) for index in range(idcg_count))
    ndcg = dcg / ideal if ideal else 0.0
    return recalls, reciprocal_rank, ndcg, first


def run_eval(conn, ctx, *, golden_dir: Path | None = None,
             config: IngestConfig | None = None, rerank: bool | None = None,
             depth: int = 10, mode: str | None = None,
             corpus_sources: Sequence[str] | None = None,
             relevance=None, search=None) -> EvalResult:
    """`rerank`, `mode` and `depth` are the three §8.6 variant axes, threaded through to
    `SourceSearch` (rerank=None leaves the decision to `models.rerank_default_on`,
    exactly as the CLI's `--no-rerank` opt-out does; mode=None likewise defers to
    `retrieval.mode`). `depth` is the k requested per query: 10 for the ordinary eval,
    50 for §8.6's pre-rerank pool measurement.

    `corpus_sources`, when given, scopes the run to golden queries whose expected
    sources are entirely covered by the corpus under test — everything else is skipped
    and counted, never scored as a miss, since a pilot corpus that only ingests a few
    sources cannot answer queries expecting the rest.

    `relevance` is injectable so the chunk-size axis can score a re-chunked corpus,
    where the golden set's chunk ids do not exist by construction, against document
    spans instead of chunk-id equality (see `_score`).

    `search` is injectable so a benchmark arm builds one search object with its own
    model and mode instead of this function re-deriving it from config — and so a metric
    test can run with no database at all.
    """
    config = config or IngestConfig.load()
    golden_dir = golden_dir or GOLDEN_RETRIEVAL_DIR
    entries = load_entries(golden_dir)
    for entry in entries:
        _validate(entry)
    if not entries:
        return EvalResult(golden_dir_missing=not Path(golden_dir).is_dir())

    relevant = relevance or _relevant
    available = set(corpus_sources) if corpus_sources is not None else None
    if search is None:
        search = SourceSearch(conn, ctx, config=config, rerank=rerank, mode=mode)

    recalls: dict[int, list[float]] = {cutoff: [] for cutoff in _RECALL_CUTOFFS}
    reciprocals, gains, latencies, per_query = [], [], [], []
    skipped = 0
    for entry in entries:
        if available is not None and not expected_sources_of(entry) <= available:
            skipped += 1
            per_query.append({"id": entry.get("id"), "band": entry.get("band"),
                              "hit_rank": None, "skipped": True})
            continue
        began = time.monotonic()
        hits = search.search(entry["query"], k=depth)
        latencies.append((time.monotonic() - began) * 1000)
        scored, reciprocal_rank, ndcg, first = _score(entry, hits, relevant=relevant)
        for cutoff, value in scored.items():
            recalls[cutoff].append(value)
        reciprocals.append(reciprocal_rank)
        gains.append(ndcg)
        per_query.append({"id": entry.get("id"), "band": entry.get("band"),
                          "hit_rank": None if first is None else first + 1,
                          "skipped": False})

    if not reciprocals:
        return EvalResult(per_query=per_query, skipped_queries=skipped)

    mean = lambda values: sum(values) / len(values)
    return EvalResult(
        queries=len(reciprocals),
        recall_at_5=mean(recalls[5]),
        recall_at_50=mean(recalls[50]) if recalls[50] and depth >= 50 else None,
        mrr=mean(reciprocals), ndcg_at_10=mean(gains),
        latency_p50_ms=sorted(latencies)[len(latencies) // 2],
        per_query=per_query, skipped_queries=skipped)
