# Reranker

The server includes an optional **cross-encoder reranker** that re-scores vector search results for significantly better retrieval precision. It uses `cross-encoder/ms-marco-MiniLM-L-6-v2` — a ~23 MB quantised ONNX model that runs locally via pure ONNX Runtime. No PyTorch, no `sentence-transformers`, no API keys.

## How it works

Without the reranker:

```
query → embed → cosine similarity → return top_k
```

With the reranker:

```
query → embed → cosine similarity (top_k × 2) → cross-encoder re-score → return top_k
```

The cross-encoder evaluates each (query, document) pair jointly, which is slower but much more accurate than cosine similarity alone. The vector search fetches `top_k × 2` candidates so the reranker has a meaningful pool to re-score.

## Threshold auto-scaling

Cross-encoder sigmoid scores occupy a much lower range than cosine similarity. Valid reranker results can score as low as 0.015, while cosine similarity rarely goes below 0.3 for relevant matches.

When `rerank=True`, the `similarity_threshold` is **automatically scaled down by 30×** so that a user-supplied value of 0.3 becomes 0.01. You always supply a threshold in cosine-similarity terms; the system handles the conversion transparently.

Calibrated from experiment data in `experiments/reranker-threshold-calibration-2026-05-12/`:

| Score range | Meaning |
|-------------|---------|
| 0.79–1.0 | Strong reranker match |
| ~0.015 | Weak but correct match |
| < 0.003 | Noise |

## Enabling

**Per-query** (recommended — call with `rerank=True`):

> "Search for quantum superposition, use reranking"

**Always on** (via `.env`):

```bash
RERANK_ENABLED=true
SIMILARITY_THRESHOLD=0.3   # optional default threshold
```

**CLI**:

```bash
rag-mcp search "machine learning" --rerank --threshold 0.3
```

## First-run download

The first time you call `search_documents` with `rerank=True`, the ~23 MB quantised ONNX model downloads from HuggingFace Hub and caches in `~/.cache/huggingface/`. On macOS ARM64, the `model_qint8_arm64.onnx` variant is used automatically. Subsequent calls use the cached model — it's a singleton, loaded once and reused across all calls.

## When to use

| Scenario | Recommendation |
|----------|---------------|
| Quick lookups, broad recall | `rerank=False` (default — faster) |
| Precision-critical answers | `rerank=True` |
| Filtering noise | `similarity_threshold=0.3` + `rerank=True` |
| Many similar results | `rerank=True` — breaks ties better |

## Fallback

If the reranker model fails to load (no internet for first download, corrupt cache, etc.), the server **gracefully falls back** to un-reranked vector search results. A warning appears in stderr logs. The server never crashes due to reranker issues. The next call retries loading automatically.
