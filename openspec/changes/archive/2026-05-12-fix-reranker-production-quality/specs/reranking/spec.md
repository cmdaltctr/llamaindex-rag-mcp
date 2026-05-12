## MODIFIED Requirements

These requirements modify the existing `reranking` capability from the
`add-advanced-rag-features` change.

### Requirement: ONNX inference via optimum (replaces sentence-transformers)

The reranker SHALL use `optimum.onnxruntime.ORTModelForSequenceClassification`
for ONNX inference instead of `sentence_transformers.CrossEncoder`, removing
the PyTorch runtime dependency.

#### Scenario: ONNX model loads successfully
- **GIVEN** the reranker model ID is `cross-encoder/ms-marco-MiniLM-L-6-v2`
- **WHEN** the reranker initialises for the first time
- **THEN** the system SHALL load the model via
  `ORTModelForSequenceClassification.from_pretrained(MODEL_ID, export=True)`
- **AND** the tokenizer SHALL be loaded via
  `AutoTokenizer.from_pretrained(MODEL_ID)`
- **AND** no `sentence_transformers` or `torch` import SHALL occur

#### Scenario: ONNX export on first load
- **GIVEN** the model has not been previously cached as ONNX
- **WHEN** the reranker initialises
- **THEN** `export=True` SHALL trigger automatic ONNX conversion
- **AND** the ONNX model SHALL be cached for subsequent loads

### Requirement: singleton recovery from transient failures

The reranker singleton SHALL recover from transient model-load failures,
rather than permanently disabling itself after the first failure.

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

### Requirement: correct model name in documentation

The module docstring in `reranker.py` SHALL reference the correct model
identifier.

#### Scenario: docstring reflects actual model
- **GIVEN** `reranker.py` is loaded
- **WHEN** the module docstring is read
- **THEN** it SHALL reference `cross-encoder/ms-marco-MiniLM-L-6-v2`
- **AND** it SHALL NOT reference `Xenova/ms-marco-MiniLM-L-6-v2`

### Requirement: no PyTorch at runtime

The `sentence-transformers` package SHALL be removed from `pyproject.toml`
dependencies. No `torch` import SHALL occur at runtime.

#### Scenario: dependency audit
- **GIVEN** the project's `pyproject.toml`
- **WHEN** the dependencies list is inspected
- **THEN** `sentence-transformers` SHALL NOT be listed
- **AND** `torch` SHALL NOT be a direct or transitive runtime dependency
  (only `optimum`, `onnxruntime`, and `transformers` for tokenisation)
