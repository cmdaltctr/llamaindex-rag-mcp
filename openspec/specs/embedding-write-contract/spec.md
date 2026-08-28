# embedding-write-contract Specification

## Purpose

Define a fail-closed structural contract for vectors before each vector-store
write.

## Requirements

### Requirement: Shared structural embedding validation

The system SHALL use one production-core validator before every
`VectorStore.write_nodes` or `VectorStore.upsert_precomputed` mutation. The
validator SHALL inspect the complete batch, and validation SHALL complete
before **any backend SDK or persistent-store mutation** — collection
creation, schema derivation, row conversion, and the SDK write itself
included. Adapter code SHALL invoke the shared validation immediately
before its backend SDK mutation as the enforcement point. The validator
SHALL receive the collection name, embedding provider/model diagnostic,
and stable node or row identifiers. The number of identifiers SHALL
exactly equal the number of vectors. `write_nodes` SHALL use its composed
embedding identity; a direct `upsert_precomputed` caller SHALL supply the
provider/model diagnostic explicitly. Both `write_nodes`-produced embeddings
and valid precomputed vectors SHALL pass through the same rule.

#### Scenario: Valid batch reaches a vector store

- **GIVEN** every vector is non-empty, numeric, finite, and has one shared dimension
- **AND** the collection is absent or has that dimension
- **WHEN** a production write path submits the batch
- **THEN** the validator MUST permit the write
- **AND** the selected adapter MAY persist the complete batch

#### Scenario: Rejected batch does not reach a backend SDK mutation

- **GIVEN** a batch has at least one structural vector error
- **WHEN** any production write path submits the batch
- **THEN** the validator MUST reject the complete batch before any backend SDK or persistent-store mutation
- **AND** no row from that batch MUST persist
- **AND** the collection generation MUST NOT advance because of that batch

#### Scenario: Empty embedding batch is rejected

- **GIVEN** a write path prepares a batch with no embeddings or no nodes
- **WHEN** the batch is submitted
- **THEN** the write MUST fail with the shared diagnostic before any mutation

#### Scenario: Identifier/vector cardinality mismatch is rejected

- **GIVEN** the vector count is smaller or larger than the node or row identifier count
- **WHEN** the batch is submitted
- **THEN** the write MUST fail with the shared diagnostic naming the mismatch
- **AND** no partial write MUST occur

#### Scenario: Direct precomputed write supplies its diagnostic

- **GIVEN** a caller invokes `upsert_precomputed` without a composed embedding identity
- **WHEN** the caller submits vectors
- **THEN** it MUST supply the embedding provider/model diagnostic explicitly
- **AND** validation MUST NOT depend on an optional store identity

### Requirement: Empty vectors are rejected

The validator SHALL reject a batch containing an empty vector. The error SHALL
identify each affected node or row identifier, the collection, and the
embedding provider/model diagnostic.

#### Scenario: Empty vector from an embedding provider

- **GIVEN** one candidate vector has zero elements
- **WHEN** normal ingestion, source replacement, or a precomputed upsert
  prepares the batch
- **THEN** the write MUST fail before any backend SDK or persistent-store mutation
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

### Requirement: Non-finite vector values are rejected

The validator SHALL reject a batch containing a vector element that is not
finite (NaN or infinity). The error SHALL identify the affected node or row
identifiers, the collection, and the embedding provider/model diagnostic.

#### Scenario: NaN or infinity in a candidate vector

- **GIVEN** a candidate vector contains NaN or an infinite value
- **WHEN** a write path validates the batch
- **THEN** the write MUST fail before any adapter mutation
- **AND** the error MUST identify the affected identifier and the non-finite
  element position or index of the vector within the batch

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
collection without exposing backend SDK objects or creating or mutating
backend state. ChromaDB and LanceDB adapters
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
before its precomputed vector-store write and **before deleting or
recreating an existing collection**. It SHALL NOT own an independent
structural-vector validation rule.

#### Scenario: Experiment 14 receives malformed embeddings

- **GIVEN** the Experiment 14 embedder returns a malformed vector batch
- **WHEN** the builder prepares its precomputed upsert
- **THEN** the shared validator MUST stop the write with its standard diagnostic
- **AND** the builder MUST NOT call `delete_collection`, `create_collection`, or `upsert_precomputed`
- **AND** existing Experiment 14 output artefacts MUST remain unchanged

#### Scenario: Experiment 14 validates before destructive rebuild

- **GIVEN** an existing collection is present and the embedder output is malformed
- **WHEN** the builder runs
- **THEN** the shared validation MUST fail before `delete_collection` or `create_collection` executes
- **AND** the existing collection and its contents MUST remain intact

### Requirement: Backend coverage proves the same contract

The test suite SHALL run the structural write contract against ChromaDB and
LanceDB. It SHALL cover direct precomputed writes and the production ingestion
and replacement paths that reach node writes.

#### Scenario: Both backend adapters receive valid vectors only

- **WHEN** the contract suite runs against ChromaDB and LanceDB
- **THEN** each invalid-vector case MUST reject before collection or schema creation, row conversion, SDK mutation, or generation advancement
- **AND** each valid-vector case MUST persist through the selected adapter
