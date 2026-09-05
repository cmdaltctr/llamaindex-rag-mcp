# vectordb-abstraction Specification

## Purpose
Defines the VectorStore abstract contract that every backend
implements, with ChromaDB's specific behaviours encoded honestly in the
contract rather than smeared across call sites. Store selection is
configuration; implementations may accept an injected client; and the
Chroma client construction keeps a single import boundary.

## Requirements
### Requirement: VectorStore abstract contract

The system SHALL define a `VectorStore` abstract base class in
`core/vectordb/base.py` covering every vector-store operation the pipeline
uses: collection creation, document write with upsert semantics, dense query
with metadata filtering, document deletion, collection metadata read and
update, and collection generation bumping. All pipeline code (ingestion
writer, retrieval pipeline) SHALL access the store only through this
interface, never through ChromaDB APIs directly.

#### Scenario: Contract covers all current operations

- **WHEN** the ABC is compared against the ChromaDB calls made by the
  pre-refactor pipeline
- **THEN** every operation in use MUST have a corresponding ABC method
- **AND** an integration test MUST verify the contract against the ChromaDB
  implementation

#### Scenario: Pipeline uses only the interface

- **WHEN** the codebase is searched for direct ChromaDB client usage outside
  `core/vectordb/`
- **THEN** no direct usage MUST remain in `core/ingestion/` or
  `core/retrieval/`

---

### Requirement: ChromaDB-specific behaviours encoded honestly

The interface SHALL explicitly model the ChromaDB behaviours the system
relies on — dimension locking at collection creation, metadata filter
syntax, and generation bumping for upsert semantics — as documented contract
behaviour rather than hidden implementation detail.

#### Scenario: Dimension locking

- **WHEN** a collection is created through the interface
- **THEN** the vector dimension MUST be fixed at creation time
- **AND** attempting to write vectors of a different dimension MUST fail with
  a clear error (ChromaDB dim-lock, ADR-003)

#### Scenario: Metadata filtering

- **WHEN** a query supplies a metadata filter
- **THEN** the implementation MUST translate it to the store's filter syntax
  (ChromaDB `where` clause) and return only matching results

#### Scenario: Generation bumping

- **WHEN** documents are upserted into an existing collection
- **THEN** the collection generation MUST be bumped exactly as the
  pre-refactor `_bump_collection_generation()` logic did

---

### Requirement: ChromaDB as first implementation

The system SHALL provide `core/vectordb/chroma.py` implementing the
`VectorStore` ABC, absorbing all logic from `chroma_utils.py` and the
ChromaDB-specific collection management formerly in the ingestion writer.
`chroma_utils.py` SHALL cease to exist as a top-level module.
`core/vectordb/chroma.py` SHALL be the **only** module in the package that
imports `chromadb` or constructs a ChromaDB client; every other consumer,
including the codebase map, SHALL go through the `VectorStore` interface.

#### Scenario: Single chromadb import site

- **WHEN** `src/omrg/` is searched for `import chromadb` or
  `chromadb.PersistentClient`
- **THEN** the only match MUST be in `core/vectordb/chroma.py`

#### Scenario: Codebase map goes through the interface

- **WHEN** the codebase map needs indexed-document information
- **THEN** it MUST call `VectorStore` methods on an injected store
- **AND** it MUST NOT create its own ChromaDB client or persist directory
  handle

#### Scenario: Existing collections keep working

- **WHEN** the server starts against an existing flat `chroma_persist_dir`
  (default `./chroma_db`) containing collections
- **THEN** all previously indexed collections MUST be readable and queryable
  with no data migration

#### Scenario: Existing tests pass against the implementation

- **WHEN** `uv run pytest -m "not slow" --cov=omrg` runs
- **THEN** all pre-existing tests MUST pass against the ChromaDB-backed
  implementation with no assertion changes beyond injected-settings plumbing

---

### Requirement: Store selection via configuration

The system SHALL select the vector-store implementation through the
`VECTOR_STORE` setting, defaulting to `lancedb` after the registered LanceDB
qualification gate passes. Settings SHALL be resolved in `config/` and object
construction SHALL occur only in `compose.py` through the registry. Selection
SHALL be a registry lookup, not a branch over store names. The constructed
store SHALL be passed to every consumer by injection, including the codebase
map subsystem.

#### Scenario: Default store is resolved from configuration

- **GIVEN** the LanceDB qualification gate passed
- **AND** `VECTOR_STORE` is not explicitly set
- **AND** no recognised legacy Chroma data requires acknowledgement
- **WHEN** runtime composition occurs
- **THEN** `compose.py` MUST construct embedded LanceDB through the registry

#### Scenario: Unknown store value

- **WHEN** `VECTOR_STORE` names an unregistered implementation
- **THEN** startup MUST fail with a clear error listing registered names

#### Scenario: Store is injected into every consumer

- **WHEN** an operation or subsystem needs vector-store access
- **THEN** it MUST receive the store as a parameter or constructor argument
- **AND** it MUST NOT construct one itself

#### Scenario: Alternate store is selectable by configuration

- **GIVEN** the complete `chroma` optional extra is installed
- **AND** `VECTOR_STORE=chroma` is explicitly set
- **WHEN** runtime composition occurs
- **THEN** `compose.py` MUST resolve Chroma through the registry
- **AND** every consumer MUST receive it through the same injection paths

#### Scenario: Access before composition

- **GIVEN** no vector store has been composed or injected
- **WHEN** a core consumer requests process-wide store access
- **THEN** the accessor MUST fail clearly rather than construct a default

### Requirement: Chroma implementation SHALL accept an injected client

The Chroma vector-store implementation SHALL support an injected client that
conforms to the Chroma client API. The same implementation SHALL serve local
and cloud deployments; pipeline consumers SHALL remain unaware of the client
type.

#### Scenario: Cloud client injection

- **WHEN** the composition root selects cloud mode
- **THEN** the Chroma store SHALL receive the constructed cloud client
- **AND** all collection operations SHALL use that client

#### Scenario: Local client compatibility

- **WHEN** local mode is selected
- **THEN** the existing persistent-client behaviour and tests SHALL remain unchanged

### Requirement: Chroma client construction SHALL keep one import boundary

All Chroma SDK imports and local/cloud client construction SHALL remain in
`core/vectordb/chroma.py`. The composition root SHALL pass resolved primitive
settings into the Chroma factory without importing or constructing a Chroma
SDK client itself.

#### Scenario: Single chromadb import site after cloud support

- **WHEN** production source is searched for direct `chromadb` imports
- **THEN** `core/vectordb/chroma.py` SHALL remain the only matching module

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

### Requirement: Stores expose a durable collection data version

Every registered vector store SHALL expose the data-version capability for a
collection, returning either an opaque durable token or explicit
unavailability. A returned token SHALL change when the collection's rows or
dataset identity change, including overwrite-based schema evolution and
recreation, and SHALL be observable by any process reading the same underlying
data. A numeric version whose history can restart is not sufficient alone.

For LanceDB, the token SHALL combine an OMRG-owned random dataset epoch stored
in current table schema metadata with `table.version`. Ordinary row mutations
SHALL preserve the epoch. Table creation, recreation and every overwrite-based
rebuild SHALL replace it. Version-history timestamps and row counts SHALL NOT
be used as substitutes.

This is distinct from the existing process-local generation counter, which
remains the mechanism for same-process invalidation. A store whose backend
offers no durable version SHALL say so explicitly rather than returning the
process-local counter under a durable name.

#### Scenario: Version advances after a write

- **GIVEN** a collection at durable version v
- **WHEN** rows are written, upserted, or deleted
- **THEN** the durable version SHALL differ from v

#### Scenario: Version is visible across processes

- **GIVEN** process A and process B each hold their own store instance over
  one underlying database
- **AND** both observe durable version v for a collection
- **WHEN** A performs a successful mutation
- **THEN** B SHALL observe a different durable version without any
  inter-process signalling
- **AND** B's process-local generation counter MAY remain unchanged

#### Scenario: Overwrite and recreation cannot collide

- **GIVEN** a cached Lance token containing epoch E and numeric version v
- **WHEN** schema evolution rebuilds the table with overwrite, or the table is
  deleted and recreated, and its numeric version later equals v
- **THEN** the rebuilt table MUST carry a new epoch distinct from E
- **AND** the complete durable token MUST differ from the cached token

#### Scenario: Cleanup does not erase identity

- **GIVEN** a Lance table carrying an OMRG dataset epoch
- **WHEN** old versions are pruned through cleanup or optimisation
- **THEN** the current table MUST retain the same epoch
- **AND** the next ordinary mutation MUST still change the complete token

#### Scenario: Existing table acquires identity on its next write

- **GIVEN** a pre-existing Lance table without an OMRG dataset epoch
- **WHEN** it is read without mutation
- **THEN** the durable-version capability MUST report unavailable and MUST NOT
  mutate the table
- **WHEN** an OMRG-controlled writer next mutates it under the write lock
- **THEN** the writer MUST install an epoch before the row mutation
- **AND** readers MUST treat the change from local fallback to durable token as
  cache invalidation

#### Scenario: Version is stable without mutation

- **GIVEN** a collection with no mutation between two reads
- **WHEN** the durable version is read twice
- **THEN** both reads SHALL return the same value

#### Scenario: Absent collection

- **WHEN** the durable version of a collection that does not exist is
  requested
- **THEN** the store SHALL report absence rather than raising

#### Scenario: Long-lived readers observe recreation

- **GIVEN** process A holds an open Lance store and has observed token T
- **WHEN** process B rebuilds or recreates that collection with a new epoch
- **THEN** A's next data-version read MUST observe a token different from T
- **AND** A MUST NOT require a process restart

#### Scenario: Unsupported backends are explicit

- **GIVEN** a store whose backend exposes no durable version
- **WHEN** the durable version is requested
- **THEN** the store SHALL report the capability as unavailable
- **AND** callers SHALL fall back to the process-local counter with the
  reduced guarantee stated in their own contract

### Requirement: Stores provide bounded filtered row reads

The vector-store abstraction SHALL provide a store-neutral operation that
returns rows matching metadata equality filters without scanning the whole
collection. Both registered adapters SHALL implement the same result and
absence semantics.

#### Scenario: Source-scoped rows are returned

- **GIVEN** rows for multiple sources in one collection
- **WHEN** rows are requested with `source_id = S`
- **THEN** only rows for S SHALL be returned
- **AND** their persisted lineage metadata SHALL be preserved

#### Scenario: Filtered reads are bounded

- **WHEN** a filtered read selects one source from a many-source collection
- **THEN** the adapter SHALL push the filter into the backend
- **AND** SHALL NOT materialise every collection row in Python

#### Scenario: Adapters agree

- **WHEN** the differential store-contract tests exercise a supported equality
  filter, an absent collection and no matches
- **THEN** LanceDB and Chroma SHALL expose equivalent public behaviour

