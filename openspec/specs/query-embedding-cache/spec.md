## Purpose

Define the process-local query embedding cache used by retrieval to avoid
repeat Ollama embedding calls for identical queries across filtered and
unfiltered search paths.

## Requirements

### Requirement: Query embedding cache reduces repeat Ollama calls

The system SHALL cache recent query embeddings so that repeated identical
queries do not re-issue the embedding request to Ollama. The cache SHALL be
keyed by `(query, embedding_model_name)` and SHALL be bounded in size. The
cache SHALL apply uniformly across every retrieval branch in an engine's
`search()` — both the metadata-filtered path and the unfiltered path. An
implementation that only catches one branch SHALL NOT satisfy this
requirement.

Ownership moves from a process-local module cache to engine-local state:
entries SHALL be shared between the filtered and unfiltered searches of one
engine, SHALL NEVER be shared between separate engines in one process, and
SHALL be released when the owning engine is closed.

#### Scenario: Repeated identical query hits cache (unfiltered)

- **GIVEN** the embedding model is configured
- **WHEN** the same `search(query="X")` call is made twice in succession with no `metadata_filter`
- **THEN** the embedding for `"X"` SHALL be computed only once
- **THEN** the second call SHALL reuse the cached embedding

#### Scenario: Repeated identical query hits cache (filtered)

- **GIVEN** the embedding model is configured
- **WHEN** the same `search(query="X", metadata_filter={"category": "ai"})` call is made twice in succession
- **THEN** the embedding for `"X"` SHALL be computed only once
- **THEN** the second call SHALL reuse the cached embedding

#### Scenario: Cache is shared between filtered and unfiltered calls

- **GIVEN** the embedding model is configured
- **WHEN** `search(query="X")` is called, then `search(query="X", metadata_filter={"category": "ai"})` is called immediately after on the same engine
- **THEN** the embedding for `"X"` SHALL be computed only once across the two calls

#### Scenario: Cache is not shared between engines

- **GIVEN** two engines in one process whose embedders report the same model name
- **WHEN** each engine embeds the same query
- **THEN** each engine SHALL compute its own embedding
- **AND** neither engine SHALL serve an entry cached by the other

#### Scenario: Different queries do not collide

- **WHEN** two different queries are embedded
- **THEN** the cache SHALL store both entries
- **THEN** each query SHALL receive its own embedding

#### Scenario: Cache is bounded

- **WHEN** more than the configured `maxsize` distinct queries are embedded
- **THEN** the cache SHALL evict the least-recently-used entries
- **THEN** memory usage SHALL not grow unbounded

#### Scenario: Cache is released with its engine

- **WHEN** an engine is closed
- **THEN** its query-embedding cache SHALL be released
- **AND** other engines' caches SHALL remain intact
