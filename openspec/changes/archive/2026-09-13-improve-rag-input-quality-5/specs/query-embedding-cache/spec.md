## MODIFIED Requirements

### Requirement: Query embedding cache reduces repeat Ollama calls

The system SHALL cache recent query embeddings in engine-local state so that repeated identical **prepared query embedding inputs** do not re-issue the embedding request. The cache SHALL be keyed by `(prepared_query, embedding_model_name)` and SHALL be bounded in size. Query preparation includes any configured query-only instruction; therefore the same raw query prepared with two different instructions SHALL NOT collide.

Entries SHALL be shared between filtered and unfiltered searches of one engine, SHALL NEVER be shared between separate engines in one process, and SHALL be released when the owning engine is closed.

The cache SHALL apply uniformly across every retrieval branch in an engine's `search()`, including metadata-filtered and unfiltered paths. An implementation that caches only one branch SHALL NOT satisfy this requirement.

#### Scenario: Repeated identical query hits cache (unfiltered)

- **GIVEN** the embedding model is configured
- **AND** the same query preparation settings remain active
- **WHEN** the same `search_documents(query="X")` call is made twice in succession with no `metadata_filter`
- **THEN** the prepared embedding input for `"X"` SHALL be computed/embedded only once
- **AND** the second call SHALL reuse the cached embedding

#### Scenario: Repeated identical query hits cache (filtered)

- **GIVEN** the embedding model is configured
- **AND** the same query preparation settings remain active
- **WHEN** the same `search_documents(query="X", metadata_filter={"category": "ai"})` call is made twice in succession
- **THEN** the prepared embedding input for `"X"` SHALL be embedded only once
- **AND** the second call SHALL reuse the cached embedding

#### Scenario: Cache is shared between filtered and unfiltered calls

- **GIVEN** the embedding model is configured
- **AND** query preparation produces the same embedding input in both calls
- **WHEN** `search_documents(query="X")` is called, then `search_documents(query="X", metadata_filter={"category": "ai"})` is called immediately after
- **THEN** the prepared query embedding SHALL be computed only once across the two calls

#### Scenario: Different queries do not collide

- **WHEN** two different prepared query embedding inputs are embedded
- **THEN** the cache SHALL store both entries
- **AND** each prepared query SHALL receive its own embedding

#### Scenario: Different instructions do not collide

- **GIVEN** the raw query is `"X"`
- **WHEN** it is embedded once with no instruction and once with a non-empty instruction
- **THEN** the two prepared query strings SHALL produce distinct cache identities
- **AND** the second call SHALL NOT reuse the first call's vector solely because the raw query text matches

#### Scenario: Cache is bounded

- **WHEN** more than the configured `maxsize` distinct prepared query/model pairs are embedded
- **THEN** the cache SHALL evict least-recently-used entries
- **AND** memory usage SHALL NOT grow unbounded

#### Scenario: Cache is not shared between engines

- **GIVEN** two engines in one process whose embedders report the same model name
- **WHEN** each engine embeds the same query
- **THEN** each engine SHALL compute its own embedding
- **AND** neither engine SHALL serve an entry cached by the other

#### Scenario: Cache is released with its engine

- **WHEN** an engine is closed
- **THEN** its query-embedding cache SHALL be released
- **AND** other engines' caches SHALL remain intact
