## MODIFIED Requirements

### Requirement: ONNX inference via pure onnxruntime

The reranker SHALL use `onnxruntime.InferenceSession` for ONNX inference
with `transformers.AutoTokenizer` for tokenisation, removing all PyTorch
runtime dependencies. Pre-exported ONNX models are downloaded from
HuggingFace Hub.

#### Scenario: ONNX model loads successfully
- **GIVEN** the reranker model ID is `Alibaba-NLP/gte-reranker-modernbert-base`
- **WHEN** the reranker initialises for the first time
- **THEN** the system SHALL load the model via `onnxruntime.InferenceSession`
- **AND** the tokenizer SHALL be loaded via `AutoTokenizer.from_pretrained()`
- **AND** no `sentence_transformers`, `torch`, or `optimum` import SHALL occur

#### Scenario: platform-aware ONNX variant selection
- **GIVEN** the reranker is running on macOS ARM
- **WHEN** the reranker downloads the ONNX model
- **THEN** it SHALL prefer `onnx/model.onnx` (fp32) for `gte-reranker-modernbert-base`
- **AND** fall back to `onnx/model.onnx` if no platform-specific variant is available
- **AND** for models that ship ARM-quantised variants (e.g. `cross-encoder/ms-marco-MiniLM-L-6-v2`), it SHALL still prefer the quantised variant

#### Scenario: module docstring reflects correct model
- **GIVEN** `reranker.py` is loaded
- **WHEN** the module docstring is read
- **THEN** it SHALL reference `Alibaba-NLP/gte-reranker-modernbert-base` as the default
- **AND** it SHALL NOT reference `cross-encoder/ms-marco-MiniLM-L-6-v2` as the default

### Requirement: reranker configuration via environment

The system SHALL support the following environment variables for reranker configuration, with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `RERANK_MODEL` | `Alibaba-NLP/gte-reranker-modernbert-base` | HuggingFace model ID for reranker |
| `RERANK_ENABLED` | `false` | Global default rerank behaviour for omitted rerank requests |
| `RERANK_ENABLED_FOR_SEMANTIC` | `true` | Policy knob allowing omitted rerank requests to enable reranking for semantic workloads below the technical threshold |
| `HARD_TECHNICAL_THRESHOLD` | `0.3` | Identifier-heavy workload fraction at or above which semantic policy reranking SHALL NOT be enabled |
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

#### Scenario: semantic policy env vars are exposed
- **GIVEN** `RERANK_ENABLED_FOR_SEMANTIC=true` and `HARD_TECHNICAL_THRESHOLD=0.3` are set
- **WHEN** the effective rerank policy resolver is called for an omitted rerank request
- **THEN** the resolver SHALL consider those values when deciding whether policy reranking is allowed

#### Scenario: explicit rerank bypasses semantic policy env vars
- **GIVEN** `RERANK_ENABLED_FOR_SEMANTIC=false`
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** reranking SHALL be applied regardless of the semantic policy setting

### Requirement: cross-encoder re-ranking for precision

The system SHALL provide an optional cross-encoder reranker that re-scores
initial vector search results to improve retrieval precision. When reranking
is enabled and hybrid retrieval is also enabled, the reranker SHALL receive
the fused dense+sparse candidate list. When reranking is enabled and hybrid
retrieval is disabled, the reranker SHALL receive the dense-only candidate
list. The fetch pool size SHALL be governed by `RERANK_MAX_FETCH` and
`RERANK_FETCH_MULTIPLIER` regardless of whether hybrid retrieval is active.
The tokenizer `max_length` SHALL default to 2048 tokens to leverage the
larger context window of ModernBERT-based rerankers while bounding latency.

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
