# Experiment 8a — Query Embedding Cache Full-Size Evaluation

This is a self-contained follow-up to Experiment 8.

Experiment 8 confirmed the cache works but used small traces and did not truly
disable the production cache in the cache-off cells. Experiment 8a fixes both
issues.

## Self-contained artefacts

- `corpus/` — copied from Exp 3; no symlink.
- `run_eval.py` — ingests corpus, generates traces if missing, then evaluates.
- `protocol.md` — full methodology.

## Run

```bash
cd experiments/8a-query-embedding-cache-fullsize-2026-05-29
uv run python run_eval.py --corpus ./corpus
```

The runner creates these traces if absent:

- `workload-warm.txt`: 50 distinct queries × 5 repeats = 250 calls.
- `workload-cold.txt`: 200 unique queries.
- `workload-agent-loop.txt`: 25 repeated agent-loop queries × 10 repeats = 250 calls.

## Main difference from Experiment 8

The runner monkey-patches `rag_mcp.retrieval._embed_query` for cache-disabled
cells, so cache-off really means every call embeds directly.
