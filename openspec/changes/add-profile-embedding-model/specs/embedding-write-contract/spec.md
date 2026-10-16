# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
