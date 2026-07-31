## Context

The reranker is a critical retrieval component that re-scores vector search candidates using a cross-encoder model. The current model (`cross-encoder/ms-marco-MiniLM-L-6-v2`, 22.7M params) was trained on MS MARCO passage data and has a 512-token context window. Experiment 10 found it **degrades technical retrieval by ~27%** on identifier-heavy queries — the reranker actively harms results for code/API/config-key searches.

NiftyPM task AIE-20 (P0) recommends `Alibaba-NLP/gte-reranker-modernbert-base` (149M params, ModernBERT architecture, 8,192-token context, Apache 2.0). Independent benchmarks confirm it matches 1.2B-param rerankers on Hit@1 (83.0%) at 8× smaller size, with a +47% F1 improvement over MiniLM on the BTZSC benchmark (arXiv:2603.11991).

The reranker runs entirely through ONNX Runtime — no PyTorch at runtime. The swap must preserve this constraint. The model is downloaded from HuggingFace Hub on first use and cached locally.

## Goals / Non-Goals

**Goals:**
- Replace default `RERANK_MODEL` with `Alibaba-NLP/gte-reranker-modernbert-base`
- Preserve ONNX Runtime inference path (no PyTorch, no sentence-transformers)
- Preserve singleton pattern, transient failure recovery, and graceful fallback
- Preserve sigmoid score normalisation and ÷30 threshold scaling (pending experiment validation)
- Verify quality improvement via A/B experiment before final adoption
- Update all specs, docs, and config to reflect the new model

**Non-Goals:**
- Adding Qwen3-Reranker-0.6B as an alternative reranker (separate future work, requires llama-server)
- Changing the reranker architecture (still a cross-encoder via ONNX, not a causal LM)
- Changing pool sizing (`RERANK_MAX_FETCH`, `RERANK_FETCH_MULTIPLIER`) — separate concern
- Changing the semantic/technical reranker policy (`RERANK_ENABLED_FOR_SEMANTIC`)
- Removing MiniLM support entirely — users can still set `RERANK_MODEL` to the old model

## Decisions

### Decision 1: Use `Alibaba-NLP/gte-reranker-modernbert-base` as default

**Rationale**: Best quality-to-size ratio among ONNX-compatible cross-encoders. 149M params, 8,192-token context, ModernBERT architecture (2-3× faster than BERT-family). Matches 1.2B Nemotron on Hit@1 (83.0%). +47% F1 over MiniLM on BTZSC. English-focused (advantage for our English technical corpora).

**Alternatives considered**:
- `Qwen3-Reranker-0.6B` (600M, GGUF): Higher multilingual quality but requires llama-server, 10-20× higher latency, causal LM architecture incompatible with current ONNX pipeline
- `bge-reranker-v2-m3` (568M): Good multilingual but 4× larger, no ModernBERT speed advantage
- `jina-reranker-v2-base-multilingual`: Good quality but Jina license (not Apache 2.0)
- HuggingFace Ettin 68M: Nearly matches Qwen3-0.6B on MTEB at 1/9th params, but very new (limited community validation)

### Decision 2: ONNX variant selection strategy

**Rationale**: The official HF repo ships eight pre-exported ONNX variants for this model (uploaded by thenlper, 2025-01): `onnx/model.onnx` (599MB fp32), `model_fp16.onnx` (300MB), `model_int8.onnx` (151MB), `model_quantized.onnx` (151MB), `model_q4.onnx`, `model_q4f16.onnx`, `model_uint8.onnx`, and `model_bnb4.onnx`. No `optimum` export is needed. The model-specific ARM-tuned variant (`model_qint8_arm64.onnx`) that MiniLM ships does not exist, but `model_quantized.onnx` and `model_int8.onnx` are standard ONNX quantised graphs that work cross-platform including ARM64 via `onnxruntime`.

**Approach**: Update `_select_onnx_variant()` to be model-aware. For `gte-reranker-modernbert-base`, prefer `onnx/model_quantized.onnx` (151MB int8) on all platforms. This keeps memory footprint reasonable while retaining full precision in the quantised graph. Fall back to `onnx/model_int8.onnx` if quantized unavailable, `onnx/model_fp16.onnx` (300MB) as second fallback, and `onnx/model.onnx` (599MB fp32) as last resort. The existing `onnx/model_qint8_arm64.onnx` path for MiniLM is preserved when `RERANK_MODEL` points to the old model.

### Decision 3: Tokenizer max_length cap at 2048

**Rationale**: The model supports 8,192 tokens but processing full 8,192-token pairs would significantly increase latency. Most RAG chunks are 512-1024 tokens. Capping at 2048 balances context window utilisation with latency. This is configurable but 2048 is the new default (up from 256).

**Alternatives**: 512 (conservative, matches old effective limit), 8192 (full context, highest latency), 1024 (middle ground).

### Decision 4: Threshold scaling — verify before changing

**Rationale**: The ÷30 threshold scaling (ADR-021) was empirically calibrated for MiniLM logits. Gte-reranker-modernbert-base may produce different logit distributions. The experiment must measure logit ranges and verify threshold behaviour. If recalibration is needed, it becomes a sub-task within this change.

## Risks / Trade-offs

- **[Larger model download (~151MB int8 quantised vs ~23MB current)]** → First-use download is ~7× larger with the quantised ONNX variant. Mitigation: log download progress, cache locally on first use. Acceptable trade-off for quality improvement.
- **[Threshold scaling may not transfer]** → ÷30 factor calibrated for MiniLM. Mitigation: Experiment measures logit distribution; recalibrate if needed before adoption.
- **[No ARM-tuned ONNX variant (`qint8_arm64`)]** → The model ships standard int8 quantised ONNX variants (`model_quantized.onnx`, 151MB) that work cross-platform including ARM64, but lacks the ARM-optimised `qint8_arm64` flavour that MiniLM ships. Mitigation: prefer `model_quantized.onnx` (standard int8); monitor memory usage on first run; if memory pressure occurs, the fp16 variant (300MB) or q4 variants are available as fallback.
- **[ModernBERT tokenizer differences]** → Tokenization behaviour may differ from BERT-family. Mitigation: Experiment includes tokenization sanity checks on technical queries.
- **[Experiment may not confirm improvement]** → If A/B shows no improvement or regression on our specific corpora, the swap is not adopted. Mitigation: Proposal is conditional on experiment results.
