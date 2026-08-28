# Experiment 10b Results: Corrected Reranker Pool-Size Sweep

**Recommendation:** Larger fetch_k pools DEGRADE quality (fetch_k=50 best at cov20=0.6141, fetch_k=500 worst at cov20=0.4655). Reranker dilution effect confirmed. Smaller pool sizes are better. ADR-019 (RERANK_ENABLED=false) validated — reranker hurts regardless of pool size. No config change.

## Corpus and setup

- Parent documents: None
- Embedding model: qwen3-embedding:0.6b
- RRF k: None
- Reranker model: cross-encoder/ms-marco-MiniLM-L-6-v2 (ONNX)
- Fetch_k sizes tested: None
- Post-ADR-021 config: MULTIPLIER=None, MAX_FETCH=None

## Cell metrics (all queries)

| Cell | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@10 | MRR@10 | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dense_only__fetch_k_50__rerank_true | 0.614 | 0.519 | 0.273 | 0.659 | 0.359 | 12114.5 |
| dense_only__fetch_k_100__rerank_true | 0.576 | 0.399 | 0.240 | 0.614 | 0.315 | 21125.0 |
| dense_only__fetch_k_200__rerank_true | 0.524 | 0.333 | 0.215 | 0.570 | 0.299 | 37230.3 |
| dense_only__fetch_k_500__rerank_true | 0.465 | 0.283 | 0.197 | 0.538 | 0.282 | 113655.2 |

## Pool-size comparison (dense-only, all queries)

| fetch_k | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@5 | Hit@10 | MRR@10 | P95 ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 0.614 | 0.519 | 0.273 | 0.520 | 0.659 | 0.359 | 12114.5 |
| 100 | 0.576 | 0.399 | 0.240 | 0.466 | 0.614 | 0.315 | 21125.0 |
| 200 | 0.524 | 0.333 | 0.215 | 0.439 | 0.570 | 0.299 | 37230.3 |
| 500 | 0.465 | 0.283 | 0.197 | 0.381 | 0.538 | 0.282 | 113655.2 |

## Pass gates

- **corpus_validity**: `{"value": 0, "pass": false}`
- **pool_sizes_distinct**: `{"value": [50, 100, 200, 500], "pass": true}`
- **pool_size_lift**: `{"value": -0.148601, "max_k_cov20": 0.4655, "min_k_cov20": 0.6141, "pass": false}`
- **diminishing_returns**: `{"value": -0.058221, "pass": true}`
- **best_fetch_k**: `{"fetch_k": 50, "coverage_at_20": 0.6141, "larger_pool_degrades": true}`
- **latency_guardrail**: `{"p95_min_ms": 12114.54, "p95_max_ms": 113655.22, "ratio": 9.3817, "pass": false}`

## Notes

This experiment uses the `fetch_k=` parameter on `search()` (TDR-005) to bypass
the `max(RERANK_MAX_FETCH, top_k × RERANK_FETCH_MULTIPLIER)` formula, producing
genuinely distinct pool sizes — the confound that voided Exp 10.
