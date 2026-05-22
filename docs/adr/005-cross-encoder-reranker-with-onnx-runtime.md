# ADR-005: Cross-Encoder Reranker with ONNX Runtime

**Date:** 2026-05-11
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Git Commits:** `5594176`, `9a1b310`

## Context

Vector cosine similarity (bi-encoder) is fast but can misrank results when the
query and document use different vocabulary or when a document covers multiple
topics. Experiment data showed that vector-only search achieved 87.5% accuracy
(7/8 queries correct), with the failure case being a cross-topic entity lookup
("What is the Colosseum?" where the relevant chunk was primarily about Rome).

A cross-encoder reranker jointly evaluates (query, document) pairs and produces
a more accurate relevance score. However, typical reranker implementations
depend on PyTorch — a heavy dependency (~2 GB) unsuitable for a lightweight
local tool.

## Decision

Implement an optional **cross-encoder reranker** using **pure ONNX Runtime**
(no PyTorch at runtime).

- Model: `cross-encoder/ms-marco-MiniLM-L-6-v2` (~23 MB quantised ONNX)
- Platform-aware variant selection: `model_qint8_arm64.onnx` on ARM64,
  `model.onnx` (fp32) as fallback
- ONNX Runtime for inference (`CPUExecutionProvider` only)
- Raw logit outputs normalised to (0, 1) via sigmoid transform
- Singleton pattern: model loaded once, reused across calls
- Graceful fallback: if loading fails, returns un-reranked results
- **÷30 threshold auto-scaling**: when `rerank=True`, the user-supplied
  `similarity_threshold` is divided by 30 because cross-encoder sigmoid
  scores occupy a much lower range than cosine similarity. Calibrated from
  experiment data (strong matches: 0.79–1.0, weak correct: 0.015, noise: < 0.003).

## Consequences

### Positive
- 100% accuracy (8/8 queries) in experiments — the reranker fixed the only
  failure case
- Lightweight: ~23 MB ONNX model vs ~2 GB PyTorch dependency
- Fully local inference; no API calls after initial model download
- Graceful degradation: server never crashes due to reranker issues
- The ÷30 auto-scaling hides score-range differences from users

### Negative
- Adds ~7 seconds cold-start latency on first query (model loading)
- ~3× latency increase per query (30 ms vector-only vs 120 ms with reranker)
- Additional dependencies: `onnxruntime`, `transformers` (tokenizer only),
  `huggingface-hub`
- The ÷30 scaling factor is empirically calibrated, not mathematically derived —
  may need adjustment for different reranker models

### Neutral
- Reranker is disabled by default (`RERANK_ENABLED=false`); users opt in
- The singleton pattern requires test teardown to reset `_instance = None`

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **PyTorch-based reranker** | ~2 GB dependency; violates "no PyTorch at runtime" constraint |
| **Cohere/Jina reranker API** | Requires cloud API key; violates fully-local constraint |
| **No reranker at all** | 87.5% accuracy insufficient for precision-critical use cases |
| **Sentence-transformers cross-encoder** | Pulls in PyTorch as a transitive dependency |
| **BM25 hybrid search** | Does not solve the semantic misranking problem |

## References

- `src/rag_mcp/reranker.py` — `CrossEncoderReranker` singleton with ONNX inference
- `src/rag_mcp/retrieval.py` — `_effective_threshold()` for ÷30 auto-scaling
- `experiments/reranker-threshold-calibration-2026-05-12/` — experiment data and analysis justifying the design
