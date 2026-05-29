## Purpose

Define optional cross-encoder reranking, score filtering, model loading, and runtime configuration for improving retrieval result precision.

## Requirements

### Requirement: cross-encoder re-ranking for precision

The system SHALL provide an optional cross-encoder reranker that re-scores
initial vector search results to improve retrieval precision. When reranking
is enabled, the system SHALL fetch a configurable larger candidate pool from
vector search before reranking, and SHALL return the top `top_k` results after
reranking.

#### Scenario: basic reranking with configurable pool
- **GIVEN** documents have been indexed into the vector store
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the system SHALL retrieve `max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)` candidates from vector search
- **AND** pass them through the cross-encoder reranker
- **AND** return the top `top_k` results reordered by reranker score

#### Scenario: default pool is at least 50 candidates
- **GIVEN** documents have been indexed
- **AND** `RERANK_MAX_FETCH` and `RERANK_FETCH_MULTIPLIER` use defaults
- **WHEN** `search_documents` is called with `rerank=True` and `top_k=5`
- **THEN** the candidate pool sent to the reranker SHALL contain at least 50 candidates subject to availability in the collection

#### Scenario: small collection returns all available candidates
- **GIVEN** a collection has fewer chunks than the configured fetch pool
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the reranker SHALL receive all available chunks (`min(fetch_k, collection.count())`)
- **THEN** reranking SHALL succeed without padding or error

#### Scenario: rerank pool latency stays within target
- **GIVEN** the existing reranker calibration corpus from `experiments/reranker-threshold-calibration-2026-05-12/`
- **WHEN** the calibration script is re-run with default `RERANK_FETCH_MULTIPLIER` and `RERANK_MAX_FETCH`
- **THEN** post-warmup P95 latency for `rerank=True` SHALL be at most 500 ms on the operator's hardware
- **THEN** the measured P95 SHALL be recorded in the experiment results
- **THEN** if P95 exceeds 500 ms, the defaults SHALL be lowered until the criterion is met

#### Scenario: reranking disabled (default)
- **GIVEN** documents have been indexed into the vector store
- **WHEN** `search_documents` is called without `rerank` (or `rerank=False`)
- **THEN** the system SHALL return results from vector search only, unchanged
- **THEN** the configurable rerank pool SHALL NOT apply

#### Scenario: reranker model unavailable
- **GIVEN** the ONNX reranker model is not downloaded or fails to load
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the system SHALL fall back to un-reranked results trimmed to `top_k`
- **AND** emit a warning log (not crash)

#### Scenario: reranked results have different scores
- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the `score` field in results SHALL reflect the reranker's score
- **AND** the score SHALL differ from the raw vector similarity score

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
- **THEN** it SHALL prefer `model_qint8_arm64.onnx` (~23 MB quantised variant)
- **AND** fall back to `model.onnx` if the ARM variant is unavailable

#### Scenario: module docstring reflects correct model
- **GIVEN** `reranker.py` is loaded
- **WHEN** the module docstring is read
- **THEN** it SHALL reference `cross-encoder/ms-marco-MiniLM-L-6-v2`
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

The system SHALL support the following environment variables for reranker
configuration, with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | HuggingFace model ID for reranker |
| `RERANK_ENABLED` | `false` | Default rerank behaviour for `search_documents` |
| `SIMILARITY_THRESHOLD` | `0.0` | Default minimum score to include a result |
| `RERANK_FETCH_MULTIPLIER` | `10` | Multiplier applied to `top_k` when reranking is enabled |
| `RERANK_MAX_FETCH` | `50` | Lower bound on the rerank candidate pool size |

#### Scenario: env vars set defaults
- **GIVEN** `SIMILARITY_THRESHOLD=0.25` is set in `.env`
- **WHEN** `search_documents` is called with no explicit threshold
- **THEN** results with `score < 0.25` SHALL be filtered out

#### Scenario: rerank pool sizing env vars apply
- **GIVEN** `RERANK_FETCH_MULTIPLIER=4` and `RERANK_MAX_FETCH=20` are set
- **WHEN** `search_documents` is called with `rerank=True` and `top_k=3`
- **THEN** the reranker SHALL receive `max(20, 3 * 4) = 20` candidates

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
