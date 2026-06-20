## Context

The current production-style retrieval profile enables the ONNX cross-encoder reranker by default. That default was supported by Qasper-style evidence retrieval in ADR-018 and by small-corpus pool sizing in Experiment 5. Experiment 9a exposed a different workload: technical documentation and Stack Overflow questions over FreshStack LangChain.

In that workload, the reranker did not behave as a harmless precision stage. It reduced Coverage@20 and Recall@50 for both dense-only and hybrid retrieval. The most plausible explanation is domain mismatch plus aggressive filtering: `cross-encoder/ms-marco-MiniLM-L-6-v2` is trained for general web passage ranking, not code identifiers, API names, errors, and technical documentation. When fed hundreds of technical candidates, it can discard relevant exact-match evidence that BM25/RRF found.

## Goals

- Measure whether reranking improves or harms realistic technical-document retrieval.
- Compare reranker OFF vs current default reranker policy under both dense-only and hybrid BM25/RRF retrieval.
- Test less aggressive pool policies and, if feasible, at least one technical-document reranker alternative.
- Produce a clear recommendation for technical workloads: keep reranking on, turn it off, change pool size, make it conditional, or replace the model.
- Keep the experiment reproducible with checkpoint/resume and logs from the start.

## Non-Goals

- Do not change hybrid retrieval implementation itself.
- Do not flip `HYBRID_ENABLED` in this change.
- Do not require cloud services or PyTorch runtime.
- Do not fine-tune a model in this change; fine-tuning may be a later follow-up if model evaluation shows it is needed.

## Candidate Experiment Matrix

Minimum cells:

| Retrieval mode | Reranker policy | Purpose |
| --- | --- | --- |
| dense-only | off | first-stage dense baseline |
| dense-only | current default | current production-style baseline |
| hybrid_bm25 | off | first-stage hybrid candidate |
| hybrid_bm25 | current default | current hybrid production-style candidate |
| dense-only | gentler pool | isolate pool-size effect |
| hybrid_bm25 | gentler pool | test whether hybrid gains survive reranking |

Optional cells:

- Alternative ONNX reranker model suitable for technical documentation.
- Two-stage reranking (for example, rerank top 100 but return top 50).
- Conditional policy: rerank semantic queries, skip rerank for identifier-heavy queries.

## Success Criteria

A changed reranker policy is acceptable only if it improves or preserves Coverage@20 and Recall@50 on realistic technical queries while keeping P95 latency within the existing Tier 3 budget. If no reranker policy beats rerank-off hybrid, the recommendation should be to disable reranking for technical/hybrid workloads or keep reranking opt-in there.
