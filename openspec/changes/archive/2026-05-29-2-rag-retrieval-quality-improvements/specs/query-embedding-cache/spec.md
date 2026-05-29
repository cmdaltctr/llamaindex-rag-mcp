## ADDED Requirements

### Requirement: Query embedding cache reduces repeat Ollama calls
The system SHALL cache recent query embeddings in process so that repeated identical queries do not re-issue the embedding request to Ollama. The cache SHALL be keyed by `(query, embedding_model_name)` and SHALL be bounded in size. The cache SHALL apply uniformly across every retrieval branch in `search()` — both the metadata-filtered direct-ChromaDB path and the unfiltered path. An implementation that only catches one branch SHALL NOT satisfy this requirement.

#### Scenario: Repeated identical query hits cache (unfiltered)
- **GIVEN** the embedding model is configured
- **WHEN** the same `search_documents(query="X")` call is made twice in succession with no `metadata_filter`
- **THEN** the embedding for `"X"` SHALL be computed only once
- **THEN** the second call SHALL reuse the cached embedding

#### Scenario: Repeated identical query hits cache (filtered)
- **GIVEN** the embedding model is configured
- **WHEN** the same `search_documents(query="X", metadata_filter={"category": "ai"})` call is made twice in succession
- **THEN** the embedding for `"X"` SHALL be computed only once
- **THEN** the second call SHALL reuse the cached embedding

#### Scenario: Cache is shared between filtered and unfiltered calls
- **GIVEN** the embedding model is configured
- **WHEN** `search_documents(query="X")` is called, then `search_documents(query="X", metadata_filter={"category": "ai"})` is called immediately after
- **THEN** the embedding for `"X"` SHALL be computed only once across the two calls

#### Scenario: Different queries do not collide
- **WHEN** two different queries are embedded
- **THEN** the cache SHALL store both entries
- **THEN** each query SHALL receive its own embedding

#### Scenario: Cache is bounded
- **WHEN** more than the configured `maxsize` distinct queries are embedded
- **THEN** the cache SHALL evict the least-recently-used entries
- **THEN** memory usage SHALL not grow unbounded
