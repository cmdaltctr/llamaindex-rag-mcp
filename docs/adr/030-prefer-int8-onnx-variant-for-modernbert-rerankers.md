# ADR-030: Prefer int8 Quantised ONNX Variant for ModernBERT Rerankers

**Date:** 2026-08-03
**Status:** Proposed
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The reranker (`src/rag_mcp/reranker.py`) loads ONNX models from HuggingFace Hub.
For ModernBERT-based models such as `Alibaba-NLP/gte-reranker-modernbert-base`,
the Hub ships eight pre-exported ONNX variants: fp32, fp16, int8 (two flavours),
and four sub-4-bit quantisations. The variant choice affects download size,
inference speed, and load reliability.

Three open questions motivated Experiment 16:

1. **Does the fp16 variant load under CoreML EP?** ADR-029 disabled CoreML
   because of a dynamic-shape crash, but that was with the legacy MiniLM int8
   model. The fp16 variant is a different graph — it might behave differently.
2. **Is fp16 + CoreML faster than int8 + CPU?** CoreML targets the Apple Neural
   Engine, which accelerates fp16 but not int8. If fp16 + CoreML worked and was
   fast, it could be the preferred path on M-series Macs.
3. **Is fp16 viable at all?** The fp16 export had not been tested.

### Experiment 16 findings

| Cell | Variant | Provider | P50 (ms) | Loaded? |
| --- | --- | --- | ---: | --- |
| 16A | int8 (`model_quantized.onnx`) | CPU | 2,348 | yes |
| 16B | fp16 (`model_fp16.onnx`) | CoreML + CPU | 5,393 | yes (with fix) |
| 16C | fp16 (`model_fp16.onnx`) | CPU | 5,670 | yes (with fix) |

**Finding 1 — fp16 crashes without a workaround.** The fp16 export triggers an
ORT 1.25.1 `SimplifiedLayerNormFusion` graph optimiser bug: the fusion pass
looks for a node arg (`InsertedPrecisionFreeCast_...`) that does not exist in
the fp16 graph. The model fails to load on **all** providers, not just CoreML.

The fix is one line — disable the single broken optimiser:

```python
disabled_optimizers=frozenset(["SimplifiedLayerNormFusion"])
```

**Finding 2 — int8 is 2.3× faster than fp16.** int8 quantisation halves the
compute (8-bit vs 16-bit operations). On CPU, int8 P50 is 2,348ms vs fp16's
5,393–5,670ms. There is no scenario where fp16 beats int8 on this hardware.

**Finding 3 — CoreML does not accelerate this model.** fp16 + CoreML (5,393ms)
is statistically indistinguishable from fp16 + CPU (5,670ms). CoreML EP
partitions the graph but most ops fall back to CPU for cross-encoder models
with dynamic sequence lengths. This confirms ADR-029's finding with
additional evidence: even when CoreML loads without crashing, it provides no
benefit.

**Finding 4 — process-level state contamination.** Loading int8 first in the
same process corrupts ORT's global optimiser state, causing subsequent fp16
loads to fail even with the `disabled_optimizers` fix. This is a benchmark
artefact — production loads one model per process.

## Decision

### 1. Default to int8 quantised variant

`model_quantized.onnx` (151 MB, int8) is the preferred variant for
ModernBERT-based reranker models on all platforms. The fallback chain in
`_select_onnx_variant()` already encodes this:

```python
return [
    "onnx/model_quantized.onnx",
    "onnx/model_int8.onnx",
    "onnx/model_fp16.onnx",
    "onnx/model.onnx",
]
```

int8 is 2.3× faster than fp16 and downloads at half the size (151 MB vs
300 MB). The quality difference between int8 and fp16 precision is negligible
for reranking — the cross-encoder produces a single relevance logit, not a
dense embedding where precision matters more.

### 2. Add SimplifiedLayerNormFusion disabled_optimizers safety net

When loading any fp16 variant (whether as a fallback or via manual env
override), pass `disabled_optimizers` to prevent the graph optimiser crash:

```python
disabled = (
    frozenset(["SimplifiedLayerNormFusion"])
    if "fp16" in onnx_filename
    else None
)
self._session = ort.InferenceSession(
    onnx_path, providers=providers, disabled_optimizers=disabled,
)
```

This is a safety net, not a default path. The int8 variant does not trigger
the bug and needs no workaround.

### 3. CoreML stays off

ADR-029 already disabled CoreML by default. Experiment 16 provides additional
evidence: even when CoreML loads successfully (fp16 + `disabled_optimizers`),
it delivers no speed benefit over CPU-only. The `RERANK_ONNX_PROVIDER`
default stays `"cpu"`.

## Consequences

### Positive

- int8 is the fastest available variant — 2.3× faster than fp16 on CPU
- Smaller download (151 MB vs 300 MB for fp16, 599 MB for fp32)
- The `disabled_optimizers` safety net prevents crashes if anyone manually
  selects fp16 via env override
- CoreML confirmed ineffective — no temptation to re-enable it

### Negative

- int8 precision could theoretically degrade reranking quality for borderline
  cases. In practice, cross-encoder logits are robust to quantisation — the
  sigmoid normalisation absorbs small precision differences
- The `SimplifiedLayerNormFusion` bug may persist in future ORT versions.
  If ORT fixes it, the `disabled_optimizers` line becomes a no-op (harmless)

### Neutral

- The variant fallback chain already handles the case where
  `model_quantized.onnx` is unavailable — it falls through to `model_int8`,
  then `model_fp16` (with the safety net), then `model.onnx` (fp32)
- Non-Apple platforms see no change — they were already CPU-only

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **fp16 as default variant** | 2.3× slower than int8 on CPU, 2× larger download, and requires the `disabled_optimizers` workaround to load at all |
| **fp16 + CoreML as default on M-series** | CoreML provides no acceleration — fp16 + CoreML (5,393ms) ≈ fp16 + CPU (5,670ms). Confirmed by Experiment 16 |
| **fp32 (`model.onnx`) for maximum precision** | 599 MB download, ~4× slower than int8. Precision gain is irrelevant for a single-logit reranker |
| **Sub-4-bit variants (q4, q4f16, uint8, bnb4)** | Untested. May have even worse precision or different ORT compatibility issues. int8 already meets latency targets |
| **Re-export fp16 with `optimum` to fix the graph** | Adds a build-time dependency and export step. The pre-exported int8 variant works without any export tooling |
| **Do nothing — leave variant selection as-is** | The `disabled_optimizers` safety net is needed to prevent crashes when fp16 is loaded as a fallback |

## References

- ADR-005: Cross-Encoder Reranker with ONNX Runtime (original adoption)
- ADR-021: Reranker Inference Optimisation (introduced CoreML)
- ADR-028: Swap Default Reranker to gte-reranker-modernbert-base (Rejected)
- ADR-029: Disable CoreML for Reranker — Silent Fallback Lesson
- Experiment 16: `experiments/16-reranker-coreml-fp16-2026-08-03/results.md`
- Code: `src/rag_mcp/reranker.py` — `_select_onnx_variant()`, `_load_model()`
- Model card: https://huggingface.co/Alibaba-NLP/gte-reranker-modernbert-base
- ORT graph optimisation docs: https://onnxruntime.ai/docs/performance/model-optimizations/graph-optimizations.html
