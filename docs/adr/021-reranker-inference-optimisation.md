# ADR-021: Reranker Inference Optimisation — CoreML, Batching, and Reduced Fetch Pool

**Date:** 2026-06-23
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

During Experiment 11 (LiteParse PDF quality comparison), the cross-encoder
reranker exhibited pathological slowness: **261 seconds per warm query**,
making the full 4-cell evaluation (25 queries × 4 cells) take approximately
**5 hours**. This was operationally untenable and threatened to block the
entire LiteParse validation gate.

Root-cause investigation revealed four compounding issues in the ONNX
Runtime execution path, none of which were addressed when the reranker was
originally adopted in ADR-005:

1. **CPU-only execution provider.** The ONNX session was hardcoded to
   `providers=["CPUExecutionProvider"]`, ignoring the CoreML Execution
   Provider available on macOS arm64. The Apple Neural Engine — hardware
   specifically designed for this workload — sat idle.

2. **No batching.** All `fetch_k` candidates (500 at the time) were
   tokenised and inference-run in a single `session.run()` call. This
   caused excessive memory allocation, poor cache utilisation, and likely
   OS-level memory pressure on the 500-row padded tensor.

3. **Excessive fetch pool.** `RERANK_FETCH_MULTIPLIER=10` and
   `RERANK_MAX_FETCH=50` produced `fetch_k=500` for `top_k=50` — reranking
   10× more candidates than the output required. Prior research (ADR-016,
   ADR-018) showed diminishing returns above 2–3× top_k.

4. **Unbounded sequence length.** The tokenizer used the model's default
   `max_length=512`, but most query-document pairs are well under 256
   tokens. Every pair paid for 512-token padding compute it didn't need.

### Measured impact (before)

| Metric              | Value                        |
| ------------------- | ---------------------------- |
| Warm query latency  | 261.0s (4.4 min/query)       |
| Full experiment ETA | ~5 hours (50 reranked queries) |
| Provider            | CPUExecutionProvider only    |
| CoreML nodes used   | 0 / 627                      |

## Decision

Apply four execution-level fixes to `reranker.py` and `config.py`. **The
model itself (`cross-encoder/ms-marco-MiniLM-L-6-v2`) is unchanged** — only
how it runs.

### Fix 1: Prefer CoreML Execution Provider

```python
available = ort.get_available_providers()
providers = []
if "CoreMLExecutionProvider" in available:
    providers.append("CoreMLExecutionProvider")
providers.append("CPUExecutionProvider")
self._session = ort.InferenceSession(onnx_path, providers=providers)
```

On macOS arm64, CoreML routes 385 of 627 model nodes to the Apple Neural
Engine. The remaining 242 nodes fall back to CPU automatically. On
non-Apple platforms, the `if` guard skips CoreML and uses CPU-only — no
behaviour change.

### Fix 2: Batched inference (32 pairs per batch)

```python
BATCH_SIZE = 32
for i in range(0, len(pairs), BATCH_SIZE):
    batch = pairs[i:i + BATCH_SIZE]
    encoded = self._tokenizer(batch, ...)
    outputs = self._session.run(None, ...)
    all_logits.extend(...)
```

Previously all candidates went in one call. Batching to 32 pairs per call
reduces peak memory, improves ONNX Runtime's internal parallelism, and
prevents the OS from swapping mid-inference.

### Fix 3: Reduce fetch_k defaults

| Constant                  | Old | New | Effect on `top_k=50` | Effect on `top_k=10` |
| ------------------------- | --- | --- | -------------------- | -------------------- |
| `RERANK_FETCH_MULTIPLIER` | 10  | 3   | `50×3=150`           | `10×3=30`            |
| `RERANK_MAX_FETCH`        | 50  | 100 | `max(100, 150)=150`  | `max(100, 30)=100`   |

For the production default (`top_k=10`), `fetch_k` stays at 100 — **ADR-018
calibration is preserved**. Only large-`top_k` experiments (like Experiment
11's `top_k=50`) see a reduction.

### Fix 4: `max_length=256` on the tokenizer

Added `max_length=256` to the `self._tokenizer(...)` call. Most
query-document pairs are under 256 tokens; the previous implicit 512-token
limit wasted compute on padding.

### Measured impact (after)

| Metric              | Value                  | Improvement     |
| ------------------- | ---------------------- | --------------- |
| Warm query latency  | 26.1s                  | **10× faster**      |
| Full experiment ETA | ~23 minutes            | **13× faster**      |
| CoreML nodes used   | 385 / 627              | Neural Engine active |
| fetch_k (`top_k=50`)  | 150 (was 500)          | 3.3× fewer candidates |

## Consequences

### Positive

- Reranker is now practical for interactive use and large-scale experiments.
- ADR-018's calibrated `fetch_k=100` for `top_k=10` is unchanged — no
  regression in production retrieval quality.
- All four fixes are platform-agnostic in design: batching, reduced
  `fetch_k`, and `max_length` benefit every platform. CoreML is an
  additive win on macOS arm64 only.
- No model swap required — `ms-marco-MiniLM-L-6-v2` remains the reranker.
  The bottleneck was execution, not model capacity.

### Negative

- CoreML EP produces slightly different numerical results than CPU-only
  (float precision differences in the Neural Engine). This is negligible
  for ranking — relative ordering is preserved — but exact score values
  differ between macOS (CoreML) and Linux/CI (CPU).
- The `qint8_arm64.onnx` quantised model variant may not be optimal for
  CoreML (which prefers fp16). A future investigation could test whether
  the non-quantised `model.onnx` is faster on CoreML despite being larger.
- Non-macOS platforms (Linux CI, Windows) see only the batching + `fetch_k`
  + `max_length` improvements, not the CoreML speedup. Their per-query
  latency will be better than before but not 10×.

### Neutral

- `RERANK_FETCH_MULTIPLIER` and `RERANK_MAX_FETCH` are still env-var
  overridable. Operators who need the old aggressive pool can set
  `RERANK_FETCH_MULTIPLIER=10` without code changes.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Swap to `gte-reranker-modernbert-base` (NiftyPM AIE-20)** | A quality decision, not a speed fix. ModernBERT-base is ~150M params vs MiniLM-L-6's ~22M — it would be **even slower** on the same broken execution path. The model swap should be evaluated **after** fixing execution, so quality gains aren't confounded with speed losses. AIE-20 remains a valid follow-on proposal. |
| **Reduce `fetch_k` alone** | Helps (500→150 saves 3.3× candidates) but doesn't address the provider bottleneck (CPU-only) or the memory-thrash from unbatched inference. Would yield ~80s/query instead of 26s. |
| **Enable CoreML alone** | CoreML can't efficiently handle the 500-row unbatched tensor. Without batching, the provider switch alone showed marginal improvement. |
| **Do nothing / accept 5-hour runs** | Operationally untenable. Experiment 11 was blocked, and any future experiment requiring reranker cells would face the same barrier. |

## References

- ADR-005: Cross-Encoder Reranker with ONNX Runtime (original adoption)
- ADR-016: RAG Retrieval Quality Improvements (fetch pool sizing)
- ADR-018: Balanced Retrieval Defaults (`top_k=10`, `fetch_k=100` calibration)
- Commit `1e02de6`: `perf(reranker): 10x speedup via CoreML, batching, shorter sequences`
- NiftyPM AIE-20: Proposed reranker model swap (should follow this ADR, not precede it)
- Experiment 11: `experiments/11-liteparse-pdf-quality-2026-06-20/` (where the slowness was discovered)
- ONNX Runtime CoreML EP docs: https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html
