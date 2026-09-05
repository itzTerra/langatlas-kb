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

Recall figures come from a four-source pilot. They are comparative between arms, not
predictions of production recall — the distractor pool is a quarter of production's.

## What this benchmark does *not* decide

The fact index (`knowledge_embeddings`, §8.3/D62) runs its own benchmark: a proxy run late
in Stage 3 and the real re-run at sweep start in Stage 5. Verdicts are per table, and the
two indexes may legitimately choose different models. Debate-history retrieval is deferred
to v2.
