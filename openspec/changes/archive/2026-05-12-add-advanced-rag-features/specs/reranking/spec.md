## ADDED Requirements

### Requirement: cross-encoder re-ranking for precision

The system SHALL provide an optional cross-encoder reranker that re-scores
initial vector search results to improve retrieval precision.

#### Scenario: basic reranking
- **GIVEN** documents have been indexed into the vector store
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the system SHALL retrieve `top_k × 2` candidates from vector search
- **AND** pass them through the cross-encoder reranker
- **AND** return the top `top_k` results reordered by reranker score

#### Scenario: reranking disabled (default)
- **GIVEN** documents have been indexed into the vector store
- **WHEN** `search_documents` is called without `rerank` (or `rerank=False`)
- **THEN** the system SHALL return results from vector search only, unchanged

#### Scenario: reranker model unavailable
- **GIVEN** the ONNX reranker model is not downloaded or fails to load
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the system SHALL fall back to un-reranked results
- **AND** emit a warning log (not crash)

#### Scenario: reranked results have different scores
- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the `score` field in results SHALL reflect the reranker's score
- **AND** the score SHALL differ from the raw vector similarity score

### Requirement: similarity threshold filtering

The system SHALL provide a configurable similarity threshold to filter out
low-confidence results.

#### Scenario: threshold filters low scores
- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called with `similarity_threshold=0.5`
- **THEN** any chunk with `score < 0.5` SHALL be excluded from results

#### Scenario: aggressive threshold returns empty
- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called with `similarity_threshold=0.99`
- **THEN** the system MAY return zero results (empty list)

#### Scenario: threshold of 0.0 includes all (default)
- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called without `similarity_threshold`
- **THEN** all chunks from vector search SHALL be returned (no filtering)

### Requirement: reranker configuration via environment

The system SHALL support the following environment variables for reranker
configuration, with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `RERANK_MODEL` | `Xenova/ms-marco-MiniLM-L-6-v2` | HuggingFace model ID for reranker |
| `RERANK_ENABLED` | `false` | Default rerank behaviour for `search_documents` |
| `SIMILARITY_THRESHOLD` | `0.0` | Default minimum score to include a result |

#### Scenario: env vars set defaults
- **GIVEN** `SIMILARITY_THRESHOLD=0.25` is set in `.env`
- **WHEN** `search_documents` is called with no explicit threshold
- **THEN** results with `score < 0.25` SHALL be filtered out

### Requirement: reranker as singleton

The reranker model SHALL be loaded once and reused across calls (singleton
pattern) to avoid repeated model loading overhead.

#### Scenario: repeated calls reuse model
- **GIVEN** the reranker has been loaded once
- **WHEN** `search_documents` is called with `rerank=True` multiple times
- **THEN** the model SHALL NOT be re-loaded on subsequent calls
