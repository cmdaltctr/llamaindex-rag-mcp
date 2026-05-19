## ADDED Requirements

### Requirement: Concurrent embedding dispatcher
The system SHALL support dispatching multiple embedding batches concurrently to Ollama's `/api/embed` endpoint when `EMBED_CONCURRENCY > 1`.

#### Scenario: Sequential dispatch (default)
- **WHEN** `EMBED_CONCURRENCY=1`
- **THEN** the system SHALL send one batch at a time to Ollama (current behaviour)

#### Scenario: Concurrent dispatch
- **WHEN** `EMBED_CONCURRENCY=2`
- **AND** there are more than `EMBED_BATCH_SIZE` chunks to embed
- **THEN** the system SHALL split chunks into batches and dispatch them concurrently across up to `EMBED_CONCURRENCY` workers
- **THEN** the system SHALL wait for all batches to complete before writing to ChromaDB

### Requirement: Concurrency safety
The concurrent dispatcher SHALL NOT write partial results to ChromaDB if any concurrent batch fails.

#### Scenario: All-or-nothing write
- **WHEN** two embedding batches run concurrently
- **AND** one batch fails
- **THEN** the ChromaDB collection SHALL NOT be modified
- **THEN** the system SHALL return an error status

### Requirement: Backward compatibility
The concurrent embedding feature SHALL be optional and opt-in via environment variable.

#### Scenario: Default is sequential
- **WHEN** `EMBED_CONCURRENCY` is not set or set to `1`
- **THEN** the system SHALL behave identically to the current sequential embedding pipeline
