from pathlib import Path
from ruamel.yaml import YAML
from langatlas_ingest.benchmark.arms import Matrix
from langatlas_ingest.benchmark.runner import ArmResult
from langatlas_ingest.benchmark.verdict import Verdict

# Round-trip loader: config/ingest.yaml's comments explain every knob, and a benchmark
# that pinned a model by deleting the documentation around it would be a bad trade.
_rt_yaml = YAML()
_rt_yaml.preserve_quotes = True


def _pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}"


def matrix_markdown(results: dict[str, ArmResult], *, matrix: Matrix) -> str:
    lines = ["# D22 source-corpus benchmark", "",
             f"Pilot: {', '.join(matrix.pilot_sources)}", "",
             "| arm | R@5 | R@50 | nDCG@10 | MRR | p50 ms | chunks/s | MB |"
             " truncated | notes |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for arm_id in sorted(results):
        result = results[arm_id]
        metrics, index = result.metrics, result.index
        notes = []
        if not index.throughput_honest:
            # Never quietly drop the number: report it and say why it cannot be ranked on.
            notes.append("cache-warm throughput")
        if metrics.get("skipped_queries"):
            notes.append(f"{metrics['skipped_queries']} queries out of corpus")
        truncated = (f"{index.truncated_chunks / index.chunks:.0%}"
                     if index.chunks else "n/a")
        rate = ("n/a" if index.chunks_per_second is None
                else f"{index.chunks_per_second:.1f}")
        lines.append(
            f"| {arm_id} | {_pct(metrics.get('recall_at_5'))} |"
            f" {_pct(metrics.get('recall_at_50'))} |"
            f" {_pct(metrics.get('ndcg_at_10'))} | {_pct(metrics.get('mrr'))} |"
            f" {metrics.get('latency_p50_ms') or 0:.0f} | {rate} |"
            f" {index.table_bytes / 1_048_576:.1f} | {truncated} |"
            f" {'; '.join(notes)} |")
    return "\n".join(lines) + "\n"


def write_verdict(verdict: Verdict, results: dict[str, ArmResult], *, matrix: Matrix,
                  root: Path) -> tuple[Path, Path]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    json_path, md_path = root / "verdict.json", root / "verdict.md"
    json_path.write_text(verdict.to_json())
    md_path.write_text(verdict.to_markdown() + "\n"
                       + matrix_markdown(results, matrix=matrix))
    return json_path, md_path


def pin_config(verdict: Verdict, *, config_path: Path, provider_config=None) -> list[str]:
    """Write the verdict's choices into config/ingest.yaml.

    The dimension is cross-checked against the capability table first and the write is
    refused on disagreement — a pinned dimension that does not match the model's real
    output would be caught later by `ensure_embedding_table`, but only after a full
    re-embed had already been attempted against the wrong table definition.
    """
    if provider_config is None:
        from langatlas_pipeline.config import ProviderConfig

        provider_config = ProviderConfig.load()
    measured = provider_config.embedding(verdict.model).dimensions
    if measured != verdict.dimensions:
        raise ValueError(
            f"{verdict.model}: the benchmark measured {verdict.dimensions} dimensions but"
            f" provider_capabilities.yaml records {measured}; re-probe before pinning")

    data = _rt_yaml.load(config_path.read_text())
    updates = [("models", "embedding", verdict.model),
               ("models", "embedding_dimensions", verdict.dimensions),
               ("models", "index_type", verdict.index_type),
               ("models", "rerank_default_on", verdict.rerank),
               ("retrieval", "mode", verdict.mode),
               ("chunking", "target_tokens", verdict.chunk_target_tokens),
               ("chunking", "max_tokens", verdict.chunk_max_tokens)]
    changed: list[str] = []
    for section, key, value in updates:
        if data[section].get(key) != value:
            changed.append(f"{section}.{key}: {data[section].get(key)!r} -> {value!r}")
            data[section][key] = value
    if changed:
        with config_path.open("w", encoding="utf-8") as fh:
            _rt_yaml.dump(data, fh)
    return changed
