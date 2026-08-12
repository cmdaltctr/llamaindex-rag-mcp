# ADR-041: onnxruntime 1.28.0 Upgrade

**Date:** 2026-08-12
**Status:** Accepted
**Scopes:** ADR-005 (ONNX Runtime reranker), ADR-029 (CoreML disabled for reranker — the CoreML provider is still present in 1.28.0; the dynamic-shape limitation is a CoreML graph compilation constraint, not an onnxruntime version issue)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The `onnxruntime>=1.17.0,<1.26.0` cap was a routine upper bound, not a
breaking-major gate (unlike the mcp and huggingface-hub caps from
ADR-039/040). It was not flagged in the original comment block for the
major-upgrade cycle, but lifting it closes the last remaining upper cap
in `pyproject.toml`.

onnxruntime 1.28.0 (released 2026-07-25) includes:

- ONNX 1.22.0 and protobuf 6.33.5 upgrade (internal)
- cuDNN/cuFFT now optional at runtime for CUDA EP
- Security hardening (multiple memory-safety, integer-overflow, and
  supply-chain fixes — CVE-2026-0994 mitigation via protobuf bump)
- Deprecated/removed: SkipLayerNorm strict mode, TensorRT fused causal
  attention kernels, dynamic WGSL generator path, `CUDA_QUANT_PREPROCESS`
  off by default

All breaking changes are CUDA/TensorRT/WebGPU/NPU-specific. The
onnxruntime Python API this project uses — `ort.InferenceSession(path,
providers=[...])` and `ort.get_available_providers()` — is unchanged
across 1.26–1.28.

### Apple Silicon acceleration paths

This project has two paths to Apple hardware acceleration, not one:

1. **onnxruntime CoreML EP** — `CoreMLExecutionProvider` is present in
   1.28.0 on macOS. Disabled by default for the reranker (ADR-029:
   CoreML compiles the graph for the first input shape and cannot
   resize when sequence length changes — a fundamental CoreML
   limitation, not an onnxruntime bug). Re-enable per-call via
   `RERANK_ONNX_PROVIDER=coreml`.

2. **PyTorch MPS** (Metal Performance Shaders) — available via the
   opt-in `torch` extra (ADR-038). PyTorch 2.13.0 with
   `torch.backends.mps.is_available() == True` on Apple Silicon.
   sentence-transformers 5.7.0 auto-detects MPS and routes the
   `CrossEncoder` model to `mps:0` without explicit device
   configuration. Unlike CoreML, MPS handles dynamic shapes natively,
   so it does not have the ADR-029 limitation. This is the preferred
   Apple acceleration path for the reranker.

## Decision

Lift the `<1.26.0` cap. No source or test changes needed.

### `pyproject.toml` change

- `"onnxruntime>=1.17.0,<1.26.0"` → `"onnxruntime>=1.17.0"`

The floor stays at `>=1.17.0` (the minimum that has the APIs we use);
no need to raise it since nothing was removed from the inference or
provider-selection API between 1.17 and 1.28.

## Alternatives considered

- **Keep the cap.** Rejected — it was a routine pin, not a breaking-major
  gate, and 1.28.0 includes security fixes (CVE-2026-0994). Aging out of
  security patches is worse than the zero risk of lifting a cap on a
  stable CPU-only API surface.

## Consequences

- **Positive:** security fixes (CVE-2026-0994, multiple memory-safety
  hardening patches), ONNX 1.22.0 support.
- **Neutral:** no API changes affect our usage. `get_available_providers()`
  still returns `CoreMLExecutionProvider` on macOS (disabled for the
  reranker by default per ADR-029; re-enable via
  `RERANK_ONNX_PROVIDER=coreml`). The preferred Apple acceleration path
  is PyTorch MPS via the `torch` extra, which is unaffected by
  onnxruntime version changes.

## Verification

- `uv lock --upgrade`: `onnxruntime 1.25.1 → 1.28.0`.
- `uv sync`: clean.
- `ort.__version__` = 1.28.0, `get_available_providers()` returns
  `['CoreMLExecutionProvider', 'AzureExecutionProvider',
'CPUExecutionProvider']`.
- `uv run pytest -m "not slow"`: **1201 passed, 3 skipped**.
- Apple Silicon acceleration verified: `torch.backends.mps.is_available()
== True` on PyTorch 2.13.0; sentence-transformers 5.7.0
  `CrossEncoder` auto-routes to `mps:0` (no explicit device config
  needed in `reranker_torch.py`).
