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

When `rerank=True` **and reranking actually succeeds**, the `similarity_threshold` is **automatically scaled down by 30×** so that a user-supplied value of 0.3 becomes 0.01. You always supply a threshold in cosine-similarity terms; the system handles the conversion transparently.

The scaling follows the rerank *outcome*, not the request: if `rerank=True` but the reranker fails (see Fallback below), the returned scores are still raw cosine similarities, so the threshold is applied **unscaled**. Scaling an unscaled score range would make filtering roughly 30× too permissive on exactly the results that fell back to un-reranked.

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
RETRIEVAL__RERANK_ENABLED=true
RETRIEVAL__SIMILARITY_THRESHOLD=0.3   # optional default threshold
```

**CLI**:

```bash
rag-mcp search "machine learning" --rerank --threshold 0.3
```

## First-run download

The first time you call `search_documents` with `rerank=True`, the ~23 MB quantised ONNX model downloads from HuggingFace Hub and caches in `~/.cache/huggingface/`. On macOS ARM64, the `model_qint8_arm64.onnx` variant is used automatically. Subsequent calls use the cached model — it's a singleton, loaded once and reused across all calls.

> **Note:** CoreML is disabled by default (ADR-029) — it doesn't support the dynamic sequence lengths that cross-encoder tokenisation produces. CPU-only inference is used instead. Override with `RERANK_ONNX_PROVIDER=coreml` to experiment.

## When to use

| Scenario | Recommendation |
|----------|---------------|
| Quick lookups, broad recall | `rerank=False` (default — faster) |
| Precision-critical answers | `rerank=True` |
| Filtering noise | `similarity_threshold=0.3` + `rerank=True` |
| Many similar results | `rerank=True` — breaks ties better |

## Fallback

If the reranker model fails to load (no internet for first download, corrupt cache, etc.) or inference raises, the server **gracefully falls back** to un-reranked vector search results. The server never crashes due to reranker issues. The next call retries loading automatically.

**Failure escalation** (ADR-029 decision #3): each failure logs a warning as before, but the server tracks consecutive failures with the same error signature process-wide. Below 3 consecutive same-signature failures it logs at WARNING; at or above that threshold it logs at ERROR, so a persistent outage (like the 5-week CoreML incident in ADR-029) stops looking identical to an occasional transient hiccup in the logs. Any successful load or inference resets the counter.

**Diagnostics**: when `include_diagnostics=True`, the `rerank_reason` field on each result describes the reranker's own failure (e.g. `"inference failed: ..."` or `"model load failed: ..."`) rather than only the policy decision that requested reranking — so a broken reranker is distinguishable from a policy-driven skip without grepping logs.
