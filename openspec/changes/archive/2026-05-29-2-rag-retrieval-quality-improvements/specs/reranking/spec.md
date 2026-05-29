## MODIFIED Requirements

### Requirement: cross-encoder re-ranking for precision

The system SHALL provide an optional cross-encoder reranker that re-scores
initial vector search results to improve retrieval precision. When reranking
is enabled, the system SHALL fetch a configurable larger candidate pool from
vector search before reranking, and SHALL return the top `top_k` results
after reranking.

#### Scenario: basic reranking with configurable pool
- **GIVEN** documents have been indexed into the vector store
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the system SHALL retrieve `max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)` candidates from vector search
- **AND** pass them through the cross-encoder reranker
- **AND** return the top `top_k` results reordered by reranker score

#### Scenario: default pool is at least 50 candidates
- **GIVEN** documents have been indexed
- **AND** `RERANK_MAX_FETCH` and `RERANK_FETCH_MULTIPLIER` use defaults
- **WHEN** `search_documents` is called with `rerank=True` and `top_k=5`
- **THEN** the candidate pool sent to the reranker SHALL contain at least 50 candidates (subject to availability in the collection)

#### Scenario: small collection returns all available candidates
- **GIVEN** a collection has fewer chunks than the configured fetch pool
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the reranker SHALL receive all available chunks (`min(fetch_k, collection.count())`)
- **THEN** reranking SHALL succeed without padding or error

#### Scenario: rerank pool latency stays within target
- **GIVEN** the existing reranker calibration corpus from `experiments/reranker-threshold-calibration-2026-05-12/`
- **WHEN** the calibration script is re-run with default `RERANK_FETCH_MULTIPLIER` and `RERANK_MAX_FETCH`
- **THEN** post-warmup P95 latency for `rerank=True` SHALL be at most 500 ms on the operator's hardware
- **THEN** the measured P95 SHALL be recorded in the experiment results
- **THEN** if P95 exceeds 500 ms, the defaults SHALL be lowered until the criterion is met

#### Scenario: reranking disabled (default)
- **GIVEN** documents have been indexed into the vector store
- **WHEN** `search_documents` is called without `rerank` (or `rerank=False`)
- **THEN** the system SHALL return results from vector search only, unchanged
- **THEN** the configurable rerank pool SHALL NOT apply

#### Scenario: reranker model unavailable
- **GIVEN** the ONNX reranker model is not downloaded or fails to load
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the system SHALL fall back to un-reranked results trimmed to `top_k`
- **AND** emit a warning log (not crash)

### Requirement: reranker configuration via environment

The system SHALL support the following environment variables for reranker
configuration, with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | HuggingFace model ID for reranker |
| `RERANK_ENABLED` | `false` | Default rerank behaviour for `search_documents` |
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
