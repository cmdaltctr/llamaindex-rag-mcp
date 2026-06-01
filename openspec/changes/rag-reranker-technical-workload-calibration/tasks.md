## 1. Experiment planning

- [x] 1.1 Create `experiments/10-reranker-technical-workload-calibration-<date>/protocol.md` with hypotheses, corpus, cell matrix, pass gates, and interpretation rules.
- [x] 1.2 Reuse the FreshStack LangChain corpus/export from Experiment 9a when available, or regenerate a deterministic ≥10,000-parent subset with the same qrels-plus-distractors method.
- [x] 1.3 Define query partitions for identifier-heavy, semantic, and continuity queries without relying on Stack Overflow tags alone.
- [x] 1.4 Define reranker policies to compare: off, current default, at least one gentler pool, and any feasible alternative ONNX reranker model.

## 2. Runner implementation

- [x] 2.1 Implement `run_eval.py` with checkpoint/resume from the start; save after every completed cell and write logs to `output/`.
- [x] 2.2 Ensure each cell records raw per-query results, Coverage@20, Recall@50, alpha-nDCG@10, Hit@10, MRR@10, latency, and reranker diagnostics.
- [x] 2.3 Assert the active retrieval implementation exposes the required `hybrid` and reranker controls before running cells.
- [x] 2.4 Keep candidate-pool semantics consistent across cells so dense and hybrid comparisons are fair.

## 3. Evaluation

- [ ] 3.1 Run the full cell matrix on the realistic technical corpus.
- [ ] 3.2 Summarise results by retrieval mode, reranker policy, and query category.
- [ ] 3.3 Identify whether reranking helps, hurts, or is neutral for technical documentation.
- [ ] 3.4 Inspect examples where reranking discards BM25/RRF-recovered relevant documents.

## 4. Decision and documentation

- [ ] 4.1 Write `results.md` with a plain-English recommendation for `RERANK_ENABLED`, pool sizing, and any hybrid-specific reranker policy.
- [ ] 4.2 If a default changes, update or create the appropriate ADR.
- [ ] 4.3 If no current reranker policy works, document reranking as opt-in for technical/hybrid workloads and propose model research as a separate follow-up.
- [ ] 4.4 Validate OpenSpec and run targeted retrieval/reranker tests before implementation changes.
