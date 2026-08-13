## ADDED Requirements

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
