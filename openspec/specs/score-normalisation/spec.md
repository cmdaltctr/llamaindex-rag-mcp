## Requirements

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
