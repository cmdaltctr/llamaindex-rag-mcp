# Experiment 10 Results

This generated summary has been superseded by the corrected full report at:

[`../results.md`](../results.md)

Reason: the first generated report treated labelled `RERANK_MAX_FETCH` values
50/200/500 as distinct effective candidate pools. After audit, all reranker-on
cells used the same effective fetch size (`fetch_k=500`) because the evaluation
used `top_k=50` and `RERANK_FETCH_MULTIPLIER=10`.

Use these files for the current interpretation:

- Corrected report: [`../results.md`](../results.md)
- Raw per-query data: [`eval_results.json`](./eval_results.json)
- Regenerated aggregate summary: [`eval_results.summary.json`](./eval_results.summary.json)
