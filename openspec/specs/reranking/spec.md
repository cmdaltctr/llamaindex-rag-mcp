## Purpose

Define optional cross-encoder reranking, score filtering, model loading, and runtime configuration for improving retrieval result precision.
## Requirements
### Requirement: Reranker candidate pool is configurable

The system SHALL keep reranker candidate-pool sizing configurable via `RERANK_MAX_FETCH` and `RERANK_FETCH_MULTIPLIER`. A realistic technical-workload calibration experiment SHALL evaluate whether the current defaults remain appropriate for technical documentation, especially when hybrid BM25/RRF retrieval is enabled.

#### Scenario: Technical workload calibration records reranker policy
- **GIVEN** a realistic technical-document benchmark with dense-only and hybrid retrieval modes
- **WHEN** reranker policies are evaluated
- **THEN** the experiment SHALL record the active `RERANK_ENABLED`, `RERANK_MAX_FETCH`, `RERANK_FETCH_MULTIPLIER`, reranker model, retrieval mode, and latency for each cell
- **THEN** the recommendation SHALL state whether reranking should remain default, become conditional, change pool size, or stay opt-in for technical workloads

### Requirement: Reranker can be evaluated independently from hybrid retrieval

The system SHALL support experiments that compare reranking on and off for both dense-only and hybrid retrieval without changing the underlying corpus or query set.

#### Scenario: Reranker on/off comparison
- **GIVEN** the same indexed corpus and query set
- **WHEN** dense-only and hybrid retrieval are each evaluated with reranking disabled and enabled
- **THEN** the experiment SHALL attribute quality changes separately to first-stage retrieval and reranker policy
- **THEN** the experiment SHALL fail loudly if completed cells cannot be distinguished by retrieval mode and reranker policy

### Requirement: cross-encoder re-ranking for precision

The system SHALL provide an optional cross-encoder reranker that re-scores
initial vector search results to improve retrieval precision. When reranking
is enabled and hybrid retrieval is also enabled, the reranker SHALL receive
the fused dense+sparse candidate list. When reranking is enabled and hybrid
retrieval is disabled, the reranker SHALL receive the dense-only candidate
list. The fetch pool size SHALL be governed by `RERANK_MAX_FETCH` and
`RERANK_FETCH_MULTIPLIER` regardless of whether hybrid retrieval is active.
The tokenizer `max_length` SHALL default to 2048 tokens to balance
context window utilisation with latency.

#### Scenario: Rerank over dense-only candidates
- **GIVEN** documents have been indexed
- **WHEN** `search_documents(query="X", rerank=True, hybrid=False)` is called
- **THEN** the system SHALL fetch dense-only candidates up to the configured fetch pool
- **THEN** the reranker SHALL re-score those candidates
- **THEN** the calibrated reranker score scaling SHALL be applied unchanged

#### Scenario: Rerank over hybrid candidates
- **GIVEN** documents have been indexed
- **WHEN** `search_documents(query="X", rerank=True, hybrid=True)` is called
- **THEN** the system SHALL run dense and sparse retrievers and fuse them via RRF
- **THEN** the top fused candidates up to the configured fetch pool SHALL be passed to the reranker
- **THEN** the calibrated reranker score scaling SHALL be applied unchanged

#### Scenario: Hybrid does not change reranker scoring semantics
- **WHEN** the same query is run with `hybrid=False, rerank=True` and `hybrid=True, rerank=True` against a corpus where dense retrieval already finds the correct chunk
- **THEN** the reranker SHALL produce equivalent reranker scores for that chunk in both runs (within numerical tolerance)
- **THEN** the calibrated reranker threshold scaling factor SHALL NOT require recalibration

#### Scenario: Reranker model unavailable with hybrid
- **GIVEN** the ONNX reranker model is not downloaded or fails to load
- **WHEN** `search_documents` is called with `rerank=True, hybrid=True`
- **THEN** the system SHALL fall back to fused (un-reranked) results trimmed to `top_k`
- **THEN** the system SHALL emit a warning log without crashing

### Requirement: ONNX inference via pure onnxruntime

The reranker SHALL use `onnxruntime.InferenceSession` for ONNX inference
with `transformers.AutoTokenizer` for tokenisation, removing all PyTorch
runtime dependencies. Pre-exported ONNX models are downloaded from
HuggingFace Hub.

#### Scenario: ONNX model loads successfully
- **GIVEN** the reranker model ID is `cross-encoder/ms-marco-MiniLM-L-6-v2`
- **WHEN** the reranker initialises for the first time
- **THEN** the system SHALL load the model via `onnxruntime.InferenceSession`
- **AND** the tokenizer SHALL be loaded via `AutoTokenizer.from_pretrained()`
- **AND** no `sentence_transformers`, `torch`, or `optimum` import SHALL occur

#### Scenario: platform-aware ONNX variant selection
- **GIVEN** the reranker is running on macOS ARM
- **WHEN** the reranker downloads the ONNX model
- **THEN** for the default model `cross-encoder/ms-marco-MiniLM-L-6-v2` on ARM64, it SHALL prefer `onnx/model_qint8_arm64.onnx` (~23 MB quantised variant)
- **AND** fall back to `onnx/model.onnx` if the ARM variant is unavailable
- **AND** for ModernBERT-based models (e.g. `Alibaba-NLP/gte-reranker-modernbert-base`), it SHALL prefer `onnx/model_quantized.onnx` (int8) with a fallback chain through `model_int8.onnx` → `model_fp16.onnx` → `model.onnx`

#### Scenario: module docstring reflects correct model
- **GIVEN** `reranker.py` is loaded
- **WHEN** the module docstring is read
- **THEN** it SHALL reference `cross-encoder/ms-marco-MiniLM-L-6-v2` as the default
- **AND** it SHALL NOT reference `Xenova/ms-marco-MiniLM-L-6-v2`

### Requirement: similarity threshold filtering

The system SHALL provide a configurable similarity threshold to filter out
low-confidence results.

#### Scenario: threshold filters low scores
- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called with `similarity_threshold=0.5`
- **THEN** any chunk with `score < 0.5` SHALL be excluded from results

#### Scenario: aggressive threshold returns empty
- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called with `similarity_threshold=0.99`
- **THEN** the system MAY return zero results (empty list)

#### Scenario: threshold of 0.0 includes all (default)
- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called without `similarity_threshold`
- **THEN** all chunks from vector search SHALL be returned (no filtering)

### Requirement: reranker configuration via environment

The system SHALL support the following environment variables for reranker configuration, with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | HuggingFace model ID for reranker |
| `RERANK_ENABLED` | `false` | Global default rerank behaviour for omitted rerank requests |
| `RERANK_ENABLED_FOR_SEMANTIC` | `true` | Policy knob allowing omitted rerank requests to enable reranking for semantic workloads below the technical threshold |
| `HARD_TECHNICAL_THRESHOLD` | `0.3` | Identifier-heavy workload fraction at or above which semantic policy reranking SHALL NOT be enabled |
| `SIMILARITY_THRESHOLD` | `0.0` | Default minimum score to include a result |
| `RERANK_FETCH_MULTIPLIER` | `3` | Multiplier applied to `top_k` when reranking is enabled |
| `RERANK_MAX_FETCH` | `100` | Lower bound on the rerank candidate pool size |

#### Scenario: env vars set defaults
- **GIVEN** `SIMILARITY_THRESHOLD=0.25` is set in `.env`
- **WHEN** `search_documents` is called with no explicit threshold
- **THEN** results with `score < 0.25` SHALL be filtered out

#### Scenario: rerank pool sizing env vars apply
- **GIVEN** `RERANK_FETCH_MULTIPLIER=4` and `RERANK_MAX_FETCH=20` are set
- **WHEN** `search_documents` is called with `rerank=True` and `top_k=3`
- **THEN** the reranker SHALL receive `max(20, 3 * 4) = 20` candidates

#### Scenario: semantic policy env vars are exposed
- **GIVEN** `RERANK_ENABLED_FOR_SEMANTIC=true` and `HARD_TECHNICAL_THRESHOLD=0.3` are set
- **WHEN** the effective rerank policy resolver is called for an omitted rerank request
- **THEN** the resolver SHALL consider those values when deciding whether policy reranking is allowed

#### Scenario: explicit rerank bypasses semantic policy env vars
- **GIVEN** `RERANK_ENABLED_FOR_SEMANTIC=false`
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** reranking SHALL be applied regardless of the semantic policy setting

### Requirement: reranker as singleton with recovery

The reranker model SHALL be loaded once and reused across calls (singleton
pattern) to avoid repeated model loading overhead. The singleton SHALL
recover from transient failures rather than permanently disabling itself.

#### Scenario: repeated calls reuse model
- **GIVEN** the reranker has been loaded once
- **WHEN** `search_documents` is called with `rerank=True` multiple times
- **THEN** the model SHALL NOT be re-loaded on subsequent calls

#### Scenario: retry after transient failure
- **GIVEN** the reranker model failed to load due to a transient error
  (e.g., network timeout downloading model weights)
- **WHEN** `search_documents` is called again with `rerank=True`
- **THEN** the system SHALL attempt to load the model again
- **AND** if the retry succeeds, results SHALL be reranked normally

#### Scenario: persistent failure still falls back gracefully
- **GIVEN** the reranker model is permanently unavailable (e.g., invalid
  model ID)
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the system SHALL fall back to un-reranked results
- **AND** SHALL emit a warning log on each failed attempt
- **AND** SHALL NOT crash or raise an exception

### Requirement: reranked provenance flag

Each search result SHALL include a `reranked` boolean field indicating whether
the cross-encoder reranker was successfully applied.

#### Scenario: reranking applied successfully
- **GIVEN** documents have been indexed
- **AND** the reranker model is available
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** every result dict SHALL include `"reranked": true`

#### Scenario: reranking disabled (default)
- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called without `rerank` (or `rerank=False`)
- **THEN** every result dict SHALL include `"reranked": false`

#### Scenario: reranking requested but model unavailable
- **GIVEN** documents have been indexed
- **AND** the reranker model fails to load
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** every result dict SHALL include `"reranked": false`
- **AND** scores SHALL be the original vector similarity scores

### Requirement: no PyTorch at runtime

The `sentence-transformers` and `optimum` packages SHALL NOT be runtime
dependencies. No `torch` import SHALL occur at runtime.

#### Scenario: dependency audit
- **GIVEN** the project's `pyproject.toml`
- **WHEN** the dependencies list is inspected
- **THEN** `sentence-transformers` SHALL NOT be listed
- **AND** `torch` SHALL NOT be a direct or transitive runtime dependency
- **AND** only `onnxruntime`, `transformers`, and `huggingface-hub` SHALL be
  used for reranker inference and model management

