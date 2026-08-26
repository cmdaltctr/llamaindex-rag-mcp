# embedding-write-contract Specification

## Purpose

Define a fail-closed structural contract for vectors before each vector-store
write.

## ADDED Requirements

### Requirement: Shared structural embedding validation

The system SHALL use one production-core validator before every
`VectorStore.write_nodes` or `VectorStore.upsert_precomputed` mutation. The
validator SHALL inspect the complete batch before either vector-store adapter
receives a write request. The validator SHALL receive the collection name,
embedding provider/model diagnostic, and stable node or row identifiers.

#### Scenario: Valid batch reaches a vector store

- **GIVEN** every vector is non-empty, numeric, and has one shared dimension
- **AND** the collection is absent or has that dimension
- **WHEN** a production write path submits the batch
- **THEN** the validator MUST permit the write
- **AND** the selected adapter MAY persist the complete batch

#### Scenario: Rejected batch does not reach an adapter

- **GIVEN** a batch has at least one structural vector error
- **WHEN** any production write path submits the batch
- **THEN** the validator MUST reject the complete batch before an adapter write
- **AND** no row from that batch MUST persist
- **AND** the collection generation MUST NOT advance because of that batch

### Requirement: Empty vectors are rejected

The validator SHALL reject a batch containing an empty vector. The error SHALL
identify each affected node or row identifier, the collection, and the
embedding provider/model diagnostic.

#### Scenario: Empty vector from an embedding provider

- **GIVEN** one candidate vector has zero elements
- **WHEN** normal ingestion, source replacement, or a precomputed upsert
  prepares the batch
- **THEN** the write MUST fail before the adapter receives it
- **AND** the error MUST identify the affected identifier

### Requirement: Non-numeric elements are rejected

The validator SHALL reject a batch containing a vector element that is not
numeric. The error SHALL identify the affected node or row identifiers, the
collection, and the embedding provider/model diagnostic.

#### Scenario: Non-numeric vector value

- **GIVEN** a candidate vector contains a non-numeric element
- **WHEN** a write path validates the batch
- **THEN** the write MUST fail before any adapter mutation
- **AND** the error MUST identify the affected identifier

### Requirement: A batch has one dimension

The validator SHALL reject a batch whose candidate vectors have mixed
dimensions. The error SHALL identify affected node or row identifiers and the
observed dimensions.

#### Scenario: Mixed dimensions in one batch

- **GIVEN** candidate vectors have different lengths
- **WHEN** a write path validates the batch
- **THEN** the write MUST fail before collection creation or adapter mutation
- **AND** no valid vector from that batch MUST persist

### Requirement: Existing collection dimension is enforced

The `VectorStore` contract SHALL expose the existing vector dimension for a
collection without exposing backend SDK objects. ChromaDB and LanceDB adapters
SHALL provide this fact from their own backend representations. The shared
validator SHALL reject a candidate batch whose sole dimension conflicts with
that existing dimension.

#### Scenario: Existing collection dimension conflicts

- **GIVEN** a collection has an established vector dimension
- **AND** a candidate batch has a different shared dimension
- **WHEN** a production write path validates the batch
- **THEN** the write MUST fail before an adapter write
- **AND** the error MUST identify the existing and candidate dimensions
- **AND** the existing collection contents MUST remain unchanged

### Requirement: Validation is fail-closed and atomic

The system SHALL validate the complete candidate batch before mutation. It
SHALL NOT filter out invalid vectors and write a valid subset. A rejected batch
SHALL NOT create a collection vector schema or advance collection generation.

#### Scenario: Valid and invalid candidates share a batch

- **GIVEN** one candidate is structurally valid
- **AND** another candidate violates the embedding write contract
- **WHEN** the batch is submitted
- **THEN** no candidate from the batch MUST persist
- **AND** the adapter write operation MUST NOT run
- **AND** collection generation MUST remain unchanged

### Requirement: Experiment 14 reuses production validation

The Experiment 14 index builder SHALL call the shared production validator
before its precomputed vector-store write. It SHALL NOT own an independent
structural-vector validation rule.

#### Scenario: Experiment 14 receives malformed embeddings

- **GIVEN** the Experiment 14 embedder returns a malformed vector batch
- **WHEN** the builder prepares its precomputed upsert
- **THEN** the shared validator MUST stop the write with its standard diagnostic
- **AND** the builder MUST NOT call `upsert_precomputed`

### Requirement: Backend coverage proves the same contract

The test suite SHALL run the structural write contract against ChromaDB and
LanceDB. It SHALL cover direct precomputed writes and the production ingestion
and replacement paths that reach node writes.

#### Scenario: Both backend adapters receive valid vectors only

- **WHEN** the contract suite runs against ChromaDB and LanceDB
- **THEN** each invalid-vector case MUST reject before the backend write seam
- **AND** each valid-vector case MUST persist through the selected adapter
