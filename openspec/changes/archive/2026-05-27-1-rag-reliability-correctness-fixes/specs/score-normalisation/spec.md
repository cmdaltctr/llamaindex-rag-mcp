## ADDED Requirements

### Requirement: non-reranked vector scores use a single conversion formula
The system SHALL convert ChromaDB L2 distances to similarity scores on every non-reranked retrieval path using the formula `score = 1.0 / (1.0 + distance)`. The metadata-filtered direct-ChromaDB path and the unfiltered LlamaIndex-backed path SHALL produce equal pre-threshold scores (within a numerical tolerance of `1e-6`) for the same `(query, chunk)` pair. Reranker scores are out of scope for this requirement and continue to use the sigmoid-normalised cross-encoder scale with the calibrated ÷30 threshold scaling.

#### Scenario: Same chunk yields equal score on both paths
- **GIVEN** a chunk indexed with category metadata
- **WHEN** an unfiltered search and a metadata-filtered search both return that chunk
- **THEN** the pre-threshold `score` field SHALL be equal within `1e-6`
- **THEN** both `score` values SHALL equal `1.0 / (1.0 + distance)` for the underlying ChromaDB L2 distance

#### Scenario: Equivalent filtered and unfiltered threshold behaviour
- **GIVEN** documents have been indexed with category metadata
- **WHEN** an unfiltered search and an equivalent metadata-filtered search are run with the same `similarity_threshold`
- **THEN** both paths SHALL apply the threshold against scores produced by the same `1.0 / (1.0 + distance)` formula
- **THEN** no result with `score < similarity_threshold` SHALL be returned from either path

#### Scenario: Reranker scaling is unaffected
- **WHEN** `rerank=True` is set on either retrieval path
- **THEN** the calibrated ÷30 threshold scaling SHALL still apply
- **THEN** the score conversion in this requirement SHALL NOT alter reranker output
