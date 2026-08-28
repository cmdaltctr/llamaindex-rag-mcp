## Why

The `🚫 Never — PyTorch at runtime` boundary was set by ADR-005 (11 May 2026) to keep a 23 MB ONNX reranker instead of a ~2 GB `sentence-transformers` install. That size argument still holds for the default install. The blanket wording does not: it now also decides which PDF parsers are admissible (ADR-020 rejects Docling, Marker, Unstructured, MinerU on this rule alone) and which rerankers may even be benchmarked (ADR-028).

The rule has also created a dependency trap. `transformers` is a **base** dependency used for exactly one call, `AutoTokenizer.from_pretrained()` in `core/retrieval/reranker.py:304`. The 2026-08-06 dependency drift audit flagged that `transformers` v5 drops TensorFlow and JAX and consolidates on `torch` as its sole backend. The pin is `transformers>=4.40.0` with no upper bound. Either a future resolution silently violates the project's own hard boundary, or the project pins `<5` indefinitely and ages out of tokeniser fixes. An upstream release decides the architecture either way.

## What Changes

- Replace `transformers.AutoTokenizer` with the `tokenizers` package in the ONNX reranker. `tokenizers` is already installed transitively, is 9.2 MB against `transformers`' 56 MB, is pure Rust, and can never pull `torch`.
- **BREAKING (dependency)**: remove `transformers` from base `dependencies` in `pyproject.toml`. It moves into the new `torch` optional extra, where a torch dependency is expected.
- Add a second reranker backend, `core/retrieval/reranker_torch.py`, wrapping `sentence_transformers.CrossEncoder`. It satisfies the same public contract as the ONNX backend and applies the same sigmoid normalisation.
- Add `RETRIEVAL__RERANK_BACKEND` (`onnx` | `torch`, default `onnx`) so backend choice is settings-driven rather than hardcoded.
- Register both backends in `core/retrieval/registry.py`. Rename the existing `reranker` entry to `reranker_onnx`.
- Route backend selection through `compose.build_reranker()` **and** the lazy fallback at `core/retrieval/pipeline.py:320`, which currently hardcodes the registry name.
- Add a `torch` optional extra: `sentence-transformers>=5.0`.
- Add a runtime tripwire test asserting `torch` is absent from `sys.modules` after a default-backend search. This turns the existing prose requirement into CI.
- Add a cross-backend contract test asserting both backends return scores in `(0, 1)` and produce comparable rankings on shared fixtures.
- Surface the reranker's success flag and failure reason into `include_diagnostics` output (ADR-029 §3 deferred item 2), so the active backend and its health are observable.
- Amend the `🚫 Never` boundary in `CLAUDE.md` from a blanket ban to a scoped one: no PyTorch in the base install or on the default retrieval path; PyTorch behind an optional extra is an ⚠️ Ask.

- Run Experiment 17 to close the Apple-acceleration question. The torch backend opens MPS (Metal Performance Shaders) via PyTorch's MPS backend — the only untested route to the machine's GPU for this project's reranker. MPS is an Apple framework built on Metal, not a PyTorch feature; it is accessible through MPSGraph, Core ML, TensorFlow's Metal plugin, MLX, and PyTorch. For this project's reranker, the torch backend is the path that makes it reachable. Three cells on the default model: ONNX int8 on CPU, torch on CPU, torch on MPS. The result goes into an ADR so the question stops recurring.

  > **Split on 2026-08-11.** Experiment 17 moved to `openspec/changes/apple-acceleration-for-reranker/` — it is research that produces an ADR and potentially a follow-up code change, separable from the pluggable-backend code. Task 9.11 already anticipated a follow-up change if MPS wins. The pluggable-backend PR (#37) merges without waiting for the benchmark.

Out of scope: changing the default backend, changing the default model, changing the default execution provider, re-testing CoreML, and any PDF parser work. The default install stays torch-free and behaviour-identical.

CoreML specifically is settled and is NOT revisited. Experiment 16 (2026-08-03) measured it: fp16 + CoreML at 5393 ms P50 against fp16 + CPU at 5670 ms, so it accelerated nothing, because ONNX Runtime partitions the graph and most operations fall back to CPU anyway. int8 + CPU won at 2348 ms. A related belief — that CoreML failed because PyTorch was missing — is also wrong: `onnxruntime` reports `CoreMLExecutionProvider` as available in a venv with no torch installed and none in `sys.modules`. CoreML is an Apple C++ framework reached natively. The ADR-029 error was a shape error, not an import error. Experiment 17 records both findings so this is not re-litigated.

## Capabilities

### New Capabilities

- `reranker-backend-selection`: pluggable reranker backends behind a registry, settings-driven selection, a torch-free default install guarantee enforced by a runtime tripwire, and a cross-backend score-range contract.

### Modified Capabilities

- `reranking`: the `ONNX inference via pure onnxruntime` requirement currently mandates `transformers.AutoTokenizer`; it changes to mandate `tokenizers`. The `no PyTorch at runtime` requirement currently forbids `sentence-transformers` as a runtime dependency outright; it changes to forbid it in the **base** install while permitting it behind an opt-in extra. The `reranker configuration via environment` table gains `RETRIEVAL__RERANK_BACKEND`.

## Impact

**Code**

- `src/rag_mcp/core/retrieval/reranker.py` — tokeniser swap; `model_max_length` handling moves in-module since `tokenizers` does not expose it the same way (existing sentinel guard at lines 311-317 already covers most of this).
- `src/rag_mcp/core/retrieval/reranker_torch.py` — new.
- `src/rag_mcp/core/retrieval/registry.py` — two `register()` lines.
- `src/rag_mcp/core/retrieval/settings.py` — one field on `RetrievalSettings`.
- `src/rag_mcp/core/settings.py` — the same field on `RetrievalBlock` (Pydantic silently drops undeclared fields during the `model_dump()` copy in `compose.settings_to_effective`).
- `src/rag_mcp/config/__init__.py` — one `_validate_provider_value` call in `_validate_provider_selections`.
- `src/rag_mcp/core/retrieval/pipeline.py:320` — registry name from settings, not a literal.
- `src/rag_mcp/compose.py::build_reranker` — backend dispatch.

**Dependencies**

- Base: `transformers` removed, `tokenizers>=0.20` added.
- New extra: `torch = ["sentence-transformers>=5.0"]`.
- Base install footprint drops — the exact saving is measured in a fresh venv at implementation time (ADR-038 records the real number). The estimate is smaller than the 47 MB isolated-wheel comparison suggests, because `tokenizers` and `huggingface-hub` are already pulled transitively by `chromadb`.

**Risk**

- The ÷30 threshold scaling (`core/retrieval/policy.py::_effective_threshold`) is calibrated against sigmoid-normalised ONNX logits from `experiments/1-reranker-threshold-calibration-2026-05-12/`. `CrossEncoder.predict()` applies `nn.Sigmoid()` by default for `num_labels=1`; the torch backend overrides this with `torch.nn.Identity()` and applies the module's own `_sigmoid` to guarantee parity. Passing `activation_fn=None` would NOT disable the default sigmoid — it would double-sigmoid the logits, compressing scores to roughly `[0.5, 0.73]` and silently breaking the ÷30 threshold. The contract test compares score values across backends, not just ranking or range, because double-sigmoid preserves monotonicity and stays in `(0, 1)`.

**Experiments**

- New: `experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/`. Runs after the torch backend works, never before.
- Reuses Experiment 16's separate-process-per-cell runner shape. Its finding 4 recorded that loading int8 first corrupts ONNX Runtime's global optimiser state and poisons later cells in the same process.

**Branching**

- Targets `v3`, not `main`. Breaking work goes to `v3`; `main` cuts a release on every push. PR #27 also targeted `v3` and is already merged at `67330ca`, so nothing blocks this.

**Docs**

- `CLAUDE.md` hard boundary table.
- `docs/guides/reranker.md`, `docs/guides/configuration.md`, `.env.example`.
- New ADR superseding ADR-005's scope (not its decision).

**Tests**

- `tests/test_reranker.py` — tokeniser mocks change.
- New: cross-backend contract test, `torch`-absence tripwire.
- Torch-backend cases marked `slow` so `-m "not slow"` stays fast and torch-free.
