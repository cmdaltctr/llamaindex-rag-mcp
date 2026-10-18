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
exactly equal the number of vectors. `write_nodes` SHALL use the identity of
the embedder that produced the batch: the identity that the caller supplies
for the write, or the store's composed embedding identity when the caller
supplies none. A direct `upsert_precomputed` caller SHALL supply the
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

#### Scenario: A profile write reports the profile's model

- **GIVEN** a store composed with model A
- **AND** a caller writes nodes embedded with model B and supplies the identity of model B
- **WHEN** a vector in the batch is malformed
- **THEN** the diagnostic MUST name model B
- **AND** the diagnostic MUST NOT name model A

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

### Requirement: The write stamp follows the embedder used

When a caller supplies an embedding identity to `write_nodes`, the store SHALL check and stamp the collection with that identity, not with its composed identity. The check SHALL complete before any backend mutation. A collection with no stamp SHALL receive the supplied identity on its first write. A stamped collection whose stamp differs SHALL refuse the batch. When the caller supplies none, the store SHALL keep its composed identity.

#### Scenario: A new collection is stamped with the profile's model

- **GIVEN** a store composed with model A
- **AND** collection `fresh` does not exist
- **WHEN** a caller writes nodes into `fresh` with the identity of model B
- **THEN** `fresh` SHALL be stamped with model B

#### Scenario: A stamped collection refuses another model before mutation

- **GIVEN** collection `papers` is stamped with model A
- **WHEN** a caller writes nodes into `papers` with the identity of model B
- **THEN** the write SHALL fail before any backend mutation
- **AND** no row from the batch SHALL persist
- **AND** the collection generation SHALL NOT advance
- **AND** the message SHALL name model A and model B

#### Scenario: A write without a supplied identity keeps today's rule

- **GIVEN** a store composed with model A
- **WHEN** a caller writes nodes without a supplied identity
- **THEN** the store SHALL check and stamp with model A

#### Scenario: Both backends follow the supplied identity

- **WHEN** the stamp tests run against ChromaDB and LanceDB
- **THEN** each backend SHALL stamp the supplied identity on a new collection
- **AND** each backend SHALL refuse a supplied identity that differs from the stamp

### Requirement: The model stamp is checked before embedding and before shape validation

A `VectorStore.write_nodes` call SHALL compare the active embedding identity with the stamp of an existing collection before it embeds any node and before it validates any vector shape. A mismatch SHALL raise the identity-mismatch error that names the stamped model and the active model. The check SHALL be read-only: it SHALL NOT create a collection, stamp a legacy collection, install a dataset epoch or advance the collection generation. A collection with no stamp, a collection that does not exist, and a store with no active identity SHALL pass the check. The write SHALL still stamp a legacy collection after the vectors pass validation, as today. Both ChromaDB and LanceDB SHALL apply this rule.

#### Scenario: A model of another vector size meets a stamped collection

- **GIVEN** a collection is stamped with model A and holds vectors of size 1024
- **AND** the active model B makes vectors of size 768
- **WHEN** `write_nodes` receives nodes without vectors
- **THEN** the write MUST fail with the identity-mismatch error that names A and B
- **AND** the error MUST NOT be a vector-size error
- **AND** the embedder MUST NOT be called
- **AND** no row MUST persist and the collection generation MUST NOT advance

#### Scenario: A model of the same vector size meets a stamped collection

- **GIVEN** a collection is stamped with model A
- **AND** the active model B makes vectors of the same size
- **WHEN** `write_nodes` receives nodes
- **THEN** the write MUST fail with the identity-mismatch error that names A and B
- **AND** the embedder MUST NOT be called

#### Scenario: A legacy collection without a stamp is still stamped after the write

- **GIVEN** a collection holds vectors and has no stamp
- **WHEN** `write_nodes` receives valid nodes
- **THEN** the early check MUST pass without changing the collection
- **AND** the write MUST stamp the collection with the active identity after validation

#### Scenario: A new collection passes the check

- **GIVEN** the collection does not exist
- **WHEN** `write_nodes` receives valid nodes
- **THEN** the early check MUST pass
- **AND** the early check MUST NOT create the collection

#### Scenario: A matching stamp passes the check

- **GIVEN** a collection is stamped with the active model
- **WHEN** `write_nodes` receives valid nodes
- **THEN** the write MUST succeed as it does today

### Requirement: A refused ingest source is not embedded

The ingestion graph SHALL check the target collection's model stamp against the identity of the embedder in use before `embed.chunks` calls the embedder. A mismatch SHALL fail the source with the identity-mismatch error, and no embedding request SHALL be sent for that source. A collection that does not exist or has no stamp SHALL pass the check. The commit step SHALL keep its own check, because a collection can change while a source is embedded.

#### Scenario: A paid provider is not billed for a refused source

- **GIVEN** a collection is stamped with model A
- **AND** an ingest run embeds with model B
- **WHEN** the run reaches `embed.chunks` for a source
- **THEN** the source MUST fail with the identity-mismatch error that names A and B
- **AND** the embedder MUST NOT receive any text

#### Scenario: A stamp that appears during embedding is still refused at commit

- **GIVEN** a collection has no stamp when `embed.chunks` runs
- **AND** another run stamps it with a different model before the commit step
- **WHEN** the commit step writes the source
- **THEN** the write MUST fail with the identity-mismatch error
- **AND** no row MUST persist

#### Scenario: A new collection is embedded as usual

- **GIVEN** the target collection does not exist
- **WHEN** the run reaches `embed.chunks`
- **THEN** the source MUST be embedded
