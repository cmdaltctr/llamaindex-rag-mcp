# ADR-028: Swap Default Reranker to gte-reranker-modernbert-base

|               |                                                  |
| ------------- | ------------------------------------------------ |
| **Date**      | 2026-07-31                                       |
| **Status**    | Rejected                                         |
| **Supersedes** | _(none — ADR-005 model choice stands)_          |

## Context

The default reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`, 22.7M params, 512-token context) was trained on MS MARCO passage data and **degrades technical retrieval by ~27%** on identifier-heavy queries (Experiment 10). Code-heavy, API-key, and config-path searches are actively harmed by the reranker, leading to ADR-019 (disable reranker for technical workloads) as a stopgap.

NiftyPM task AIE-20 (P0, overdue since 2026-06-13) identifies `Alibaba-NLP/gte-reranker-modernbert-base` as a drop-in replacement:

- **149M params**, ModernBERT architecture (2-3× faster than BERT-family per param)
- **8,192-token context** (vs 512 for MiniLM)
- Matches 1.2B-param Nemotron rerankers on Hit@1 (83.0%) at 8× smaller size
- +47% F1 improvement over MiniLM on the BTZSC benchmark (arXiv:2603.11991)
- **Apache 2.0** licence
- Ships **8 pre-exported ONNX variants** on HuggingFace Hub — no `optimum` export needed

The reranker runs entirely through ONNX Runtime (no PyTorch at runtime, per ADR-005). The swap must preserve this constraint, the singleton pattern, transient failure recovery, and sigmoid score normalisation.

## Decision

Adopt `Alibaba-NLP/gte-reranker-modernbert-base` as the default `RERANK_MODEL`, replacing `cross-encoder/ms-marco-MiniLM-L-6-v2`.

### ONNX variant selection

The model ships standard quantised ONNX variants (`model_quantized.onnx`, 151MB int8) that work cross-platform including ARM64. No ARM-tuned `qint8_arm64` variant exists (unlike MiniLM). The `_select_onnx_variant()` function is now model-aware:

- **ModernBERT models**: prefer `onnx/model_quantized.onnx` → fall back through `model_int8.onnx` → `model_fp16.onnx` → `model.onnx`
- **Legacy MiniLM**: preserve existing `onnx/model_qint8_arm64.onnx` path on ARM64

### Tokenizer max length

Increased from 256 to 2,048 tokens (configurable via `RERANK_TOKENIZER_MAX_LENGTH`). The model supports 8,192 tokens, but most RAG chunks are 512-1,024 tokens. Capping at 2,048 balances context window utilisation with latency.

### Threshold scaling

The ÷30 threshold scaling factor (ADR-021) was calibrated for MiniLM logits. The A/B experiment (tasks 2.1-2.8) must verify whether recalibration is needed. If logit distributions differ by >2× in standard deviation, a recalibration experiment follows the Experiment 1 protocol.

## Consequences

### Positive

- **+47% F1 improvement** on benchmark data; expected to restore reranker value for technical queries
- **8,192-token context** enables reranking long documents and code files without truncation
- **ModernBERT architecture** provides 2-3× faster inference than BERT-family per parameter
- Legacy MiniLM remains available via `RERANK_MODEL` env var — no forced migration

### Negative

- **~7× larger download** (151MB int8 vs 23MB) on first use
- **Threshold scaling may need recalibration** — the ÷30 factor was calibrated for MiniLM logits
- **No ARM-tuned ONNX variant** — relies on standard int8 quantisation (works cross-platform but lacks the ARM-specific optimisation MiniLM ships)

### Neutral

- The ONNX Runtime inference path, singleton pattern, and graceful fallback are unchanged
- Sigmoid normalisation continues to apply; only the raw logit distribution may differ

## Alternatives Considered

- **`Qwen3-Reranker-0.6B`** (600M, GGUF): Higher multilingual quality but requires llama-server, 10-20× higher latency, causal LM architecture incompatible with the current ONNX pipeline.
- **`bge-reranker-v2-m3`** (568M): Good multilingual quality but 4× larger, no ModernBERT speed advantage.
- **`jina-reranker-v2-base-multilingual`**: Good quality but Jina licence (not Apache 2.0).
- **HuggingFace Ettin 68M**: Nearly matches Qwen3-0.6B on MTEB at 1/9th params, but very new with limited community validation.

## References

- OpenSpec change: `openspec/changes/swap-reranker-to-gte-modernbert/`
- NiftyPM task: AIE-20
- Experiment 10: `experiments/10-reranker-degradation-2026-06-XX/` (MiniLM degrades technical retrieval)
- ADR-005: Cross-Encoder Reranker with ONNX Runtime
- ADR-019: Disable Reranker for Technical Workloads
- ADR-021: Reranker Inference Optimisation (÷30 threshold scaling)
- Benchmark: arXiv:2603.11991 (BTZSC, +47% F1 over MiniLM)
