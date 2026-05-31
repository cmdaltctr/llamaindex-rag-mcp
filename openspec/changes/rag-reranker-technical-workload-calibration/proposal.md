## Why

Experiment 9a (`experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/`) showed that hybrid BM25 + RRF improves first-stage retrieval on realistic technical documentation, but the current reranker policy erases that gain. On the 10,025-document FreshStack LangChain subset, hybrid without reranking was the best cell across Coverage@20, Recall@50, alpha-nDCG@10, Hit@10, and MRR@10. Both dense and hybrid retrieval degraded when `cross-encoder/ms-marco-MiniLM-L-6-v2` reranking was applied.

Experiment 5 calibrated reranker pool size on a tiny five-document fixture corpus. It proved the `(RERANK_MAX_FETCH=50, RERANK_FETCH_MULTIPLIER=10)` defaults were fast and non-regressing there, but it did not answer whether reranking helps realistic technical-document retrieval. We need a focused follow-up to decide whether reranking should stay on by default for technical corpora, use different pool sizing, use a different reranker model, or be disabled when hybrid retrieval is active.

## What Changes

- Add Experiment 10 to evaluate reranker ON vs OFF on a realistic technical-document corpus, reusing the FreshStack LangChain export when possible.
- Compare dense-only and hybrid BM25/RRF under multiple reranker policies: rerank off, current default, gentler candidate pools, and optionally alternative technical reranker models.
- Preserve the completed hybrid retrieval feature as opt-in; this change does not flip `HYBRID_ENABLED`.
- Produce a new recommendation for `RERANK_ENABLED`, `RERANK_MAX_FETCH`, `RERANK_FETCH_MULTIPLIER`, and any hybrid-specific reranker policy.

## Impact

- `experiments/10-reranker-technical-workload-calibration-<date>/` for protocol, runner, raw results, summary, and report.
- Potential follow-up changes to `src/rag_mcp/config.py` defaults only if the experiment supports them.
- Potential follow-up changes to `src/rag_mcp/retrieval.py` if policy becomes conditional (for example, rerank off for hybrid, two-stage rerank, or smaller candidate pool).
- ADR update or new ADR documenting any reranker default change.
