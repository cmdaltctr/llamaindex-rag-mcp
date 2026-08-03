## Why

The current reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`, 22.7M params, 512-token context) **degrades technical retrieval by ~27%** (Experiment 10). It was trained on MS MARCO passage data and struggles with code-heavy, identifier-dense queries typical of our technical corpora. NiftyPM task AIE-20 (P0, overdue since 2026-06-13) identifies `Alibaba-NLP/gte-reranker-modernbert-base` as a drop-in replacement that matches 1.2B-param rerankers on Hit@1 (83.0%) at 8× smaller size, with 8,192-token context and ModernBERT architecture (2-3× faster than BERT-family). Independent benchmarks (BTZSC, arXiv:2603.11991) confirm it scores 0.63 avg F1 vs MiniLM's 0.43 — a +47% improvement — while remaining a standard cross-encoder compatible with our ONNX Runtime pipeline.

## What Changes

- **BREAKING**: Default `RERANK_MODEL` changes from `cross-encoder/ms-marco-MiniLM-L-6-v2` to `Alibaba-NLP/gte-reranker-modernbert-base`
- Update `_select_onnx_variant()` to handle ModernBERT ONNX model paths (prefer `onnx/model_quantized.onnx` int8, 151MB; no ARM-tuned `qint8_arm64` variant exists for this model)
- Update `reranker.py` module docstring and model references
- Update `reranking` spec: ONNX variant selection scenario, model docstring scenario, and `RERANK_MODEL` default in env var table
- Update `.env.example` with new default `RERANK_MODEL`
- Update `docs/guides/reranker.md` (if exists) or `docs/guides/architecture.md` reranker section with new model details
- A/B experiment on FreshStack LangChain + Qasper to verify quality improvement before adoption (Experiment subtasks from AIE-20)
- **BREAKING**: Max token length changes from 256 to 8192 (or a pragmatic cap like 2048) in the tokenizer call, affecting reranker latency characteristics

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `reranking`: Default `RERANK_MODEL` changes to `Alibaba-NLP/gte-reranker-modernbert-base`. ONNX variant selection logic must adapt (prefer `onnx/model_quantized.onnx` int8; no ARM-tuned `qint8_arm64` variant for this model). Module docstring and model reference scenarios must reflect the new model. Tokenizer `max_length` increases from 256 to leverage the 8,192-token context window. The `RERANK_MODEL` env var default in the configuration table updates.
- `score-normalisation`: Sigmoid normalisation continues to apply, but raw logit distributions may differ between MiniLM and gte-reranker-modernbert-base. The ÷30 threshold scaling factor (ADR-021) may need recalibration if the new model's logit distribution differs significantly. Experiment must verify threshold behaviour.

## Impact

- **Code**: `src/rag_mcp/reranker.py` — `RERANK_MODEL` default, `_select_onnx_variant()`, tokenizer `max_length`, module docstring
- **Config**: `.env.example` — `RERANK_MODEL` default value
- **Specs**: `openspec/specs/reranking/spec.md`, `openspec/specs/score-normalisation/spec.md` — update model references, ONNX variant scenarios, env var defaults
- **Dependencies**: No new runtime dependencies. `onnxruntime`, `transformers`, `huggingface-hub` remain. Model is ~151MB int8 quantised (vs ~23MB current) — first-use download time increases
- **Experiments**: New experiment directory `experiments/N-gte-reranker-swap-YYYY-MM-DD/` for A/B comparison (FreshStack LangChain + Qasper, vs current reranker, vs rerank-off baseline)
- **ADRs**: New ADR documenting the model swap decision and threshold recalibration results
- **NiftyPM**: AIE-20 subtasks (ONNX export verification, A/B comparison, baseline comparison, experiment write-up)
- **Latency**: On GPU (L4), ~42ms P50 at 6.2K tok/s (Superlinked benchmarks). On CPU ONNX Runtime (Apple Silicon M1), latency is to be measured in the experiment — ModernBERT's architecture is efficient per-param, but 6.5× the parameter count means latency impact is uncertain. The experiment (task 2.7) settles this empirically.
- **Risk**: Threshold scaling (÷30) was calibrated for MiniLM logits. If gte-reranker logit distribution differs, threshold filtering may behave differently until recalibrated
