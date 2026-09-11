# Experiment 22 data locations

The large artefacts were relocated on 2026-09-07 so they survive worktree
cleanup. They are gitignored and intentionally live outside this repository.

## LanceDB index (6.6 GB)

Moved to:

```text
~/Development/DATA/omrg/experiments/exp22-lancedb
```

To rerun evaluation cells against the preserved baseline index, point
`LANCEDB_URI` (or `STORE_URI` in `run_eval.py`) at that path before running.
The index holds 32,631 chunks over 10,024 FreshStack files embedded with
`qwen/qwen3-embedding-4b` via OpenRouter.

## FreshStack corpus (116 MB)

Moved to:

```text
~/Development/DATA/omrg/experiments/freshstack-corpus
```

Contains `langchain/` (10,009 documents), `continuity/` (15 documents), and
`langchain_manifest.jsonl`. A copy of the manifest stays at
`corpus/langchain_manifest.jsonl` in this directory so `run_eval.py` works
unchanged. Stage 5 candidate builds should reuse this corpus instead of
re-exporting.

## What stays in this directory

Scripts, `plan.json`, qrels, ground truth, per-cell checkpoints
(`output/cells/*.json` hold the raw retrieved parent IDs per query), and
`results.md`. The checkpoints alone are sufficient to recompute every metric
without the index.
