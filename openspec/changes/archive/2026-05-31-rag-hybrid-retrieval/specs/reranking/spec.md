## MODIFIED Requirements

### Requirement: cross-encoder re-ranking for precision

The system SHALL provide an optional cross-encoder reranker that re-scores
initial vector search results to improve retrieval precision. When reranking
is enabled and hybrid retrieval is also enabled, the reranker SHALL receive
the fused dense+sparse candidate list. When reranking is enabled and hybrid
retrieval is disabled, the reranker SHALL receive the dense-only candidate
list. The fetch pool size SHALL be governed by `RERANK_MAX_FETCH` and
`RERANK_FETCH_MULTIPLIER` regardless of whether hybrid retrieval is active.

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
