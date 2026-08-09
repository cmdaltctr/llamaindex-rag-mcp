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

The reranker SHALL distinguish a transient failure from a persistent one by
tracking consecutive failures with the same error signature. Below the
escalation threshold, a failure SHALL log at WARNING as today. At or above
the threshold, the failure SHALL log at ERROR instead, so a persistently
broken provider stops being indistinguishable from an occasional transient
hiccup in the logs. The escalation SHALL NOT change the fallback behaviour —
retrieval SHALL still return un-reranked results and SHALL NOT raise.

The test reset hook (`CrossEncoderReranker._instance = None`) SHALL either be
preserved in an equivalent form (e.g. a cache-reset function) or be
deliberately retired with every affected test updated; it SHALL NOT be
silently dropped. The consecutive-failure counter SHALL reset alongside the
model cache so tests remain isolated.

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
- **AND** SHALL emit a log on each failed attempt — at WARNING below the
  escalation threshold, at ERROR at or above it
- **AND** SHALL NOT crash or raise an exception

#### Scenario: persistent failure escalates to ERROR after the threshold
- **GIVEN** the reranker has failed with the same error signature on N
  consecutive calls, where N is the configured escalation threshold
- **WHEN** the reranker fails again with the same error signature
- **THEN** the system SHALL log at ERROR level instead of WARNING
- **AND** SHALL still fall back to un-reranked results without raising

#### Scenario: a successful call resets the consecutive-failure counter
- **GIVEN** the reranker has failed one or more consecutive times
- **WHEN** a subsequent call succeeds
- **THEN** the consecutive-failure counter SHALL reset to zero
- **AND** the next failure (if any) SHALL log at WARNING, not ERROR

#### Scenario: test isolation preserved
- **GIVEN** a test suite that resets reranker state between cases
- **WHEN** the reset hook (or its replacement) is invoked
- **THEN** no reranker state, including the consecutive-failure counter,
  MUST leak across test cases

### Requirement: reranked provenance flag

Each search result SHALL include a `reranked` boolean field indicating whether
the cross-encoder reranker was successfully applied.

When `include_diagnostics=True` and reranking was requested but did not
apply because the reranker failed (transient or persistent), the diagnostic
`rerank_reason` field SHALL explain the failure rather than only a policy
skip reason. This makes a broken reranker distinguishable from a
policy-driven skip without grepping logs.

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

#### Scenario: failure reason surfaced in diagnostics
- **GIVEN** the reranker model fails to load
- **WHEN** `search_documents` is called with `rerank=True` and
  `include_diagnostics=True`
- **THEN** the `rerank_reason` diagnostic field SHALL describe the failure
  (e.g. identify it as a load or inference failure), not only a policy
  decision string

## ADDED Requirements

### Requirement: ONNX execution provider selection

The reranker SHALL select its ONNX Runtime execution provider via
`RERANK_ONNX_PROVIDER`, defaulting to CPU. CoreML SHALL only be used when
explicitly requested and available on the current platform, since CoreML's
static graph compilation cannot handle the variable sequence lengths
produced by cross-encoder tokenisation (ADR-029).

#### Scenario: default provider is CPU
- **GIVEN** `RERANK_ONNX_PROVIDER` is unset
- **WHEN** the reranker model loads
- **THEN** the ONNX session SHALL use `CPUExecutionProvider` only

#### Scenario: CoreML opt-in when available
- **GIVEN** `RERANK_ONNX_PROVIDER=coreml` is set
- **AND** `CoreMLExecutionProvider` is in the platform's available providers
- **WHEN** the reranker model loads
- **THEN** the ONNX session SHALL use `CoreMLExecutionProvider` with
  `CPUExecutionProvider` as a fallback provider

#### Scenario: CoreML requested but unavailable falls back to CPU
- **GIVEN** `RERANK_ONNX_PROVIDER=coreml` is set
- **AND** `CoreMLExecutionProvider` is NOT in the platform's available
  providers
- **WHEN** the reranker model loads
- **THEN** the ONNX session SHALL use `CPUExecutionProvider` only
