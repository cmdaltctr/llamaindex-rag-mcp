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

### Requirement: Threshold scaling follows rerank outcome, not rerank intent

The calibrated ÷30 threshold scaling exists because cross-encoder sigmoid
scores occupy a much lower range than cosine similarity. It SHALL therefore
be applied only when the returned scores are actually reranker scores — that
is, when reranking was requested **and succeeded**. When reranking was
requested but did not apply (the reranker failed to load, or inference
failed, and results carry `reranked: false`), the scores are unchanged cosine
similarities and the threshold SHALL be applied unscaled.

Applying the scaling to un-reranked cosine scores makes filtering roughly
30× too permissive, admitting noise the caller's `similarity_threshold` was
meant to exclude. Because a reranker failure is already silent by design
(retrieval still returns results), this compounds an invisible failure with
an invisible loss of filtering — the same silent-degradation class this
capability exists to prevent.

The scaling **factor** itself is unchanged and remains empirically calibrated;
only the condition under which it is applied changes.

#### Scenario: Successful reranking scales the threshold

- **GIVEN** documents have been indexed and the reranker is available
- **WHEN** a search runs with `rerank=True` and `similarity_threshold=0.3`
- **THEN** the effective threshold applied to reranker scores SHALL be the
  ÷30-scaled value

#### Scenario: Failed reranking does not scale the threshold

- **GIVEN** the reranker fails to load or its inference raises
- **WHEN** a search runs with `rerank=True` and `similarity_threshold=0.3`
- **THEN** the returned results SHALL carry `reranked: false`
- **THEN** the effective threshold SHALL be the unscaled `0.3`, because the
  scores being filtered are cosine similarities, not reranker scores

#### Scenario: Reranking not requested does not scale the threshold

- **WHEN** a search runs with `rerank=False` and `similarity_threshold=0.3`
- **THEN** the effective threshold SHALL be the unscaled `0.3`

