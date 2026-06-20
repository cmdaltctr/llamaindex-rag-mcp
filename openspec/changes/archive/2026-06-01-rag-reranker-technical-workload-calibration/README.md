# rag-reranker-technical-workload-calibration

Evaluate reranker ON vs OFF, pool sizing, and model policy on realistic technical-document retrieval after Experiment 9a showed reranking erased hybrid first-stage gains.

## Outcome

Completed via Experiment 10: `experiments/10-reranker-technical-workload-calibration-2026-05-31/`.

The corrected interpretation is:

- Reranking with the current `cross-encoder/ms-marco-MiniLM-L-6-v2` model substantially underperformed rerank-off retrieval on the FreshStack LangChain technical workload.
- Hybrid BM25 without reranking was the best measured configuration: Coverage@20 0.738 vs 0.540 for hybrid rerank-on.
- The intended labelled `RERANK_MAX_FETCH` sweep (50/200/500) did not vary effective fetch size because `top_k=50` and `RERANK_FETCH_MULTIPLIER=10` forced all reranker-on cells to effective `fetch_k=500`.
- Therefore, current reranker policy is marked FAIL for technical workloads, while effective pool-size sensitivity remains INCONCLUSIVE.

## Decisions Produced

- Created ADR-019: `docs/adr/019-reranker-disabled-for-technical-workloads.md`.
- Marked ADR-018 as superseded by ADR-019.
- Updated `config.py` so `RERANK_ENABLED` defaults to `false`.
- Added policy knobs `RERANK_ENABLED_FOR_SEMANTIC` and `HARD_TECHNICAL_THRESHOLD`, with follow-up implementation tracked separately.
- Created follow-up OpenSpec change: `rag-semantic-technical-reranker-policy`.

## Archive Readiness

All planning, runner, evaluation, and decision-documentation tasks are complete. This change can be archived. The remaining semantic/technical policy implementation work is tracked by the follow-up OpenSpec change rather than this calibration change.
