# Reranker

The server includes an optional **cross-encoder reranker** that re-scores vector search results for significantly better retrieval precision. It uses `cross-encoder/ms-marco-MiniLM-L-6-v2` — a ~23 MB quantised ONNX model that runs locally via pure ONNX Runtime. The default install has no PyTorch; a torch-backed backend is available as an opt-in extra (see [Backends](#backends) below).

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

## Backends

The reranker has two interchangeable inference backends. Both produce scores on the same `(0, 1)` scale via a shared sigmoid transform, so the calibrated threshold stays valid whichever backend runs (ADR-038).

| Backend | Settings value | Install | Torch loaded? |
|---------|---------------|---------|---------------|
| ONNX Runtime (default) | `RETRIEVAL__RERANK_BACKEND=onnx` | Base install | No |
| sentence-transformers | `RETRIEVAL__RERANK_BACKEND=torch` | `uv sync --extra torch` (~200 MB on macOS ARM) | Yes — only when this backend is selected |

The ONNX backend tokenises with the pure-Rust `tokenizers` package, which cannot pull `torch`. The torch backend imports `sentence_transformers` lazily inside its model-load method, so simply installing the extra does not change the default path.

**Sigmoid parity**: `CrossEncoder.predict()` applies `nn.Sigmoid()` by default for `num_labels=1` models. The torch backend overrides this with `nn.Identity()` and applies the shared `_sigmoid` once — otherwise the logits would be double-sigmoided, compressing scores to roughly `[0.5, 0.73]` and silently breaking the ÷30 threshold (ADR-038, design decision 3). The cross-backend contract test (`tests/test_reranker_backend_contract.py`) compares score *values*, not just ranking, to catch this.

**Fallback**: if `RETRIEVAL__RERANK_BACKEND=torch` is set but the extra is not installed, the server logs an error naming `uv sync --extra torch` and falls back to the ONNX backend. If the ONNX backend also fails, the search returns un-reranked results truncated to `top_k`.

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

**Diagnostics**: when `include_diagnostics=True`, each result carries:
- `rerank_reason` — the policy decision or the reranker's own failure reason (e.g. `"inference failed: ..."` or `"model load failed: ..."`)
- `rerank_backend` — the backend that performed the re-scoring (`"onnx"` or `"torch"`), which may differ from the settings value when the torch extra is missing and the helper fell back to ONNX

So a broken reranker is distinguishable from a policy-driven skip without grepping logs, and the active backend is observable alongside it (ADR-029 deferred item 2).
