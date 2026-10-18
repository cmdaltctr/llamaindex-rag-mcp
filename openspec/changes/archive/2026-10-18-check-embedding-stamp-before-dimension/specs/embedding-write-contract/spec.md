## ADDED Requirements

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
