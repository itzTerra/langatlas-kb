import os
from dataclasses import dataclass, replace
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_ingest.goldens.score import Thresholds
from langatlas_ingest.paths import INGEST_CONFIG_PATH

_yaml = YAML(typ="safe")


@dataclass(frozen=True)
class IngestConfig:
    chunk_target_tokens: int
    chunk_max_tokens: int
    chunk_overlap_tokens: int
    embedding_model: str
    reranker_model: str
    rerank_default_on: bool
    # Scaffolding for the D22 verdict pin — the runtime authority for the dimension is
    # still `provider_capabilities.yaml` and for the index still `ensure_embedding_table`;
    # these fields exist so `bench-verdict --write` has somewhere to record what it measured.
    embedding_dimensions: int | None
    index_type: str
    retrieval_k: int
    retrieval_candidates: int
    # Deliberately decoupled from `retrieval_candidates`: RRF fusion over a wide pool is
    # one SQL statement, but reranking is 1B's 8-documents-per-call completion client, so
    # the rerank pool is what actually costs sequential provider round-trips.
    rerank_candidates: int
    rrf_k: int
    relevance_floor: float
    retrieval_mode: str          # §8.6's variant axis: hybrid | vector | fts
    max_section_tokens: int
    pdf_backend: str
    dsn: str
    golden_candidate_model: str
    golden_thresholds: Thresholds
    verifier_entry_point: str | None
    controversy_assessor_entry_point: str | None

    @classmethod
    def load(cls, path: Path | None = None, *, overrides: dict | None = None) -> "IngestConfig":
        raw = _yaml.load((path or INGEST_CONFIG_PATH).read_text())
        chunking, models = raw["chunking"], raw["models"]
        retrieval, extraction = raw["retrieval"], raw["extraction"]
        # `.get` with defaults, not `raw[...]`: a config file predating this block is a
        # valid file, not a crash — the defaults are the ratified §6.2 numbers anyway.
        goldens = raw.get("goldens") or {}
        golden_thresholds = goldens.get("thresholds") or {}
        config = cls(
            chunk_target_tokens=int(chunking["target_tokens"]),
            chunk_max_tokens=int(chunking["max_tokens"]),
            chunk_overlap_tokens=int(chunking["overlap_tokens"]),
            embedding_model=models["embedding"],
            reranker_model=models["reranker"],
            rerank_default_on=bool(models["rerank_default_on"]),
            embedding_dimensions=(int(models["embedding_dimensions"])
                                  if models.get("embedding_dimensions") else None),
            index_type=models.get("index_type", "hnsw-halfvec-cosine"),
            retrieval_k=int(retrieval["k"]),
            retrieval_candidates=int(retrieval["candidates"]),
            rerank_candidates=int(retrieval["rerank_candidates"]),
            rrf_k=int(retrieval["rrf_k"]),
            relevance_floor=float(retrieval["relevance_floor"]),
            retrieval_mode=retrieval.get("mode", "hybrid"),
            max_section_tokens=int(retrieval["max_section_tokens"]),
            pdf_backend=extraction["pdf_backend"],
            # The DSN carries a password, so the env var has to win: CI and the
            # orchestrator (1E) both supply their own.
            dsn=os.environ.get("LANGATLAS_DSN") or raw["database"]["dsn"],
            golden_candidate_model=goldens.get("candidate_model", "kimi"),
            golden_thresholds=Thresholds(
                false_accept_max=float(golden_thresholds.get("false_accept_max", 0.02)),
                false_reject_max=float(golden_thresholds.get("false_reject_max", 0.10))),
            verifier_entry_point=goldens.get("verifier_entry_point"),
            controversy_assessor_entry_point=goldens.get(
                "controversy_assessor_entry_point"),
        )
        return replace(config, **overrides) if overrides else config
