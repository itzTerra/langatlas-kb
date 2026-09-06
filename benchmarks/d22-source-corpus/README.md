# D22 source-corpus embedding benchmark

The committed record behind `config/ingest.yaml`'s pinned `models.embedding`,
`models.embedding_dimensions`, `models.index_type`, `models.rerank_default_on`,
`retrieval.mode` and `chunking` values (spec §8.6, Stage 2C).

- `../../config/benchmark/d22-source-corpus.yaml` — the run matrix: pilot, candidates,
  variant axes, decision margins. Configuration the developer ratifies.
- `results/<arm_id>.json` — one file per measured arm. Also the runner's checkpoint: an
  arm whose file exists is skipped on re-invocation.
- `verdict.json` / `verdict.md` — the per-table verdict and the full arm table.

Results are committed while the embeddings they measure are not: the vectors are derived
data (D1/D15), but the measurement justifying a production setting is a research record.

## Re-running

```bash
docker compose up -d db
uv --directory tools/ingest run langatlas-sources bench-pilot            # confirm the pilot
uv --directory tools/ingest run langatlas-sources bench-build --drop     # 600/800 + parity
uv --directory tools/ingest run langatlas-sources bench-run              # the 18 primary arms
uv --directory tools/ingest run langatlas-sources bench-verdict          # read the verdict
```

The secondary chunk-size axis runs after the model is chosen, one chunk size at a time,
because each size is a different corpus:

```bash
uv --directory tools/ingest run langatlas-sources bench-build --drop \
    --chunk-target 400 --chunk-max 550
uv --directory tools/ingest run langatlas-sources bench-run --chunk-size-for <model>
```

`bench-run` is resumable: delete an arm's JSON (or pass `--force`) to re-measure it.

### Indexing-throughput caveat on the committed arm results

The `results/*.json` files committed here were generated before a post-merge fix to
`throughput_honest` (Stage 2C final-review findings I2/I3): the flag now also requires
that every chunk in the arm's corpus was embedded fresh during that arm's own run, not
just that no cache hit occurred. Each model's `hybrid` and `hybrid-rerank` arms share
their `vector` arm's embedding table (same model, same chunk size), so by the time those
two arms ran there was nothing left pending — they embedded nothing and their
`embed_seconds`/`chunks_per_second`/`truncated_chunks` numbers are artifacts of that,
not a measurement. Under the old logic this showed as `throughput_honest: true` with an
implausibly large `chunks_per_second`; the numbers themselves were not recomputed, so a
result file that still shows that pattern should be read as "not honestly measured"
regardless of what its own `throughput_honest` field says.

In practice, only each model's first-populated arm gives a real indexing-cost number —
typically `vector`, except `qwen3-embedding-4b`, whose embedding table was already
populated from production ingestion before this benchmark ran, so none of its arms
(including `vector`) measure a genuine cold embed. This caveat is about indexing-cost
and truncation numbers only: the verdict's actual model/mode/reranker/chunking choice,
which is driven by the retrieval metrics (recall/MRR/nDCG), is unaffected.

Recall figures come from a four-source pilot. They are comparative between arms, not
predictions of production recall — the distractor pool is a quarter of production's.

## What this benchmark does *not* decide

The fact index (`knowledge_embeddings`, §8.3/D62) runs its own benchmark: a proxy run late
in Stage 3 and the real re-run at sweep start in Stage 5. Verdicts are per table, and the
two indexes may legitimately choose different models. Debate-history retrieval is deferred
to v2.
