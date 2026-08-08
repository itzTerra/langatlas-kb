import os
from dataclasses import dataclass, replace
from pathlib import Path
from ruamel.yaml import YAML
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
    retrieval_k: int
    retrieval_candidates: int
    rrf_k: int
    relevance_floor: float
    pdf_backend: str
    dsn: str

    @classmethod
    def load(cls, path: Path | None = None, *, overrides: dict | None = None) -> "IngestConfig":
        raw = _yaml.load((path or INGEST_CONFIG_PATH).read_text())
        chunking, models = raw["chunking"], raw["models"]
        retrieval, extraction = raw["retrieval"], raw["extraction"]
        config = cls(
            chunk_target_tokens=int(chunking["target_tokens"]),
            chunk_max_tokens=int(chunking["max_tokens"]),
            chunk_overlap_tokens=int(chunking["overlap_tokens"]),
            embedding_model=models["embedding"],
            reranker_model=models["reranker"],
            rerank_default_on=bool(models["rerank_default_on"]),
            retrieval_k=int(retrieval["k"]),
            retrieval_candidates=int(retrieval["candidates"]),
            rrf_k=int(retrieval["rrf_k"]),
            relevance_floor=float(retrieval["relevance_floor"]),
            pdf_backend=extraction["pdf_backend"],
            # The DSN carries a password, so the env var has to win: CI and the
            # orchestrator (1E) both supply their own.
            dsn=os.environ.get("LANGATLAS_DSN") or raw["database"]["dsn"],
        )
        return replace(config, **overrides) if overrides else config
