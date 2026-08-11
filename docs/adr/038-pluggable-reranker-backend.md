# ADR-038: Pluggable Reranker Backend

**Date:** 2026-08-11
**Status:** Accepted
**Scopes:** ADR-005 (does not reverse it — narrows the blanket "no PyTorch at runtime" to "no PyTorch in the base install or on the default retrieval path")
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

ADR-005 (11 May 2026) set a blanket "no PyTorch at runtime" boundary. The
size argument still holds for the default install: a ~23 MB ONNX reranker
beats a ~2 GB `sentence-transformers` dependency. But the blanket wording
over-reached: it later decided which PDF parsers were admissible (ADR-020
rejected Docling, Marker, Unstructured, MinerU on this rule alone) and
which rerankers could even be benchmarked (ADR-028). The rule meant "keep
the default install light" but read as "PyTorch must not exist anywhere".

The rule also created a dependency trap. `transformers` was a **base**
dependency used for exactly one call: `AutoTokenizer.from_pretrained()` in
`core/retrieval/reranker.py`. The 2026-08-06 dependency drift audit
flagged that `transformers` v5 drops TensorFlow and JAX and consolidates
on `torch` as its sole backend. The pin was `transformers>=4.40.0` with
no upper bound. Either a future resolution silently violated the
project's own hard boundary, or the project pinned `<5` indefinitely and
aged out of tokeniser fixes. An upstream release was deciding the
architecture.

## Decision

1. **Replace `transformers.AutoTokenizer` with the `tokenizers` package**
   in the ONNX reranker. `tokenizers` is already installed transitively
   (by `chromadb`), is 9.2 MB against `transformers`' 56 MB, is pure
   Rust, and can never pull `torch`.

2. **Remove `transformers` from base dependencies.** It moves into the
   new `torch` optional extra, where a torch dependency is expected.
   `tokenizers>=0.20` takes its place in base deps.

3. **Add a second reranker backend** (`core/retrieval/reranker_torch.py`),
   wrapping `sentence_transformers.CrossEncoder`. It satisfies the same
   public contract as the ONNX backend and applies the same sigmoid
   normalisation. Available behind the `torch` optional extra:
   `uv sync --extra torch`.

4. **Make backend choice settings-driven.**
   `RETRIEVAL__RERANK_BACKEND` (`onnx` | `torch`, default `onnx`) selects
   the backend. Both construction paths — `compose.build_reranker()` and
   the lazy fallback in `pipeline.py` — route through a shared
   `core/retrieval/backend.py` helper so they cannot diverge.

5. **Retire the bare `"reranker"` registry name** in favour of
   `"reranker_onnx"` and `"reranker_torch"`. A stale alias resolving to
   the wrong backend is the silent-divergence failure this change exists
   to prevent.

6. **Scope the "no PyTorch" boundary** from "no PyTorch at runtime" to
   "no PyTorch in the base install or on the default retrieval path".
   PyTorch behind the `torch` optional extra is admissible. The amended
   boundary is recorded in `CLAUDE.md`.

7. **Enforce sigmoid parity by contract test.** The torch backend calls
   `CrossEncoder.predict(..., activation_fn=torch.nn.Identity())` to
   suppress the library's default sigmoid, then applies the shared
   `_sigmoid` once. Passing `activation_fn=None` would NOT disable
   activation — for `num_labels=1` it resolves to `nn.Sigmoid()`,
   double-applying sigmoid and compressing scores to roughly
   `[0.5, 0.73]`. The cross-backend contract test compares score _values_
   across backends (not just ranking or range) because double-sigmoid
   preserves monotonicity and stays in `(0, 1)`.

## Install-size delta

The `transformers` wheel is 56 MB; the `tokenizers` wheel is 9.2 MB. But
the real saving is smaller than the 47 MB isolated-wheel comparison
suggests, because `tokenizers` and `huggingface-hub` are already pulled
transitively by `chromadb`. The exact number should be measured in a
fresh venv at deployment time (`uv pip list --format=freeze` before and
after, then `diff`).

## Consequences

### Positive

- The `transformers` v5 trap is closed permanently. No upstream release
  can force an architecture decision.
- The default install stays torch-free — verified by a runtime tripwire
  test (`tests/test_no_torch_at_runtime.py`) and a dependency-audit test
  (`tests/test_dependency_audit.py`), not by convention.
- The torch backend opens the MPS route to Apple GPU acceleration via
  PyTorch's MPS backend. MPS (Metal Performance Shaders) is an Apple
  framework, not a PyTorch feature — it is accessible through MPSGraph,
  Core ML, MLX, and PyTorch. For this project's reranker, the torch
  backend is the path that makes it reachable. Measured in Experiment 17
  (ADR-039 records the verdict).
- Score-range parity is enforced by test, not by review.

### Negative

- Two backends double the "which one actually ran" surface. Mitigated by
  the backend-name diagnostic field (ADR-029 deferred item 2) and by a
  dedicated CI job that exercises the torch backend (task 11.5).
- The torch backend can rot from disuse — it is not on the default path.
  Mitigated by the dedicated CI job; if it proves insufficient, the
  honest response is to remove the backend rather than ship a broken
  option.
- `tokenizers` does not expose `model_max_length`. The ONNX backend now
  reads `max_position_embeddings` from `config.json` via
  `huggingface_hub`, falling back to the configured default when absent.

### Neutral

- The cache key changed from `model_id` to `(backend_name, model_id)`.
  Both backends can be asked for the same model ID without collision.
- The bare `"reranker"` registry name is gone. Any code or test
  monkeypatching the old name needs updating to `"reranker_onnx"`.

## Alternatives Considered

| Option                                           | Rejected Because                                                                                                    |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| Pin `transformers<5` forever                     | Defers the problem and ages out of tokeniser fixes                                                                  |
| Keep `transformers` in base deps, ignore v5 risk | An upstream release silently violates the project's own boundary                                                    |
| Let each backend define its own normalisation    | Multiplies the calibrated ÷30 constant by the number of backends; each copy drifts independently                    |
| Keep `"reranker"` as an alias for the default    | A stale alias resolving to the wrong backend is exactly the silent-divergence failure this change exists to prevent |

## References

- `src/rag_mcp/core/retrieval/reranker.py` — ONNX backend, `tokenizers` swap
- `src/rag_mcp/core/retrieval/reranker_torch.py` — torch backend
- `src/rag_mcp/core/retrieval/backend.py` — shared backend-resolution helper
- `src/rag_mcp/core/retrieval/_reranker_cache.py` — shared model cache
- ADR-005 — the original "no PyTorch at runtime" boundary (scoped, not reversed)
- ADR-029 — observability: `rerank_reason` and `rerank_backend` diagnostics
- ADR-039 — Apple acceleration verdict (Experiment 17)
- `tests/test_reranker_backend_contract.py` — cross-backend score parity
- `tests/test_no_torch_at_runtime.py` — runtime torch-free tripwire
