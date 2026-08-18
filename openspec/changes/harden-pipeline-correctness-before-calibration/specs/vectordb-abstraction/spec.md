## MODIFIED Requirements

### Requirement: Vector-store dense queries return canonical scored rows

The `VectorStore.query_dense()` contract SHALL return store-neutral result rows whose `score` is higher-is-better and conforms to the canonical dense score contract defined by `retrieval-score-semantics`. Backend-native distance fields MAY be retained only as optional diagnostics; core retrieval SHALL NOT require them to compute public relevance scores.

#### Scenario: Chroma adapter owns Chroma metric conversion
- **WHEN** ChromaDB returns its native distance representation
- **THEN** `core/vectordb/chroma.py` SHALL convert it to the canonical dense score before returning the store-neutral row
- **AND** `core/retrieval/dense.py` SHALL not apply a Chroma-specific formula

#### Scenario: Lance adapter owns Lance metric conversion
- **WHEN** LanceDB returns `_distance` or another native score
- **THEN** the Lance adapter SHALL convert it to the same declared canonical score semantics before core retrieval consumes it

### Requirement: Registered vector stores pass differential semantic contract tests

Every registered production vector store SHALL run against the same deterministic contract fixtures for dense ranking, score semantics, metadata filtering, mutations, generation invalidation, collection metadata and precomputed upsert where supported. Passing the ABC type/interface is not sufficient evidence of swappability.

#### Scenario: New backend registration
- **GIVEN** a new vector store is registered
- **WHEN** CI runs the vector-store semantic contract suite
- **THEN** the backend MUST satisfy the shared behavioural fixtures before it is considered production-swappable

### Requirement: Generation counters are store-owned mutation state

Each vector-store instance SHALL own and advance its collection generation counter exactly once for every successful mutation that changes sparse-visible state. Callers SHALL NOT be required to remember an additional generation bump after invoking a mutating store method.

#### Scenario: Direct write and orchestrated write match
- **GIVEN** the same store mutation is invoked directly in a contract test and through production orchestration
- **WHEN** each operation succeeds from generation `g`
- **THEN** generation SHALL become `g+1` in both cases
- **AND** the orchestration path SHALL NOT end at `g+2`

### Requirement: Store identity can namespace process-local derivative caches

The vector-store abstraction SHALL provide or permit a stable process-local identity token suitable for namespacing derivative caches such as BM25. The identity need not persist across process restarts and MUST NOT expose credentials.

#### Scenario: Two stores share a collection name
- **GIVEN** two distinct store instances each expose collection `documents`
- **WHEN** a process-local derivative cache is constructed
- **THEN** the cache key SHALL be able to distinguish the two stores

### Requirement: Embedding-provider swappability scope is explicit

The current production composition model SHALL document embedding-provider selection as deployment/process-scoped while LlamaIndex's embed model remains process-global. The vector-store abstraction MUST NOT imply safe concurrent per-collection embedding-provider switching that the runtime does not implement.

#### Scenario: Different deployment provider
- **WHEN** a process starts with a different registered embedding provider
- **THEN** the composition root MAY construct the new provider and stores SHALL operate through the same contract

#### Scenario: Concurrent per-collection provider request
- **WHEN** callers attempt to assume collection A and collection B can simultaneously use different process-global embed models
- **THEN** documentation/tests SHALL make that unsupported boundary explicit until a future design removes the global dependency
