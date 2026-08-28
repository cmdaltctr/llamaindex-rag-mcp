## Purpose

Define how similarity scores are computed and normalised so that
`similarity_threshold` behaves consistently across all retrieval paths
and reranking states.

## Requirements

### Requirement: non-reranked vector scores use a single conversion formula

The system SHALL convert ChromaDB L2 distances to similarity scores on
every non-reranked retrieval path using the formula
`score = 1.0 / (1.0 + distance)`. The metadata-filtered direct-ChromaDB
path and the unfiltered path SHALL produce equal pre-threshold scores
(within a numerical tolerance of `1e-6`) for the same `(query, chunk)`
pair. Reranker scores are out of scope for this requirement and continue
to use the sigmoid-normalised cross-encoder scale with the calibrated
÷30 threshold scaling.

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

### Requirement: sigmoid score normalisation for reranker

The system SHALL normalise cross-encoder reranker scores to a 0–1 range using
the sigmoid function so that `similarity_threshold` behaves consistently
regardless of whether reranking is active.

#### Scenario: reranker scores are normalised to 0–1
- **GIVEN** documents have been indexed
- **AND** the reranker model is available
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** every result's `score` SHALL be in the range (0.0, 1.0)
- **AND** scores SHALL be derived by applying `sigmoid(logit)` to the raw
  cross-encoder output

#### Scenario: normalised scores are comparable with vector scores
- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called first with `rerank=False` and then
  with `rerank=True` using the same `similarity_threshold=0.5`
- **THEN** the threshold SHALL filter results correctly in both cases
- **AND** no result with `score < 0.5` SHALL appear in either response

#### Scenario: ranking order preserved after normalisation
- **GIVEN** documents have been indexed
- **AND** the reranker produces raw logits `[-2.0, 3.5, 0.5]`
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the sigmoid-normalised scores SHALL be `[0.119, 0.970, 0.622]`
  (approximately)
- **AND** the result order SHALL be the same as sorting by raw logits
  (sigmoid is monotonic)

#### Scenario: normalisation applies only to reranker scores
- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called with `rerank=False` (default)
- **THEN** the `score` field SHALL be the raw vector cosine similarity
  from ChromaDB (no sigmoid applied)
