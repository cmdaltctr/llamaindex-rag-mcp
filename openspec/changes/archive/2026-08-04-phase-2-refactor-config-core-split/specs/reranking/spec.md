## MODIFIED Requirements

### Requirement: reranker as singleton with recovery

The reranker model SHALL be loaded once per process and reused across calls
to avoid repeated model loading overhead. The reranker SHALL be constructed
in `compose.py` (the composition root) as an injected dependency, with
process-wide model caching preserving the load-once behaviour of the former
`__new__` singleton. The reranker SHALL receive its settings (model ID,
enabled flag) via injection and SHALL NOT call `load_dotenv()` independently
of the settings resolver. The reranker SHALL recover from transient failures
rather than permanently disabling itself.

The test reset hook (`CrossEncoderReranker._instance = None`) SHALL either be
preserved in an equivalent form (e.g. a cache-reset function) or be
deliberately retired with every affected test updated; it SHALL NOT be
silently dropped.

#### Scenario: repeated calls reuse model
- **GIVEN** the reranker has been constructed and its model loaded once
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

#### Scenario: test isolation preserved
- **GIVEN** a test suite that resets reranker state between cases
- **WHEN** the reset hook (or its replacement) is invoked
- **THEN** no reranker state MUST leak across test cases
