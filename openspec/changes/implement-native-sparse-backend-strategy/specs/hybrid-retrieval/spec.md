## ADDED Requirements

### Requirement: Concrete sparse backends resolve through one contract
The `bm25` and `native` sparse backend names SHALL resolve through one sparse-query contract. The `auto` value SHALL remain a capability-selection policy and SHALL resolve to a concrete registered backend before query execution.

#### Scenario: BM25 is selected
- **WHEN** the effective sparse backend is `bm25`
- **THEN** hybrid retrieval SHALL execute the registered BM25 implementation

#### Scenario: Native is selected and supported
- **WHEN** the effective sparse backend is `native`
- **AND** the selected vector store supports native sparse queries
- **THEN** hybrid retrieval SHALL execute a real registered native sparse implementation
- **AND** SHALL NOT report an empty placeholder ranking as successful

#### Scenario: Auto resolves to native when supported
- **WHEN** the effective sparse backend is `auto`
- **AND** the selected vector store supports native sparse queries
- **THEN** resolution SHALL select the registered `native` backend before query execution

#### Scenario: Auto resolves to BM25 when native is unsupported
- **WHEN** the effective sparse backend is `auto`
- **AND** the selected vector store does not support native sparse queries
- **THEN** resolution SHALL select the registered `bm25` backend without emitting the explicit-native fallback warning

#### Scenario: Unknown concrete backend is configured
- **WHEN** sparse backend resolution produces an unregistered concrete name
- **THEN** startup SHALL fail and list the registered sparse backend names

### Requirement: Native fallback remains explicit
The system SHALL retain BM25 fallback when native sparse capability is absent or fails safely, and SHALL emit a visible warning before returning results.

#### Scenario: Explicit native is unsupported
- **WHEN** `native` is selected but the selected vector store cannot issue native sparse queries
- **THEN** the system SHALL warn and execute BM25
- **AND** SHALL NOT identify the resulting sparse ranking as native

#### Scenario: Native fails safely at query time
- **WHEN** the selected native backend raises a supported runtime error during a sparse query
- **THEN** the hybrid pipeline SHALL fall back to BM25 for that query
- **AND** SHALL emit the visible fallback warning before returning results
- **AND** SHALL NOT label the resulting sparse ranking as native

#### Scenario: Existing collection has mixed sparse coverage
- **WHEN** native retrieval runs against a collection with partial sparse coverage
- **THEN** every chunk SHALL remain eligible for dense ranking
- **AND** the existing one-shot remediation warning SHALL remain in effect

### Requirement: Native FTS lifecycle is specified and durable
The native sparse implementation on LanceDB SHALL define its full-text-search index lifecycle explicitly: additive initial creation on the stored `text` column, refresh after writes and source replacements, delete and stale-node handling, freshness diagnostics distinct from indexed/unindexed coverage, and failure diagnostics that route to BM25 fallback. After a write, replacement, or deletion, the index SHALL be treated as stale until refresh completes. A native query SHALL NOT return stale index results as successful: it SHALL establish freshness or warn and fall back to BM25. The process-local store generation counter SHALL NOT be used as durable FTS-index maintenance; it SHALL remain a cache-invalidation mechanism for the in-memory BM25 index.

#### Scenario: FTS index is created additively
- **WHEN** native sparse is first used on a collection without an FTS index
- **THEN** index creation SHALL be additive and explicitly triggered
- **AND** the collection SHALL remain queryable throughout

#### Scenario: Mutations make freshness explicit
- **WHEN** chunks are written, a source is replaced, or rows are deleted after an FTS index exists
- **THEN** the FTS index SHALL be considered stale until refresh completes
- **AND** a native query SHALL either establish a fresh state that covers new rows and excludes stale or deleted rows, or warn and fall back to BM25
- **AND** diagnostics SHALL report the resulting fresh, stale, or fallback state

#### Scenario: Partial FTS coverage is distinguishable
- **WHEN** a collection contains both indexed and unindexed rows
- **THEN** diagnostics SHALL distinguish indexed from unindexed coverage
- **AND** unindexed rows SHALL remain eligible in dense rankings

## MODIFIED Requirements

### Requirement: Sparse backend defaults to BM25 for v1
At startup, the system SHALL select the sparse retrieval backend based on the `RETRIEVAL__HYBRID_SPARSE_BACKEND` env var, which SHALL accept `auto`, `native`, or `bm25`. **The default for v1 SHALL be `bm25`.** When `RETRIEVAL__HYBRID_SPARSE_BACKEND=auto`, the system SHALL run capability detection against the **selected vector store** (through its registry capability metadata and a native full-text-search probe) and select `native` or `bm25` accordingly — not against any specific vendor runtime version. When `RETRIEVAL__HYBRID_SPARSE_BACKEND=native` is set explicitly but the selected store cannot issue native sparse queries, the system SHALL log a WARNING and fall back to `bm25` rather than crashing.

#### Scenario: v1 default is bm25
- **GIVEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND` is unset
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL use the BM25 fallback path
- **THEN** no capability detection SHALL be invoked

#### Scenario: Auto-detected native path
- **GIVEN** the selected vector store supports native sparse queries
- **AND** `RETRIEVAL__HYBRID_SPARSE_BACKEND=auto`
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL issue native sparse rankings through the selected store
- **THEN** no in-memory BM25 index SHALL be constructed

#### Scenario: Auto detection falls back when native is unsupported
- **GIVEN** the selected vector store does not support native sparse queries
- **AND** `RETRIEVAL__HYBRID_SPARSE_BACKEND=auto`
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL build or reuse an in-memory BM25 index over the active collection
- **THEN** sparse rankings SHALL come from the BM25 index

#### Scenario: Explicit native override falls back gracefully
- **GIVEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND=native` is set
- **AND** the selected vector store does not support native sparse queries
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL fall back to the BM25 path without crashing

#### Scenario: Manual BM25 override
- **GIVEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND=bm25` is set
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL use the BM25 fallback regardless of native capability detection

### Requirement: Mixed-coverage collections trigger a one-shot warning
When the native sparse path is active and the system detects that some chunks in the active collection lack sparse coverage (on LanceDB, lack full-text-search index coverage; on a sparse-vector store, lack sparse vectors), the system SHALL emit a one-shot WARNING log on the first hybrid query against that collection within the process lifetime. The warning SHALL identify the collection and SHALL include a remediation hint advising re-ingestion or index creation for full hybrid coverage. Subsequent hybrid queries against the same collection within the same process SHALL NOT re-emit the warning. The BM25 path is unaffected because it always indexes every chunk it sees.

#### Scenario: First hybrid query on a partially-covered collection
- **GIVEN** the native sparse path is active
- **AND** a collection contains a mix of covered and uncovered chunks
- **WHEN** the first hybrid query against that collection runs in the process
- **THEN** the system SHALL emit a WARNING-level log naming the collection
- **THEN** the warning SHALL include a remediation hint to re-ingest or create the index

#### Scenario: Subsequent queries on the same collection do not re-warn
- **GIVEN** a previous hybrid query has already emitted the mixed-coverage warning
- **WHEN** another hybrid query runs against the same collection in the same process
- **THEN** the system SHALL NOT emit the mixed-coverage warning again

#### Scenario: BM25 path skips the warning entirely
- **GIVEN** the BM25 fallback path is active
- **WHEN** a hybrid query runs against any collection
- **THEN** the system SHALL NOT emit the mixed-coverage warning

### Requirement: Existing collections are usable without re-ingestion
The system SHALL accept existing collections without forcing a re-ingestion. When the native sparse path is selected and chunks lack sparse coverage (an unindexed row on an FTS backend, or a missing sparse vector on a sparse-vector backend), those chunks SHALL still participate in the dense ranking and SHALL be excluded from the sparse ranking only. RRF SHALL handle the missing-rank case naturally.

#### Scenario: Mixed coverage collection
- **GIVEN** a collection where some chunks have sparse coverage and others do not
- **WHEN** hybrid retrieval runs
- **THEN** all chunks SHALL participate in dense ranking
- **THEN** only covered chunks SHALL participate in sparse ranking
- **THEN** the system SHALL NOT raise on chunks lacking sparse coverage
