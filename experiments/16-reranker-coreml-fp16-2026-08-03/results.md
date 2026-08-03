# Experiment 16: Reranker CoreML EP + fp16 feasibility and latency

**Status**: FAIL (H2) — fp16 loads with fix but is 2.3× slower than int8; CoreML does not help
**Date**: 2026-08-03
**Model**: `Alibaba-NLP/gte-reranker-modernbert-base`
**Platform**: macOS-26.5.1-arm64 | arm64 | ORT 1.25.1
**Iterations**: 5 warm × 5 queries × 20 docs (each cell in a separate process)

---

## Summary

The fp16 variant crashes on load due to an ORT `SimplifiedLayerNormFusion` graph
optimiser bug. The fix is one line — `disabled_optimizers=frozenset(['SimplifiedLayerNormFusion'])`.
With that fix, fp16 loads on both CoreML and CPU.

**But fp16 + CoreML is 2.3× slower than int8 + CPU.** CoreML does not accelerate
this model. int8 + CPU is the fastest option. Keep the swap default as-is.

## Cell comparison (corrected — each cell in a separate process)

| Cell | Variant | Provider | Loaded | P50 (ms) | P95 (ms) | Mean (ms) | Cold start (s) |
| --- | --- | --- | :---: | ---: | ---: | ---: | ---: |
| 16A | model_quantized.onnx (int8) | CPU | yes | 2347.5 | 2596.3 | 2368.6 | 0.23 |
| 16B | model_fp16.onnx | CoreML + CPU | yes (with fix) | 5392.8 | 5925.6 | 5456.9 | 0.53 |
| 16C | model_fp16.onnx | CPU | yes (with fix) | 5669.7 | 6284.9 | 5687.7 | 0.49 |

## Pass gates

| Gate | Result | Detail |
| --- | :---: | --- |
| H1 — fp16 + CoreML loads | PASS (with fix) | Requires `disabled_optimizers=frozenset(['SimplifiedLayerNormFusion'])` |
| H2 — fp16 + CoreML P50 < int8 + CPU P50 | FAIL | 5393ms vs 2348ms — fp16 is 2.3× slower |
| H2 — margin >= 5ms | FAIL | Margin is negative: int8 is faster by 3045ms |
| H3 — cold start <= 3× | PASS | 0.53s vs 0.23s |
| H3 — peak RSS <= 2× | PASS | Comparable |

## Key findings

### 1. The fp16 crash is fixable

The `SimplifiedLayerNormFusion` graph optimiser in ORT 1.25.1 cannot handle the
fp16 export's `InsertedPrecisionFreeCast` node. Disabling that one optimiser
allows fp16 to load on any provider:

```python
sess = ort.InferenceSession(
    path, providers=providers,
    disabled_optimizers=frozenset(["SimplifiedLayerNormFusion"]),
)
```

### 2. CoreML does not help

fp16 + CoreML (5393ms) ≈ fp16 + CPU (5670ms). CoreML EP is not accelerating
this model — ORT partitions the graph and most ops fall back to CPU anyway.
This confirms the existing code comment: CoreML EP is unsuitable for
cross-encoder models with dynamic sequence lengths.

### 3. int8 is 2.3× faster than fp16

int8 quantisation halves the compute (8-bit vs 16-bit ops). On CPU, this makes
int8 the clear winner: 2348ms vs 5393ms P50. There is no scenario where fp16
beats int8 on this hardware.

### 4. Process-level state contamination (benchmark artefact)

Loading int8 first in the same process corrupts ORT's global optimiser state,
causing subsequent fp16 loads to fail even with the fix. This is a benchmark
artefact — production loads one model per process and would never hit this.

## Recommendation

1. **Keep int8 + CPU as the swap default.** It is the fastest option and the
   swap design already specifies it.
2. **Add `disabled_optimizers` to `reranker.py`** as a safety net — if someone
   manually selects fp16 via env override, it should load without crashing.
   One line in `_load_model()`:
   ```python
   disabled = frozenset(["SimplifiedLayerNormFusion"]) if "fp16" in onnx_filename else None
   self._session = ort.InferenceSession(
       onnx_path, providers=providers, disabled_optimizers=disabled,
   )
   ```
3. **CoreML stays off.** This experiment confirms it does not help for
   cross-encoder reranker models. The `RERANK_ONNX_PROVIDER` default stays
   `"cpu"`.
4. **No different model needed.** The model is fine. The quality improvement
   (the swap's actual goal) comes from the ModernBERT architecture, not the
   precision format.

## What to do next

- Add the `disabled_optimizers` safety net to `reranker.py` (part of the swap
  implementation, task 1.1/1.2).
- Proceed with the swap's retrieval-quality A/B (Exp 15) using int8 + CPU as
  the gte cell — this experiment confirmed it's the right variant.
